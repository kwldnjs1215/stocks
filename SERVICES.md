# Stocks Dashboard 서비스 정보

## 접속 주소

| 서비스 | 로컬 | WiFi (192.168.0.x) |
|--------|------|--------------------|
| React 프론트엔드 | http://localhost:5176 | http://192.168.0.3:5176 |
| FastAPI 백엔드 | http://localhost:8001 | http://192.168.0.3:8001 |
| API 문서 (Swagger) | http://localhost:8001/docs | http://192.168.0.3:8001/docs |

## 실행 방법

### 한번에 실행 (권장)
```bash
npm run dev
```
백엔드(8001, uvicorn `--reload`) + 프론트엔드(5176, vite)를 `concurrently`로 한 터미널에서 동시 기동. Ctrl+C로 둘 다 종료.

### 별도 실행
```bash
npm run dev:backend   # 백엔드만
npm run dev:frontend  # 프론트엔드만
```

### 레거시
`start.bat`도 그대로 유지(별도 cmd 창으로 띄우고 브라우저 자동 실행).

## 탭 구성

| 탭 | 설명 |
|----|------|
| 대시보드 | 포트폴리오 현황, 평가손익, 섹터별 비중 |
| 시황 | 네이버 금융 기반 코스피/코스닥 및 업종별 등락 현황 |
| 매매 입력 | 종목별 매수/매도 거래 내역 추가 |
| 입출금 | 증권 계좌 입출금 내역 관리 |
| 분석 | 수익률 추이, 월별 손익 분석 |

## API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/dashboard` | 포트폴리오 전체 데이터 |
| GET | `/api/analytics` | 수익률 분석 데이터 |
| GET | `/api/market` | 시황 데이터 (30분 캐시) |
| POST | `/api/market/refresh` | 시황 캐시 강제 갱신 |
| GET | `/api/settings` | 설정 조회 |
| POST | `/api/trades` | 거래 내역 저장 |
| POST | `/api/stocks` | 종목 정보 저장 |
| POST | `/api/cashflows` | 입출금 내역 저장 |

## 데이터 저장 위치

```
data/portfolio_data.json
```
