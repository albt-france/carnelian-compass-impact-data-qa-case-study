"""Unit tests of each scoring function."""
import numpy as np
import pandas as pd
import pytest

from scoring.engine import aggregate, cap, company_metrics, midrank_pct, nonprofit_metrics, peer_key, points


def test_midrank_percentile_with_ties_and_groups():
    v = pd.Series([1, 2, 2, 3, 10, np.nan])
    g = pd.Series(["a", "a", "a", "a", "b", "a"])
    p = midrank_pct(v, g)
    assert p.iloc[:4].tolist() == [0.125, 0.5, 0.5, 0.875]
    assert p.iloc[4] == 0.5          # alone in its group
    assert np.isnan(p.iloc[5])       # missing stays missing, never 0


def test_peer_group_falls_back_when_small_or_unknown():
    primary = pd.Series(["B"] * 30 + ["E"] * 5 + [None])
    band = pd.Series(["S"] * 36)
    k = peer_key(primary, band, 30)
    assert k[0] == "B|S" and k[30] == "ALL|S" and k[35] == "ALL|S"


def test_caps_and_rounding(cfg):
    m = pd.DataFrame({"reserves_months": [500.0, -50.0, 3.1234567], "debt_ratio": [9.0, -1.0, 0.5]})
    c = cap(m, cfg["nonprofit"])
    assert c.reserves_months.tolist() == [60.0, -12.0, 3.123457]
    assert c.debt_ratio.tolist() == [1.5, 0.0, 0.5]


def test_points_direction(cfg):
    m = pd.DataFrame({k: [1.0, 2.0] for k in ["reserves_months", "debt_ratio", "program_share", "fundraising_cost", "revenue_change", "transparency"]})
    p = points(m, pd.Series(["g", "g"]), cfg["nonprofit"])
    assert p.reserves_months.tolist() == [25.0, 75.0]     # higher is better
    assert p.debt_ratio.tolist() == [75.0, 25.0]          # lower is better


def test_aggregate_reweights_missing_pillar_and_withholds_low_coverage(cfg):
    c = cfg["nonprofit"]
    pts = pd.DataFrame({"reserves_months": [80, 80, np.nan], "debt_ratio": [60, 60, np.nan], "program_share": [50, 50, np.nan],
                        "fundraising_cost": [np.nan, np.nan, np.nan], "revenue_change": [40, np.nan, np.nan], "transparency": [100, 100, 100]})
    r = aggregate(pts, c)
    # all pillars: (0.3*70 + 0.3*50 + 0.2*40 + 0.2*100) / 1.0
    assert r.score[0] == pytest.approx(64.0)
    # stability missing: weights re-scaled over 0.8, coverage 0.8
    assert r.coverage[1] == pytest.approx(0.8)
    assert r.score[1] == pytest.approx((0.3 * 70 + 0.3 * 50 + 0.2 * 100) / 0.8)
    # only transparency: coverage 0.2 < 0.6 -> no score (not zero)
    assert np.isnan(r.score[2]) and r.status[2] == "insufficient data"


def org(**kw):
    base = dict(period_begin=pd.Timestamp("2023-01-01"), period_end=pd.Timestamp("2023-12-31"), efiled_at="2024-05-01T10:00:00+00:00",
                audited=True, currency="USD", revenue=1200.0, revenue_py=1000.0, expenses=1200.0, assets=1000.0, liabilities=250.0,
                net_assets=750.0, exp_total_p9=1200.0, exp_program=960.0, exp_fundraising=60.0, contributions=600.0)
    base.update(kw)
    return pd.DataFrame([base])


def test_nonprofit_metrics_by_hand(cfg):
    m = nonprofit_metrics(org(), cfg["nonprofit"]).iloc[0]
    assert m.reserves_months == pytest.approx(750 / (1200 / 12))   # 7.5 months
    assert m.debt_ratio == pytest.approx(0.25)
    assert m.program_share == pytest.approx(0.8)
    assert m.fundraising_cost == pytest.approx(0.1)
    assert m.revenue_change == pytest.approx(0.2)
    assert m.transparency == pytest.approx(1.0)                    # audited and filed on time


def test_late_filing_lowers_transparency(cfg):
    m = nonprofit_metrics(org(efiled_at="2024-11-20T10:00:00+00:00", audited=False), cfg["nonprofit"]).iloc[0]
    assert m.transparency == 0.0


def test_company_metrics(cfg):
    c = pd.DataFrame([dict(co2e_2023=2e6, co2e_2021=1e6, revenue_2023=1e9, sbti_near_term_status="Validated Targets",
                           ownership_complete=1.0, facilities_in_2021=3, n_facilities=3),
                      dict(co2e_2023=1e6, co2e_2021=np.nan, revenue_2023=np.nan, sbti_near_term_status=None,
                           ownership_complete=0.5, facilities_in_2021=1, n_facilities=2)])
    m = company_metrics(c, cfg["company"])
    assert m.intensity_t_per_musd[0] == pytest.approx(2000)
    assert m.emissions_change[0] == pytest.approx(1.0)
    assert m.sbti_points.tolist() == [100, 0]
    assert m.disclosure_points.tolist() == [100, 0]
    assert np.isnan(m.intensity_t_per_musd[1]) and np.isnan(m.emissions_change[1])
