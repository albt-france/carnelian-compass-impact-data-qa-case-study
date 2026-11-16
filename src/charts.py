"""Report charts (matplotlib -> inline SVG). House style: light card background,
blue = the data, grey = the comparison, red = errors, dashed lines = thresholds, Segoe UI, one y-axis only."""
from __future__ import annotations

import io
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

BLUE, BLUE_L, BLUE_D = "#2A78D6", "#86B6EF", "#1C5CAB"
GRAY, GRAY_D, RED = "#C9C7BF", "#898781", "#D03B3B"
INK, INK2, GRID, CARD = "#0B0B0B", "#52514E", "#E1E0D9", "#FCFCFB"

plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 9.5, "text.color": INK2,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "axes.facecolor": CARD, "figure.facecolor": CARD,
    "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
    "axes.grid": True, "axes.grid.axis": "x", "grid.color": GRID, "grid.linewidth": 0.8,
    "xtick.color": GRAY_D, "ytick.color": INK2, "xtick.labelsize": 9, "ytick.labelsize": 9,
    "xtick.major.size": 0, "ytick.major.size": 0, "legend.frameon": False, "legend.fontsize": 9,
    "svg.fonttype": "none", "axes.axisbelow": True,
})


def fig(w_px, h_px):
    return plt.subplots(figsize=(w_px / 96, h_px / 96), dpi=96)


def svg(f) -> str:
    buf = io.StringIO()
    f.savefig(buf, format="svg", bbox_inches="tight", pad_inches=0.05)
    plt.close(f)
    s = buf.getvalue()
    s = s[s.find("<svg"):]
    s = re.sub(r'width="[\d.]+pt" height="[\d.]+pt"', 'width="100%" height="100%" preserveAspectRatio="xMidYMid meet"', s, 1)
    return re.sub(r"<metadata>.*?</metadata>", "", s, flags=re.S)


# ---------------------------------------------------------------- Carnelian case study charts
def health_heatmap(h: pd.DataFrame, w=620, h_px=250):
    dims = ["completeness", "validity", "consistency", "uniqueness", "freshness", "accuracy"]
    names = {"us": "US nonprofits (IRS)", "uk": "UK charities (CCEW)", "companies": "Companies (EPA/SEC/SBTi)", "power": "Power plants (EPA/CT)"}
    p = h.pivot_table(index="table", columns="dimension", values="score").reindex(columns=dims).reindex(list(names))
    f, ax = fig(w, h_px)
    ax.grid(False)
    for i, t in enumerate(p.index):
        for j, d in enumerate(dims):
            v = p.loc[t, d]
            if np.isnan(v):
                ax.add_patch(plt.Rectangle((j, i), 0.96, 0.92, color="#F1F0EB"))
                ax.text(j + 0.48, i + 0.46, "n/a", ha="center", va="center", fontsize=8.5, color=GRAY_D)
                continue
            col = BLUE_D if v >= 0.97 else (BLUE_L if v >= 0.9 else RED)
            ax.add_patch(plt.Rectangle((j, i), 0.96, 0.92, color=col, alpha=0.9 if v < 0.9 else 1))
            ax.text(j + 0.48, i + 0.46, f"{v:.1%}", ha="center", va="center", fontsize=9.5, color="white" if col != BLUE_L else INK, fontweight="bold")
    ax.set_xlim(0, len(dims)); ax.set_ylim(len(p), 0)
    ax.set_xticks(np.arange(len(dims)) + 0.48, [d.capitalize() for d in dims])
    ax.set_yticks(np.arange(len(p)) + 0.46, [names[t] for t in p.index])
    ax.xaxis.tick_top()
    return svg(f)


def hbar(labels, values, w=560, h=260, fmt="{:,.0f}", color=None, highlight=None, xlabel=""):
    f, ax = fig(w, h)
    y = np.arange(len(labels))[::-1]
    cols = [RED if (highlight and highlight(l, v)) else (color or BLUE) for l, v in zip(labels, values)]
    ax.barh(y, values, color=cols, height=0.62)
    mx = max(values) if len(values) else 1
    for yi, v in zip(y, values):
        ax.text(v + mx * 0.012, yi, fmt.format(v), va="center", fontsize=8.5, color=INK2)
    ax.set_yticks(y, labels)
    ax.set_xlim(0, mx * 1.18)
    ax.set_xlabel(xlabel)
    return svg(f)


