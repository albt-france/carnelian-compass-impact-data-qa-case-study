"""Demo scoring engine (illustrative, not Carnelian's methodology).

Pipeline: raw metrics -> caps -> peer-group percentile (mid-rank) -> 0-100 points (direction-aware)
-> pillar = mean of available metric points -> score = weighted mean of available pillars, re-weighted.
Missing data is never a zero: a missing metric is skipped, and below `min_coverage` no score is published.
A data-quality gate withholds scores for records with an error-severity flag.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

CONFIG = Path(__file__).with_name("config.yaml")


def load_config() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def metric_directions(cfg: dict) -> dict:
    return {m: d for p in cfg["pillars"].values() for m, d in p["metrics"].items()}


def cap(m: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    m = m.copy()
    for k, (lo, hi) in cfg["caps"].items():
        if k in m:
            m[k] = m[k].clip(lo, hi).round(6)   # rounded so ties are exact (same rule in the Excel golden set)
    return m


def midrank_pct(values: pd.Series, groups: pd.Series) -> pd.Series:
    """Percentile = (count below + 0.5 x count equal) / count with data, within the group. Same formula as the
    Excel golden set: (COUNTIFS(<x) + 0.5*COUNTIFS(=x)) / COUNTIFS(<>"")."""
    out = pd.Series(np.nan, index=values.index)
    for _, idx in values.groupby(groups).groups.items():
        v = values.loc[idx]
        ok = v.dropna()
        if ok.empty:
            continue
        s = np.sort(ok.values)
        below = np.searchsorted(s, ok.values, side="left")
        equal = np.searchsorted(s, ok.values, side="right") - below
        out.loc[ok.index] = (below + 0.5 * equal) / len(s)
    return out


def peer_key(primary: pd.Series, fallback: pd.Series, min_size: int) -> pd.Series:
    k = primary.fillna("?") + "|" + fallback.astype(str)
    n = k.map(k.value_counts())
    return np.where((n >= min_size) & primary.notna(), k, "ALL|" + fallback.astype(str))


def points(m: pd.DataFrame, peers: pd.Series, cfg: dict) -> pd.DataFrame:
    out = pd.DataFrame(index=m.index)
    fixed = set(cfg.get("fixed_scale", []))
    for k, direction in metric_directions(cfg).items():
        if k in fixed:
            out[k] = m[k]
            continue
        p = midrank_pct(m[k], pd.Series(peers, index=m.index))
        out[k] = 100 * (p if direction == "higher" else 1 - p)
    return out


def aggregate(pts: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    res = pd.DataFrame(index=pts.index)
    wsum = pd.Series(0.0, index=pts.index)
    acc = pd.Series(0.0, index=pts.index)
    for name, p in cfg["pillars"].items():
        res[name] = pts[list(p["metrics"])].mean(axis=1, skipna=True)
        has = res[name].notna()
        wsum += np.where(has, p["weight"], 0.0)
        acc += np.where(has, p["weight"] * res[name].fillna(0), 0.0)
    total_w = sum(p["weight"] for p in cfg["pillars"].values())
    res["coverage"] = wsum / total_w
    res["score"] = np.where(res.coverage >= cfg["min_coverage"], acc / wsum.replace(0, np.nan), np.nan)
    res["status"] = np.where(res.score.notna(), "scored", "insufficient data")
    return res


# ------------------------------------------------------------------ nonprofits
def latest_per_org(us: pd.DataFrame) -> pd.DataFrame:
    """Uniqueness fix (UNIQ-01): keep the latest e-filed return per EIN."""
    return us.sort_values(["efiled_at", "record_id"]).drop_duplicates("ein", keep="last").copy()


def size_band(revenue_usd: pd.Series, cfg: dict) -> pd.Series:
    return pd.cut(revenue_usd.clip(lower=0), cfg["size_bands"] + [np.inf], right=False, labels=cfg["size_labels"]).astype(str)


def nonprofit_metrics(d: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    fx = np.where(d.get("currency", "USD") == "GBP", cfg["fx_usd_per_gbp"], 1.0)
    days = (d.period_end - d.period_begin).dt.days + 1
    annual = np.where((days > 0) & ~days.between(360, 371), 365 / days, 1.0)   # 18-month or short years
    exp_annual = d.expenses * annual
    m = pd.DataFrame(index=d.index)
    m["reserves_months"] = np.where(exp_annual > 0, d.net_assets / (exp_annual / 12), np.nan)
    m["debt_ratio"] = np.where(d.assets > 0, d.liabilities / d.assets, np.nan)
    m["program_share"] = np.where(d.exp_total_p9 > 0, d.exp_program / d.exp_total_p9, np.nan)
    m["fundraising_cost"] = np.where(d.contributions > 0, d.exp_fundraising / d.contributions, np.nan)
    m["revenue_change"] = np.where((d.revenue_py > 0) & (d.revenue >= 0), (d.revenue / d.revenue_py - 1).abs(), np.nan)
    audited = d.audited.astype("float") if "audited" in d else np.nan
    deadline = d.period_end + pd.DateOffset(months=10) + pd.DateOffset(days=15)
    timely = np.where(d.efiled_at.notna(), (pd.to_datetime(d.efiled_at, utc=True).dt.tz_localize(None) <= deadline).astype(float), np.nan)
    m["transparency"] = pd.concat([pd.Series(audited, index=d.index), pd.Series(timely, index=d.index)], axis=1).mean(axis=1)
    m["revenue_usd"] = d.revenue * fx
    return m


def score_nonprofits(us: pd.DataFrame, cfg: dict | None = None, blocked: set | None = None) -> pd.DataFrame:
    cfg = (cfg or load_config())["nonprofit"] if "nonprofit" in (cfg or load_config()) else cfg
    org = latest_per_org(us)
    m = cap(nonprofit_metrics(org, cfg), cfg)
    org["size_band_calc"] = size_band(m.revenue_usd, cfg)
    peers = peer_key(org.ntee_major, org.size_band_calc, cfg["peer_min_size"])
    pts = points(m, peers, cfg)
    res = aggregate(pts, cfg)
    out = pd.concat([org[["record_id", "ein", "ntee_major", "size_band_calc"]], m.add_prefix("m_"), pts.add_prefix("p_"), res], axis=1)
    out["peer_group"] = peers
    if blocked:
        gate = out.record_id.isin(blocked)
        out.loc[gate, "score"] = np.nan
        out.loc[gate, "status"] = "blocked by data quality"
    out["rank_pct"] = out.score.rank(pct=True)
    return out.reset_index(drop=True)


# ------------------------------------------------------------------ companies
def company_metrics(c: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    m = pd.DataFrame(index=c.index)
    m["intensity_t_per_musd"] = np.where(c.revenue_2023 > 0, c.co2e_2023 / (c.revenue_2023 / 1e6), np.nan)
    m["emissions_change"] = np.where(c.co2e_2021 > 0, c.co2e_2023 / c.co2e_2021 - 1, np.nan)
    m["sbti_points"] = c.sbti_near_term_status.map(cfg["sbti_points"]).fillna(0.0)
    parts = pd.concat([c.revenue_2023.notna().astype(float), (c.co2e_2021 > 0).astype(float),
                       (c.ownership_complete >= 0.999).astype(float), (c.facilities_in_2021 >= c.n_facilities).astype(float)], axis=1)
    m["disclosure_points"] = 100 * parts.mean(axis=1)
    return m


def score_companies(co: pd.DataFrame, cfg: dict | None = None, blocked: set | None = None) -> pd.DataFrame:
    cfg = (cfg or load_config())["company"] if "company" in (cfg or load_config()) else cfg
    m = cap(company_metrics(co, cfg), cfg)
    n = co.sector.map(co.sector.value_counts())
    peers = np.where(n >= cfg["peer_min_size"], co.sector, "ALL")
    pts = points(m, peers, cfg)
    res = aggregate(pts, cfg)
    out = pd.concat([co[["record_id", "sector"]], m.add_prefix("m_"), pts.add_prefix("p_"), res], axis=1)
    if blocked:
        gate = out.record_id.isin(blocked)
        out.loc[gate, "score"] = np.nan
        out.loc[gate, "status"] = "blocked by data quality"
    out["rank_pct"] = out.score.rank(pct=True)
    return out.reset_index(drop=True)
