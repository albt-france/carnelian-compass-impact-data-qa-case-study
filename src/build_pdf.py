"""8-page PDF report (16:9): HTML + inline SVG charts, printed by headless Edge. Every number is read from
data/outputs (pipeline results); none is typed in the text. Usage: python src/build_pdf.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
from jinja2 import Template

sys.path.insert(0, str(Path(__file__).resolve().parent))
import charts as C  # noqa: E402
from config import DOCS, FOOTER, OUT, PROCESSED, ROOT, SEEN_ON, ai_note  # noqa: E402
from dq.engine import load_rules  # noqa: E402
from scoring.engine import load_config  # noqa: E402

TMP = ROOT / ".tmp"
PDF = DOCS / "Carnelian_Compass_impact_data_QA_case_study.pdf"
rd = lambda n: pd.read_csv(OUT / f"{n}.csv")  # noqa: E731

CSS = """
@page { size: 16in 9in; margin: 0 }
* { box-sizing: border-box; margin: 0; padding: 0 }
body { font-family: 'Segoe UI', system-ui, sans-serif; color: #0B0B0B; background: #F4F4F2; }
.page { width: 1536px; height: 864px; padding: 30px 40px 16px; display: flex; flex-direction: column;
        background: #F4F4F2; page-break-after: always; overflow: hidden; position: relative }
header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; min-height: 56px }
h1 { font-size: 24px; font-weight: 700; line-height: 1.2; max-width: 1250px; letter-spacing: -0.2px }
.sub { color: #52514E; font-size: 13.5px; margin-top: 5px; max-width: 1270px; line-height: 1.4 }
.tag { font-size: 11.5px; font-weight: 700; letter-spacing: .8px; color: #52514E; border: 1px solid #C9C7BF;
       border-radius: 4px; padding: 4px 9px; white-space: nowrap; margin-top: 6px; background: #FCFCFB }
.tag.sim { color: #1C5CAB; border-color: #86B6EF } .tag.real { color: #0E7A55; border-color: #8FD3B8 }
.kpis { display: grid; gap: 12px; margin-bottom: 12px }
.card { background: #FCFCFB; border: 1px solid #E1E0D9; border-radius: 8px; padding: 12px 16px; display: flex;
        flex-direction: column; min-height: 0; overflow: hidden }
.kpi { padding: 11px 16px }
.klabel { font-size: 11px; font-weight: 700; color: #52514E; letter-spacing: .5px; text-transform: uppercase }
.kval { font-size: 29px; font-weight: 700; margin-top: 2px; line-height: 1.15 } .kval.blue { color: #1C5CAB } .kval.red { color: #D03B3B }
.knote { font-size: 12px; color: #52514E; margin-top: 3px; line-height: 1.35 }
.grid { display: grid; gap: 12px; flex: 1; min-height: 0 }
.card h3 { font-size: 13.5px; font-weight: 600; margin-bottom: 6px }
.ctag { font-size: 9.5px; font-weight: 700; letter-spacing: .6px; padding: 1px 5px; border-radius: 3px; margin-left: 6px; vertical-align: 1px }
.ctag.real { color: #0E7A55; border: 1px solid #8FD3B8 } .ctag.sim { color: #1C5CAB; border: 1px solid #86B6EF }
.body { flex: 1; min-height: 0; display: flex; align-items: center; justify-content: center; font-size: 12.8px; line-height: 1.42 }
.body svg { width: 100%; height: 100% } .body img { max-width: 100%; max-height: 100% }
.body.text { display: block; overflow: hidden; color: #2B2A28 }
.body.text p { margin-bottom: 6px } .body.text ul { margin: 0 0 5px 17px } .body.text li { margin-bottom: 3px }
table { border-collapse: collapse; width: 100%; font-size: 11.8px }
th { text-align: left; color: #52514E; font-weight: 600; border-bottom: 1px solid #C9C7BF; padding: 3px 5px }
td { padding: 3px 5px; border-bottom: 1px solid #EEEDE8; vertical-align: top } td.n, th.n { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap }
td.err { color: #B02E2E; font-weight: 600 } td.ok { color: #0E7A55; font-weight: 600 }
footer { font-size: 10.5px; color: #898781; margin-top: 8px }
b.blue { color: #1C5CAB } b.red { color: #B02E2E }
.lab { font-weight: 700; color: #52514E; font-size: 11.5px; letter-spacing: .4px }
.flow { display: flex; gap: 7px; align-items: stretch; width: 100% }
.flow div.s { flex: 1; border: 1px solid #86B6EF; background: #EEF5FD; border-radius: 6px; padding: 7px; font-size: 12px; text-align: center }
.flow div.s b { display: block; color: #1C5CAB; margin-bottom: 3px } .flow div.a { color: #898781; font-size: 18px; align-self: center }
.flow div.s.gate { border-color: #E3A0A0; background: #FBEFEF } .flow div.s.gate b { color: #B02E2E }
.mono { font-family: Consolas, monospace; font-size: 11px; background: #F1F0EB; padding: 1px 4px; border-radius: 3px }
.ai { border-left: 3px solid #2A78D6; padding: 6px 10px; background: #EEF5FD; font-size: 12.5px; margin-top: 4px }
.q { display: grid; grid-template-columns: 22px 1fr; gap: 3px 6px; font-size: 12.8px } .q b { color: #1C5CAB }
"""

PAGE = Template("""
<section class="page">
  <header><div><h1>{{ p.title }}</h1>{% if p.subtitle %}<p class="sub">{{ p.subtitle }}</p>{% endif %}</div>
  {% if p.tag %}<div class="tag {{ p.tag_class }}">{{ p.tag }}</div>{% endif %}</header>
  {% if p.kpis %}<div class="kpis" style="grid-template-columns: repeat({{ p.kpis|length }}, 1fr)">
    {% for k in p.kpis %}<div class="card kpi"><div class="klabel">{{ k[0] }}</div><div class="kval {{ k[3] if k|length > 3 else '' }}">{{ k[1] }}</div><div class="knote">{{ k[2] }}</div></div>{% endfor %}
  </div>{% endif %}
  <div class="grid" style="grid-template-columns: {{ p.cols }}; grid-template-rows: {{ p.rows }}">
    {% for c in p.cards %}<div class="card" style="grid-column: {{ c.col }}; grid-row: {{ c.row }}">
      {% if c.title %}<h3>{{ c.title }}{% if c.tag %}<span class="ctag {{ 'sim' if c.tag == 'SIMULATED' else 'real' }}">{{ c.tag }}</span>{% endif %}</h3>{% endif %}<div class="body {{ 'text' if c.text else '' }}">{{ c.body }}</div></div>{% endfor %}
  </div>
  <footer>{{ p.footer }} · {{ foot }}</footer>
</section>""")


def card(title, body, col="auto", row="auto", text=False, tag=None):
    return dict(title=title, body=body, col=col, row=row, text=text, tag=tag)


def pct(x, d=0):
    return f"{100 * x:.{d}f}%"


def flow(steps, gates=()):
    return '<div class="flow">' + '<div class="a">→</div>'.join(
        f'<div class="s{" gate" if a in gates else ""}"><b>{a}</b>{b}</div>' for a, b in steps) + "</div>"


def build_pages():
    det, rr, rec, h = rd("detection_by_type"), rd("rule_results"), rd("reconciliation_summary"), rd("health")
    rob = json.loads((OUT / "robustness_summary.json").read_text())
    rules = load_rules()
    cfg = load_config()
    sn, sc = rd("scores_nonprofit"), rd("scores_company")
    log = rd("issues_log")
    mc_np = rd("robustness_mc_nonprofit")
    oat_c = rd("robustness_oat_company")
    golden = pd.read_csv(ROOT / "tests" / "golden" / "golden_expected.csv")
    gold_py = rd("scores_nonprofit_nogate").set_index("record_id").loc[golden.record_id].score.values
    ntests = int((OUT / "test_count.txt").read_text()) if (OUT / "test_count.txt").exists() else 0
    R = lambda pair, meas: rec[(rec.source_pair == pair) & (rec.measure == meas)].iloc[0]  # noqa: E731
    soi_rev = R("IRS e-file vs IRS SOI extract", "revenue")
    man = R("Dataset vs original return (manual sample)", "fields matching")
    pp_found = R("IRS e-file vs ProPublica", "fiscal period found")
    pp_rev = R("IRS e-file vs ProPublica", "revenue")
    bmf_new = R("IRS e-file vs IRS BMF", "BMF period is more recent")
    ct25 = R("EPA GHGRP vs Climate TRACE", "emissions within ±25%")
    ct10 = R("EPA GHGRP vs Climate TRACE", "emissions within ±10%")
    ctown = R("EPA GHGRP vs Climate TRACE", "parent vs owner name similarity >= 50")
    ctmatch = R("EPA GHGRP vs Climate TRACE", "EPA plants with a Climate TRACE asset within 2 km")
    sbti = R("SBTi vs EPA-reported emissions", "top-300 emitters found in SBTi")
    sec = R("SEC vs EPA (company identity)", "top-300 emitters matched to an SEC filer")
    recall = det.detected.sum() / det.injected.sum()
    ov_rows = [("IRS e-file vs SOI revenue", soi_rev.agree_rate, int(soi_rev.compared)),
               ("Dataset vs original returns", man.agree_rate, int(man.compared)),
               ("e-file vs ProPublica, same year", pp_rev.agree_rate, int(pp_rev.compared)),
               ("EPA vs Climate TRACE ±25%", ct25.agree_rate, int(ct25.compared)),
               ("EPA parent vs CT owner", ctown.agree_rate, int(ctown.compared))]
    from prepare import load_clean
    us_t = load_clean()["us"]
    ntee_miss = us_t.groupby("size_band").ntee_cd.apply(lambda x: x.isna().mean())
    aud = us_t.groupby("size_band").audited.apply(lambda x: x.astype(float).mean())
    dup_eins = int(us_t.ein.duplicated().groupby(us_t.ein).any().sum())
    lag = [("e-file data used here", us_t.drop_duplicates("ein").period_end.dt.year),
           ("IRS master file", us_t.drop_duplicates("ein").bmf_period_end.dt.year),
           ("ProPublica", pd.read_parquet(ROOT / "data" / "raw" / "propublica_sample.parquet").dropna(subset=["pp_tax_prd"])
            .groupby("ein").pp_tax_prd.max().astype(int).astype(str).str[:4].astype(int))]
    lagd = pd.concat([pd.DataFrame({"source": n, "year": v.dropna().astype(int)}) for n, v in lag])
    lagd = lagd[lagd.year >= 2021].groupby(["source", "year"]).size().rename("n").reset_index()
    lagd["share"] = lagd.n / lagd.groupby("source").n.transform("sum")
    lagd["source"] = pd.Categorical(lagd.source, [n for n, _ in lag])
    lagd = lagd.sort_values(["source", "year"])
    lagd["source"] = lagd.source.astype(str)
    real = rr.set_index("id").flagged_real
    co = pd.read_parquet(PROCESSED / "companies.parquet")
    rejected = int((co.sec_match_status == "rejected after review").sum() + (co.sbti_match_status == "rejected after review").sum())
    reviewed = rejected + int((co.sec_match_status == "accepted after review").sum() + (co.sbti_match_status == "accepted after review").sum())
    np_rob, co_rob = rob["nonprofit"], rob["company"]
    lost = oat_c[(oat_c.pillar == "carbon_intensity") & (oat_c.factor == 1.5)].scores_lost.iloc[0]
    pages = []

    # 0 Overview ----------------------------------------------------------------------
    qs = ("<div class='q'>" + "".join(f"<b>{i}.</b><span>{q}</span>" for i, q in enumerate([
        "What does public nonprofit, ESG and impact data really look like: complete, consistent, fresh? (p.2)",
        "When two public sources describe the same thing, do they agree, and why not? (p.3)",
        "Can a transparent score with adjustable weights be built on top, without hiding missing data? (p.4)",
        "How do you test such a score: reference cases, edge cases, regression, weight sensitivity? (p.5)",
        "Do the controls actually catch errors? Measured with 300 known, injected errors. (p.6)"], 1)) + "</div>")
    recs = ("<ul><li><b>Gate every score on data quality</b>: error-level rules withhold the score; the audit showed two warning rules "
            "must also hold it (p.6).</li><li><b>Reconcile before scoring</b>: join on EIN <i>and</i> fiscal period; sources number years differently (p.3).</li>"
            "<li><b>Never turn missing data into zero</b>: re-weight, show coverage, withhold below 60% (p.4).</li>"
            "<li><b>Test a new weighting before release</b>: rank stability and coverage side effects, on a golden set and a frozen sample (p.5).</li>"
            "<li><b>Route judgement calls to people</b>: fuzzy name matches, parent companies, model-vs-report gaps go to a research queue (p.2-3).</li></ul>")
    data = (f"<p><span class='lab'>PUBLIC DATA</span> &nbsp;2,000 US public charities (IRS Form 990 e-file data, tax year 2023, via NCCS), "
            f"IRS SOI extract and master file, ProPublica API (160), 30 original returns; 500 UK charities (Charity Commission); "
            f"{ctmatch.compared:,} US power plants (EPA GHGRP vs Climate TRACE); 300 largest GHGRP parent companies with SEC revenue and SBTi status.</p>"
            "<p><span class='lab'>SIMULATED</span> &nbsp;300 known errors injected on a copy (10 types x 30), answer key opened only at the end. "
            "The demo score is <b>illustrative, not Carnelian's methodology</b>, which is not public.</p>"
            f"<p><span class='lab'>TOOLS</span> &nbsp;Python (pandas, DuckDB SQL), pytest ({ntests} tests), Excel workbook with formulas, Plotly dashboard.</p>")
    pages.append(dict(
        title="Carnelian Compass: how to trust an impact score",
        subtitle="A data-quality and validation framework for nonprofit and ESG scoring, built on public IRS, Charity Commission, EPA, "
                 "Climate TRACE and SBTi data, with test cases, benchmark examples and an error-injection audit.",
        tag="OVERVIEW", tag_class="",
        kpis=[("Injected errors caught · p.6", pct(recall, 1), f"{det.detected.sum()} of {det.injected.sum()} SIMULATED errors, 40 rules, Python and SQL agree", "blue"),
              ("Source agreement · p.3", pct(soi_rev.agree_rate, 1), f"IRS e-file vs IRS SOI revenue ({soi_rev.compared:,} orgs); {int(man.agree)}/{int(man.compared)} fields match the original returns", "blue"),
              ("Golden set · p.5", f"{len(golden)}/{len(golden)}", "organisations scored by hand in Excel and reproduced exactly by the code (every intermediate value)", "blue"),
              ("Rank stability · p.5", f"τ = {np_rob['tau_median']:.2f}", f"median Kendall tau over 1,000 random weightings; top decile keeps {pct(np_rob['top_decile_overlap'])} of its members", "blue")],
        cols="1.05fr 1fr 1fr", rows="auto 1fr",
        cards=[card("Five questions", qs, text=True), card("Recommendations for Compass", recs, text=True),
               card("Data & methods", data, text=True),
               card("Data health of the real sources (pass rate) · p.2", C.health_heatmap(h[h.dataset.str.startswith("real")], w=560, h_px=230), tag="PUBLIC DATA"),
               card("Agreement between sources · p.3", C.agreement_bars(ov_rows, w=520, h=250), tag="PUBLIC DATA"),
               card("Injected errors caught, by type · p.6", C.detection_bars(det, w=560, h=300, legend=False), tag="SIMULATED")],
        footer="Sources and licences: p.7 and data/SOURCES.md · code: src/ · tests: tests/ · workbook: qa/QA_workbook.xlsx"))

    # 1 Carnelian & the problem --------------------------------------------------------
    facts = ("<ul><li><b>Founded in 2025</b>, three activities: <b>Studio</b> (venture building and capital), <b>Advisory</b> (operational support) "
             "and <b>Technology</b> (custom software and Compass).</li>"
             "<li><b>Compass</b>: an impact intelligence platform for investors, philanthropists and institutions to measure, manage and optimise "
             "social and environmental outcomes.</li>"
             "<li>How it works: <b>connect</b> investment and giving portfolios; <b>normalise and score</b> (comparable ESG and impact scores); "
             "<b>visualise</b>; <b>get insights</b> (recommendations, alerts).</li>"
             "<li>Features listed: <b>adjustable metrics and weights</b>, <b>nonprofit scoring</b>, impact measurement, thematic giving portfolios, "
             "ESG scoring and benchmarking, scenario analysis, white-label platform and API access.</li>"
             "<li>Its blog frames data as a life cycle: choose indicators for a concept that cannot be measured directly, then ask who touched each "
             "number between reality and the dataset.</li></ul>"
             f"<p style='font-size:11.5px;color:#52514E'>As stated by Carnelian on its website, seen on {SEEN_ON}. No internal information is used.</p>")
    hard = ("<p>A comparable score mixes sources that were never designed to be compared:</p><ul>"
            "<li><b>Different years</b>: a fiscal year ending June 2024 is \"tax year 2023\" for the IRS and \"2024\" in other databases.</li>"
            "<li><b>Different units and currencies</b>: dollars, pounds, tonnes, thousands.</li>"
            "<li><b>Different entities</b>: a power plant belongs to an operator, a holding and a listed group; each source picks one.</li>"
            "<li><b>Reported vs modelled</b>: EPA figures are reported by facilities; Climate TRACE estimates them from satellites and models.</li>"
            "<li><b>Lags</b>: bulk data trails the latest filings by one to two years.</li>"
            "<li><b>Gaps</b>: small organisations file shorter forms; private companies publish no revenue.</li></ul>"
            "<p>Each gap can move a score more than the real-world difference it is meant to measure. That is the QA analyst's job.</p>")
    src = [("IRS Form 990 e-file (NCCS)", "US nonprofit financials, functional expenses", "PUBLIC"),
           ("IRS SOI extract + master file", "Second copy of totals; activity code; latest period", "PUBLIC"),
           ("ProPublica Nonprofit Explorer", "Third copy, links to filings", "PUBLIC"),
           ("Charity Commission register", "UK income, spending, filing status (GBP)", "PUBLIC"),
           ("EPA GHGRP", "Reported facility emissions, parent companies", "PUBLIC"),
           ("Climate TRACE", "Modelled asset emissions, owners", "PUBLIC"),
           ("SBTi Target Dashboard", "Validated climate targets", "PUBLIC"),
           ("SEC EDGAR XBRL", "Company revenue (for carbon intensity)", "PUBLIC")]
    srct = "<table><tr><th>Source</th><th>What it brings to a score</th></tr>" + "".join(
        f"<tr><td>{a}</td><td>{b}</td></tr>" for a, b, _ in src) + "</table>"
    pipe = flow([("Connect", "8 public sources<br>4 tables"), ("Validate", "40 rules, 6 dimensions<br>Python + SQL"),
                 ("Reconcile", "source vs source<br>+ 30 original returns"), ("Gate", "errors withhold<br>the score"),
                 ("Score", "peer percentiles<br>adjustable weights"), ("Test", "golden set, edge cases<br>regression, robustness"),
                 ("Audit", "300 injected errors<br>recall and precision")], gates=("Gate",))
    pages.append(dict(
        title="Compass promises comparable scores from heterogeneous data; the score is only as good as the data and the checks behind it",
        subtitle="What Carnelian publishes about itself and Compass, and why comparable impact scores are hard: this study rebuilds the problem on public data.",
        tag="PUBLIC DATA", tag_class="real", kpis=None, cols="1.05fr 1fr 1fr", rows="auto 1fr 1fr",
        cards=[card("The control chain built in this study (the Data & QA Analyst scope)", pipe, col="1 / 4"),
               card("Carnelian and Compass, as stated by Carnelian", facts, text=True, row="2 / 4"),
               card("Why comparable scores are hard", hard, text=True, row="2 / 4"),
               card("Public sources used here", srct, text=True, col="3", row="2"),
               card("Same organisations, three sources, three different 'latest' years", C.lag_bars(lagd, w=470, h=220), col="3", row="3", tag="PUBLIC DATA")],
        footer=f"Source: carnelianventures.com (home, Compass, Technology, About, blog), seen on {SEEN_ON}"))

    # 2 Public data profile ------------------------------------------------------------
    hr = h[h.dataset.str.startswith("real")]
    anom = [("Same EIN filed twice for 2023 (original + amended)", dup_eins, f"orgs ({int(real['UNIQ-01'])} rows)", "keep the latest"),
            ("Activity code (NTEE) missing in the master file", int(real["COMP-03"]), "of 2,032 returns", "size-band peers"),
            ("Program + management + fundraising ≠ total", int(real["CONS-01"]), "returns", "research"),
            ("Negative assets or liabilities", int(real["VAL-02"]), "returns", "research"),
            ("Revenue more than 5x or under 0.2x prior year", int(real["CONS-04"]), "returns", "research"),
            ("A newer return already exists (master file)", int(real["FRESH-02"]), "orgs", "refresh"),
            ("UK accounts older than 3 years", int(real["FRESH-03"]), "of 500 charities", "do not use"),
            ("UK charity overdue or in double default", int(real["FRESH-04"]), "charities", "lower transparency")]
    at = "<table><tr><th>Real anomaly (not injected)</th><th class='n'>Count</th><th></th><th>Action</th></tr>" + "".join(
        f"<tr><td>{a}</td><td class='n'>{b:,}</td><td>{c}</td><td>{d}</td></tr>" for a, b, c, d in anom) + "</table>"
    open_r = (log.status == "Open - research")
    q = log[open_r].groupby("table").size().reindex(["us", "uk", "companies", "power"]).fillna(0).astype(int)
    qlabels = ["US nonprofits", "UK charities", "Companies", "Power plants"]
    pages.append(dict(
        title=f"The real data is mostly clean but never clean enough: {dup_eins} organisations filed twice, "
              f"{pct(real['COMP-03'] / 2032)} lack an activity code, and {pct(bmf_new.agree_rate)} already have a newer return",
        subtitle=f"40 rules over six dimensions, run on the untouched public data. Pass rate = share of records passing every error/warning rule of a dimension. "
                 f"{len(log):,} issues logged; {int(open_r.sum()):,} need a person to look at the source (research queue).",
        tag="PUBLIC DATA", tag_class="real", kpis=None, cols="1.15fr 1fr", rows="1fr 1fr",
        cards=[card("Data health by source and dimension (pass rate)", C.health_heatmap(hr), tag="PUBLIC DATA"),
               card("Real anomalies found by the rules", at, text=True, tag="PUBLIC DATA"),
               card("Research queue: open issues by source", C.hbar(qlabels, q.tolist(), w=760, h=250), tag="PUBLIC DATA"),
               card("Reading the profile", "<ul>"
                    f"<li><b>The pass rates hide the biggest gap, freshness</b>: the newest bulk e-file data is tax year 2023, while the IRS master file "
                    f"already lists a later return for {pct(bmf_new.agree_rate)} of organisations (an info rule, so it does not lower the rate). "
                    "A score must show the period it is based on.</li>"
                    f"<li><b>Missing activity codes are not a small-organisation problem</b>: {pct(ntee_miss.min())} to {pct(ntee_miss.max())} by size band. "
                    "Peer groups fall back to size only.</li>"
                    f"<li><b>A field can mislead</b>: only {pct(aud['XL >$50m'])} of the largest organisations tick \"separate audited statements\" "
                    f"(vs {pct(aud['L $5-50m'])} of $5-50m ones): many are audited inside consolidated statements, a second box. The transparency metric "
                    "should read both: logged as a method fix.</li>"
                    f"<li><b>Power plants have the lowest accuracy</b>: model and report differ by more than 50% for {int(real['ACC-06'])} plants (p.3).</li></ul>",
                    text=True)],
        footer="Rules: src/dq/rules.yaml (run in pandas and DuckDB SQL) · results: data/outputs/rule_results.csv, issues_log.csv"))

    # 3 Sources disagree ----------------------------------------------------------------
    rows = [("IRS e-file vs SOI: revenue", soi_rev.agree_rate, int(soi_rev.compared)),
            ("IRS e-file vs SOI: assets", R("IRS e-file vs IRS SOI extract", "assets").agree_rate, int(R("IRS e-file vs IRS SOI extract", "assets").compared)),
            ("Dataset vs original returns: fields", man.agree_rate, int(man.compared)),
            ("e-file vs ProPublica: revenue, same year", pp_rev.agree_rate, int(pp_rev.compared)),
            ("ProPublica has the same fiscal year", pp_found.agree_rate, int(pp_found.compared)),
            ("UK register vs annual return: income", R("UK register vs annual return", "latest income").agree_rate, int(R("UK register vs annual return", "latest income").compared)),
            ("EPA vs Climate TRACE: within ±25%", ct25.agree_rate, int(ct25.compared)),
            ("EPA parent vs Climate TRACE owner", ctown.agree_rate, int(ctown.compared)),
            ("Top-300 emitters with an SEC filer", sec.agree_rate, int(sec.compared)),
            ("Top-300 emitters in SBTi", sbti.agree_rate, int(sbti.compared))]
    soi = rd("recon_irs_soi")
    worst = soi.sort_values("rev_gap", ascending=False).head(3)
    ep = rd("recon_epa_ct")
    ep = ep[ep.epa_co2e > 0]
    cases = ("<table><tr><th>Anonymised case</th><th>What contradicts</th><th>Explanation / next step</th></tr>"
             f"<tr><td>Nonprofit #1</td><td>e-file revenue = {worst.iloc[0].revenue / worst.iloc[0].soi_revenue:.2f}x the SOI revenue</td><td>amended return filed later; keep the latest, log both</td></tr>"
             f"<tr><td>Nonprofit #2</td><td>ProPublica has no FY ending 2024</td><td>its year label = year the period ends; IRS tax year = year it begins</td></tr>"
             f"<tr><td>Plant #3</td><td>Climate TRACE = {ep.ct_to_epa_ratio.max():.0f}x EPA</td><td>idle unit or a different boundary: research</td></tr>"
             "<tr><td>Company #4</td><td>US steelmaker matched to a Polish firm whose name is one letter shorter</td><td>fuzzy match rejected by hand</td></tr></table>")
    pages.append(dict(
        title=f"When sources disagree: IRS copies agree {pct(soi_rev.agree_rate, 1)} of the time, but modelled and reported emissions agree within 25% "
              f"for only {pct(ct25.agree_rate)} of power plants",
        subtitle=f"Reconciliation joins on identifier and fiscal period. Every disagreement on the IRS side traced back to amended returns; on the "
                 f"emissions side to model vs report, plant boundaries and ownership levels. {reviewed} fuzzy name matches were reviewed by hand and "
                 f"{rejected} rejected (e.g. a steelmaker matched to an unrelated firm).",
        tag="PUBLIC DATA", tag_class="real", kpis=None, cols="1fr 1fr", rows="1.25fr 1fr",
        cards=[card("Agreement rate by source pair (dashed line: 95%)", C.agreement_bars(rows, w=640, h=330), tag="PUBLIC DATA"),
               card(f"EPA reported vs Climate TRACE modelled emissions, {len(ep):,} power plants, 2023", C.scatter_epa_ct(ep, w=640, h=330), tag="PUBLIC DATA"),
               card("Cases where the data contradicts itself (anonymised)", cases, text=True),
               card("What a reconciliation must record", "<ul>"
                    "<li><b>Join key</b>: identifier + fiscal period, never identifier alone (an amended return or a later year slips in).</li>"
                    f"<li><b>Tolerance</b>: 1% for copies of the same filing; ±25% is a reasonable bar between a model and a report "
                    f"(only {pct(ct10.agree_rate)} agree within 10%).</li>"
                    "<li><b>Direction of trust</b>: reported figures first, models as a check; the gap is logged, not averaged.</li>"
                    "<li><b>Entity level</b>: EPA names the ultimate parent, Climate TRACE often the operator: compare at the same level before attributing emissions.</li>"
                    "<li><b>Coverage</b>: only " + pct(sec.agree_rate) + " of the largest emitters have SEC revenue, so carbon intensity is missing for most.</li></ul>",
                    text=True)],
        footer="Code: src/reconcile.py · ProPublica Nonprofit Explorer API · NCCS e-file · IRS SOI/BMF · EPA Envirofacts · Climate TRACE API (CC BY 4.0) · SBTi · SEC XBRL frames"))

    # 4 Demo score -----------------------------------------------------------------------
    pc = cfg["nonprofit"]["pillars"]
    wt = "<table><tr><th>Pillar</th><th class='n'>Weight</th><th>Metrics (direction)</th></tr>" + "".join(
        f"<tr><td>{k.replace('_', ' ')}</td><td class='n'>{v['weight']:.0%}</td><td>{', '.join(f'{m.replace(chr(95), chr(32))} ({d})' for m, d in v['metrics'].items())}</td></tr>"
        for k, v in pc.items()) + "</table><p style='margin-top:6px;font-size:11.5px'>Companies: carbon intensity 35%, emissions trend 25%, SBTi target 20%, disclosure 20%. Weights live in <span class='mono'>src/scoring/config.yaml</span>.</p>"
    steps = flow([("1. Metrics", "ratios from the return;<br>18-month years annualised"), ("2. Caps", "extremes capped<br>(e.g. reserves ≤ 60 months)"),
                  ("3. Peers", "percentile within NTEE x size<br>(fallback: size, n < 30)"), ("4. Pillars", "mean of available<br>metrics"),
                  ("5. Weights", "re-weighted when a<br>pillar is missing"), ("6. Coverage", "no score below 60%<br>of the weight"),
                  ("7. DQ gate", "error flags withhold<br>the score")], gates=("7. DQ gate",))
    st = sn.status.value_counts()
    covd = sn.coverage.round(2).value_counts().sort_index(ascending=False)
    wt += ("<p style='margin-top:8px'><b>Missing data, made visible</b> (share of pillar weight with data):</p><table><tr><th>Coverage</th><th class='n'>Organisations</th><th>Result</th></tr>"
           + "".join(f"<tr><td>{c:.0%}</td><td class='n'>{n:,}</td><td>{'scored' if c >= 0.6 else 'no score (insufficient data)'}</td></tr>" for c, n in covd.items())
           + "</table>")
    lim = ("<ul><li><b>A financial ratio is not an impact measure.</b> It says whether an organisation is solvent, stable and transparent, "
           "not whether lives changed. Outcome data (IRIS+ metrics, the five dimensions of impact: what, who, how much, contribution, risk) "
           "would sit on top.</li><li><b>A low overhead share is not always good</b>: under-investing in staff, systems and evaluation weakens programs; "
           "the program-share metric is capped at 100% and ranked within peers so that it cannot dominate.</li>"
           "<li><b>Emissions do not tell the whole story</b> of a company's impact: direct US emissions only, no products, supply chain or social side.</li>"
           "<li>Percentiles make scores relative: a top score means better than peers in this sample, not good in absolute terms.</li></ul>")
    pages.append(dict(
        title=f"A transparent demo score: {st.get('scored', 0):,} organisations scored, {st.get('blocked by data quality', 0)} withheld by the "
              f"data-quality gate and {st.get('insufficient data', 0)} for missing data, never scored as zero",
        subtitle="Illustrative, not Carnelian's methodology (which is not public): built to show how a Compass-style score with adjustable metrics "
                 "and weights can be documented, normalised by peer group and made safe against missing or bad data.",
        tag="PUBLIC DATA · DEMO SCORE", tag_class="real", kpis=None, cols="1fr 1fr 1fr", rows="auto 1fr",
        cards=[card("How a score is built (docs/METHODOLOGY.md)", steps, col="1 / 4"),
               card("Pillars, weights and metrics", wt, text=True),
               card("Score distribution by size band (published scores only)", C.box_by_group(sn[sn.status == "scored"], "size_band_calc", "score",
                    cfg["nonprofit"]["size_labels"], w=470, h=300, ylabel="Demo score (0-100)"), tag="PUBLIC DATA"),
               card("Limits, said plainly", lim, text=True)],
        footer="Code: src/scoring/engine.py · config: src/scoring/config.yaml · ratios: program-expense share, fundraising cost per $ raised, months of reserves, debt ratio"))

    # 5 Testing the score ---------------------------------------------------------------
    edge = ("<table><tr><th>Edge case (tests/test_edge_cases.py)</th><th>Expected behaviour</th></tr>"
            "<tr><td>No revenue</td><td>stability = -100%, size band S, scored</td></tr>"
            "<tr><td>Brand-new organisation (no prior year)</td><td>stability missing, re-weighted, coverage 80%</td></tr>"
            "<tr><td>Zero expenses</td><td>reserves and program share missing, not zero</td></tr>"
            "<tr><td>Only one pillar available</td><td>no score: \"insufficient data\"</td></tr>"
            "<tr><td>Extreme reserves and debt</td><td>capped at 60 months and 1.5</td></tr>"
            "<tr><td>Amounts in GBP</td><td>ratios unchanged, size band converted at 1.28</td></tr>"
            "<tr><td>18-month fiscal year</td><td>flows annualised before ratios</td></tr>"
            "<tr><td>Negative revenue</td><td>no stability metric</td></tr>"
            "<tr><td>Original + amended return</td><td>scored once, latest return</td></tr></table>")
    tests = (f"<ul><li><b>{ntests} pytest tests</b>, all passing: one per rule and engine (80), scoring units, edge cases, data contracts.</li>"
             f"<li><b>Golden set</b>: {len(golden)} real organisations scored by hand in Excel (formulas, LibreOffice-recalculated); the code matches "
             f"all {len(golden) * 26} intermediate values (metrics, percentiles, points, pillars, coverage, score).</li>"
             "<li><b>Non-regression</b>: 150 frozen scores (100 organisations, 50 companies); any unexplained change fails the build.</li>"
             f"<li><b>Testing a new weighting</b>: raising the carbon-intensity weight by 50% looks harmless on ranks (τ = "
             f"{oat_c[(oat_c.pillar == 'carbon_intensity') & (oat_c.factor == 1.5)].tau.iloc[0]:.2f}) but <b class='red'>drops {lost} companies below the "
             "coverage threshold</b>: their score disappears. Exactly what to catch before production.</li></ul>")
    pages.append(dict(
        title=f"Testing the score: the code reproduces {len(golden)} hand-calculated cases exactly, and rankings stay stable under random weights "
              f"(median τ = {np_rob['tau_median']:.2f})",
        subtitle=f"1,000 random weightings around the base weights (Dirichlet): median Kendall tau {np_rob['tau_median']:.2f} for nonprofits "
                 f"({co_rob['tau_median']:.2f} for companies); an organisation moves by {np_rob['mean_abs_rank_change_pts']:.0f} percentile points on average. "
                 "Weights matter, which is why Compass makes them adjustable and why each change needs a test.",
        tag="PUBLIC DATA · TESTS", tag_class="real", kpis=None, cols="1fr 1fr 1fr", rows="1fr 1fr",
        cards=[card("What is tested, and the finding a test caught", tests, text=True, col="1", row="1"),
               card("Rank stability: Kendall tau over 1,000 random weightings (nonprofits)", C.hist(mc_np.tau, w=470, h=250, bins=30,
                    xlabel="Kendall tau vs base ranking (1 = identical)"), tag="PUBLIC DATA", col="2", row="1"),
               card("Edge cases the score must survive", edge, text=True, col="3", row="1 / 3"),
               card(f"Golden set: Excel by hand vs code, {len(golden)} organisations (exact match)", C.golden_scatter(
                    pd.to_numeric(golden.score), gold_py), tag="PUBLIC DATA", col="1", row="2"),
               card("One weight at a time, x0.5 and x1.5 (companies)", C.oat_bars(oat_c), tag="PUBLIC DATA", col="2", row="2")],
        footer="Tests: tests/ (pytest) · golden set: qa/QA_workbook.xlsx (Golden_set) and tests/golden/ · robustness: src/robustness.py"))

    # 6 Did we catch the errors -------------------------------------------------------
    ei = rd("error_impact_nonprofit")
    worst_types = det.sort_values("recall").head(5)
    dd = rd("detection_detail")
    pm_miss = set(dd[(~dd.detected) & (dd.error_type == "parent_mismatch")].record_id)
    fc = pd.read_csv(OUT / "flags_clean.csv", dtype=str)
    pm_hidden = len(pm_miss & set(fc[fc.rule_id == "ACC-07"].record_id))
    pm_det = int(det.set_index("error_type").detected["parent_mismatch"])
    blind = ("<ul>" + "".join(f"<li><b>{r.label}: {r.detected}/{r.injected}</b>. " + {
        "parent_mismatch": f"{pm_hidden} of the {30 - pm_det} misses sit on plants already flagged in the real data (EPA parent and Climate TRACE "
                           "owner names already differ), so the error hides behind an existing alert; the others produced similar names. "
                           "Fix: compare ownership IDs, not names, and re-review open alerts when a value changes.",
        "currency": "A charity with no income has nothing to convert, so a wrong currency is invisible. Fix: check the currency field itself.",
        "signs": "A sign flipped on a zero value changes nothing.", "missing_small": "A blank split when total expenses are zero is legitimate.",
        "stale": "A record with no period date cannot be aged. Fix: make the date mandatory."}.get(r.error_type, "") + "</li>"
        for r in worst_types.itertuples()) + "</ul>")
    acts = ("<ul><li><b>Gate v1</b> withheld scores on error-level flags only. The audit showed that "
            f"<b class='red'>{co_rob['gate_v1_moved_over_10pts_not_blocked']} of 20 company errors</b> (units, x10) were flagged by warning rules "
            "and still moved a published rank by more than 10 points.</li>"
            f"<li><b>Gate v2</b> holds the score on those two rules (emissions jump, emissions per facility below the reporting threshold): "
            f"{co_rob['injected_moved_over_10pts_not_blocked']} injected errors now reach a published score; {co_rob['blocked_real']} real companies wait for research.</li>"
            f"<li>Nonprofits: {np_rob['injected_blocked_by_gate']} of {np_rob['injected_records_scored']} scored records with an injected error are withheld; "
            f"without the gate, {np_rob['injected_moved_over_10pts']} would have moved by more than 10 points.</li>"
            f"<li>Precision: {pct(det.precision.mean())} of the new alerts point at an injected error; the real cost is the baseline workload "
            f"(e.g. {int(det.set_index('error_type').baseline_alerts_real_data['parent_mismatch'])} owner-name alerts on the real data).</li></ul>")
    pages.append(dict(
        title=f"The checks caught {det.detected.sum()} of 300 injected errors ({pct(recall, 1)}); the misses show where rules need IDs, not names",
        subtitle="SIMULATED: 10 error types x 30 injected on a copy of the real data (seed 42): units, signs, sums, duplicates, shifted fiscal years, "
                 "missing values in small organisations, x10 outliers, wrong parent company, GBP read as USD, stale filings. The answer key was opened only after the checks ran.",
        tag="SIMULATED ERRORS · REAL RECORDS", tag_class="sim", kpis=None, cols="1.1fr 1fr", rows="1fr 1fr",
        cards=[card("Injected vs detected, by error type (hidden answer key)", C.detection_bars(det, w=680, h=330, legend=False), tag="SIMULATED"),
               card("Blind spots (lowest recall)", blind, text=True),
               card("Rank change of nonprofits carrying an injected error, if scored without the gate", C.impact_strip(ei, w=680, h=250), tag="SIMULATED"),
               card("Actions taken after the audit", acts, text=True)],
        footer="Injection: src/inject_errors.py · evaluation: src/evaluate_detection.py · answer key: data/_hidden_truth.csv · detail: qa/QA_workbook.xlsx (Detection)"))

    # 7 Standards, process, methods ----------------------------------------------------
    std = ("<table><tr><th>Dimension</th><th>Standard proposed for Compass inputs</th></tr>"
           "<tr><td>Completeness</td><td>core totals present; split present when total > 0; coverage shown with every score</td></tr>"
           "<tr><td>Validity</td><td>no negative expenses or assets; period 360-371 days or annualised; currency declared</td></tr>"
           "<tr><td>Consistency</td><td>parts add up (±0.5%); balance sheet balances (±1%); year-on-year within 0.2-5x</td></tr>"
           "<tr><td>Uniqueness</td><td>one record per entity and period; fuzzy matches below 100 reviewed by a person</td></tr>"
           "<tr><td>Freshness</td><td>period end < 3 years; newer filing triggers a refresh</td></tr>"
           "<tr><td>Accuracy</td><td>copies of a filing agree within 1%; model vs report within ±25% or logged</td></tr></table>")
    proc = flow([("Ingest", "neutral client<br>no personal fields"), ("Validate", "40 rules"), ("Reconcile", "ID + period"),
                 ("Gate", "errors & holds"), ("Review", "research queue<br>issues log"), ("Release", "tests green<br>regression frozen")], gates=("Gate",))
    lic = ("<ul style='font-size:11.5px'><li>IRS SOI extract and master file; IRS e-file data via NCCS (Urban Institute) and the GivingTuesday data lake: US public data.</li>"
           "<li>ProPublica Nonprofit Explorer API (CC BY-NC-ND 3.0 US): used to compare, values not republished.</li><li>Charity Commission register: Open Government Licence v3.0.</li>"
           "<li>EPA GHGRP (Envirofacts): public domain. Climate TRACE: CC BY 4.0 (attributed; values aggregated and matched by us). SEC EDGAR XBRL frames: public, fair-access policy.</li>"
           "<li>SBTi Target Dashboard: public download; raw file not redistributed, only the status of matched companies.</li>"
           "<li>Frameworks cited, not copied: GIIN IRIS+, Impact Management Project five dimensions.</li></ul>")
    lim = ("<ul style='font-size:11.5px'><li>Errors are SIMULATED: detection rates measure the rules on known errors, not the quality of any source.</li>"
           "<li>The demo score is illustrative and relative to this sample; it is not a ranking to use for giving or investing, and no organisation is named.</li>"
           "<li>Sample: 2,000 US charities (equal size bands), 500 UK charities, 300 companies, US direct emissions only.</li>"
           "<li>The 30-return check reads the original XML by script, value by value; links are in the workbook for a human spot-check.</li></ul>")
    pages.append(dict(
        title="Standards and a repeatable control procedure: every score traceable to its inputs, every exception to a decision",
        subtitle="What this study proposes to make Compass scores defensible: written standards per dimension, rules as configuration, a gate before "
                 "publication, a research queue for judgement calls, and tests that run on every change.",
        tag="STANDARDS · METHODS · AI NOTE", tag_class="", kpis=None, cols="1.1fr 1fr 1fr", rows="auto 1fr 0.8fr",
        cards=[card("Control procedure (docs/DATA_STANDARDS.md)", proc, col="1 / 4"),
               card("Data standards by dimension", std, text=True, col="1", row="2"),
               card("Sources and licences", lic, text=True, col="2", row="2"),
               card("Limits & AI note", lim + f"<div class='ai'>{'AI-assisted workflow: ' + ai_note()}</div>", text=True, col="3", row="2 / 4"),
               card("Rule catalogue: 40 rules by dimension and severity", C.stacked_rules(rules, w=520, h=200), col="1", row="3"),
               card("Next steps on a real Compass dataset", "<ul>"
                    "<li>Run the 40 rules on Compass inputs and agree severities and tolerances with the methodology owner.</li>"
                    "<li>Replace name matching with identifiers (EIN, LEI, CIK, EPA facility ID) wherever they exist.</li>"
                    "<li>Fix the transparency metric (read the consolidated-audit box) and re-freeze the regression sample.</li>"
                    "<li>Add the golden set and the injection audit to every release of a new weighting.</li></ul>", text=True, col="2", row="3")],
        footer="Rerun: python src/run_all.py · data/SOURCES.md · docs/METHODOLOGY.md · docs/DATA_STANDARDS.md"))
    return pages


def edge() -> str:
    for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        if Path(p).exists():
            return p
    return shutil.which("msedge") or "msedge"


def wait_file(path: Path, timeout=120):
    last, t0 = -1, time.time()
    while time.time() - t0 < timeout:
        if path.exists() and path.stat().st_size > 0 and path.stat().st_size == last:
            return
        last = path.stat().st_size if path.exists() else -1
        time.sleep(1.5)
    raise TimeoutError(f"{path} not produced")


def clean_pdf(path: Path):
    """Metadata reduced to the title: no author, tool or path."""
    from pypdf import PdfReader, PdfWriter
    r, w = PdfReader(str(path)), PdfWriter()
    for pg in r.pages:
        w.add_page(pg)
    w.add_metadata({"/Title": "Carnelian Compass: how to trust an impact score"})
    for k in ("/Producer", "/Creator", "/Author"):
        w._info.get_object().pop(k, None)
    tmp = path.with_suffix(".tmp.pdf")
    with open(tmp, "wb") as fh:
        w.write(fh)
    tmp.replace(path)


def main():
    TMP.mkdir(exist_ok=True)
    (DOCS / "img").mkdir(parents=True, exist_ok=True)
    prof = TMP / "edge-profile"
    pages = build_pages()
    head = f"<!doctype html><html><head><meta charset='utf-8'><title>Carnelian Compass QA</title><style>{CSS}</style></head><body>"
    sections = [PAGE.render(p=p, foot=FOOTER) for p in pages]
    src = TMP / "report.html"
    src.write_text(head + "".join(sections) + "</body></html>", encoding="utf-8")
    PDF.unlink(missing_ok=True)
    subprocess.run([edge(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--print-to-pdf-no-header",
                    f"--user-data-dir={prof}", f"--print-to-pdf={PDF}", src.as_uri()], check=True, capture_output=True, timeout=180)
    wait_file(PDF)
    clean_pdf(PDF)
    names = ["00_overview", "01_carnelian_compass", "02_public_data", "03_sources_disagree", "04_demo_score", "05_testing", "06_error_audit", "07_standards_methods"]
    for name, sec in zip(names, sections):
        one = TMP / f"{name}.html"
        one.write_text(head.replace("page-break-after: always", "") + sec + "</body></html>", encoding="utf-8")
        out = DOCS / "img" / f"{name}.png"
        out.unlink(missing_ok=True)
        subprocess.run([edge(), "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={prof}",
                        "--window-size=1536,864", f"--screenshot={out}", one.as_uri()], check=True, capture_output=True, timeout=120)
        wait_file(out)
    from pypdf import PdfReader
    print("PDF:", PDF.relative_to(ROOT), f"({PDF.stat().st_size // 1024} KB, {len(PdfReader(str(PDF)).pages)} pages)")


if __name__ == "__main__":
    main()
