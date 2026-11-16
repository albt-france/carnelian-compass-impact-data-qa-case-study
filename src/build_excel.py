"""QA workbook (qa/QA_workbook.xlsx) and issues log (qa/issues_log.xlsx).

Inputs are data values (public records, flags, rule definitions); every result is an Excel formula, so a reviewer
can audit each number. The golden set recomputes the demo score by hand for 20 organisations, independently of
the Python code (see src/golden.py and tests/test_golden.py). Document properties are left empty.

Usage: python src/build_excel.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import OUT, QA  # noqa: E402
from dq.engine import load_rules  # noqa: E402
from prepare import load_clean  # noqa: E402
from scoring.engine import latest_per_org, load_config  # noqa: E402

HEAD = PatternFill("solid", fgColor="E1E0D9")
INPUT = PatternFill("solid", fgColor="FFFFFF")
CALC = PatternFill("solid", fgColor="EEF5FD")
BOLD = Font(bold=True)
NOTE = Font(italic=True, color="52514E")
QA.mkdir(exist_ok=True)


def golden_ids(org: pd.DataFrame, n=20) -> list:
    """20 real organisations chosen to cover the cases the score must handle (seeded, deterministic)."""
    o = org.copy()
    days = (o.period_end - o.period_begin).dt.days + 1
    picks = []

    def take(mask, k):
        cand = o[mask & ~o.record_id.isin(picks)].sort_values("record_id")
        picks.extend(cand.sample(min(k, len(cand)), random_state=42).record_id.tolist())
    take(~days.between(360, 371), 2)                        # short or long accounting period
    take(o.contributions.fillna(0) <= 0, 2)                  # no contributions -> fundraising cost missing
    take(o.revenue_py.isna() | (o.revenue_py <= 0), 2)       # new organisation, no prior year
    take(o.ntee_major.isna(), 1)                             # no NTEE code -> peer fallback
    take(o.net_assets / o.expenses.clip(lower=1) * 12 > 60, 1)   # reserves above the cap
    take(o.liabilities > o.assets, 1)                        # debt ratio above 1
    take(o.audited.isna(), 1)                                # audit flag missing
    for band in sorted(o.size_band.dropna().unique()):        # fill up across size bands
        take(o.size_band == band, 2)
    take(o.record_id.notna(), max(0, n - len(picks)))
    return picks[:n]


def style_header(ws, row=1):
    for c in ws[row]:
        c.fill, c.font = HEAD, BOLD
        c.alignment = Alignment(wrap_text=True, vertical="top")


def widths(ws, w):
    for i, x in enumerate(w, 1):
        ws.column_dimensions[get_column_letter(i)].width = x


def blank_props(wb):
    p = wb.properties
    p.creator = ""
    p.lastModifiedBy = ""
    p.title = p.subject = p.description = p.keywords = p.category = None


def write_df(ws, df, start_row=1):
    ws.append(list(df.columns)) if start_row == 1 else None
    for r in df.itertuples(index=False):
        ws.append([None if (isinstance(v, float) and np.isnan(v)) or v is pd.NaT or (v is pd.NA) else
                   (v.to_pydatetime() if isinstance(v, pd.Timestamp) else v) for v in r])


# ------------------------------------------------------------------ sheets
def sheet_readme(wb):
    ws = wb.active
    ws.title = "README"
    lines = [
        ("Carnelian Compass: how to trust an impact score - QA workbook", BOLD),
        ("Independent case study based on public data · not affiliated with or endorsed by Carnelian Ventures", NOTE),
        ("", None),
        ("White cells = inputs (public data, rule definitions, flags). Blue cells = formulas. No pasted results.", None),
        ("Rules: 40 data-quality rules (src/dq/rules.yaml); flag counts are COUNTIF formulas over the Flags sheet.", None),
        ("Issues_log: every flag on the real data, with status, decision and research need (filter by status).", None),
        ("Golden_set: the demo score recomputed by hand for 20 real organisations; the Python code must match it exactly.", None),
        ("Population: the 2,000 organisations the percentiles are taken from (inputs + metric formulas).", None),
        ("Manual_check: 30 returns compared field by field with the original e-filed Form 990.", None),
        ("Detection: SIMULATED injected errors vs what the rules caught (recall by type).", None),
        ("Summary: headline numbers, all formulas.", None),
        ("", None),
        ("Labels: PUBLIC DATA = real records (IRS, NCCS e-file, Charity Commission, EPA, Climate TRACE, SBTi, SEC).", None),
        ("SIMULATED = errors injected on purpose to measure detection. The demo score is illustrative, not Carnelian's methodology.", None),
    ]
    for text, font in lines:
        ws.append([text])
        if font:
            ws.cell(ws.max_row, 1).font = font
    ws.column_dimensions["A"].width = 120


def sheet_rules_flags(wb, rules, results, flags):
    ws = wb.create_sheet("Flags")
    ws.append(["rule_id", "table", "record_id"])
    for r in flags.itertuples(index=False):
        ws.append(list(r))
    style_header(ws)
    widths(ws, [10, 12, 28])
    ws.freeze_panes = "A2"
    ws = wb.create_sheet("Rules", 1)
    cols = ["id", "table", "dimension", "severity", "field", "description", "sql", "action", "research", "records_checked",
            "flagged (formula)", "pass rate (formula)"]
    ws.append(cols)
    chk = results.set_index("id").checked_real
    for i, r in enumerate(rules.itertuples(), start=2):
        ws.append([r.id, r.table, r.dimension, r.severity, r.field, r.description, r.sql, r.action,
                   "Yes" if r.research else "No", int(chk[r.id]), f'=COUNTIF(Flags!$A:$A,A{i})', f"=1-K{i}/J{i}"])
        ws[f"K{i}"].fill = ws[f"L{i}"].fill = CALC
        ws[f"L{i}"].number_format = "0.0%"
    style_header(ws)
    widths(ws, [10, 11, 13, 9, 26, 60, 50, 45, 9, 10, 10, 10])
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = f"A1:L{ws.max_row}"
    ws.conditional_formatting.add(f"L2:L{ws.max_row}", CellIsRule(operator="lessThan", formula=["0.95"], font=Font(color="B02E2E", bold=True)))


def sheet_issues(wb, log, name="Issues_log"):
    ws = wb.create_sheet(name)
    log = log.copy()
    log["owner"] = ""
    log["date_opened"] = pd.Timestamp("2026-11-16").date()
    log["resolution_note"] = ""
    ws.append(list(log.columns))
    for r in log.itertuples(index=False):
        ws.append(list(r))
    style_header(ws)
    n = ws.max_row
    dv = DataValidation(type="list", formula1='"Open - research,Resolved - rule action applied,Accepted - flagged,Noted,Noted - systemic,Closed - false positive,Closed - corrected at source"', allow_blank=False)
    ws.add_data_validation(dv)
    col = get_column_letter(list(log.columns).index("status") + 1)
    dv.add(f"{col}2:{col}{n}")
    widths(ws, [8, 9, 10, 26, 12, 9, 22, 55, 26, 45, 9, 9, 12, 10, 12, 30])
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = f"A1:{get_column_letter(ws.max_column)}{n}"
    return ws


def sheet_population(wb, org, cfg):
    ws = wb.create_sheet("Population")
    inputs = ["record_id", "ein", "ntee_major", "period_begin", "period_end", "efiled_utc", "audited", "currency", "revenue",
              "revenue_py", "expenses", "assets", "liabilities", "net_assets", "exp_total_p9", "exp_program", "exp_fundraising",
              "contributions"]
    calc = ["days", "annual_factor", "size_band", "peer_group", "reserves_months", "debt_ratio", "program_share",
            "fundraising_cost", "revenue_change", "transparency"]
    ws.append(inputs + calc)
    o = org.copy()
    o["efiled_utc"] = pd.to_datetime(o.efiled_at, utc=True).dt.tz_localize(None)
    o["audited"] = o.audited.map({True: 1, False: 0})
    caps = cfg["caps"]
    fx = cfg["fx_usd_per_gbp"]
    b = cfg["size_bands"]
    lab = cfg["size_labels"]
    for i, r in enumerate(o[inputs].itertuples(index=False), start=2):
        vals = [None if (v is None or v is pd.NaT or (isinstance(v, float) and np.isnan(v)) or v is pd.NA) else
                (v.to_pydatetime() if isinstance(v, pd.Timestamp) else v) for v in r]
        f = {
            "days": f'=IF(OR(D{i}="",E{i}=""),"",E{i}-D{i}+1)',
            "annual_factor": f'=IF(S{i}="",1,IF(AND(S{i}>0,OR(S{i}<360,S{i}>371)),365/S{i},1))',
            "size_band": (f'=IF(I{i}="","nan",IF(MAX(I{i},0)*IF(H{i}="GBP",{fx},1)<{b[1]},"{lab[0]}",IF(MAX(I{i},0)*IF(H{i}="GBP",{fx},1)<{b[2]},"{lab[1]}",'
                          f'IF(MAX(I{i},0)*IF(H{i}="GBP",{fx},1)<{b[3]},"{lab[2]}","{lab[3]}"))))'),
            "peer_group": f'=IF(AND(C{i}<>"",COUNTIFS($C:$C,C{i},$U:$U,U{i})>={cfg["peer_min_size"]}),C{i}&"|"&U{i},"ALL|"&U{i})',
            "reserves_months": f'=IF(OR(K{i}="",N{i}=""),"",IF(K{i}*T{i}>0,ROUND(MIN(MAX(N{i}/(K{i}*T{i}/12),{caps["reserves_months"][0]}),{caps["reserves_months"][1]}),6),""))',
            "debt_ratio": f'=IF(OR(L{i}="",M{i}=""),"",IF(L{i}>0,ROUND(MIN(MAX(M{i}/L{i},{caps["debt_ratio"][0]}),{caps["debt_ratio"][1]}),6),""))',
            "program_share": f'=IF(OR(O{i}="",P{i}=""),"",IF(O{i}>0,ROUND(MIN(MAX(P{i}/O{i},0),1),6),""))',
            "fundraising_cost": f'=IF(OR(R{i}="",Q{i}=""),"",IF(R{i}>0,ROUND(MIN(MAX(Q{i}/R{i},{caps["fundraising_cost"][0]}),{caps["fundraising_cost"][1]}),6),""))',
            "revenue_change": f'=IF(OR(J{i}="",I{i}=""),"",IF(AND(J{i}>0,I{i}>=0),ROUND(MIN(ABS(I{i}/J{i}-1),{caps["revenue_change"][1]}),6),""))',
            "transparency": (f'=IF(AND(G{i}="",F{i}=""),"",ROUND(IF(G{i}="",IF(F{i}<=EDATE(E{i},10)+15,1,0),'
                             f'IF(F{i}="",G{i},(G{i}+IF(F{i}<=EDATE(E{i},10)+15,1,0))/2)),6))'),
        }
        ws.append(vals + [f[c] for c in calc])
    style_header(ws)
    for col in "DE":
        for c in ws[col][1:]:
            c.number_format = "yyyy-mm-dd"
    for c in ws["F"][1:]:
        c.number_format = "yyyy-mm-dd hh:mm"
    widths(ws, [24, 11, 6, 11, 11, 16, 7, 7] + [13] * 10 + [7, 8, 11, 14] + [11] * 6)
    ws.freeze_panes = "B2"
    return len(o) + 1


def sheet_golden(wb, org, ids, cfg, last):
    ws = wb.create_sheet("Golden_set", 3)
    pil = cfg["pillars"]
    ws["A1"] = "Golden set: the demo score computed by hand for 20 real organisations (PUBLIC DATA). Edit the weights to test a change."
    ws["A1"].font = BOLD
    ws["A2"] = "Percentile = (count below + 0.5 x count equal) / count, within the peer group, on the Population sheet. Points = 100 x percentile (or 100 x (1 - percentile) when lower is better)."
    ws["A2"].font = NOTE
    ws.append([])
    ws.append(["Pillar", "Weight"])
    style_header(ws, 4)
    wrow = {}
    for k, p in pil.items():
        ws.append([k, p["weight"]])
        wrow[k] = ws.max_row
    ws.append(["min_coverage", cfg["min_coverage"]])
    covrow = ws.max_row
    ws.append([])
    metrics = [(m, d) for p in pil.values() for m, d in p["metrics"].items()]
    mcol = {"reserves_months": "W", "debt_ratio": "X", "program_share": "Y", "fundraising_cost": "Z", "revenue_change": "AA", "transparency": "AB"}
    hdr = ["record_id", "Population row", "peer_group"] + [f"{m} (metric)" for m, _ in metrics] + [f"{m} (pct)" for m, _ in metrics] + \
          [f"{m} (points)" for m, _ in metrics] + list(pil) + ["coverage", "score"]
    ws.append(hdr)
    h = ws.max_row
    style_header(ws, h)
    pos = {rid: i + 2 for i, rid in enumerate(org.record_id)}
    nm = len(metrics)
    for rid in ids:
        r = ws.max_row + 1
        row = [rid, pos[rid], f"=INDEX(Population!$V:$V,B{r})"]
        for m, _ in metrics:
            row.append(f'=INDEX(Population!${mcol[m]}:${mcol[m]},B{r})')
        for j, (m, _) in enumerate(metrics):
            x = f"{get_column_letter(4 + j)}{r}"
            rng = f"Population!${mcol[m]}$2:${mcol[m]}${last}"
            peer = f"Population!$V$2:$V${last}"
            row.append(f'=IF({x}="","",(COUNTIFS({peer},$C{r},{rng},"<"&{x})+0.5*COUNTIFS({peer},$C{r},{rng},{x}))'
                       f'/COUNTIFS({peer},$C{r},{rng},">=-1E+300"))')
        for j, (m, d) in enumerate(metrics):
            pc = f"{get_column_letter(4 + nm + j)}{r}"
            row.append(f'=IF({pc}="","",100*{pc})' if d == "higher" else f'=IF({pc}="","",100*(1-{pc}))')
        start = 4 + 2 * nm
        k0 = 0
        pcells = []
        for k, p in pil.items():
            cols = [f"{get_column_letter(start + k0 + j)}{r}" for j in range(len(p["metrics"]))]
            k0 += len(p["metrics"])
            row.append(f'=IFERROR(AVERAGE({",".join(cols)}),"")')
            pcells.append((k, f"{get_column_letter(len(row))}{r}"))
        num = "+".join(f'IF({c}="",0,$B${wrow[k]}*{c})' for k, c in pcells)
        den = "+".join(f'IF({c}="",0,$B${wrow[k]})' for k, c in pcells)
        tot = "+".join(f"$B${wrow[k]}" for k, _ in pcells)
        row.append(f"=({den})/({tot})")
        cov = f"{get_column_letter(len(row))}{r}"
        row.append(f'=IF({cov}>=$B${covrow},({num})/({den}),"")')
        ws.append(row)
        for c in ws[r][2:]:
            c.fill = CALC
    for c in ws[h + 1:ws.max_row]:
        for x in c[3:]:
            x.number_format = "0.0000"
    widths(ws, [24, 9, 13] + [12] * (len(hdr) - 3))
    ws.freeze_panes = ws.cell(h + 1, 2)
    return h + 1, h + len(ids)


def sheet_manual(wb, mc):
    ws = wb.create_sheet("Manual_check")
    ws.append(["record_id", "size_band", "field", "dataset_value", "document_value", "difference (formula)", "match (formula)", "source_xml"])
    for i, r in enumerate(mc.itertuples(), start=2):
        ws.append([r.record_id, r.size_band, r.field, r.dataset_value, None if pd.isna(r.document_value) else r.document_value,
                   f"=D{i}-N(E{i})", f'=IF(ABS(F{i})<=1,"match","MISMATCH")', r.source_xml])
        ws[f"F{i}"].fill = ws[f"G{i}"].fill = CALC
    style_header(ws)
    widths(ws, [24, 10, 16, 15, 15, 12, 11, 70])
    ws.freeze_panes = "A2"
    n = ws.max_row
    ws["J1"], ws["K1"] = "Fields checked", f"=COUNTA(C2:C{n})"
    ws["J2"], ws["K2"] = "Fields matching", f'=COUNTIF(G2:G{n},"match")'
    ws["J3"], ws["K3"] = "Match rate", "=K2/K1"
    ws["K3"].number_format = "0.0%"
    ws["J5"] = "Method: each value read from the original e-filed Form 990 (XML, link in column H) and compared with the dataset. Blank document value = line left empty on the return (= 0)."
    return n


def sheet_detection(wb, det, by_type):
    ws = wb.create_sheet("Detection_detail")
    ws.append(["error_id", "table", "error_type", "record_id", "detected", "rules", "by_designed_rule"])
    for r in det[["error_id", "table", "error_type", "record_id", "detected", "rules", "by_designed_rule"]].itertuples(index=False):
        ws.append(list(r))
    style_header(ws)
    widths(ws, [8, 11, 16, 28, 9, 30, 10])
    n = ws.max_row
    ws = wb.create_sheet("Detection")
    ws.append(["SIMULATED: 300 errors injected on a copy of the real data (seed 42); answer key opened only after the checks ran."])
    ws["A1"].font = BOLD
    ws.append(["error_type", "label", "injected (formula)", "detected (formula)", "recall (formula)", "designed rules"])
    style_header(ws, 2)
    for r in by_type.sort_values("error_type").itertuples():
        i = ws.max_row + 1
        ws.append([r.error_type, r.label, f'=COUNTIF(Detection_detail!$C$2:$C${n},A{i})',
                   f'=COUNTIFS(Detection_detail!$C$2:$C${n},A{i},Detection_detail!$E$2:$E${n},TRUE)', f"=D{i}/C{i}", r.designed_rules])
        ws[f"E{i}"].number_format = "0.0%"
        for c in "CDE":
            ws[f"{c}{i}"].fill = CALC
    i = ws.max_row + 1
    ws.append(["TOTAL", "", f"=SUM(C3:C{i - 1})", f"=SUM(D3:D{i - 1})", f"=D{i}/C{i}", ""])
    ws[f"E{i}"].number_format = "0.0%"
    for c in ws[i]:
        c.font = BOLD
    widths(ws, [16, 24, 12, 12, 10, 40])
    return i


def sheet_summary(wb, det_total_row, manual_n, g_first, g_last):
    ws = wb.create_sheet("Summary", 1)
    ws.append(["Summary (all formulas)", ""])
    ws["A1"].font = BOLD
    rows = [
        ("Rules in the catalogue", "=COUNTA(Rules!A:A)-1", "0"),
        ("Flags on the real data (PUBLIC DATA)", "=COUNTA(Flags!A:A)-1", "#,##0"),
        ("Rules with a pass rate below 95%", '=COUNTIF(Rules!L:L,"<0.95")', "0"),
        ("Issues logged", "=COUNTA(Issues_log!A:A)-1", "#,##0"),
        ("Issues open for research", '=COUNTIF(Issues_log!K:K,"Yes")', "#,##0"),
        ("Errors injected (SIMULATED)", f"=Detection!C{det_total_row}", "0"),
        ("Errors detected", f"=Detection!D{det_total_row}", "0"),
        ("Detection rate", f"=Detection!E{det_total_row}", "0.0%"),
        ("Manual check: fields matching the original return", f"=Manual_check!K3", "0.0%"),
        ("Golden set: organisations", f"=COUNTA(Golden_set!A{g_first}:A{g_last})", "0"),
        ("Golden set: average demo score", f"=AVERAGE(Golden_set!AA{g_first}:AA{g_last})", "0.0"),
    ]
    for label, f, fmt in rows:
        ws.append([label, f])
        ws.cell(ws.max_row, 2).number_format = fmt
        ws.cell(ws.max_row, 2).fill = CALC
    widths(ws, [55, 16])


def main():
    cfg = load_config()["nonprofit"]
    rules = load_rules()
    results = pd.read_csv(OUT / "rule_results.csv")
    flags = pd.read_csv(OUT / "flags_clean.csv", dtype=str)
    log = pd.read_csv(OUT / "issues_log.csv", dtype=str)
    org = latest_per_org(load_clean()["us"]).reset_index(drop=True)
    ids = golden_ids(org)
    pd.Series(ids, name="record_id").to_csv(OUT / "golden_ids.csv", index=False)
    wb = Workbook()
    sheet_readme(wb)
    sheet_rules_flags(wb, rules, results, flags)
    sheet_issues(wb, log)
    last = sheet_population(wb, org, cfg)
    g_first, g_last = sheet_golden(wb, org, ids, cfg, last)
    manual_n = sheet_manual(wb, pd.read_csv(OUT / "manual_check.csv"))
    det_row = sheet_detection(wb, pd.read_csv(OUT / "detection_detail.csv"), pd.read_csv(OUT / "detection_by_type.csv"))
    sheet_summary(wb, det_row, manual_n, g_first, g_last)
    blank_props(wb)
    wb.calculation.fullCalcOnLoad = True
    wb.save(QA / "QA_workbook.xlsx")
    wb2 = Workbook()
    wb2.remove(wb2.active)
    sheet_issues(wb2, log, "Issues_log")
    blank_props(wb2)
    wb2.save(QA / "issues_log.xlsx")
    (OUT / "golden_layout.txt").write_text(f"{g_first},{g_last}", encoding="utf-8")
    print("QA workbook:", QA / "QA_workbook.xlsx", "| golden rows", g_first, "-", g_last)


if __name__ == "__main__":
    main()
