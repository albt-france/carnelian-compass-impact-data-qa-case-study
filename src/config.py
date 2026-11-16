"""Shared paths and constants."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"              # large downloads, never published (see .gitignore)
PROCESSED = ROOT / "data" / "processed"  # filtered extracts used by the analysis (published)
OUT = ROOT / "data" / "outputs"          # results of checks, scores, tests (published)
DOCS = ROOT / "docs"
QA = ROOT / "qa"
DASH = ROOT / "dashboard"
SEED = 42

# Neutral client name: no personal contact in any request.
USER_AGENT = "impact-data-qa-study/1.0 (research script)"

FOOTER = "Independent case study based on public data · not affiliated with or endorsed by Carnelian Ventures"


def ai_note() -> str:
    """The AI-use statement is written once, in the README (Methods); the PDF quotes it from there."""
    for line in (ROOT / "README.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("- **AI-assisted workflow**"):
            return line.split("**: ", 1)[1].strip()
    raise ValueError("AI note not found in README.md")
SEEN_ON = "16 November 2026"

for _p in (RAW, PROCESSED, OUT):
    _p.mkdir(parents=True, exist_ok=True)
