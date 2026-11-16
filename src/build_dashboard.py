"""Stand-alone HTML 'Data quality cockpit' (dashboard/data_quality_cockpit.html): four tabs, Plotly embedded (works
offline), aggregates and public identifiers only. Usage: python src/build_dashboard.py  (open ...html#1 to #4)
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DASH, FOOTER, OUT  # noqa: E402
from prepare import load_clean  # noqa: E402

BLUE, BLUE_L, GRAY, RED, INK2 = "#2A78D6", "#86B6EF", "#C9C7BF", "#D03B3B", "#52514E"
SEV = {"error": RED, "warning": BLUE_L, "info": GRAY}
LAYOUT = dict(font=dict(family="Segoe UI, sans-serif", size=12, color=INK2), paper_bgcolor="#FCFCFB",
              plot_bgcolor="#FCFCFB", margin=dict(l=10, r=10, t=44, b=10), hoverlabel=dict(font_size=12))
DIMS = ["completeness", "validity", "consistency", "uniqueness", "freshness", "accuracy"]
TNAME = {"us": "US nonprofits", "uk": "UK charities", "companies": "Companies", "power": "Power plants"}
_first = [True]


def div(fig):
    fig.update_layout(**LAYOUT)
    inc = "inline" if _first[0] else False
    _first[0] = False
    return pio.to_html(fig, full_html=False, include_plotlyjs=True if inc else False, config={"displayModeBar": False, "responsive": True})


def table(df, cols):
    head = "".join(f"<th>{html.escape(c)}</th>" for c in cols.values())
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(r[k]))}</td>" for k in cols) + "</tr>" for _, r in df.iterrows())
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def heat(h, title):
    p = h.pivot_table(index="table", columns="dimension", values="score").reindex(columns=DIMS).reindex(list(TNAME))
    f = go.Figure(go.Heatmap(z=p.values, x=[d.capitalize() for d in DIMS], y=[TNAME[t] for t in p.index], zmin=0.45, zmax=1,
                             colorscale=[[0, RED], [0.75, BLUE_L], [1, "#1C5CAB"]], text=p.map(lambda v: "" if pd.isna(v) else f"{v:.1%}").values,
                             texttemplate="%{text}", hovertemplate="%{y} · %{x}: %{z:.1%}<extra></extra>", showscale=False))
    f.update_layout(height=320, title=title, yaxis_autorange="reversed")
    return f


def main():
    h, rr, log = pd.read_csv(OUT / "health.csv"), pd.read_csv(OUT / "rule_results.csv"), pd.read_csv(OUT / "issues_log.csv")
    rec, det = pd.read_csv(OUT / "reconciliation_summary.csv"), pd.read_csv(OUT / "detection_by_type.csv")
    rob = json.loads((OUT / "robustness_summary.json").read_text())
    flags = pd.read_csv(OUT / "flags_clean.csv", dtype=str)
    pages = []

    # 1 Data health ------------------------------------------------------------------
    real, inj = h[h.dataset.str.startswith("real")], h[~h.dataset.str.startswith("real")]
    us = load_clean()["us"]
    err_rules = set(rr[rr.severity == "error"].id)
    bad = set(flags[flags.rule_id.isin(err_rules) & (flags.table == "us")].record_id)
    us["ok"] = ~us.record_id.isin(bad)
    us["month"] = us.period_end.dt.to_period("M").astype(str)
    ev = us.groupby("month").agg(n=("ok", "size"), ok=("ok", "mean")).reset_index()
    ev = ev[ev.n >= 15]
    e = go.Figure()
    e.add_bar(x=ev.month, y=ev.n, name="Returns", marker_color=GRAY, yaxis="y2", opacity=0.6)
    e.add_scatter(x=ev.month, y=ev.ok, name="Share passing all error rules", mode="lines+markers", line=dict(color=BLUE))
    e.update_layout(height=320, title="US returns by fiscal-year end month: volume and share passing every error rule",
                    yaxis=dict(tickformat=".0%", range=[0.8, 1.01]), yaxis2=dict(overlaying="y", side="right", showgrid=False), xaxis_type="category",
                    legend=dict(orientation="h", y=-0.2))
    kp = [(f"{len(rr)}", "rules, Python and SQL agree"), (f"{rr.flagged_real.sum():,}", "flags on the real data"),
          (f"{(log.status == 'Open - research').sum():,}", "issues in the research queue"),
          (f"{real.score.mean():.1%}", "average pass rate (real data)")]
    pages.append(("Data health", "Data health by source and dimension: real data vs data with SIMULATED injected errors", "PUBLIC DATA + SIMULATED", kp,
                  f'<div class="two">{div(heat(real, "Real data (PUBLIC DATA)"))}{div(heat(inj, "With 300 injected errors (SIMULATED)"))}</div>{div(e)}'))

    # 2 Issues -----------------------------------------------------------------------
    r = rr[rr.flagged_real > 0].sort_values("flagged_real")
    f = go.Figure()
    for sev, col in SEV.items():
        s = r[r.severity == sev]
        f.add_bar(y=s.id, x=s.flagged_real, orientation="h", name=sev, marker_color=col,
                  text=s.description, textposition="none", hovertemplate="%{y}: %{x} records<br>%{text}<extra></extra>")
    f.update_layout(barmode="stack", height=620, title="Flags on the real data, by rule and severity", xaxis_type="log",
                    xaxis_title="Records flagged (log scale)", legend=dict(orientation="h", y=-0.08))
    st = log.groupby(["table", "status"]).size().reset_index(name="n")
    g = go.Figure()
    scol = {"Open - research": RED, "Accepted - flagged": BLUE_L, "Resolved - rule action applied": "#1C5CAB", "Noted": GRAY, "Noted - systemic": "#E1E0D9"}
    for s_ in scol:
        x = st[st.status == s_]
        g.add_bar(x=[TNAME[t] for t in x.table], y=x.n, name=s_, marker_color=scol[s_])
    g.update_layout(barmode="stack", height=320, title="Issues log by source and status", legend=dict(orientation="h", y=-0.2))
    q = log[log.status == "Open - research"].groupby(["rule_id", "severity", "description"]).size().reset_index(name="open").sort_values(
        ["severity", "open"], ascending=[True, False])
    pages.append(("Issues", "Issues by rule and severity, status, and the research queue", "PUBLIC DATA",
                  [(f"{len(log):,}", "issues logged"), (f"{(log.severity == 'error').sum():,}", "error-level issues"),
                   (f"{(log.status == 'Open - research').sum():,}", "open, need research"), ("qa/issues_log.xlsx", "full log with decisions")],
                  f'<div class="two">{div(f)}<div>{div(g)}<h3>Research queue (open issues by rule, errors first)</h3>'
                  f'{table(q, {"rule_id": "Rule", "severity": "Severity", "description": "What fails", "open": "Open"})}</div></div>'))

    # 3 Source agreement ---------------------------------------------------------------
    rows = rec[~rec.measure.str.contains("found|recent|SEC|SBTi|Climate TRACE asset", regex=True)].copy()
    rows["label"] = rows.source_pair + ": " + rows.measure
    rows = rows.sort_values("agree_rate")
    a = go.Figure(go.Bar(y=rows.label, x=rows.agree_rate, orientation="h", marker_color=[BLUE if v >= 0.95 else RED for v in rows.agree_rate],
                         text=[f"{v:.1%} (n={n:,})" for v, n in zip(rows.agree_rate, rows.compared)], textposition="outside",
                         hovertemplate="%{y}<br>%{x:.1%}<extra></extra>"))
    a.update_layout(height=520, title="Agreement rate by source pair and measure", xaxis=dict(tickformat=".0%", range=[0, 1.25]))
    ep = pd.read_csv(OUT / "recon_epa_ct.csv")
    ep = ep[(ep.epa_co2e > 1000) & (ep.ct_co2e > 1000)]
    ok = (ep.ct_to_epa_ratio - 1).abs() <= 0.25
    sc = go.Figure()
    for m, col, name in ((ok, BLUE, "within ±25%"), (~ok, RED, "gap above 25%")):
        s = ep[m]
        sc.add_scatter(x=s.epa_co2e, y=s.ct_co2e, mode="markers", marker=dict(color=col, size=6, opacity=0.6), name=name,
                       text=s.record_id + " · " + s.state + " · " + s.ct_type.fillna(""),
                       hovertemplate="%{text}<br>EPA %{x:,.0f} t · CT %{y:,.0f} t<extra></extra>")
    sc.add_scatter(x=[1e3, 3e7], y=[1e3, 3e7], mode="lines", line=dict(color=INK2, dash="dash"), name="same value", hoverinfo="skip")
    sc.update_layout(height=520, title="EPA reported vs Climate TRACE modelled, power plants 2023 (tCO2e)", xaxis_type="log", yaxis_type="log",
                     xaxis_title="EPA GHGRP", yaxis_title="Climate TRACE", legend=dict(orientation="h", y=-0.15))
    soi = rec[(rec.source_pair == "IRS e-file vs IRS SOI extract") & (rec.measure == "revenue")].iloc[0]
    ct = rec[rec.measure == "emissions within ±25%"].iloc[0]
    pages.append(("Source agreement", "When sources disagree: IRS copies agree; modelled and reported emissions often do not", "PUBLIC DATA",
                  [(f"{soi.agree_rate:.1%}", "IRS e-file vs SOI revenue"), (f"{ct.agree_rate:.0%}", "power plants within ±25% (EPA vs CT)"),
                   ("30/30", "returns matching the original filing"), ("22", "fuzzy name matches rejected by hand")],
                  f'<div class="two">{div(a)}{div(sc)}</div>'))

    # 4 Score robustness ---------------------------------------------------------------
    mc = pd.read_csv(OUT / "robustness_mc_nonprofit.csv")
    t = go.Figure(go.Histogram(x=mc.tau, marker_color=BLUE, nbinsx=30))
    t.update_layout(height=340, title="Kendall tau vs base ranking, 1,000 random weightings (nonprofits)", xaxis_title="tau")
    d = det.sort_values("recall")
    dd = go.Figure()
    dd.add_bar(y=d.label, x=d.injected, orientation="h", name="Injected", marker_color=GRAY)
    dd.add_bar(y=d.label, x=d.detected, orientation="h", name="Detected", marker_color=[RED if v < 0.9 else BLUE for v in d.recall])
    dd.update_layout(barmode="group", height=340, title="SIMULATED errors: injected vs detected", legend=dict(orientation="h", y=-0.15))
    ei = pd.read_csv(OUT / "error_impact_nonprofit.csv")
    ei = ei[ei.injected_error]
    im = go.Figure()
    for blocked, col, name in ((True, GRAY, "withheld by the gate"), (False, RED, "would be published")):
        s = ei[(ei.status_gate == "blocked by data quality") == blocked]
        im.add_scatter(x=s.rank_pct_clean * 100, y=s.rank_pct_injected * 100, mode="markers", marker=dict(color=col, size=7), name=name)
    im.add_scatter(x=[0, 100], y=[0, 100], mode="lines", line=dict(color=INK2, dash="dash"), name="no change", hoverinfo="skip")
    im.update_layout(height=340, title="Records with an injected error: percentile rank before vs after", xaxis_title="clean rank",
                     yaxis_title="rank with the error", legend=dict(orientation="h", y=-0.2))
    oat = pd.concat([pd.read_csv(OUT / f"robustness_oat_{k}.csv").assign(kind=k) for k in ("nonprofit", "company")])
    oat["label"] = oat.kind + " · " + oat.pillar.str.replace("_", " ") + " x" + oat.factor.astype(str)
    o = go.Figure(go.Bar(y=oat.label, x=oat.tau, orientation="h", marker_color=[RED if v > 0 else BLUE for v in oat.scores_lost],
                         text=[f"{t_:.2f}" + (f" · {int(v)} scores lost" if v else "") for t_, v in zip(oat.tau, oat.scores_lost)], textposition="outside"))
    o.update_layout(height=340, title="One weight at a time (x0.5, x1.5): Kendall tau and scores lost", xaxis=dict(range=[0.6, 1.15]))
    npr, cor = rob["nonprofit"], rob["company"]
    pages.append(("Score robustness", "Score robustness: weights, coverage side effects and the effect of errors", "PUBLIC DATA + SIMULATED",
                  [(f"{npr['tau_median']:.2f}", "median Kendall tau, nonprofits"), (f"{cor['tau_median']:.2f}", "median Kendall tau, companies"),
                   (f"{det.detected.sum()}/{det.injected.sum()}", "injected errors detected"),
                   (f"{cor['gate_v1_moved_over_10pts_not_blocked']} → {cor['injected_moved_over_10pts_not_blocked']}", "company errors leaking, gate v1 → v2")],
                  f'<div class="two">{div(t)}{div(o)}{div(dd)}{div(im)}</div>'))

    nav = "".join(f'<button data-p="{i + 1}">{i + 1}. {html.escape(p[0])}</button>' for i, p in enumerate(pages))
    secs = ""
    for i, (name, title, tag, kp, body) in enumerate(pages):
        k = "".join(f'<div class="kpi"><b>{html.escape(v)}</b><span>{html.escape(t_)}</span></div>' for v, t_ in kp)
        secs += (f'<section id="p{i + 1}" class="page"><header><h1>{html.escape(title)}</h1><span class="tag">{tag}</span></header>'
                 f'<div class="kpis">{k}</div>{body}</section>')
    out = TEMPLATE.replace("{{NAV}}", nav).replace("{{SECTIONS}}", secs).replace("{{FOOTER}}", html.escape(FOOTER))
    DASH.mkdir(exist_ok=True)
    (DASH / "data_quality_cockpit.html").write_text(out, encoding="utf-8")
    print("dashboard:", (DASH / "data_quality_cockpit.html").stat().st_size // 1024, "KB")


TEMPLATE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Data quality cockpit</title><style>
:root{--bg:#F4F4F2;--card:#FCFCFB;--ink:#0B0B0B;--ink2:#52514E;--line:#E1E0D9;--blue:#1C5CAB}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:'Segoe UI',system-ui,sans-serif}
nav{display:flex;flex-wrap:wrap;gap:6px;padding:12px 16px;background:var(--card);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5}
nav .brand{font-weight:700;margin-right:12px;align-self:center}
nav button{border:1px solid var(--line);background:var(--bg);padding:7px 12px;border-radius:6px;cursor:pointer;font:inherit;color:var(--ink2)}
nav button.on{background:var(--blue);color:#fff;border-color:var(--blue)}
.page{display:none;max-width:1400px;margin:0 auto;padding:16px}.page.on{display:block}
header{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}h1{font-size:21px;margin:4px 0 12px}h3{font-size:14px;margin:14px 0 4px}
.tag{font-size:11px;font-weight:700;letter-spacing:.6px;color:var(--ink2);border:1px solid #C9C7BF;border-radius:4px;padding:4px 8px;white-space:nowrap}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:12px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 14px}.kpi b{display:block;font-size:24px;color:var(--blue)}
.kpi span{font-size:12px;color:var(--ink2)}.two{display:grid;grid-template-columns:repeat(auto-fit,minmax(560px,1fr));gap:12px;margin-bottom:12px}
table{border-collapse:collapse;width:100%;background:var(--card);font-size:12.5px}th,td{text-align:left;padding:5px 8px;border-bottom:1px solid var(--line)}
th{color:var(--ink2)}footer{text-align:center;color:#898781;font-size:12px;padding:16px}@media(max-width:600px){.two{grid-template-columns:1fr}h1{font-size:18px}}
</style></head><body><nav><span class="brand">Data quality cockpit</span>{{NAV}}</nav>{{SECTIONS}}<footer>{{FOOTER}} · demo score illustrative, not Carnelian's methodology · simulated parts labelled</footer>
<script>
function show(n){document.querySelectorAll('.page').forEach((s,i)=>s.classList.toggle('on',i==n-1));
document.querySelectorAll('nav button').forEach((b,i)=>b.classList.toggle('on',i==n-1));
document.querySelectorAll('#p'+n+' .plotly-graph-div').forEach(d=>{if(window.Plotly)Plotly.Plots.resize(d)});}
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{location.hash=b.dataset.p;show(+b.dataset.p)});
show(+(location.hash.slice(1))||1);
</script></body></html>"""

if __name__ == "__main__":
    main()
