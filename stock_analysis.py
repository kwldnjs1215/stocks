from __future__ import annotations

import math
import os
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests

try:
    import FinanceDataReader as fdr
except Exception:  # pragma: no cover - optional runtime dependency
    fdr = None


NAME_TO_SYMBOL = {
    "샌디스크": "SNDK",
    "sandisk": "SNDK",
    "sndk": "SNDK",
    "엔비디아": "NVDA",
    "nvidia": "NVDA",
    "마이크론": "MU",
    "micron": "MU",
    "웨스턴디지털": "WDC",
    "western digital": "WDC",
    "시게이트": "STX",
    "seagate": "STX",
    "삼성전자": "005930",
    "sk하이닉스": "000660",
    "하이닉스": "000660",
}

PEER_MAP = {
    "SNDK": ["WDC", "MU", "STX", "NVDA", "LITE", "CIEN"],
    "WDC": ["SNDK", "MU", "STX", "NVDA"],
    "MU": ["SNDK", "WDC", "STX", "NVDA", "AMD"],
    "NVDA": ["AMD", "AVGO", "TSM", "MU", "SNDK"],
    "005930": ["000660", "005380", "035420", "373220"],
    "000660": ["005930", "SNDK", "MU", "NVDA"],
}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace(",", "").strip()
            if value in {"", "-"}:
                return default
        result = float(value)
        return result if math.isfinite(result) else default
    except Exception:
        return default


def _fmt_date(value: Any) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value)[:10]


def _env_value(name: str) -> str:
    value = os.environ.get(name, "")
    if value:
        return value.strip().strip('"').strip("'")
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return ""
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith(name + "="):
                raw = stripped.split("=", 1)[1].strip()
                match = re.match(r"""^['"]([^'"]+)['"]""", raw)
                return (match.group(1) if match else raw.split(" #", 1)[0]).strip().strip('"').strip("'")
            if stripped.startswith(name + ":"):
                raw = stripped.split(":", 1)[1].strip()
                match = re.match(r"""^['"]([^'"]+)['"]""", raw)
                return (match.group(1) if match else raw.split(" #", 1)[0]).strip().strip('"').strip("'")
    except Exception:
        return ""
    return ""


def resolve_symbol(query: str) -> dict[str, str]:
    raw = query.strip()
    key = raw.lower().replace(" ", "")
    symbol = NAME_TO_SYMBOL.get(raw.lower()) or NAME_TO_SYMBOL.get(key) or raw.upper()
    market = "KR" if re.fullmatch(r"\d{6}", symbol) else "US"
    exchange = "NAS"
    if market == "US" and symbol in {"WDC", "STX"}:
        exchange = "NYS"
    return {"query": raw, "symbol": symbol, "market": market, "exchange": exchange}


@dataclass
class KisClient:
    app_key: str
    app_secret: str
    base_url: str
    token: str = ""
    token_expiry: float = 0.0

    @property
    def token_path(self) -> Path:
        return Path(__file__).resolve().parent / ".kis_token.json"

    def _read_cached_token(self) -> str:
        try:
            data = json.loads(self.token_path.read_text(encoding="utf-8"))
            token = data.get("token", "")
            expiry = float(data.get("expiry", 0))
            if token and time.time() < expiry - 60:
                self.token = token
                self.token_expiry = expiry
                return token
        except Exception:
            pass
        return ""

    def _write_cached_token(self) -> None:
        try:
            self.token_path.write_text(
                json.dumps({"token": self.token, "expiry": self.token_expiry}),
                encoding="utf-8",
            )
        except Exception:
            pass

    @classmethod
    def from_env(cls) -> "KisClient | None":
        app_key = _env_value("MYAPP")
        app_secret = _env_value("MYSEC")
        base_url = _env_value("PROD") or "https://openapi.koreainvestment.com:9443"
        if base_url and not base_url.startswith("http"):
            base_url = "https://openapi.koreainvestment.com:9443"
        if not app_key or not app_secret:
            return None
        return cls(app_key=app_key, app_secret=app_secret, base_url=base_url.rstrip("/"))

    def ensure_token(self) -> str:
        if self.token and time.time() < self.token_expiry - 60:
            return self.token
        cached = self._read_cached_token()
        if cached:
            return cached
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }
        res = requests.post(
            f"{self.base_url}/oauth2/tokenP",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        res.raise_for_status()
        data = res.json()
        self.token = data.get("access_token", "")
        expires_in = int(_num(data.get("expires_in"), 86400))
        self.token_expiry = time.time() + expires_in
        self._write_cached_token()
        return self.token

    def get(self, path: str, tr_id: str, params: dict[str, str]) -> dict[str, Any]:
        token = self.ensure_token()
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
        }
        res = requests.get(f"{self.base_url}{path}", headers=headers, params=params, timeout=10)
        res.raise_for_status()
        data = res.json()
        if data.get("rt_cd") not in {None, "0"}:
            raise RuntimeError(data.get("msg1") or "KIS API error")
        return data


