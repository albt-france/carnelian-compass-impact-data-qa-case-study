"""Golden set: 20 real organisations scored by hand in Excel (qa/QA_workbook.xlsx, sheet Golden_set, recalculated
by LibreOffice -> tests/golden/golden_expected.csv). The Python engine must reproduce every intermediate value."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scoring.engine import score_nonprofits

EXPECTED = pd.read_csv(Path(__file__).parent / "golden" / "golden_expected.csv").set_index("record_id")
METRICS = ["reserves_months", "debt_ratio", "program_share", "fundraising_cost", "revenue_change", "transparency"]
PILLARS = ["financial_health", "efficiency", "stability", "transparency"]


@pytest.fixture(scope="module")
def scored(clean):
    return score_nonprofits(clean["us"]).set_index("record_id").loc[EXPECTED.index]


def same(a, b):
    a, b = pd.to_numeric(a), pd.to_numeric(b)
    return bool(((a - b).abs() <= 1e-9).where(a.notna() & b.notna(), a.isna() & b.isna()).all())


def test_golden_set_has_20_records():
    assert len(EXPECTED) == 20


def test_peer_groups(scored):
    assert (scored.peer_group == EXPECTED.peer_group).all()


@pytest.mark.parametrize("m", METRICS)
def test_metric_values(scored, m):
    assert same(scored[f"m_{m}"], EXPECTED[f"{m} (metric)"])


@pytest.mark.parametrize("m", METRICS)
def test_points(scored, m):
    assert same(scored[f"p_{m}"], EXPECTED[f"{m} (points)"])


def test_pillars_coverage_score(scored):
    for p in PILLARS:
        assert same(scored[p], EXPECTED[p])
    assert same(scored.coverage, EXPECTED.coverage)
    assert same(scored.score, EXPECTED.score)


def test_golden_covers_the_hard_cases():
    assert EXPECTED["fundraising_cost (metric)"].isna().any()       # no contributions
    assert EXPECTED["revenue_change (metric)"].isna().any()         # new organisation
    assert EXPECTED.peer_group.str.startswith("ALL").any()           # peer fallback
    assert (EXPECTED["reserves_months (metric)"] == 60).any()        # cap reached
    assert not np.isnan(EXPECTED.score.astype(float)).all()
