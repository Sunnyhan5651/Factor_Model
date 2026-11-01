#!/usr/bin/env python3
"""12-1 Momentum 팩터 백테스트 실행 스크립트.

사용 예:
  python run_backtest.py                          # 기본 파라미터 실행
  python run_backtest.py --start 2018-01-01       # 시작일 변경
  python run_backtest.py --no-cache               # 캐시 무시하고 재수집
  python run_backtest.py --universe-size 100      # 유니버스 100개로 축소
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from factorlib.config  import Params
from factorlib.data    import load_dataset
from factorlib.engine  import run_backtest
from factorlib.metrics import compute_ic, compute_metrics
from factorlib.plots   import (plot_quantile_bar, plot_ls_equity,
                                plot_ic_series, plot_quantile_equity,
                                plot_yearly_heatmap)

_HERE = Path(__file__).parent.resolve()


# ── 터미널 출력 유틸 ──────────────────────────────────────────────────────────

_CJK_RANGES = ((0xAC00, 0xD7A3), (0x1100, 0x11FF), (0x3130, 0x318F),
               (0x4E00, 0x9FFF), (0x3400, 0x4DBF))


def _wlen(s: str) -> int:
    return sum(2 if any(lo <= ord(c) <= hi for lo, hi in _CJK_RANGES) else 1
               for c in s)


def _pad(s: str, w: int, align: str = "<") -> str:
    p = max(0, w - _wlen(s))
    if align == "<": return s + " " * p
    if align == ">": return " " * p + s
    lp = p // 2; return " " * lp + s + " " * (p - lp)


def _nf(v, fmt: str) -> str:
    if v != v: return "N/A"
    try:       return fmt % v
    except:    return "N/A"


def print_metrics(metrics: dict) -> None:
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
    print(f"  12-1 Momentum Long-Short 성과 요약")
    print(f"{'═' * TOTAL}")
    print(hline("┌", "┬", "┐"))
    print("│ " + _pad("지표", WL) + " │ " + _pad("값", WV, "^") + " │")
    print(hline("├", "┼", "┤"))
    for lbl, val in rows:
        print(row(lbl, val))
    print(hline("└", "┴", "┘"))


def print_yearly(ls_returns, ic_series) -> None:
    import pandas as pd
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


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start",         default="2016-01-01")
    ap.add_argument("--end",           default="2024-12-31")
    ap.add_argument("--universe-size",  type=int,   default=200)
    ap.add_argument("--n-quantile",     type=int,   default=5)
    ap.add_argument("--commission-bps", type=float, default=1.5,
                    help="위탁수수료 편도 (기본 1.5bp, 키움증권 기준)")
    ap.add_argument("--slippage-bps",   type=float, default=3.0,
                    help="슬리피지 편도 (기본 3bp, KOSPI 대형주 기준)")
    ap.add_argument("--no-cache",       action="store_true")
    ap.add_argument("--out",           default=str(_HERE / "results"))
    ap.add_argument("--cache",         default=str(_HERE / ".cache"))
    args = ap.parse_args()

    t0 = time.time()

    params = Params(
        start          = args.start,
        end            = args.end,
        universe_size  = args.universe_size,
        n_quantile     = args.n_quantile,
        commission_bps = args.commission_bps,
        slippage_bps   = args.slippage_bps,
    )

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    cache_dir = None if args.no_cache else args.cache

    # ── 1. 데이터 로딩 ───────────────────────────────────────────────────────
    print(f"\n[1/4] 데이터 로딩 ({params.start} ~ {params.end})")
    dataset = load_dataset(params, cache_dir=cache_dir or str(_HERE / ".cache"))

    print(f"      가격 데이터: {dataset.prices.shape[0]}개월 × {dataset.prices.shape[1]}개 종목")

    # ── 2. 백테스트 실행 ─────────────────────────────────────────────────────
    print("\n[2/4] 백테스트 실행 중...")
    result = run_backtest(dataset, params)

    n_months = len(result.ls_returns)
    print(f"      완료 — 총 {n_months}개월 수익률 산출")

    # ── 3. 성과 지표 계산 ────────────────────────────────────────────────────
    print("\n[3/4] 성과 지표 계산 중...")
    ic_series = compute_ic(result.factor_scores, result.fwd_returns)
    metrics   = compute_metrics(result.ls_returns, ic_series)

    print_metrics(metrics)
    print_yearly(result.ls_returns, ic_series)

    avg_to = result.turnover_series.mean()

    from factorlib.config import TAX_BY_YEAR, TAX_DEFAULT
    import numpy as np
    years = range(int(params.start[:4]), int(params.end[:4]) + 1)
    avg_tax = float(np.mean([TAX_BY_YEAR.get(y, TAX_DEFAULT) for y in years]))
    round_trip_bps = (params.commission_bps + params.slippage_bps) * 2 + avg_tax

    print(f"\n  ┌─ 거래비용 내역 (편도 기준) ──────────────────────────")
    print(f"  │  위탁수수료   : {params.commission_bps:.1f} bp")
    print(f"  │  슬리피지     : {params.slippage_bps:.1f} bp")
    print(f"  │  증권거래세   : {avg_tax:.1f} bp (매도, 기간 평균)")
    print(f"  │  왕복 합계    : {round_trip_bps:.1f} bp")
    print(f"  └──────────────────────────────────────────────────")
    print(f"  평균 월별 회전율 (편도): {avg_to:.1%}")
    print(f"  월평균 비용 드래그     : {avg_to * round_trip_bps / 100:.2f} %")

    # ── 4. 시각화 저장 ───────────────────────────────────────────────────────
    print(f"\n[4/4] 차트 저장 중... → {out_dir}")
    plot_quantile_bar(result.quantile_returns, out_dir)
    plot_ls_equity(result.ls_returns, out_dir)
    plot_ic_series(ic_series, out_dir)
    plot_quantile_equity(result.quantile_returns, result.ls_returns, out_dir)
    plot_yearly_heatmap(result.ls_returns, out_dir)

    print(f"\n실행 완료: {time.time() - t0:.0f}초 | 결과 폴더: {out_dir.absolute()}")


if __name__ == "__main__":
    main()
