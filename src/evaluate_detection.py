"""Open the hidden answer key (only now, after the checks ran) and measure detection.

recall    = injected errors caught by at least one rule that was not already firing on that record in the real data
precision = share of the NEW alerts created by the injection that point at an injected error
baseline  = alerts the same rules raise on the untouched real data (the review workload, and where real anomalies are)

Usage: python src/evaluate_detection.py  -> data/outputs/detection_by_type.csv, detection_by_rule.csv, detection_detail.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import OUT  # noqa: E402
from inject_errors import TRUTH  # noqa: E402

DESIGNED = {  # rules written with each error type in mind (others may catch it too)
    "units": ["ACC-01", "ACC-02", "ACC-03", "CONS-09", "CONS-08"],
    "signs": ["VAL-01", "VAL-02", "VAL-06", "VAL-08"],
    "sums": ["CONS-01"],
    "duplicates": ["UNIQ-01", "UNIQ-03"],
    "fiscal_year": ["VAL-05", "ACC-04"],
    "missing_small": ["COMP-02"],
    "outliers_x10": ["CONS-04", "ACC-01", "CONS-08"],
    "parent_mismatch": ["ACC-07"],
    "currency": ["VAL-07"],
    "stale": ["FRESH-01", "FRESH-03"],
}
LABELS = {"units": "Units (thousands)", "signs": "Negative amounts", "sums": "Parts do not add up", "duplicates": "Duplicates",
          "fiscal_year": "Fiscal year shifted", "missing_small": "Missing (small orgs)", "outliers_x10": "Outliers x10",
          "parent_mismatch": "Wrong parent company", "currency": "GBP treated as USD", "stale": "Stale filing used"}


def base_id(rid: str) -> str:
    return rid[:-4] if rid.endswith("-dup") else rid


def main():
    truth = pd.read_csv(TRUTH)
    fc = pd.read_csv(OUT / "flags_clean.csv", dtype=str)
    fi = pd.read_csv(OUT / "flags_injected.csv", dtype=str)
    rules = pd.read_csv(OUT / "rule_results.csv")
    sev = rules.set_index("id").severity
    base = set(zip(fc.rule_id, fc.record_id))
    new = fi[[(r, x) not in base for r, x in zip(fi.rule_id, fi.record_id)]].copy()
    new = new[new.rule_id.map(sev) != "info"]
    new["base_id"] = new.record_id.map(base_id)
    affected = set(truth.record_id) | {base_id(x) for x in truth.record_id}
    new["hits_injected"] = new.record_id.isin(affected) | new.base_id.isin(affected)
    det = []
    for e in truth.itertuples():
        ids = {e.record_id, base_id(e.record_id)} if e.error_type == "duplicates" else {e.record_id}
        caught = new[new.record_id.isin(ids)]
        det.append(dict(error_id=e.error_id, table=e.table, error_type=e.error_type, record_id=e.record_id,
                        detected=len(caught) > 0, rules=", ".join(sorted(caught.rule_id.unique())),
                        by_designed_rule=bool(set(caught.rule_id) & set(DESIGNED[e.error_type]))))
    det = pd.DataFrame(det)
    det.to_csv(OUT / "detection_detail.csv", index=False)
    rows = []
    for t, g in det.groupby("error_type"):
        nd = new[new.rule_id.isin(DESIGNED[t])]
        rows.append(dict(error_type=t, label=LABELS[t], tables=", ".join(sorted(g.table.unique())), injected=len(g),
                         detected=int(g.detected.sum()), recall=g.detected.mean(),
                         designed_rules=", ".join(DESIGNED[t]),
                         new_alerts_designed_rules=len(nd), precision=nd.hits_injected.mean() if len(nd) else float("nan"),
                         baseline_alerts_real_data=int(fc[fc.rule_id.isin(DESIGNED[t])].shape[0])))
    bt = pd.DataFrame(rows).sort_values("recall")
    bt.to_csv(OUT / "detection_by_type.csv", index=False)
    br = (new.groupby("rule_id").agg(new_alerts=("record_id", "size"), on_injected=("hits_injected", "sum"))
          .assign(precision=lambda d: d.on_injected / d.new_alerts).reset_index())
    br["baseline_alerts_real_data"] = br.rule_id.map(fc.groupby("rule_id").size()).fillna(0).astype(int)
    br.to_csv(OUT / "detection_by_rule.csv", index=False)
    print(f"recall {det.detected.mean():.1%} ({det.detected.sum()}/{len(det)}) | new alerts {len(new)}, precision {new.hits_injected.mean():.1%}")
    print(bt[["error_type", "injected", "detected", "recall", "precision", "baseline_alerts_real_data"]].to_string(index=False))


if __name__ == "__main__":
    main()
