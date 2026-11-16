"""Run the 40-rule catalogue on the real tables (PUBLIC DATA) and on the copy with injected errors (SIMULATED),
with both engines (pandas and DuckDB SQL), then write the rule results, the data-health scores and the issues log.

Usage: python src/run_checks.py
Outputs (data/outputs/): rule_results.csv, flags_clean.csv, flags_injected.csv, health.csv, issues_log.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import OUT  # noqa: E402
from dq.engine import health, load_rules, run_python, run_sql, summary  # noqa: E402
from prepare import TABLES, load_clean  # noqa: E402

AGGREGATE_INFO_ABOVE = 50   # info rules with more flags than this become one systemic issue


def load_injected() -> dict:
    return {k: pd.read_parquet(TABLES / f"injected_{k}.parquet") for k in ("us", "uk", "companies", "power")}


def both_engines(tables):
    py, sql = run_python(tables), run_sql(tables)
    key = ["rule_id", "record_id"]
    diff = py.merge(sql, on=key + ["table"], how="outer", indicator=True).query("_merge != 'both'")
    if len(diff):
        raise AssertionError(f"Python and SQL engines disagree on {len(diff)} flags:\n{diff.head()}")
    return py


def status(sev, research):
    if sev == "info":
        return "Noted"
    if research:
        return "Open - research"
    return "Resolved - rule action applied" if sev == "error" else "Accepted - flagged"


def issues_log(flags: pd.DataFrame, rules: pd.DataFrame, tables: dict) -> pd.DataFrame:
    f = flags.merge(rules.drop(columns="table"), left_on="rule_id", right_on="id")
    rows = []
    for rid, g in f.groupby("rule_id", sort=False):
        r = g.iloc[0]
        if r.severity == "info" and len(g) > AGGREGATE_INFO_ABOVE:
            rows.append(dict(rule_id=rid, table=r.table, record_id=f"{len(g)} records", dimension=r.dimension, severity=r.severity,
                             field=r.field, description=r.description, status="Noted - systemic", decision=r.action,
                             needs_research="No", scope="systemic"))
            continue
        for rec in g.record_id:
            rows.append(dict(rule_id=rid, table=r.table, record_id=rec, dimension=r.dimension, severity=r.severity, field=r.field,
                             description=r.description, status=status(r.severity, r.research), decision=r.action,
                             needs_research="Yes" if r.research else "No", scope="record"))
    log = pd.DataFrame(rows)
    log.insert(0, "issue_id", [f"I{i + 1:04d}" for i in range(len(log))])
    log["source_label"] = "PUBLIC DATA"
    return log


def main():
    rules = load_rules()
    clean, inj = load_clean(), load_injected()
    fc, fi = both_engines(clean), both_engines(inj)
    fc.to_csv(OUT / "flags_clean.csv", index=False)
    fi.to_csv(OUT / "flags_injected.csv", index=False)
    s = summary(fc, clean, rules).rename(columns={"records_flagged": "flagged_real", "pass_rate": "pass_rate_real",
                                                  "records_checked": "checked_real"})
    si = summary(fi, inj, rules)[["id", "records_checked", "records_flagged"]].rename(
        columns={"records_checked": "checked_injected", "records_flagged": "flagged_injected"})
    res = s.merge(si, on="id")
    res = res.merge(rules[["id", "field", "sql"]], on="id")
    res.to_csv(OUT / "rule_results.csv", index=False)
    h = health(fc, clean, rules).assign(dataset="real (PUBLIC DATA)")
    hi = health(fi, inj, rules).assign(dataset="with injected errors (SIMULATED)")
    pd.concat([h, hi]).to_csv(OUT / "health.csv", index=False)
    log = issues_log(fc, rules, clean)
    log.to_csv(OUT / "issues_log.csv", index=False)
    print(f"rules: {len(rules)} | flags real: {len(fc)} | flags injected: {len(fi)} | issues logged: {len(log)} "
          f"(open research: {(log.status == 'Open - research').sum()}) | engines agree")


if __name__ == "__main__":
    main()
