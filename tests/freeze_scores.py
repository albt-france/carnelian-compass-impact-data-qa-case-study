"""Freeze the regression sample (run only after an intended method change)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from prepare import load_clean  # noqa: E402
from scoring.engine import score_companies, score_nonprofits  # noqa: E402

if __name__ == "__main__":
    t = load_clean()
    out = Path(__file__).parent / "regression"
    out.mkdir(exist_ok=True)
    np_ = score_nonprofits(t["us"]).sample(100, random_state=7)
    co = score_companies(t["companies"]).sample(50, random_state=7)
    for name, df in (("nonprofit", np_), ("company", co)):
        df[["record_id", "score", "coverage", "status"]].to_csv(out / f"frozen_{name}.csv", index=False)
    print("frozen", len(np_), "organisations and", len(co), "companies")
