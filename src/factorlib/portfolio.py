"""분위수 포트폴리오 구성 모듈.

Q5 (상위 20%): Long  /  Q1 (하위 20%): Short
Equal-weight 적용, 리밸런싱 회전율 계산.
"""
from __future__ import annotations

import pandas as pd
import numpy as np


def assign_quantiles(scores: pd.Series, n_quantile: int = 5) -> pd.Series:
    """
    팩터 점수 → 분위수 레이블 (1 = 최하위, n_quantile = 최상위).
    동점이 있을 경우 ties='first' 처리.
    """
    valid = scores.dropna()
    if len(valid) < n_quantile * 5:   # 분위당 최소 5개 종목 필요
        return pd.Series(dtype=float)

    labels = pd.qcut(valid, n_quantile, labels=False, duplicates="drop") + 1
    return labels.astype(int)


def build_weights(quantile_assignments: pd.Series, q: int) -> pd.Series:
    """특정 분위수의 equal-weight 포트폴리오 비중."""
    tickers = quantile_assignments[quantile_assignments == q].index
    if len(tickers) == 0:
        return pd.Series(dtype=float)
    return pd.Series(1.0 / len(tickers), index=tickers)


def compute_turnover(prev_weights: pd.Series, new_weights: pd.Series) -> float:
    """
    두 포트폴리오 간 회전율 계산.
    turnover = 0.5 * Σ|w_new - w_old|  (편도 기준)
    """
    all_tickers = prev_weights.index.union(new_weights.index)
    prev = prev_weights.reindex(all_tickers).fillna(0.0)
    new  = new_weights.reindex(all_tickers).fillna(0.0)
    return float(0.5 * (new - prev).abs().sum())