_KIS: KisClient | None = None


def _kis_client() -> KisClient | None:
    global _KIS
    if _KIS is None:
        _KIS = KisClient.from_env()
    return _KIS


def _kis_price(resolved: dict[str, str]) -> dict[str, Any] | None:
    client = _kis_client()
    if not client:
        return None
    try:
        if resolved["market"] == "KR":
            data = client.get(
                "/uapi/domestic-stock/v1/quotations/inquire-price",
                "FHKST01010100",
                {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": resolved["symbol"]},
            ).get("output", {})
            return {
                "price": _num(data.get("stck_prpr")),
                "change_pct": _num(data.get("prdy_ctrt")),
                "volume": _num(data.get("acml_vol")),
                "source": "KIS",
            }
        data = client.get(
            "/uapi/overseas-price/v1/quotations/price",
            "HHDFS00000300",
            {"AUTH": "", "EXCD": resolved["exchange"], "SYMB": resolved["symbol"]},
        ).get("output", {})
        return {
            "price": _num(data.get("last") or data.get("ovrs_nmix_prpr")),
            "change_pct": _num(data.get("rate") or data.get("prdy_ctrt")),
            "volume": _num(data.get("tvol") or data.get("acml_vol")),
            "source": "KIS",
        }
    except Exception:
        return None


def _kis_daily(resolved: dict[str, str]) -> list[dict[str, Any]]:
    client = _kis_client()
    if not client:
        return []
    end = datetime.now()
    start = end - timedelta(days=180)
    try:
        if resolved["market"] == "KR":
            data = client.get(
                "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
                "FHKST03010100",
                {
                    "FID_COND_MRKT_DIV_CODE": "J",
                    "FID_INPUT_ISCD": resolved["symbol"],
                    "FID_INPUT_DATE_1": start.strftime("%Y%m%d"),
                    "FID_INPUT_DATE_2": end.strftime("%Y%m%d"),
                    "FID_PERIOD_DIV_CODE": "D",
                    "FID_ORG_ADJ_PRC": "0",
                },
            )
            rows = data.get("output2") or []
            return [
                {
                    "date": str(r.get("stck_bsop_date", "")),
                    "open": _num(r.get("stck_oprc")),
                    "high": _num(r.get("stck_hgpr")),
                    "low": _num(r.get("stck_lwpr")),
                    "close": _num(r.get("stck_clpr")),
                    "volume": _num(r.get("acml_vol")),
                }
                for r in rows
            ][::-1]
        data = client.get(
            "/uapi/overseas-price/v1/quotations/dailyprice",
            "HHDFS76240000",
            {
                "AUTH": "",
                "EXCD": resolved["exchange"],
                "SYMB": resolved["symbol"],
                "GUBN": "0",
                "BYMD": end.strftime("%Y%m%d"),
                "MODP": "1",
            },
        )
        rows = data.get("output2") or []
        return [
            {
                "date": str(r.get("xymd", "")),
                "open": _num(r.get("open")),
                "high": _num(r.get("high")),
                "low": _num(r.get("low")),
                "close": _num(r.get("clos")),
                "volume": _num(r.get("tvol")),
            }
            for r in rows
        ][::-1]
    except Exception:
        return []


def _kis_intraday_5m(resolved: dict[str, str]) -> list[dict[str, Any]]:
    client = _kis_client()
    if not client or resolved["market"] != "US":
        return []
    try:
        data = client.get(
            "/uapi/overseas-price/v1/quotations/inquire-time-itemchartprice",
            "HHDFS76950200",
            {
                "AUTH": "",
                "EXCD": resolved["exchange"],
                "SYMB": resolved["symbol"],
                "NMIN": "5",
                "PINC": "1",
                "NEXT": "",
                "NREC": "120",
                "FILL": "",
                "KEYB": "",
            },
        )
        rows = data.get("output2") or []
        parsed = []
        for r in rows:
            close = _num(
                r.get("last")
                or r.get("clos")
                or r.get("ovrs_nmix_prpr")
                or r.get("stck_prpr")
                or r.get("price")
            )
            if close <= 0:
                continue
            parsed.append({
                "date": str(r.get("xymd") or r.get("stck_bsop_date") or r.get("date") or ""),
                "time": str(r.get("xhms") or r.get("stck_cntg_hour") or r.get("time") or ""),
                "open": _num(r.get("open") or r.get("stck_oprc"), close),
                "high": _num(r.get("high") or r.get("stck_hgpr"), close),
                "low": _num(r.get("low") or r.get("stck_lwpr"), close),
                "close": close,
                "volume": _num(r.get("evol") or r.get("tvol") or r.get("cntg_vol") or r.get("acml_vol")),
            })
        return sorted(parsed, key=lambda x: (x["date"], x["time"]))
    except Exception:
        return []


def _fdr_daily(resolved: dict[str, str]) -> list[dict[str, Any]]:
    if fdr is None:
        return []
    end = datetime.now()
    start = end - timedelta(days=240)
    try:
        df = fdr.DataReader(resolved["symbol"], start, end)
    except Exception:
        return []
    if df is None or df.empty:
        return []
    df = df.tail(140)
    rows = []
    for idx, row in df.iterrows():
        rows.append({
            "date": _fmt_date(idx),
            "open": _num(row.get("Open")),
            "high": _num(row.get("High")),
            "low": _num(row.get("Low")),
            "close": _num(row.get("Close")),
            "volume": _num(row.get("Volume")),
        })
    return rows


def _short_term_levels(rows: list[dict[str, Any]], current: float) -> dict[str, Any]:
    if len(rows) < 12:
        return {
            "available": False,
            "message": "5분봉 데이터가 부족해서 단기 지지/저항을 계산하지 못했습니다.",
            "bars": [],
        }
    dates = [r["date"] for r in rows if r.get("date")]
    target_date = dates[-1] if dates else ""
    if len(set(dates)) >= 2:
        target_date = sorted(set(dates))[-2]
    session = [r for r in rows if not target_date or r.get("date") == target_date]
    if len(session) < 12:
        session = rows[-80:]

    supports = []
    resistances = []
    for i in range(1, len(session) - 1):
        prev_r, cur, next_r = session[i - 1], session[i], session[i + 1]
        if cur["low"] <= prev_r["low"] and cur["low"] <= next_r["low"]:
            supports.append(cur)
        if cur["high"] >= prev_r["high"] and cur["high"] >= next_r["high"]:
            resistances.append(cur)

    below = [r for r in supports if r["low"] <= current] or [r for r in session if r["low"] <= current]
    above = [r for r in resistances if r["high"] >= current] or [r for r in session if r["high"] >= current]
    support = max(below, key=lambda r: (r["low"], r["volume"]), default=min(session, key=lambda r: r["low"]))
    resistance = min(above, key=lambda r: (r["high"], -r["volume"]), default=max(session, key=lambda r: r["high"]))
    avg_vol = sum(r["volume"] for r in session) / max(len(session), 1)

    return {
        "available": True,
        "source": "KIS 5분봉",
        "timeframe": f"{target_date or '최근'} 5분봉",
        "support": {
            "price": round(support["low"], 2),
            "time": support.get("time", ""),
            "reason": f"5분봉 스윙 저점이며 해당 봉 거래량이 평균 대비 {support['volume'] / avg_vol:.1f}배였습니다." if avg_vol else "5분봉 스윙 저점입니다.",
        },
        "resistance": {
            "price": round(resistance["high"], 2),
            "time": resistance.get("time", ""),
            "reason": f"5분봉 스윙 고점이며 해당 봉 거래량이 평균 대비 {resistance['volume'] / avg_vol:.1f}배였습니다." if avg_vol else "5분봉 스윙 고점입니다.",
        },
        "bars": [
            {
                "time": (r.get("time") or "")[:4],
                "close": round(r["close"], 2),
                "volume": round(r["volume"]),
            }
            for r in session[-48:]
        ],
    }


def _sma(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return round(sum(values[-window:]) / window, 2)


def _rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) <= period:
        return None
    gains, losses = [], []
    for prev, cur in zip(closes[-period - 1:-1], closes[-period:]):
        delta = cur - prev
        gains.append(max(delta, 0))
        losses.append(abs(min(delta, 0)))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    return round(100 - (100 / (1 + avg_gain / avg_loss)), 2)


def _volume_profile(rows: list[dict[str, Any]], buckets: int = 12) -> list[dict[str, Any]]:
    recent = rows[-80:] if len(rows) > 80 else rows
    if not recent:
        return []
    low = min(r["low"] or r["close"] for r in recent)
    high = max(r["high"] or r["close"] for r in recent)
    if high <= low:
        return []
    step = (high - low) / buckets
    profile = [{"low": low + step * i, "high": low + step * (i + 1), "volume": 0.0} for i in range(buckets)]
    for r in recent:
        close = r["close"]
        idx = min(int((close - low) / step), buckets - 1)
        profile[idx]["volume"] += r["volume"]
    return [
        {"low": round(p["low"], 2), "high": round(p["high"], 2), "volume": round(p["volume"])}
        for p in profile
    ]


def _levels(rows: list[dict[str, Any]], profile: list[dict[str, Any]]) -> dict[str, Any]:
    price = rows[-1]["close"]
    below = [p for p in profile if p["high"] <= price]
    above = [p for p in profile if p["low"] >= price]
    support_bin = max(below, key=lambda p: p["volume"], default=None)
    resistance_bin = max(above, key=lambda p: p["volume"], default=None)
    lows = sorted(rows[-30:], key=lambda r: r["low"])[:3]
    highs = sorted(rows[-30:], key=lambda r: r["high"], reverse=True)[:3]
    support_price = support_bin["high"] if support_bin else (lows[0]["low"] if lows else price)
    resistance_price = resistance_bin["low"] if resistance_bin else (highs[0]["high"] if highs else price)
    return {
        "support": {
            "price": round(support_price, 2),
            "reason": "최근 80거래일 매물대 중 현재가 아래에서 거래량이 가장 두꺼운 구간입니다." if support_bin else "최근 30거래일 저점권을 기준으로 계산했습니다.",
        },
        "resistance": {
            "price": round(resistance_price, 2),
            "reason": "최근 80거래일 매물대 중 현재가 위에서 거래량이 가장 두꺼운 구간입니다." if resistance_bin else "최근 30거래일 고점권을 기준으로 계산했습니다.",
        },
    }


def _pressure(rows: list[dict[str, Any]]) -> dict[str, Any]:
    recent = rows[-20:]
    up_volume = 0.0
    down_volume = 0.0
    obv = 0.0
    for prev, cur in zip(recent[:-1], recent[1:]):
        vol = cur["volume"]
        if cur["close"] >= prev["close"]:
            up_volume += vol
            obv += vol
        else:
            down_volume += vol
            obv -= vol
    total = up_volume + down_volume
    buy_pct = round(up_volume / total * 100, 1) if total else 50.0
    sell_pct = round(100 - buy_pct, 1)
    avg_vol = sum(r["volume"] for r in recent[:-1]) / max(len(recent[:-1]), 1)
    last_vol = recent[-1]["volume"] if recent else 0
    return {
        "buy_pct": buy_pct,
        "sell_pct": sell_pct,
        "obv_bias": "매수 우위" if obv > 0 else "매도 우위" if obv < 0 else "중립",
        "volume_ratio": round(last_vol / avg_vol, 2) if avg_vol else 0,
        "comment": "상승일 거래량 비중이 높습니다." if buy_pct >= 55 else "하락일 거래량 비중이 높습니다." if sell_pct >= 55 else "매수/매도 거래량이 비슷합니다.",
    }


def _options(symbol: str, spot: float) -> dict[str, Any]:
    if not symbol or re.fullmatch(r"\d{6}", symbol):
        return {"available": False, "message": "국내 개별주 옵션 체인은 아직 연결하지 않았습니다."}
    try:
        base = f"https://query2.finance.yahoo.com/v7/finance/options/{symbol}"
        meta = requests.get(base, timeout=8).json().get("optionChain", {}).get("result", [])
        if not meta:
            return {"available": False, "message": "옵션 체인을 찾지 못했습니다."}
        expiry = meta[0].get("expirationDates", [None])[0]
        chain = requests.get(f"{base}?date={expiry}", timeout=8).json()["optionChain"]["result"][0]
        options = chain.get("options", [{}])[0]
        calls = options.get("calls", [])
        puts = options.get("puts", [])
        call_volume = int(sum(_num(o.get("volume")) for o in calls))
        put_volume = int(sum(_num(o.get("volume")) for o in puts))
        strikes = sorted({round(_num(o.get("strike")), 2) for o in calls + puts if _num(o.get("strike")) > 0})
        max_pain = None
        min_pain = None
        for strike in strikes:
            pain = sum(max(0, strike - _num(c.get("strike"))) * _num(c.get("openInterest")) for c in calls)
            pain += sum(max(0, _num(p.get("strike")) - strike) * _num(p.get("openInterest")) for p in puts)
            if min_pain is None or pain < min_pain:
                min_pain = pain
                max_pain = strike
        return {
            "available": True,
            "source": "Yahoo Options",
            "expiry": datetime.fromtimestamp(expiry).strftime("%Y-%m-%d") if expiry else "",
            "call_volume": call_volume,
            "put_volume": put_volume,
            "put_call_volume_ratio": round(put_volume / call_volume, 2) if call_volume else None,
            "max_pain": max_pain,
            "spot_vs_max_pain_pct": round((spot / max_pain - 1) * 100, 2) if spot and max_pain else None,
        }
    except Exception:
        return {"available": False, "message": "옵션 데이터 조회에 실패했습니다."}


def _quote_summary(symbol: str) -> dict[str, Any]:
    if re.fullmatch(r"\d{6}", symbol):
        return {}
    try:
        url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"
        params = {"modules": "assetProfile,calendarEvents,summaryDetail,price"}
        result = requests.get(url, params=params, timeout=8).json()["quoteSummary"]["result"][0]
        profile = result.get("assetProfile", {})
        calendar = result.get("calendarEvents", {})
        earnings = calendar.get("earnings", {})
        earnings_dates = [
            datetime.fromtimestamp(x.get("raw")).strftime("%Y-%m-%d")
            for x in earnings.get("earningsDate", [])
            if isinstance(x, dict) and x.get("raw")
        ]
        return {
            "sector": profile.get("sector", ""),
            "industry": profile.get("industry", ""),
            "summary": profile.get("longBusinessSummary", ""),
            "earnings_dates": earnings_dates,
        }
    except Exception:
        return {}


def _news(symbol: str) -> list[dict[str, str]]:
    if re.fullmatch(r"\d{6}", symbol):
        return []
    try:
        url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US"
        text = requests.get(url, timeout=8).text
        items = re.findall(r"<item>(.*?)</item>", text, flags=re.S)[:6]
        out = []
        for item in items:
            title = re.search(r"<title><!\[CDATA\[(.*?)\]\]></title>|<title>(.*?)</title>", item, flags=re.S)
            link = re.search(r"<link>(.*?)</link>", item, flags=re.S)
            pub = re.search(r"<pubDate>(.*?)</pubDate>", item, flags=re.S)
            out.append({
                "title": (title.group(1) or title.group(2)).strip() if title else "",
                "url": link.group(1).strip() if link else "",
                "date": pub.group(1).strip() if pub else "",
            })
        return [n for n in out if n["title"]]
    except Exception:
        return []


def _peer_rows(symbol: str) -> list[dict[str, Any]]:
    peers = PEER_MAP.get(symbol, [])[:6]
    rows = []
    for peer in peers:
        resolved = resolve_symbol(peer)
        daily = _fdr_daily(resolved)
        if len(daily) < 6:
            continue
        price = daily[-1]["close"]
        change_5d = round((price / daily[-6]["close"] - 1) * 100, 2)
        rows.append({"symbol": peer, "price": round(price, 2), "change_5d": change_5d})
    return rows


def _analysis_context(analysis: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": analysis.get("symbol"),
        "quote": analysis.get("quote"),
        "technical": analysis.get("technical"),
        "levels": analysis.get("levels"),
        "short_term_levels": analysis.get("short_term_levels"),
        "pressure": analysis.get("pressure"),
        "options": analysis.get("options"),
        "peers": analysis.get("peers"),
        "events": analysis.get("events"),
        "news_titles": [n.get("title") for n in analysis.get("news", [])[:5]],
    }


def _anthropic_message(system: str, user: str, max_tokens: int = 900) -> str | None:
    api_key = _env_value("ANTHROPIC_API_KEY") or _env_value("CLAUDE_API_KEY")
    if not api_key:
        return None
    model = _env_value("ANTHROPIC_MODEL") or "claude-sonnet-4-20250514"
    try:
        res = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            timeout=20,
        )
        res.raise_for_status()
        data = res.json()
        parts = data.get("content", [])
        text = "\n".join(p.get("text", "") for p in parts if p.get("type") == "text")
        return text.strip() or None
    except Exception:
        return None


