-- Data-quality rules as DuckDB SQL, generated from src/dq/rules.yaml (do not edit by hand).
-- Each query returns the records that FAIL the rule. Run from the repository root, e.g.:
--   duckdb -c ".read sql/dq_rules.sql"
-- Tables: data/outputs/tables/clean_{us,uk,companies,power}.parquet (PUBLIC DATA)

-- COMP-01 [completeness / error] Core totals (revenue, total expenses, total assets) are present.
SELECT 'COMP-01' AS rule_id, record_id FROM 'data/outputs/tables/clean_us.parquet' AS t WHERE revenue IS NULL OR expenses IS NULL OR assets IS NULL;

-- COMP-02 [completeness / error] Functional expense split (program / management / fundraising) is present when total expenses are positive.
SELECT 'COMP-02' AS rule_id, record_id FROM 'data/outputs/tables/clean_us.parquet' AS t WHERE exp_total_p9 > 0 AND (exp_program IS NULL OR exp_management IS NULL OR exp_fundraising IS NULL);

-- COMP-03 [completeness / warning] NTEE activity code is present (needed for peer-group normalisation).
SELECT 'COMP-03' AS rule_id, record_id FROM 'data/outputs/tables/clean_us.parquet' AS t WHERE ntee_cd IS NULL;

-- COMP-04 [completeness / warning] Latest income and expenditure are present in the register.
SELECT 'COMP-04' AS rule_id, record_id FROM 'data/outputs/tables/clean_uk.parquet' AS t WHERE latest_income IS NULL OR latest_expenditure IS NULL;

-- COMP-05 [completeness / info] Revenue is available (needed for carbon intensity).
SELECT 'COMP-05' AS rule_id, record_id FROM 'data/outputs/tables/clean_companies.parquet' AS t WHERE revenue_2023 IS NULL;

-- COMP-06 [completeness / warning] Emissions for the base year 2021 are available (needed for the trend).
SELECT 'COMP-06' AS rule_id, record_id FROM 'data/outputs/tables/clean_companies.parquet' AS t WHERE co2e_2021 IS NULL OR co2e_2021 = 0;

-- VAL-01 [validity / error] Total expenses are not negative.
SELECT 'VAL-01' AS rule_id, record_id FROM 'data/outputs/tables/clean_us.parquet' AS t WHERE expenses < 0 OR exp_total_p9 < 0;

-- VAL-02 [validity / error] Total assets and liabilities are not negative.
SELECT 'VAL-02' AS rule_id, record_id FROM 'data/outputs/tables/clean_us.parquet' AS t WHERE assets < 0 OR liabilities < 0;

-- VAL-03 [validity / warning] Negative total revenue (possible with investment losses, but rare).
SELECT 'VAL-03' AS rule_id, record_id FROM 'data/outputs/tables/clean_us.parquet' AS t WHERE revenue < 0;

-- VAL-04 [validity / warning] Accounting period lasts 360 to 371 days (short first year or 18-month period otherwise).
SELECT 'VAL-04' AS rule_id, record_id FROM 'data/outputs/tables/clean_us.parquet' AS t WHERE period_days_calc NOT BETWEEN 360 AND 371;

-- VAL-05 [validity / error] The period starts in the stated tax year (tax year 2023 = period beginning in 2023).
SELECT 'VAL-05' AS rule_id, record_id FROM 'data/outputs/tables/clean_us.parquet' AS t WHERE year(period_begin) <> 2023;

-- VAL-06 [validity / error] Income and expenditure are not negative.
SELECT 'VAL-06' AS rule_id, record_id FROM 'data/outputs/tables/clean_uk.parquet' AS t WHERE latest_income < 0 OR latest_expenditure < 0;

-- VAL-07 [validity / error] USD amounts equal GBP amounts x reference rate (1.28), within 2%.
SELECT 'VAL-07' AS rule_id, record_id FROM 'data/outputs/tables/clean_uk.parquet' AS t WHERE (latest_income > 0 AND abs(income_usd / (latest_income * 1.28) - 1) > 0.02) OR (latest_expenditure > 0 AND abs(expenditure_usd / (latest_expenditure * 1.28) - 1) > 0.02);

-- VAL-08 [validity / error] Reported emissions are not negative.
SELECT 'VAL-08' AS rule_id, record_id FROM 'data/outputs/tables/clean_companies.parquet' AS t WHERE co2e_2023 < 0;

