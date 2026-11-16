"""SIMULATED: inject 300 known, realistic errors into a COPY of the real tables (seed 42).

The answer key goes to data/_hidden_truth.csv and is read only by src/evaluate_detection.py, after the checks ran.
Ten error types (see docs/DATA_STANDARDS.md):
units, signs, sums, duplicates, fiscal_year, missing_small, outliers_x10, parent_mismatch, currency, stale.

Usage: python src/inject_errors.py   -> data/outputs/tables/injected_*.parquet + data/_hidden_truth.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import ROOT, SEED  # noqa: E402
from prepare import TABLES, derive, load_clean  # noqa: E402

TRUTH = ROOT / "data" / "_hidden_truth.csv"
PLAN = {  # table -> error type -> count  (total 300)
    "us": {"units": 20, "signs": 25, "sums": 30, "fiscal_year": 30, "missing_small": 30, "outliers_x10": 20, "stale": 20, "duplicates": 25},
    "uk": {"signs": 5, "duplicates": 5, "currency": 30, "stale": 10},
    "companies": {"units": 10, "outliers_x10": 10},
    "power": {"parent_mismatch": 30},
}
US_MONEY = ["revenue", "revenue_py", "expenses", "expenses_py", "assets_boy", "assets", "liabilities", "net_assets",
            "exp_total_p9", "exp_program", "exp_management", "exp_fundraising", "contributions", "program_revenue",
            "fundraising_exp_p1", "prof_fundraising_fees", "joint_costs"]


def typo(name: str, rng) -> str:
    """A near-duplicate name: drop a legal suffix, or swap two letters."""
    if not isinstance(name, str) or len(name) < 4:
        return f"{name} "
    for suf in (" INC", " INCORPORATED", " CORP", " CORPORATION", " LIMITED", " LTD"):
        if name.upper().endswith(suf):
            return name[: -len(suf)]
    i = int(rng.integers(1, len(name) - 2))
    return name[:i] + name[i + 1] + name[i] + name[i + 2:]


def main():
    rng = np.random.default_rng(SEED)
    t = load_clean()
    truth, eid = [], 0

    def log(table, rid, etype, field, before, after):
        nonlocal eid
        eid += 1
        truth.append(dict(error_id=f"E{eid:03d}", table=table, record_id=rid, error_type=etype, field=field,
                          original_value=before, injected_value=after))

    # ---------------- US returns
    us = t["us"].copy()
    eligible = us[~us.amended & ~us.ein.duplicated(keep=False)].index.to_numpy()
    small = us.loc[eligible][us.loc[eligible].size_band.str.startswith("S")].index.to_numpy()
    p = PLAN["us"]
    miss_idx = rng.choice(small, p["missing_small"], replace=False)
    rest = np.setdiff1d(eligible, miss_idx)
    n_other = sum(v for k, v in p.items() if k not in ("missing_small",))
    pick = rng.choice(rest, n_other, replace=False)
    groups, start = {}, 0
    for k, v in p.items():
        if k == "missing_small":
            continue
        groups[k], start = pick[start:start + v], start + v
    groups["missing_small"] = miss_idx
    for i in groups["units"]:
        log("us", us.at[i, "record_id"], "units", "all amounts", us.at[i, "revenue"], round(us.at[i, "revenue"] / 1000))
        for c in US_MONEY:
            us.at[i, c] = np.round(us.at[i, c] / 1000)
    for j, i in enumerate(groups["signs"]):
        c = "expenses" if j % 5 < 3 else "assets"
        log("us", us.at[i, "record_id"], "signs", c, us.at[i, c], -us.at[i, c])
        us.at[i, c] = -us.at[i, c]
    for i in groups["sums"]:
        f = 1 + rng.uniform(0.1, 0.4)
        log("us", us.at[i, "record_id"], "sums", "exp_program", us.at[i, "exp_program"], round(us.at[i, "exp_program"] * f))
        us.at[i, "exp_program"] = round(us.at[i, "exp_program"] * f)
    for i in groups["fiscal_year"]:
        before = us.at[i, "period_end"]
        us.at[i, "period_end"] = before + pd.DateOffset(years=1)
        us.at[i, "period_begin"] = us.at[i, "period_begin"] + pd.DateOffset(years=1)
        us.at[i, "tax_pd"] = us.at[i, "period_end"].strftime("%Y%m")
        log("us", us.at[i, "record_id"], "fiscal_year", "period_end", str(before.date()), str(us.at[i, "period_end"].date()))
    for i in groups["missing_small"]:
        log("us", us.at[i, "record_id"], "missing_small", "exp_program/management/fundraising", us.at[i, "exp_program"], None)
        us.loc[i, ["exp_program", "exp_management", "exp_fundraising"]] = np.nan
    for i in groups["outliers_x10"]:
        log("us", us.at[i, "record_id"], "outliers_x10", "revenue", us.at[i, "revenue"], us.at[i, "revenue"] * 10)
        us.at[i, "revenue"] = us.at[i, "revenue"] * 10
    for i in groups["stale"]:
        before = us.at[i, "period_end"]
        us.at[i, "period_end"] = before - pd.DateOffset(years=3)
        us.at[i, "period_begin"] = us.at[i, "period_begin"] - pd.DateOffset(years=3)
        us.at[i, "tax_pd"] = us.at[i, "period_end"].strftime("%Y%m")
        log("us", us.at[i, "record_id"], "stale", "period_end", str(before.date()), str(us.at[i, "period_end"].date()))
    dups = us.loc[groups["duplicates"]].copy()
    dups["name"] = [typo(n, rng) for n in dups.name]
    dups["record_id"] = dups.record_id + "-dup"
    for r in dups.itertuples():
        log("us", r.record_id, "duplicates", "name", None, r.name)
    us = pd.concat([us, dups], ignore_index=True)

    # ---------------- UK charities
    uk = t["uk"].copy()
    p = PLAN["uk"]
    pick = rng.choice(uk.index.to_numpy(), sum(p.values()), replace=False)
    g, start = {}, 0
    for k, v in p.items():
        g[k], start = pick[start:start + v], start + v
    for i in g["signs"]:
        log("uk", uk.at[i, "record_id"], "signs", "latest_expenditure", uk.at[i, "latest_expenditure"], -uk.at[i, "latest_expenditure"])
        uk.at[i, "latest_expenditure"] = -uk.at[i, "latest_expenditure"]
        uk.at[i, "expenditure_usd"] = -uk.at[i, "expenditure_usd"]
    for i in g["currency"]:
        log("uk", uk.at[i, "record_id"], "currency", "income_usd", uk.at[i, "income_usd"], uk.at[i, "latest_income"])
        uk.at[i, "income_usd"] = uk.at[i, "latest_income"]
        uk.at[i, "expenditure_usd"] = uk.at[i, "latest_expenditure"]
    for i in g["stale"]:
        before = uk.at[i, "latest_acc_fin_period_end_date"]
        uk.at[i, "latest_acc_fin_period_end_date"] = before - pd.DateOffset(years=4)
        uk.at[i, "latest_acc_fin_period_start_date"] = uk.at[i, "latest_acc_fin_period_start_date"] - pd.DateOffset(years=4)
        log("uk", uk.at[i, "record_id"], "stale", "latest_acc_fin_period_end_date", str(before.date()),
            str(uk.at[i, "latest_acc_fin_period_end_date"].date()))
    d = uk.loc[g["duplicates"]].copy()
    d["charity_name"] = [typo(n, rng) for n in d.charity_name]
    d["record_id"] = d.record_id + "-dup"
    for r in d.itertuples():
        log("uk", r.record_id, "duplicates", "charity_name", None, r.charity_name)
    uk = pd.concat([uk, d], ignore_index=True)

    # ---------------- companies
    co = t["companies"].copy()
    pick = rng.choice(co[co.co2e_2021.notna()].index.to_numpy(), 20, replace=False)
    for i in pick[:10]:
        log("companies", co.at[i, "record_id"], "units", "co2e_2023", co.at[i, "co2e_2023"], co.at[i, "co2e_2023"] / 1000)
        co.at[i, "co2e_2023"] = co.at[i, "co2e_2023"] / 1000
    for i in pick[10:]:
        log("companies", co.at[i, "record_id"], "outliers_x10", "co2e_2023", co.at[i, "co2e_2023"], co.at[i, "co2e_2023"] * 10)
        co.at[i, "co2e_2023"] = co.at[i, "co2e_2023"] * 10

    # ---------------- power plants: emissions attributed to the wrong parent company
    pw = t["power"].copy()
    pick = rng.choice(pw.index.to_numpy(), 30, replace=False)
    for i in pick:
        donors = pw.epa_parent[pw.epa_parent != pw.at[i, "epa_parent"]].dropna()
        new = donors.iloc[int(rng.integers(len(donors)))]
        log("power", pw.at[i, "record_id"], "parent_mismatch", "epa_parent", pw.at[i, "epa_parent"], new)
        pw.at[i, "epa_parent"] = new

    out = derive({"us": us, "uk": uk, "companies": co, "power": pw})
    for k, v in out.items():
        v.to_parquet(TABLES / f"injected_{k}.parquet", index=False)
    tr = pd.DataFrame(truth)
    tr.to_csv(TRUTH, index=False)
    print("injected", len(tr), "errors:", tr.groupby("error_type").size().to_dict())


if __name__ == "__main__":
    main()
