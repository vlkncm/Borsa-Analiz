from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib

import pandas as pd


ANALYSIS_UNIVERSES = {
    "daily_trade": "ALL_ACTIVE_BIST",
    "short_term": "BIST30",
    "medium_term": "BIST30",
    "under_50": "ALL_ACTIVE_BIST_UNDER_50",
    "high_movement": "ALL_ACTIVE_BIST",
}

MODEL_VERSIONS = {
    "daily_trade": "gunluk-trade-v1",
    "short_term": "vade-kisa-v1",
    "medium_term": "vade-orta-v1",
    "under_50": "elli-tl-v1",
    "high_movement": "t1t2-v1",
}


def normalize_symbols(symbols) -> list[str]:
    result = []
    seen = set()
    for value in symbols or ():
        symbol = str(value or "").strip().upper()
        if symbol and not symbol.endswith(".IS"):
            symbol += ".IS"
        if symbol and symbol not in seen:
            seen.add(symbol)
            result.append(symbol)
    return result


def build_analysis_universes(all_active, bist30) -> dict[str, list[str]]:
    all_symbols = normalize_symbols(all_active)
    all_set = set(all_symbols)
    bist30_symbols = [symbol for symbol in normalize_symbols(bist30) if symbol in all_set]
    return {
        "daily_trade": list(all_symbols),
        "short_term": list(bist30_symbols),
        "medium_term": list(bist30_symbols),
        # Fiyat filtresi veri alindiktan sonra ilgili motorda uygulanir.
        "under_50": list(all_symbols),
        "high_movement": list(all_symbols),
    }


def filter_frame_to_symbols(frame: pd.DataFrame, symbols) -> pd.DataFrame:
    if frame is None or frame.empty or "Hisse" not in frame:
        return pd.DataFrame() if frame is None else frame.iloc[0:0].copy()
    allowed = set(normalize_symbols(symbols))
    values = frame["Hisse"].astype(str).str.strip().str.upper()
    values = values.where(values.str.endswith(".IS"), values + ".IS")
    return frame[values.isin(allowed)].copy()


def valid_under_50(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame() if frame is None else frame.iloc[0:0].copy()
    price_column = next((name for name in ("Fiyat", "Mevcut Fiyat", "Referans Fiyat") if name in frame), None)
    if price_column is None:
        return frame.iloc[0:0].copy()
    price = pd.to_numeric(frame[price_column], errors="coerce")
    return frame[price.notna() & price.gt(0) & price.le(50.0)].copy()


@dataclass(frozen=True)
class AnalysisCacheKey:
    symbol: str
    analysis_type: str
    universe_type: str
    data_timestamp: str
    model_version: str
    scan_id: str

    def value(self) -> str:
        raw = "|".join((self.symbol, self.analysis_type, self.universe_type,
                        self.data_timestamp, self.model_version, self.scan_id))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def tag_analysis_result(frame: pd.DataFrame, analysis_type: str, scan_id: str,
                        data_timestamp: str | None = None) -> pd.DataFrame:
    result = pd.DataFrame() if frame is None else frame.copy()
    timestamp = data_timestamp or datetime.now().isoformat(timespec="seconds")
    result["Analiz Türü"] = analysis_type
    result["Evren Türü"] = ANALYSIS_UNIVERSES[analysis_type]
    result["Model Sürümü"] = MODEL_VERSIONS[analysis_type]
    result["Tarama Kimliği"] = scan_id
    result["Veri Zaman Damgası"] = timestamp
    if "Hisse" in result:
        result["Cache Anahtarı"] = [
            AnalysisCacheKey(str(symbol), analysis_type, ANALYSIS_UNIVERSES[analysis_type],
                             timestamp, MODEL_VERSIONS[analysis_type], scan_id).value()
            for symbol in result["Hisse"]
        ]
    return result
