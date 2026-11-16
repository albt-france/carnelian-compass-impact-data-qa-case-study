"""Source reconciliation (PUBLIC DATA): IRS e-file vs IRS SOI extract vs IRS BMF vs ProPublica, the 30-return manual
check against the original filings, EPA GHGRP vs Climate TRACE, SBTi vs reported emissions, UK register vs returns.

Usage: python src/reconcile.py -> data/outputs/reconciliation_summary.csv + detail files
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import OUT, PROCESSED, RAW  # noqa: E402
from prepare import load_clean  # noqa: E402
from scoring.engine import latest_per_org  # noqa: E402

TOL = 0.01


def rel_gap(a, b):
    return (a - b).abs() / b.abs().clip(lower=1)


def agree(a, b, tol=TOL):
    ok = a.notna() & b.notna()
    return ok.sum(), ((rel_gap(a, b) <= tol) & ok).sum()


def main():
    t = load_clean()
    rows = []

    def add(pair, measure, n, k, note):
        rows.append(dict(source_pair=pair, measure=measure, compared=int(n), agree=int(k), agree_rate=k / n if n else np.nan, note=note))

    org = latest_per_org(t["us"])
    # 1. e-file vs SOI extract
    same = org.soi_tax_pd == org.tax_pd
    for f, s in (("revenue", "soi_revenue"), ("expenses", "soi_expenses"), ("assets", "soi_assets")):
        n, k = agree(org.loc[same, f], org.loc[same, s])
        add("IRS e-file vs IRS SOI extract", f, n, k, "same EIN and fiscal period; tolerance 1%")
    add("IRS e-file vs IRS SOI extract", "fiscal period found", len(org), int(same.sum()), "SOI record for the same fiscal period")
    d = org.loc[same, ["record_id", "size_band", "revenue", "soi_revenue", "assets", "soi_assets"]].copy()
    d["rev_gap"] = rel_gap(d.revenue, d.soi_revenue)
    d["asset_gap"] = rel_gap(d.assets, d.soi_assets)
    d.to_csv(OUT / "recon_irs_soi.csv", index=False)
    # 2. e-file vs BMF: the master file carries the LATEST return, usually a later year
    bp = org.bmf_period_end == org.period_end
    n, k = agree(org.loc[bp, "revenue"], org.loc[bp, "bmf_revenue"])
    add("IRS e-file vs IRS BMF", "revenue (same period only)", n, k, f"BMF shows the same period for {bp.mean():.0%} of orgs only")
    add("IRS e-file vs IRS BMF", "BMF period is more recent", len(org), int((org.bmf_period_end > org.period_end).sum()),
        "share of orgs where a newer return already exists")
    # 3. ProPublica sample
    pp = pd.read_parquet(RAW / "propublica_sample.parquet")   # ProPublica terms (CC BY-NC-ND 3.0 US): values not republished
    pp = pp[pp.pp_status == "ok"].copy()
    pp["tax_pd"] = pp.pp_tax_prd.astype("Int64").astype(str)
    m = org.merge(pp, on=["ein", "tax_pd"], how="inner")
    n_orgs = pp.ein.nunique()
    add("IRS e-file vs ProPublica", "fiscal period found", 160, m.ein.nunique(), f"{n_orgs} of 160 orgs returned filing data")
    for f, s in (("revenue", "pp_totrevenue"), ("expenses", "pp_totfuncexpns"), ("assets", "pp_totassetsend"), ("liabilities", "pp_totliabend")):
        n, k = agree(m[f], pd.to_numeric(m[s]))
        add("IRS e-file vs ProPublica", f, n, k, "same EIN and fiscal period; tolerance 1%")
    flags = m[["record_id", "ein", "size_band"]].copy()   # agreement flags only: ProPublica values are not republished
    for f, s_ in (("revenue", "pp_totrevenue"), ("expenses", "pp_totfuncexpns"), ("assets", "pp_totassetsend")):
        flags[f"{f}_agrees"] = rel_gap(m[f], pd.to_numeric(m[s_])) <= TOL
    flags.to_csv(OUT / "recon_propublica.csv", index=False)
    # 4. manual verification against the original e-filed returns (30, stratified by size)
    mc = pd.read_parquet(PROCESSED / "manual_check_originals.parquet")
    mm = mc.merge(t["us"][["object_id", "revenue", "expenses", "assets", "liabilities", "net_assets", "exp_total_p9", "exp_program",
                           "exp_management", "exp_fundraising"]], on="object_id")
    fields = ["revenue", "expenses", "assets", "liabilities", "net_assets", "exp_total_p9", "exp_program", "exp_management", "exp_fundraising"]
    long = []
    for f in fields:
        ok = (mm[f] - mm[f"doc_{f}"].fillna(0)).abs() <= 1
        long.append(pd.DataFrame({"record_id": mm.object_id, "size_band": mm.size_band, "field": f, "dataset_value": mm[f],
                                  "document_value": mm[f"doc_{f}"], "match": ok, "source_xml": mm.source_xml}))
    long = pd.concat(long)
    long.to_csv(OUT / "manual_check.csv", index=False)
    add("Dataset vs original return (manual sample)", "fields matching", len(long), int(long.match.sum()), "30 returns x 9 fields")
    add("Dataset vs original return (manual sample)", "returns fully matching", 30, int(long.groupby("record_id").match.all().sum()), "")
    # 5. EPA vs Climate TRACE
    pw = t["power"]
    ok = pw[pw.epa_co2e > 0]
    r = ok.ct_to_epa_ratio
    for band in (0.10, 0.25, 0.50):
        add("EPA GHGRP vs Climate TRACE", f"emissions within ±{band:.0%}", len(ok), int(((r - 1).abs() <= band).sum()), "power plants, 2023, CO2e")
    add("EPA GHGRP vs Climate TRACE", "parent vs owner name similarity >= 50", pw.parent_owner_similarity.notna().sum(),
        int((pw.parent_owner_similarity >= 50).sum()), "EPA ultimate parent vs Climate TRACE owner")
    allp = pd.read_parquet(PROCESSED / "epa_vs_climatetrace_power_2023.parquet")
    add("EPA GHGRP vs Climate TRACE", "EPA plants with a Climate TRACE asset within 2 km", len(allp), int((allp.match == "matched").sum()), "")
    ok[["record_id", "state", "ct_type", "epa_co2e", "ct_co2e", "ct_to_epa_ratio", "parent_owner_similarity", "ct_confidence"]].to_csv(
        OUT / "recon_epa_ct.csv", index=False)
    # 6. SBTi vs reported emissions
    co = t["companies"]
    sb = co[co.sbti_id.notna()]
    val = sb[sb.sbti_near_term_status == "Validated Targets"]
    add("SBTi vs EPA-reported emissions", "top-300 emitters found in SBTi", len(co), len(sb), "name match after manual review")
    add("SBTi vs EPA-reported emissions", "validated target and emissions not up >10%", int(val.emissions_change.notna().sum()),
        int((val.emissions_change <= 0.10).sum()), "2021 -> 2023, US direct emissions only")
    add("SEC vs EPA (company identity)", "top-300 emitters matched to an SEC filer", len(co), int(co.sec_cik.notna().sum()),
        "others: private, cooperative, municipal or foreign")
    # 7. UK register vs annual return
    uk = t["uk"]
    n, k = agree(uk.latest_income, uk.total_gross_income, 0)
    add("UK register vs annual return", "latest income", n, k, "exact match")
    s = pd.DataFrame(rows)
    s.to_csv(OUT / "reconciliation_summary.csv", index=False)
    prof = json.loads((PROCESSED / "sbti_profile.json").read_text())
    (OUT / "sbti_file_profile.json").write_text(json.dumps(prof, indent=1), encoding="utf-8")
    print(s[["source_pair", "measure", "compared", "agree_rate"]].to_string(index=False))


if __name__ == "__main__":
    main()
