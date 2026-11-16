"""Score robustness: (1) Monte Carlo on the weights -> rank stability (Kendall tau);
(2) one pillar weight at a time +/-50%; (3) effect of the SIMULATED injected errors on ranks, with and without
the data-quality gate.

Usage: python src/robustness.py -> data/outputs/robustness_*.csv, robustness_summary.json, scores_*.csv
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import kendalltau

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import OUT, SEED  # noqa: E402
from dq.engine import load_rules  # noqa: E402
from inject_errors import TRUTH  # noqa: E402
from prepare import load_clean  # noqa: E402
from run_checks import load_injected  # noqa: E402
from scoring.engine import aggregate, load_config, score_companies, score_nonprofits  # noqa: E402

N_DRAWS = 1000
CONCENTRATION = 20   # Dirichlet(alpha = weight x 20): draws stay around the base weights (sd ~ 0.08-0.1)


def blocked_ids(flags_file: str, holds: bool = True) -> set:
    """Gate v1 = error-severity rules; gate v2 (default) = v1 + rules marked holds_score (added after the audit)."""
    f = pd.read_csv(OUT / flags_file, dtype=str)
    rules = load_rules()
    hold = rules.severity.eq("error") | (holds & rules.get("holds_score", pd.Series(False, index=rules.index)).fillna(False).astype(bool))
    return set(f[f.rule_id.isin(set(rules[hold].id))].record_id)


def reweight(base: pd.DataFrame, cfg: dict, weights: dict) -> pd.Series:
    c = copy.deepcopy(cfg)
    for k, w in weights.items():
        c["pillars"][k]["weight"] = w
    pts = base[[c_ for c_ in base.columns if c_.startswith("p_")]].rename(columns=lambda x: x[2:])
    return aggregate(pts, c).score


def monte_carlo(base: pd.DataFrame, cfg: dict, rng) -> pd.DataFrame:
    names = list(cfg["pillars"])
    w0 = np.array([cfg["pillars"][k]["weight"] for k in names])
    ref = base.score
    ok = ref.notna()
    rows = []
    for i in range(N_DRAWS):
        w = rng.dirichlet(w0 * CONCENTRATION)
        s = reweight(base, cfg, dict(zip(names, w)))
        tau = kendalltau(ref[ok], s[ok]).statistic
        dr = (ref[ok].rank(pct=True) - s[ok].rank(pct=True)).abs() * 100
        top_ref = set(ref[ok].nlargest(int(ok.sum() * 0.1)).index)
        top_new = set(s[ok].nlargest(int(ok.sum() * 0.1)).index)
        rows.append(dict(draw=i, tau=tau, mean_abs_rank_change_pts=dr.mean(), share_within_10pts=(dr <= 10).mean(),
                         top_decile_overlap=len(top_ref & top_new) / len(top_ref), **{f"w_{k}": v for k, v in zip(names, w)}))
    return pd.DataFrame(rows)


def one_at_a_time(base, cfg):
    ref = base.score
    ok = ref.notna()
    rows = []
    for k in cfg["pillars"]:
        for f in (0.5, 1.5):
            w = {n: p["weight"] * (f if n == k else 1) for n, p in cfg["pillars"].items()}
            s = reweight(base, cfg, w)
            both = ok & s.notna()
            rows.append(dict(pillar=k, factor=f, tau=kendalltau(ref[both], s[both]).statistic,
                             scores_lost=int((ok & s.isna()).sum()), scores_gained=int((~ok & s.notna()).sum())))
    return pd.DataFrame(rows)


def error_impact(kind: str, clean: pd.DataFrame, inj_nogate: pd.DataFrame, inj_gate: pd.DataFrame, truth_ids: set) -> pd.DataFrame:
    a = clean.set_index("record_id")[["score", "rank_pct"]]
    b = inj_nogate.set_index("record_id")[["score", "rank_pct", "status"]]
    g = inj_gate.set_index("record_id")[["status"]].rename(columns={"status": "status_gate"})
    m = a.join(b, lsuffix="_clean", rsuffix="_injected", how="inner")
    m = m.join(g, how="left")
    m["injected_error"] = m.index.isin(truth_ids)
    m["rank_change_pts"] = (m.rank_pct_injected - m.rank_pct_clean).abs() * 100
    m["kind"] = kind
    return m.reset_index()


def main():
    rng = np.random.default_rng(SEED)
    cfg_all = load_config()
    clean, inj = load_clean(), load_injected()
    truth = pd.read_csv(TRUTH)
    summary = {}
    for kind, fn, tname in (("nonprofit", score_nonprofits, "us"), ("company", score_companies, "companies")):
        cfg = cfg_all[kind]
        base = fn(clean[tname], cfg_all)
        base_gate = fn(clean[tname], cfg_all, blocked=blocked_ids("flags_clean.csv"))
        base.to_csv(OUT / f"scores_{kind}_nogate.csv", index=False)
        base_gate.to_csv(OUT / f"scores_{kind}.csv", index=False)
        mc = monte_carlo(base, cfg, rng)
        mc.to_csv(OUT / f"robustness_mc_{kind}.csv", index=False)
        oat = one_at_a_time(base, cfg)
        oat.to_csv(OUT / f"robustness_oat_{kind}.csv", index=False)
        inj_nogate = fn(inj[tname], cfg_all)
        inj_gate = fn(inj[tname], cfg_all, blocked=blocked_ids("flags_injected.csv"))
        inj_gate_v1 = fn(inj[tname], cfg_all, blocked=blocked_ids("flags_injected.csv", holds=False))
        ids = set(truth[truth.table == tname].record_id)
        ei = error_impact(kind, base, inj_nogate, inj_gate, ids)
        ei.to_csv(OUT / f"error_impact_{kind}.csv", index=False)
        e = ei[ei.injected_error]
        v1 = error_impact(kind, base, inj_nogate, inj_gate_v1, ids)
        e1 = v1[v1.injected_error]
        summary[kind] = dict(
            scored=int(base.score.notna().sum()), insufficient=int((base.status == "insufficient data").sum()),
            blocked_real=int((base_gate.status == "blocked by data quality").sum()),
            tau_median=float(mc.tau.median()), tau_p05=float(mc.tau.quantile(0.05)),
            mean_abs_rank_change_pts=float(mc.mean_abs_rank_change_pts.median()),
            share_within_10pts=float(mc.share_within_10pts.median()), top_decile_overlap=float(mc.top_decile_overlap.median()),
            injected_records_scored=int(len(e)),
            injected_median_rank_change_pts=float(e.rank_change_pts.median()) if len(e) else None,
            injected_moved_over_10pts=int((e.rank_change_pts > 10).sum()),
            injected_blocked_by_gate=int((e.status_gate == "blocked by data quality").sum()),
            injected_moved_over_10pts_not_blocked=int(((e.rank_change_pts > 10) & (e.status_gate != "blocked by data quality")).sum()),
            gate_v1_moved_over_10pts_not_blocked=int(((e1.rank_change_pts > 10) & (e1.status_gate != "blocked by data quality")).sum()),
            gate_v1_blocked=int((e1.status_gate == "blocked by data quality").sum()),
            others_median_rank_change_pts=float(ei[~ei.injected_error].rank_change_pts.median()),
            others_moved_over_5pts=int((ei[~ei.injected_error].rank_change_pts > 5).sum()))
    (OUT / "robustness_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
