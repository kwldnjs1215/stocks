from __future__ import annotations

import json
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_PATH = DATA_DIR / "portfolio_data.json"
IMPORT_DIR = BASE_DIR.parent / "stocks-claude"
MONTHS = [f"{month}월" for month in range(1, 13)]
DEFAULT_SECTION_NAMES = ["미국주식", "국내주식"]
SECTION_CURRENCIES = {"미국주식": "USD", "국내주식": "KRW"}
DEFAULT_USD_TO_KRW = 1350
DEFAULT_INITIAL_PRINCIPAL_KRW = 9_378_327
USER_DEPOSIT_TYPES = {"이체입금", "오픈뱅킹은행입금이체"}
USER_WITHDRAWAL_TYPES = {"이체출금", "은행이체출금", "간편송금 계좌출금", "미약정대체출금"}


@dataclass
class StockColumn:
    name: str
    realized: bool = False

    @property
    def display_name(self) -> str:
        return f"{self.name}+" if self.realized else self.name


@dataclass
class PortfolioSection:
    name: str
    stocks: list[StockColumn] = field(default_factory=list)
    rows: dict[str, dict[str, int]] = field(default_factory=dict)

    def ensure_months(self) -> None:
        for month in MONTHS:
            self.rows.setdefault(month, {})
            for stock in self.stocks:
                self.rows[month].setdefault(stock.name, 0)

    def section_total(self) -> int:
        return sum(sum(values.values()) for values in self.rows.values())

    def month_total(self, month: str) -> int:
        return sum(self.rows.get(month, {}).values())

    def stock_names(self) -> list[str]:
        return [stock.name for stock in self.stocks]


class HtmlTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_cell = False
        self.current: list[str] = []
        self.rows: list[list[str]] = []
        self.buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
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
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def parse_trade_date(value: str) -> date:
    return datetime.strptime(value.strip(), "%Y.%m.%d").date()


def normalize_stock_input(raw_name: str) -> tuple[str, bool]:
    cleaned = raw_name.strip()
    realized = cleaned.endswith("+")
    if realized:
        cleaned = cleaned[:-1].strip()
    return cleaned, realized


def parse_stock_header(header: str) -> StockColumn:
    name, realized = normalize_stock_input(header)
    return StockColumn(name=name or header.strip(), realized=realized)


def get_default_section_name(index: int) -> str:
    if index <= len(DEFAULT_SECTION_NAMES):
        return DEFAULT_SECTION_NAMES[index - 1]
    return f"그룹 {index}"


def is_placeholder_section_name(name: str) -> bool:
    normalized = name.replace(" ", "").lower()
    return normalized in {"그룹1", "그룹2", "group1", "group2"}


def build_empty_section(name: str) -> PortfolioSection:
    section = PortfolioSection(name=name)
    section.ensure_months()
    return section


def build_default_portfolio() -> list[PortfolioSection]:
    return [build_empty_section(name) for name in DEFAULT_SECTION_NAMES]


def section_to_dict(section: PortfolioSection) -> dict[str, Any]:
    return {
        "name": section.name,
        "stocks": [{"name": stock.name, "realized": stock.realized} for stock in section.stocks],
        "rows": section.rows,
    }


def load_json_data() -> dict[str, Any]:
    if not DATA_PATH.exists():
        return {"sections": []}

    try:
        return json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"sections": []}


def build_section_from_dict(item: dict[str, Any], index: int) -> PortfolioSection:
    section_name = item.get("name") or get_default_section_name(index)
    if is_placeholder_section_name(section_name):
        section_name = get_default_section_name(index)

    stocks = [
        StockColumn(name=stock.get("name", "").strip(), realized=bool(stock.get("realized", False)))
        for stock in item.get("stocks", [])
        if stock.get("name", "").strip()
    ]
    section = PortfolioSection(
        name=section_name,
        stocks=stocks,
    )

    raw_rows = item.get("rows", {})
    for month in MONTHS:
        month_values = raw_rows.get(month, {})
        section.rows[month] = {
            stock.name: parse_int(month_values.get(stock.name, 0)) for stock in section.stocks
        }

    section.ensure_months()
    return section


