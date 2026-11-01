# Factor Model — 12-1 Momentum Backtest

KOSPI 시가총액 상위 종목을 유니버스로 **12-1 Momentum 팩터**를 구현하고 백테스트한 프로젝트입니다.  
KOSPI 데이터(FDR)와 외부 CSV 데이터 두 가지 입력을 모두 지원합니다.

---

## 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [팩터 정의](#2-팩터-정의--12-1-momentum)
3. [데이터 및 유니버스](#3-데이터-및-유니버스)
4. [포트폴리오 구성](#4-포트폴리오-구성)
5. [백테스트 방법론](#5-백테스트-방법론)
6. [코드 구조](#6-코드-구조)
7. [실행 방법](#7-실행-방법)
8. [성과 지표](#8-성과-지표)
9. [한계 및 개선 방향](#9-한계-및-개선-방향)

---

## 1. 프로젝트 개요

| 항목 | 내용 |
|------|------|
| **팩터** | 12-1 Momentum (직전 12개월 월별 수익률 평균, 최근 1개월 제외) |
| **유니버스** | KOSPI 시가총액 상위 200개, 500원 미만 동전주 제외 (월별 동적 구성) |
| **백테스트 기간** | 2016-01-01 ~ 2024-12-31 (기본값) |
| **리밸런싱** | 월말 |
| **포트폴리오** | 5분위 Long-Short (Q5 Long / Q1 Short, Equal-weight) |
| **거래비용** | 수수료 1.5bp + 슬리피지 3bp (편도) + 증권거래세 연도별 자동 적용 |
| **데이터 소스** | FinanceDataReader (FDR, Naver Finance 백엔드) |

---

## 2. 팩터 정의 — 12-1 Momentum

Jegadeesh & Titman (1993)에서 제시된 모멘텀 팩터를 한국 주식시장에 적용합니다.

### 팩터 공식

```
monthly_ret[t] = Price[t] / Price[t-1] - 1

Momentum[t] = mean( monthly_ret[t-1], monthly_ret[t-2], ..., monthly_ret[t-12] )
```

- 최근 1개월(`t`)을 skip하여 단기 반전 효과를 제거합니다.
- 직전 12개월 월별 수익률의 **산술 평균**을 팩터로 사용합니다 (포인트-투-포인트 대비 단일 월 이상치에 덜 민감).

### 정규화

```
1. Winsorization: 날짜별 크로스섹션 상하위 1% 극단값 클리핑
2. Z-score:       z(t, i) = (factor(t, i) - mean_t) / std_t
```

유효 종목 수가 20개 미만인 날짜는 전체 NaN 처리합니다.

---

## 3. 데이터 및 유니버스

### 데이터 소스

- **FinanceDataReader (FDR)** — KOSPI 종목별 일별 종가 수집 후 월말 영업일 기준 리샘플
- 시가총액 근사: 월말 종가 × 현재 발행주식수
- 수집 후 `.cache/` 폴더에 parquet 형식으로 캐싱

### 유니버스 구성 (월별 동적)

| 필터 | 기준 |
|------|------|
| 시장 | KOSPI |
| 시가총액 | 월말 기준 상위 200개 |
| 최소 주가 | 500원 이상 (동전주 제외) |

> **Survivorship Bias**: FDR 특성상 현재 상장 종목만 포함 — 상장폐지 종목 미포함.  
> **Look-ahead Bias 방지**: 팩터 계산에 `t-1` ~ `t-12` 수익률만 사용. 수익률 측정은 `t → t+1` 구간.

---

## 4. 포트폴리오 구성

### 분위수 배분

팩터 점수를 기준으로 유니버스를 5분위로 나눕니다:

| 분위 | 범위 | 포지션 |
|------|------|--------|
| Q5 | 상위 20% (모멘텀 강) | **Long** |
| Q4 ~ Q2 | 중간 60% | 미보유 |
| Q1 | 하위 20% (모멘텀 약) | **Short** |

### Long-Short 수익률

```
LS_return(t) = (Q5_return(t) - Q1_return(t)) / 2 - (cost_long + cost_short) / 2
```

레버리지 중립화를 위해 수익률과 거래비용 모두 2로 나눕니다.

---

## 5. 백테스트 방법론

### 실행 흐름

```
데이터 수집 (FDR)
    ├── 종목별 월말 종가
    └── 시가총액 근사 (종가 × 발행주식수)
    ↓
월별 크로스섹션 팩터 계산
    ├── 12-1 모멘텀 (롤링 평균)
    ├── Winsorization (상하위 1%)
    └── Z-score 정규화
    ↓
유니버스 필터링
    ├── 시가총액 상위 200개
    └── 500원 이상 (동전주 제거)
    ↓
1개월 보유 수익률 측정
    ├── 거래비용 차감
    └── Long-Short 합산
    ↓
성과 분석
    ├── Sharpe, MDD, Calmar
    ├── IC / ICIR (팩터 예측력)
    ├── Newey-West t통계량
    └── 연도별 분해
```

### 거래비용 모델

편도 회전율(turnover) 1단위 발생 시 매수와 매도가 동시에 일어납니다.

```
매수 비용 = (수수료 + 슬리피지) / 10,000
매도 비용 = (수수료 + 슬리피지 + 증권거래세) / 10,000

round_trip_cost = turnover × (매수 비용 + 매도 비용)
ls_return       = (long_ret - short_ret) / 2 − (cost_long + cost_short) / 2
```

| 비용 항목 | 값 | 적용 방향 |
|----------|-----|---------|
| 위탁수수료 (키움증권) | 1.5bp | 매수 + 매도 |
| 슬리피지 (KOSPI 대형주) | 3.0bp | 매수 + 매도 |
| 증권거래세 | 연도별 자동 | 매도만 |

**증권거래세 연도별 세율 (KOSPI, 농어촌특별세 포함)**

| 기간 | 세율 |
|------|------|
| 2016 ~ 2022 | 23bp |
| 2023 | 20bp |
| 2024 | 18bp |
| 2025 ~ | 15bp |

> turnover = 0.5 × Σ|w_new − w_old|  (편도 기준)

---

## 6. 코드 구조

```
단일팩터모델/
├── run_backtest.py          # KOSPI 백테스트 실행 스크립트 (CLI)
├── run_backtest_csv.py      # 외부 CSV 데이터 백테스트 실행 스크립트
├── requirements.txt
└── src/
    └── factorlib/
        ├── config.py        # 파라미터 (Params dataclass)
        ├── data.py          # FDR 데이터 수집 / 캐싱 / 유니버스
        ├── factors.py       # 팩터 계산 (모멘텀, winsorize, z-score)
        ├── portfolio.py     # 분위수 배분, 비중, 회전율
        ├── engine.py        # 백테스트 엔진 (월별 루프, 거래비용)
        ├── metrics.py       # 성과 지표 (Sharpe, MDD, IC, NW t-stat)
        └── plots.py         # 시각화 (5개 차트)
```

### 모듈별 역할

| 모듈 | 주요 함수/클래스 | 설명 |
|------|----------|------|
| `config.py` | `Params` | 전체 파라미터 관리 dataclass |
| `data.py` | `load_dataset()`, `FactorDataset` | FDR 수집, parquet 캐싱 |
| `factors.py` | `compute_momentum()`, `zscore_cross_section()`, `winsorize()` | 12-1 모멘텀, 정규화 |
| `portfolio.py` | `assign_quantiles()`, `build_weights()`, `compute_turnover()` | qcut 분위수, equal-weight, 회전율 |
| `engine.py` | `run_backtest()` | 월별 리밸런싱 루프, 거래비용 처리 |
| `metrics.py` | `compute_metrics()` | Sharpe, MDD, IC/ICIR, Newey-West |
| `plots.py` | `plot_*()` | matplotlib 차트 5종 저장 |

### 주요 데이터 구조

```python
@dataclass
class FactorDataset:
    prices:      pd.DataFrame   # date × ticker (월말 종가)
    market_caps: pd.DataFrame   # date × ticker (시가총액 근사)

@dataclass
class Params:
    lookback_long:  int   = 12     # 모멘텀 형성 기간 (개월)
    lookback_skip:  int   = 1      # 단기 반전 제거용 skip (개월)
    universe_size:  int   = 200    # 유니버스 종목 수
    min_price:      float = 500.0  # 최소 주가 (동전주 제외)
    n_quantile:     int   = 5      # 분위수
    commission_bps: float = 1.5    # 수수료 편도 (bp)
    slippage_bps:   float = 3.0    # 슬리피지 편도 (bp)
    start:          str   = "2016-01-01"
    end:            str   = "2024-12-31"
```

---

## 7. 실행 방법

### 설치

```bash
pip install -r requirements.txt
```

### KOSPI 백테스트

```bash
# 기본 실행
python run_backtest.py

# 분석 기간 변경
python run_backtest.py --start 2018-01-01 --end 2023-12-31

# 유니버스 크기 조정
python run_backtest.py --universe-size 100

# 캐시 무시하고 재수집
python run_backtest.py --no-cache

# 거래비용 직접 지정
python run_backtest.py --commission-bps 2.0 --slippage-bps 5.0
```

### 외부 CSV 백테스트 (CRSP 포맷)

`PERMNO, date, EXCHCD, TICKER, COMNAM, ADJ_PRC, VOL` 컬럼을 포함한 월말 데이터를 지원합니다.  
시가총액 대리변수로 `가격 × 거래량`(달러 거래대금)을 사용합니다.

```bash
# 기본 실행 (NYSE+AMEX+NASDAQ, 상위 500개)
python run_backtest_csv.py

# CSV 경로 지정
python run_backtest_csv.py --csv /path/to/data.csv

# 거래소 필터 지정 (1=NYSE, 2=AMEX, 3=NASDAQ)
python run_backtest_csv.py --exchcd 1 3

# 유니버스 크기 조정
python run_backtest_csv.py --universe-size 300
```

### 캐시 구조 (KOSPI)

```
.cache/
├── prices.parquet       # 종목별 월말 종가 (전체 기간)
└── market_caps.parquet  # 종목별 월말 시가총액
```

최초 실행 시 FDR로 수집 후 캐싱. 이후 실행에서는 캐시를 즉시 로드합니다.

### 출력 결과

```
results/              ← KOSPI 백테스트 결과
results_csv/          ← CSV 백테스트 결과
    ├── 01_quantile_bar.png      # 분위수별 연환산 수익률 바차트
    ├── 02_ls_equity.png         # Long-Short 누적 손익 곡선
    ├── 03_ic_series.png         # IC 시계열 (월별 + 12M 이동평균)
    ├── 04_quantile_equity.png   # Q1~Q5 + LS 누적 수익률
    └── 05_yearly_heatmap.png    # 연도별 월간 수익률 히트맵
```

---

## 8. 성과 지표

### 팩터 평가 지표

| 지표 | 설명 | 해석 기준 |
|------|------|----------|
| **IC (Spearman)** | 팩터 점수 ↔ 다음 달 수익률 순위 상관 | \|IC\| > 0.05 → 유의미 |
| **ICIR** | IC 평균 / IC 표준편차 | > 0.5 → 안정적 팩터 |
| **IC > 0 비율** | 양의 IC가 나온 비율 | > 55% → 일관성 있음 |

### 포트폴리오 평가 지표

| 지표 | 설명 |
|------|------|
| **Sharpe Ratio** | 위험조정 수익률 (연환산) |
| **MDD** | 최대 낙폭 |
| **Calmar** | 연환산 수익률 / \|MDD\| |
| **Newey-West t** | 자기상관 보정 t통계량 (\|t\| > 2 → 유의수준 5%) |

---

## 9. 한계 및 개선 방향

### 현재 한계

| 한계 | 내용 |
|------|------|
| **Survivorship Bias** | 상장폐지 종목이 유니버스에서 누락 |
| **시가총액 근사** | 발행주식수가 현재 기준 고정값 → 과거 시점 근사치 |
| **Equal-weight** | 시가총액 가중치 미적용 |
| **거래비용 단순화** | AUM 규모별 시장충격비용 미반영 |
| **공매도 제약** | Q1 Short이 실제로는 어려울 수 있음 |

### 추가 개선 방향

- [ ] 시가총액 가중 포트폴리오 (Value-weighted)
- [ ] 다중 팩터 합산 (Momentum + Value + Quality)
- [ ] Fama-French 3/5 팩터 모델 대비 알파 분해
- [ ] 생존 편향 제거 (상장폐지 종목 포함 데이터 사용)

---

## References

- Jegadeesh, N., & Titman, S. (1993). *Returns to Buying Winners and Selling Losers*. Journal of Finance.
- Asness, C., Moskowitz, T., & Pedersen, L. (2013). *Value and Momentum Everywhere*. Journal of Finance.
- Daniel, K., & Moskowitz, T. (2016). *Momentum Crashes*. Journal of Financial Economics.
- 감형규, 신용재 (2011). *모멘텀 효과를 이용한 투자전략의 성과에 관한 연구*. 한국증권학회지.

---

*FinanceDataReader 기반 | KOSPI 시가총액 상위 200 유니버스 | 월별 리밸런싱*
