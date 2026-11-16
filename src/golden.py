"""Golden set: recalculate the QA workbook with LibreOffice (headless) and store the hand-computed (Excel formula)
values of the 20 golden organisations in tests/golden/golden_expected.csv. tests/test_golden.py then checks that
the Python scoring engine reproduces them exactly. Re-run only when the method changes on purpose.

Usage: python src/golden.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import OUT, QA, ROOT  # noqa: E402

EXPECTED = ROOT / "tests" / "golden" / "golden_expected.csv"


def soffice() -> str:
    for p in (r"C:\Program Files\LibreOffice\program\soffice.exe", r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"):
        if Path(p).exists():
            return p
    return shutil.which("soffice") or "soffice"


def recalc(src: Path, out_dir: Path) -> Path:
    prof = out_dir / "lo-profile"
    subprocess.run([soffice(), f"-env:UserInstallation={prof.as_uri()}", "--headless", "--calc", "--convert-to", "xlsx",
                    "--outdir", str(out_dir), str(src)], check=True, capture_output=True, timeout=600)
    return out_dir / src.name


def main():
    first, last = map(int, (OUT / "golden_layout.txt").read_text().split(","))
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        src = tmp / "in" / "QA_workbook.xlsx"
        src.parent.mkdir()
        shutil.copy(QA / "QA_workbook.xlsx", src)
        res = recalc(src, tmp)
        ws = load_workbook(res, data_only=True)["Golden_set"]
        header = [c.value for c in ws[first - 1]]
        rows = [[c.value for c in ws[r]][: len(header)] for r in range(first, last + 1)]
    df = pd.DataFrame(rows, columns=header).drop(columns=["Population row"])
    df = df.replace("", float("nan"))
    EXPECTED.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(EXPECTED, index=False)
    print("golden expected values:", EXPECTED, df.shape, "| mean score", round(pd.to_numeric(df.score).mean(), 2))


if __name__ == "__main__":
    main()
