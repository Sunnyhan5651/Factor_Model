"""시각화 모듈.

생성 차트:
  1. 분위수별 연환산 수익률 바차트
  2. Long-Short 누적 손익 곡선
  3. IC 시계열 (월별 + 12개월 이동평균)
  4. 분위수별 누적 수익률 (Q1~Q5 + LS)
  5. 연도별 Long-Short 수익률 히트맵
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")   # 헤드리스 환경 대응
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd
import numpy as np

from .metrics import compute_cumulative, compute_ann_return


# ── 공통 설정 ─────────────────────────────────────────────────────────────────

COLORS = {
    1: "#d62728",   # Q1 (하위, 빨강)
    2: "#ff7f0e",
    3: "#9467bd",
    4: "#17becf",
    5: "#2ca02c",   # Q5 (상위, 초록)
    "ls": "#1f77b4",
}

plt.rcParams.update({
    "font.family":    "AppleGothic",
    "axes.unicode_minus": False,
    "figure.dpi":     120,
    "axes.spines.top":   False,
    "axes.spines.right": False,
})


def _save(fig: plt.Figure, path: Path, name: str) -> None:
    out = path / name
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"  저장: {out}")


# ── 1. 분위수 연환산 수익률 바차트 ────────────────────────────────────────────

def plot_quantile_bar(quantile_returns: dict[int, pd.Series],
                      out_dir: Path) -> None:
    ann_rets = {
        q: compute_ann_return(r) * 100
        for q, r in quantile_returns.items()
        if len(r) > 0
    }
    qs   = sorted(ann_rets)
    vals = [ann_rets[q] for q in qs]
    clrs = [COLORS.get(q, "#aaa") for q in qs]

    fig, ax = plt.subplots(figsize=(7, 4))
    bars = ax.bar([f"Q{q}" for q in qs], vals, color=clrs, width=0.6)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title("분위수별 연환산 수익률 (12-1 Momentum)", fontsize=13)
    ax.set_ylabel("연환산 수익률 (%)")
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.1f%%"))
    for bar, val in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2,
                val + (0.3 if val >= 0 else -0.6),
                f"{val:.1f}%", ha="center", va="bottom", fontsize=9)
    _save(fig, out_dir, "01_quantile_bar.png")


# ── 2. Long-Short 누적 손익 곡선 ─────────────────────────────────────────────

def plot_ls_equity(ls_returns: pd.Series, out_dir: Path) -> None:
    cum = compute_cumulative(ls_returns) * 100 - 100   # % 기준

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(cum.index, cum.values, color=COLORS["ls"], linewidth=1.5)
    ax.fill_between(cum.index, cum.values, 0,
                    where=(cum.values >= 0), alpha=0.15, color=COLORS["ls"])
    ax.fill_between(cum.index, cum.values, 0,
                    where=(cum.values < 0),  alpha=0.15, color=COLORS[1])
    ax.axhline(0, color="black", linewidth=0.6, linestyle="--")
    ax.set_title("Long-Short 누적 수익률 (Q5 Long / Q1 Short)", fontsize=13)
    ax.set_ylabel("누적 수익률 (%)")
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f%%"))
    _save(fig, out_dir, "02_ls_equity.png")


# ── 3. IC 시계열 ──────────────────────────────────────────────────────────────

def plot_ic_series(ic_series: pd.Series, out_dir: Path) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)

    # 월별 IC
    axes[0].bar(ic_series.index, ic_series.values,
                color=[COLORS[5] if v > 0 else COLORS[1] for v in ic_series.values],
                width=25, alpha=0.7)
    axes[0].axhline(0, color="black", linewidth=0.6)
    axes[0].axhline(ic_series.mean(), color=COLORS["ls"], linewidth=1.2,
                    linestyle="--", label=f"평균 IC: {ic_series.mean():.3f}")
    axes[0].set_title("월별 IC (Information Coefficient)", fontsize=12)
    axes[0].set_ylabel("Spearman IC")
    axes[0].legend(fontsize=9)

    # 12개월 이동평균 IC
    ic_ma = ic_series.rolling(12).mean()
    axes[1].plot(ic_ma.index, ic_ma.values, color=COLORS["ls"], linewidth=1.5)
    axes[1].axhline(0, color="black", linewidth=0.6)
    axes[1].set_title("12개월 이동평균 IC", fontsize=12)
    axes[1].set_ylabel("Rolling IC")

    fig.tight_layout()
    _save(fig, out_dir, "03_ic_series.png")


# ── 4. 분위수별 누적 수익률 ───────────────────────────────────────────────────

def plot_quantile_equity(quantile_returns: dict[int, pd.Series],
                         ls_returns: pd.Series, out_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))

    for q, ret in sorted(quantile_returns.items()):
        if len(ret) == 0:
            continue
        cum = compute_cumulative(ret)
        ax.plot(cum.index, cum.values, color=COLORS.get(q, "#aaa"),
                linewidth=1.2, label=f"Q{q}", alpha=0.85)

    if len(ls_returns) > 0:
        cum_ls = compute_cumulative(ls_returns)
        ax.plot(cum_ls.index, cum_ls.values,
                color=COLORS["ls"], linewidth=2.0,
                linestyle="--", label="L/S (Q5-Q1)")

    ax.axhline(1, color="black", linewidth=0.6, linestyle=":")
    ax.set_title("분위수별 누적 수익률", fontsize=13)
    ax.set_ylabel("누적 수익률 (원금=1)")
    ax.legend(loc="upper left", fontsize=9)
    _save(fig, out_dir, "04_quantile_equity.png")


# ── 5. 연도별 Long-Short 수익률 히트맵 ───────────────────────────────────────

def plot_yearly_heatmap(ls_returns: pd.Series, out_dir: Path) -> None:
    df = ls_returns.to_frame("ret")
    df["year"]  = df.index.year
    df["month"] = df.index.month
    pivot = df.pivot_table(values="ret", index="year", columns="month", aggfunc="sum")
    pivot.columns = [f"{m}월" for m in pivot.columns]
    pivot_pct = pivot * 100

    fig, ax = plt.subplots(figsize=(13, max(4, len(pivot) * 0.5 + 1)))
    vmax = max(abs(pivot_pct.values[~np.isnan(pivot_pct.values)])) if pivot_pct.notna().any().any() else 5

    im = ax.imshow(pivot_pct.values, cmap="RdYlGn", vmin=-vmax, vmax=vmax, aspect="auto")
    ax.set_xticks(range(len(pivot_pct.columns)))
    ax.set_xticklabels(pivot_pct.columns, fontsize=9)
    ax.set_yticks(range(len(pivot_pct.index)))
    ax.set_yticklabels(pivot_pct.index, fontsize=9)

    for i in range(len(pivot_pct.index)):
        for j in range(len(pivot_pct.columns)):
            val = pivot_pct.values[i, j]
            if not np.isnan(val):
                ax.text(j, i, f"{val:.1f}", ha="center", va="center",
                        fontsize=7, color="black")

    plt.colorbar(im, ax=ax, label="수익률 (%)")
    ax.set_title("연도별 월간 Long-Short 수익률 히트맵", fontsize=13)
    fig.tight_layout()
    _save(fig, out_dir, "05_yearly_heatmap.png")
