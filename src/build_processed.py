"""Turn the raw public files into small, analysis-ready extracts in data/processed/.

Privacy by design: person-level fields (care-of names, officers, trustees, contact details, addresses) are never
read (`usecols`), so they never enter the pipeline. Facility names are used for matching only and not saved.

Usage: python src/build_processed.py
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from rapidfuzz import fuzz, process

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import PROCESSED, RAW, SEED  # noqa: E402

RNG = np.random.default_rng(SEED)
PERSONAL_NAME_PATTERN = r"\bFAMILY\b|\bMEMORIAL\b|\bESTATE OF\b|\bIN MEMORY\b|\bIN HONOR\b"
SIZE_BANDS = [0, 500_000, 5_000_000, 50_000_000, np.inf]
SIZE_LABELS = ["S <$0.5m", "M $0.5-5m", "L $5-50m", "XL >$50m"]
N_PER_BAND = 500


def num(s):
    return pd.to_numeric(s, errors="coerce")


# ------------------------------------------------------------------ US nonprofits
def bmf() -> pd.DataFrame:
    cols = ["EIN", "NAME", "STATE", "SUBSECTION", "FOUNDATION", "RULING", "NTEE_CD", "TAX_PERIOD",
            "ASSET_AMT", "INCOME_AMT", "REVENUE_AMT", "FILING_REQ_CD"]
    b = pd.concat([pd.read_csv(RAW / f"irs/eo{i}.csv", usecols=cols, dtype=str) for i in range(1, 5)])
    b["EIN"] = b.EIN.str.zfill(9)
    return b.drop_duplicates("EIN")


def nccs() -> pd.DataFrame:
    p1 = ["OBJECTID", "ORG_EIN", "ORG_NAME_L1", "RETURN_TYPE", "RETURN_AMENDED_X", "RETURN_GROUP_X", "RETURN_PARTIAL_X",
          "RETURN_TAXPER_DAYS", "RETURN_TIME_STAMP", "TAX_PERIOD_BEGIN_DATE", "TAX_PERIOD_END_DATE", "TAX_YEAR", "URL",
          "F9_01_ACT_GVRN_EMPL_TOT", "F9_01_REV_CONTR_TOT_CY", "F9_01_REV_PROG_TOT_CY", "F9_01_REV_TOT_CY", "F9_01_REV_TOT_PY",
          "F9_01_EXP_PROF_FUNDR_TOT_CY", "F9_01_EXP_FUNDR_TOT_CY", "F9_01_EXP_TOT_CY", "F9_01_EXP_TOT_PY",
          "F9_01_NAFB_ASSET_TOT_BOY", "F9_01_NAFB_ASSET_TOT_EOY", "F9_01_NAFB_LIAB_TOT_EOY", "F9_01_NAFB_TOT_EOY"]
    a = pq.read_table(RAW / "nccs/F9-P01-T00-SUMMARY-2023.parquet", columns=p1).to_pandas()
    a = a[a.RETURN_TYPE == "990"]
    p9 = ["OBJECTID", "F9_09_EXP_TOT_TOT", "F9_09_EXP_TOT_PROG", "F9_09_EXP_TOT_MGMT", "F9_09_EXP_TOT_FUNDR", "F9_09_EXP_JOINT_COST_TOT"]
    b = pq.read_table(RAW / "nccs/F9-P09-T00-EXPENSES-2023.parquet", columns=p9).to_pandas()
    m = a.merge(b, on="OBJECTID", how="left")
    ren = {"OBJECTID": "object_id", "ORG_EIN": "ein", "ORG_NAME_L1": "name", "RETURN_AMENDED_X": "amended", "RETURN_GROUP_X": "group_return",
           "RETURN_PARTIAL_X": "partial_return", "RETURN_TAXPER_DAYS": "period_days", "RETURN_TIME_STAMP": "efiled_at",
           "TAX_PERIOD_BEGIN_DATE": "period_begin", "TAX_PERIOD_END_DATE": "period_end", "TAX_YEAR": "tax_year", "URL": "source_xml",
           "F9_01_ACT_GVRN_EMPL_TOT": "employees", "F9_01_REV_CONTR_TOT_CY": "contributions", "F9_01_REV_PROG_TOT_CY": "program_revenue",
           "F9_01_REV_TOT_CY": "revenue", "F9_01_REV_TOT_PY": "revenue_py", "F9_01_EXP_PROF_FUNDR_TOT_CY": "prof_fundraising_fees",
           "F9_01_EXP_FUNDR_TOT_CY": "fundraising_exp_p1", "F9_01_EXP_TOT_CY": "expenses", "F9_01_EXP_TOT_PY": "expenses_py",
           "F9_01_NAFB_ASSET_TOT_BOY": "assets_boy", "F9_01_NAFB_ASSET_TOT_EOY": "assets", "F9_01_NAFB_LIAB_TOT_EOY": "liabilities",
           "F9_01_NAFB_TOT_EOY": "net_assets", "F9_09_EXP_TOT_TOT": "exp_total_p9", "F9_09_EXP_TOT_PROG": "exp_program",
           "F9_09_EXP_TOT_MGMT": "exp_management", "F9_09_EXP_TOT_FUNDR": "exp_fundraising", "F9_09_EXP_JOINT_COST_TOT": "joint_costs"}
    m = m.rename(columns=ren)[list(ren.values())]
    for c in ["period_days", "employees", "contributions", "program_revenue", "revenue", "revenue_py", "prof_fundraising_fees",
              "fundraising_exp_p1", "expenses", "expenses_py", "assets_boy", "assets", "liabilities", "net_assets", "exp_total_p9",
              "exp_program", "exp_management", "exp_fundraising", "joint_costs"]:
        m[c] = num(m[c])
    for c in ["amended", "group_return", "partial_return"]:
        m[c] = m[c].eq("TRUE")
    return m


def soi(eins: set) -> pd.DataFrame:
    keep = ["EIN", "tax_pd", "totrevenue", "totfuncexpns", "totassetsend", "totliabend", "totnetassetend",
            "sepindaudfinstmtcd", "noemplyeesw3cnt"]
    out = []
    for yr in (24, 25):
        with zipfile.ZipFile(RAW / f"irs/{yr}eoextract990.zip") as z:
            f = z.open(z.infolist()[0])
            d = pd.read_csv(f, dtype=str, usecols=lambda c: c in keep or c.lower() in [k.lower() for k in keep])
        d.columns = [c if c == "EIN" else c.lower() for c in d.columns]
        d["EIN"] = d.EIN.str.zfill(9)
        d = d[d.EIN.isin(eins)].copy()
        d["processing_year"] = 2000 + yr
        out.append(d)
    s = pd.concat(out).rename(columns={"EIN": "ein"})
    for c in ["totrevenue", "totfuncexpns", "totassetsend", "totliabend", "totnetassetend", "noemplyeesw3cnt"]:
        s[c] = num(s[c])
    s["audited"] = s.sepindaudfinstmtcd.eq("Y")
    return s.drop(columns="sepindaudfinstmtcd")


def build_us():
    m = nccs()
    b = bmf()
    m = m.merge(b.rename(columns={"EIN": "ein"})[["ein", "STATE", "SUBSECTION", "FOUNDATION", "RULING", "NTEE_CD", "TAX_PERIOD",
                                                   "ASSET_AMT", "INCOME_AMT", "REVENUE_AMT"]], on="ein", how="left")
    m = m.rename(columns={"STATE": "state", "SUBSECTION": "subsection", "FOUNDATION": "foundation_code", "RULING": "ruling",
                          "NTEE_CD": "ntee_cd", "TAX_PERIOD": "bmf_tax_period", "ASSET_AMT": "bmf_assets",
                          "INCOME_AMT": "bmf_income", "REVENUE_AMT": "bmf_revenue"})
    for c in ["bmf_assets", "bmf_income", "bmf_revenue"]:
        m[c] = num(m[c])
    # universe: 501(c)(3) public charities, single-entity returns, no name that reads like a person or family
    u = m[(m.subsection == "03") & (~m.foundation_code.isin(["02", "03", "04"])) & (~m.group_return)
          & (~m.name.fillna("").str.upper().str.contains(PERSONAL_NAME_PATTERN, regex=True))]
    first = u.sort_values("efiled_at").drop_duplicates("ein", keep="last")   # one return per EIN to draw the sample
    first = first[first.revenue.notna()]
    first["size_band"] = pd.cut(first.revenue.clip(lower=0), SIZE_BANDS, right=False, labels=SIZE_LABELS).astype(str)
    sample = pd.concat([first[first.size_band == b].sample(N_PER_BAND, random_state=SEED) for b in SIZE_LABELS])
    eins = set(sample.ein)
    # keep every 2023 return of the sampled EINs (amended / duplicate returns are a real-data finding)
    returns = u[u.ein.isin(eins)].merge(sample[["ein", "size_band"]], on="ein")
    returns["ntee_major"] = returns.ntee_cd.str[0]
    returns["ruling_year"] = num(returns.ruling.str[:4])
    returns.drop(columns=["ruling", "subsection", "foundation_code", "group_return"]).to_parquet(PROCESSED / "us_returns_2023.parquet", index=False)
    soi(eins).to_parquet(PROCESSED / "us_soi_extract.parquet", index=False)
    pop = first.groupby("size_band").size().rename("population").reset_index()
    pop.to_csv(PROCESSED / "us_sampling_frame.csv", index=False)
    print("US:", len(returns), "returns,", len(eins), "EINs; population by band:", pop.population.tolist())


# ------------------------------------------------------------------ UK charities
def build_uk(n=500):
    def rd(name, cols):
        with zipfile.ZipFile(RAW / f"ccew/publicextract.{name}.zip") as z:
            return pd.read_csv(z.open(z.infolist()[0]), sep="\t", usecols=cols, dtype=str, quoting=3, on_bad_lines="skip")
    c = rd("charity", ["registered_charity_number", "linked_charity_number", "charity_name", "charity_type",
                       "charity_registration_status", "date_of_registration", "date_of_removal", "charity_reporting_status",
                       "latest_acc_fin_period_start_date", "latest_acc_fin_period_end_date", "latest_income", "latest_expenditure",
                       "charity_insolvent", "charity_in_administration"])
    c = c[(c.linked_charity_number == "0") & (c.charity_registration_status == "Registered")
          & (~c.charity_name.fillna("").str.upper().str.contains(PERSONAL_NAME_PATTERN, regex=True))]
    s = c.sample(n, random_state=SEED).drop(columns="linked_charity_number")
    for col in ["latest_income", "latest_expenditure"]:
        s[col] = num(s[col])
    nums = set(s.registered_charity_number)
    cl = rd("charity_classification", ["registered_charity_number", "linked_charity_number", "classification_type", "classification_description"])
    cl = cl[(cl.registered_charity_number.isin(nums)) & (cl.linked_charity_number == "0") & (cl.classification_type == "What")]
    s = s.merge(cl.groupby("registered_charity_number").classification_description.first().rename("category"), on="registered_charity_number", how="left")
    ar = rd("charity_annual_return_history", ["registered_charity_number", "fin_period_start_date", "fin_period_end_date",
                                              "reporting_due_date", "date_annual_return_received", "date_accounts_received",
                                              "total_gross_income", "total_gross_expenditure", "accounts_qualified"])
    ar = ar[ar.registered_charity_number.isin(nums)].copy()
    for col in ["total_gross_income", "total_gross_expenditure"]:
        ar[col] = num(ar[col])
    s.to_parquet(PROCESSED / "uk_charities.parquet", index=False)
    ar.to_parquet(PROCESSED / "uk_annual_returns.parquet", index=False)
    print("UK:", len(s), "charities,", len(ar), "annual returns")


# ------------------------------------------------------------------ companies (EPA, SEC, SBTi, Climate TRACE)
SUFFIX = r"\b(INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|LLC|L L C|LP|L P|LTD|LIMITED|PLC|HOLDINGS?|GROUP|THE|N A|USA|US|AMERICA|AMERICAS|NORTH)\b"


def norm(s: str) -> str:
    s = re.sub(r"[^A-Z0-9 ]", " ", str(s).upper().replace("&", " AND "))
    s = re.sub(SUFFIX, " ", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_parents(text):
    """'ACME CORP (60%); BETA LLC (40%)' -> [('ACME CORP', 60.0), ('BETA LLC', 40.0)]"""
    if not isinstance(text, str) or not text.strip():
        return []
    out = []
    for part in text.split(";"):
        m = re.match(r"\s*(.*?)\s*\(([\d.]+)%\)\s*$", part)
        out.append((m.group(1), float(m.group(2))) if m else (part.strip(), np.nan))
    return out


def build_companies(n=300):
    em, fac = {}, {}
    for y in (2021, 2023):
        f = pd.DataFrame(json.loads((RAW / f"epa/pub_dim_facility_{y}.json").read_text()))
        e = pd.DataFrame(json.loads((RAW / f"epa/pub_facts_sector_ghg_emission_{y}.json").read_text()))
        em[y] = e.groupby("facility_id").co2e_emission.sum()
        fac[y] = f
    f23 = fac[2023]
    rows = []
    for r in f23.itertuples():
        parents = parse_parents(r.parent_company)
        pct_sum = np.nansum([p for _, p in parents]) if parents else np.nan
        for name, p in parents or [(None, np.nan)]:
            rows.append(dict(facility_id=r.facility_id, state=r.state, naics=r.naics_code, subparts=r.reported_subparts,
                             parent_raw=name, ownership_pct=p, ownership_sum=pct_sum, n_parents=len(parents),
                             co2e_2023=em[2023].get(r.facility_id, np.nan), co2e_2021=em[2021].get(r.facility_id, np.nan),
                             in_2021=r.facility_id in set(fac[2021].facility_id), lat=r.latitude, lon=r.longitude))
    fp = pd.DataFrame(rows)
    fp["parent_key"] = fp.parent_raw.map(lambda s: norm(s) if s else None)
    fp["share"] = (fp.ownership_pct / 100).fillna(1 / fp.n_parents.replace(0, 1))
    fp.to_parquet(PROCESSED / "epa_facility_parents_2023.parquet", index=False)
    g = fp.dropna(subset=["parent_key"]).assign(e23=lambda d: d.co2e_2023 * d.share, e21=lambda d: d.co2e_2021 * d.share)
    comp = g.groupby("parent_key").agg(parent_name=("parent_raw", "first"), n_facilities=("facility_id", "nunique"),
                                       co2e_2023=("e23", "sum"), co2e_2021=("e21", lambda s: s.sum(min_count=1)),
                                       facilities_in_2021=("in_2021", "sum"),
                                       ownership_complete=("ownership_sum", lambda s: float(np.mean(np.isclose(s, 100, atol=0.5))))
                                       ).reset_index()
    comp = comp.sort_values("co2e_2023", ascending=False).head(n).reset_index(drop=True)
    # SEC revenue (XBRL frames, CY2023 and CY2021): two revenue tags, keep the largest value per company
    def frames(year):
        out = []
        for tag in ("Revenues", "RevenueFromContract"):
            d = json.loads((RAW / f"sec/frames_{tag}_CY{year}.json").read_text())
            out += [dict(cik=x["cik"], sec_name=x["entityName"], rev=x["val"], tag=tag) for x in d["data"]]
        return pd.DataFrame(out).sort_values("rev").drop_duplicates("cik", keep="last")
    s23, s21 = frames(2023), frames(2021)
    s23 = s23.merge(s21[["cik", "rev"]].rename(columns={"rev": "rev_2021"}), on="cik", how="left")
    s23["key"] = s23.sec_name.map(norm)
    keys = s23.key.tolist()
    sb = pd.read_excel(RAW / "sbti/companies-excel.xlsx")
    sb["key"] = sb.company_name.map(norm)
    sbk = sb.key.tolist()
    recs = []
    for r in comp.itertuples():
        best = process.extractOne(r.parent_key, keys, scorer=fuzz.token_sort_ratio) if r.parent_key else None
        sbest = process.extractOne(r.parent_key, sbk, scorer=fuzz.token_sort_ratio) if r.parent_key else None
        rec = dict(parent_key=r.parent_key)
        if best and best[1] >= 85:
            x = s23.iloc[best[2]]
            rec.update(sec_cik=int(x.cik), sec_name=x.sec_name, sec_match_score=best[1], revenue_2023=x.rev,
                       revenue_2021=x.rev_2021, revenue_tag=x.tag)
        if sbest and sbest[1] >= 85:
            x = sb.iloc[sbest[2]]
            rec.update(sbti_id=x.sbti_id, sbti_name=x.company_name, sbti_match_score=sbest[1], sbti_location=x.location,
                       sbti_sector=x.sector, sbti_near_term_status=x.near_term_status,
                       sbti_near_term_year=str(x.near_term_target_year), sbti_net_zero_status=x.net_zero_status,
                       sbti_date_updated=str(x.date_updated)[:10])
        recs.append(rec)
    comp = comp.merge(pd.DataFrame(recs), on="parent_key", how="left")
    comp.insert(0, "company_id", [f"C{i + 1:03d}" for i in range(len(comp))])
    # fuzzy matches below 100 go to a human review queue; decisions live in data/processed/match_review.csv
    rv = pd.read_csv(PROCESSED / "match_review.csv")
    for tgt, score_col, cols in (("sec", "sec_match_score", ["sec_cik", "sec_name", "revenue_2023", "revenue_2021", "revenue_tag"]),
                                 ("sbti", "sbti_match_score", [c for c in comp.columns if c.startswith("sbti_") and c != "sbti_match_score"])):
        dec = rv[rv.target == tgt].set_index("company_id").decision
        status = np.where(comp[score_col].isna(), "no candidate",
                          np.where(comp[score_col] >= 100, "auto (exact key)", comp.company_id.map(dec).fillna("pending review")))
        status = pd.Series(status).replace({"accept": "accepted after review", "reject": "rejected after review"})
        comp[f"{tgt}_match_status"] = status.values
        comp.loc[comp[f"{tgt}_match_status"].eq("rejected after review"), cols] = np.nan
    comp.to_parquet(PROCESSED / "companies.parquet", index=False)
    # SBTi file profile (whole file: used for real-data checks, raw rows not redistributed)
    prof = dict(rows=len(sb), duplicate_names=int(sb.company_name.duplicated().sum()),
                missing_sector=int(sb.sector.isna().sum()), missing_location=int(sb.location.isna().sum()),
                near_term_status=sb.near_term_status.value_counts(dropna=False).to_dict(),
                net_zero_status=sb.net_zero_status.value_counts(dropna=False).to_dict(),
                targets_set_without_year=int(((sb.near_term_status == "Targets set") & sb.near_term_target_year.isna()).sum()),
                usa_rows=int((sb.location == "United States of America").sum()))
    (PROCESSED / "sbti_profile.json").write_text(json.dumps(prof, indent=1, default=str), encoding="utf-8")
    print("Companies:", len(comp), "SEC matched", comp.sec_cik.notna().sum(), "SBTi matched", comp.sbti_id.notna().sum())


def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))


def build_epa_vs_ct(max_km=2.0):
    ct = json.loads((RAW / "climatetrace/assets_USA_power_2023.json").read_text())
    c = pd.DataFrame([dict(ct_id=a["Id"], ct_name=a["Name"], ct_type=a["AssetType"], lon=a["Centroid"]["Geometry"][0],
                           lat=a["Centroid"]["Geometry"][1],
                           ct_co2e=sum(e.get("EmissionsQuantity") or 0 for e in a["EmissionsSummary"] if e["Gas"] == "co2e_100yr"),
                           ct_capacity_mw=next((e.get("Capacity") for e in a["EmissionsSummary"]), None),
                           ct_owners="; ".join(o.get("CompanyName") or "" for o in (a.get("Owners") or [])),
                           ct_confidence=next((v[0].get("total_co2e_100yrgwp") for d in (a.get("Confidence") or []) for k, v in d.items() if k == "2023"), None))
                      for a in ct if a.get("Centroid")])
    f = pd.DataFrame(json.loads((RAW / "epa/pub_dim_facility_2023.json").read_text()))
    e = pd.DataFrame(json.loads((RAW / "epa/pub_facts_sector_ghg_emission_2023.json").read_text()))
    f = f[f.reported_subparts.fillna("").str.split(",").map(lambda x: "D" in [s.strip() for s in x])]
    f = f.merge(e.groupby("facility_id").co2e_emission.sum().rename("epa_co2e").reset_index(), on="facility_id", how="left")
    out = []
    clat, clon = c.lat.values, c.lon.values
    for r in f.itertuples():
        d = haversine(r.latitude, r.longitude, clat, clon)
        cand = np.where(d <= max_km)[0]
        if len(cand) == 0:
            out.append(dict(facility_id=r.facility_id, state=r.state, epa_co2e=r.epa_co2e, epa_parent=r.parent_company, match="none"))
            continue
        sc = [fuzz.token_set_ratio(norm(r.facility_name), norm(c.ct_name.iat[i])) for i in cand]
        k = cand[int(np.argmax(np.array(sc) - d[cand] * 5))]
        out.append(dict(facility_id=r.facility_id, state=r.state, epa_co2e=r.epa_co2e, epa_parent=r.parent_company,
                        match="matched", distance_km=round(float(d[k]), 3), name_score=float(max(sc)),
                        ct_id=int(c.ct_id.iat[k]), ct_type=c.ct_type.iat[k], ct_co2e=c.ct_co2e.iat[k],
                        ct_capacity_mw=c.ct_capacity_mw.iat[k], ct_owners=c.ct_owners.iat[k], ct_confidence=c.ct_confidence.iat[k],
                        n_candidates=len(cand)))
    m = pd.DataFrame(out)
    m.to_parquet(PROCESSED / "epa_vs_climatetrace_power_2023.parquet", index=False)
    print("EPA power facilities:", len(m), "matched to Climate TRACE:", (m.match == "matched").sum(), "CT assets:", len(c))


if __name__ == "__main__":
    build_us()
    build_uk()
    build_companies()
    build_epa_vs_ct()