def scatter_epa_ct(d: pd.DataFrame, w=560, h=330):
    d = d[(d.epa_co2e > 1000) & (d.ct_co2e > 1000)]
    f, ax = fig(w, h)
    ax.grid(True, axis="both")
    ok = (d.ct_to_epa_ratio - 1).abs() <= 0.25
    ax.scatter(d.epa_co2e[ok] / 1e6, d.ct_co2e[ok] / 1e6, s=9, color=BLUE, alpha=0.55, label="within ±25%", lw=0)
    ax.scatter(d.epa_co2e[~ok] / 1e6, d.ct_co2e[~ok] / 1e6, s=9, color=RED, alpha=0.55, label="gap above 25%", lw=0)
    ax.set_xscale("log"); ax.set_yscale("log")
    lims = [0.001, 30]
    ax.plot(lims, lims, color=INK2, lw=1)
    ax.plot(lims, [x * 1.25 for x in lims], color=GRAY_D, lw=0.8, ls="--")
    ax.plot(lims, [x * 0.75 for x in lims], color=GRAY_D, lw=0.8, ls="--")
    ax.set_xlim(lims); ax.set_ylim(lims)
    ax.set_xlabel("EPA GHGRP reported, MtCO2e (2023)"); ax.set_ylabel("Climate TRACE estimate, MtCO2e")
    ax.legend(loc="upper left")
    return svg(f)


def agreement_bars(rows, w=560, h=300):
    """rows: list of (label, rate, n)"""
    f, ax = fig(w, h)
    y = np.arange(len(rows))[::-1]
    rates = [r[1] for r in rows]
    ax.barh(y, rates, color=[BLUE if r >= 0.95 else (BLUE_L if r >= 0.7 else RED) for r in rates], height=0.6)
    for yi, (lab, r, n) in zip(y, rows):
        ax.text(r + 0.01, yi, f"{r:.1%}  (n={n:,})", va="center", fontsize=8.5, color=INK2)
    ax.set_yticks(y, [r[0] for r in rows])
    ax.set_xlim(0, 1.25)
    ax.axvline(0.95, color=GRAY_D, ls="--", lw=0.8)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    return svg(f)


def detection_bars(d: pd.DataFrame, w=640, h=330, legend=True):
    d = d.sort_values("recall", ascending=True)
    y = np.arange(len(d))
    f, ax = fig(w, h)
    ax.barh(y + 0.2, d.injected, 0.38, color=GRAY, label="Injected (hidden key)")
    ax.barh(y - 0.2, d.detected, 0.38, color=[RED if r < 0.9 else BLUE for r in d.recall], label="Detected by the rules")
    for yi, (dt, inj, r) in enumerate(zip(d.detected, d.injected, d.recall)):
        ax.text(inj + 0.6, yi, f"{dt}/{inj}  ({r:.0%})", va="center", fontsize=8.5, color=INK2)
    ax.set_yticks(y, d.label)
    ax.set_xlim(0, 44)
    ax.set_xlabel("Errors (grey: injected, blue/red: detected)" if not legend else "Errors")
    if legend:
        ax.legend(loc="lower right")
    return svg(f)


def hist(values, w=520, h=260, bins=30, xlabel="", ref=None, color=None):
    f, ax = fig(w, h)
    ax.hist(values, bins=bins, color=color or BLUE, edgecolor=CARD, lw=0.5)
    if ref is not None:
        ax.axvline(ref, color=RED, ls="--", lw=1)
    ax.set_xlabel(xlabel)
    ax.grid(axis="y"); ax.grid(axis="x", visible=False)
    return svg(f)


def box_by_group(df, group, value, order, w=520, h=260, ylabel=""):
    f, ax = fig(w, h)
    data = [df.loc[df[group] == g, value].dropna() for g in order]
    bp = ax.boxplot(data, widths=0.5, patch_artist=True, showfliers=False)
    for b in bp["boxes"]:
        b.set(facecolor=BLUE_L, edgecolor=BLUE_D)
    for m in bp["medians"]:
        m.set(color=BLUE_D, lw=2)
    ax.set_xticks(range(1, len(order) + 1), [f"{g}\n(n={len(x)})" for g, x in zip(order, data)])
    ax.set_ylabel(ylabel)
    ax.grid(axis="y"); ax.grid(axis="x", visible=False)
    return svg(f)


