#!/usr/bin/env python3
"""CSV 데이터 기반 12-1 Momentum 팩터 백테스트.

IFE_term_stock_data.csv (CRSP 포맷) 에 기존 팩터 엔진 적용.

컬럼: PERMNO, date, EXCHCD, TICKER, COMNAM, ADJ_PRC, VOL

사용 예:
  python run_backtest_csv.py
  python run_backtest_csv.py --csv /path/to/data.csv
  python run_backtest_csv.py --exchcd 1 2 3     # NYSE+AMEX+NASDAQ (기본)
  python run_backtest_csv.py --universe-size 500
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent / "src"))

from factorlib.config  import Params
from factorlib.data    import FactorDataset
from factorlib.engine  import run_backtest
from factorlib.metrics import compute_ic, compute_metrics
from factorlib.plots   import (plot_quantile_bar, plot_ls_equity,
                                plot_ic_series, plot_quantile_equity,
                                plot_yearly_heatmap)

_HERE      = Path(__file__).parent.resolve()
_CSV_DEFAULT = Path("/Users/sunkyuhan/Desktop/HYFE/IFE_term_project/IFE_term_stock_data.csv")

_CJK_RANGES = ((0xAC00, 0xD7A3), (0x1100, 0x11FF), (0x3130, 0x318F),
               (0x4E00, 0x9FFF), (0x3400, 0x4DBF))


def _wlen(s: str) -> int:
    return sum(2 if any(lo <= ord(c) <= hi for lo, hi in _CJK_RANGES) else 1
               for c in s)


def _pad(s: str, w: int, align: str = "<") -> str:
    p = max(0, w - _wlen(s))
    if align == "<":  return s + " " * p
    if align == ">":  return " " * p + s
    lp = p // 2;      return " " * lp + s + " " * (p - lp)


def _nf(v, fmt: str) -> str:
    if v != v: return "N/A"
    try:       return fmt % v
    except:    return "N/A"


def load_csv_dataset(csv_path: str,
                     exchcd_filter: list[int],
                     min_price: float,
                     start: str,
                     end: str) -> FactorDataset:
    """CSV → FactorDataset 변환.

    market_caps 대리변수: ADJ_PRC × VOL (월별 달러 거래대금)
    이 값 기준으로 universe_size 상위 종목을 선택.
    """
    print(f"  CSV 로딩: {csv_path}")
    df = pd.read_csv(csv_path, parse_dates=["date"])

    # ── 거래소 필터 ────────────────────────────────────────────────
    df = df[df["EXCHCD"].isin(exchcd_filter)]

    # ── 기간 필터 ──────────────────────────────────────────────────
    df = df[(df["date"] >= pd.to_datetime(start)) &
            (df["date"] <= pd.to_datetime(end))]

    # ── 가격 이상치 제거 (1달러 미만 또는 1만 달러 초과) ──────────
    df = df[(df["ADJ_PRC"] >= min_price) & (df["ADJ_PRC"] < 10_000)]

    # ── 월별 중복 PERMNO 제거 (마지막 값 사용) ─────────────────────
    df = df.sort_values("date").drop_duplicates(subset=["PERMNO", "date"], keep="last")

    # PERMNO → 문자열 티커로 변환
    df["ticker"] = df["PERMNO"].astype(str)

    # ── Wide 피봇: date × ticker ────────────────────────────────────
    prices = df.pivot(index="date", columns="ticker", values="ADJ_PRC")
    prices.index = pd.DatetimeIndex(prices.index)
    prices.sort_index(inplace=True)

    # ── 시가총액 대리변수: 가격 × 거래량 ───────────────────────────
    vol_df = df.pivot(index="date", columns="ticker", values="VOL").fillna(0)
    vol_df.index = pd.DatetimeIndex(vol_df.index)
    vol_df.sort_index(inplace=True)

    # 인덱스/컬럼 정렬
    common_idx = prices.index.intersection(vol_df.index)
    common_col = prices.columns.intersection(vol_df.columns)
    prices      = prices.loc[common_idx, common_col]
    vol_df      = vol_df.loc[common_idx, common_col]

    proxy_mcap = prices.mul(vol_df)   # 달러 거래대금 (유동성 대리)

    print(f"  {len(prices)}개월 × {prices.shape[1]}개 종목 로딩 완료")
    print(f"  기간: {prices.index[0].date()} ~ {prices.index[-1].date()}")

    return FactorDataset(prices=prices, market_caps=proxy_mcap)


def print_metrics(metrics: dict, source: str) -> None:
    WL, WV = 18, 14
    rows = [
        ("누적 수익률",       _nf(metrics.get("total_return_pct"),  "%+.2f %%")),
        ("연환산 수익률",     _nf(metrics.get("ann_return_pct"),    "%+.2f %%")),
        ("연환산 변동성",     _nf(metrics.get("ann_vol_pct"),       "%.2f %%")),
        ("Sharpe Ratio",      _nf(metrics.get("sharpe"),            "%+.3f")),
        ("MDD",               _nf(metrics.get("mdd_pct"),          "%.2f %%")),
        ("MDD 지속(월)",      _nf(metrics.get("mdd_months"),       "%d 개월")),
        ("Calmar",            _nf(metrics.get("calmar"),           "%+.3f")),
        ("IC 평균",           _nf(metrics.get("ic_mean"),          "%.4f")),
        ("IC std",            _nf(metrics.get("ic_std"),           "%.4f")),
        ("ICIR",              _nf(metrics.get("icir"),             "%.3f")),
        ("IC > 0 비율",       _nf(metrics.get("ic_pos_pct"),       "%.1f %%")),
        ("NW 월평균 수익률",  _nf(metrics.get("nw_mean_monthly"),  "%+.3f %%")),
        ("NW t통계량",        _nf(metrics.get("nw_t"),             "%+.3f")),
        ("분석 기간(월)",     _nf(metrics.get("n_months"),         "%d 개월")),
    ]
    TOTAL = 4 + WL + WV + 3

    def hline(l, m, r): return l + "─" * (WL + 2) + m + "─" * (WV + 2) + r
    def row(lbl, val):  return "│ " + _pad(lbl, WL) + " │ " + _pad(val, WV, ">") + " │"

    print(f"\n{'═' * TOTAL}")
    print(f"  12-1 Momentum Long-Short 성과 요약  [{source}]")
    print(f"{'═' * TOTAL}")
    print(hline("┌", "┬", "┐"))
    print("│ " + _pad("지표", WL) + " │ " + _pad("값", WV, "^") + " │")
    print(hline("├", "┼", "┤"))
    for lbl, val in rows:
        print(row(lbl, val))
    print(hline("└", "┴", "┘"))


def print_yearly(ls_returns, ic_series) -> None:
    if len(ls_returns) == 0:
        return
    years = sorted(set(ls_returns.index.year))
    print(f"\n{'─' * 40}")
    print(f"  연도별 Long-Short 수익률")
    print(f"{'─' * 40}")
    for yr in years:
        yr_ret = ls_returns[ls_returns.index.year == yr]
        ann    = float((1 + yr_ret).prod() - 1) * 100
        yr_ic  = ic_series[ic_series.index.year == yr] if len(ic_series) > 0 else pd.Series()
        ic_avg = f"{yr_ic.mean():.3f}" if len(yr_ic) > 0 else "N/A"
        sign   = "+" if ann >= 0 else ""
        print(f"  {yr}  수익률: {sign}{ann:.2f}%   IC: {ic_avg}")
    print(f"{'─' * 40}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv",           default=str(_CSV_DEFAULT))
    ap.add_argument("--start",         default="2000-01-01")
    ap.add_argument("--end",           default="2020-12-31")
    ap.add_argument("--exchcd",        type=int, nargs="+", default=[1, 2, 3],
                    help="EXCHCD 필터 (1=NYSE, 2=AMEX, 3=NASDAQ)")
    ap.add_argument("--universe-size", type=int,   default=500)
    ap.add_argument("--min-price",     type=float, default=1.0,
                    help="최소 주가 (USD, 페니스톡 제외)")
    ap.add_argument("--n-quantile",    type=int,   default=5)
    ap.add_argument("--commission-bps",type=float, default=1.5)
    ap.add_argument("--slippage-bps",  type=float, default=3.0)
    ap.add_argument("--out",           default=str(_HERE / "results_csv"))
    args = ap.parse_args()

    t0 = time.time()

    params = Params(
        lookback_long  = 12,
        lookback_skip  = 1,
        universe_size  = args.universe_size,
        min_price      = args.min_price,
        n_quantile     = args.n_quantile,
        commission_bps = args.commission_bps,
        slippage_bps   = args.slippage_bps,
        start          = args.start,
        end            = args.end,
    )

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. 데이터 로딩 ───────────────────────────────────────────────────────
    print(f"\n[1/4] CSV 데이터 로딩 ({args.start} ~ {args.end})")
    print(f"      거래소 필터: EXCHCD {args.exchcd}  |  유니버스: {args.universe_size}개")
    dataset = load_csv_dataset(
        csv_path     = args.csv,
        exchcd_filter= args.exchcd,
        min_price    = args.min_price,
        start        = args.start,
        end          = args.end,
    )

    # ── 2. 백테스트 실행 ─────────────────────────────────────────────────────
    print("\n[2/4] 백테스트 실행 중...")
    result = run_backtest(dataset, params)
    print(f"      완료 — 총 {len(result.ls_returns)}개월 수익률 산출")

    # ── 3. 성과 지표 ─────────────────────────────────────────────────────────
    print("\n[3/4] 성과 지표 계산 중...")
    ic_series = compute_ic(result.factor_scores, result.fwd_returns)
    metrics   = compute_metrics(result.ls_returns, ic_series)

    source = f"IFE CSV, EXCHCD={args.exchcd}, N={args.universe_size}"
    print_metrics(metrics, source)
    print_yearly(result.ls_returns, ic_series)

    avg_to = result.turnover_series.mean()
    print(f"\n  평균 월별 회전율 (편도): {avg_to:.1%}")

    # ── 4. 차트 저장 ─────────────────────────────────────────────────────────
    print(f"\n[4/4] 차트 저장 중... → {out_dir}")
    plot_quantile_bar(result.quantile_returns, out_dir)
    plot_ls_equity(result.ls_returns, out_dir)
    plot_ic_series(ic_series, out_dir)
    plot_quantile_equity(result.quantile_returns, result.ls_returns, out_dir)
    plot_yearly_heatmap(result.ls_returns, out_dir)

    print(f"\n실행 완료: {time.time() - t0:.0f}초 | 결과 폴더: {out_dir.absolute()}")


if __name__ == "__main__":
    main()
