"""Edge cases: the score must neither crash nor invent a number. Each case sits in a synthetic population."""
import numpy as np
import pandas as pd
import pytest

from scoring.engine import score_nonprofits

N_POP = 60


def population():
    rng = np.random.default_rng(0)
    rows = []
    for i in range(N_POP):
        rev = float(rng.uniform(1e5, 4e5))
        exp = rev * rng.uniform(0.8, 1.1)
        rows.append(dict(record_id=f"P{i}", ein=f"{i:09d}", ntee_major="B", period_begin=pd.Timestamp("2023-01-01"),
                         period_end=pd.Timestamp("2023-12-31"), efiled_at="2024-05-01T10:00:00+00:00", audited=bool(i % 2),
                         currency="USD", revenue=rev, revenue_py=rev * rng.uniform(0.7, 1.3), expenses=exp, assets=rev,
                         liabilities=rev * rng.uniform(0, 0.6), net_assets=rev * 0.5, exp_total_p9=exp, exp_program=exp * 0.8,
                         exp_fundraising=exp * 0.05, contributions=rev * 0.5))
    return pd.DataFrame(rows)


def run(**changes):
    p = population()
    edge = p.iloc[[0]].copy().assign(record_id="EDGE", ein="999999999", **changes)
    s = score_nonprofits(pd.concat([p, edge], ignore_index=True))
    return s.set_index("record_id").loc["EDGE"], s.set_index("record_id")


def test_zero_revenue():
    r, _ = run(revenue=0.0)
    assert r.m_revenue_change == 1.0 and r.size_band_calc.startswith("S") and r.status == "scored"


def test_brand_new_org_without_prior_year():
    r, _ = run(revenue_py=np.nan)
    assert np.isnan(r.stability) and r.coverage == pytest.approx(0.8) and not np.isnan(r.score)


def test_zero_expenses():
    r, _ = run(expenses=0.0, exp_total_p9=0.0, exp_program=0.0, exp_fundraising=0.0)
    assert np.isnan(r.m_reserves_months) and np.isnan(r.m_program_share)
    assert r.m_fundraising_cost == 0.0


def test_partial_data_is_withheld_not_zero():
    r, _ = run(revenue=np.nan, revenue_py=np.nan, expenses=np.nan, assets=np.nan, liabilities=np.nan, net_assets=np.nan,
               exp_total_p9=np.nan, exp_program=np.nan, exp_fundraising=np.nan, contributions=np.nan)
    assert np.isnan(r.score) and r.status == "insufficient data"


def test_extreme_values_are_capped():
    r, _ = run(net_assets=1e12, liabilities=1e12)
    assert r.m_reserves_months == 60 and r.m_debt_ratio == 1.5


def test_currency_gbp_ratios_unchanged_size_band_converted():
    usd, _ = run(revenue=400_000.0)
    gbp, _ = run(revenue=400_000.0, currency="GBP")
    for k in ["m_debt_ratio", "m_program_share", "m_fundraising_cost", "m_reserves_months"]:
        assert usd[k] == gbp[k]
    assert usd.size_band_calc.startswith("S") and gbp.size_band_calc.startswith("M")   # 400k GBP = 512k USD


def test_18_month_period_is_annualised():
    base, _ = run()
    long, _ = run(period_begin=pd.Timestamp("2022-07-01"), expenses=float(population().expenses[0]) * 549 / 365)   # 1 Jul 2022 - 31 Dec 2023 = 549 days
    assert long.m_reserves_months == pytest.approx(base.m_reserves_months, abs=1e-6)


def test_negative_revenue_has_no_stability_metric():
    r, _ = run(revenue=-10.0)
    assert np.isnan(r.m_revenue_change)


def test_duplicate_returns_are_scored_once():
    p = population()
    dup = p.iloc[[0]].assign(record_id="P0-amended", efiled_at="2024-09-01T10:00:00+00:00")
    s = score_nonprofits(pd.concat([p, dup], ignore_index=True))
    assert len(s) == N_POP and "P0-amended" in set(s.record_id) and "P0" not in set(s.record_id)
