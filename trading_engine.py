from __future__ import annotations

import json
import math
import os
import time as _time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TRADING_STATE_PATH = DATA_DIR / "trading_state.json"
TRADING_RULES_PATH = DATA_DIR / "trading_rules.md"
TRADING_JOURNAL_DIR = DATA_DIR / "trading_journal"
LEGACY_TRADING_JOURNAL_PATH = DATA_DIR / "trading_journal.md"
KIS_TOKEN_PATH = BASE_DIR / ".kis_token.json"

DEFAULT_TRADING_CONFIG: dict[str, Any] = {
    "enabled": False,
    "dry_run": True,
    "market": "KR",
    "strategy_name": "surge_scalping",
    "open_scan_time": "09:03",
    "scan_end_time": "10:30",
    "universe_top_n": 50,
    "candidate_limit": 12,
    "capital_krw": 100_000,
    "max_positions": 1,
    "per_trade_budget_krw": 90_000,
    "min_stock_price_krw": 1_000,
    "max_stock_price_krw": 30_000,
    "min_trade_value_krw": 5_000_000_000,
    "min_intraday_range_pct": 3.0,
    "min_change_pct": 5.0,
    "buy_split_pct": [60, 40],
    "add_buy_pullback_pct": -0.6,
    "add_buy_breakout_pct": 0.8,
    "stop_loss_pct": -1.3,
    "take_profit_pct": 1.8,
    "sell_split_pct": [50, 50],
    "first_take_profit_pct": 0.8,
    "second_take_profit_pct": 1.8,
    "trailing_stop_pct": 0.6,
    "force_exit_time": "10:45",
    "cooldown_minutes": 10,
    "last_open_scan_date": "",
}

DEFAULT_RULES = """# 급등주 스캘핑 자동매매 원칙

## 운용 범위
- 국내 주식만 대상으로 한다.
- 장 초반 급등주만 대상으로 한다.
- 신규 진입은 09:03~10:30 사이만 허용한다.
- 기본 운용은 dry-run이며, 실주문은 별도 환경변수와 대시보드 설정이 모두 켜졌을 때만 허용한다.

## 진입 조건
- 가격은 1,000원~30,000원 사이를 우선한다.
- 전일 대비 +5% 이상 급등 중이어야 한다.
- 누적 거래대금 50억원 이상, 장중 변동폭 3% 이상이어야 한다.
- 분봉 기준으로는 VWAP 위, 직전 고점 재돌파, 거래량 재확대가 있어야 한다.
- 호가/수급 기준으로는 매도벽이 단순히 많은 게 아니라 실제 체결로 소화되는지 본다.

## 리스크 관리
- 총 실험 자금은 100,000원으로 시작한다.
- 1종목만 보유하고 90,000원 안에서 60% / 40%로 분할매수한다.
- 1차 매수는 조건 충족 시, 2차 매수는 눌림 후 재상승 또는 재돌파 때만 한다.
- 1차 익절은 +0.8%에서 절반, 2차 익절은 +1.8% 또는 트레일링 스탑으로 정리한다.
- 손절은 평균단가 기준 -1.3%에서 전량 정리한다.
- 10:45까지 남은 포지션은 청산 후보로 둔다.
- 매수/매도/관망의 이유는 `data/trading_journal/YYYY-MM-DD.md`에 날짜별로 누적한다.
"""


@dataclass
class KisConfig:
    app_key: str
    app_secret: str
    account_no: str
    account_product_code: str
    base_url: str
    mock: bool
    live_orders_enabled: bool

    @classmethod
    def from_env(cls) -> "KisConfig":
        mock = os.environ.get("KIS_MOCK", "true").lower() in {"1", "true", "yes", "y"}
        default_base = (
            "https://openapivts.koreainvestment.com:29443"
            if mock
            else "https://openapi.koreainvestment.com:9443"
        )
        account = os.environ.get("KIS_ACCOUNT_NO", os.environ.get("KIS_CANO", ""))
        return cls(
            app_key=os.environ.get("KIS_APP_KEY", os.environ.get("MYAPP", "")),
            app_secret=os.environ.get("KIS_APP_SECRET", os.environ.get("MYSEC", "")),
            account_no=account,
            account_product_code=os.environ.get("KIS_ACCOUNT_PRODUCT_CODE", os.environ.get("KIS_ACNT_PRDT_CD", "01")),
            base_url=os.environ.get("KIS_BASE_URL", default_base).rstrip("/"),
            mock=mock,
            live_orders_enabled=os.environ.get("KIS_ENABLE_LIVE_ORDERS", "false").lower() in {"1", "true", "yes", "y"},
        )

    @property
    def configured(self) -> bool:
        return bool(self.app_key and self.app_secret)


