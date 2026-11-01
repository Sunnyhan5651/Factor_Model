from dataclasses import dataclass

KRX_API_KEY: str = "0684D9C39E7D4B0787BDE4FE549362524A028264"
KRX_API_BASE: str = "https://data-dbg.krx.co.kr/svc/apis"

TAX_BY_YEAR: dict[int, float] = {
    2016: 23.0, 2017: 23.0, 2018: 23.0, 2019: 23.0,
    2020: 23.0, 2021: 23.0, 2022: 23.0,
    2023: 20.0, 2024: 18.0, 2025: 15.0,
}
TAX_DEFAULT: float = 15.0

@dataclass
class Params:
    lookback_long: int = 12   # 12개월 누적 수익률 (12-1 모멘텀)
    lookback_skip: int = 1
    universe_size: int = 200
    min_price: float = 500.0
    n_quantile: int = 5
    commission_bps: float = 1.5
    slippage_bps: float = 3.0
    start: str = "2016-01-01"
    end: str = "2024-12-31"
