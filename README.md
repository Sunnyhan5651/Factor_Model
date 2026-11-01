# Factor Model — 12-1 Momentum Backtest

KOSPI 시가총액 상위 200개 종목을 유니버스로 **12-1 Momentum 팩터**를 재현하고 백테스트한 프로젝트입니다.

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
| **팩터** | 12-1 Momentum (12개월 누적 수익률, 최근 1개월 제외) |
| **유니버스** | KOSPI 시가총액 상위 200개 (월별 동적 구성) |
| **백테스트 기간** | 2016-01-01 ~ 2024-12-31 (기본값) |
| **리밸런싱** | 월말 |
| **포트폴리오** | 5분위 Long-Short (Q5 Long / Q1 Short, Equal-weight) |
| **거래비용** | 수수료 1.5bp + 슬리피지 3bp (편도) + 증권거래세 연도별 자동 적용 |
| **데이터 소스** | pykrx (KRX 정보데이터시스템) |

---

## 2. 팩터 정의 — 12-1 Momentum

Jegadeesh & Titman (1993)에서 제시된 모멘텀 팩터를 한국 주식시장에 적용합니다.

```
Momentum(t) = Price(t-1) / Price(t-13) - 1
```

- `Price(t-1)` : 한 달 전 종가 (단기 반전 효과 제거를 위한 skip)
- `Price(t-13)` : 13달 전 종가
- 결과적으로 **최근 2~13개월 구간** 의 누적 수익률을 팩터로 사용

### 직관

> 최근 1년간 상승한 종목은 향후에도 계속 상승하는 경향이 있다.  
> (단, 가장 최근 1개월은 단기 반전 효과로 제외)

### 정규화

팩터 점수는 **크로스섹션 z-score** 로 정규화:

```
z(t, i) = (factor(t, i) - mean_cross(t)) / std_cross(t)
```

상하위 1% 극단값은 winsorization으로 처리합니다.

---

## 3. 데이터 및 유니버스

### 데이터 소스

- **pykrx** 라이브러리를 통해 KRX 정보데이터시스템에서 수집
- 월말 영업일 기준 전체 KOSPI 종목의 종가 및 시가총액
- 1회 수집 후 `.cache/` 폴더에 parquet 형식으로 캐싱

### 유니버스 구성 (월별 동적)

| 필터 | 기준 |
|------|------|
| 시장 | KOSPI |
| 시가총액 | 월말 기준 상위 200개 |
| 최소 주가 | 500원 이상 (동전주 제외) |

> **Survivorship Bias 완화**: 매 월말에 그 시점의 시가총액을 기준으로 유니버스를 재구성합니다.  
> 단, pykrx 특성상 상장폐지 종목의 완전한 포함은 어렵습니다.

### Look-ahead Bias 방지

- 유니버스 구성: 당일 시장 마감 후 확인 가능한 시가총액 사용 (당일 기준 → 허용)
- 팩터 계산: `t-1`, `t-13` 시점 가격만 사용
- 수익률 측정: `t → t+1` 월말 수익률 (팩터 계산 이후 구간)

---

## 4. 포트폴리오 구성

### 분위수 배분

팩터 점수를 기준으로 유니버스를 5분위로 나눕니다:

| 분위 | 범위 | 포지션 |
|------|------|--------|
| Q5 | 상위 20% (모멘텀 강) | **Long** |
| Q4 | 상위 20~40% | 관찰 |
| Q3 | 중간 20% | 관찰 |
| Q2 | 하위 20~40% | 관찰 |
| Q1 | 하위 20% (모멘텀 약) | **Short** |

### Long-Short 수익률

```
LS_return(t) = (Q5_return(t) - Q1_return(t)) / 2 - (cost_long + cost_short) / 2
```

레버리지 중립화를 위해 수익률과 거래비용 모두 2로 나눕니다.

### 비중 방식

- **Equal-weight**: 분위수 내 모든 종목에 동일 비중 적용
- 매월 리밸런싱 시 회전율(turnover) 계산 후 거래비용 반영

---

## 5. 백테스트 방법론

### 실행 흐름

