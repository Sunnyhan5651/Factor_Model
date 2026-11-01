"""팩터 익스포저 계산 모듈.

현재 구현: 12-1 Momentum (롤링 평균 방식)
  - 최근 1개월 수익률을 제외한 직전 12개월 월별 수익률의 평균
  - 공식: mean( ret[t-1], ret[t-2], ..., ret[t-12] )
"""
from __future__ import annotations
import pandas as pd
import numpy as np
from .config import Params

def compute_momentum(price_df: pd.DataFrame, params: Params) -> pd.DataFrame:
    monthly_ret = price_df.pct_change(1)
    momentum = monthly_ret.shift(params.lookback_skip).rolling(params.lookback_long).mean()
    return momentum

def zscore_cross_section(factor_df: pd.DataFrame, min_stocks: int = 20) -> pd.DataFrame:
    mean = factor_df.mean(axis=1)
    std  = factor_df.std(axis=1)
    std[std == 0] = float("nan")
    zscored = factor_df.sub(mean, axis=0).div(std, axis=0)
    n_valid = factor_df.notna().sum(axis=1)
    zscored[n_valid < min_stocks] = float("nan")
    return zscored

def winsorize(factor_df: pd.DataFrame, pct: float = 0.01) -> pd.DataFrame:
    if factor_df.empty or factor_df.shape[1] == 0:
        return factor_df
    lo = factor_df.quantile(pct, axis=1)
    hi = factor_df.quantile(1 - pct, axis=1)
    return factor_df.clip(lower=lo, upper=hi, axis=0)
