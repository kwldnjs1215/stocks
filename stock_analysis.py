from __future__ import annotations

import math
import os
import json
import re
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests

try:
    import FinanceDataReader as fdr
except Exception:  # pragma: no cover - optional runtime dependency
    fdr = None

try:
    import yfinance as yf
except Exception:  # pragma: no cover - optional runtime dependency
    yf = None


NAME_TO_SYMBOL = {
    "샌디스크": "SNDK",
    "엔비디아": "NVDA",
    "마이크론": "MU",
    "웨스턴디지털": "WDC",
    "시게이트": "STX",
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


_KR_NAME_INDEX: dict[str, str] | None = None


def _kr_name_index() -> dict[str, str]:
    global _KR_NAME_INDEX
    if _KR_NAME_INDEX is not None:
        return _KR_NAME_INDEX
    if fdr is None:
        _KR_NAME_INDEX = {}
        return _KR_NAME_INDEX
    try:
        df = fdr.StockListing("KRX")
        index: dict[str, str] = {}
        for code, name in zip(df["Code"], df["Name"]):
            if not isinstance(code, str) or not isinstance(name, str):
                continue
            key = name.lower().replace(" ", "")
            if key and key not in index:
                index[key] = code
        _KR_NAME_INDEX = index
    except Exception:
        _KR_NAME_INDEX = {}
    return _KR_NAME_INDEX


def resolve_symbol(query: str) -> dict[str, str]:
    raw = query.strip()
    key = raw.lower().replace(" ", "")
    symbol = NAME_TO_SYMBOL.get(raw.lower()) or NAME_TO_SYMBOL.get(key)
    if not symbol:
        symbol = _kr_name_index().get(key)
    if not symbol:
        symbol = raw.upper()
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


def _kis_intraday_1m_kr(resolved: dict[str, str], max_batches: int = 3) -> list[dict[str, Any]]:
    """KIS 국내 1분봉. 한 호출당 30개 → 페이지네이션으로 max_batches*30개."""
    client = _kis_client()
    if not client:
        return []
    now = datetime.now()
    if 9 <= now.hour < 15 or (now.hour == 15 and now.minute <= 30):
        cursor_time = now.strftime("%H%M%S")
    else:
        cursor_time = "153000"

    all_bars: list[dict[str, Any]] = []
    for _ in range(max_batches):
        try:
            data = client.get(
                "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
                "FHKST03010200",
                {
                    "FID_ETC_CLS_CODE": "",
                    "FID_COND_MRKT_DIV_CODE": "J",
                    "FID_INPUT_ISCD": resolved["symbol"],
                    "FID_INPUT_HOUR_1": cursor_time,
                    "FID_PW_DATA_INCU_YN": "Y",
                },
            )
        except Exception:
            break
        rows = data.get("output2") or []
        batch: list[dict[str, Any]] = []
        for r in rows:
            close = _num(r.get("stck_prpr"))
            if close <= 0:
                continue
            batch.append({
                "date": str(r.get("stck_bsop_date", "")),
                "time": str(r.get("stck_cntg_hour", "")).zfill(6),
                "open": _num(r.get("stck_oprc"), close),
                "high": _num(r.get("stck_hgpr"), close),
                "low": _num(r.get("stck_lwpr"), close),
                "close": close,
                "volume": _num(r.get("cntg_vol")),
            })
        if not batch:
            break
        all_bars.extend(batch)
        earliest = min(b["time"] for b in batch)
        try:
            hh = int(earliest[:2])
            mm = int(earliest[2:4])
            mm -= 1
            if mm < 0:
                mm = 59
                hh -= 1
            if hh < 9:
                break
            cursor_time = f"{hh:02d}{mm:02d}00"
        except Exception:
            break

    seen = set()
    unique: list[dict[str, Any]] = []
    for b in all_bars:
        key = (b["date"], b["time"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(b)
    return sorted(unique, key=lambda x: (x["date"], x["time"]))


def _resample_to_5m(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """1분봉을 5분 단위로 OHLC 리샘플링."""
    if not bars:
        return []
    buckets: dict[str, list[dict[str, Any]]] = {}
    for b in bars:
        t = b.get("time", "")
        if len(t) < 4:
            continue
        try:
            hh = int(t[:2])
            mm = int(t[2:4])
        except ValueError:
            continue
        bucket_min = (mm // 5) * 5
        key = f"{b.get('date', '')}_{hh:02d}{bucket_min:02d}"
        buckets.setdefault(key, []).append(b)
    out: list[dict[str, Any]] = []
    for key in sorted(buckets):
        group = sorted(buckets[key], key=lambda x: x["time"])
        date, hhmm = key.split("_", 1)
        out.append({
            "date": date,
            "time": hhmm + "00",
            "open": group[0]["open"],
            "high": max(g["high"] for g in group),
            "low": min(g["low"] for g in group),
            "close": group[-1]["close"],
            "volume": sum(g["volume"] for g in group),
        })
    return out


def _kis_intraday_5m(resolved: dict[str, str]) -> list[dict[str, Any]]:
    client = _kis_client()
    if not client:
        return []
    if resolved["market"] == "KR":
        return _resample_to_5m(_kis_intraday_1m_kr(resolved))
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


def _next_kospi200_expiry_yyyymm() -> str:
    """다음 KOSPI200 월간옵션 만기(둘째주 목요일) 기준의 YYYYMM."""
    today = datetime.now().date()

    def second_thursday(y: int, m: int):
        for d in range(8, 15):
            if datetime(y, m, d).weekday() == 3:
                return datetime(y, m, d).date()
        return None

    exp = second_thursday(today.year, today.month)
    if exp and today < exp:
        return f"{today.year:04d}{today.month:02d}"
    if today.month == 12:
        return f"{today.year + 1:04d}01"
    return f"{today.year:04d}{today.month + 1:02d}"


def _kis_kospi200_options() -> dict[str, Any]:
    """국내 종목 분석 시 시장 전반 분위기로 KOSPI200 옵션 체인 사용."""
    client = _kis_client()
    if not client:
        return {"available": False, "message": "KIS API 키가 없어 KOSPI200 옵션을 가져오지 못했습니다."}

    expiry = _next_kospi200_expiry_yyyymm()
    try:
        data = client.get(
            "/uapi/domestic-futureoption/v1/quotations/display-board-callput",
            "FHPIF05030100",
            {
                "FID_COND_MRKT_DIV_CODE": "O",
                "FID_COND_SCR_DIV_CODE": "20503",
                "FID_MRKT_CLS_CODE": "CO",
                "FID_MTRT_CNT": expiry,
                "FID_MRKT_CLS_CODE1": "PO",
                "FID_COND_MRKT_CLS_CODE": "",
            },
        )
    except Exception as e:
        return {"available": False, "message": f"KOSPI200 옵션 조회 실패: {str(e)[:60]}"}

    calls = data.get("output1") or []
    puts = data.get("output2") or []
    if not calls or not puts:
        return {"available": False, "message": "KOSPI200 옵션 체인 응답이 비어있습니다."}

    call_vol = sum(int(_num(r.get("acml_vol"))) for r in calls)
    put_vol = sum(int(_num(r.get("acml_vol"))) for r in puts)
    call_oi = sum(int(_num(r.get("hts_otst_stpl_qty"))) for r in calls)
    put_oi = sum(int(_num(r.get("hts_otst_stpl_qty"))) for r in puts)

    atm_row = next((r for r in calls if r.get("atm_cls_name") == "ATM"), None)
    atm_strike = _num(atm_row.get("acpr")) if atm_row else 0
    atm_iv = _num(atm_row.get("hts_ints_vltl")) if atm_row else 0

    by_strike: dict[float, dict[str, float]] = {}
    for r in calls:
        k = _num(r.get("acpr"))
        if k > 0:
            by_strike.setdefault(k, {"call_oi": 0, "put_oi": 0})["call_oi"] = _num(r.get("hts_otst_stpl_qty"))
    for r in puts:
        k = _num(r.get("acpr"))
        if k > 0:
            by_strike.setdefault(k, {"call_oi": 0, "put_oi": 0})["put_oi"] = _num(r.get("hts_otst_stpl_qty"))

    strikes = sorted(by_strike)
    max_pain = None
    min_pain = None
    for k in strikes:
        pain = 0.0
        for s in strikes:
            data_s = by_strike[s]
            pain += max(0.0, k - s) * data_s["call_oi"]
            pain += max(0.0, s - k) * data_s["put_oi"]
        if min_pain is None or pain < min_pain:
            min_pain = pain
            max_pain = k

    pcv = round(put_vol / call_vol, 2) if call_vol else None
    return {
        "available": True,
        "source": "KIS KOSPI200 옵션",
        "scope": "시장 전반 (KOSPI200 지수옵션)",
        "expiry": f"{expiry[:4]}-{expiry[4:]}",
        "call_volume": call_vol,
        "put_volume": put_vol,
        "put_call_volume_ratio": pcv,
        "call_open_interest": call_oi,
        "put_open_interest": put_oi,
        "put_call_oi_ratio": round(put_oi / call_oi, 2) if call_oi else None,
        "max_pain": max_pain,
        "atm_strike": round(atm_strike, 2) if atm_strike else None,
        "atm_iv": round(atm_iv, 2) if atm_iv else None,
    }


def _options(symbol: str, spot: float) -> dict[str, Any]:
    if not symbol:
        return {"available": False, "message": "심볼이 없어 옵션을 가져오지 못했습니다."}
    if re.fullmatch(r"\d{6}", symbol):
        return _kis_kospi200_options()
    if yf is None:
        return {"available": False, "message": "yfinance 패키지가 설치되지 않았습니다."}
    try:
        t = yf.Ticker(symbol)
        expirations = t.options
        if not expirations:
            return {"available": False, "message": "옵션 체인을 찾지 못했습니다."}
        expiry = expirations[0]
        chain = t.option_chain(expiry)
        calls = chain.calls
        puts = chain.puts
        call_volume = int(calls["volume"].fillna(0).sum())
        put_volume = int(puts["volume"].fillna(0).sum())
        call_oi = int(calls["openInterest"].fillna(0).sum())
        put_oi = int(puts["openInterest"].fillna(0).sum())

        strikes = sorted(set(calls["strike"].tolist()) | set(puts["strike"].tolist()))
        max_pain = None
        min_pain = None
        call_strikes = calls["strike"].values
        call_oi_arr = calls["openInterest"].fillna(0).values
        put_strikes = puts["strike"].values
        put_oi_arr = puts["openInterest"].fillna(0).values
        for strike in strikes:
            pain = float(sum(max(0, strike - cs) * coi for cs, coi in zip(call_strikes, call_oi_arr)))
            pain += float(sum(max(0, ps - strike) * poi for ps, poi in zip(put_strikes, put_oi_arr)))
            if min_pain is None or pain < min_pain:
                min_pain = pain
                max_pain = strike

        atm_iv = None
        if spot and not calls.empty:
            calls_sorted = calls.iloc[(calls["strike"] - spot).abs().argsort()]
            atm_row = calls_sorted.iloc[0]
            iv = atm_row.get("impliedVolatility")
            if isinstance(iv, (int, float)) and not math.isnan(iv):
                atm_iv = round(float(iv) * 100, 2)

        return {
            "available": True,
            "source": "Yahoo Options (yfinance)",
            "scope": "개별주 옵션",
            "expiry": expiry,
            "call_volume": call_volume,
            "put_volume": put_volume,
            "put_call_volume_ratio": round(put_volume / call_volume, 2) if call_volume else None,
            "call_open_interest": call_oi,
            "put_open_interest": put_oi,
            "put_call_oi_ratio": round(put_oi / call_oi, 2) if call_oi else None,
            "max_pain": float(max_pain) if max_pain is not None else None,
            "spot_vs_max_pain_pct": round((spot / max_pain - 1) * 100, 2) if spot and max_pain else None,
            "atm_iv": atm_iv,
        }
    except Exception as e:
        return {"available": False, "message": f"옵션 데이터 조회 실패: {str(e)[:60]}"}


def _quote_summary(symbol: str) -> dict[str, Any]:
    """yfinance로 회사 정보 조회. 국내 종목은 .KS/.KQ suffix 자동 시도."""
    if yf is None:
        return {}
    candidates = [symbol]
    if re.fullmatch(r"\d{6}", symbol):
        candidates = [f"{symbol}.KS", f"{symbol}.KQ"]

    for cand in candidates:
        try:
            t = yf.Ticker(cand)
            info = t.info or {}
            if not (info.get("longName") or info.get("sector") or info.get("longBusinessSummary")):
                continue
            upcoming: list[str] = []
            try:
                cal = t.calendar
                if isinstance(cal, dict):
                    for d in cal.get("Earnings Date", []) or []:
                        if hasattr(d, "strftime"):
                            upcoming.append(d.strftime("%Y-%m-%d"))
            except Exception:
                pass
            return {
                "yf_symbol": cand,
                "name": info.get("longName") or info.get("shortName") or "",
                "sector": info.get("sector") or "",
                "industry": info.get("industry") or "",
                "summary": info.get("longBusinessSummary") or "",
                "market_cap": info.get("marketCap"),
                "trailing_pe": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "dividend_yield": info.get("dividendYield"),
                "earnings_dates": upcoming,
            }
        except Exception:
            continue
    return {}


def _news_search(query: str, lang: str = "ko", limit: int = 6) -> list[dict[str, str]]:
    """Google News RSS로 키워드 검색. 한/영 동작."""
    if not query.strip():
        return []
    encoded = urllib.parse.quote(query)
    if lang == "ko":
        url = f"https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"
    else:
        url = f"https://news.google.com/rss/search?q={encoded}&hl=en&gl=US&ceid=US:en"
    try:
        text = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"}).text
        items = re.findall(r"<item>(.*?)</item>", text, flags=re.S)[:limit]
        out: list[dict[str, str]] = []
        for item in items:
            title_m = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", item, flags=re.S)
            link_m = re.search(r"<link>(.*?)</link>", item, flags=re.S)
            pub_m = re.search(r"<pubDate>(.*?)</pubDate>", item, flags=re.S)
            source_m = re.search(r"<source[^>]*>(.*?)</source>", item, flags=re.S)
            title = (title_m.group(1) if title_m else "").strip()
            if not title:
                continue
            out.append({
                "title": title,
                "url": (link_m.group(1) if link_m else "").strip(),
                "date": (pub_m.group(1) if pub_m else "").strip(),
                "source": (source_m.group(1) if source_m else "").strip(),
            })
        return out
    except Exception:
        return []


def _sector_keywords(symbol: str, query: str, company: dict[str, Any], lang: str) -> list[str]:
    """LLM으로 시장/산업 동향 뉴스 검색 키워드 추출.

    메타데이터(섹터/산업/회사 요약)가 비어있어도 종목명/티커만으로 동작.
    """
    name = company.get("name", "")
    sector = company.get("sector", "")
    industry = company.get("industry", "")
    summary = (company.get("summary") or "")[:1200]

    context_lines = [f"종목 티커: {symbol}"]
    if query and query != symbol:
        context_lines.append(f"사용자 입력 이름: {query}")
    if name:
        context_lines.append(f"회사명: {name}")
    if sector:
        context_lines.append(f"섹터: {sector}")
    if industry:
        context_lines.append(f"산업: {industry}")
    if summary:
        context_lines.append(f"회사 요약: {summary}")
    context = "\n".join(context_lines)

    lang_label = "한국어" if lang == "ko" else "영어"
    prompt = (
        f"{context}\n\n"
        f"이 회사 주가를 견인하는 시장/산업 동향 뉴스 검색 키워드를 {lang_label}로 5~6개 뽑아줘.\n"
        "조건:\n"
        "- 각 키워드는 뉴스 검색에 그대로 쓸 수 있는 구체적 형태\n"
        "- 회사 비즈니스의 핵심 동력에 초점 (제품 가격 사이클, 수요/공급, capex, "
        "주요 고객사 동향, 정책/규제, 원자재, 환율 등)\n"
        "- 추상적 단어('반도체', 'Technology', 'Computer Hardware')는 피하고 동향 중심으로\n"
        "- 좋은 예: 'NAND 가격 동향', 'HBM 수요', '메모리 capex', '낸드 숏티지', "
        "'주택 분양 시장', '해외 플랜트 수주', '데이터센터 capex'\n\n"
        "쉼표 구분으로만 답하고 다른 설명은 추가하지 마."
    )
    text = _anthropic_message("너는 시장 분석 보조자다.", prompt, max_tokens=250)
    if not text:
        out = []
        if industry:
            out.append(industry)
        if sector and sector != industry:
            out.append(sector)
        return out
    parts = [p.strip(" \"'.").strip() for p in text.split(",")]
    return [p for p in parts if p][:6]


_KR_CODE_TO_NAME: dict[str, str] = {}


def _kr_code_to_name(code: str) -> str:
    if not re.fullmatch(r"\d{6}", code):
        return ""
    if not _KR_CODE_TO_NAME:
        idx = _kr_name_index()
        for name_key, c in idx.items():
            _KR_CODE_TO_NAME[c] = name_key
    return _KR_CODE_TO_NAME.get(code, "")


def _news_for_symbol(query: str, resolved: dict[str, str], company: dict[str, Any]) -> dict[str, Any]:
    """직접/섹터/관련주 카테고리별 뉴스."""
    symbol = resolved["symbol"]
    market = resolved["market"]
    lang = "ko" if market == "KR" else "en"

    if market == "KR":
        direct_q = query or _kr_code_to_name(symbol) or symbol
    else:
        direct_q = symbol

    direct_news = _news_search(direct_q, lang=lang, limit=6)

    keywords = _sector_keywords(symbol, query, company, lang)
    seen_titles: set[str] = {n["title"] for n in direct_news}
    sector_news: list[dict[str, str]] = []
    for kw in keywords:
        for n in _news_search(kw, lang=lang, limit=3):
            if n["title"] in seen_titles:
                continue
            seen_titles.add(n["title"])
            n["keyword"] = kw
            sector_news.append(n)
        if len(sector_news) >= 8:
            break

    peer_news: list[dict[str, str]] = []
    peer_symbols = PEER_MAP.get(symbol, [])[:4]
    for peer in peer_symbols:
        peer_resolved = resolve_symbol(peer)
        peer_lang = "ko" if peer_resolved["market"] == "KR" else "en"
        if peer_resolved["market"] == "KR":
            peer_q = _kr_code_to_name(peer) or peer
        else:
            peer_q = peer
        for n in _news_search(peer_q, lang=peer_lang, limit=2):
            if n["title"] in seen_titles:
                continue
            seen_titles.add(n["title"])
            n["peer"] = peer
            peer_news.append(n)

    return {
        "direct": direct_news,
        "sector": sector_news[:8],
        "peers": peer_news[:8],
        "keywords": keywords,
    }


def _market_news() -> dict[str, list[dict[str, str]]]:
    """미국/국내 시황 뉴스."""
    return {
        "us": _news_search("US stock market today S&P 500 Nasdaq", lang="en", limit=5),
        "kr": _news_search("코스피 코스닥 오늘 증시 동향", lang="ko", limit=5),
    }


def _earnings_detail(symbol: str) -> dict[str, Any]:
    """yfinance earnings_history + calendar (미국주만)."""
    if re.fullmatch(r"\d{6}", symbol):
        return {
            "available": False,
            "message": "국내 종목 실적 디테일은 별도 데이터 소스가 필요합니다.",
        }
    if yf is None:
        return {"available": False, "message": "yfinance 패키지가 설치되지 않았습니다."}
    try:
        t = yf.Ticker(symbol)
        past: list[dict[str, Any]] = []
        try:
            eh = t.earnings_history
            if eh is not None and not eh.empty:
                for idx, row in eh.iterrows():
                    qstr = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)
                    est = row.get("epsEstimate")
                    act = row.get("epsActual")
                    diff_pct = row.get("surprisePercent")
                    past.append({
                        "quarter": qstr,
                        "eps_estimate": float(est) if isinstance(est, (int, float)) and not math.isnan(est) else None,
                        "eps_actual": float(act) if isinstance(act, (int, float)) and not math.isnan(act) else None,
                        "surprise_pct": round(float(diff_pct) * 100, 2) if isinstance(diff_pct, (int, float)) and not math.isnan(diff_pct) else None,
                    })
        except Exception:
            pass

        future_estimates: list[dict[str, Any]] = []
        upcoming_dates: list[str] = []
        try:
            cal = t.calendar
            if isinstance(cal, dict):
                for d in cal.get("Earnings Date", []) or []:
                    if hasattr(d, "strftime"):
                        upcoming_dates.append(d.strftime("%Y-%m-%d"))
                eps_avg = cal.get("Earnings Average")
                if isinstance(eps_avg, (int, float)):
                    future_estimates.append({
                        "period": "next",
                        "label": "다음 실적 컨센서스",
                        "eps_avg": float(eps_avg),
                        "eps_low": float(cal["Earnings Low"]) if isinstance(cal.get("Earnings Low"), (int, float)) else None,
                        "eps_high": float(cal["Earnings High"]) if isinstance(cal.get("Earnings High"), (int, float)) else None,
                        "revenue_avg": float(cal["Revenue Average"]) if isinstance(cal.get("Revenue Average"), (int, float)) else None,
                        "revenue_low": float(cal["Revenue Low"]) if isinstance(cal.get("Revenue Low"), (int, float)) else None,
                        "revenue_high": float(cal["Revenue High"]) if isinstance(cal.get("Revenue High"), (int, float)) else None,
                    })
        except Exception:
            pass

        if not past and not future_estimates and not upcoming_dates:
            return {"available": False, "message": "Yahoo에서 실적 데이터를 받지 못했습니다."}

        return {
            "available": True,
            "source": "Yahoo Finance (yfinance)",
            "past": past[-6:],
            "future_estimates": future_estimates,
            "upcoming_dates": upcoming_dates,
        }
    except Exception as e:
        return {"available": False, "message": f"실적 데이터 조회 실패: {str(e)[:60]}"}


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
    news = analysis.get("news") or {}
    direct_titles = [n.get("title") for n in (news.get("direct") or [])[:5]]
    sector_titles = [n.get("title") for n in (news.get("sector") or [])[:5]]
    peer_titles = [n.get("title") for n in (news.get("peers") or [])[:5]]
    events = analysis.get("events") or {}
    earnings = events.get("earnings") if isinstance(events, dict) else None
    return {
        "symbol": analysis.get("symbol"),
        "quote": analysis.get("quote"),
        "technical": analysis.get("technical"),
        "levels": analysis.get("levels"),
        "short_term_levels": analysis.get("short_term_levels"),
        "pressure": analysis.get("pressure"),
        "options": analysis.get("options"),
        "peers": analysis.get("peers"),
        "earnings": earnings,
        "news_direct": direct_titles,
        "news_sector": sector_titles,
        "news_peers": peer_titles,
        "sector_keywords": news.get("keywords") or [],
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
        "news": _news_for_symbol(query, resolved, summary),
        "market_news": _market_news(),
        "events": {
            "earnings": _earnings_detail(resolved["symbol"]),
        },
        "notes": [
            "옵션 데이터: 국내는 KOSPI200 지수옵션(시장 분위기), 미국은 Yahoo 체인.",
            "뉴스: 직접/섹터/관련주 카테고리는 Google News 검색, 시황은 별도.",
            "실적 디테일은 미국 종목만 Yahoo earnings로 가져옵니다.",
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
