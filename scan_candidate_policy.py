"""Tarama adayları için merkezi normalizasyon, işlem planı ve teşhis kuralları."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
import math
from pathlib import Path
import unicodedata


STRATEGY_THRESHOLDS = {
    "daily_trade": {"strong_score": 68.0, "strong_rr": 1.35, "watch_score": 55.0, "watch_rr": 1.10},
    "short_term": {"strong_score": 65.0, "strong_rr": 1.40, "watch_score": 55.0, "watch_rr": 1.15},
    "medium_term": {"strong_score": 64.0, "strong_rr": 1.30, "watch_score": 54.0, "watch_rr": 1.15},
    "under_50": {"strong_score": 65.0, "strong_rr": 1.40, "watch_score": 52.0, "watch_rr": 1.15},
}


def _normalized_text(value) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").strip().upper())
    return " ".join("".join(ch for ch in text if not unicodedata.combining(ch)).split())


def normalize_professional_class(value) -> str:
    text = _normalized_text(value)
    if not text or text in {"NAN", "NONE", "BILINMIYOR"}:
        return "UNKNOWN"
    if "VERI YETERSIZ" in text:
        return "INSUFFICIENT_DATA"
    if any(token in text for token in ("ISLEM YAPMA", "ALMA", "VETO", "RED")):
        return "DO_NOT_TRADE"
    if "UYGUN ADAY" in text or text in {"AL", "BUGUN AL", "GUCLU AL"}:
        return "SUITABLE"
    if "TEYIT" in text or "BEKLE" in text:
        return "WAIT_CONFIRMATION"
    if "IZLE" in text or "TAKIP" in text or "TUT" in text:
        return "WATCH"
    return "UNKNOWN"


def normalize_data_status(value) -> str:
    text = _normalized_text(value)
    if not text or text in {"NAN", "NONE"}:
        return "PARTIAL"
    if any(token in text for token in ("BOZUK", "GECERSIZ", "INVALID", "HATA", "VERI YOK")):
        return "INVALID"
    if any(token in text for token in ("ESKI", "STALE", "KARAR YOK")):
        return "STALE"
    if any(token in text for token in ("GUVENILIR", "YETERLI", "CANLI", "RELIABLE", "OK")):
        return "RELIABLE"
    if any(token in text for token in ("GECIKMELI", "KONTROL", "KISMI", "PARTIAL")):
        return "PARTIAL"
    return "PARTIAL"


def finite_number(value) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


@dataclass(frozen=True)
class TradePlan:
    target: float | None
    stop: float | None
    rr: float | None
    source: str


def safe_risk_reward(entry, target, stop) -> float | None:
    entry_value, target_value, stop_value = map(finite_number, (entry, target, stop))
    if entry_value is None or target_value is None or stop_value is None:
        return None
    risk = entry_value - stop_value
    reward = target_value - entry_value
    if entry_value <= 0 or risk <= 0 or reward <= 0:
        return None
    result = reward / risk
    return result if math.isfinite(result) else None


def safe_trade_plan(entry, target, stop, atr=None, support=None, resistance=None,
                    strategy: str = "short_term") -> TradePlan:
    entry_value = finite_number(entry)
    if entry_value is None or entry_value <= 0:
        return TradePlan(None, None, None, "Geçersiz fiyat")
    target_value, stop_value = finite_number(target), finite_number(stop)
    direct_rr = safe_risk_reward(entry_value, target_value, stop_value)
    if direct_rr is not None:
        return TradePlan(target_value, stop_value, direct_rr, "Model")

    atr_value = finite_number(atr)
    support_value = finite_number(support)
    resistance_value = finite_number(resistance)
    if atr_value is None or atr_value <= 0:
        return TradePlan(None, None, None, "Plan hesaplanamadı")
    stop_factor = 1.25 if strategy == "daily_trade" else 1.5 if strategy == "short_term" else 2.0
    target_factor = 1.8 if strategy == "daily_trade" else 2.2 if strategy == "short_term" else 3.0
    atr_stop = entry_value - atr_value * stop_factor
    stop_candidates = [atr_stop]
    if support_value is not None and 0 < support_value < entry_value:
        stop_candidates.append(support_value * 0.995)
    # En yakın geçerli koruma seviyesi gereksiz geniş riski önler.
    stop_value = max(stop_candidates)
    atr_target = entry_value + atr_value * target_factor
    target_candidates = [atr_target]
    if resistance_value is not None and resistance_value > entry_value:
        target_candidates.append(resistance_value)
    target_value = max(target_candidates)
    rr = safe_risk_reward(entry_value, target_value, stop_value)
    return TradePlan(target_value, stop_value, rr, "ATR + destek/direnç fallback")


@dataclass
class ScanDiagnostics:
    strategy: str
    universe: str = "ALL_ACTIVE_BIST"
    symbols_total: int = 0
    data_ok: int = 0
    analysis_ok: int = 0
    invalid_price: int = 0
    invalid_target_stop: int = 0
    data_quality_rejected: int = 0
    professional_veto: int = 0
    score_rejected: int = 0
    rr_rejected: int = 0
    strong_candidates: int = 0
    watch_candidates: int = 0
    errors: int = 0
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat(timespec="seconds")

    def is_consistent(self) -> bool:
        counts = asdict(self)
        numeric = [value for key, value in counts.items() if key not in {"strategy", "universe", "created_at"}]
        return all(isinstance(value, int) and value >= 0 for value in numeric) and self.data_ok + self.errors <= self.symbols_total

    def to_dict(self) -> dict:
        return asdict(self)

    def summary(self) -> str:
        return (f"{self.symbols_total} hisse tarandı · {self.analysis_ok} analiz başarılı · "
                f"{self.strong_candidates} güçlü aday · {self.watch_candidates} takip adayı · "
                f"{self.errors} veri hatası")


def diagnostics_log_path() -> Path:
    return Path.home() / "Documents" / "Borsa Analiz Pro MAX" / "logs" / "scan_diagnostics.log"


def write_scan_diagnostics(diagnostics: ScanDiagnostics, path: Path | None = None) -> Path:
    destination = path or diagnostics_log_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(diagnostics.to_dict(), ensure_ascii=False) + "\n")
    return destination
