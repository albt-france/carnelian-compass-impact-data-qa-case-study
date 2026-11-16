"""Build and execute the single analysis notebook (notebooks/carnelian_compass_qa.ipynb).
It reads the pipeline outputs and shows small, aggregated tables only. Usage: python src/build_notebook.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import nbformat as nbf
from nbconvert.preprocessors import ExecutePreprocessor

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import ROOT  # noqa: E402

NB = ROOT / "notebooks" / "carnelian_compass_qa.ipynb"
md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell

CELLS = [
    md("# Carnelian Compass: how to trust an impact score\n"
       "Data-quality and validation framework for nonprofit and ESG scoring, on public data.\n\n"
       "*Independent case study based on public data · not affiliated with or endorsed by Carnelian Ventures.* "
       "Real records are labelled **PUBLIC DATA**; injected errors are **SIMULATED**. The demo score is illustrative, "
       "not Carnelian's methodology. This notebook reads the outputs of `python src/run_all.py`."),
    code("import json, sys\nfrom pathlib import Path\nimport pandas as pd\n"
         "ROOT = Path.cwd().parent if Path.cwd().name == 'notebooks' else Path.cwd()\nsys.path.insert(0, str(ROOT / 'src'))\n"
         "OUT = ROOT / 'data' / 'outputs'\nfrom prepare import load_clean\npd.set_option('display.width', 140)\nt = load_clean()\n"
         "{k: v.shape for k, v in t.items()}"),
    md("## 1. Data profile (PUBLIC DATA)\nRecords per source, and the share of missing values in the fields the score needs."),
    code("us = t['us']\nkey = ['revenue', 'expenses', 'assets', 'exp_program', 'exp_fundraising', 'contributions', 'revenue_py', 'ntee_cd', 'audited', 'soi_revenue']\n"
         "us[key].isna().mean().round(3).rename('share missing').to_frame().T"),
    code("us.drop_duplicates('ein').groupby('size_band').agg(orgs=('ein', 'nunique'), median_revenue=('revenue', 'median'),\n"
         "    ntee_missing=('ntee_cd', lambda s: s.isna().mean()), audited=('audited', lambda s: s.astype(float).mean())).round(3)"),
    md("## 2. Rule results\n40 rules over six dimensions, run in pandas **and** DuckDB SQL (the pipeline stops if they disagree)."),
    code("rr = pd.read_csv(OUT / 'rule_results.csv')\n"
         "rr.groupby(['dimension', 'severity']).agg(rules=('id', 'size'), flags_real=('flagged_real', 'sum')).unstack(fill_value=0)"),
    code("rr[rr.flagged_real > 0].sort_values('flagged_real', ascending=False)[['id', 'severity', 'description', 'flagged_real', 'pass_rate_real']].head(12)"),
    code("pd.read_csv(OUT / 'health.csv').pivot_table(index=['dataset', 'table'], columns='dimension', values='score').round(3)"),
    md("## 3. Reconciliation between sources"),
    code("pd.read_csv(OUT / 'reconciliation_summary.csv')[['source_pair', 'measure', 'compared', 'agree_rate', 'note']]"),
    code("mc = pd.read_csv(OUT / 'manual_check.csv')\nmc.groupby('field').match.mean().rename('match rate vs original return').to_frame().T"),
    md("## 4. Detection of the 300 injected errors (SIMULATED)\nRecall = injected errors caught; precision = share of new alerts that point at an injected error; "
       "baseline = alerts the same rules raise on the untouched real data."),
    code("pd.read_csv(OUT / 'detection_by_type.csv')[['label', 'injected', 'detected', 'recall', 'precision', 'designed_rules', 'baseline_alerts_real_data']]"),
    code("d = pd.read_csv(OUT / 'detection_detail.csv')\nd[~d.detected].groupby(['table', 'error_type']).size().rename('missed')"),
    md("## 5. Score sensitivity"),
    code("s = json.loads((OUT / 'robustness_summary.json').read_text())\npd.DataFrame(s).round(3)"),
    code("pd.concat([pd.read_csv(OUT / f'robustness_oat_{k}.csv').assign(kind=k) for k in ('nonprofit', 'company')]).round(3)"),
    md("## 6. Cases that need more research (anonymised)\nOpen research items by rule, and three anonymised examples where sources contradict each other."),
    code("log = pd.read_csv(OUT / 'issues_log.csv')\nlog[log.status == 'Open - research'].groupby(['rule_id', 'severity']).size().rename('open').sort_values(ascending=False).head(10)"),
    code("soi = pd.read_csv(OUT / 'recon_irs_soi.csv').sort_values('rev_gap', ascending=False).head(3)\n"
         "soi.assign(case=[f'Nonprofit #{i + 1}' for i in range(len(soi))], ratio=(soi.revenue / soi.soi_revenue).round(3))[['case', 'size_band', 'ratio']]"),
    md("**Reading**: every IRS-side disagreement sits on an amended return; the fix is to join on EIN + fiscal period and keep the latest "
       "return, while logging both. Model-vs-report gaps on power plants are logged, not averaged."),
]


def main():
    nb = nbf.v4.new_notebook()
    nb.cells = CELLS
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    ExecutePreprocessor(timeout=600, kernel_name="python3").preprocess(nb, {"metadata": {"path": str(NB.parent)}})
    NB.parent.mkdir(exist_ok=True)
    nbf.write(nb, NB)
    print("notebook:", NB.relative_to(ROOT))


if __name__ == "__main__":
    main()