def load_portfolio() -> list[PortfolioSection]:
    raw_data = load_json_data()
    raw_sections = raw_data.get("sections", [])
    if not raw_sections:
        return build_default_portfolio()

    sections = [build_section_from_dict(item, index) for index, item in enumerate(raw_sections, start=1)]
    if not sections:
        return build_default_portfolio()
    return sections


def get_settings() -> dict[str, Any]:
    raw_data = load_json_data()
    return {
        "owner_name": raw_data.get("owner_name", ""),
        "baseline_principal_krw": parse_int(
            raw_data.get("baseline_principal_krw", raw_data.get("initial_principal_krw", DEFAULT_INITIAL_PRINCIPAL_KRW))
        ) or DEFAULT_INITIAL_PRINCIPAL_KRW,
        "usd_to_krw_rate": parse_int(raw_data.get("usd_to_krw_rate", DEFAULT_USD_TO_KRW)) or DEFAULT_USD_TO_KRW,
        "cash_flows": raw_data.get("cash_flows", []),
    }


def save_portfolio(sections: list[PortfolioSection]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    current = load_json_data()
    payload = {
        "owner_name": current.get("owner_name", ""),
        "baseline_principal_krw": parse_int(
            current.get("baseline_principal_krw", current.get("initial_principal_krw", DEFAULT_INITIAL_PRINCIPAL_KRW))
        ) or DEFAULT_INITIAL_PRINCIPAL_KRW,
        "usd_to_krw_rate": parse_int(current.get("usd_to_krw_rate", DEFAULT_USD_TO_KRW)) or DEFAULT_USD_TO_KRW,
        "cash_flows": current.get("cash_flows", []),
        "sections": [section_to_dict(section) for section in sections],
    }
    DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def save_settings(
    owner_name: str,
    baseline_principal_krw: int,
    usd_to_krw_rate: int,
    cash_flows: list[dict[str, Any]],
) -> None:
    current = load_json_data()
    payload = {
        "owner_name": owner_name,
        "baseline_principal_krw": baseline_principal_krw or DEFAULT_INITIAL_PRINCIPAL_KRW,
        "usd_to_krw_rate": usd_to_krw_rate or DEFAULT_USD_TO_KRW,
        "cash_flows": cash_flows,
        "sections": current.get("sections", []),
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


@st.cache_data(show_spinner=False)
def parse_html_table(path_str: str) -> list[dict[str, str]]:
    parser = HtmlTableParser()
    parser.feed(Path(path_str).read_text(encoding="euc-kr"))
    if not parser.rows:
        return []
    header = parser.rows[0]
    records = []
    for row in parser.rows[1:]:
        padded = row + [""] * (len(header) - len(row))
        records.append(dict(zip(header, padded)))
    return records


@st.cache_data(show_spinner=False)
def load_cash_records() -> list[dict[str, str]]:
    file_path = IMPORT_DIR / "입출금거래내역_김지원_2021.01.01_2026.04.17.xls"
    if not file_path.exists():
        return []
    return parse_html_table(str(file_path))


@st.cache_data(show_spinner=False)
def load_trade_records() -> list[dict[str, str]]:
    paths = sorted(IMPORT_DIR.glob("종합거래내역(간략)_김지원_*.xls"))
    records: list[dict[str, str]] = []
    for path in paths:
        records.extend(parse_html_table(str(path)))
    records.sort(key=lambda item: item.get("실거래일자", ""))
    return records


def add_stock_to_section(section: PortfolioSection, raw_name: str, realized: bool) -> str:
    stock_name = raw_name.strip()
    if not stock_name:
        return "종목 이름을 입력해주세요."

    existing = next((stock for stock in section.stocks if stock.name == stock_name), None)
    if existing:
        existing.realized = existing.realized or realized
    else:
        section.stocks.append(StockColumn(name=stock_name, realized=realized))
        for month in MONTHS:
            section.rows.setdefault(month, {})[stock_name] = 0
    return ""


def build_month_dataframe(section: PortfolioSection) -> pd.DataFrame:
    records = []
    for month in MONTHS:
        row = {"월": month}
        for stock in section.stocks:
            row[stock.display_name] = section.rows[month].get(stock.name, 0)
        row["월 합계"] = section.month_total(month)
        records.append(row)
    return pd.DataFrame(records)


def build_month_summary_dataframe(section: PortfolioSection) -> pd.DataFrame:
    cumulative = 0
    records = []
    for month in MONTHS:
        month_profit = section.month_total(month)
        cumulative += month_profit
        records.append({"월": month, "월 수익": month_profit, "누적 수익": cumulative})
    return pd.DataFrame(records)


def build_cumulative_stock_dataframe(section: PortfolioSection) -> pd.DataFrame:
    cumulative_by_stock = {stock.name: 0 for stock in section.stocks}
    records: list[dict[str, int | str]] = []

    for month in MONTHS:
        row: dict[str, int | str] = {"월": month}
        for stock in section.stocks:
            cumulative_by_stock[stock.name] += section.rows[month].get(stock.name, 0)
            row[stock.display_name] = cumulative_by_stock[stock.name]
        records.append(row)

    frame = pd.DataFrame(records)
    if "월" in frame.columns:
        frame = frame.set_index("월")
    return frame


def format_amount(value: int, currency: str) -> str:
    sign = "+" if value > 0 else ""
    if currency == "USD":
        return f"{sign}${value:,}"
    return f"{sign}{value:,}"


def get_currency(section_name: str) -> str:
    return SECTION_CURRENCIES.get(section_name, "KRW")


def calculate_rate(profit: int, principal: int) -> float:
    if principal <= 0:
        return 0.0
    return (profit / principal) * 100


def convert_profit_to_krw(section: PortfolioSection, amount: int, usd_to_krw_rate: int) -> int:
    if get_currency(section.name) == "USD":
        return round(amount * usd_to_krw_rate)
    return amount


def calculate_current_principal(settings: dict[str, Any]) -> int:
    total = parse_int(settings.get("baseline_principal_krw", DEFAULT_INITIAL_PRINCIPAL_KRW))
    for flow in settings.get("cash_flows", []):
        amount = parse_int(flow.get("amount", 0))
        flow_type = str(flow.get("type", "")).strip()
        if flow_type == "입금":
            total += amount
        elif flow_type == "출금":
            total -= amount
    return total


def build_cash_flow_dataframe(cash_flows: list[dict[str, Any]]) -> pd.DataFrame:
    records = [
        {
            "날짜": flow.get("date", ""),
            "유형": flow.get("type", ""),
            "금액": parse_int(flow.get("amount", 0)),
            "메모": flow.get("memo", ""),
        }
        for flow in cash_flows
    ]
    return pd.DataFrame(records)


def get_current_year_profit_krw(sections: list[PortfolioSection], usd_to_krw_rate: int) -> int:
    return sum(convert_profit_to_krw(section, section.section_total(), usd_to_krw_rate) for section in sections)


def get_latest_current_year_profit_krw(sections: list[PortfolioSection], usd_to_krw_rate: int) -> tuple[str, int]:
    for month in reversed(MONTHS):
        total = sum(convert_profit_to_krw(section, section.month_total(month), usd_to_krw_rate) for section in sections)
        if total != 0:
            return month, total
    return "-", 0


def compute_yearly_principal_map(settings: dict[str, Any]) -> tuple[dict[int, int], dict[int, int]]:
    yearly_delta = defaultdict(int)
    for record in load_cash_records():
        trade_type = record.get("거래유형", "").strip()
        detail_type = record.get("거래종류", "").strip()
        amount = parse_int(record.get("거래금액", 0))
        year = parse_trade_date(record.get("실거래일자", "")).year
        if trade_type == "입금" and detail_type in USER_DEPOSIT_TYPES:
            yearly_delta[year] += amount
        elif trade_type == "출금" and detail_type in USER_WITHDRAWAL_TYPES:
            yearly_delta[year] -= amount

    for flow in settings.get("cash_flows", []):
        flow_date = str(flow.get("date", "")).strip()
        if not flow_date:
            continue
        year = datetime.strptime(flow_date, "%Y-%m-%d").year
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
    inventory: dict[tuple[str, str], deque[dict[str, Any]]] = defaultdict(deque)
    annual: dict[int, dict[str, Any]] = defaultdict(
        lambda: {"profit_krw": 0, "sells": 0, "wins": 0, "losses": 0, "hold_days": 0.0}
    )
    symbol_profit: dict[str, int] = defaultdict(int)
    symbol_count: dict[str, int] = defaultdict(int)
    symbol_trade_count: dict[str, int] = defaultdict(int)
    monthly_profit: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    buy_count = 0
    sell_count = 0
    usd_trade_count = 0
    krw_trade_count = 0

    for record in records:
        action = record.get("거래유형", "").strip()
        if action not in {"매수", "매도"}:
            continue
        detail = record.get("상세내용", "").strip()
        symbol = record.get("종목명", "").strip() or "기타"
        trade_date = parse_trade_date(record.get("실거래일자", ""))
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
        cost_basis = 0.0
        hold_days = 0.0
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

    annual_df = pd.DataFrame(
        [
            {
                "year": year,
                "realized_profit_krw": values["profit_krw"],
                "sells": values["sells"],
                "wins": values["wins"],
                "losses": values["losses"],
                "win_rate": (values["wins"] / values["sells"] * 100) if values["sells"] else 0.0,
                "avg_hold_days": (values["hold_days"] / values["sells"]) if values["sells"] else 0.0,
            }
            for year, values in sorted(annual.items())
        ]
    )
    symbol_profit_df = (
        pd.DataFrame([{"종목명": key, "실현손익(원화)": value} for key, value in symbol_profit.items()])
        .sort_values("실현손익(원화)", ascending=False)
        if symbol_profit
        else pd.DataFrame(columns=["종목명", "실현손익(원화)"])
    )
    symbol_count_df = (
        pd.DataFrame([{"종목명": key, "매도횟수": value} for key, value in symbol_count.items()])
        .sort_values("매도횟수", ascending=False)
        if symbol_count
        else pd.DataFrame(columns=["종목명", "매도횟수"])
    )
    symbol_trade_df = (
        pd.DataFrame([{"종목명": key, "거래횟수": value} for key, value in symbol_trade_count.items()])
        .sort_values("거래횟수", ascending=False)
        if symbol_trade_count
        else pd.DataFrame(columns=["종목명", "거래횟수"])
    )
    return {
        "annual_df": annual_df,
        "symbol_profit_df": symbol_profit_df,
        "symbol_count_df": symbol_count_df,
        "symbol_trade_df": symbol_trade_df,
        "monthly_profit": {year: dict(values) for year, values in monthly_profit.items()},
        "buy_count": buy_count,
        "sell_count": sell_count,
        "usd_trade_count": usd_trade_count,
        "krw_trade_count": krw_trade_count,
    }


def build_yearly_summary_df(settings: dict[str, Any]) -> pd.DataFrame:
    analytics = compute_trade_analytics(parse_int(settings.get("usd_to_krw_rate", DEFAULT_USD_TO_KRW)))
    annual_df = analytics["annual_df"].copy()
    if annual_df.empty:
        return annual_df
    yearly_delta, year_end_principal = compute_yearly_principal_map(settings)
    annual_df["연도 반영 원금"] = annual_df["year"].map(lambda year: year_end_principal.get(year, 0))
    annual_df["연간 원금 변동"] = annual_df["year"].map(lambda year: yearly_delta.get(year, 0))
    annual_df["원금대비 수익률"] = annual_df.apply(
        lambda row: calculate_rate(int(row["realized_profit_krw"]), int(row["연도 반영 원금"])),
        axis=1,
    )
    return annual_df


def infer_trading_style(annual_df: pd.DataFrame, buy_count: int, sell_count: int) -> tuple[str, list[str]]:
    avg_hold_days = annual_df["avg_hold_days"].mean() if not annual_df.empty else 0.0
    trades_per_year = (buy_count + sell_count) / max(len(annual_df), 1)

    if avg_hold_days <= 10:
        style = "초단기 스윙형"
    elif avg_hold_days <= 35:
        style = "단기 스윙형"
    elif avg_hold_days <= 90:
        style = "중기 보유형"
    else:
        style = "장기 보유형"

    traits = []
    if trades_per_year >= 25:
        traits.append("회전율이 높은 편이라 기회 포착은 빠르지만 과매매 위험이 있습니다.")
    else:
        traits.append("거래 빈도가 과하지 않아 손실 통제에는 유리한 편입니다.")

    if avg_hold_days <= 20:
        traits.append("짧게 들어갔다가 빠르게 정리하는 패턴이 강합니다.")
    elif avg_hold_days >= 60:
        traits.append("버티는 힘이 있는 편이라 추세를 길게 먹는 타입에 가깝습니다.")
    else:
        traits.append("너무 짧지도 길지도 않은 중간 보유 성향이 보입니다.")

    return style, traits


def build_improvement_tips(
    annual_df: pd.DataFrame,
    symbol_profit_df: pd.DataFrame,
    symbol_trade_df: pd.DataFrame,
    buy_count: int,
    sell_count: int,
) -> list[str]:
    tips: list[str] = []
    avg_hold_days = annual_df["avg_hold_days"].mean() if not annual_df.empty else 0.0
    overall_win_rate = (annual_df["wins"].sum() / max(annual_df["sells"].sum(), 1)) * 100 if not annual_df.empty else 0.0
    trades_per_year = (buy_count + sell_count) / max(len(annual_df), 1)

    if trades_per_year >= 25:
        tips.append("진입 이유와 청산 이유를 한 줄로 남겨서, 반복 매매 중 성과 없는 패턴을 빨리 끊는 게 좋습니다.")
    if avg_hold_days <= 12:
        tips.append("짧은 보유 비중이 높아서, 일부는 목표 수익 구간을 더 길게 가져가는 연습이 수익률 개선에 도움될 수 있습니다.")
    if overall_win_rate < 50:
        tips.append("승률보다 손익비가 중요한 구간으로 보이니, 손절 기준과 익절 기준을 숫자로 고정해두는 편이 좋습니다.")
    else:
        tips.append("승률은 괜찮은 편이라, 수익이 나는 종목을 조금 더 오래 들고 가는 쪽이 전체 수익률을 끌어올릴 수 있습니다.")

    if not symbol_trade_df.empty:
        top_symbol = symbol_trade_df.iloc[0]
        tips.append(f"`{top_symbol['종목명']}`처럼 자주 보는 종목은 진입 타점 기록을 따로 모아서 본인만의 패턴북을 만드는 게 좋습니다.")
    if not symbol_profit_df.empty and len(symbol_profit_df) >= 2:
        worst_symbol = symbol_profit_df.iloc[-1]
        if int(worst_symbol["실현손익(원화)"]) < 0:
            tips.append(f"`{worst_symbol['종목명']}` 계열은 손실 반복 가능성이 있으니, 다음에는 비중을 줄이거나 1회 진입 금액 상한을 정해보는 걸 추천합니다.")

    return tips[:4]


def initialize_state() -> None:
    st.session_state.sections = load_portfolio()
    st.session_state.settings = get_settings()

def render_navigation() -> str:
    st.sidebar.title("메뉴")
    return st.sidebar.radio("페이지", ["대시보드", "매매 입력", "입출금내역 관리", "분석"], label_visibility="collapsed")


def render_dashboard(sections: list[PortfolioSection], settings: dict[str, Any]) -> None:
    current_year = date.today().year
    usd_to_krw_rate = parse_int(settings.get("usd_to_krw_rate", DEFAULT_USD_TO_KRW)) or DEFAULT_USD_TO_KRW
    current_principal = calculate_current_principal(settings)
    current_profit_krw = get_current_year_profit_krw(sections, usd_to_krw_rate)
    latest_month, latest_profit_krw = get_latest_current_year_profit_krw(sections, usd_to_krw_rate)

    st.title("주식 관리 대시보드")
    st.write("메인에서는 연도별 수익률과 현재 연도 수익 흐름을 같이 보도록 정리했습니다.")

    st.markdown(
        f"""
        <div style="padding: 1.15rem 1.25rem; border: 1px solid #f0d6d6; border-radius: 18px; background: linear-gradient(180deg, #fff7f7 0%, #fff 100%);">
            <div style="font-size: 0.95rem; color: #6b7280;">현재 기준 총 수익</div>
            <div style="margin-top: 0.45rem; font-size: 2.5rem; font-weight: 800; color: #d90429;">{format_amount(current_profit_krw, 'KRW')}</div>
            <div style="margin-top: 0.85rem; font-size: 0.92rem; color: #4b5563;">현재 반영 원금: {format_amount(current_principal, 'KRW')}</div>
            <div style="margin-top: 0.3rem; font-size: 0.92rem; color: #4b5563;">누적 수익률: {calculate_rate(current_profit_krw, current_principal):.2f}%</div>
            <div style="margin-top: 0.3rem; font-size: 0.92rem; color: #4b5563;">가장 최근 수익률: {latest_month} / {calculate_rate(latest_profit_krw, current_principal):.2f}%</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    yearly_df = build_yearly_summary_df(settings)
    if not yearly_df.empty:
        st.subheader("연도별 원금 대비 수익률")
        tabs = st.tabs([f"{int(row['year'])}년" for _, row in yearly_df.iterrows()])
        for tab, (_, row) in zip(tabs, yearly_df.iterrows()):
            with tab:
                cols = st.columns(4)
                cols[0].metric("실현손익", format_amount(int(row["realized_profit_krw"]), "KRW"))
                cols[1].metric("연도 반영 원금", format_amount(int(row["연도 반영 원금"]), "KRW"))
                cols[2].metric("원금 변동", format_amount(int(row["연간 원금 변동"]), "KRW"))
                cols[3].metric("수익률", f"{row['원금대비 수익률']:.2f}%")
                st.caption(f"매도 {int(row['sells'])}회, 승률 {row['win_rate']:.1f}%, 평균 보유일 {row['avg_hold_days']:.1f}일")

    st.divider()
    st.subheader(f"{current_year}년 수익 입력 현황")
    top_columns = st.columns(max(len(sections), 1))
    for column, section in zip(top_columns, sections):
        with column:
            currency = get_currency(section.name)
            st.markdown(
                f"""
                <div style="padding: 1.1rem 1.2rem; border: 1px solid #f0d6d6; border-radius: 18px; background: linear-gradient(180deg, #fff7f7 0%, #fff 100%);">
                    <div style="font-size: 0.95rem; color: #6b7280;">{section.name} {current_year}년 총 수익</div>
                    <div style="margin-top: 0.45rem; font-size: 2.1rem; font-weight: 800; color: #d90429;">{format_amount(section.section_total(), currency)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.divider()
    market_columns = st.columns(max(len(sections), 1))
    for column, section in zip(market_columns, sections):
        with column:
            currency = get_currency(section.name)
            st.subheader(section.name)
            summary_df = build_month_summary_dataframe(section).copy()
            summary_df["월 수익"] = summary_df["월 수익"].map(lambda value: format_amount(int(value), currency))
            summary_df["누적 수익"] = summary_df["누적 수익"].map(lambda value: format_amount(int(value), currency))
            st.dataframe(summary_df, use_container_width=True, hide_index=True)
            cumulative_df = build_cumulative_stock_dataframe(section)
            st.caption(f"종목별 누적 수익 그래프 ({currency})")
            if cumulative_df.empty or cumulative_df.shape[1] == 0:
                st.info("등록된 종목이 아직 없습니다.")
            else:
                st.area_chart(cumulative_df)
            with st.expander(f"{section.name} 월별 상세 내역", expanded=False):
                st.dataframe(build_month_dataframe(section), use_container_width=True, hide_index=True)


def render_trade_input_page(sections: list[PortfolioSection]) -> None:
    st.title("매매 입력")
    st.write("수익 입력과 종목 추가를 이 페이지에서 같이 처리할 수 있게 했습니다.")
    section_names = [section.name for section in sections]
    left, right = st.columns(2)

    with left:
        with st.form("profit-entry-form", clear_on_submit=True):
            selected_section_name = st.selectbox("시장", section_names)
            month = st.selectbox("월", MONTHS)
            stock_input = st.text_input("종목명", placeholder="예: 삼성전자 또는 엔비디아+")
            amount = st.number_input("수익 금액", step=1, value=0)
            submit = st.form_submit_button("수익 반영")
        if submit:
            section = next(section for section in sections if section.name == selected_section_name)
            stock_name, realized = normalize_stock_input(stock_input)
            if not stock_name:
                st.warning("종목명을 먼저 입력해주세요.")
            else:
                error = add_stock_to_section(section, stock_name, realized)
                if error:
                    st.warning(error)
                else:
                    section.rows[month][stock_name] = section.rows[month].get(stock_name, 0) + parse_int(amount)
                    save_portfolio(sections)
                    st.success(f"{month} / {stock_name} 수익을 저장했습니다.")

    with right:
        with st.form("stock-add-form", clear_on_submit=True):
            selected_section_name = st.selectbox("추가할 시장", section_names, key="trade-page-section")
            new_stock = st.text_input("새 종목명", placeholder="예: TQQQ 또는 동국제약")
            stock_submit = st.form_submit_button("종목 추가")
        if stock_submit:
            section = next(section for section in sections if section.name == selected_section_name)
            stock_name, realized = normalize_stock_input(new_stock)
            if not stock_name:
                st.warning("추가할 종목명을 입력해주세요.")
            else:
                error = add_stock_to_section(section, stock_name, realized)
                if error:
                    st.warning(error)
                else:
                    save_portfolio(sections)
                    st.success(f"{section.name}에 {stock_name} 종목을 추가했습니다.")


def render_cashflow_page(settings: dict[str, Any]) -> None:
    st.title("입출금내역 관리")
    st.write("파일 기준 원금 위에 이후 입출금만 추가해서 현재 원금을 관리할 수 있습니다.")
    baseline = parse_int(settings.get("baseline_principal_krw", DEFAULT_INITIAL_PRINCIPAL_KRW))
    current = calculate_current_principal(settings)
    cols = st.columns(3)
    cols[0].metric("파일 기준 원금", format_amount(baseline, "KRW"))
    cols[1].metric("수동 반영 증감", format_amount(current - baseline, "KRW"))
    cols[2].metric("현재 반영 원금", format_amount(current, "KRW"))

    with st.form("cashflow-add-form", clear_on_submit=True):
        flow_date = st.date_input("날짜", value=date.today(), format="YYYY-MM-DD")
        flow_type = st.selectbox("유형", ["입금", "출금"])
        flow_amount = st.number_input("금액", min_value=0, step=10000, value=0)
        flow_memo = st.text_input("메모", placeholder="예: 추가 입금, 생활비 출금")
        submit = st.form_submit_button("입출금 저장")
    if submit:
        if parse_int(flow_amount) <= 0:
            st.warning("금액은 0보다 크게 입력해주세요.")
        else:
            cash_flows = list(settings.get("cash_flows", []))
            cash_flows.append({"date": flow_date.isoformat(), "type": flow_type, "amount": parse_int(flow_amount), "memo": flow_memo.strip()})
            save_settings(
                owner_name=str(settings.get("owner_name", "")),
                baseline_principal_krw=baseline,
                usd_to_krw_rate=parse_int(settings.get("usd_to_krw_rate", DEFAULT_USD_TO_KRW)) or DEFAULT_USD_TO_KRW,
                cash_flows=cash_flows,
            )
            st.session_state.settings = get_settings()
            st.success("입출금 내역을 저장했습니다.")

    cash_flow_df = build_cash_flow_dataframe(list(st.session_state.settings.get("cash_flows", [])))
    if cash_flow_df.empty:
        st.write("추가한 입출금 내역이 아직 없습니다.")
    else:
        display_df = cash_flow_df.copy()
        display_df["금액"] = display_df["금액"].map(lambda value: format_amount(int(value), "KRW"))
        st.dataframe(display_df, use_container_width=True, hide_index=True)


def render_analysis_page(settings: dict[str, Any]) -> None:
    st.title("분석")
    st.write("종합거래내역을 기준으로 실현손익과 매매 습관을 요약했습니다.")
    analytics = compute_trade_analytics(parse_int(settings.get("usd_to_krw_rate", DEFAULT_USD_TO_KRW)))
    annual_df = analytics["annual_df"]
    symbol_profit_df = analytics["symbol_profit_df"]
    symbol_count_df = analytics["symbol_count_df"]
    symbol_trade_df = analytics["symbol_trade_df"]
    if annual_df.empty:
        st.info("분석할 매도 내역이 아직 없습니다.")
        return

    buy_count = int(analytics["buy_count"])
    sell_count = int(analytics["sell_count"])
    usd_trade_count = int(analytics["usd_trade_count"])
    krw_trade_count = int(analytics["krw_trade_count"])
    total_sells = int(annual_df["sells"].sum())
    total_wins = int(annual_df["wins"].sum())
    total_profit = int(annual_df["realized_profit_krw"].sum())
    avg_hold_days = annual_df["avg_hold_days"].mean()
    style_label, style_traits = infer_trading_style(annual_df, buy_count, sell_count)
    improvement_tips = build_improvement_tips(annual_df, symbol_profit_df, symbol_trade_df, buy_count, sell_count)

    cols = st.columns(4)
    cols[0].metric("총 매도 횟수", total_sells)
    cols[1].metric("전체 승률", f"{(total_wins / total_sells * 100) if total_sells else 0:.1f}%")
    cols[2].metric("총 실현손익", format_amount(total_profit, "KRW"))
    cols[3].metric("평균 보유일", f"{avg_hold_days:.1f}일")

    st.subheader("내 매매 스타일")
    st.markdown(
        f"""
        <div style="padding: 1rem 1.1rem; border: 1px solid #dde7f5; border-radius: 16px; background: linear-gradient(180deg, #f8fbff 0%, #ffffff 100%);">
            <div style="font-size: 0.95rem; color: #5b6472;">스타일 판정</div>
            <div style="margin-top: 0.35rem; font-size: 1.8rem; font-weight: 800; color: #0f4c81;">{style_label}</div>
            <div style="margin-top: 0.7rem; font-size: 0.92rem; color: #4b5563;">총 매수 {buy_count}회 / 총 매도 {sell_count}회</div>
            <div style="margin-top: 0.25rem; font-size: 0.92rem; color: #4b5563;">미국 거래 {usd_trade_count}회 / 국내 거래 {krw_trade_count}회</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.subheader("패턴 요약")
    for trait in style_traits:
        st.write(f"- {trait}")
    if not symbol_profit_df.empty:
        best = symbol_profit_df.iloc[0]
        worst = symbol_profit_df.iloc[-1]
        st.write(f"- 가장 수익이 좋았던 종목은 `{best['종목명']}`이고 실현손익은 `{format_amount(int(best['실현손익(원화)']), 'KRW')}`입니다.")
        st.write(f"- 가장 아쉬웠던 종목은 `{worst['종목명']}`이고 실현손익은 `{format_amount(int(worst['실현손익(원화)']), 'KRW')}`입니다.")
    if not symbol_count_df.empty:
        top_count = symbol_count_df.iloc[0]
        st.write(f"- 가장 자주 매도한 종목은 `{top_count['종목명']}`으로 `{int(top_count['매도횟수'])}회` 정리했습니다.")
    if not symbol_trade_df.empty:
        favorite = symbol_trade_df.iloc[0]
        st.write(f"- 가장 자주 거래한 종목은 `{favorite['종목명']}`으로 총 `{int(favorite['거래횟수'])}회` 매매했습니다.")

    st.subheader("수익률을 올리기 위해 해볼 것")
    for tip in improvement_tips:
        st.write(f"- {tip}")

    left, right = st.columns(2)
    with left:
        st.subheader("종목별 실현손익")
        if not symbol_profit_df.empty:
            st.bar_chart(symbol_profit_df.head(10).set_index("종목명"))
    with right:
        st.subheader("종목별 매도 횟수")
        if not symbol_count_df.empty:
            st.bar_chart(symbol_count_df.head(10).set_index("종목명"))

    st.subheader("연도별 실현손익")
    st.bar_chart(annual_df[["year", "realized_profit_krw"]].set_index("year"))
    selected_year = st.selectbox("월별 실현손익 보기", [int(year) for year in annual_df["year"].tolist()], index=len(annual_df) - 1)
    monthly_values = analytics["monthly_profit"].get(selected_year, {})
    monthly_df = pd.DataFrame({"월": MONTHS, "실현손익(원화)": [monthly_values.get(month, 0) for month in MONTHS]}).set_index("월")
    st.line_chart(monthly_df)


def main() -> None:
    st.set_page_config(page_title="주식 관리 대시보드", page_icon="📈", layout="wide")
    initialize_state()
    sections: list[PortfolioSection] = st.session_state.sections
    settings: dict[str, Any] = st.session_state.settings

    page = render_navigation()
    if page == "대시보드":
        render_dashboard(sections, settings)
    elif page == "매매 입력":
        render_trade_input_page(sections)
    elif page == "입출금내역 관리":
        render_cashflow_page(settings)
    else:
        render_analysis_page(settings)

    st.caption("저장 파일: `data/portfolio_data.json`")


if __name__ == "__main__":
    main()