-- VAL-09 [validity / warning] EPA-reported emissions are positive for a plant that Climate TRACE models.
SELECT 'VAL-09' AS rule_id, record_id FROM 'data/outputs/tables/clean_power.parquet' AS t WHERE epa_co2e IS NULL OR epa_co2e <= 0;

-- CONS-01 [consistency / error] Program + management + fundraising = total functional expenses (tolerance $1 or 0.5%).
SELECT 'CONS-01' AS rule_id, record_id FROM 'data/outputs/tables/clean_us.parquet' AS t WHERE abs(exp_program + exp_management + exp_fundraising - exp_total_p9) > greatest(1, 0.005 * abs(exp_total_p9));

-- CONS-02 [consistency / error] Part IX total expenses = Part I total expenses (tolerance $1 or 0.5%).
SELECT 'CONS-02' AS rule_id, record_id FROM 'data/outputs/tables/clean_us.parquet' AS t WHERE abs(exp_total_p9 - expenses) > greatest(1, 0.005 * abs(expenses));

-- CONS-03 [consistency / error] Assets - liabilities = net assets (tolerance $1 or 1% of assets).
SELECT 'CONS-03' AS rule_id, record_id FROM 'data/outputs/tables/clean_us.parquet' AS t WHERE abs(assets - liabilities - net_assets) > greatest(1, 0.01 * abs(assets));

-- CONS-04 [consistency / warning] Revenue is within 0.2x to 5x of the prior year reported on the same return.
SELECT 'CONS-04' AS rule_id, record_id FROM 'data/outputs/tables/clean_us.parquet' AS t WHERE revenue > 0 AND revenue_py > 0 AND (revenue / revenue_py > 5 OR revenue / revenue_py < 0.2);

-- CONS-05 [consistency / warning] Expenses are within 0.1x to 10x of revenue.
SELECT 'CONS-05' AS rule_id, record_id FROM 'data/outputs/tables/clean_us.parquet' AS t WHERE revenue > 0 AND expenses > 0 AND (expenses / revenue > 10 OR expenses / revenue < 0.1);

-- CONS-06 [consistency / warning] Fundraising expenses in Part I (line 16b) = Part IX column D (tolerance $1 or 1%).
SELECT 'CONS-06' AS rule_id, record_id FROM 'data/outputs/tables/clean_us.parquet' AS t WHERE abs(fundraising_exp_p1 - exp_fundraising) > greatest(1, 0.01 * abs(exp_fundraising));

-- CONS-07 [consistency / warning] Expenditure is within 0.1x to 10x of income.
SELECT 'CONS-07' AS rule_id, record_id FROM 'data/outputs/tables/clean_uk.parquet' AS t WHERE latest_income > 0 AND latest_expenditure > 0 AND (latest_expenditure / latest_income > 10 OR latest_expenditure / latest_income < 0.1);

-- CONS-08 [consistency / warning] Emissions are within 0.33x to 3x of 2021.
SELECT 'CONS-08' AS rule_id, record_id FROM 'data/outputs/tables/clean_companies.parquet' AS t WHERE co2e_2021 > 0 AND (co2e_2023 / co2e_2021 > 3 OR co2e_2023 / co2e_2021 < 0.33);

-- CONS-09 [consistency / warning] Average emissions per facility are at least 25,000 tCO2e (the GHGRP reporting threshold for most sources).
SELECT 'CONS-09' AS rule_id, record_id FROM 'data/outputs/tables/clean_companies.parquet' AS t WHERE co2e_2023 / n_facilities < 25000;

-- UNIQ-01 [uniqueness / error] One return per EIN for the tax year.
SELECT 'UNIQ-01' AS rule_id, record_id FROM 'data/outputs/tables/clean_us.parquet' AS t WHERE ein IN (SELECT ein FROM 'data/outputs/tables/clean_us.parquet' GROUP BY ein HAVING count(*) > 1);

-- UNIQ-02 [uniqueness / info] The same normalised name is used by more than one EIN.
SELECT 'UNIQ-02' AS rule_id, record_id FROM 'data/outputs/tables/clean_us.parquet' AS t WHERE name_key IN (SELECT name_key FROM 'data/outputs/tables/clean_us.parquet' GROUP BY name_key HAVING count(DISTINCT ein) > 1);

-- UNIQ-03 [uniqueness / error] One row per registered charity number.
SELECT 'UNIQ-03' AS rule_id, record_id FROM 'data/outputs/tables/clean_uk.parquet' AS t WHERE registered_charity_number IN (SELECT registered_charity_number FROM 'data/outputs/tables/clean_uk.parquet' GROUP BY registered_charity_number HAVING count(*) > 1);

