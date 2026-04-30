from __future__ import annotations

import base64
import json
import os
import time as _time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import requests as _requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 프로필별 .env 파일 로드 (start.bat이 STOCKS_PROFILE 세팅)
try:
    from dotenv import load_dotenv
    _profile = os.environ.get("STOCKS_PROFILE", "")
    _env_file = Path(__file__).resolve().parent / (f".env.{_profile}" if _profile else ".env")
    load_dotenv(_env_file, override=False)  # bat이 이미 설정한 값 유지
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_PATH = DATA_DIR / "portfolio_data.json"
MONTHS = [f"{m}월" for m in range(1, 13)]
DEFAULT_SECTION_NAMES = ["미국주식", "국내주식"]
SECTION_CURRENCIES = {"미국주식": "USD", "국내주식": "KRW"}
DEFAULT_USD_TO_KRW = 1350
DEFAULT_INITIAL_PRINCIPAL_KRW = 9_378_327
USER_DEPOSIT_TYPES = {"이체입금", "오픈뱅킹은행입금이체"}
USER_WITHDRAWAL_TYPES = {"이체출금", "은행이체출금", "간편송금 계좌출금", "미약정대체출금"}


# ── GitHub 동기화 ─────────────────────────────────────────────────────────────

_GH_TOKEN = os.environ.get("GITHUB_TOKEN", "")
_GH_REPO = os.environ.get("GITHUB_REPO", "")          # e.g. "username/stocks"
_GH_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
_GH_FILE_PATH = os.environ.get("GITHUB_FILE_PATH", "data/portfolio_data.json")

_gh_last_sync: float = 0.0
_gh_status: str = "미설정"


def _gh_configured() -> bool:
    return bool(_GH_TOKEN and _GH_REPO)


def _gh_headers() -> dict:
    return {"Authorization": f"token {_GH_TOKEN}", "Accept": "application/vnd.github+json"}


def _gh_url() -> str:
    return f"https://api.github.com/repos/{_GH_REPO}/contents/{_GH_FILE_PATH}"


def _gh_get_sha() -> str | None:
    try:
        r = _requests.get(_gh_url(), headers=_gh_headers(), params={"ref": _GH_BRANCH}, timeout=10)
        return r.json().get("sha") if r.status_code == 200 else None
    except Exception:
        return None


def github_pull() -> bool:
    """GitHub에서 portfolio_data.json을 받아 로컬에 저장."""
    global _gh_status
    if not _gh_configured():
        return False
    try:
        r = _requests.get(_gh_url(), headers=_gh_headers(), params={"ref": _GH_BRANCH}, timeout=10)
        if r.status_code != 200:
            _gh_status = f"풀 실패: {r.status_code}"
            return False
        content = base64.b64decode(r.json()["content"]).decode("utf-8")
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        DATA_PATH.write_text(content, encoding="utf-8")
        _gh_status = "동기화됨"
        return True
    except Exception as e:
        _gh_status = f"풀 오류: {str(e)[:60]}"
        return False


def github_push(raw: dict) -> bool:
    """로컬 데이터를 GitHub에 업로드."""
    global _gh_last_sync, _gh_status
    if not _gh_configured():
        return False
    try:
        content_b64 = base64.b64encode(
            json.dumps(raw, ensure_ascii=False, indent=2).encode("utf-8")
        ).decode("ascii")
        sha = _gh_get_sha()
        payload: dict = {
            "message": f"portfolio update {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "content": content_b64,
            "branch": _GH_BRANCH,
        }
        if sha:
            payload["sha"] = sha
        r = _requests.put(_gh_url(), headers=_gh_headers(), json=payload, timeout=15)
        if r.status_code in (200, 201):
            _gh_last_sync = _time.time()
            _gh_status = "동기화됨"
            return True
        _gh_status = f"푸시 실패: {r.status_code}"
        return False
    except Exception as e:
        _gh_status = f"푸시 오류: {str(e)[:60]}"
        return False


