# Demo scoring methodology

**Illustrative, not Carnelian's methodology.** Compass's scoring method is not public. This demo score exists to show how a
score with adjustable metrics and weights can be documented, normalised and tested. It is not a ranking to use for giving or
investing, and no organisation is named in the report.

Configuration: [`src/scoring/config.yaml`](../src/scoring/config.yaml) · code: [`src/scoring/engine.py`](../src/scoring/engine.py)

## Nonprofits (US Form 990, tax year 2023)

| Pillar (weight) | Metric | Definition | Better | Cap |
|---|---|---|---|---|
| Financial health (30%) | Reserves (months) | net assets / (annualised total expenses / 12) | higher | -12 to 60 |
| | Debt ratio | total liabilities / total assets | lower | 0 to 1.5 |
| Efficiency (30%) | Program share | program service expenses / total functional expenses (Part IX) | higher | 0 to 1 |
| | Fundraising cost | fundraising expenses / contributions (cost to raise $1) | lower | 0 to 2 |
| Stability (20%) | Revenue change | abs(revenue / prior-year revenue - 1), from the same return | lower | 0 to 2 |
| Transparency (20%) | Transparency | mean of: separate audited statements (IRS SOI extract) and filed within 10.5 months of year end | higher | 0 to 1 |

Steps:
1. **Uniqueness fix**: keep the latest e-filed return per EIN (original + amended returns exist for 31 organisations).
2. **Metrics**: flows are annualised when the period is not 360-371 days (18-month or short first years). A metric is missing
   (never zero) when its denominator is missing or not positive.
3. **Caps**, then rounding to 6 decimals (so ties are exact, the same rule as in the Excel golden set).
4. **Normalisation**: mid-rank percentile within the peer group NTEE major group x size band; groups smaller than 30 fall
   back to the size band alone; organisations without an NTEE code use the size band. Points = 100 x percentile (or
   100 x (1 - percentile) when lower is better).
5. **Pillar** = mean of its available metric points.
6. **Score** = weighted mean of the available pillars, re-weighted; **coverage** = share of the weight with data; no score
   below 60% coverage ("insufficient data").
7. **Data-quality gate**: records with an error flag (or a `holds_score` warning) get no published score.

## Companies (300 largest GHGRP parent companies, 2023)

| Pillar (weight) | Metric | Definition | Better |
|---|---|---|---|
| Carbon intensity (35%) | tCO2e per $m revenue | ownership-weighted direct US emissions / SEC revenue | lower (percentile within sector, n ≥ 10) |
| Emissions trend (25%) | change 2021 → 2023 | ownership-weighted, same facilities' parent | lower |
| Climate target (20%) | SBTi near-term status | validated / targets set = 100, commitment = 50, else 0 | fixed scale |
| Disclosure (20%) | share of 4 checks | revenue public; 2021 emissions present; ownership shares sum to 100%; all facilities reported in 2021 | fixed scale |

## Limits, said plainly

- **A financial ratio is not an impact measure.** It shows solvency, stability and transparency, not outcomes. Outcome
  measurement (GIIN IRIS+ metrics, the five dimensions of impact of the Impact Management Project: what, who, how much,
  contribution, risk) would sit on top of these ratios.
- **A low overhead share is not always good.** Under-investing in staff, systems and evaluation can weaken programs. The
  program share is capped, ranked within peers and weighted at 15% of the total so it cannot dominate.
- **Emissions do not tell the whole story** of a company's impact: direct US emissions only (no products, supply chain,
  Scope 3, or social impact).
- **Percentiles are relative** to this sample and its peer groups.
- **Transparency metric**: large organisations audited inside consolidated statements do not tick "separate audited
  statements" (only 36% of the largest do). A v2 should read the consolidated-audit box too; logged as a method fix.

## Robustness (src/robustness.py)

- 1,000 random weightings (Dirichlet around the base weights): median Kendall tau 0.79 (nonprofits), 0.89 (companies).
- One weight at a time x0.5 / x1.5: tau 0.79-0.96; raising the carbon-intensity weight by 50% drops 183 companies below the
  coverage threshold (their score disappears), a side effect to review before any weighting change.
- Effect of the SIMULATED errors on ranks, with and without the gate (see the PDF, page 6).