def _llm_strategy(analysis: dict[str, Any]) -> dict[str, Any]:
    prompt = json.dumps(_analysis_context(analysis), ensure_ascii=False)
    text = _anthropic_message(
        "너는 개인 투자자를 돕는 시장 분석 보조자다. 확정적 매수/매도 지시는 피하고, 조건부 시나리오와 리스크 관리를 한국어로 간결하게 제시한다.",
        f"아래 종목 분석 데이터를 바탕으로 단기/중기 전략 메모를 작성해줘. 반드시 1) 핵심 판단 2) 상승 시나리오 3) 하락 시나리오 4) 체크할 무효화 조건 5) 포지션 관리 아이디어 순서로 써줘.\n\n{prompt}",
        max_tokens=1000,
    )
    if not text:
        return {"available": False, "message": "ANTHROPIC_API_KEY가 없거나 Claude 호출에 실패했습니다."}
    return {"available": True, "source": "Claude", "text": text}


def build_stock_analysis(query: str) -> dict[str, Any]:
    resolved = resolve_symbol(query)
    daily = _kis_daily(resolved) or _fdr_daily(resolved)
    if len(daily) < 20:
        raise ValueError("분석할 일봉 데이터가 부족합니다. 티커나 종목명을 확인해주세요.")
    quote = _kis_price(resolved)
    closes = [r["close"] for r in daily if r["close"]]
    current = quote["price"] if quote and quote.get("price") else closes[-1]
    for r in daily[-1:]:
        r["close"] = current

    profile = _volume_profile(daily)
    levels = _levels(daily, profile)
    pressure = _pressure(daily)
    summary = _quote_summary(resolved["symbol"])
    options = _options(resolved["symbol"], current)
    short_term_levels = _short_term_levels(_kis_intraday_5m(resolved), current)
    week = daily[-7:]
    recent_high = max(r["high"] for r in daily[-120:])
    recent_low = min(r["low"] for r in daily[-120:])

    ma5 = _sma(closes, 5)
    ma20 = _sma(closes, 20)
    ma60 = _sma(closes, 60)
    rsi = _rsi(closes)
    trend = "상승 추세" if ma5 and ma20 and ma5 > ma20 else "하락/조정 추세" if ma5 and ma20 and ma5 < ma20 else "중립"
    if rsi is not None and rsi >= 70:
        rsi_comment = "과열권입니다. 추격보다 눌림 확인이 더 유리합니다."
    elif rsi is not None and rsi <= 30:
        rsi_comment = "침체권입니다. 반등 신호와 거래량 확인이 필요합니다."
    else:
        rsi_comment = "중립권입니다. 추세와 매물대 확인이 더 중요합니다."

    analysis = {
        "input": query,
        "symbol": resolved["symbol"],
        "market": resolved["market"],
        "exchange": resolved["exchange"],
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "data_source": quote["source"] if quote else "FinanceDataReader",
        "quote": {
            "price": round(current, 2),
            "change_pct": quote.get("change_pct") if quote else round((current / daily[-2]["close"] - 1) * 100, 2),
            "volume": quote.get("volume") if quote else daily[-1]["volume"],
        },
        "technical": {
            "rsi14": rsi,
            "rsi_comment": rsi_comment,
            "ma5": ma5,
            "ma20": ma20,
            "ma60": ma60,
            "trend": trend,
            "recent_low": round(recent_low, 2),
            "recent_high": round(recent_high, 2),
        },
        "weekly_flow": [
            {
                "date": r["date"],
                "close": round(r["close"], 2),
                "change_pct": round((r["close"] / week[i - 1]["close"] - 1) * 100, 2) if i > 0 else 0,
                "volume": round(r["volume"]),
            }
            for i, r in enumerate(week)
        ],
        "volume_profile": profile,
        "levels": levels,
        "short_term_levels": short_term_levels,
        "pressure": pressure,
        "options": options,
        "peers": _peer_rows(resolved["symbol"]),
        "company": summary,
        "news": _news(resolved["symbol"]),
        "events": {
            "past": ["최근 실적 발표/가이던스 변화", "지수 편입·대형 수급 이벤트 여부 확인"],
            "future": summary.get("earnings_dates", []) or ["다음 실적 발표 일정 확인 필요"],
        },
        "notes": [
            "옵션 데이터는 미국 종목에 한해 Yahoo 옵션 체인으로 계산합니다.",
            "매수세/매도세는 일봉 상승일·하락일 거래량 기반의 추정치입니다.",
            "단기 지지/저항은 한국투자 5분봉 데이터가 있을 때만 계산합니다.",
        ],
    }
    analysis["llm_strategy"] = _llm_strategy(analysis)
    return analysis


