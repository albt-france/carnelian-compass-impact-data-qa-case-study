# Data standards and control procedure

Proposed standards for the inputs of an impact score such as Compass, and the procedure used in this study to enforce them.
Rules live in [`src/dq/rules.yaml`](../src/dq/rules.yaml) (40 rules), run with two independent engines (pandas and DuckDB SQL,
exported to [`sql/dq_rules.sql`](../sql/dq_rules.sql)); the pipeline stops if the engines disagree.

## 1. Six dimensions

| Dimension | Question | Standard | Rules |
|---|---|---|---|
| Completeness | Is the field there? | Core totals present; functional split present when total expenses > 0; activity code present (else size-only peers); coverage shown with every score | COMP-01 to COMP-06 |
| Validity | Is the value possible? | No negative expenses, assets, liabilities or emissions; accounting period 360-371 days or annualised; period starts in the stated tax year; currency conversion consistent | VAL-01 to VAL-09 |
| Consistency | Do related fields agree? | Program + management + fundraising = total (±0.5%); Part IX = Part I total; assets - liabilities = net assets (±1%); year-on-year within 0.2x-5x; emissions per facility ≥ 25,000 tCO2e (GHGRP threshold) | CONS-01 to CONS-09 |
| Uniqueness | One record per entity and period? | One return per EIN per tax year (keep the latest); one row per charity number; one SEC registrant per parent; fuzzy matches below 100 reviewed by a person | UNIQ-01 to UNIQ-04 |
| Freshness | Is it current? | Period end less than 3 years before the as-of date; a newer filing in the master file triggers a refresh; filing status not overdue | FRESH-01 to FRESH-04 |
| Accuracy | Does it match another source? | Copies of the same filing agree within 1% (IRS e-file vs SOI extract); register vs annual return exact; model vs report within ±25% or logged; parent vs owner names compared at the same entity level | ACC-01 to ACC-08 |

## 2. Severity and what happens to the score

| Severity | Meaning | Effect on the score |
|---|---|---|
| error | the value is wrong or unusable | score withheld ("blocked by data quality") |
| warning | the value is possible but suspicious | score published with a flag; **hold** when the rule is marked `holds_score` |
| info | context (lag, coverage) | none; shown in the dashboard |

`holds_score` was added to CONS-08 and CONS-09 after the error-injection audit (gate v2): with errors-only gating, 15 of 20
injected company errors (units, x10) still moved a published rank by more than 10 percentile points.

## 3. Control procedure

1. **Ingest** with a neutral client, a pause between requests, cached files; person-level fields (officers, trustees, care-of
   names, contacts, addresses) are never read.
2. **Validate**: run the 40 rules in both engines on every refresh.
3. **Reconcile**: join on identifier **and** fiscal period; compare copies of a filing (1%), model vs report (±25%), and check a
   stratified sample against original documents (30 returns here, 9 fields each).
4. **Gate**: error flags and `holds_score` warnings withhold the score.
5. **Review**: every flag goes to the issues log (`qa/issues_log.xlsx`) with rule, severity, status, decision and research need.
   Judgement calls (fuzzy name matches, parent companies, model-vs-report gaps) go to the research queue.
6. **Release** only when the tests pass (unit, golden set, edge cases, non-regression) and the regression sample is unchanged or
   re-frozen with a written reason.

## 4. Issue statuses

`Open - research` → `Closed - corrected at source` / `Closed - false positive`; `Accepted - flagged` (kept with a flag);
`Resolved - rule action applied` (automatic action, e.g. keep the latest return); `Noted` / `Noted - systemic` (info rules).

## 5. Test cases and reference examples

- **Golden set**: 20 real organisations scored by hand in Excel (`qa/QA_workbook.xlsx`, sheet Golden_set); expected values in
  `tests/golden/golden_expected.csv` (LibreOffice recalculation). The code must match every intermediate value.
- **Edge cases**: no revenue, new organisation, zero expenses, partial data, extreme values, GBP amounts, 18-month year,
  negative revenue, original + amended return (`tests/test_edge_cases.py`).
- **Non-regression**: 150 frozen scores (`tests/regression/`).
- **Error injection**: 300 known errors, 10 types (`src/inject_errors.py`), recall and precision by type.
