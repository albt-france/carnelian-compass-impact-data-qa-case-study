"""Rerun the whole study in order. Downloads are cached, so a second run only recomputes.
Usage: python src/run_all.py            (add --skip-download to reuse data/raw as is)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
STEPS = ["download_data", "build_processed", "fetch_samples", "prepare", "inject_errors", "run_checks", "evaluate_detection",
         "reconcile", "robustness", "build_excel", "export_sql", "build_dashboard", "build_notebook", "build_pdf"]


def run(args):
    print(">", " ".join(args[1:]), flush=True)
    subprocess.run(args, check=True, cwd=ROOT)


def main():
    skip = "--skip-download" in sys.argv
    for s in STEPS:
        if skip and s in ("download_data", "fetch_samples"):
            continue
        if s == "build_dashboard":   # tests run before the outputs that quote the test count
            r = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=ROOT, capture_output=True, text=True)
            last = r.stdout.strip().splitlines()[-1]
            print("> pytest:", last, flush=True)
            if r.returncode != 0:
                raise SystemExit("tests failed: fix before publishing")
            (ROOT / "data" / "outputs" / "test_count.txt").write_text(last.split(" passed")[0].split()[-1])
        run([PY, f"src/{s}.py"])
    print("done")


if __name__ == "__main__":
    main()
