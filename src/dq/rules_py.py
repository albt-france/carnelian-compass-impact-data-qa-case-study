"""Python (pandas) implementation of every rule in rules.yaml, written independently of the SQL.
Each function takes the table and returns a boolean mask: True = the record FAILS the rule.
Comparisons with a missing value are False, like SQL NULL in a WHERE clause."""
from __future__ import annotations

import numpy as np
import pandas as pd

FX = 1.28


def _tol(ref, rel, floor=1.0):
    return np.maximum(floor, rel * ref.abs())


def _gap(a, b, rel, floor=1.0, ref=None):
    ref = b if ref is None else ref
    return (a - b).abs() > _tol(ref, rel, floor)


def _ratio_out(num, den, lo, hi):
    r = num / den
    return (r > hi) | (r < lo)


def _dup(s: pd.Series) -> pd.Series:
    return s.notna() & s.duplicated(keep=False)


RULES = {
    "COMP-01": lambda d: d.revenue.isna() | d.expenses.isna() | d.assets.isna(),
    "COMP-02": lambda d: (d.exp_total_p9 > 0) & (d.exp_program.isna() | d.exp_management.isna() | d.exp_fundraising.isna()),
    "COMP-03": lambda d: d.ntee_cd.isna(),
    "COMP-04": lambda d: d.latest_income.isna() | d.latest_expenditure.isna(),
    "COMP-05": lambda d: d.revenue_2023.isna(),
    "COMP-06": lambda d: d.co2e_2021.isna() | (d.co2e_2021 == 0),
    "VAL-01": lambda d: (d.expenses < 0) | (d.exp_total_p9 < 0),
    "VAL-02": lambda d: (d.assets < 0) | (d.liabilities < 0),
    "VAL-03": lambda d: d.revenue < 0,
    "VAL-04": lambda d: d.period_days_calc.notna() & ~d.period_days_calc.between(360, 371),
    "VAL-05": lambda d: d.period_begin.notna() & (d.period_begin.dt.year != 2023),
    "VAL-06": lambda d: (d.latest_income < 0) | (d.latest_expenditure < 0),
    "VAL-07": lambda d: ((d.latest_income > 0) & ((d.income_usd / (d.latest_income * FX) - 1).abs() > 0.02))
                        | ((d.latest_expenditure > 0) & ((d.expenditure_usd / (d.latest_expenditure * FX) - 1).abs() > 0.02)),
    "VAL-08": lambda d: d.co2e_2023 < 0,
    "VAL-09": lambda d: d.epa_co2e.isna() | (d.epa_co2e <= 0),
    "CONS-01": lambda d: _gap(d.exp_program + d.exp_management + d.exp_fundraising, d.exp_total_p9, 0.005),
    "CONS-02": lambda d: _gap(d.exp_total_p9, d.expenses, 0.005),
    "CONS-03": lambda d: _gap(d.assets - d.liabilities, d.net_assets, 0.01, ref=d.assets),
    "CONS-04": lambda d: (d.revenue > 0) & (d.revenue_py > 0) & _ratio_out(d.revenue, d.revenue_py, 0.2, 5),
    "CONS-05": lambda d: (d.revenue > 0) & (d.expenses > 0) & _ratio_out(d.expenses, d.revenue, 0.1, 10),
    "CONS-06": lambda d: _gap(d.fundraising_exp_p1, d.exp_fundraising, 0.01),
    "CONS-07": lambda d: (d.latest_income > 0) & (d.latest_expenditure > 0) & _ratio_out(d.latest_expenditure, d.latest_income, 0.1, 10),
    "CONS-08": lambda d: (d.co2e_2021 > 0) & _ratio_out(d.co2e_2023, d.co2e_2021, 0.33, 3),
    "CONS-09": lambda d: d.co2e_2023 / d.n_facilities < 25000,
    "UNIQ-01": lambda d: _dup(d.ein),
    "UNIQ-02": lambda d: d.name_key.isin(d.groupby("name_key").ein.nunique().loc[lambda s: s > 1].index),
    "UNIQ-03": lambda d: _dup(d.registered_charity_number),
    "UNIQ-04": lambda d: _dup(d.sec_cik),
    "FRESH-01": lambda d: d.years_since_period_end > 3,
    "FRESH-02": lambda d: d.bmf_period_end > d.period_end + pd.Timedelta(days=31),
    "FRESH-03": lambda d: d.years_since_period_end > 3,
    "FRESH-04": lambda d: d.charity_reporting_status.isin(["Submission Overdue", "Submission Double Default"]),
    "ACC-01": lambda d: d.soi_revenue.notna() & _gap(d.revenue, d.soi_revenue, 0.01),
    "ACC-02": lambda d: d.soi_assets.notna() & _gap(d.assets, d.soi_assets, 0.01),
    "ACC-03": lambda d: d.soi_expenses.notna() & _gap(d.expenses, d.soi_expenses, 0.01),
    "ACC-04": lambda d: d.soi_tax_pd.notna() & (d.tax_pd != d.soi_tax_pd),
    "ACC-05": lambda d: (d.total_gross_income.notna() & ((d.latest_income - d.total_gross_income).abs() > 1))
                        | (d.fin_period_end_date.notna() & d.latest_acc_fin_period_end_date.notna()
                           & (d.latest_acc_fin_period_end_date != d.fin_period_end_date)),
    "ACC-06": lambda d: (d.epa_co2e > 0) & _ratio_out(d.ct_co2e, d.epa_co2e, 0.5, 1.5),
    "ACC-07": lambda d: d.parent_owner_similarity < 50,
    "ACC-08": lambda d: (d.sbti_near_term_status == "Validated Targets") & (d.emissions_change > 0.10),
}
