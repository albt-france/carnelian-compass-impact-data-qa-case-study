"""Build the four analysis tables the checks and the scores run on, from data/processed/.

us        one row per US Form 990 return (tax year 2023), joined with the IRS SOI extract and the IRS BMF
uk        one row per UK registered charity, joined with its latest annual return
companies one row per GHGRP parent company (top 300), with SEC revenue and SBTi status
power     one row per GHGRP power plant matched to a Climate TRACE asset

`derive()` recomputes every derived column, so it is run again after errors are injected.
Usage: python src/prepare.py   -> data/outputs/tables/clean_*.parquet
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from rapidfuzz import fuzz

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_processed import norm, parse_parents  # noqa: E402
from config import OUT, PROCESSED  # noqa: E402

AS_OF = pd.Timestamp("2026-11-16")
FX_USD_PER_GBP = 1.28
TABLES = OUT / "tables"
NAICS3 = {"221": "Utilities", "211": "Oil & gas extraction", "213": "Oil & gas extraction", "486": "Pipelines",
          "324": "Refining", "325": "Chemicals", "327": "Cement & minerals", "331": "Metals", "322": "Paper",
          "562": "Waste", "212": "Mining", "311": "Food"}


def build_us() -> pd.DataFrame:
    r = pd.read_parquet(PROCESSED / "us_returns_2023.parquet")
    s = pd.read_parquet(PROCESSED / "us_soi_extract.parquet").dropna(subset=["tax_pd"])
    r["period_end"] = pd.to_datetime(r.period_end)
    r["period_begin"] = pd.to_datetime(r.period_begin)
    r["tax_pd"] = r.period_end.dt.strftime("%Y%m")
    # SOI record for the same fiscal period if it exists, else the SOI record closest in time
    s = s.sort_values("processing_year").drop_duplicates(["ein", "tax_pd"], keep="last")
    m = r.merge(s, on=["ein", "tax_pd"], how="left", indicator=True)
    miss = m["_merge"] == "left_only"
    if miss.any():
        alt = r[r.object_id.isin(m.loc[miss, "object_id"])][["object_id", "ein", "tax_pd"]].merge(
            s.rename(columns={"tax_pd": "soi_tax_pd_alt"}), on="ein")
        alt["gap"] = (alt.soi_tax_pd_alt.astype(int) - alt.tax_pd.astype(int)).abs()
        alt = alt.sort_values("gap").drop_duplicates("object_id").drop(columns=["gap", "ein", "tax_pd"])
        m = m.merge(alt.add_suffix("_x").rename(columns={"object_id_x": "object_id"}), on="object_id", how="left")
        for c in ["totrevenue", "totfuncexpns", "totassetsend", "totliabend", "totnetassetend", "audited", "noemplyeesw3cnt", "processing_year"]:
            m[c] = m[c].where(~miss, m[f"{c}_x"])
        m["soi_tax_pd"] = np.where(miss, m["soi_tax_pd_alt_x"], m.tax_pd)
        m = m.drop(columns=[c for c in m.columns if c.endswith("_x")])
    else:
        m["soi_tax_pd"] = m.tax_pd
    m.loc[m.totrevenue.isna() & m.totassetsend.isna(), "soi_tax_pd"] = np.nan
    m = m.drop(columns=["_merge"]).rename(columns={
        "totrevenue": "soi_revenue", "totfuncexpns": "soi_expenses", "totassetsend": "soi_assets", "totliabend": "soi_liabilities",
        "totnetassetend": "soi_net_assets", "noemplyeesw3cnt": "soi_employees", "processing_year": "soi_processing_year"})
    m["audited"] = m.audited.astype("boolean")
    m["bmf_period_end"] = pd.to_datetime(m.bmf_tax_period, format="%Y%m", errors="coerce") + pd.offsets.MonthEnd(0)
    m["record_id"] = m.object_id.astype(str)
    m["source"] = "IRS e-file (NCCS)"
    m["currency"] = "USD"
    return m


def build_uk() -> pd.DataFrame:
    c = pd.read_parquet(PROCESSED / "uk_charities.parquet")
    a = pd.read_parquet(PROCESSED / "uk_annual_returns.parquet")
    for col in ["fin_period_start_date", "fin_period_end_date", "reporting_due_date", "date_annual_return_received", "date_accounts_received"]:
        a[col] = pd.to_datetime(a[col], errors="coerce")
    for col in ["latest_acc_fin_period_start_date", "latest_acc_fin_period_end_date", "date_of_registration"]:
        c[col] = pd.to_datetime(c[col], errors="coerce")
    a = a.sort_values("fin_period_end_date")
    last = a.drop_duplicates("registered_charity_number", keep="last")
    n_returns = a.groupby("registered_charity_number").size().rename("n_annual_returns")
    u = c.merge(last, on="registered_charity_number", how="left").merge(n_returns, on="registered_charity_number", how="left")
    u["record_id"] = "UK" + u.registered_charity_number.astype(str)
    u["currency"] = "GBP"
    u["income_usd"] = u.latest_income * FX_USD_PER_GBP
    u["expenditure_usd"] = u.latest_expenditure * FX_USD_PER_GBP
    u["source"] = "Charity Commission register"
    return u


def build_companies() -> pd.DataFrame:
    c = pd.read_parquet(PROCESSED / "companies.parquet")
    fp = pd.read_parquet(PROCESSED / "epa_facility_parents_2023.parquet").dropna(subset=["parent_key"])
    fp["naics3"] = fp.naics.astype(str).str[:3]
    sec = (fp.assign(w=fp.co2e_2023.fillna(0) * fp.share).groupby(["parent_key", "naics3"]).w.sum()
           .reset_index().sort_values("w").drop_duplicates("parent_key", keep="last"))
    c = c.merge(sec[["parent_key", "naics3"]], on="parent_key", how="left")
    c["sector"] = c.naics3.map(NAICS3).fillna("Other industry")
    c["record_id"] = c.company_id
    c["emissions_unit"] = "tCO2e"
    return c


def build_power() -> pd.DataFrame:
    p = pd.read_parquet(PROCESSED / "epa_vs_climatetrace_power_2023.parquet")
    p = p[p.match == "matched"].copy()
    p["record_id"] = "F" + p.facility_id.astype(str)
    return p


def derive(t: dict) -> dict:
    """Derived columns used by rules and scores; recomputed after any change to the base columns."""
    us = t["us"]
    us["name_key"] = us.name.map(norm)
    us["period_days_calc"] = (us.period_end - us.period_begin).dt.days + 1
    us["years_since_period_end"] = (AS_OF - us.period_end).dt.days / 365.25
    uk = t["uk"]
    uk["years_since_period_end"] = (AS_OF - uk.latest_acc_fin_period_end_date).dt.days / 365.25
    co = t["companies"]
    co["intensity_t_per_musd"] = co.co2e_2023 / (co.revenue_2023 / 1e6)
    co["emissions_change"] = co.co2e_2023 / co.co2e_2021 - 1
    co["co2e_per_facility"] = co.co2e_2023 / co.n_facilities
    pw = t["power"]

    def sim(a, b):
        pa = [norm(n) for n, _ in parse_parents(a)] if isinstance(a, str) else []
        pb = [norm(x) for x in str(b).split(";") if x.strip()] if isinstance(b, str) else []
        return max([fuzz.token_set_ratio(x, y) for x in pa for y in pb] or [np.nan])
    pw["parent_owner_similarity"] = [sim(a, b) for a, b in zip(pw.epa_parent, pw.ct_owners)]
    pw["ct_to_epa_ratio"] = pw.ct_co2e / pw.epa_co2e
    return t


def load_clean() -> dict:
    return {k: pd.read_parquet(TABLES / f"clean_{k}.parquet") for k in ("us", "uk", "companies", "power")}


def main():
    TABLES.mkdir(parents=True, exist_ok=True)
    t = derive({"us": build_us(), "uk": build_uk(), "companies": build_companies(), "power": build_power()})
    for k, v in t.items():
        v.to_parquet(TABLES / f"clean_{k}.parquet", index=False)
        print(k, v.shape)


if __name__ == "__main__":
    main()