def impact_strip(ei: pd.DataFrame, w=560, h=280):
    """Rank change of records carrying an injected error: without the gate (all) vs what still reaches users with the gate."""
    e = ei[ei.injected_error]
    f, ax = fig(w, h)
    x = np.sort(e.rank_change_pts.dropna().values)[::-1]
    ax.bar(np.arange(len(x)), x, color=[RED if v > 10 else GRAY for v in x], width=1.0)
    ax.axhline(10, color=INK2, ls="--", lw=0.8)
    ax.set_ylabel("Rank change (percentile points)")
    ax.set_xlabel("Records with an injected error, sorted")
    ax.grid(axis="y"); ax.grid(axis="x", visible=False)
    return svg(f)


def lag_bars(d: pd.DataFrame, w=470, h=240):
    """d: columns source, year, share. Latest fiscal year available per source."""
    srcs = list(dict.fromkeys(d.source))
    years = sorted(d.year.unique())
    f, ax = fig(w, h)
    x = np.arange(len(years))
    cols = [GRAY, BLUE_L, BLUE_D]
    bw = 0.8 / len(srcs)
    for i, s_ in enumerate(srcs):
        v = d[d.source == s_].set_index("year").share.reindex(years).fillna(0)
        ax.bar(x + (i - (len(srcs) - 1) / 2) * bw, v, bw * 0.95, color=cols[i % 3], label=s_)
    ax.set_xticks(x, [str(int(y)) for y in years])
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.set_xlabel("Year the latest available fiscal period ends")
    ax.grid(axis="y"); ax.grid(axis="x", visible=False)
    ax.set_ylim(0, 1.05)
    ax.legend(loc="upper left", fontsize=8)
    return svg(f)


def oat_bars(oat: pd.DataFrame, w=470, h=250):
    """One-at-a-time weight change: Kendall tau for each pillar x0.5 / x1.5."""
    d = oat.copy()
    d["label"] = d.pillar.str.replace("_", " ") + " x" + d.factor.map(lambda f: f"{f:g}")
    d = d.iloc[::-1]
    f, ax = fig(w, h)
    y = np.arange(len(d))
    cols = [RED if l > 0 else BLUE for l in d.get("scores_lost", pd.Series(0, index=d.index))]
    ax.barh(y, d.tau, color=cols, height=0.62)
    for yi, (t, l) in enumerate(zip(d.tau, d.get("scores_lost", pd.Series(0, index=d.index)))):
        ax.text(t + 0.005, yi, f"{t:.2f}" + (f"  ({int(l)} scores lost)" if l else ""), va="center", fontsize=8, color=INK2)
    ax.set_yticks(y, d.label, fontsize=8)
    ax.set_xlim(0.6, 1.08)
    ax.set_xlabel("Kendall tau vs base ranking")
    return svg(f)


def golden_scatter(excel: pd.Series, python: pd.Series, w=470, h=250):
    f, ax = fig(w, h)
    ax.grid(True, axis="both")
    ax.plot([0, 100], [0, 100], color=GRAY_D, lw=1, ls="--")
    ax.scatter(excel, python, s=36, color=BLUE, zorder=3)
    ax.set_xlim(0, 100); ax.set_ylim(0, 100)
    ax.set_xlabel("Score computed by hand in Excel"); ax.set_ylabel("Score computed by the code")
    return svg(f)


def stacked_rules(rules: pd.DataFrame, w=470, h=230):
    dims = ["completeness", "validity", "consistency", "uniqueness", "freshness", "accuracy"]
    p = rules.groupby(["dimension", "severity"]).size().unstack(fill_value=0).reindex(dims).fillna(0)
    f, ax = fig(w, h)
    left = np.zeros(len(p))
    for sev, col in (("error", RED), ("warning", BLUE_L), ("info", GRAY)):
        if sev in p:
            ax.barh(np.arange(len(p))[::-1], p[sev], left=left, color=col, label=sev, height=0.6)
            left += p[sev].values
    ax.set_yticks(np.arange(len(p))[::-1], [d.capitalize() for d in p.index])
    ax.set_xlabel("Rules (red: error · light blue: warning · grey: info)")
    return svg(f)
