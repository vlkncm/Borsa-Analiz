"""T+1/T+2 radarinin tek, izlenebilir karar sozlesmesi.

Worker, dashboard, detay ekrani ve snapshot bu modulun urettigi ayni sonucu
kullanir. Kural skoru yalniz teknik on degerlendirmedir; kalibre model kararini
ezemez.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Iterable, Mapping


REASON_TEXT = {
    "MISSING_PRICE_DATA": "Fiyat verisi bulunamadi",
    "STALE_PRICE_DATA": "Fiyat verisi ortak tarama kesiminden eski",
    "SYMBOL_MAPPING_ERROR": "Veri saglayici sembol eslemesi dogrulanamadi",
    "SECURITY_TYPE_UNVERIFIED": "Menkul turu dogrulanamadi",
    "SHORT_HISTORY": "Standart model icin islem gecmisi kisa",
    "MODEL_NOT_CALIBRATED": "Bu yol icin kalibre model yok",
    "MISSING_MODEL_FEATURES": "Model girdilerinden biri veya birkaci eksik",
    "OUTSIDE_TOP_PERCENTILE": "Kesitsel ilk yuzdelik dilimde degil",
    "P7_BELOW_THRESHOLD": "%7+ model esiginin altinda",
    "P8_BELOW_THRESHOLD": "%8+ model esiginin altinda",
    "LIMIT_PROBABILITY_LOW": "Tavan hazirlik olasiligi dusuk",
    "LEVELS_NOT_VALIDATED": "Giris, hedef ve stop birlikte dogrulanamadi",
    "NET_EV_NOT_POSITIVE": "Net beklenen deger pozitif degil",
    "NET_EV_UNAVAILABLE": "Net beklenen deger hesaplanamadi",
    "SLIPPAGE_RISK": "Tahmini fiyat kaymasi yuksek",
    "LOW_LIQUIDITY": "Likidite teyidi zayif",
    "MOVE_ALREADY_EXTENDED": "Hareket ATR bazinda fazla ilerlemis",
    "NEGATIVE_KAP": "Dogrulanmis olumsuz KAP riski var",
    "KAP_UNAVAILABLE": "KAP durumu alinamadi; olumsuz haber varsayilmadi",
    "MARKET_RISK_OFF": "Piyasa rejimi risk-off",
    "MARKET_DATA_UNAVAILABLE": "BIST 100 rejim verisi alinamadi",
    "SECTOR_WEAK": "Sektor goreceli gucu zayif",
    "SECTOR_DATA_UNAVAILABLE": "Sektor verisi yok; otomatik olumsuz sayilmadi",
    "INCLUDED_WIDE_RADAR": "Kesitsel genis radara dahil",
    "INCLUDED_ELITE": "Guvenlik kosullariyla seckin listeye dahil",
    "INCLUDED_IPO_RADAR": "Kalibre edilmemis yeni halka arz radarinda",
}


@dataclass(frozen=True)
class CandidateDecision:
    symbol: str
    horizon: str
    rank: int | None
    percentile: float | None
    probabilities: Mapping[str, float | None]
    reference_score: float | None
    final_decision: str
    decision_reasons: tuple[str, ...]
    risks: tuple[str, ...]
    gate_codes: tuple[str, ...]
    rejected_by: str | None
    security_type: str
    data_freshness: str
    model_version: str
    feature_hash: str
    market_regime: str | None
    sector_score: float | None
    kap_status: str | None
    entry: float | None
    target: float | None
    stop: float | None
    risk_reward: float | None
    net_ev: float | None
    eligible_wide: bool = False
    eligible_elite: bool = False
    probability_reliable: bool = False
    technical_precheck: float | None = None
    current_price: float | None = None
    ceiling_price: float | None = None
    why_not_elite: tuple[str, ...] = ()
    as_of_timestamp: str = ""
    cache_key: str = ""
    data_version: str = ""
    security_cache_source: str | None = None
    security_cache_at: str | None = None
    security_cache_stale: bool | None = None

    def dict(self) -> dict[str, Any]:
        return asdict(self)


def _finite(value: Any) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _contains(values: Iterable[str], needle: str) -> bool:
    return any(needle in str(value).upper() for value in values)


def build_candidate_decisions(
    ranked_rows: Iterable[Mapping[str, Any]],
    *,
    market_regime: str | None,
    contexts: Mapping[str, Mapping[str, Any]] | None = None,
    wide_limit: int = 50,
) -> list[CandidateDecision]:
    """Siralanmis model satirlarindan ortak karar uretir.

    Net EV henuz karar kapisi olarak dogrulanmadigi icin negatif olmasi satiri
    gizlemez. Diger guvenlik kosullari uygunsa sonuc acikca ``IZLE`` olur.
    """
    rows, contexts = list(ranked_rows), contexts or {}
    decisions: list[CandidateDecision] = []
    for row in rows:
        symbol = str(row.get("symbol", ""))
        ctx = contexts.get(symbol, {})
        probs = dict(row.get("probabilities") or {})
        reliable = all(_finite(probs.get(name)) for name in ("max_7", "max_8", "limit_up"))
        short = str(row.get("status", "")).startswith(("YENI HALKA", "HAREKET KACTI"))
        rank = int(row["rank"]) if _finite(row.get("rank")) else None
        percentile = float(row["percentile"]) if _finite(row.get("percentile")) else None
        security_type = str(row.get("security_type") or "BELIRSIZ")
        freshness = str(ctx.get("data_freshness") or "BELIRSIZ")
        kap_status = ctx.get("kap_status")
        sector_score = ctx.get("sector_score")
        risks = list(row.get("risks") or ())
        reasons = list(row.get("reasons") or ())
        gates: list[str] = []

        if freshness == "MISSING": gates.append("MISSING_PRICE_DATA")
        elif freshness != "GUNCEL": gates.append("STALE_PRICE_DATA")
        if ctx.get("symbol_mapping_error"): gates.append("SYMBOL_MAPPING_ERROR")
        if security_type == "BELIRSIZ": gates.append("SECURITY_TYPE_UNVERIFIED")
        if short: gates.append("SHORT_HISTORY")
        if not reliable: gates.append("MODEL_NOT_CALIBRATED")
        if row.get("missing_features"): gates.append("MISSING_MODEL_FEATURES")
        if percentile is None or percentile < 95: gates.append("OUTSIDE_TOP_PERCENTILE")
        if reliable and float(probs["max_7"]) < 20: gates.append("P7_BELOW_THRESHOLD")
        if reliable and float(probs["max_8"]) < 10: gates.append("P8_BELOW_THRESHOLD")
        if reliable and float(probs["limit_up"]) < 3: gates.append("LIMIT_PROBABILITY_LOW")
        if not bool(row.get("levels_valid")): gates.append("LEVELS_NOT_VALIDATED")
        ev = row.get("net_ev_pct")
        if not _finite(ev): gates.append("NET_EV_UNAVAILABLE")
        elif float(ev) <= 0: gates.append("NET_EV_NOT_POSITIVE")
        if _contains(risks, "KAYMA"): gates.append("SLIPPAGE_RISK")
        if _contains(risks, "HACIM TEYIDI ZAYIF"): gates.append("LOW_LIQUIDITY")
        if _contains(risks, "ILERLEMIS"): gates.append("MOVE_ALREADY_EXTENDED")
        if str(kap_status).upper() == "NEGATIF": gates.append("NEGATIVE_KAP")
        elif kap_status in (None, "", "BELIRSIZ", "VERI_YOK", "HATA"): gates.append("KAP_UNAVAILABLE")
        if market_regime in (None, "", "VERI YETERSIZ", "VERİ YETERSİZ"):
            gates.append("MARKET_DATA_UNAVAILABLE")
        elif str(market_regime).upper() in {"NEGATIF", "RISK_OFF", "RİSK-OFF"}:
            gates.append("MARKET_RISK_OFF")
        if sector_score is None: gates.append("SECTOR_DATA_UNAVAILABLE")
        elif float(sector_score) < 0: gates.append("SECTOR_WEAK")

        wide = bool(short or (reliable and rank is not None and rank <= wide_limit))
        if short:
            gates.append("INCLUDED_IPO_RADAR")
        elif wide:
            gates.append("INCLUDED_WIDE_RADAR")

        hard = {
            "MISSING_PRICE_DATA", "STALE_PRICE_DATA", "SYMBOL_MAPPING_ERROR",
            "SECURITY_TYPE_UNVERIFIED", "MODEL_NOT_CALIBRATED", "MISSING_MODEL_FEATURES",
            "OUTSIDE_TOP_PERCENTILE", "P7_BELOW_THRESHOLD", "P8_BELOW_THRESHOLD",
            "LEVELS_NOT_VALIDATED", "SLIPPAGE_RISK", "LOW_LIQUIDITY",
            "MOVE_ALREADY_EXTENDED", "NEGATIVE_KAP", "MARKET_RISK_OFF", "SECTOR_WEAK",
        }
        # KAP/sektor verisinin yoklugu belirsizliktir; tek basina eleme degildir.
        blockers = [code for code in gates if code in hard]
        elite = reliable and not short and not blockers
        if elite: gates.append("INCLUDED_ELITE")

        if short:
            decision = "YENİ ALIM YAPMA" if _contains(risks, "GEC GIRIS") else "VERİ YETERSİZ"
        elif not reliable or freshness == "MISSING":
            decision = "VERİ YETERSİZ"
        elif blockers:
            decision = "BEKLE"
        elif not _finite(ev):
            decision = "VERİ YETERSİZ"
        elif float(ev) > 0:
            decision = "AL ADAYI – CANLI TEYİT BEKLE"
        else:
            decision = "İZLE – RİSK/GETİRİ TEYİDİ"

        reasons.extend(REASON_TEXT[code] for code in gates if code.startswith("INCLUDED_"))
        why_not = tuple(REASON_TEXT[code] for code in gates if code in hard or code.startswith("NET_EV_"))
        rejected = next((code for code in gates if code in hard), None)
        decisions.append(CandidateDecision(
            symbol=symbol, horizon=str(row.get("horizon", "")), rank=rank, percentile=percentile,
            probabilities=probs, reference_score=(row.get("ranking_score") if _finite(row.get("ranking_score")) else row.get("raw_score")), final_decision=decision,
            decision_reasons=tuple(dict.fromkeys(reasons)), risks=tuple(dict.fromkeys(risks)),
            gate_codes=tuple(dict.fromkeys(gates)), rejected_by=rejected,
            security_type=security_type, data_freshness=freshness,
            model_version=str(row.get("model_version", "")), feature_hash=str(row.get("feature_hash", "")),
            market_regime=market_regime, sector_score=sector_score, kap_status=kap_status,
            entry=row.get("entry_high"), target=row.get("target_7"), stop=row.get("stop"),
            risk_reward=row.get("risk_reward"), net_ev=float(ev) if _finite(ev) else None,
            eligible_wide=wide, eligible_elite=elite, probability_reliable=reliable,
            technical_precheck=row.get("raw_score"), why_not_elite=why_not,
            current_price=row.get("current_price"), ceiling_price=row.get("ceiling_price"),
            as_of_timestamp=str(row.get("as_of_timestamp", "")), cache_key=str(row.get("cache_key", "")),
            data_version=str(row.get("data_version", "")),
            security_cache_source=ctx.get("security_cache_source"),
            security_cache_at=ctx.get("security_cache_at"),
            security_cache_stale=ctx.get("security_cache_stale"),
        ))
    return decisions


def net_ev_audit(decisions: Iterable[CandidateDecision]) -> dict[str, Any]:
    rows = list(decisions)
    calculated = [item for item in rows if _finite(item.net_ev)]
    positive = [item for item in calculated if float(item.net_ev) > 0]
    negative = [item for item in calculated if float(item.net_ev) <= 0]
    ev_only = [item for item in rows if item.eligible_elite and "NET_EV_NOT_POSITIVE" in item.gate_codes]
    top20 = sorted((item for item in calculated if item.rank is not None), key=lambda x: x.rank)[:20]
    return {
        "scanned": len(rows), "calculated": len(calculated), "positive": len(positive),
        "non_positive": len(negative), "rejected_only_by_ev": len(ev_only),
        "top20": [{"symbol": x.symbol, "rank": x.rank, "net_ev": x.net_ev} for x in top20],
    }


def duplicate_feature_hashes(decisions: Iterable[CandidateDecision]) -> dict[str, tuple[str, ...]]:
    groups: dict[str, list[str]] = {}
    for item in decisions:
        if item.feature_hash:
            groups.setdefault(item.feature_hash, []).append(item.symbol)
    return {key: tuple(values) for key, values in groups.items() if len(set(values)) > 1}
