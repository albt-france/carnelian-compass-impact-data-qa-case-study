# Data sources, dates and terms

All data was downloaded on 16 November 2026 by `python src/download_data.py` and `python src/fetch_samples.py`
(neutral User-Agent, one request at a time, pauses between requests, cached). Large raw files stay in `data/raw/` and are
not published. Person-level fields (officers, trustees, care-of names, contact details, addresses) are never read.

| Source | What | Access | Terms |
|---|---|---|---|
| Carnelian Ventures website | Published facts on the company and Compass (home, Compass, Technology, About, one blog post) | carnelianventures.com, robots.txt respected | Facts cited as "as stated by Carnelian"; no names of people, no logo, demo form never used |
| IRS Form 990 e-file data via NCCS (Urban Institute) | Part I summary and Part IX functional expenses, tax year 2023 (efile v3.1 parquet) | nccs-efile.s3.us-east-1.amazonaws.com | Built from public IRS e-file data; freely available from NCCS; cite NCCS / Urban Institute |
| Original Form 990 XML returns | 30 returns for the manual check | GivingTuesday 990 data lake (links in the NCCS URL field) | Public IRS filings |
| IRS SOI annual extract of exempt-organization financial data | Processing years 2024 and 2025, Form 990 | irs.gov/pub/irs-soi | US government work, public domain |
| IRS Exempt Organizations Business Master File | EIN, NTEE code, subsection, latest tax period | irs.gov/pub/irs-soi (eo1-eo4) | US government work, public domain |
| ProPublica Nonprofit Explorer API | Cross-check on 160 organisations | projects.propublica.org/nonprofits/api/v2 | CC BY-NC-ND 3.0 US: used to compute agreement rates only; values not republished (kept in data/raw) |
| Charity Commission for England and Wales | Register extract, annual return history, classification | Full register download | Open Government Licence v3.0 |
| EPA Greenhouse Gas Reporting Program | Facilities, parent companies, emissions 2021 and 2023 | Envirofacts API (data.epa.gov/efservice) | US government work, public domain |
| Climate TRACE | US power-sector assets, 2023, emissions and owners | api.climatetrace.org v6 | CC BY 4.0 (attribution: Climate TRACE; we matched assets to EPA plants and aggregated) |
| SBTi Target Dashboard | Company targets and status | files.sciencebasedtargets.org (companies-excel.xlsx) | Public download; raw file not redistributed, only the status of the 26 matched companies |
| SEC EDGAR XBRL frames | Company revenue CY2023 and CY2021 (2 tags) | data.sec.gov/api/xbrl/frames | Public; SEC fair-access policy (6 requests) |

Frameworks cited (definitions only, not copied): GIIN IRIS+; Impact Management Project, five dimensions of impact; usual
nonprofit ratios (program-expense share, fundraising cost per dollar raised, months of reserves, debt ratio).

## Published extracts (data/processed/)

| File | Rows | Content |
|---|---|---|
| us_returns_2023.parquet | 2,032 | 2,000 sampled 501(c)(3) public charities (500 per size band, seed 42), all their 2023 returns |
| us_soi_extract.parquet | 3,972 | SOI extract rows for the same EINs |
| us_sampling_frame.csv | 4 | population by size band (for weighting back to the population) |
| uk_charities.parquet, uk_annual_returns.parquet | 500 / 2,248 | random sample of registered main charities and their return history |
| companies.parquet | 300 | top GHGRP parents, SEC and SBTi matches with review status |
| epa_facility_parents_2023.parquet | facilities x parents | ownership shares, emissions 2021/2023 (no facility names) |
| epa_vs_climatetrace_power_2023.parquet | 1,091 | EPA power plants matched to Climate TRACE assets |
| manual_check_originals.parquet | 30 | values read from the original returns |
| match_review.csv | 30 | manual decisions on fuzzy name matches below 100 |

`data/_hidden_truth.csv` is the answer key of the SIMULATED errors. It is kept so the detection test can be rerun; it was
read only by `src/evaluate_detection.py`, after the checks ran.
