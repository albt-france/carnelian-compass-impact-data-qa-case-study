import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture(scope="session")
def clean():
    from prepare import load_clean
    return load_clean()


@pytest.fixture(scope="session")
def injected():
    from run_checks import load_injected
    return load_injected()


@pytest.fixture(scope="session")
def cfg():
    from scoring.engine import load_config
    return load_config()


@pytest.fixture(scope="session")
def outputs():
    return ROOT / "data" / "outputs"


def frame(records: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(records)