def save_data(raw: dict) -> None:
    """데이터를 로컬 저장 후 GitHub에 자동 푸시."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    github_push(raw)


# ── FastAPI 앱 ────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(_app: FastAPI):
    if _gh_configured():
        github_pull()
    yield


app = FastAPI(title="Stock Dashboard API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 파서 ──────────────────────────────────────────────────────────────────────

class HtmlTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_cell = False
        self.current: list[str] = []
        self.rows: list[list[str]] = []
        self.buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "tr":
            self.current = []
        elif tag in ("td", "th"):
            self.in_cell = True
            self.buffer = []
        elif tag == "br" and self.in_cell:
            self.buffer.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th"):
            self.current.append("".join(self.buffer).strip())
            self.in_cell = False
        elif tag == "tr" and self.current:
            self.rows.append(self.current)

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.buffer.append(data)


# ── 유틸 ─────────────────────────────────────────────────────────────────────

def parse_int(value: Any) -> int:
    if value is None:
        return 0
    text = str(value).strip().replace(",", "")
    if not text:
        return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def parse_number(value: Any) -> float:
    if value is None:
        return 0.0
    text = str(value).strip().replace(",", "")
    try:
        return float(text)
    except ValueError:
        return 0.0


def parse_trade_date(value: str) -> date:
    return datetime.strptime(value.strip(), "%Y.%m.%d").date()


# ── 데이터 로드 ───────────────────────────────────────────────────────────────

def load_json_data() -> dict[str, Any]:
    if not DATA_PATH.exists():
        return {"sections": []}
    try:
        return json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"sections": []}


def parse_html_table(path: Path) -> list[dict[str, str]]:
    parser = HtmlTableParser()
    parser.feed(path.read_text(encoding="euc-kr"))
    if not parser.rows:
        return []
    header = parser.rows[0]
    records = []
    for row in parser.rows[1:]:
        padded = row + [""] * (len(header) - len(row))
        records.append(dict(zip(header, padded)))
    return records


def load_asset_summary() -> dict[str, Any]:
    paths = list(DATA_DIR.glob("*종합잔고*.xls"))
    if not paths:
        return {}
    # 직접 raw 행 파싱 (parse_html_table은 첫 행을 헤더로 쓰므로 부적합)
    parser = HtmlTableParser()
    parser.feed(paths[0].read_text(encoding="euc-kr"))
    rows = parser.rows
    if len(rows) < 2:
        return {}

    def strip_unit(v: str) -> int:
        return parse_int(v.replace("원", "").replace(",", "").replace("%", ""))

    # 상단 요약: 행 0~3이 key-value 쌍으로 구성 — 위치 기반 고정 파싱
    # row[0]: 자산금액, 투자금액, 평가금액
    # row[1]: 평가손익, 수익률, 예수금+채권금액
    # row[2]: 예수금, ...
    r0 = rows[0] if len(rows) > 0 else []
    r1 = rows[1] if len(rows) > 1 else []
    r2 = rows[2] if len(rows) > 2 else []

    total_assets  = strip_unit(r0[1]) if len(r0) > 1 else 0
    invest_amount = strip_unit(r0[3]) if len(r0) > 3 else 0
    eval_amount   = strip_unit(r0[5]) if len(r0) > 5 else 0
    unrealized_pnl = strip_unit(r1[1]) if len(r1) > 1 else 0
    cash          = strip_unit(r2[1]) if len(r2) > 1 else 0

    # 종목별 보유 현황 (헤더 행 = 첫 셀이 "No"인 행)
    header_idx = next((i for i, r in enumerate(rows) if r and r[0] == "No"), None)
    holdings = []
    if header_idx is not None:
        header = rows[header_idx]
        for row in rows[header_idx + 1:]:
            if not row or not row[0].isdigit():
                continue
            padded = row + [""] * (len(header) - len(row))
            entry = dict(zip(header, padded))
            holdings.append({
                "name": entry.get("품목명", ""),
                "type": entry.get("단가구분", ""),
                "qty": parse_number(entry.get("수량", "0")),
                "avg_price": parse_number(entry.get("단가", "0")),
                "invest": parse_int(entry.get("투자금액", "0")),
                "eval": parse_int(entry.get("평가금액", "0")),
                "pnl": parse_int(entry.get("평가손익", "0")),
                "rate": parse_number(entry.get("수익률", "0")),
            })

    return {
        "total_assets": total_assets,
        "invest_amount": invest_amount,
        "eval_amount": eval_amount,
        "unrealized_pnl": unrealized_pnl,
        "cash": cash,
        "holdings": holdings,
    }


def load_cash_records() -> list[dict[str, str]]:
    paths = list(DATA_DIR.glob("입출금거래내역_*.xls"))
    if not paths:
        return []
    return parse_html_table(paths[0])


def load_trade_records() -> list[dict[str, str]]:
    paths = sorted(DATA_DIR.glob("종합거래내역(간략)_*.xls"))
    records: list[dict[str, str]] = []
    for path in paths:
        records.extend(parse_html_table(path))
    records.sort(key=lambda r: r.get("실거래일자", ""))
    return records


# ── 포트폴리오 로직 ───────────────────────────────────────────────────────────

def calculate_current_principal(settings: dict[str, Any]) -> int:
    total = parse_int(settings.get("baseline_principal_krw", DEFAULT_INITIAL_PRINCIPAL_KRW))
    for flow in settings.get("cash_flows", []):
        amount = parse_int(flow.get("amount", 0))
        if flow.get("type") == "입금":
            total += amount
        elif flow.get("type") == "출금":
            total -= amount
    return total


def get_currency(section_name: str) -> str:
    return SECTION_CURRENCIES.get(section_name, "KRW")


def section_month_total(rows: dict, month: str) -> float:
    return sum(rows.get(month, {}).values())


def section_total(rows: dict) -> float:
    return sum(sum(v.values()) for v in rows.values())


def get_rows_for_year(section: dict, year: int | None) -> dict:
    """Return manual rows for a year.

    Older data was stored in section["rows"] without a year. Treat those rows as
    current-year data so existing manual entries remain visible after the newer
    rows_by_year format was introduced.
    """
    legacy_rows = section.get("rows", {})
    rows_by_year = section.get("rows_by_year", {})
    if not rows_by_year:
        return legacy_rows

    def merge_rows(base: dict, extra: dict) -> dict:
        merged = {month: dict(stocks) for month, stocks in base.items()}
        for month, stocks in extra.items():
            m = merged.setdefault(month, {})
            for stock, val in stocks.items():
                m[stock] = m.get(stock, 0) + val
        return merged

    if year is not None:
        year_rows = rows_by_year.get(str(year), {})
        if year == datetime.now().year:
            return merge_rows(legacy_rows, year_rows)
        return year_rows

    # 전체 합산
    combined: dict = {month: dict(stocks) for month, stocks in legacy_rows.items()}
    for yr_data in rows_by_year.values():
        for month, stocks in yr_data.items():
            m = combined.setdefault(month, {})
            for stock, val in stocks.items():
                m[stock] = m.get(stock, 0) + val
    return combined or legacy_rows


def get_manual_annual_totals(sections: list, usd_rate: float) -> dict[int, float]:
    """rows_by_year 기준 연도별 수익 합산 → {year: profit_krw}"""
    result: dict[int, float] = defaultdict(float)
    for section in sections:
        rows_by_year = section.get("rows_by_year", {})
        currency = get_currency(section.get("name", ""))
        legacy_total = sum(sum(month.values()) for month in section.get("rows", {}).values())
        if legacy_total:
            result[datetime.now().year] += legacy_total * usd_rate if currency == "USD" else legacy_total
        for year_str, year_data in rows_by_year.items():
            try:
                year = int(year_str)
            except ValueError:
                continue
            total = sum(sum(month.values()) for month in year_data.values())
            result[year] += total * usd_rate if currency == "USD" else total
    return dict(result)


def merge_annual_with_manual(xls_annual: list, manual_totals: dict[int, float]) -> list:
    """XLS 연간 데이터 + 수동 입력 수익 병합. 수동 입력만 있는 연도도 포함."""
    xls_by_year = {row["year"]: dict(row) for row in xls_annual}
    all_years = sorted(set(list(xls_by_year.keys()) + list(manual_totals.keys())))
    result = []
    for year in all_years:
        manual = manual_totals.get(year, 0.0)
        if year in xls_by_year:
            row = dict(xls_by_year[year])
            row["realized_profit_krw"] = round(row["realized_profit_krw"] + manual)
            row["manual_profit_krw"] = round(manual)
        else:
            row = {
                "year": year,
                "realized_profit_krw": round(manual),
                "manual_profit_krw": round(manual),
                "sells": 0, "wins": 0, "win_rate": 0.0, "avg_hold_days": 0.0,
            }
        result.append(row)
    return result


def compute_yearly_principal_map(settings: dict[str, Any]) -> tuple[dict[int, int], dict[int, int]]:
    yearly_delta: dict[int, int] = defaultdict(int)
    for record in load_cash_records():
        trade_type = record.get("거래유형", "").strip()
        detail_type = record.get("거래종류", "").strip()
        amount = parse_int(record.get("거래금액", 0))
        try:
            year = parse_trade_date(record.get("실거래일자", "")).year
        except Exception:
            continue
        if trade_type == "입금" and detail_type in USER_DEPOSIT_TYPES:
            yearly_delta[year] += amount
        elif trade_type == "출금" and detail_type in USER_WITHDRAWAL_TYPES:
            yearly_delta[year] -= amount

    for flow in settings.get("cash_flows", []):
        flow_date = str(flow.get("date", "")).strip()
        if not flow_date:
            continue
        try:
            year = datetime.strptime(flow_date, "%Y-%m-%d").year
        except Exception:
            continue
        amount = parse_int(flow.get("amount", 0))
        if flow.get("type") == "입금":
            yearly_delta[year] += amount
        elif flow.get("type") == "출금":
            yearly_delta[year] -= amount

    year_end_principal: dict[int, int] = {}
    running = 0
    for year in sorted(yearly_delta):
        running += yearly_delta[year]
        year_end_principal[year] = running
    return dict(yearly_delta), year_end_principal


def compute_trade_analytics(usd_to_krw_rate: int) -> dict[str, Any]:
    records = load_trade_records()
    inventory: dict[tuple, deque] = defaultdict(deque)
    annual: dict[int, dict] = defaultdict(lambda: {"profit_krw": 0, "sells": 0, "wins": 0, "losses": 0, "hold_days": 0.0})
    symbol_profit: dict[str, int] = defaultdict(int)
    symbol_count: dict[str, int] = defaultdict(int)
    symbol_trade_count: dict[str, int] = defaultdict(int)
    monthly_profit: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    buy_count = sell_count = usd_trade_count = krw_trade_count = 0

    for record in records:
        action = record.get("거래유형", "").strip()
        if action not in {"매수", "매도"}:
            continue
        detail = record.get("상세내용", "").strip()
        symbol = record.get("종목명", "").strip() or "기타"
        try:
            trade_date = parse_trade_date(record.get("실거래일자", ""))
        except Exception:
            continue
        quantity = parse_number(record.get("수량", 0))
        if quantity <= 0:
            continue
        settlement = parse_number(record.get("정산금액", 0)) or parse_number(record.get("거래금액", 0))
        currency = "USD" if "외화증권" in detail else "KRW"
        key = (symbol, currency)
        symbol_trade_count[symbol] += 1
        if currency == "USD":
            usd_trade_count += 1
        else:
            krw_trade_count += 1

        if action == "매수":
            buy_count += 1
            inventory[key].append({"qty": quantity, "cost_per_unit": settlement / quantity, "date": trade_date})
            continue

        sell_count += 1
        proceeds = settlement
        remaining = quantity
        cost_basis = hold_days = 0.0
        while remaining > 0 and inventory[key]:
            lot = inventory[key][0]
            matched = min(remaining, lot["qty"])
            cost_basis += matched * lot["cost_per_unit"]
            hold_days += matched * (trade_date - lot["date"]).days
            lot["qty"] -= matched
            remaining -= matched
            if lot["qty"] <= 0:
                inventory[key].popleft()
        if remaining > 0:
            cost_basis += remaining * (proceeds / quantity)

        realized_native = proceeds - cost_basis
        realized_krw = round(realized_native * usd_to_krw_rate) if currency == "USD" else round(realized_native)
        year = trade_date.year
        annual[year]["profit_krw"] += realized_krw
        annual[year]["sells"] += 1
        annual[year]["hold_days"] += hold_days / quantity if quantity else 0
        annual[year]["wins"] += 1 if realized_krw > 0 else 0
        annual[year]["losses"] += 1 if realized_krw < 0 else 0
        symbol_profit[symbol] += realized_krw
        symbol_count[symbol] += 1
        monthly_profit[year][f"{trade_date.month}월"] += realized_krw

    annual_list = [
        {
            "year": year,
            "realized_profit_krw": int(v["profit_krw"]),
            "sells": int(v["sells"]),
            "wins": int(v["wins"]),
            "losses": int(v["losses"]),
            "win_rate": round(v["wins"] / v["sells"] * 100, 1) if v["sells"] else 0.0,
            "avg_hold_days": round(v["hold_days"] / v["sells"], 1) if v["sells"] else 0.0,
        }
        for year, v in sorted(annual.items())
    ]

    symbol_profit_list = sorted(
        [{"종목명": k, "실현손익": int(v)} for k, v in symbol_profit.items()],
        key=lambda x: x["실현손익"], reverse=True
    )
    symbol_count_list = sorted(
        [{"종목명": k, "매도횟수": int(v)} for k, v in symbol_count.items()],
        key=lambda x: x["매도횟수"], reverse=True
    )
    symbol_trade_list = sorted(
        [{"종목명": k, "거래횟수": int(v)} for k, v in symbol_trade_count.items()],
        key=lambda x: x["거래횟수"], reverse=True
    )

    return {
        "annual": annual_list,
        "symbol_profit": symbol_profit_list,
        "symbol_count": symbol_count_list,
        "symbol_trade": symbol_trade_list,
        "monthly_profit": {str(yr): dict(mv) for yr, mv in monthly_profit.items()},
        "buy_count": buy_count,
        "sell_count": sell_count,
        "usd_trade_count": usd_trade_count,
        "krw_trade_count": krw_trade_count,
    }


def infer_trading_style(annual: list[dict], buy_count: int, sell_count: int) -> dict[str, Any]:
    if not annual:
        return {"label": "데이터 없음", "traits": []}
    avg_hold = sum(r["avg_hold_days"] for r in annual) / len(annual)
    trades_per_year = (buy_count + sell_count) / len(annual)

    if avg_hold <= 10:
        label = "초단기 스윙형"
    elif avg_hold <= 35:
        label = "단기 스윙형"
    elif avg_hold <= 90:
        label = "중기 보유형"
    else:
        label = "장기 보유형"

    traits = []
    if trades_per_year >= 25:
        traits.append("회전율이 높아 기회 포착은 빠르지만 과매매 위험이 있습니다.")
    else:
        traits.append("거래 빈도가 과하지 않아 손실 통제에 유리한 편입니다.")
    if avg_hold <= 20:
        traits.append("짧게 들어갔다가 빠르게 정리하는 패턴이 강합니다.")
    elif avg_hold >= 60:
        traits.append("버티는 힘이 있어 추세를 길게 먹는 타입에 가깝습니다.")
    else:
        traits.append("너무 짧지도 길지도 않은 중간 보유 성향이 보입니다.")

    return {"label": label, "avg_hold_days": round(avg_hold, 1), "traits": traits}


def build_improvement_tips(analytics: dict[str, Any]) -> list[str]:
    annual = analytics["annual"]
    symbol_profit = analytics["symbol_profit"]
    symbol_trade = analytics["symbol_trade"]
    symbol_count = analytics["symbol_count"]
    buy_count = analytics["buy_count"]
    sell_count = analytics["sell_count"]
    usd_trade_count = analytics["usd_trade_count"]
    krw_trade_count = analytics["krw_trade_count"]

    if not annual:
        return []

    total_sells = sum(r["sells"] for r in annual)
    total_wins = sum(r["wins"] for r in annual)
    overall_win_rate = (total_wins / total_sells * 100) if total_sells else 0.0
    trades_per_year = (buy_count + sell_count) / len(annual)
    total_trades = buy_count + sell_count

    # 연도별 효율 (건당 수익)
    efficiency = [
        {"year": r["year"], "per_trade": r["realized_profit_krw"] / r["sells"] if r["sells"] else 0, "sells": r["sells"], "avg_hold": r["avg_hold_days"]}
        for r in annual
    ]
    best_eff = max(efficiency, key=lambda x: x["per_trade"])
    recent = annual[-1] if annual else None
    prev_years = annual[:-1]
    avg_prev_sells = sum(r["sells"] for r in prev_years) / len(prev_years) if prev_years else 0

    tips = []

    # 1. 승률 vs 손익비
    if overall_win_rate >= 75:
        tips.append(
            f"승률이 {overall_win_rate:.0f}%로 매우 높습니다. 이 수준의 승률에서는 손절 금액보다 익절 금액을 키우는 것이 수익률 레버리지에 훨씬 효과적입니다. "
            "이기는 포지션을 지금보다 1.5배만 더 들고 가도 연간 수익이 눈에 띄게 달라질 수 있어요."
        )
    else:
        tips.append("승률이 50% 아래로 내려간 해가 있다면 종목 선정 기준을 명확히 문서화해두는 것이 효과적입니다.")

    # 2. 최고 효율 연도 패턴 활용
    if best_eff["per_trade"] > 0:
        tips.append(
            f"{best_eff['year']}년은 {best_eff['sells']}번의 매도로 건당 평균 {int(best_eff['per_trade']):,}원을 벌어 전체 기간 중 가장 효율적인 해였습니다. "
            f"당시 평균 보유일은 {best_eff['avg_hold']:.0f}일이었는데, 이 보유 패턴이 본인 스타일에서 '스윗 스팟'에 가장 가까웠을 가능성이 높습니다."
        )

    # 3. 최근 매매 빈도 급증 (2026년 같은 케이스)
    if recent and recent["sells"] > avg_prev_sells * 2 and len(annual) > 2:
        tips.append(
            f"{recent['year']}년 매도 횟수({recent['sells']}회)는 이전 연평균({avg_prev_sells:.0f}회)의 "
            f"{recent['sells']/max(avg_prev_sells,1):.1f}배입니다. 활동량이 늘어난 건 기회 감각이 좋아졌다는 신호이기도 하지만, "
            "건당 수익이 줄어들지 않는지 분기별로 점검하는 루틴이 필요합니다."
        )

    # 4. 단기 보유 비중 높을 때
    if recent and recent["avg_hold_days"] <= 30:
        tips.append(
            f"최근 평균 보유일이 {recent['avg_hold_days']:.0f}일로 매우 짧아졌습니다. "
            "단기 매매는 슬리피지·수수료 비용이 쌓이기 쉬운 구조입니다. 진입 종목 중 최소 20~30%는 '중기 보유 전용 바구니'로 분리해서 "
            "단기 노이즈에 흔들리지 않도록 관리하는 것을 권장합니다."
        )

    # 5. 손실 종목 집중도
    loss_symbols = [r for r in symbol_profit if r["실현손익"] < 0]
    if loss_symbols:
        worst = loss_symbols[0]  # sorted by profit desc, so last = worst
        worst = symbol_profit[-1]
        tips.append(
            f"손실 종목 중 '{worst['종목명']}'의 손실이 가장 큽니다. "
            "손실이 난 종목을 다시 매수할 때는 '이전 손실을 만회하려는 심리'가 들어가지 않았는지 한 번 더 확인하세요. "
            "복수심 매매는 같은 종목에서 손실이 두 배로 커지는 패턴으로 이어지기 쉽습니다."
        )

    # 6. 자주 거래하는 종목 패턴북
    if symbol_trade:
        top = symbol_trade[0]
        tips.append(
            f"'{top['종목명']}'은 총 {top['거래횟수']}회로 가장 많이 거래한 종목입니다. "
            "이렇게 반복해서 보는 종목은 진입 가격대, 청산 조건, 보유 결과를 시계열로 기록해두면 "
            "본인만의 해당 종목 전용 매매 패턴이 만들어집니다. 같은 종목이라도 시즌성이나 이벤트 패턴이 반복되는 경우가 많습니다."
        )

    # 7. USD vs KRW 비중 균형
    if total_trades > 0:
        usd_ratio = usd_trade_count / total_trades * 100
        if usd_ratio > 60:
            tips.append(
                f"전체 거래의 {usd_ratio:.0f}%가 미국 주식입니다. 미국 장은 환율 변동이 수익에 직접 영향을 주기 때문에, "
                "달러가 강세일 때 매도 vs 약세일 때 매도가 실제 원화 손익에 얼마나 차이를 내는지 한 번 계산해두면 좋습니다."
            )
        elif usd_ratio < 30:
            tips.append(
                f"국내 주식 비중이 {100-usd_ratio:.0f}%로 높은 편입니다. "
                "미국 장은 국내와 상관관계가 낮아 포트폴리오 분산 효과가 있습니다. "
                "승률이 높은 지금 시점에 미국 ETF 몇 종목을 장기 보유 바구니에 넣어보는 것도 고려해볼 만합니다."
            )

    # 8. 매도 횟수 대비 매수 비율
    if buy_count > 0 and sell_count > 0:
        ratio = buy_count / sell_count
        if ratio > 2:
            tips.append(
                f"매수 {buy_count}회, 매도 {sell_count}회로 아직 정리하지 않은 포지션이 상당수 쌓여 있습니다. "
                "보유 중인 미실현 포지션의 목표가와 손절가를 다시 점검하고, 기준 없이 들고 있는 종목은 이번 기회에 정리하는 것을 권장합니다."
            )

    return tips


# ── API 엔드포인트 ────────────────────────────────────────────────────────────

@app.get("/api/dashboard")
def get_dashboard():
    raw = load_json_data()
    settings = {
        "owner_name": raw.get("owner_name", ""),
        "baseline_principal_krw": parse_int(raw.get("baseline_principal_krw", DEFAULT_INITIAL_PRINCIPAL_KRW)) or DEFAULT_INITIAL_PRINCIPAL_KRW,
        "usd_to_krw_rate": parse_int(raw.get("usd_to_krw_rate", DEFAULT_USD_TO_KRW)) or DEFAULT_USD_TO_KRW,
        "cash_flows": raw.get("cash_flows", []),
    }
    usd_rate = settings["usd_to_krw_rate"]
    current_principal = calculate_current_principal(settings)
    sections_raw = raw.get("sections", [])

    sections_out = []
    total_profit_krw = 0
    for section in sections_raw:
        name = section.get("name", "")
        currency = get_currency(name)

        # 전체 합산 (all-time): rows_by_year 우선, 없으면 legacy rows
        rows_all = get_rows_for_year(section, None)
        s_total = section_total(rows_all)
        s_total_krw = round(s_total * usd_rate) if currency == "USD" else s_total
        total_profit_krw += s_total_krw

        def build_monthly(rows: dict) -> list:
            result, cum = [], 0.0
            for month in MONTHS:
                m = section_month_total(rows, month)
                cum += m
                result.append({"month": month, "profit": m, "cumulative": cum})
            return result

        def build_stocks_monthly(rows: dict) -> list:
            stock_cum: dict[str, float] = {}
            out = []
            for month in MONTHS:
                entry: dict[str, Any] = {"month": month}
                for stock in section.get("stocks", []):
                    sname = stock["name"]
                    val = rows.get(month, {}).get(sname, 0)
                    stock_cum[sname] = stock_cum.get(sname, 0) + val
                    entry[sname] = stock_cum[sname]
                out.append(entry)
            return out

        # 연도별 월별 데이터
        rows_by_year = section.get("rows_by_year", {})
        monthly_by_year: dict[str, list] = {}
        total_by_year: dict[str, float] = {}
        stocks_monthly_by_year: dict[str, list] = {}
        year_keys = set(rows_by_year.keys())
        if section.get("rows"):
            year_keys.add(str(datetime.now().year))
        for yr_str in sorted(year_keys):
            try:
                yr_rows = get_rows_for_year(section, int(yr_str))
            except ValueError:
                yr_rows = rows_by_year.get(yr_str, {})
            monthly_by_year[yr_str] = build_monthly(yr_rows)
            stocks_monthly_by_year[yr_str] = build_stocks_monthly(yr_rows)
            total_by_year[yr_str] = section_total(yr_rows)

        sections_out.append({
            "name": name,
            "currency": currency,
            "total": s_total,
            "total_krw": s_total_krw,
            "total_by_year": total_by_year,
            "stocks": section.get("stocks", []),
            "monthly": build_monthly(rows_all),
            "monthly_by_year": monthly_by_year,
            "stocks_monthly": build_stocks_monthly(rows_all),
            "stocks_monthly_by_year": stocks_monthly_by_year,
        })

    analytics = compute_trade_analytics(usd_rate)
    manual_annual = get_manual_annual_totals(sections_raw, usd_rate)
    merged_annual = merge_annual_with_manual(analytics["annual"], manual_annual)

    yearly_delta, year_end_principal = compute_yearly_principal_map(settings)
    yearly_summary = []
    for row in merged_annual:
        year = row["year"]
        principal = year_end_principal.get(year, 0)
        delta = yearly_delta.get(year, 0)
        rate = round(row["realized_profit_krw"] / principal * 100, 2) if principal > 0 else 0.0
        yearly_summary.append({**row, "year_principal": principal, "year_delta": delta, "return_rate": rate})

    asset_summary = load_asset_summary()

    return {
        "settings": settings,
        "current_principal": current_principal,
        "total_profit_krw": total_profit_krw,
        "sections": sections_out,
        "yearly_summary": yearly_summary,
        "asset_summary": asset_summary,
    }


@app.get("/api/debug-asset")
def debug_asset():
    paths = list(DATA_DIR.glob("*종합잔고*.xls"))
    if not paths:
        return {"error": "file not found", "data_dir": str(DATA_DIR)}
    parser = HtmlTableParser()
    parser.feed(paths[0].read_text(encoding="euc-kr"))
    rows = parser.rows
    r0 = rows[0] if rows else []
    return {
        "r0_len": len(r0),
        "r0_1": r0[1] if len(r0) > 1 else None,
        "r0_3": r0[3] if len(r0) > 3 else None,
        "r0_3_repr": repr(r0[3]) if len(r0) > 3 else None,
        "after_replace": r0[3].replace("원", "X").replace(",", "") if len(r0) > 3 else None,
    }


@app.get("/api/analytics")
def get_analytics():
    raw = load_json_data()
    usd_rate = parse_int(raw.get("usd_to_krw_rate", DEFAULT_USD_TO_KRW)) or DEFAULT_USD_TO_KRW
    analytics = compute_trade_analytics(usd_rate)

    # 수동 입력 연도별 합산 → annual에 병합
    sections_raw = raw.get("sections", [])
    manual_annual = get_manual_annual_totals(sections_raw, usd_rate)
    merged_annual = merge_annual_with_manual(analytics["annual"], manual_annual)

    style = infer_trading_style(merged_annual, analytics["buy_count"], analytics["sell_count"])
    tips = build_improvement_tips({**analytics, "annual": merged_annual})

    # 수동 입력 섹션별 요약 (전체 연도 합산)
    manual_sections = []
    for section in sections_raw:
        name = section.get("name", "")
        currency = get_currency(name)
        rows_all = get_rows_for_year(section, None)   # 전 연도 합산
        total = section_total(rows_all)
        total_krw = round(total * usd_rate) if currency == "USD" else total

        monthly, cumulative = [], 0.0
        for month in MONTHS:
            val = section_month_total(rows_all, month)
            cumulative += val
            monthly.append({"month": month, "profit": val, "cumulative": cumulative})

        # 종목별 합계 (전 연도)
        stock_totals = []
        for stock in section.get("stocks", []):
            sname = stock["name"]
            s_total = sum(rows_all.get(m, {}).get(sname, 0) for m in MONTHS)
            if s_total != 0:
                stock_totals.append({"name": sname, "total": s_total, "realized": stock.get("realized", False)})
        stock_totals.sort(key=lambda x: x["total"], reverse=True)

        # 연도별 종목 합계
        stock_totals_by_year: dict[str, list] = {}
        for yr_str, yr_rows in section.get("rows_by_year", {}).items():
            yr_stocks = []
            for stock in section.get("stocks", []):
                sname = stock["name"]
                s_total_yr = sum(yr_rows.get(m, {}).get(sname, 0) for m in MONTHS)
                if s_total_yr != 0:
                    yr_stocks.append({"name": sname, "total": s_total_yr, "realized": stock.get("realized", False)})
            yr_stocks.sort(key=lambda x: x["total"], reverse=True)
            stock_totals_by_year[yr_str] = yr_stocks

        manual_sections.append({
            "name": name,
            "currency": currency,
            "total": total,
            "total_krw": total_krw,
            "monthly": monthly,
            "stock_totals": stock_totals,
            "stock_totals_by_year": stock_totals_by_year,
        })

    return {
        **analytics,
        "annual": merged_annual,
        "style": style,
        "tips": tips,
        "manual_sections": manual_sections,
    }


@app.get("/api/settings")
def get_settings():
    raw = load_json_data()
    return {
        "owner_name": raw.get("owner_name", ""),
        "baseline_principal_krw": parse_int(raw.get("baseline_principal_krw", DEFAULT_INITIAL_PRINCIPAL_KRW)) or DEFAULT_INITIAL_PRINCIPAL_KRW,
        "usd_to_krw_rate": parse_int(raw.get("usd_to_krw_rate", DEFAULT_USD_TO_KRW)) or DEFAULT_USD_TO_KRW,
        "cash_flows": raw.get("cash_flows", []),
        "sections": raw.get("sections", []),
    }


class TradeInput(BaseModel):
    section_name: str
    month: str
    stock_name: str
    amount: float   # USD는 소수점 허용 (e.g. 9.72)
    realized: bool = False
    year: int = datetime.now().year


@app.post("/api/trades")
def add_trade(body: TradeInput):
    raw = load_json_data()
    sections = raw.get("sections", [])
    section = next((s for s in sections if s["name"] == body.section_name), None)
    if not section:
        raise HTTPException(status_code=404, detail="섹션을 찾을 수 없습니다.")

    stocks = section.setdefault("stocks", [])
    if not any(s["name"] == body.stock_name for s in stocks):
        stocks.append({"name": body.stock_name, "realized": body.realized})

    # rows_by_year에 연도별 저장
    rows_by_year = section.setdefault("rows_by_year", {})
    year_rows = rows_by_year.setdefault(str(body.year), {})
    month_rows = year_rows.setdefault(body.month, {})
    month_rows[body.stock_name] = month_rows.get(body.stock_name, 0) + body.amount

    save_data(raw)
    return {"ok": True}


class StockAdd(BaseModel):
    section_name: str
    stock_name: str
    realized: bool = False


@app.post("/api/stocks")
def add_stock(body: StockAdd):
    raw = load_json_data()
    sections = raw.get("sections", [])
    section = next((s for s in sections if s["name"] == body.section_name), None)
    if not section:
        raise HTTPException(status_code=404, detail="섹션을 찾을 수 없습니다.")

    stocks = section.setdefault("stocks", [])
    if not any(s["name"] == body.stock_name for s in stocks):
        stocks.append({"name": body.stock_name, "realized": body.realized})
        rows = section.setdefault("rows", {})
        for month in MONTHS:
            rows.setdefault(month, {})[body.stock_name] = 0

    save_data(raw)
    return {"ok": True}


class CashFlowAdd(BaseModel):
    date: str
    type: str
    amount: int
    memo: str = ""


@app.post("/api/cashflows")
def add_cashflow(body: CashFlowAdd):
    raw = load_json_data()
    flows = raw.get("cash_flows", [])
    flows.append({"date": body.date, "type": body.type, "amount": body.amount, "memo": body.memo})
    raw["cash_flows"] = flows
    save_data(raw)
    return {"ok": True}


@app.get("/api/github/status")
def github_status():
    return {
        "configured": _gh_configured(),
        "repo": _GH_REPO if _gh_configured() else "",
        "branch": _GH_BRANCH,
        "last_sync": _gh_last_sync,
        "status": _gh_status,
    }


@app.post("/api/github/sync")
def github_sync_pull():
    """GitHub에서 최신 데이터를 강제로 가져옴."""
    if not _gh_configured():
        raise HTTPException(status_code=400, detail="GitHub 설정(GITHUB_TOKEN, GITHUB_REPO)이 없습니다.")
    ok = github_pull()
    return {"ok": ok, "status": _gh_status}


_market_cache: dict = {"data": None, "ts": 0.0}
_MARKET_TTL = 1800  # 30분 캐시


def _fetch_sectors() -> list[dict]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://finance.naver.com/",
        "Accept-Language": "ko-KR,ko;q=0.9",
    }
    resp = _requests.get(
        "https://finance.naver.com/sise/sise_group.naver?type=upjong",
        headers=headers,
        timeout=10,
    )
    resp.encoding = "euc-kr"
    soup = BeautifulSoup(resp.text, "html.parser")

    sectors: list[dict] = []
    table = soup.find("table", class_="type_1")
    if table:
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            # col0: 업종명, col1: 등락률(+1.23% 형식)
            link = cells[0].find("a")
            name = (link.text if link else cells[0].text).strip()
            try:
                change = float(cells[1].text.strip().replace("%", "").replace("+", "").replace(",", ""))
            except ValueError:
                continue
            if not name:
                continue
            sectors.append({"name": name, "change": round(change, 2)})

    return sorted(sectors, key=lambda x: x["change"], reverse=True)


def _fetch_index(code: str) -> dict:
    try:
        resp = _requests.get(
            f"https://m.stock.naver.com/api/index/{code}/basic",
            timeout=5,
        )
        d = resp.json()
        return {
            "name": code,
            "price": float(d.get("closePrice", "0").replace(",", "")),
            "change": float(d.get("fluctuationsRatio", "0")),
            "change_val": float(d.get("compareToPreviousClosePrice", "0").replace(",", "")),
        }
    except Exception:
        return {"name": code, "price": 0.0, "change": 0.0, "change_val": 0.0}


@app.get("/api/market")
async def get_market():
    now = _time.time()
    if _market_cache["data"] and (now - _market_cache["ts"]) < _MARKET_TTL:
        return _market_cache["data"]

    try:
        sectors = _fetch_sectors()
        kospi = _fetch_index("KOSPI")
        kosdaq = _fetch_index("KOSDAQ")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"시황 데이터 수집 실패: {e}")

    rising = [s for s in sectors if s["change"] >= 0.5]
    falling = [s for s in sectors if s["change"] <= -0.5]
    flat = [s for s in sectors if -0.5 < s["change"] < 0.5]

    r, f = len(rising), len(falling)
    if r > f * 1.5:
        trend = "강세"
    elif f > r * 1.5:
        trend = "약세"
    else:
        trend = "혼조"

    result = {
        "sectors": sectors,
        "rising": rising,
        "falling": falling,
        "flat": flat,
        "indices": [kospi, kosdaq],
        "summary": {
            "rising_count": r,
            "falling_count": f,
            "flat_count": len(flat),
            "trend": trend,
        },
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    _market_cache["data"] = result
    _market_cache["ts"] = now
    return result


@app.post("/api/market/refresh")
async def refresh_market():
    _market_cache["ts"] = 0.0
    return await get_market()


# ── 섹터 추이 ─────────────────────────────────────────────────────────────────

import FinanceDataReader as _fdr

SECTOR_ETFS = [
    {"sector": "반도체",     "etf": "TIGER 반도체",        "code": "091160"},
    {"sector": "2차전지",    "etf": "TIGER 2차전지테마",    "code": "305720"},
    {"sector": "방산",       "etf": "KODEX K-방산",         "code": "329200"},
    {"sector": "바이오",     "etf": "KODEX 바이오",         "code": "272580"},
    {"sector": "자동차",     "etf": "KODEX 자동차",         "code": "091180"},
    {"sector": "금융/은행",  "etf": "KODEX 은행",           "code": "091170"},
    {"sector": "조선",       "etf": "HANARO 조선해양",      "code": "395160"},
    {"sector": "금(Gold)",   "etf": "KODEX 골드선물H",      "code": "132030"},
    {"sector": "AI/소프트웨어", "etf": "TIGER AI코리아",   "code": "364980"},
    {"sector": "전력/에너지", "etf": "TIGER 전력&에너지",   "code": "381180"},
]

_trend_cache: dict = {"data": None, "ts": 0.0}
_TREND_TTL = 21600  # 6시간 캐시 (장중에는 하루 한 번 업데이트)


def _calc_streak(returns: list[float]) -> int:
    """연속 상승/하락일수. 양수=연속 상승, 음수=연속 하락."""
    if not returns:
        return 0
    streak = 1 if returns[-1] > 0 else -1
    direction = streak
    for r in reversed(returns[:-1]):
        if (r > 0) == (direction > 0):
            streak += direction
        else:
            break
    return streak


def _trend_comment(streak: int, change_5d: float, from_high_pct: float) -> str:
    parts = []
    if streak >= 4:
        parts.append(f"{streak}일 연속 상승 중")
    elif streak >= 2:
        parts.append(f"{streak}일 연속 상승")
    elif streak <= -4:
        parts.append(f"{abs(streak)}일 연속 하락 중")
    elif streak <= -2:
        parts.append(f"{abs(streak)}일 연속 하락")

    if from_high_pct <= -7:
        parts.append(f"고점 대비 {abs(from_high_pct):.1f}% 조정 중")
    elif from_high_pct <= -4:
        parts.append(f"고점 대비 {abs(from_high_pct):.1f}% 하락")

    if not parts:
        if abs(change_5d) < 1.0:
            parts.append("횡보 구간")
        elif change_5d >= 5:
            parts.append("강한 상승 추세")
        elif change_5d >= 2:
            parts.append("상승 추세")
        elif change_5d <= -5:
            parts.append("강한 하락 추세")
        elif change_5d <= -2:
            parts.append("하락 추세")

    return " · ".join(parts) if parts else "보합"


def _fetch_one_sector(info: dict) -> dict | None:
    from datetime import timedelta
    try:
        end = datetime.today()
        start = end - timedelta(days=40)
        df = _fdr.DataReader(info["code"], start, end)
        if df.empty or len(df) < 3:
            return None
        df = df.tail(22)  # 최근 22거래일

        closes = df["Close"].tolist()
        dates = [d.strftime("%m/%d") for d in df.index]
        # 일별 수익률 (%)
        daily_returns = [0.0] + [
            round((closes[i] / closes[i - 1] - 1) * 100, 2)
            for i in range(1, len(closes))
        ]

        change_1d = daily_returns[-1]
        change_5d = round((closes[-1] / closes[-6] - 1) * 100, 2) if len(closes) >= 6 else 0.0
        change_20d = round((closes[-1] / closes[0] - 1) * 100, 2)
        high_20d = max(closes)
        from_high = round((closes[-1] / high_20d - 1) * 100, 2)
        streak = _calc_streak(daily_returns[1:])

        if change_5d >= 3 or streak >= 3:
            momentum = "상승"
        elif change_5d <= -3 or streak <= -3:
            momentum = "하락"
        elif abs(change_5d) < 1.5:
            momentum = "횡보"
        else:
            momentum = "상승" if change_5d > 0 else "하락"

        sparkline = [
            {"date": dates[i], "close": closes[i], "r": daily_returns[i]}
            for i in range(len(closes))
        ]

        return {
            "sector": info["sector"],
            "etf": info["etf"],
            "code": info["code"],
            "price": int(closes[-1]),
            "change_1d": change_1d,
            "change_5d": change_5d,
            "change_20d": change_20d,
            "from_high": from_high,
            "streak": streak,
            "momentum": momentum,
            "comment": _trend_comment(streak, change_5d, from_high),
            "sparkline": sparkline,
        }
    except Exception:
        return None


@app.get("/api/sector-trend")
async def get_sector_trend():
    now = _time.time()
    if _trend_cache["data"] and (now - _trend_cache["ts"]) < _TREND_TTL:
        return _trend_cache["data"]

    results = []
    for info in SECTOR_ETFS:
        data = _fetch_one_sector(info)
        if data:
            results.append(data)

    results.sort(key=lambda x: x["change_5d"], reverse=True)
    out = {"sectors": results, "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
    _trend_cache["data"] = out
    _trend_cache["ts"] = now
    return out


@app.post("/api/sector-trend/refresh")
async def refresh_sector_trend():
    _trend_cache["ts"] = 0.0
    return await get_sector_trend()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8001, reload=True)
