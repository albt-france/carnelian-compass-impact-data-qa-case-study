"""Download every public source into data/raw/ (not published). Polite: neutral User-Agent, one request at a
time, pauses between calls, files cached (a second run downloads nothing).

Usage: python src/download_data.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import RAW, USER_AGENT  # noqa: E402

S = requests.Session()
S.headers["User-Agent"] = USER_AGENT
PAUSE = 1.5

FILES = {
    # IRS SOI annual extract of exempt-organization financial data (public domain)
    "irs/24eoextract990.zip": "https://www.irs.gov/pub/irs-soi/24eoextract990.zip",
    "irs/25eoextract990.zip": "https://www.irs.gov/pub/irs-soi/25eoextract990.zip",
    "irs/25eofinextractdoc.xlsx": "https://www.irs.gov/pub/irs-soi/25eofinextractdoc.xlsx",
    # IRS Exempt Organizations Business Master File, four regional files (public domain)
    **{f"irs/eo{i}.csv": f"https://www.irs.gov/pub/irs-soi/eo{i}.csv" for i in range(1, 5)},
    # NCCS / Urban Institute e-file tables built from IRS Form 990 e-filings: Part I summary, Part IX expenses
    "nccs/F9-P01-T00-SUMMARY-2023.parquet": "https://nccs-efile.s3.us-east-1.amazonaws.com/public/efile_v3_1/F9-P01-T00-SUMMARY-2023.parquet",
    "nccs/F9-P09-T00-EXPENSES-2023.parquet": "https://nccs-efile.s3.us-east-1.amazonaws.com/public/efile_v3_1/F9-P09-T00-EXPENSES-2023.parquet",
    # Charity Commission for England and Wales, full register extract (Open Government Licence v3.0)
    "ccew/publicextract.charity.zip": "https://ccewuksprdoneregsadata1.blob.core.windows.net/data/txt/publicextract.charity.zip",
    "ccew/publicextract.charity_annual_return_history.zip": "https://ccewuksprdoneregsadata1.blob.core.windows.net/data/txt/publicextract.charity_annual_return_history.zip",
    "ccew/publicextract.charity_classification.zip": "https://ccewuksprdoneregsadata1.blob.core.windows.net/data/txt/publicextract.charity_classification.zip",
    # SBTi Target Dashboard export
    "sbti/companies-excel.xlsx": "https://files.sciencebasedtargets.org/production/files/companies-excel.xlsx",
    # SEC XBRL frames: one value per company for calendar year 2023 (data.sec.gov)
    "sec/frames_Revenues_CY2023.json": "https://data.sec.gov/api/xbrl/frames/us-gaap/Revenues/USD/CY2023.json",
    "sec/frames_RevenueFromContract_CY2023.json": "https://data.sec.gov/api/xbrl/frames/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax/USD/CY2023.json",
    "sec/frames_Revenues_CY2021.json": "https://data.sec.gov/api/xbrl/frames/us-gaap/Revenues/USD/CY2021.json",
    "sec/frames_RevenueFromContract_CY2021.json": "https://data.sec.gov/api/xbrl/frames/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax/USD/CY2021.json",
}


def get_file(rel: str, url: str):
    out = RAW / rel
    if out.exists() and out.stat().st_size > 0:
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    print("GET", url)
    with S.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        tmp = out.with_suffix(out.suffix + ".part")
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
        tmp.replace(out)
    time.sleep(PAUSE)


def epa(table: str, year: int):
    """EPA GHGRP via Envirofacts (public domain), paged 10,000 rows at a time."""
    out = RAW / "epa" / f"{table}_{year}.json"
    if out.exists():
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    rows, start = [], 0
    while True:
        url = f"https://data.epa.gov/efservice/{table}/year/=/{year}/rows/{start}:{start + 9999}/JSON"
        print("GET", url)
        r = S.get(url, timeout=300)
        r.raise_for_status()
        batch = r.json()
        rows += batch
        time.sleep(PAUSE)
        if len(batch) < 10000:
            break
        start += 10000
    out.write_text(json.dumps(rows), encoding="utf-8")


def climate_trace(year: int = 2023, sector: str = "power"):
    """Climate TRACE asset-level estimates for US power plants (CC BY 4.0), paged through the public API."""
    out = RAW / "climatetrace" / f"assets_USA_{sector}_{year}.json"
    if out.exists():
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    assets, offset, limit = [], 0, 1000
    while True:
        url = f"https://api.climatetrace.org/v6/assets?countries=USA&sectors={sector}&year={year}&limit={limit}&offset={offset}"
        print("GET", url)
        r = S.get(url, timeout=300)
        r.raise_for_status()
        batch = r.json().get("assets") or []
        assets += batch
        time.sleep(PAUSE)
        if len(batch) < limit:
            break
        offset += limit
    out.write_text(json.dumps(assets), encoding="utf-8")


def main():
    for rel, url in FILES.items():
        get_file(rel, url)
    for y in (2021, 2023):
        epa("pub_dim_facility", y)
        epa("pub_facts_sector_ghg_emission", y)
    climate_trace()
    print("raw data ready in", RAW)


if __name__ == "__main__":
    main()
