"""Fintables OHLCV sağlayıcısı.

Sunucu şeması değişebildiği için bu adaptör yalnız OHLCV/metadata sözleşmesini
uygular; indikatörler analiz motorlarında kalır. Yanıt REST veya MCP-tool
sonucu olarak ``data``/``result`` altında tablo taşıyabilir.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import pandas as pd

ISTANBUL = ZoneInfo("Europe/Istanbul")


def fintables_symbol(symbol: str) -> str:
    return str(symbol).upper().replace(".IS", "").strip()


class FintablesProvider:
    source = "Fintables"

    def __init__(self, endpoint: str | None = None, timeout: float = 5.0):
        self.endpoint = endpoint or os.getenv("FINTABLES_MCP_URL", "https://evo.fintables.com/mcp")
        self.timeout = timeout

    def _request(self, symbol: str, interval: str, period: str):
        # Fintables gateway'leri çoğunlukla bu yalın istek sözleşmesini kabul eder.
        payload = {"method": "get_ohlcv", "params": {"symbol": fintables_symbol(symbol), "interval": interval, "period": period}}
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        token = os.getenv("FINTABLES_API_KEY")
        if token:
            headers["Authorization"] = f"Bearer {token}"
            headers["X-API-Key"] = token
        req = Request(self.endpoint, data=json.dumps(payload).encode(), headers=headers, method="POST")
        with urlopen(req, timeout=self.timeout) as response:
            raw = json.loads(response.read().decode("utf-8"))
        value = raw.get("result", raw) if isinstance(raw, dict) else raw
        if isinstance(value, dict):
            value = value.get("data", value.get("rows", value.get("candles", value)))
        if isinstance(value, dict) and all(isinstance(v, (list, tuple)) for v in value.values()):
            frame = pd.DataFrame(value)
        else:
            frame = pd.DataFrame(value)
        rename = {"open":"Open","high":"High","low":"Low","close":"Close","volume":"Volume","time":"timestamp","timestamp":"timestamp","date":"timestamp"}
        frame = frame.rename(columns={c: rename.get(str(c).lower(), c) for c in frame.columns})
        if "timestamp" in frame:
            frame.index = pd.to_datetime(frame.pop("timestamp"), errors="coerce", utc=True).dt.tz_convert(ISTANBUL)
        return _istanbul_index(_normalize(frame))

    def _get(self, symbol: str, interval: str, period: str):
        from veri_saglayici import VeriMetadatasi, _normalize, _istanbul_index
        fetched = datetime.now(ISTANBUL)
        frame = self._request(symbol, interval, period)
        if frame.empty:
            raise ValueError("Fintables boş OHLCV döndürdü")
        last = frame.index[-1].to_pydatetime()
        delay = max(0.0, (fetched-last).total_seconds()/60.0)
        declared_delay = 15.0 if interval in {"1m", "5m", "15m"} else 0.0
        meta = VeriMetadatasi(source=self.source, fetched_at=fetched, last_bar_at=last,
            symbol=fintables_symbol(symbol), first_bar_at=frame.index[0].to_pydatetime(), interval=interval,
            is_delayed=declared_delay > 0, delay_minutes=max(delay, declared_delay),
            is_stale=frame.empty or delay > max(60, declared_delay * 4), is_complete_bar=True,
            price_basis="raw", corporate_action_warning=bool(frame.attrs.get("corporate_action_warning", False)))
        frame.attrs["veri_kaynagi"] = self.source
        frame.attrs["fintables_delay_minutes"] = declared_delay
        return frame, meta

    def get_daily_ohlcv(self, symbol, period="6mo"): return self._get(symbol, "1d", period)
    def get_hourly_ohlcv(self, symbol, period="3mo"): return self._get(symbol, "60m", period)
    def get_intraday_15m(self, symbol, period="5d"): return self._get(symbol, "15m", period)
    def get_intraday_5m(self, symbol, period="5d"): return self._get(symbol, "5m", period)
    def get_intraday_1m(self, symbol, period="1d"): return self._get(symbol, "1m", period)
    def get_intraday_ohlcv(self, symbol, interval="15m", period="5d"):
        if interval not in {"1m", "5m", "15m", "60m"}: raise ValueError("Desteklenmeyen Fintables aralığı")
        return self._get(symbol, interval, period)
