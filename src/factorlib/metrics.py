"""성과 지표 계산 모듈.

주요 지표:
  - Sharpe Ratio (연환산)
  - MDD (Maximum Drawdown)
  - IC (Information Coefficient, Spearman)
  - ICIR (IC / IC.std())
  - Newey-West t통계량 (자기상관 보정)
  - 분위수별 연환산 수익률
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


# ── IC (Information Coefficient) ─────────────────────────────────────────────

def compute_ic(factor_scores: pd.DataFrame,
               fwd_returns: pd.DataFrame) -> pd.Series:
    """
    날짜별 Spearman IC: 팩터 점수 ↔ 1개월 선행 수익률 순위 상관계수.
    """
    ic_dict = {}
    for date in factor_scores.index:
        if date not in fwd_returns.index:
            continue
        scores = factor_scores.loc[date].dropna()
        fwd    = fwd_returns.loc[date].reindex(scores.index).dropna()
        common = scores.index.intersection(fwd.index)
        if len(common) < 20:
            continue
        rho, _ = stats.spearmanr(scores[common], fwd[common])
        ic_dict[date] = float(rho)

    return pd.Series(ic_dict).sort_index()


def compute_icir(ic_series: pd.Series) -> float:
    """IC / IC.std() — 팩터 안정성 지표."""
    if ic_series.std() == 0:
        return float("nan")
    return float(ic_series.mean() / ic_series.std())


# ── 포트폴리오 성과 지표 ──────────────────────────────────────────────────────

def compute_cumulative(returns: pd.Series) -> pd.Series:
    """누적 수익률 (원금 1로 시작)."""
    return (1 + returns).cumprod()


def compute_mdd(returns: pd.Series) -> tuple[float, int]:
    """
    최대 낙폭 (MDD)과 낙폭 지속 기간(개월).
    Returns: (mdd_pct, mdd_duration_months)
    """
    cum = compute_cumulative(returns)
    peak = cum.cummax()
    drawdown = (cum - peak) / peak
    mdd = float(drawdown.min())

    # MDD 지속 기간
    is_dd = drawdown < 0
    max_duration = 0
    cur_duration = 0
    for v in is_dd:
        if v:
            cur_duration += 1
            max_duration = max(max_duration, cur_duration)
        else:
            cur_duration = 0

    return mdd, max_duration


def compute_sharpe(returns: pd.Series, freq: int = 12,
                   rf: float = 0.0) -> float:
    """
    연환산 Sharpe Ratio.
    freq=12: 월별 수익률 → 연환산 (×√12)
    """
    excess = returns - rf / freq
    if excess.std() == 0:
        return float("nan")
    return float(excess.mean() / excess.std() * np.sqrt(freq))


def compute_ann_return(returns: pd.Series, freq: int = 12) -> float:
    """연환산 수익률."""
    if len(returns) == 0:
        return float("nan")
    total = float((1 + returns).prod())
    n_years = len(returns) / freq
    return float(total ** (1 / n_years) - 1)


def compute_ann_vol(returns: pd.Series, freq: int = 12) -> float:
    """연환산 변동성."""
    return float(returns.std() * np.sqrt(freq))


# ── Newey-West t통계량 ────────────────────────────────────────────────────────

def newey_west_t(returns: pd.Series, lags: int | None = None) -> tuple[float, float]:
    """
    자기상관을 보정한 Newey-West t통계량.
    Returns: (mean_monthly, t_stat)
    """
    r = returns.dropna().values
    n = len(r)
    if n < 10:
        return float("nan"), float("nan")

    if lags is None:
        lags = int(np.floor(4 * (n / 100) ** (2 / 9)))

    mean = r.mean()
    gamma0 = np.var(r, ddof=1)
    nw_var = gamma0

    for lag in range(1, lags + 1):
        gamma_l = np.cov(r[lag:], r[:-lag])[0, 1]
        w = 1 - lag / (lags + 1)   # Bartlett kernel
        nw_var += 2 * w * gamma_l

    se = np.sqrt(nw_var / n)
    t_stat = mean / se if se > 0 else float("nan")
    return float(mean), float(t_stat)


# ── 종합 지표 계산 ────────────────────────────────────────────────────────────

def compute_metrics(returns: pd.Series,
                    ic_series: pd.Series | None = None) -> dict:
    """Long-Short 수익률 시리즈에서 전체 성과 지표 딕셔너리 반환."""
    mdd, mdd_dur = compute_mdd(returns)
    nw_mean, nw_t = newey_west_t(returns)

    m: dict = {
        "total_return_pct":  float((1 + returns).prod() - 1) * 100,
        "ann_return_pct":    compute_ann_return(returns) * 100,
        "ann_vol_pct":       compute_ann_vol(returns) * 100,
        "sharpe":            compute_sharpe(returns),
        "mdd_pct":           mdd * 100,
        "mdd_months":        mdd_dur,
        "calmar":            compute_ann_return(returns) / abs(mdd) if mdd != 0 else float("nan"),
        "nw_mean_monthly":   nw_mean * 100,
        "nw_t":              nw_t,
        "n_months":          len(returns),
    }

    if ic_series is not None and len(ic_series) > 0:
        m["ic_mean"]  = float(ic_series.mean())
        m["ic_std"]   = float(ic_series.std())
        m["icir"]     = compute_icir(ic_series)
        m["ic_pos_pct"] = float((ic_series > 0).mean() * 100)

    return m
