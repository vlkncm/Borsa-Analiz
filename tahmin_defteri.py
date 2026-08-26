"""Değiştirilemez tahmin olay günlüğü, sonuçlandırma ve performans ölçümü."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable
import uuid

import pandas as pd


def varsayilan_yol() -> Path:
    path = Path.home() / "Documents" / "Borsa Analiz Pro MAX" / "performans" / "tahmin_olaylari.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _canonical(event: dict) -> str:
    return json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def olaylari_oku(path: Path | None = None) -> list[dict]:
    path = path or varsayilan_yol()
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except Exception:
            rows.append({"event_type": "CORRUPT_LINE", "raw": line})
    return rows


def zinciri_dogrula(path: Path | None = None) -> tuple[bool, str]:
    previous = "GENESIS"
    for index, event in enumerate(olaylari_oku(path), 1):
        if event.get("event_type") == "CORRUPT_LINE":
            return False, f"{index}. satır okunamadı"
        stored = event.get("event_hash", "")
        payload = {k: v for k, v in event.items() if k != "event_hash"}
        expected = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
        if event.get("previous_hash") != previous or stored != expected:
            return False, f"{index}. olayın hash zinciri geçersiz"
        previous = stored
    return True, "Olay zinciri doğrulandı"


def olay_ekle(event: dict, path: Path | None = None) -> dict:
    path = path or varsayilan_yol()
    path.parent.mkdir(parents=True, exist_ok=True)
    events = olaylari_oku(path)
    previous = events[-1].get("event_hash", "GENESIS") if events else "GENESIS"
    payload = dict(event)
    payload.setdefault("event_id", uuid.uuid4().hex)
    payload.setdefault("event_time", datetime.now(timezone.utc).isoformat())
    payload["previous_hash"] = previous
    payload["event_hash"] = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str) + "\n")
    return payload


def sinyal_kaydet(item: dict, strategy_id: str, path: Path | None = None) -> dict:
    return olay_ekle({
        "event_type": "SIGNAL_CREATED", "signal_id": uuid.uuid4().hex,
        "symbol": item.get("symbol", item.get("Hisse", "")), "strategy_id": strategy_id,
        "data_time": item.get("veri_tarihi", item.get("Veri Tarihi", "")),
        "market_regime": item.get("piyasa_rejimi_v2", "YATAY"),
        "sector": item.get("sektor_adi", "BİLİNMİYOR"), "sector_score": item.get("sektor_puani", 0),
        "entry_low": item.get("onerilen_alis_alt", 0), "entry_high": item.get("onerilen_alis_ust", 0),
        "target_1": item.get("hedef_1", 0), "target_2": item.get("onerilen_satis", item.get("hedef_2", 0)),
        "stop": item.get("onerilen_stop", item.get("stop_loss", 0)),
        "duration_low": item.get("beklenen_sure_alt", 0), "duration_high": item.get("beklenen_sure_ust", 0),
        "confidence": item.get("ayarlanmis_guven", item.get("v4_guven_puani", 0)),
        "calibrated_probability": item.get("kalibre_olasilik"), "risk_reward": item.get("karar_risk_getiri", 0),
        "net_ev": item.get("net_ev_yuzde", -999), "decision": item.get("profesyonel_karar", "İZLE"),
        "estimated_cost_pct": item.get("tahmini_maliyet_yuzde", 0),
    }, path)


def aktif_sinyaller(path: Path | None = None) -> list[dict]:
    events = olaylari_oku(path)
    created = {e.get("signal_id"): e for e in events if e.get("event_type") == "SIGNAL_CREATED"}
    closed = {e.get("signal_id") for e in events if e.get("event_type") == "SIGNAL_OUTCOME"}
    return [event for key, event in created.items() if key not in closed]


def sonucu_hesapla(signal: dict, ohlc: pd.DataFrame, commission_bps: float = 10,
                    slippage_bps: float = 7) -> dict:
    required = {"High", "Low", "Close"}
    if ohlc is None or ohlc.empty or not required.issubset(ohlc.columns):
        return {"status": "BELİRSİZ", "reason": "Sonuçlandırma için OHLC verisi yok"}
    data = ohlc.copy().dropna(subset=list(required))
    if data.empty:
        return {"status": "BELİRSİZ", "reason": "Geçerli OHLC satırı yok"}
    entry = float(signal.get("entry_high") or signal.get("entry_low") or 0)
    target = float(signal.get("target_2") or signal.get("target_1") or 0)
    stop = float(signal.get("stop") or 0)
    if not 0 < stop < entry < target:
        return {"status": "BELİRSİZ", "reason": "Sinyal seviyeleri tutarsız"}
    outcome, exit_price, hit_day = "SÜRESİ DOLDU", float(data["Close"].iloc[-1]), len(data)
    # Aynı barda hedef ve stop varsa iyimserlikten kaçınarak stop önce sayılır.
    for day, (_, row) in enumerate(data.iterrows(), 1):
        if float(row["Low"]) <= stop:
            outcome, exit_price, hit_day = "STOP ÖNCE", stop, day; break
        if float(row["High"]) >= target:
            outcome, exit_price, hit_day = "HEDEF ÖNCE", target, day; break
    max_up = (float(data["High"].max())/entry-1)*100
    max_down = (float(data["Low"].min())/entry-1)*100
    cost = (2*commission_bps+2*slippage_bps)/100
    net = (exit_price/entry-1)*100-cost
    expected_high = int(signal.get("duration_high") or len(data))
    return {"status": outcome, "hit_day": hit_day, "max_up_pct": round(max_up, 2),
        "max_down_pct": round(max_down, 2), "gross_return_pct": round((exit_price/entry-1)*100, 2),
        "net_return_pct": round(net, 2), "duration_accurate": hit_day <= expected_high,
        "exit_price": round(exit_price, 4), "commission_bps": commission_bps, "slippage_bps": slippage_bps}


def sonucu_kaydet(signal: dict, ohlc: pd.DataFrame, path: Path | None = None, **costs) -> dict:
    outcome = sonucu_hesapla(signal, ohlc, **costs)
    return olay_ekle({"event_type": "SIGNAL_OUTCOME", "signal_id": signal.get("signal_id"),
        "symbol": signal.get("symbol"), "strategy_id": signal.get("strategy_id"), **outcome}, path)


def acik_tahminleri_sonuclandir(path: Path | None = None, provider=None) -> list[dict]:
    """Açık tahminleri yeni OHLC ile hedef-stop sırasına göre otomatik kapatır.

    Hedef/stop görülmediyse yalnızca öngörülen azami işlem günü dolduğunda
    ``SÜRESİ DOLDU`` kaydı oluşturur; erken dönemde açık kaydı kapatmaz.
    """
    if provider is None:
        from veri_saglayici import get_daily_ohlcv
        provider = lambda symbol: get_daily_ohlcv(symbol, "1y")[0]
    saved = []
    for signal in aktif_sinyaller(path):
        try:
            frame = provider(signal.get("symbol", ""))
            if frame is None or frame.empty:
                continue
            data_time = pd.to_datetime(signal.get("data_time"), errors="coerce", utc=True)
            if pd.notna(data_time) and isinstance(frame.index, pd.DatetimeIndex):
                index = frame.index
                compare = index.tz_localize("UTC") if index.tz is None else index.tz_convert("UTC")
                frame = frame.loc[compare > data_time]
            if frame.empty:
                continue
            result = sonucu_hesapla(signal, frame)
            duration = int(signal.get("duration_high") or 0)
            if result["status"] == "SÜRESİ DOLDU" and (duration <= 0 or len(frame) < duration):
                continue
            saved.append(olay_ekle({"event_type": "SIGNAL_OUTCOME", "signal_id": signal.get("signal_id"),
                "symbol": signal.get("symbol"), "strategy_id": signal.get("strategy_id"), **result}, path))
        except Exception:
            continue
    return saved


def performans_ozeti(path: Path | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    events = olaylari_oku(path)
    signals = {e.get("signal_id"): e for e in events if e.get("event_type") == "SIGNAL_CREATED"}
    outcomes = [e for e in events if e.get("event_type") == "SIGNAL_OUTCOME"]
    rows = []
    for event in outcomes:
        base = signals.get(event.get("signal_id"), {})
        rows.append({**base, **event})
    detail = pd.DataFrame(rows)
    open_count = len(set(signals)-{x.get("signal_id") for x in outcomes})
    if detail.empty:
        summary = pd.DataFrame([{"Açık": open_count, "Tamamlanan": 0, "Başarılı": 0, "Başarısız": 0,
            "Süresi Dolan": 0, "Hedef Önce %": 0, "Stop Önce %": 0, "Ortalama Net %": 0,
            "Brier": None, "Örnek": 0}])
        return summary, detail
    target = detail["status"].eq("HEDEF ÖNCE")
    stop = detail["status"].eq("STOP ÖNCE")
    p = pd.to_numeric(detail.get("calibrated_probability"), errors="coerce")/100
    valid_p = p.notna()
    brier = float(((p[valid_p]-target[valid_p].astype(float))**2).mean()) if valid_p.any() else None
    summary = pd.DataFrame([{"Açık": open_count, "Tamamlanan": len(detail), "Başarılı": int(target.sum()),
        "Başarısız": int(stop.sum()), "Süresi Dolan": int(detail["status"].eq("SÜRESİ DOLDU").sum()),
        "Hedef Önce %": round(target.mean()*100, 2), "Stop Önce %": round(stop.mean()*100, 2),
        "Ortalama Yükseliş %": round(pd.to_numeric(detail["max_up_pct"], errors="coerce").mean(), 2),
        "Ortalama Düşüş %": round(pd.to_numeric(detail["max_down_pct"], errors="coerce").mean(), 2),
        "Ortalama Net %": round(pd.to_numeric(detail["net_return_pct"], errors="coerce").mean(), 2),
        "Brier": round(brier, 4) if brier is not None else None, "Örnek": len(detail)}])
    return summary, detail


def model_sagligi(path: Path | None = None, min_samples: int = 30) -> dict[str, Any]:
    summary, detail = performans_ozeti(path)
    row = summary.iloc[0].to_dict()
    samples = int(row.get("Örnek", 0))
    if samples < min_samples:
        return {"protection_mode": True, "reason": "Yetersiz canlı örnek; yalnızca izleme", "risk_multiplier": .5}
    target_rate = float(row.get("Hedef Önce %", 0))
    avg_net = float(row.get("Ortalama Net %", 0))
    brier = row.get("Brier")
    degraded = target_rate < 45 or avg_net <= 0 or (brier is not None and not pd.isna(brier) and float(brier) > .25)
    return {"protection_mode": degraded,
        "reason": "Canlı performans bozuldu" if degraded else "Canlı performans kabul edilebilir",
        "risk_multiplier": .5 if degraded else 1.0}
