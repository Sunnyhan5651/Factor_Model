"""월별 KOSPI 전종목 가격/시가총액 데이터 수집.

수집 전략 (기본: FDR):
  - 종목 리스트: FinanceDataReader StockListing('KOSPI')
  - 종목별 일별 종가 → 월말 리샘플: FinanceDataReader DataReader
  - 시가총액 근사: 월말 종가 × 현재 발행주식수

주의:
  - 현재 상장 종목만 제공 → 상장폐지 종목 미포함 (생존 편향)
  - 발행주식수는 현재 기준 고정값 → 근사치

캐싱: parquet 저장 → 재실행 시 즉시 로딩.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import FinanceDataReader as fdr

from .config import Params


@dataclass
class FactorDataset:
    prices:      pd.DataFrame   # date × ticker (월말 종가)
    market_caps: pd.DataFrame   # date × ticker (시가총액 근사)


# ── 월말 날짜 생성 ─────────────────────────────────────────────────────────────

def _month_end_dates(start: str, end: str) -> pd.DatetimeIndex:
    """영업일 기준 월말 날짜 인덱스 (pandas 버전 호환)."""
    for freq in ("BME", "BM"):
        try:
            idx = pd.date_range(start, end, freq=freq)
            if len(idx) > 0:
                return idx
        except Exception:
            continue
    return pd.date_range(start, end, freq="ME")


# ── 월말 리샘플 헬퍼 ──────────────────────────────────────────────────────────

def _to_monthly(series: pd.Series) -> pd.Series:
    """일별 시리즈 → 영업일 기준 월말 리샘플 (pandas 버전 호환)."""
    series.index = pd.to_datetime(series.index)
    for freq in ("BME", "BM", "ME", "M"):
        try:
            result = series.resample(freq).last().dropna()
            if len(result) > 0:
                return result
        except Exception:
            continue
    return series.groupby(pd.Grouper(freq="ME")).last().dropna()


# ── KOSPI 전종목 리스트 ───────────────────────────────────────────────────────

def _get_kospi_listing() -> pd.DataFrame:
    """FDR StockListing으로 현재 KOSPI 전종목 조회."""
    listing = fdr.StockListing("KOSPI")[["Code", "Name", "Marcap", "Stocks"]]
    listing = listing.dropna(subset=["Marcap", "Stocks"])
    listing = listing[listing["Marcap"] > 0]
    return listing.reset_index(drop=True)


# ── 종목별 월말 가격 수집 ─────────────────────────────────────────────────────

def _fetch_monthly_prices(tickers: list[str],
                          start: str, end: str) -> pd.DataFrame:
    """FDR DataReader로 종목별 일별 가격 수집 후 월말 리샘플."""
    n = len(tickers)
    monthly_dict: dict[str, pd.Series] = {}
    fail_count = 0

    for i, ticker in enumerate(tickers, 1):
        print(f"  [{i:4d}/{n}] {ticker}", end="\r")
        try:
            df = fdr.DataReader(ticker, start, end)
            if df is None or len(df) < 5:
                fail_count += 1
                continue
            monthly = _to_monthly(df["Close"])
            if len(monthly) > 0:
                monthly_dict[ticker] = monthly
            else:
                fail_count += 1
        except Exception:
            fail_count += 1
        time.sleep(0.05)

    print(f"\n      수집 성공: {len(monthly_dict)}개 / 실패: {fail_count}개")

    if not monthly_dict:
        return pd.DataFrame()

    price_df = pd.DataFrame(monthly_dict)
    price_df.index = pd.to_datetime(price_df.index)
    price_df.index.name = "date"
    price_df.sort_index(inplace=True)
    return price_df


# ── 메인 로더 ─────────────────────────────────────────────────────────────────

def load_dataset(params: Params, cache_dir: str = ".cache") -> FactorDataset:
    """
    KOSPI 전종목 월별 가격·시가총액 수집 후 FactorDataset 반환.
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
    print("[1/3] KOSPI 전종목 리스트 조회 중 (FDR)...")
    listing    = _get_kospi_listing()
    tickers    = listing["Code"].tolist()
    shares_map = listing.set_index("Code")["Stocks"].to_dict()
    print(f"      전체 {len(tickers)}개 종목")

    print(f"\n[2/3] 종목별 월별 가격 수집 중 (FDR, Naver Finance)...")
    print(f"      기간: {params.start} ~ {params.end}")
    prices = _fetch_monthly_prices(tickers, params.start, params.end)

    if prices.empty:
        raise RuntimeError(
            "가격 데이터 수집 실패. 네트워크 연결 및 FDR 설치 상태를 확인하세요.\n"
            "  pip install finance-datareader --upgrade"
        )

    prices = prices.loc[params.start:params.end]
    prices.replace(0, float("nan"), inplace=True)

    print(f"\n[3/3] 시가총액 근사값 계산 중...")
    shares_series = pd.Series(shares_map).reindex(prices.columns).fillna(0)
    market_caps   = prices.mul(shares_series, axis=1)

    prices.to_parquet(price_cache)
    market_caps.to_parquet(cap_cache)
    print(f"\n[완료] {prices.shape[0]}개월 × {prices.shape[1]}개 종목, 캐시 저장 ({cache_dir})")

    return FactorDataset(prices=prices, market_caps=market_caps)


# ── 유니버스 추출 ─────────────────────────────────────────────────────────────

def get_universe(market_caps: pd.DataFrame, date: pd.Timestamp,
                 size: int, min_price: float,
                 prices: pd.DataFrame) -> list[str]:
    """특정 날짜 기준 시가총액 상위 size개 종목. 동전주(min_price 미만) 제외."""
    if date not in market_caps.index:
        return []
    caps   = market_caps.loc[date].dropna()
    closes = prices.loc[date].dropna() if date in prices.index else pd.Series(dtype=float)
    valid  = closes[closes >= min_price].index
    caps   = caps[caps.index.isin(valid)]
    return caps.nlargest(size).index.tolist()