```
데이터 수집 (pykrx)
    ↓
월별 크로스섹션 팩터 계산
    ├── 12-1 모멘텀 계산
    ├── Winsorization (상하위 1%)
    └── Z-score 정규화
    ↓
분위수 포트폴리오 구성
    ├── Q1 ~ Q5 equal-weight
    └── 유니버스 = 시가총액 상위 200
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

```
왕복 합계 예시 (2024년 기준):
  수수료 3.0bp + 슬리피지 6.0bp + 세금 18bp = 27bp
```

> turnover = 0.5 × Σ|w_new − w_old|  (편도 기준)

---

## 6. 코드 구조

```
단일팩터모델/
├── run_backtest.py          # 메인 실행 스크립트
├── requirements.txt
├── .gitignore
└── src/
    └── factorlib/
        ├── __init__.py
        ├── config.py        # 파라미터 (Params dataclass)
        ├── data.py          # pykrx 데이터 수집 / 캐싱 / 유니버스
        ├── factors.py       # 팩터 계산 (모멘텀, z-score, winsorize)
        ├── portfolio.py     # 분위수 배분, 비중, 회전율
        ├── engine.py        # 백테스트 엔진 (월별 루프)
        ├── metrics.py       # 성과 지표 (Sharpe, MDD, IC, NW t-stat)
        └── plots.py         # 시각화 (5개 차트)
```

### 모듈별 역할

| 모듈 | 주요 함수 | 설명 |
|------|----------|------|
| `config.py` | `Params` | 전체 파라미터 관리 dataclass |
| `data.py` | `load_dataset()` | pykrx 크로스섹션 수집, parquet 캐싱 |
| `factors.py` | `compute_momentum()` | 12-1 모멘텀, z-score, winsorize |
| `portfolio.py` | `assign_quantiles()` | qcut 기반 분위수, equal-weight 비중 |
| `engine.py` | `run_backtest()` | 월별 리밸런싱 루프, 거래비용 처리 |
| `metrics.py` | `compute_metrics()` | Sharpe, MDD, IC/ICIR, Newey-West |
| `plots.py` | `plot_*()` | matplotlib 차트 5종 저장 |

---

## 7. 실행 방법

### 설치

```bash
pip install -r requirements.txt
```

### 기본 실행

```bash
python run_backtest.py
```

### 옵션 지정

```bash
# 분석 기간 변경
python run_backtest.py --start 2018-01-01 --end 2023-12-31

# 유니버스 크기 조정
python run_backtest.py --universe-size 100

# 캐시 무시하고 재수집
python run_backtest.py --no-cache

# 거래비용 직접 지정
python run_backtest.py --commission-bps 2.0 --slippage-bps 5.0
```

### 출력 결과

```
results/
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
| **Survivorship Bias** | 상장폐지 종목이 유니버스에서 일부 누락 |
| **Equal-weight** | 시가총액 가중치 미적용 (소형주 과대 노출 가능) |
| **단일 팩터** | 섹터 효과, 시가총액 효과 미중립화 |
| **거래비용 단순화** | 대형주 균일 슬리피지 가정, AUM 규모별 시장충격비용 미반영 |
| **공매도 제약** | Q1 Short이 실제로는 어려울 수 있음 |

### 개선 방향

- [ ] 섹터 중립화 (Sector-neutral Momentum)
- [ ] 시가총액 가중 포트폴리오 (Value-weighted)
- [ ] 다중 팩터 합산 (Momentum + Value + Quality)
- [ ] Long-only 포트폴리오 버전 추가
- [ ] Fama-French 3/5 팩터 모델 대비 알파 분해

---

## References

- Jegadeesh, N., & Titman, S. (1993). *Returns to Buying Winners and Selling Losers*. Journal of Finance.
- Asness, C., Moskowitz, T., & Pedersen, L. (2013). *Value and Momentum Everywhere*. Journal of Finance.
- 김진우 외 (2020). *국내 주식시장의 모멘텀 팩터 분석*. 한국재무학회.

---

*pykrx 데이터 기반 | KOSPI 시가총액 상위 200 유니버스 | 월별 리밸런싱*
