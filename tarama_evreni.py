"""Analiz stratejileri için merkezi ve açık hisse evreni seçimi."""
from __future__ import annotations

from datetime import date, datetime
from typing import Callable, Iterable

import pandas as pd

from bist30 import BIST30_KUMESI, bist30_hisseleri, normalize_bist_sembolu
from bist_evreni import tum_bist_hisseleri


ALL_BIST = "all_bist"
BIST30_ONLY = "bist30_only"

SHORT_TERM = "short_term"
MEDIUM_TERM = "medium_term"
DAILY_TRADE = "daily_trade"
UNDER_50_TL = "under_50_tl"
CEILING_POTENTIAL = "ceiling_potential"

SCAN_UNIVERSE = {
    SHORT_TERM: BIST30_ONLY,
    MEDIUM_TERM: BIST30_ONLY,
    DAILY_TRADE: ALL_BIST,
    UNDER_50_TL: ALL_BIST,
    CEILING_POTENTIAL: ALL_BIST,
}


def normalize_scan_scope(value: str | None) -> str:
    """Yeni sabitlerle eski ortam değerlerini tek bir kapsama dönüştürür."""
    text = str(value or ALL_BIST).strip().casefold()
    if text in {"bist30", "bist_30", "bist30_only"}:
        return BIST30_ONLY
    return ALL_BIST


def scan_scope_for_strategy(strategy_type: str | None) -> str:
    strategy = str(strategy_type or "general_scan").strip().casefold()
    return SCAN_UNIVERSE.get(strategy, ALL_BIST)


def normalize_symbols(symbols: Iterable[object]) -> list[str]:
    """Geçersiz sembolleri atar, normalize eder ve sırayı bozmadan tekilleştirir."""
    result: list[str] = []
    seen: set[str] = set()
    for value in symbols or ():
        symbol = normalize_bist_sembolu(str(value))
        if symbol and symbol not in seen:
            seen.add(symbol)
            result.append(symbol)
    return result


def get_scan_universe(
    strategy_type: str | None = None,
    *,
    scope: str | None = None,
    all_provider: Callable[[], Iterable[object]] = tum_bist_hisseleri,
    bist30_provider: Callable[[], Iterable[object]] = bist30_hisseleri,
) -> list[str]:
    selected_scope = normalize_scan_scope(scope) if scope is not None else scan_scope_for_strategy(strategy_type)
    provider = bist30_provider if selected_scope == BIST30_ONLY else all_provider
    symbols = normalize_symbols(provider())
    if selected_scope == BIST30_ONLY:
        symbols = [symbol for symbol in symbols if symbol in BIST30_KUMESI]
    return symbols


def strategy_symbol_mask(values, strategy_type: str):
    """Bir tablo için merkezi strateji kapsam maskesi üretir."""
    series = pd.Series(values, copy=False).astype(str)
    if scan_scope_for_strategy(strategy_type) == ALL_BIST:
        return pd.Series(True, index=series.index)
    normalized = series.map(normalize_bist_sembolu)
    return normalized.isin(BIST30_KUMESI)


def filter_frame_for_strategy(frame: pd.DataFrame, strategy_type: str) -> pd.DataFrame:
    if frame is None or frame.empty or "Hisse" not in frame.columns:
        return pd.DataFrame() if frame is None else frame.copy()
    return frame[strategy_symbol_mask(frame["Hisse"], strategy_type)].copy()


def universe_label(scope: str) -> str:
    return "BIST 30" if normalize_scan_scope(scope) == BIST30_ONLY else "Tüm Aktif BIST"


def report_cache_key(strategy_type: str, scope: str, day: date | str | None = None) -> str:
    report_day = day.isoformat() if isinstance(day, date) else str(day or date.today().isoformat())
    return f"{str(strategy_type).strip().casefold()}:{normalize_scan_scope(scope)}:{report_day}"


def report_metadata(strategy_type: str, scope: str, scanned_count: int, result_count: int, created_at=None) -> dict:
    created = created_at or datetime.now()
    created_text = created.isoformat(timespec="seconds") if hasattr(created, "isoformat") else str(created)
    return {
        "Analiz Türü": str(strategy_type),
        "Hisse Evreni": normalize_scan_scope(scope),
        "Hisse Evreni Etiketi": universe_label(scope),
        "Oluşturulma Zamanı": created_text,
        "Taranan Hisse Sayısı": int(scanned_count),
        "Sonuç Sayısı": int(result_count),
        "Cache Anahtarı": report_cache_key(strategy_type, scope, created.date() if hasattr(created, "date") else None),
    }


def metadata_frame_to_dict(frame) -> dict:
    if frame is None or getattr(frame, "empty", True):
        return {}
    if {"Alan", "Değer"}.issubset(frame.columns):
        return dict(zip(frame["Alan"].astype(str), frame["Değer"]))
    return {}


def report_scope_is_compatible(metadata: dict, strategy_type: str) -> bool:
    """Metadata'sı olmayan eski raporlar evren varsayımıyla kullanılmaz."""
    if not metadata or not str(metadata.get("Hisse Evreni", "")).strip():
        return False
    actual = normalize_scan_scope(metadata.get("Hisse Evreni"))
    expected = scan_scope_for_strategy(strategy_type)
    return actual == expected
