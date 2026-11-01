from dataclasses import dataclass


# ── 연도별 증권거래세 (KOSPI 매도, 농어촌특별세 포함) ────────────────────────────
# 2016~2022: 0.23%  /  2023: 0.20%  /  2024: 0.18%  /  2025~: 0.15%
TAX_BY_YEAR: dict[int, float] = {
    2016: 23.0, 2017: 23.0, 2018: 23.0, 2019: 23.0,
    2020: 23.0, 2021: 23.0, 2022: 23.0,
    2023: 20.0,
    2024: 18.0,
    2025: 15.0,
}
TAX_DEFAULT: float = 15.0   # 위 딕셔너리에 없는 연도 fallback


@dataclass
class Params:
    # ── Factor ─────────────────────────────────────────────
    lookback_long: int = 12   # 12개월 누적 수익률
    lookback_skip: int = 1    # 최근 1개월 제외 (단기 반전 회피)

    # ── Universe ────────────────────────────────────────────
    universe_size: int   = 200    # 시가총액 상위 N개 종목
    min_price:     float = 500.0  # 동전주 제외 최소 주가

    # ── Portfolio ───────────────────────────────────────────
    n_quantile: int = 5   # 분위수 개수 (Q1 ~ Q5)

    # ── Transaction cost ────────────────────────────────────
    # 키움증권 온라인 기준 편도 1.5bp, KOSPI 대형주 슬리피지 3bp
    # 증권거래세는 TAX_BY_YEAR에서 연도별 자동 적용 (매도 시만 부과)
    commission_bps: float = 1.5   # 위탁수수료 (편도)
    slippage_bps:   float = 3.0   # 슬리피지 bid-ask + 시장충격 (편도)

    # ── Backtest period ─────────────────────────────────────
    start: str = "2016-01-01"
    end:   str = "2024-12-31"
