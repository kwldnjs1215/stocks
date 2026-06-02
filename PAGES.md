# PAGES.md — 사이드바 메뉴별 기능 & 로직 가이드

Claude가 작업할 때 참고하는 문서. 각 페이지가 어떤 API를 호출하고, 백엔드 어디서 어떤 로직을 거치는지 빠르게 찾기 위한 인덱스.

사이드바 순서는 [frontend/src/App.tsx:12-21](frontend/src/App.tsx#L12) 기준.

---

## 1. 대시보드 (`dashboard`)

- **프론트**: [frontend/src/pages/Dashboard.tsx](frontend/src/pages/Dashboard.tsx)
- **API**: `GET /api/dashboard`
- **백엔드 핸들러**: [api.py:1052 `get_dashboard()`](api.py#L1052)

### 데이터 흐름
1. `load_json_data()` — `data/portfolio_data.json` 로드 (섹션, 종목, rows_by_year, settings)
2. `calculate_current_principal(settings)` — 입출금/시작자본 합산으로 현재 투자원금 계산
3. 섹션마다(`미국주식`, `국내주식`) 처리:
   - `get_rows_for_year(section, current_year)` — 올해 월별/종목별 실현손익
   - `section_total()`, `section_month_total()` — 합산
   - `build_monthly()`, `build_stocks_monthly()` — 월별 누적 차트 데이터
   - USD 섹션은 `usd_to_krw_rate`로 원화 환산
4. `compute_manual_trade_analytics(sections_raw, usd_rate)` — 수동입력 트레이드 통계
5. `compute_yearly_principal_map(settings)` — 연도별 원금/델타로 수익률 계산 → `yearly_summary`
6. `load_asset_summary()` — `data/*종합잔고*.xls` HTML 파서로 평가금액 파싱

### 핵심 포인트
- **연도별 데이터**는 `rows_by_year[year][month][stock]` 구조에 저장됨 (legacy `rows`는 fallback)
- 화면의 "올해 성과"는 항상 현재년도 키, 과거 성과는 셀렉터로 선택
- 환율 변경되면 USD 섹션의 KRW 환산값이 다 다시 계산됨

---

## 2. 시황 (`market`)

- **프론트**: [frontend/src/pages/MarketOverview.tsx](frontend/src/pages/MarketOverview.tsx)
- **API**: `GET /api/market`, `POST /api/market/refresh`
- **백엔드 핸들러**: [api.py:1447](api.py#L1447), [api.py:1491](api.py#L1491)

### 데이터 흐름
1. **네이버 금융** HTML 스크래핑 (`finance.naver.com/sise/sise_group.naver?type=upjong`)
2. `BeautifulSoup`로 업종별 등락률 파싱 → `sectors` 리스트
3. 코스피/코스닥 지수 → `indices`
4. 등락별 분류(`rising` ≥+0.5%, `falling` ≤-0.5%, `flat`) → `summary.trend` 판정
5. 결과는 **30분 캐시** — `MARKET_CACHE` 모듈 전역
6. `/refresh`는 캐시 무시하고 강제 재호출

### 핵심 포인트
- 외부 사이트 의존 — 네이버 마크업 바뀌면 파서 깨질 수 있음
- 캐시는 메모리 기반이라 백엔드 재시작 시 초기화

---

## 3. 섹터 추이 (`trend`)

- **프론트**: [frontend/src/pages/SectorTrend.tsx](frontend/src/pages/SectorTrend.tsx)
- **API**: `GET /api/sector-trend`, `POST /api/sector-trend/refresh`
- **백엔드 핸들러**: [api.py:1622](api.py#L1622), [api.py:1641](api.py#L1641)

### 데이터 흐름
- `/api/market`과 비슷하나, 시간 흐름에 따른 섹터별 등락 히스토리를 누적
- 백엔드 캐시 + 누적 시리즈 형태로 반환

---

## 4. 종목 분석 (`research`)

- **프론트**: [frontend/src/pages/StockResearch.tsx](frontend/src/pages/StockResearch.tsx)
- **API**: `POST /api/stock-analysis`, `POST /api/stock-analysis/chat`
- **백엔드 핸들러**: [api.py:1214](api.py#L1214), [api.py:1224](api.py#L1224)
- **분석 엔진**: [stock_analysis.py](stock_analysis.py)

### 데이터 흐름
1. `resolve_symbol(query)` ([stock_analysis.py:113](stock_analysis.py#L113))
   - 작은 alias 테이블(`NAME_TO_SYMBOL`, 미국주 한글 별칭) 우선
   - 없으면 `_kr_name_index()`로 **KRX 전체 listing(FDR)** 에서 한글 이름 → 6자리 코드 자동 매핑 (lazy 캐시)
   - 그래도 없으면 raw.upper() → 미국 티커로 간주
2. `_kis_daily()` (한국투자 일봉 API) → 실패 시 `_fdr_daily()` (FinanceDataReader)로 폴백
3. `_kis_price()` — 현재가 (KIS API 토큰은 `.kis_token.json` 캐시)
4. 기술지표: `_sma(5/20/60)`, `_rsi(14)`, `_volume_profile()` → `_levels()` (중기 지지/저항)
5. `_kis_intraday_5m()` — 5분봉 → `_short_term_levels()` (단기 지지/저항)
   - 미국주: KIS 해외 5분봉 API 직접 호출
   - 국내주: KIS 국내 1분봉 API(`FHKST03010200`)를 페이지네이션으로 3회 호출(~90개) → `_resample_to_5m()`로 5분 OHLC 합산
6. `_pressure()` — 최근 20일 OBV 기반 매수/매도 압력
7. `_options()` — 옵션 데이터 (Yahoo는 crumb 인증 필요해서 모두 yfinance로 옮김)
   - 미국주: `yfinance` 옵션 체인 — 콜/풋 거래량/OI, P/C 비율, 맥스페인, ATM IV
   - 국내주: `_kis_kospi200_options()` — KIS `display_board_callput` (TR `FHPIF05030100`)로 KOSPI200 지수옵션 콜/풋 체인. P/C 거래량/미결제, 맥스페인, ATM 행사가/IV. "시장 전반 분위기"로 표시. 만기는 다음 둘째주 목요일 자동 선택
8. `_quote_summary()` — `yfinance.Ticker.info` (섹터/산업/회사 요약/시가총액/PER 등) + `calendar` (다음 실적일)
9. `_news_for_symbol()` — Google News RSS 기반 카테고리별 뉴스
   - direct: 종목명/티커 검색
   - sector: `_sector_keywords()`(LLM이 종목별 동향 키워드 4~6개 동적 생성, 예 NAND 가격/HBM 수요/메모리 capex)로 검색
   - peers: PEER_MAP의 관련주 종목명 검색
10. `_market_news()` — 미국(S&P/Nasdaq 키워드) + 국내(코스피/코스닥 키워드) 시황 뉴스
11. `_earnings_detail()` — 미국주 한정. `yfinance.earnings_history`로 분기별 예상/실제 EPS + surprise %, `calendar`로 다음 실적 컨센서스(EPS/매출 범위) + 발표일
12. `_peer_rows()` — `PEER_MAP`에 정의된 동종업계 5일 수익률
13. `_llm_strategy()` — Claude API 호출 (`ANTHROPIC_API_KEY` 환경변수 필요), 시나리오 메모 생성

### 핵심 포인트
- **종목명 매핑은 동적** — KRX 2878개 종목 어느 것이나 한글로 검색 가능 (`NAME_TO_SYMBOL`은 미국주 한글 alias 전용)
- KIS API 키(`MYAPP`, `MYSEC`)가 없으면 KIS 호출 전부 skip → FDR로 폴백
- LLM 메모는 API 키 없을 때 graceful degrade
- 챗: `/api/stock-analysis/chat`는 1번에서 만든 `analysis` dict를 그대로 넘겨서 컨텍스트 재활용

---

## 5. 자동매매 (`tradingBot`)

- **프론트**: [frontend/src/pages/TradingBot.tsx](frontend/src/pages/TradingBot.tsx)
- **API**: `/api/trading/status`, `/api/trading/config` (PATCH), `/api/trading/open-scan` (POST), `/api/trading/rules` (GET/POST), `/api/trading/journal` (GET), `/api/trading/reset-surge-scalping` (POST)
- **백엔드 핸들러**: [api.py:1347 ~ 1444](api.py#L1347)
- **엔진**: [trading_engine.py](trading_engine.py)

### 데이터 흐름
1. `trading_status()` ([trading_engine.py](trading_engine.py))
   - 현재 설정(`config`), KIS 연결 상태(`kis`), 최근 실행 결과(`latest_run`), 매매규칙(`rules`), 매매일지(`journal_*`)
2. `run_open_scan()` — 시초 스캔
   - 유니버스(`universe_top_n`) → 거래량/등락 필터 → 후보 점수화
   - 시그널: `BUY` / `WATCH`
   - 분할매수 plan(`buy_split_pct`), 분할매도 plan(`sell_split_pct`), 손절/익절/트레일링 stop 계산
   - `dry_run`이면 주문 안 보내고 plan만 기록
3. `should_run_open_scan()` — `open_scan_time` 도달 + `last_open_scan_date` 다름 시 자동 실행 (백엔드 lifespan에서 폴링)
4. `update_trading_config(patch)` — 부분 수정
5. `read_trading_rules()` / `write_trading_rules()` — `data/trading_rules.md` 같은 텍스트 파일 R/W
6. `read_trading_journal(date)` / `list_trading_journal_dates()` — `data/trading_journal/YYYY-MM-DD.md`

### 핵심 포인트
- **`enabled` + `dry_run` 조합으로 안전장치 이중화** — `live_orders_enabled` (KIS 계좌 설정)도 별도
- 매매일지는 `data/trading_journal/` (gitignore됨)
- `reset-surge-scalping` 같은 프리셋 = 특정 전략 파라미터 일괄 적용

---

## 6. 매매 입력 (`trade`)

- **프론트**: [frontend/src/pages/TradeInput.tsx](frontend/src/pages/TradeInput.tsx)
- **API**: `GET /api/settings`, `POST /api/trades`, `POST /api/stocks`
- **백엔드 핸들러**: [api.py:1184](api.py#L1184), [api.py:1231](api.py#L1231), [api.py:1258](api.py#L1258)

### 데이터 흐름
1. `/api/settings` 로드 → 섹션/종목 리스트 콤보박스 채움
2. `POST /api/trades` ([api.py:1231](api.py#L1231))
   - body: `{section_name, month, stock_name, amount(float), realized, year}`
   - 해당 섹션 → `stocks` 자동 등록 → `rows_by_year[year][month][stock]`에 누적(`+=`)
   - `save_data()`로 `data/portfolio_data.json` 저장 → (옵션) GitHub 자동 동기화
3. `POST /api/stocks` — 신규 종목만 추가(amount=0)

### 핵심 포인트
- **amount는 float** — USD 소수점(9.72 같은) 허용 ([api.py:1200](api.py#L1200))
- 한 종목명 여러 번 저장 시 누적 합산
- 저장 시 frontend는 `onDataUpdate` → 대시보드/분석 refreshKey 증가시켜 리렌더

---

## 7. 입출금 (`cashflow`)

- **프론트**: [frontend/src/pages/CashFlow.tsx](frontend/src/pages/CashFlow.tsx)
- **API**: `GET /api/settings`, `POST /api/cashflows`
- **백엔드 핸들러**: [api.py:1284](api.py#L1284)

### 데이터 흐름
1. `cash_flows` 배열을 `settings.cash_flows`에서 로드
2. POST로 추가/수정 → `data/portfolio_data.json`의 `cash_flows` 전체 덮어쓰기
3. 입출금이 바뀌면 `calculate_current_principal()`이 다음 대시보드 호출 시 반영됨

### 핵심 포인트
- 입출금 타입은 `USER_DEPOSIT_TYPES` / `USER_WITHDRAWAL_TYPES`로 분류 ([api.py:57-58](api.py#L57))
- 연도별 원금 계산(`compute_yearly_principal_map`)의 기준 데이터

---

## 8. 분석 (`analytics`)

- **프론트**: [frontend/src/pages/Analytics.tsx](frontend/src/pages/Analytics.tsx)
- **API**: `GET /api/analytics`, `POST /api/analytics/refresh`
- **백엔드 핸들러**: [api.py:1162](api.py#L1162), [api.py:1179](api.py#L1179)

### 데이터 흐름
1. `combine_yearly_portfolio_data()` — 연도별 파일이 분리되어 있다면 합치는 단계
2. `compute_manual_trade_analytics(sections, usd_rate)` — 핵심 통계 엔진
   - `annual[]`: 연도별 실현손익, 매도횟수, 승률, 평균보유일
   - `buy_count`, `sell_count`: 전체 카운트
   - 종목/월별 분포 등
3. `infer_trading_style(annual, buy_count, sell_count)` — 거래 패턴 → "단타형" / "스윙형" 등 라벨링
4. `build_improvement_tips(analytics)` — 통계 기반 자동 코칭 멘트 ([api.py:1018~1047](api.py#L1018) 부근)
5. `/refresh`는 `sync_current_year_portfolio_file()` — 현재 연도 데이터 재집계

### 핵심 포인트
- "스타일/팁"은 룰베이스 휴리스틱(LLM 아님)
- 거래 데이터는 매매입력에서 들어온 `rows_by_year`가 단일 source of truth

---

## 부가: GitHub 동기화 (사이드바 하단)

- **API**: `GET /api/github/status`, `POST /api/github/sync`
- **백엔드 핸들러**: [api.py:1294](api.py#L1294), [api.py:1305](api.py#L1305)
- **설정**: `.env`의 `GITHUB_TOKEN`, `GITHUB_REPO`, `GITHUB_BRANCH`

### 동작
- `status`: 토큰/리포 설정 여부, 마지막 동기화 시간
- `sync`: 원격에서 `portfolio_data.json`을 가져와서 로컬 덮어쓰기 (다중 기기 동기화용)
- 매매입력/입출금 저장 시 자동으로 백그라운드 push (api.py 내 `save_data()` 후속 처리)

---

## 공통 백엔드 인프라

| 영역 | 위치 |
|---|---|
| FastAPI 앱/미들웨어 | [api.py:1-100](api.py) |
| 데이터 로드/저장 | `load_json_data()`, `save_data()` (api.py 상단부) |
| 종목 분석 엔진 | [stock_analysis.py](stock_analysis.py) — KIS/FDR/Yahoo/Claude 통합 |
| 자동매매 엔진 | [trading_engine.py](trading_engine.py) |
| 환경변수 로딩 | `STOCKS_PROFILE` → `.env.{profile}` ([api.py:36-43](api.py#L36)) |
| 데이터 파일 | `data/portfolio_data.json` (메인), `data/*종합잔고*.xls` (잔고), `data/trading_journal/` (일지) |

## 환경변수 (핵심만)

- `MYAPP`, `MYSEC` — 한국투자 OpenAPI 키 (실시간 시세, 자동매매)
- `PROD` — KIS base URL (기본: 실서버)
- `ANTHROPIC_API_KEY` — 종목 분석 LLM 메모/Q&A
- `GITHUB_TOKEN`, `GITHUB_REPO`, `GITHUB_BRANCH` — 데이터 동기화
- `STOCKS_PROFILE` — `company` / `home` 분기 (start.bat이 세팅)
