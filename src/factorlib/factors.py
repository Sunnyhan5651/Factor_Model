"""팩터 익스포저 계산 모듈.

현재 구현: 12-1 Momentum
  - 12개월 누적 수익률에서 최근 1개월 수익률을 제거
  - 공식: price[t-1] / price[t-13] - 1
  - 크로스섹션 z-score 정규화 적용
"""
from __future__ import annotations

import pandas as pd
import numpy as np

from .config import Params


def compute_momentum(price_df: pd.DataFrame, params: Params) -> pd.DataFrame:
    """
    월별 price_df (date × ticker) → 월별 12-1 모멘텀 팩터 DataFrame.

    price[t-1]  : 한 달 전 가격 (단기 반전 효과 제거용 skip)
    price[t-13] : 13달 전 가격
    factor[t]   = price[t-1] / price[t-13] - 1
    """
    skip  = params.lookback_skip          # 1
    total = params.lookback_long + skip   # 13

    price_lag1  = price_df.shift(skip)    # t-1
    price_lag13 = price_df.shift(total)   # t-13

    momentum = price_lag1 / price_lag13 - 1

    # 두 기준 가격 모두 유효한 경우만 남김
    valid_mask = price_lag1.notna() & price_lag13.notna()
    momentum[~valid_mask] = float("nan")

    return momentum


def zscore_cross_section(factor_df: pd.DataFrame,
                         min_stocks: int = 20) -> pd.DataFrame:
    """
    날짜별 크로스섹션 z-score 정규화.
    유효 종목 수가 min_stocks 미만인 날짜는 전부 NaN 처리.
    """
    mean = factor_df.mean(axis=1)
    std  = factor_df.std(axis=1)

    # 표준편차 0인 날짜 처리
    std[std == 0] = float("nan")

    zscored = factor_df.sub(mean, axis=0).div(std, axis=0)

    # 유효 종목 수 필터
    n_valid = factor_df.notna().sum(axis=1)
    zscored[n_valid < min_stocks] = float("nan")

    return zscored


def winsorize(factor_df: pd.DataFrame, pct: float = 0.01) -> pd.DataFrame:
    """상하위 pct% 극단값 winsorization (날짜별 크로스섹션)."""
    if factor_df.empty or factor_df.shape[1] == 0:
        return factor_df
    lo = factor_df.quantile(pct, axis=1)
    hi = factor_df.quantile(1 - pct, axis=1)
    return factor_df.clip(lower=lo, upper=hi, axis=0)
