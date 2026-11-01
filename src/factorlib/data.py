"""월별 KOSPI 가격/시가총액 데이터 수집.

수집 전략:
  - 종목 리스트 + 현재 시가총액: FinanceDataReader StockListing
  - 종목별 일별 가격 → 월말 리샘플: pykrx get_market_ohlcv_by_date (Naver 백엔드)
  - 역사적 시가총액 근사: 월말 종가 × 현재 발행주식수

주의:
  - StockListing 은 현재 상장 종목만 제공 → 상장폐지 종목 미포함 (생존 편향)
  - 발행주식수는 현재 기준 고정값 → 유상증자/감자 이력 미반영 (근사치)

캐싱: parquet 저장 → 재실행 시 즉시 로딩.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import FinanceDataReader as fdr
from pykrx import stock

from .config import Params


@dataclass
class FactorDataset:
    prices:      pd.DataFrame   # date × ticker (월말 수정종가)
    market_caps: pd.DataFrame   # date × ticker (시가총액 근사)


# ── 월말 날짜 생성 ─────────────────────────────────────────────────────────────

def _month_end_dates(start: str, end: str) -> pd.DatetimeIndex:
    """영업일 기준 월말 날짜 인덱스 (Business Month End)."""
    return pd.date_range(start, end, freq="BME")


# ── KOSPI 종목 리스트 (FDR) ───────────────────────────────────────────────────

def _get_kospi_listing(universe_size: int) -> pd.DataFrame:
    """
    FDR StockListing으로 현재 KOSPI 전 종목 조회.
    시가총액 상위 universe_size * 2 개를 수집 대상으로 반환.
    컬럼: Code, Name, Marcap, Stocks
    """
    listing = fdr.StockListing("KOSPI")[["Code", "Name", "Marcap", "Stocks"]]
    listing = listing.dropna(subset=["Marcap", "Stocks"])
    listing = listing[listing["Marcap"] > 0]
    # 수집 버퍼: 상위 N의 2배 (월별 유니버스 변동 대응)
    top = listing.nlargest(universe_size * 2, "Marcap").reset_index(drop=True)
    return top


# ── 종목별 월말 가격 수집 (pykrx Naver 백엔드) ────────────────────────────────

def _fetch_monthly_prices(tickers: list[str],
                          start: str, end: str) -> pd.DataFrame:
    """
    pykrx get_market_ohlcv_by_date 로 종목별 일별 가격 수집 후
    영업일 기준 월말(BME)로 리샘플링.
    """
    start_str = start.replace("-", "")
    end_str   = end.replace("-", "")
    n = len(tickers)
    monthly_dict: dict[str, pd.Series] = {}

    for i, ticker in enumerate(tickers, 1):
        print(f"  [{i:3d}/{n}] {ticker}", end="\r")
        try:
            df = stock.get_market_ohlcv_by_date(start_str, end_str, ticker)
            if df is None or len(df) < 10:
                continue
            # 일별 → 월말 (영업일 기준 마지막 거래일 종가)
            monthly = df["종가"].resample("BME").last().dropna()
            if len(monthly) > 0:
                monthly_dict[ticker] = monthly
        except Exception:
            pass
        time.sleep(0.1)   # Naver rate limit 방지

    print()
    price_df = pd.DataFrame(monthly_dict)
    price_df.index.name = "date"
    return price_df


# ── 메인 로더 ─────────────────────────────────────────────────────────────────

def load_dataset(params: Params, cache_dir: str = ".cache") -> FactorDataset:
    """
    KOSPI 상위 종목 월별 가격·시가총액 수집 후 FactorDataset 반환.
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
        start_dt = pd.to_datetime(params.start)
        end_dt   = pd.to_datetime(params.end)
        prices      = prices.loc[start_dt:end_dt]
        market_caps = market_caps.loc[start_dt:end_dt]
        print(f"[캐시] {len(prices)}개월 × {prices.shape[1]}개 종목 로딩 완료")
        return FactorDataset(prices=prices, market_caps=market_caps)

    # ── 신규 수집 ──────────────────────────────────────────
    print("[1/3] KOSPI 종목 리스트 조회 중 (FDR)...")
    listing = _get_kospi_listing(params.universe_size)
    tickers      = listing["Code"].tolist()
    shares_map   = listing.set_index("Code")["Stocks"].to_dict()
    print(f"      수집 대상: {len(tickers)}개 종목")

    print(f"\n[2/3] 종목별 월별 가격 수집 중 (pykrx / Naver)...")
    print(f"      기간: {params.start} ~ {params.end}")
    prices = _fetch_monthly_prices(tickers, params.start, params.end)

    # 기간 필터 및 0 → NaN
    prices = prices.loc[params.start:params.end]
    prices.replace(0, float("nan"), inplace=True)

    print(f"\n[3/3] 시가총액 근사값 계산 중...")
    print(f"      (월별 종가 × 현재 발행주식수, 근사치)")
    shares_series = pd.Series(shares_map).reindex(prices.columns).fillna(0)
    market_caps   = prices.mul(shares_series, axis=1)

    # 캐시 저장
    prices.to_parquet(price_cache)
    market_caps.to_parquet(cap_cache)
    print(f"\n[완료] {prices.shape[0]}개월 × {prices.shape[1]}개 종목, 캐시 저장 ({cache_dir})")

    return FactorDataset(prices=prices, market_caps=market_caps)


# ── 유니버스 추출 ─────────────────────────────────────────────────────────────

def get_universe(market_caps: pd.DataFrame, date: pd.Timestamp,
                 size: int, min_price: float,
                 prices: pd.DataFrame) -> list[str]:
    """
    특정 날짜 기준 시가총액 상위 size개 종목 반환.
    주가 min_price 미만 동전주 제외.
    """
    if date not in market_caps.index:
        return []

    caps   = market_caps.loc[date].dropna()
    closes = prices.loc[date].dropna() if date in prices.index else pd.Series(dtype=float)

    valid = closes[closes >= min_price].index
    caps  = caps[caps.index.isin(valid)]

    return caps.nlargest(size).index.tolist()