-- UNIQ-04 [uniqueness / warning] One SEC registrant is not matched to two different parent names.
SELECT 'UNIQ-04' AS rule_id, record_id FROM 'data/outputs/tables/clean_companies.parquet' AS t WHERE sec_cik IN (SELECT sec_cik FROM 'data/outputs/tables/clean_companies.parquet' WHERE sec_cik IS NOT NULL GROUP BY sec_cik HAVING count(*) > 1);

-- FRESH-01 [freshness / error] The return ends less than 3 years before the as-of date.
SELECT 'FRESH-01' AS rule_id, record_id FROM 'data/outputs/tables/clean_us.parquet' AS t WHERE years_since_period_end > 3;

-- FRESH-02 [freshness / info] The IRS master file already lists a more recent return than the one used.
SELECT 'FRESH-02' AS rule_id, record_id FROM 'data/outputs/tables/clean_us.parquet' AS t WHERE bmf_period_end > period_end + INTERVAL 31 DAY;

-- FRESH-03 [freshness / error] Latest accounts end less than 3 years before the as-of date.
SELECT 'FRESH-03' AS rule_id, record_id FROM 'data/outputs/tables/clean_uk.parquet' AS t WHERE years_since_period_end > 3;

-- FRESH-04 [freshness / warning] The charity is not overdue or in double default on its filings.
SELECT 'FRESH-04' AS rule_id, record_id FROM 'data/outputs/tables/clean_uk.parquet' AS t WHERE charity_reporting_status IN ('Submission Overdue', 'Submission Double Default');

-- ACC-01 [accuracy / error] E-file revenue = IRS SOI extract revenue for the same organisation (tolerance $1 or 1%).
SELECT 'ACC-01' AS rule_id, record_id FROM 'data/outputs/tables/clean_us.parquet' AS t WHERE soi_revenue IS NOT NULL AND abs(revenue - soi_revenue) > greatest(1, 0.01 * abs(soi_revenue));

-- ACC-02 [accuracy / error] E-file total assets = SOI extract total assets (tolerance $1 or 1%).
SELECT 'ACC-02' AS rule_id, record_id FROM 'data/outputs/tables/clean_us.parquet' AS t WHERE soi_assets IS NOT NULL AND abs(assets - soi_assets) > greatest(1, 0.01 * abs(soi_assets));

-- ACC-03 [accuracy / error] E-file total expenses = SOI extract total functional expenses (tolerance $1 or 1%).
SELECT 'ACC-03' AS rule_id, record_id FROM 'data/outputs/tables/clean_us.parquet' AS t WHERE soi_expenses IS NOT NULL AND abs(expenses - soi_expenses) > greatest(1, 0.01 * abs(soi_expenses));

-- ACC-04 [accuracy / warning] The e-file fiscal period matches the SOI extract fiscal period.
SELECT 'ACC-04' AS rule_id, record_id FROM 'data/outputs/tables/clean_us.parquet' AS t WHERE soi_tax_pd IS NOT NULL AND tax_pd <> soi_tax_pd;

-- ACC-05 [accuracy / warning] Register income = income in the latest annual return, same period.
SELECT 'ACC-05' AS rule_id, record_id FROM 'data/outputs/tables/clean_uk.parquet' AS t WHERE (total_gross_income IS NOT NULL AND abs(latest_income - total_gross_income) > 1) OR (fin_period_end_date IS NOT NULL AND latest_acc_fin_period_end_date <> fin_period_end_date);

-- ACC-06 [accuracy / warning] Climate TRACE estimate is within 0.5x to 1.5x of the EPA-reported emissions.
SELECT 'ACC-06' AS rule_id, record_id FROM 'data/outputs/tables/clean_power.parquet' AS t WHERE epa_co2e > 0 AND (ct_to_epa_ratio > 1.5 OR ct_to_epa_ratio < 0.5);

-- ACC-07 [accuracy / warning] EPA parent company and Climate TRACE owner share a name (similarity >= 50).
SELECT 'ACC-07' AS rule_id, record_id FROM 'data/outputs/tables/clean_power.parquet' AS t WHERE parent_owner_similarity < 50;

-- ACC-08 [accuracy / info] A company with an SBTi-validated target does not show emissions up more than 10% since 2021.
SELECT 'ACC-08' AS rule_id, record_id FROM 'data/outputs/tables/clean_companies.parquet' AS t WHERE sbti_near_term_status = 'Validated Targets' AND emissions_change > 0.10;