class KisClient:
    def __init__(self, config: KisConfig | None = None) -> None:
        self.config = config or KisConfig.from_env()

    def status(self) -> dict[str, Any]:
        token = self._load_token()
        return {
            "configured": self.config.configured,
            "mock": self.config.mock,
            "base_url": self.config.base_url,
            "account_configured": bool(self.config.account_no),
            "live_orders_enabled": self.config.live_orders_enabled,
            "token_cached": bool(token and token.get("access_token")),
            "token_expires_at": token.get("expires_at", 0) if token else 0,
        }

    def _load_token(self) -> dict[str, Any]:
        if not KIS_TOKEN_PATH.exists():
            return {}
        try:
            return json.loads(KIS_TOKEN_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _save_token(self, token: dict[str, Any]) -> None:
        KIS_TOKEN_PATH.write_text(json.dumps(token, ensure_ascii=False, indent=2), encoding="utf-8")

    def _access_token(self) -> str:
        if not self.config.configured:
            raise RuntimeError("KIS_APP_KEY/KIS_APP_SECRET 설정이 없습니다.")

        cached = self._load_token()
        if cached.get("access_token") and float(cached.get("expires_at", 0)) > _time.time() + 300:
            return str(cached["access_token"])

        resp = requests.post(
            f"{self.config.base_url}/oauth2/tokenP",
            headers={"content-type": "application/json"},
            json={
                "grant_type": "client_credentials",
                "appkey": self.config.app_key,
                "appsecret": self.config.app_secret,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        expires_in = int(data.get("expires_in", 86400))
        token = {
            "access_token": data["access_token"],
            "expires_at": _time.time() + expires_in,
        }
        self._save_token(token)
        return str(token["access_token"])

    def _headers(self, tr_id: str) -> dict[str, str]:
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self._access_token()}",
            "appkey": self.config.app_key,
            "appsecret": self.config.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }

    def _hashkey(self, body: dict[str, Any]) -> str:
        resp = requests.post(
            f"{self.config.base_url}/uapi/hashkey",
            headers={
                "content-type": "application/json; charset=utf-8",
                "appkey": self.config.app_key,
                "appsecret": self.config.app_secret,
            },
            json=body,
            timeout=10,
        )
        resp.raise_for_status()
        return str(resp.json().get("HASH", ""))

    def fetch_transaction_value_rank(self, limit: int) -> list[dict[str, Any]]:
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_COND_SCR_DIV_CODE": "20171",
            "FID_INPUT_ISCD": "0000",
            "FID_DIV_CLS_CODE": "0",
            "FID_BLNG_CLS_CODE": "0",
            "FID_TRGT_CLS_CODE": "111111111",
            "FID_TRGT_EXLS_CLS_CODE": "000000",
            "FID_INPUT_PRICE_1": "0",
            "FID_INPUT_PRICE_2": "0",
            "FID_VOL_CNT": "0",
        }
        resp = requests.get(
            f"{self.config.base_url}/uapi/domestic-stock/v1/quotations/volume-rank",
            headers=self._headers("FHPST01710000"),
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        payload = resp.json()
        rows = payload.get("output", [])
        if not isinstance(rows, list):
            rows = []

        candidates = []
        for row in rows[:limit]:
            price = _num(row.get("stck_prpr"))
            high = _num(row.get("stck_hgpr"))
            low = _num(row.get("stck_lwpr"))
            trade_value = _num(row.get("acml_tr_pbmn"))
            change_pct = _num(row.get("prdy_ctrt"))
            volume = _num(row.get("acml_vol"))
            code = str(row.get("mksc_shrn_iscd") or row.get("stck_shrn_iscd") or "").strip()
            name = str(row.get("hts_kor_isnm") or row.get("prdt_name") or code).strip()
            if not code:
                continue
            candidates.append(
                {
                    "code": code,
                    "name": name,
                    "price": int(price),
                    "high": int(high),
                    "low": int(low),
                    "change_pct": round(change_pct, 2),
                    "volume": int(volume),
                    "trade_value_krw": int(trade_value),
                    "source": "kis",
                }
            )
        return candidates

    def place_domestic_buy_order(self, code: str, quantity: int) -> dict[str, Any]:
        if not self.config.account_no:
            raise RuntimeError("KIS_ACCOUNT_NO 설정이 없습니다.")
        if quantity <= 0:
            raise RuntimeError("주문 수량이 0입니다.")
        if not self.config.live_orders_enabled:
            raise RuntimeError("KIS_ENABLE_LIVE_ORDERS가 false라 실주문을 막았습니다.")

        body = {
            "CANO": self.config.account_no,
            "ACNT_PRDT_CD": self.config.account_product_code,
            "PDNO": code,
            "ORD_DVSN": "01",
            "ORD_QTY": str(quantity),
            "ORD_UNPR": "0",
        }
        tr_id = "VTTC0802U" if self.config.mock else "TTTC0802U"
        headers = self._headers(tr_id)
        headers["hashkey"] = self._hashkey(body)
        resp = requests.post(
            f"{self.config.base_url}/uapi/domestic-stock/v1/trading/order-cash",
            headers=headers,
            json=body,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()


def _num(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return 0.0


def load_trading_state() -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not TRADING_STATE_PATH.exists():
        return {"config": DEFAULT_TRADING_CONFIG.copy(), "runs": [], "positions": []}
    try:
        raw = json.loads(TRADING_STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raw = {}
    config = DEFAULT_TRADING_CONFIG.copy()
    config.update(raw.get("config", {}))
    return {
        "config": config,
        "runs": raw.get("runs", []),
        "positions": raw.get("positions", []),
    }


def save_trading_state(state: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TRADING_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_trading_docs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TRADING_JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    if not TRADING_RULES_PATH.exists():
        TRADING_RULES_PATH.write_text(DEFAULT_RULES, encoding="utf-8")
    today_path = trading_journal_path()
    if not today_path.exists():
        today_path.write_text(f"# {today_path.stem} 급등주 스캘핑 매매일지\n", encoding="utf-8")


def trading_journal_path(day: str | None = None) -> Path:
    date_key = day or datetime.now().strftime("%Y-%m-%d")
    return TRADING_JOURNAL_DIR / f"{date_key}.md"


def read_trading_rules() -> str:
    ensure_trading_docs()
    return TRADING_RULES_PATH.read_text(encoding="utf-8")


def write_trading_rules(content: str) -> str:
    ensure_trading_docs()
    text = content.strip() + "\n"
    TRADING_RULES_PATH.write_text(text, encoding="utf-8")
    return text


def append_rule_note(note: str) -> str:
    ensure_trading_docs()
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    text = TRADING_RULES_PATH.read_text(encoding="utf-8").rstrip()
    text = f"{text}\n\n## {stamp} 메모\n{note.strip()}\n"
    TRADING_RULES_PATH.write_text(text, encoding="utf-8")
    return text


def list_trading_journal_dates() -> list[str]:
    ensure_trading_docs()
    return sorted([p.stem for p in TRADING_JOURNAL_DIR.glob("*.md")], reverse=True)


def read_trading_journal(day: str | None = None, tail_chars: int = 12000) -> str:
    ensure_trading_docs()
    path = trading_journal_path(day)
    if not path.exists():
        return f"# {path.stem} 급등주 스캘핑 매매일지\n\n아직 기록이 없습니다.\n"
    text = path.read_text(encoding="utf-8")
    return text[-tail_chars:]


def _demo_candidates(limit: int) -> list[dict[str, Any]]:
    demo = [
        ("900110", "급등테스트A", 7250, 7680, 6890, 12.4, 8_400_000_000),
        ("900120", "급등테스트B", 14380, 15120, 13600, 8.7, 12_700_000_000),
        ("900130", "급등테스트C", 28600, 30100, 27150, 6.2, 6_200_000_000),
        ("900140", "과열테스트D", 41200, 43900, 38650, 14.5, 21_900_000_000),
        ("900150", "저유동테스트E", 3180, 3370, 3090, 7.1, 1_400_000_000),
    ]
    return [
        {
            "code": code,
            "name": name,
            "price": price,
            "high": high,
            "low": low,
            "change_pct": change,
            "volume": 0,
            "trade_value_krw": value,
            "source": "demo",
        }
        for code, name, price, high, low, change, value in demo[:limit]
    ]


def score_candidate(candidate: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    price = max(float(candidate.get("price", 0)), 1.0)
    intraday_range_pct = ((float(candidate.get("high", 0)) - float(candidate.get("low", 0))) / price) * 100
    change_pct = float(candidate.get("change_pct", 0))
    trade_value = float(candidate.get("trade_value_krw", 0))
    min_stock_price = float(config.get("min_stock_price_krw", 1_000))
    max_stock_price = float(config.get("max_stock_price_krw", 30_000))

    liquidity_ok = trade_value >= float(config["min_trade_value_krw"])
    volatility_ok = intraday_range_pct >= float(config["min_intraday_range_pct"])
    momentum_ok = change_pct >= float(config["min_change_pct"])
    price_ok = min_stock_price <= price <= max_stock_price
    buy_signal = liquidity_ok and volatility_ok and momentum_ok and price_ok
    score = math.log10(max(trade_value, 1)) + intraday_range_pct * 1.1 + max(change_pct, 0) * 1.8

    reasons = [
        "급등주 스캘핑 후보",
        f"거래대금 {int(trade_value):,}원",
        f"장중 변동폭 {intraday_range_pct:.2f}%",
        f"등락률 {change_pct:+.2f}%",
    ]
    if buy_signal:
        reasons.append("가격/유동성/변동성/급등률 기준 통과")
    else:
        failed = []
        if not liquidity_ok:
            failed.append("거래대금 부족")
        if not volatility_ok:
            failed.append("변동성 부족")
        if not momentum_ok:
            failed.append("급등률 부족")
        if not price_ok:
            failed.append("10만원 스캘핑 가격대 이탈")
        reasons.append("관망: " + ", ".join(failed))

    return {
        **candidate,
        "intraday_range_pct": round(intraday_range_pct, 2),
        "score": round(score, 2),
        "signal": "BUY" if buy_signal else "WATCH",
        "decision": "DRY_RUN_BUY" if buy_signal and config.get("dry_run", True) else ("BUY_READY" if buy_signal else "WATCH"),
        "reason": " / ".join(reasons),
        "risk": {
            "capital_krw": int(config["capital_krw"]),
            "budget_krw": int(config["per_trade_budget_krw"]),
            "buy_split_pct": config["buy_split_pct"],
            "sell_split_pct": config["sell_split_pct"],
            "stop_loss_pct": float(config["stop_loss_pct"]),
            "take_profit_pct": float(config["take_profit_pct"]),
            "first_take_profit_pct": float(config["first_take_profit_pct"]),
            "second_take_profit_pct": float(config["second_take_profit_pct"]),
            "trailing_stop_pct": float(config["trailing_stop_pct"]),
            "force_exit_time": str(config["force_exit_time"]),
        },
    }


def build_split_buy_plan(candidate: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    price = max(int(candidate.get("price", 0)), 1)
    budget = min(int(config["per_trade_budget_krw"]), int(config["capital_krw"]))
    split_pct = [float(x) for x in config.get("buy_split_pct", [50, 30, 20])]
    total_pct = sum(split_pct) or 100
    labels = ["초도 진입", "눌림 추가", "돌파 추가"]
    triggers = [
        "기준 통과 즉시",
        f"진입가 대비 {config['add_buy_pullback_pct']}% 눌림 후 재상승",
        f"진입가 대비 +{config['add_buy_breakout_pct']}% 돌파 유지",
    ]

    plan = []
    for idx, pct in enumerate(split_pct):
        leg_budget = int(budget * pct / total_pct)
        quantity = leg_budget // price
        if quantity <= 0:
            continue
        plan.append(
            {
                "leg": idx + 1,
                "label": labels[idx] if idx < len(labels) else f"{idx + 1}차 매수",
                "trigger": triggers[idx] if idx < len(triggers) else "조건 충족",
                "budget_krw": leg_budget,
                "quantity": quantity,
            }
        )
    return plan


def build_split_sell_plan(total_quantity: int, config: dict[str, Any]) -> list[dict[str, Any]]:
    split_pct = [float(x) for x in config.get("sell_split_pct", [50, 50])]
    total_pct = sum(split_pct) or 100
    triggers = [
        f"평균단가 대비 +{config['first_take_profit_pct']}%",
        f"평균단가 대비 +{config['second_take_profit_pct']}% 또는 트레일링 스탑",
    ]
    plan = []
    remaining = total_quantity
    for idx, pct in enumerate(split_pct):
        if idx == len(split_pct) - 1:
            quantity = remaining
        else:
            quantity = min(int(total_quantity * pct / total_pct), remaining)
        remaining -= quantity
        if quantity <= 0:
            continue
        plan.append(
            {
                "leg": idx + 1,
                "trigger": triggers[idx] if idx < len(triggers) else "익절 조건",
                "quantity": quantity,
            }
        )
    return plan


def run_open_scan(force_demo: bool = False) -> dict[str, Any]:
    ensure_trading_docs()
    state = load_trading_state()
    config = state["config"]
    client = KisClient()
    warnings: list[str] = []

    try:
        if force_demo or not client.config.configured:
            raise RuntimeError("KIS 인증 정보가 없어 데모 후보로 계산했습니다.")
        raw_candidates = client.fetch_transaction_value_rank(int(config["universe_top_n"]))
    except Exception as exc:
        warnings.append(str(exc))
        raw_candidates = _demo_candidates(int(config["universe_top_n"]))

    ranked = [score_candidate(c, config) for c in raw_candidates]
    ranked.sort(key=lambda item: item["score"], reverse=True)
    candidates = ranked[: int(config["candidate_limit"])]
    buy_candidates = [c for c in candidates if c["signal"] == "BUY"][: int(config["max_positions"])]

    planned_orders = [
        {
            "side": "BUY",
            "code": c["code"],
            "name": c["name"],
            "budget_krw": int(config["per_trade_budget_krw"]),
            "quantity": sum(leg["quantity"] for leg in build_split_buy_plan(c, config)),
            "buy_plan": build_split_buy_plan(c, config),
            "sell_plan": build_split_sell_plan(sum(leg["quantity"] for leg in build_split_buy_plan(c, config)), config),
            "stop_loss_pct": float(config["stop_loss_pct"]),
            "force_exit_time": str(config["force_exit_time"]),
            "reason": c["reason"],
            "dry_run": bool(config.get("dry_run", True)),
        }
        for c in buy_candidates
    ]

    executed_orders = []
    if not config.get("dry_run", True):
        for order in planned_orders:
            try:
                response = client.place_domestic_buy_order(order["code"], int(order["quantity"]))
                executed_orders.append({**order, "ok": True, "response": response})
            except Exception as exc:
                executed_orders.append({**order, "ok": False, "error": str(exc)})

    run = {
        "id": datetime.now().strftime("%Y%m%d%H%M%S"),
        "ran_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "dry_run" if config.get("dry_run", True) else "live_ready",
        "strategy_name": config.get("strategy_name", "surge_scalping"),
        "enabled": bool(config.get("enabled")),
        "market": "KR",
        "warnings": warnings,
        "candidates": candidates,
        "planned_orders": planned_orders,
        "executed_orders": executed_orders,
    }

    state["runs"] = [run] + state.get("runs", [])[:49]
    state["config"]["last_open_scan_date"] = datetime.now().strftime("%Y-%m-%d")
    save_trading_state(state)
    append_journal_run(run, config)
    journal_date = datetime.now().strftime("%Y-%m-%d")
    return {
        "config": state["config"],
        "kis": client.status(),
        "latest_run": run,
        "journal_date": journal_date,
        "journal_dates": list_trading_journal_dates(),
        "journal_tail": read_trading_journal(journal_date),
    }


def append_journal_run(run: dict[str, Any], config: dict[str, Any]) -> None:
    ensure_trading_docs()
    lines = [
        "",
        f"## {run['ran_at']} 급등주 스캘핑 스캔",
        f"- 모드: {run['mode']}",
        f"- 기준: 가격 {int(config['min_stock_price_krw']):,}~{int(config['max_stock_price_krw']):,}원, 거래대금 {int(config['min_trade_value_krw']):,}원 이상, 변동폭 {config['min_intraday_range_pct']}% 이상, 급등률 {config['min_change_pct']}% 이상",
    ]
    if run.get("warnings"):
        lines.append(f"- 경고: {' / '.join(run['warnings'])}")
    if run.get("planned_orders"):
        lines.append("- 주문 계획")
        for order in run["planned_orders"]:
            lines.append(
                f"  - {order['name']}({order['code']}) {order['quantity']}주 매수 후보: {order['reason']}"
            )
            for leg in order.get("buy_plan", []):
                lines.append(
                    f"    - 매수 {leg['leg']}차: {leg['label']}, {leg['quantity']}주, {leg['budget_krw']:,}원, 조건={leg['trigger']}"
                )
            for leg in order.get("sell_plan", []):
                lines.append(f"    - 매도 {leg['leg']}차: {leg['quantity']}주, 조건={leg['trigger']}")
            lines.append(f"    - 손절: 평균단가 대비 {order['stop_loss_pct']}%, 당일청산 기준 {order['force_exit_time']}")
    else:
        lines.append("- 주문 계획: 없음")

    if run.get("executed_orders"):
        lines.append("- 주문 실행 결과")
        for order in run["executed_orders"]:
            status = "성공" if order.get("ok") else f"실패: {order.get('error')}"
            lines.append(f"  - {order['name']}({order['code']}) {order['quantity']}주: {status}")

    lines.append("- 후보 판단")
    for c in run.get("candidates", []):
        lines.append(f"  - {c['name']}({c['code']}): {c['decision']} - {c['reason']}")

    with trading_journal_path().open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def trading_status(journal_date: str | None = None) -> dict[str, Any]:
    ensure_trading_docs()
    state = load_trading_state()
    latest_run = state.get("runs", [None])[0] if state.get("runs") else None
    selected_date = journal_date or datetime.now().strftime("%Y-%m-%d")
    return {
        "config": state["config"],
        "kis": KisClient().status(),
        "latest_run": latest_run,
        "runs_count": len(state.get("runs", [])),
        "rules": read_trading_rules(),
        "journal_date": selected_date,
        "journal_dates": list_trading_journal_dates(),
        "journal_tail": read_trading_journal(selected_date),
    }


def update_trading_config(patch: dict[str, Any]) -> dict[str, Any]:
    state = load_trading_state()
    allowed = set(DEFAULT_TRADING_CONFIG)
    for key, value in patch.items():
        if key in allowed:
            state["config"][key] = value
    if not state["config"].get("dry_run", True) and not KisClient().config.live_orders_enabled:
        state["config"]["dry_run"] = True
    save_trading_state(state)
    return trading_status()


def reset_trading_for_surge_scalping() -> dict[str, Any]:
    ensure_trading_docs()
    state = {
        "config": DEFAULT_TRADING_CONFIG.copy(),
        "runs": [],
        "positions": [],
    }
    save_trading_state(state)
    TRADING_RULES_PATH.write_text(DEFAULT_RULES, encoding="utf-8")
    today_path = trading_journal_path()
    today_path.write_text(
        f"# {today_path.stem} 급등주 스캘핑 매매일지\n\n"
        "## 리셋\n"
        "- 전략을 급등주 스캘핑으로 초기화했습니다.\n"
        "- 과거 실행 기록은 trading_state.json에서 비웠습니다.\n",
        encoding="utf-8",
    )
    return trading_status(today_path.stem)


def should_run_open_scan(now: datetime | None = None) -> bool:
    now = now or datetime.now()
    if now.weekday() >= 5:
        return False
    state = load_trading_state()
    config = state["config"]
    if not config.get("enabled"):
        return False
    if config.get("last_open_scan_date") == now.strftime("%Y-%m-%d"):
        return False
    open_scan_time = str(config.get("open_scan_time", "09:05"))
    hour, minute = [int(x) for x in open_scan_time.split(":")[:2]]
    scan_start = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    scan_end = scan_start.replace(minute=min(scan_start.minute + 10, 59))
    return scan_start <= now <= scan_end
