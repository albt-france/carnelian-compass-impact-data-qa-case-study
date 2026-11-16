"""Unit tests: every rule flags a known-bad record, leaves a known-good one alone, and the Python and SQL engines
agree (on these synthetic cases and on the full real and injected tables)."""
import pandas as pd
import pytest

from dq.engine import load_rules, run_python, run_sql

T = pd.Timestamp
GOOD = {
    "us": dict(record_id="good", ein="000000001", name_key="ALPHA", revenue=1000.0, revenue_py=900.0, expenses=950.0, assets=2000.0,
               liabilities=500.0, net_assets=1500.0, exp_total_p9=950.0, exp_program=800.0, exp_management=100.0,
               exp_fundraising=50.0, fundraising_exp_p1=50.0, ntee_cd="B20", period_begin=T("2023-01-01"),
               period_end=T("2023-12-31"), period_days_calc=365.0, years_since_period_end=2.9, bmf_period_end=T("2023-12-31"),
               soi_revenue=1000.0, soi_assets=2000.0, soi_expenses=950.0, tax_pd="202312", soi_tax_pd="202312"),
    "uk": dict(record_id="good", registered_charity_number="1", latest_income=1000.0, latest_expenditure=900.0, income_usd=1280.0,
               expenditure_usd=1152.0, total_gross_income=1000.0, fin_period_end_date=T("2025-03-31"),
               latest_acc_fin_period_end_date=T("2025-03-31"), years_since_period_end=1.6, charity_reporting_status="Submission Received"),
    "companies": dict(record_id="good", co2e_2023=1e6, co2e_2021=1e6, n_facilities=5, revenue_2023=1e9, sec_cik=1.0,
                      sbti_near_term_status=None, emissions_change=0.0),
    "power": dict(record_id="good", epa_co2e=1e6, ct_co2e=1e6, ct_to_epa_ratio=1.0, parent_owner_similarity=80.0),
}
BAD = {  # rule -> changes that must make the record fail it
    "COMP-01": dict(revenue=None), "COMP-02": dict(exp_program=None), "COMP-03": dict(ntee_cd=None),
    "COMP-04": dict(latest_income=None), "COMP-05": dict(revenue_2023=None), "COMP-06": dict(co2e_2021=None),
    "VAL-01": dict(expenses=-950.0), "VAL-02": dict(assets=-1.0), "VAL-03": dict(revenue=-5.0), "VAL-04": dict(period_days_calc=548.0),
    "VAL-05": dict(period_begin=T("2024-01-01")), "VAL-06": dict(latest_expenditure=-1.0), "VAL-07": dict(income_usd=1000.0),
    "VAL-08": dict(co2e_2023=-1.0), "VAL-09": dict(epa_co2e=0.0),
    "CONS-01": dict(exp_program=900.0), "CONS-02": dict(exp_total_p9=1200.0), "CONS-03": dict(net_assets=100.0),
    "CONS-04": dict(revenue=10000.0), "CONS-05": dict(expenses=20000.0), "CONS-06": dict(fundraising_exp_p1=80.0),
    "CONS-07": dict(latest_expenditure=20000.0, expenditure_usd=25600.0), "CONS-08": dict(co2e_2023=4e6),
    "CONS-09": dict(co2e_2023=1e5),
    "UNIQ-01": dict(ein="000000001"), "UNIQ-02": dict(ein="000000002", name_key="ALPHA"), "UNIQ-03": dict(registered_charity_number="1"),
    "UNIQ-04": dict(sec_cik=1.0),
    "FRESH-01": dict(years_since_period_end=3.5), "FRESH-02": dict(bmf_period_end=T("2025-12-31")),
    "FRESH-03": dict(years_since_period_end=3.5), "FRESH-04": dict(charity_reporting_status="Submission Overdue"),
    "ACC-01": dict(soi_revenue=2000.0), "ACC-02": dict(soi_assets=3000.0), "ACC-03": dict(soi_expenses=2000.0),
    "ACC-04": dict(soi_tax_pd="202212"), "ACC-05": dict(total_gross_income=1200.0), "ACC-06": dict(ct_co2e=2e6, ct_to_epa_ratio=2.0),
    "ACC-07": dict(parent_owner_similarity=20.0), "ACC-08": dict(sbti_near_term_status="Validated Targets", emissions_change=0.2),
}
# records that do not collide unless the rule is about collisions
DISTINCT = {"us": dict(ein="000000009", name_key="BETA"), "uk": dict(registered_charity_number="9"), "companies": dict(sec_cik=9.0)}
RULES = load_rules()


def case(rule_id):
    r = RULES.set_index("id").loc[rule_id]
    good = dict(GOOD[r.table])
    bad = {**good, **DISTINCT.get(r.table, {}), **BAD[rule_id], "record_id": "bad"}
    return r.table, pd.DataFrame([good, bad]), RULES[RULES.id == rule_id]


def test_catalogue_size_and_fields():
    assert 30 <= len(RULES) <= 40
    assert RULES.id.is_unique
    assert set(RULES.dimension) == {"completeness", "validity", "consistency", "uniqueness", "freshness", "accuracy"}
    assert set(RULES.severity) <= {"error", "warning", "info"}
    assert set(BAD) == set(RULES.id), "every rule needs a unit test case"


@pytest.mark.parametrize("rule_id", sorted(BAD))
@pytest.mark.parametrize("engine", [run_python, run_sql], ids=["python", "sql"])
def test_rule_flags_bad_not_good(rule_id, engine):
    table, df, rule = case(rule_id)
    flagged = set(engine({table: df}, rule).record_id)
    expected = {"good", "bad"} if rule_id.startswith("UNIQ") else {"bad"}
    assert flagged == expected


def test_good_records_pass_every_rule():
    for table, rec in GOOD.items():
        df = pd.DataFrame([rec])
        rules = RULES[(RULES.table == table)]
        assert run_python({table: df}, rules).empty
        assert run_sql({table: df}, rules).empty


@pytest.mark.parametrize("which", ["clean", "injected"])
def test_engines_agree_on_full_tables(which, clean, injected):
    t = clean if which == "clean" else injected
    a, b = run_python(t), run_sql(t)
    key = lambda d: set(zip(d.rule_id, d.record_id))  # noqa: E731
    assert key(a) == key(b)


def test_summary_and_health_scores():
    from dq.engine import health, summary
    table, df, rule = case("VAL-02")
    flags = run_python({table: df}, rule)
    s = summary(flags, {table: df}, rule)
    assert s.records_flagged.iloc[0] == 1 and s.pass_rate.iloc[0] == 0.5
    h = health(flags, {table: df}, rule)
    assert h.score.iloc[0] == 0.5 and h.dimension.iloc[0] == "validity"
