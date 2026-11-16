"""Data contracts on the published extracts: sizes, labels, and no person-level fields."""
import json
from pathlib import Path

import pandas as pd

P = Path(__file__).resolve().parents[1] / "data" / "processed"
FORBIDDEN = ["ico", "careofname", "care_of", "officer", "trustee", "contact", "email", "phone", "street", "address", "preparer"]


def test_no_person_level_columns():
    for f in P.glob("*.parquet"):
        cols = [c.lower() for c in pd.read_parquet(f).columns]
        assert not [c for c in cols for w in FORBIDDEN if w in c], f.name


def test_sample_sizes():
    us = pd.read_parquet(P / "us_returns_2023.parquet")
    assert us.ein.nunique() == 2000
    assert us.drop_duplicates("ein").size_band.value_counts().eq(500).all()
    assert len(pd.read_parquet(P / "uk_charities.parquet")) == 500
    assert len(pd.read_parquet(P / "companies.parquet")) == 300


def test_match_review_applied():
    c = pd.read_parquet(P / "companies.parquet")
    assert not c.sec_match_status.eq("pending review").any()
    assert c.loc[c.sec_match_status == "rejected after review", "sec_cik"].isna().all()


def test_sbti_profile_exists():
    assert json.loads((P / "sbti_profile.json").read_text())["rows"] > 1000
