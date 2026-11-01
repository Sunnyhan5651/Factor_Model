from dataclasses import dataclass


@dataclass
class Params:
    # ── Factor ─────────────────────────────────────────────
    lookback_long: int = 12   # 12개월 누적 수익률
    lookback_skip: int = 1    # 최근 1개월 제외 (단기 반전 회피)

    # ── Universe ────────────────────────────────────────────
    universe_size: int = 200  # 시가총액 상위 N개 종목
    min_price: float = 500.0  # 동전주 제외 최소 주가

    # ── Portfolio ───────────────────────────────────────────
    n_quantile: int = 5       # 분위수 개수 (Q1 ~ Q5)

    # ── Transaction cost ────────────────────────────────────
    cost_bps: float = 10.0    # 편도 거래비용 (bps)

    # ── Backtest period ─────────────────────────────────────
    start: str = "2016-01-01"
    end: str   = "2024-12-31"
