"""월별 KOSPI 가격/시가총액 데이터 수집 (pykrx 기반).

수집 전략: 종목별 루프 대신 날짜별 전체 크로스섹션 조회 (1 call/month).
캐싱: parquet으로 저장 → 재실행 시 즉시 로딩.
"""
from __future__ import annotations

import time
import pickle
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from pykrx import stock

from .config import Params


@dataclass
class FactorDataset:
    prices:      pd.DataFrame   # date × ticker (월말 수정종가)
    market_caps: pd.DataFrame   # date × ticker (시가총액)


# ── 월말 영업일 계산 ──────────────────────────────────────────────────────────

def _month_end_dates(start: str, end: str) -> list[str]:
    """YYYYMMDD 형식 월말 날짜 리스트."""
    idx = pd.date_range(start, end, freq="BME")   # Business Month End
    return [d.strftime("%Y%m%d") for d in idx]


# ── pykrx 크로스섹션 수집 ─────────────────────────────────────────────────────

def _fetch_cross_section(date_str: str) -> tuple[pd.Series, pd.Series]:
    """
    특정 날짜의 전체 KOSPI 종가 및 시가총액을 반환.
    Returns: (close_series, cap_series) indexed by ticker code
    """
    try:
        ohlcv = stock.get_market_ohlcv_by_ticker(date_str, market="KOSPI")
        cap   = stock.get_market_cap_by_ticker(date_str, market="KOSPI")

        close = ohlcv["종가"].rename(date_str)
        mktcap = cap["시가총액"].rename(date_str)
        return close, mktcap
    except Exception as e:
        print(f"  [skip] {date_str}: {e}")
        return pd.Series(name=date_str, dtype=float), pd.Series(name=date_str, dtype=float)


# ── 메인 로더 ─────────────────────────────────────────────────────────────────

def load_dataset(params: Params, cache_dir: str = ".cache") -> FactorDataset:
    """
    pykrx로 월별 KOSPI 전종목 가격·시가총액 수집 후 FactorDataset 반환.
    cache_dir에 parquet 캐시가 있으면 즉시 반환.
    """
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)

    price_cache = cache_path / "prices.parquet"
    cap_cache   = cache_path / "market_caps.parquet"

    # ── 캐시 히트 ──────────────────────────────────────────
    if price_cache.exists() and cap_cache.exists():
        print("[캐시] 로컬 캐시에서 데이터 로딩...")
        prices      = pd.read_parquet(price_cache)
        market_caps = pd.read_parquet(cap_cache)
        # 요청 기간이 캐시 범위 내에 있으면 슬라이싱 후 반환
        start_dt = pd.to_datetime(params.start)
        end_dt   = pd.to_datetime(params.end)
        prices      = prices[(prices.index >= start_dt) & (prices.index <= end_dt)]
        market_caps = market_caps[(market_caps.index >= start_dt) & (market_caps.index <= end_dt)]
        print(f"[캐시] {len(prices)}개월 데이터 로딩 완료")
        return FactorDataset(prices=prices, market_caps=market_caps)

    # ── 신규 수집 ──────────────────────────────────────────
    dates = _month_end_dates(params.start, params.end)
    print(f"[수집] {params.start} ~ {params.end}, {len(dates)}개 월말 날짜")

    price_rows:  list[pd.Series] = []
    cap_rows:    list[pd.Series] = []

    for i, d in enumerate(dates, 1):
        print(f"  [{i:3d}/{len(dates)}] {d}", end="\r")
        close, mktcap = _fetch_cross_section(d)
        price_rows.append(close)
        cap_rows.append(mktcap)
        time.sleep(0.3)   # pykrx rate limit 방지

    print()

    prices      = pd.DataFrame(price_rows)
    market_caps = pd.DataFrame(cap_rows)

    # 인덱스를 datetime으로 변환
    prices.index      = pd.to_datetime(prices.index, format="%Y%m%d")
    market_caps.index = pd.to_datetime(market_caps.index, format="%Y%m%d")

    prices.sort_index(inplace=True)
    market_caps.sort_index(inplace=True)

    # 0이거나 None인 값 → NaN 처리
    prices.replace(0, float("nan"), inplace=True)
    market_caps.replace(0, float("nan"), inplace=True)

    # 캐시 저장
    prices.to_parquet(price_cache)
    market_caps.to_parquet(cap_cache)
    print(f"[완료] {len(prices)}개월 × {prices.shape[1]}개 종목 수집 완료, 캐시 저장")

    return FactorDataset(prices=prices, market_caps=market_caps)


# ── 유니버스 추출 ─────────────────────────────────────────────────────────────

def get_universe(market_caps: pd.DataFrame, date: pd.Timestamp,
                 size: int, min_price: float,
                 prices: pd.DataFrame) -> list[str]:
    """
    특정 날짜 기준 시가총액 상위 size개 종목 반환.
    주가 min_price 미만 종목 제외 (동전주 필터).
    """
    if date not in market_caps.index:
        return []

    caps   = market_caps.loc[date].dropna()
    closes = prices.loc[date].dropna() if date in prices.index else pd.Series(dtype=float)

    # 동전주 제외
    valid_tickers = closes[closes >= min_price].index
    caps = caps[caps.index.isin(valid_tickers)]

    top = caps.nlargest(size).index.tolist()
    return top
