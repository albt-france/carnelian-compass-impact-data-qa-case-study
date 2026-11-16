"""Two small, polite collections on samples drawn from the processed US returns (seed 42):

1. ProPublica Nonprofit Explorer API, 160 organisations (40 per size band): independent cross-check source.
2. The original e-filed Form 990 XML of 30 returns (stratified by size band) for the manual verification sample.

Only financial fields are kept: names of officers, preparers or contacts in the API/XML are never stored.
Raw responses are cached in data/raw/ (not published). Usage: python src/fetch_samples.py
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import PROCESSED, RAW, SEED, USER_AGENT  # noqa: E402

S = requests.Session()
S.headers["User-Agent"] = USER_AGENT
PAUSE = 2.0
PP_FIELDS = ["tax_prd", "tax_prd_yr", "formtype", "totrevenue", "totfuncexpns", "totassetsend", "totliabend", "totnetassetend", "pdf_url"]


def latest_returns() -> pd.DataFrame:
    r = pd.read_parquet(PROCESSED / "us_returns_2023.parquet")
    return r.sort_values("efiled_at").drop_duplicates("ein", keep="last")


def propublica(n_per_band=40):
    org = latest_returns()
    s = pd.concat([g.sample(n_per_band, random_state=SEED) for _, g in org.groupby("size_band")])
    cache = RAW / "propublica"
    cache.mkdir(parents=True, exist_ok=True)
    rows = []
    for ein in s.ein:
        f = cache / f"{ein}.json"
        if not f.exists():
            r = S.get(f"https://projects.propublica.org/nonprofits/api/v2/organizations/{ein}.json", timeout=60)
            f.write_text(r.text if r.status_code == 200 else json.dumps({"status": r.status_code}), encoding="utf-8")
            time.sleep(PAUSE)
        d = json.loads(f.read_text(encoding="utf-8"))
        fl = d.get("filings_with_data") or []
        if not fl:
            rows.append(dict(ein=ein, pp_status="no filing data"))
        for x in fl:
            rows.append(dict(ein=ein, pp_status="ok", **{f"pp_{k}": x.get(k) for k in PP_FIELDS}))
    out = pd.DataFrame(rows)
    out.to_parquet(RAW / "propublica_sample.parquet", index=False)   # CC BY-NC-ND: kept out of the published data
    print("ProPublica:", out.ein.nunique(), "orgs,", len(out), "filings")


XML_TAGS = {"revenue": "CYTotalRevenueAmt", "expenses": "CYTotalExpensesAmt", "assets": "TotalAssetsEOYAmt",
            "liabilities": "TotalLiabilitiesEOYAmt", "net_assets": "NetAssetsOrFundBalancesEOYAmt"}
P9 = {"exp_total_p9": "TotalAmt", "exp_program": "ProgramServicesAmt", "exp_management": "ManagementAndGeneralAmt",
      "exp_fundraising": "FundraisingAmt"}


def tag(xml: str, name: str):
    m = re.search(rf"<(?:\w+:)?{name}>\s*(-?[\d.]+)\s*</", xml)
    return float(m.group(1)) if m else None


def originals(n_per_band=8):
    org = latest_returns()
    s = pd.concat([g.sample(n_per_band, random_state=SEED + 1) for _, g in org.groupby("size_band")]).head(30)
    cache = RAW / "xml"
    cache.mkdir(parents=True, exist_ok=True)
    rows = []
    for r in s.itertuples():
        f = cache / f"{r.object_id}.xml"
        if not f.exists():
            resp = S.get(r.source_xml, timeout=120)
            f.write_text(resp.text if resp.status_code == 200 else "", encoding="utf-8")
            time.sleep(PAUSE)
        xml = f.read_text(encoding="utf-8")
        rec = dict(ein=r.ein, object_id=r.object_id, size_band=r.size_band, source_xml=r.source_xml, xml_found=bool(xml))
        for k, t in XML_TAGS.items():
            rec[f"doc_{k}"] = tag(xml, t)
        grp = re.search(r"<(?:\w+:)?TotalFunctionalExpensesGrp>(.*?)</(?:\w+:)?TotalFunctionalExpensesGrp>", xml, re.S)
        for k, t in P9.items():
            rec[f"doc_{k}"] = tag(grp.group(1), t) if grp else None
        rows.append(rec)
    pd.DataFrame(rows).to_parquet(PROCESSED / "manual_check_originals.parquet", index=False)
    print("Originals:", len(rows), "returns, XML found:", sum(x["xml_found"] for x in rows))


if __name__ == "__main__":
    originals()
    propublica()
