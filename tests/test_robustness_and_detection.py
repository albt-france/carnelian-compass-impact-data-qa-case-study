"""Robustness of the ranking and performance of the checks (SIMULATED errors)."""
import json

import numpy as np
import pandas as pd
from scipy.stats import kendalltau

from robustness import blocked_ids, monte_carlo
from scoring.engine import score_companies, score_nonprofits


def test_rank_stability_under_random_weights(clean, cfg):
    base = score_nonprofits(clean["us"])
    mc = monte_carlo(base, cfg["nonprofit"], np.random.default_rng(1)).head(100)
    assert mc.tau.median() > 0.7          # rankings broadly stable when weights move
    assert mc.top_decile_overlap.median() > 0.6


def test_gate_stops_injected_errors_from_moving_ranks(clean, injected):
    for fn, t in ((score_nonprofits, "us"), (score_companies, "companies")):
        a = fn(clean[t]).set_index("record_id")
        b = fn(injected[t], blocked=blocked_ids("flags_injected.csv")).set_index("record_id")
        both = a.index.intersection(b.index)
        moved = ((a.loc[both].rank_pct - b.loc[both].rank_pct).abs() * 100 > 10) & b.loc[both].score.notna()
        truth = set(pd.read_csv("data/_hidden_truth.csv").record_id)
        assert not (moved & both.isin(truth)).any(), f"{t}: an injected error moved a published rank by >10 pts"


def test_detection_targets(outputs):
    bt = pd.read_csv(outputs / "detection_by_type.csv")
    assert bt.injected.sum() == 300 and (bt.injected == 30).all()
    assert bt.detected.sum() / bt.injected.sum() >= 0.9
    assert (bt.recall >= 0.5).all()
    assert (bt.precision.dropna() >= 0.95).all()


def test_reconciliation_and_manual_check(outputs):
    r = pd.read_csv(outputs / "reconciliation_summary.csv")
    m = r[r.source_pair.str.startswith("Dataset vs original")]
    assert (m.agree_rate == 1).all()
    soi = r[(r.source_pair == "IRS e-file vs IRS SOI extract") & (r.measure == "revenue")].agree_rate.iloc[0]
    assert soi > 0.98


def test_robustness_summary_written(outputs):
    s = json.loads((outputs / "robustness_summary.json").read_text())
    assert s["nonprofit"]["injected_moved_over_10pts_not_blocked"] == 0
    assert s["company"]["gate_v1_moved_over_10pts_not_blocked"] > 0   # the audit finding that led to gate v2
    assert kendalltau([1, 2, 3], [1, 2, 3]).statistic == 1
