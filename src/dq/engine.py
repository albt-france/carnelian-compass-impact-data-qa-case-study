"""Run the rule catalogue with two engines (pandas and DuckDB SQL) and summarise the results."""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import yaml

from dq.rules_py import RULES

CATALOGUE = Path(__file__).with_name("rules.yaml")
DIMENSIONS = ["completeness", "validity", "consistency", "uniqueness", "freshness", "accuracy"]


def load_rules() -> pd.DataFrame:
    return pd.DataFrame(yaml.safe_load(CATALOGUE.read_text(encoding="utf-8"))["rules"])


def run_python(tables: dict, rules: pd.DataFrame | None = None) -> pd.DataFrame:
    rules = load_rules() if rules is None else rules
    out = []
    for r in rules.itertuples():
        d = tables[r.table]
        mask = RULES[r.id](d).fillna(False).astype(bool)
        out.append(pd.DataFrame({"rule_id": r.id, "table": r.table, "record_id": d.loc[mask, "record_id"].values}))
    return pd.concat(out, ignore_index=True)


def run_sql(tables: dict, rules: pd.DataFrame | None = None) -> pd.DataFrame:
    rules = load_rules() if rules is None else rules
    con = duckdb.connect()
    out = []
    for r in rules.itertuples():
        t = tables[r.table]
        con.register("t", t)
        ids = con.execute(f"SELECT record_id FROM t WHERE {r.sql}").df().record_id
        con.unregister("t")
        out.append(pd.DataFrame({"rule_id": r.id, "table": r.table, "record_id": ids.values}))
    con.close()
    return pd.concat(out, ignore_index=True)


def summary(flags: pd.DataFrame, tables: dict, rules: pd.DataFrame | None = None) -> pd.DataFrame:
    rules = load_rules() if rules is None else rules
    n = flags.groupby("rule_id").record_id.nunique()
    s = rules[["id", "table", "dimension", "severity", "description", "action", "research"]].copy()
    s["records_checked"] = s.table.map(lambda k: len(tables[k]))
    s["records_flagged"] = s.id.map(n).fillna(0).astype(int)
    s["pass_rate"] = 1 - s.records_flagged / s.records_checked
    return s


def health(flags: pd.DataFrame, tables: dict, rules: pd.DataFrame | None = None) -> pd.DataFrame:
    """Share of records passing every rule of a dimension, per table (info rules excluded)."""
    rules = load_rules() if rules is None else rules
    f = flags.merge(rules[["id", "dimension", "severity"]], left_on="rule_id", right_on="id")
    f = f[f.severity != "info"]
    rows = []
    for tname, t in tables.items():
        for dim in DIMENSIONS:
            if not ((rules.table == tname) & (rules.dimension == dim) & (rules.severity != "info")).any():
                continue
            bad = f[(f.table == tname) & (f.dimension == dim)].record_id.nunique()
            rows.append(dict(table=tname, dimension=dim, records=len(t), failing=bad, score=1 - bad / len(t)))
    return pd.DataFrame(rows)
