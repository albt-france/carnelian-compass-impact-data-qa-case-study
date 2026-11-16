"""Write the rule catalogue as plain DuckDB SQL (sql/dq_rules.sql): one query per rule, runnable on the parquet tables.
Usage: python src/export_sql.py"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import ROOT  # noqa: E402
from dq.engine import load_rules  # noqa: E402

HEAD = """-- Data-quality rules as DuckDB SQL, generated from src/dq/rules.yaml (do not edit by hand).
-- Each query returns the records that FAIL the rule. Run from the repository root, e.g.:
--   duckdb -c ".read sql/dq_rules.sql"
-- Tables: data/outputs/tables/clean_{us,uk,companies,power}.parquet (PUBLIC DATA)
"""


def main():
    out = [HEAD]
    for r in load_rules().itertuples():
        sql = r.sql.replace("FROM t ", f"FROM '{{src}}' ")
        src = f"data/outputs/tables/clean_{r.table}.parquet"
        out.append(f"-- {r.id} [{r.dimension} / {r.severity}] {r.description}\n"
                   f"SELECT '{r.id}' AS rule_id, record_id FROM '{src}' AS t WHERE {sql.replace('{src}', src)};\n")
    (ROOT / "sql" / "dq_rules.sql").write_text("\n".join(out), encoding="utf-8")
    print("sql/dq_rules.sql:", len(out) - 1, "rules")


if __name__ == "__main__":
    main()
