"""Non-regression: scores of a frozen sample (100 organisations, 50 companies). Any unexpected change fails.
After an intended method change, re-freeze with: python tests/freeze_scores.py (and explain why in the commit)."""
from pathlib import Path

import pandas as pd
import pytest

from scoring.engine import score_companies, score_nonprofits

FROZEN = Path(__file__).parent / "regression"


@pytest.mark.parametrize("kind", ["nonprofit", "company"])
def test_scores_unchanged(kind, clean):
    frozen = pd.read_csv(FROZEN / f"frozen_{kind}.csv").set_index("record_id")
    now = (score_nonprofits(clean["us"]) if kind == "nonprofit" else score_companies(clean["companies"])).set_index("record_id")
    now = now.loc[frozen.index]
    for col in ["score", "coverage"]:
        a, b = now[col], frozen[col]
        assert ((a - b).abs() <= 1e-9).where(a.notna() & b.notna(), a.isna() & b.isna()).all(), f"{kind} {col} changed"
    assert (now.status == frozen.status).all()
