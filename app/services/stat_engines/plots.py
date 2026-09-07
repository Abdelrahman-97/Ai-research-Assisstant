"""Matplotlib figures for the test engines (Agg backend, brand teal).

Each function draws one PNG and returns its path. Kept separate so engines stay
focused on the maths; a plotting failure is caught by the caller and never fails
the analysis itself.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from app.services.stat_engines.base import TEAL, TEAL_SOFT  # noqa: E402


def _save(fig, path: str | Path) -> str:
    fig.tight_layout()
    fig.savefig(str(path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    return str(path)


def box_by_group(groups: dict[str, list[float]], *, ylabel: str, path: str | Path,
                 title: str = "") -> str:
    """Box plot of a numeric outcome across groups."""
    fig, ax = plt.subplots(figsize=(6, 4))
    labels = list(groups.keys())
    data = [groups[k] for k in labels]
    bp = ax.boxplot(data, patch_artist=True, widths=0.5)
    ax.set_xticks(range(1, len(labels) + 1))
    ax.set_xticklabels(labels)
    for patch in bp["boxes"]:
        patch.set_facecolor(TEAL_SOFT)
        patch.set_edgecolor(TEAL)
    for med in bp["medians"]:
        med.set_color(TEAL)
        med.set_linewidth(2)
    ax.set_ylabel(ylabel)
    if title:
        ax.set_title(title)
    ax.grid(axis="y", alpha=0.3)
    return _save(fig, path)


def scatter_fit(x: list[float], y: list[float], *, xlabel: str, ylabel: str,
                path: str | Path, slope: float | None = None, intercept: float | None = None) -> str:
    """Scatter plot with an optional fitted line."""
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.scatter(x, y, color=TEAL, alpha=0.7, edgecolors="white", s=40)
    if slope is not None and intercept is not None and x:
        xs = [min(x), max(x)]
        ys = [intercept + slope * v for v in xs]
        ax.plot(xs, ys, color="#b4462f", linewidth=2)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(alpha=0.3)
    return _save(fig, path)


def paired_lines(pre: list[float], post: list[float], *, labels=("Pre", "Post"),
                 ylabel: str, path: str | Path) -> str:
    """Before/after paired plot (a line per participant)."""
    fig, ax = plt.subplots(figsize=(5, 4))
    for a, b in zip(pre, post):
        ax.plot([0, 1], [a, b], color=TEAL_SOFT, alpha=0.5, marker="o", markersize=3)
    ax.plot([0, 1], [sum(pre) / len(pre), sum(post) / len(post)],
            color=TEAL, linewidth=3, marker="o", label="Mean")
    ax.set_xticks([0, 1])
    ax.set_xticklabels(list(labels))
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", alpha=0.3)
    ax.legend()
    return _save(fig, path)


def km_curves(curves: dict[str, dict], *, path: str | Path, xlabel: str = "Time") -> str:
    """Kaplan-Meier step curves. `curves[label] = {'time': [...], 'surv': [...]}`."""
    fig, ax = plt.subplots(figsize=(6, 4))
    palette = [TEAL, "#b4462f", "#5b8fa8", "#d8a657", "#8a6fb0"]
    for i, (label, c) in enumerate(curves.items()):
        ax.step(c["time"], c["surv"], where="post", color=palette[i % len(palette)],
                linewidth=2, label=str(label))
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Survival probability")
    ax.set_ylim(0, 1.02)
    ax.grid(alpha=0.3)
    ax.legend()
    return _save(fig, path)


def bland_altman(means: list[float], diffs: list[float], *, bias: float, loa_low: float,
                 loa_high: float, path: str | Path) -> str:
    """Bland-Altman plot: differences vs means, with bias and limits of agreement."""
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.scatter(means, diffs, color=TEAL, alpha=0.7, edgecolors="white", s=40)
    ax.axhline(bias, color="#b4462f", linewidth=1.5, label=f"Bias = {bias:.3g}")
    ax.axhline(loa_high, color="#5b8fa8", linestyle="--", linewidth=1,
               label=f"+1.96 SD = {loa_high:.3g}")
    ax.axhline(loa_low, color="#5b8fa8", linestyle="--", linewidth=1,
               label=f"-1.96 SD = {loa_low:.3g}")
    ax.set_xlabel("Mean of the two measurements")
    ax.set_ylabel("Difference between measurements")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    return _save(fig, path)


def grouped_bar(row_labels: list[str], col_labels: list[str], counts: list[list[float]],
                *, path: str | Path, ylabel: str = "Count") -> str:
    """Grouped bar chart for a contingency table."""
    fig, ax = plt.subplots(figsize=(6, 4))
    n_cols = len(col_labels)
    width = 0.8 / max(1, n_cols)
    palette = [TEAL, TEAL_SOFT, "#b4462f", "#d8a657", "#5b8fa8", "#8a6fb0"]
    for j, col in enumerate(col_labels):
        xs = [i + j * width for i in range(len(row_labels))]
        ys = [counts[i][j] for i in range(len(row_labels))]
        ax.bar(xs, ys, width=width, label=str(col), color=palette[j % len(palette)])
    ax.set_xticks([i + 0.4 - width / 2 for i in range(len(row_labels))])
    ax.set_xticklabels([str(r) for r in row_labels])
    ax.set_ylabel(ylabel)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    return _save(fig, path)