def answer_stock_question(analysis: dict[str, Any], question: str) -> str:
    llm_answer = _anthropic_message(
        "너는 개인 투자자를 돕는 시장 분석 보조자다. 확정적 매수/매도 지시는 피하고, 제공된 데이터 안에서만 근거를 들어 한국어로 답한다.",
        f"분석 데이터:\n{json.dumps(_analysis_context(analysis), ensure_ascii=False)}\n\n사용자 질문: {question}",
        max_tokens=800,
    )
    if llm_answer:
        return llm_answer
    q = question.lower()
    tech = analysis.get("technical", {})
    levels = analysis.get("levels", {})
    pressure = analysis.get("pressure", {})
    options = analysis.get("options", {})
    if any(k in q for k in ["지지", "하방", "손절", "support"]):
        s = levels.get("support", {})
        return f"하방 기준은 {s.get('price')} 부근을 먼저 봅니다. 이유는 {s.get('reason')} 현재 RSI는 {tech.get('rsi14')}이고, 이 구간이 깨지면 최근 저점/20일선 재확인이 필요합니다."
    if any(k in q for k in ["저항", "상방", "목표", "resistance"]):
        r = levels.get("resistance", {})
        return f"상방 저항은 {r.get('price')} 부근입니다. {r.get('reason')} 5일선과 20일선 배열은 {tech.get('trend')}로 읽힙니다."
    if any(k in q for k in ["옵션", "콜", "풋", "맥스페인"]):
        if options.get("available"):
            return f"최근 만기 {options.get('expiry')} 기준 콜 거래량은 {options.get('call_volume'):,}, 풋 거래량은 {options.get('put_volume'):,}입니다. 맥스페인은 {options.get('max_pain')}이고 현재가 대비 {options.get('spot_vs_max_pain_pct')}% 위치입니다."
        return options.get("message", "옵션 데이터가 없습니다.")
    if any(k in q for k in ["수급", "매수", "매도", "거래량"]):
        return f"최근 20거래일 기준 매수세 {pressure.get('buy_pct')}%, 매도세 {pressure.get('sell_pct')}%로 추정됩니다. OBV 흐름은 {pressure.get('obv_bias')}이고, 직전 거래량은 평균 대비 {pressure.get('volume_ratio')}배입니다."
    return (
        f"{analysis.get('symbol')}의 현재 핵심은 {tech.get('trend')}와 RSI {tech.get('rsi14')}입니다. "
        f"하방 {levels.get('support', {}).get('price')}, 상방 {levels.get('resistance', {}).get('price')}를 기준으로 보고, "
        f"수급은 {pressure.get('comment')}"
    )
