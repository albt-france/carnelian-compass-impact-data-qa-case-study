-- Source reconciliation in DuckDB SQL (same logic as src/reconcile.py). Run from the repository root:
--   duckdb -c ".read sql/reconciliation.sql"

-- 1. IRS e-file vs IRS SOI extract: latest return per EIN, same fiscal period, tolerance 1%
WITH latest AS (
  SELECT * FROM 'data/outputs/tables/clean_us.parquet'
  QUALIFY row_number() OVER (PARTITION BY ein ORDER BY efiled_at DESC, record_id DESC) = 1
)
SELECT 'e-file vs SOI' AS pair,
       count(*) FILTER (WHERE soi_tax_pd = tax_pd)                                         AS compared,
       avg(CASE WHEN abs(revenue - soi_revenue) <= 0.01 * greatest(abs(soi_revenue), 1) THEN 1 ELSE 0 END)
           FILTER (WHERE soi_tax_pd = tax_pd)                                              AS revenue_agree_rate,
       count(*) FILTER (WHERE soi_tax_pd = tax_pd AND abs(revenue - soi_revenue) > 0.01 * greatest(abs(soi_revenue), 1) AND amended) AS gaps_on_amended_returns
FROM latest;

-- 2. EPA GHGRP vs Climate TRACE (power plants, 2023): agreement bands
SELECT 'EPA vs Climate TRACE' AS pair, count(*) AS plants,
       avg(CASE WHEN abs(ct_to_epa_ratio - 1) <= 0.10 THEN 1 ELSE 0 END) AS within_10pct,
       avg(CASE WHEN abs(ct_to_epa_ratio - 1) <= 0.25 THEN 1 ELSE 0 END) AS within_25pct,
       avg(CASE WHEN abs(ct_to_epa_ratio - 1) <= 0.50 THEN 1 ELSE 0 END) AS within_50pct,
       median(ct_to_epa_ratio) AS median_ratio
FROM 'data/outputs/tables/clean_power.parquet' WHERE epa_co2e > 0;

-- 3. Model vs report gap by Climate TRACE asset type
SELECT ct_type, count(*) AS plants, round(median(ct_to_epa_ratio), 3) AS median_ratio,
       round(avg(CASE WHEN abs(ct_to_epa_ratio - 1) <= 0.25 THEN 1 ELSE 0 END), 3) AS within_25pct
FROM 'data/outputs/tables/clean_power.parquet' WHERE epa_co2e > 0
GROUP BY ct_type HAVING count(*) >= 20 ORDER BY plants DESC;

-- 4. SBTi status of the 300 largest GHGRP parent companies
SELECT coalesce(sbti_near_term_status, 'not in SBTi') AS sbti_status, count(*) AS companies,
       round(median(emissions_change), 3) AS median_emissions_change_2021_2023
FROM 'data/outputs/tables/clean_companies.parquet' GROUP BY 1 ORDER BY companies DESC;
