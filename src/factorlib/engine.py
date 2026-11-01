"""백테스트 엔진.

월별 리밸런싱:
  1. 팩터 점수 계산 → 분위수 할당
  2. 다음 달 말까지 보유 수익률 계산
  3. 거래비용 (turnover × cost_bps) 차감
  4. Long-Short: Q5 long + Q1 short (각 50% 레버리지)
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
import numpy as np

from .config import Params
from .data import FactorDataset, get_universe
from .factors import compute_momentum, zscore_cross_section, winsorize
from .portfolio import assign_quantiles, build_weights, compute_turnover


@dataclass
class BacktestResult:
    # 날짜별 수익률 시리즈
    quantile_returns: dict[int, pd.Series]   # {q: return_series}
    ls_returns:       pd.Series              # Long-Short 일별 수익률

    # IC 계산용 raw 데이터
    factor_scores:  pd.DataFrame             # date × ticker
    fwd_returns:    pd.DataFrame             # date × ticker (1개월 선행)

    # 회전율
    turnover_series: pd.Series


def run_backtest(dataset: FactorDataset, params: Params) -> BacktestResult:
    """전체 백테스트 실행."""

    price_df = dataset.prices
    cap_df   = dataset.market_caps
    dates    = price_df.index.tolist()

    # ── 팩터 계산 (전체 기간) ─────────────────────────────────────────────────
    momentum_raw = compute_momentum(price_df, params)
    momentum_raw = winsorize(momentum_raw, pct=0.01)
    factor_df    = zscore_cross_section(momentum_raw)

    # ── 1개월 선행 수익률 ─────────────────────────────────────────────────────
    fwd_ret_df = price_df.pct_change(1).shift(-1)   # t+1 수익률

    # ── 리밸런싱 날짜: 팩터가 유효한 날짜 ─────────────────────────────────────
    rebal_dates = [d for d in dates if factor_df.loc[d].notna().sum() >= params.n_quantile * 5]

    n_q = params.n_quantile
    q_returns   = {q: {} for q in range(1, n_q + 1)}
    ls_ret_dict = {}
    turnover_dict = {}

    prev_long_w  = pd.Series(dtype=float)
    prev_short_w = pd.Series(dtype=float)

    for i, date in enumerate(rebal_dates):
        if i + 1 >= len(rebal_dates):
            break

        next_date = rebal_dates[i + 1]

        # ── 유니버스 결정 ────────────────────────────────────────────────────
        universe = get_universe(cap_df, date, params.universe_size,
                                params.min_price, price_df)
        if len(universe) < n_q * 5:
            continue

        # ── 팩터 점수 (유니버스 내) ──────────────────────────────────────────
        scores = factor_df.loc[date].reindex(universe).dropna()
        if len(scores) < n_q * 5:
            continue

        # ── 분위수 할당 ──────────────────────────────────────────────────────
        q_labels = assign_quantiles(scores, n_q)
        if q_labels.empty:
            continue

        # ── 다음 달 수익률 (next_date 기준) ──────────────────────────────────
        if next_date not in price_df.index or date not in price_df.index:
            continue

        cur_price  = price_df.loc[date]
        next_price = price_df.loc[next_date]
        fwd_ret    = (next_price / cur_price - 1).reindex(scores.index)

        # ── 분위수별 수익률 ──────────────────────────────────────────────────
        for q in range(1, n_q + 1):
            q_tickers = q_labels[q_labels == q].index
            q_fwd     = fwd_ret[q_tickers].dropna()
            if len(q_fwd) > 0:
                q_returns[q][next_date] = float(q_fwd.mean())

        # ── Long-Short 포트폴리오 ────────────────────────────────────────────
        long_w  = build_weights(q_labels, n_q)       # Q5 long
        short_w = build_weights(q_labels, 1)          # Q1 short

        long_ret  = fwd_ret[long_w.index].dropna().mean()
        short_ret = fwd_ret[short_w.index].dropna().mean()

        if pd.isna(long_ret) or pd.isna(short_ret):
            continue

        # ── 거래비용 ─────────────────────────────────────────────────────────
        to_long  = compute_turnover(prev_long_w,  long_w)
        to_short = compute_turnover(prev_short_w, short_w)
        cost     = (to_long + to_short) * params.cost_bps / 10_000

        # Long-Short 수익률: (Long - Short) / 2 로 레버리지 중립화
        ls_ret = (long_ret - short_ret) / 2.0 - cost

        ls_ret_dict[next_date]  = ls_ret
        turnover_dict[next_date] = (to_long + to_short) / 2.0

        prev_long_w  = long_w
        prev_short_w = short_w

    # ── 결과 패키징 ──────────────────────────────────────────────────────────
    quantile_returns = {
        q: pd.Series(q_returns[q]).sort_index()
        for q in range(1, n_q + 1)
    }
    ls_series       = pd.Series(ls_ret_dict).sort_index()
    turnover_series = pd.Series(turnover_dict).sort_index()

    return BacktestResult(
        quantile_returns=quantile_returns,
        ls_returns=ls_series,
        factor_scores=factor_df,
        fwd_returns=fwd_ret_df,
        turnover_series=turnover_series,
    )
