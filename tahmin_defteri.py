"""Değiştirilemez tahmin olay günlüğü, sonuçlandırma ve performans ölçümü."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable
import uuid
import threading

_LEDGER_LOCK = threading.RLock()
EVALUATION_VERSION = 2
TERMINAL = {"HEDEF ÖNCE", "STOP ÖNCE", "SÜRESİ DOLDU", "GİRİŞ OLMADI"}

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
    with _LEDGER_LOCK:
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
    # Aynı veri günü/strateji/hisse tekrar tarandığında örnek sayısını şişirme.
    data_time = item.get("veri_tarihi", item.get("Veri Tarihi", ""))
    symbol = item.get("symbol", item.get("Hisse", ""))
    with _LEDGER_LOCK:
        events = olaylari_oku(path)
        closed = {e.get("signal_id") for e in events if e.get("event_type") == "SIGNAL_OUTCOME"}
        for event in events:
            if (event.get("event_type") == "SIGNAL_CREATED"
                    and event.get("evaluation_version") == EVALUATION_VERSION
                    and ((data_time and event.get("data_time") == data_time) or event.get("signal_id") not in closed)
                    and event.get("symbol") == symbol and event.get("strategy_id") == strategy_id):
                return event
        return olay_ekle({
        "evaluation_version": EVALUATION_VERSION,
        "entry_policy": "band_next_session",
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
    """Sonraki seans giriş bandı, sabit vade ve muhafazakâr OHLC sıralaması.

    OHLC barı içinde girişten önce mi sonra mı hedef görüldüğü bilinmez. Giriş
    açılışta değilse aynı bar hedefi sayılmaz; stop ihtimali muhafazakâr sayılır.
    """
    required = ["Open", "High", "Low", "Close"]
    if ohlc is None or ohlc.empty or not set(required).issubset(ohlc):
        return {"status": "BELİRSİZ", "reason": "Sonuçlandırma için tam OHLC verisi yok"}
    data = ohlc.copy().sort_index()
    data = data.loc[~data.index.duplicated(keep="last")]
    data[required] = data[required].apply(pd.to_numeric, errors="coerce").replace([math.inf, -math.inf], float("nan"))
    valid = (data[required].notna().all(axis=1) & (data[required] > 0).all(axis=1)
             & data["High"].ge(data[["Open", "Close", "Low"]].max(axis=1))
             & data["Low"].le(data[["Open", "Close", "High"]].min(axis=1)))
    try:
        low = float(signal.get("entry_low") or signal.get("entry_high") or 0)
        high = float(signal.get("entry_high") or low)
        target = float(signal.get("target_2") or signal.get("target_1") or 0)
        stop = float(signal.get("stop") or 0)
        duration = int(signal.get("duration_high") or 0)
        if not all(math.isfinite(x) for x in (low, high, target, stop, commission_bps, slippage_bps)):
            raise ValueError()
        if not 0 < stop < low <= high < target or duration <= 0 or min(commission_bps, slippage_bps) < 0:
            raise ValueError()
    except (ValueError, TypeError, OverflowError):
        return {"status": "BELİRSİZ", "reason": "Sinyal seviyeleri, maliyet veya vade tutarsız"}
    data = data.iloc[:duration]
    entry = None
    entry_day = None
    visited = []
    outcome = "AÇIK"
    exit_price = None
    for day, (_, row) in enumerate(data.iterrows(), 1):
        if not valid.iloc[day-1]:
            return {"status": "BELİRSİZ", "reason": "Geçersiz OHLC; eksik bar atlanarak vade hesaplanamaz"}
        opening = float(row["Open"])
        at_open = False
        if entry is None:
            if low <= opening <= high:
                entry, at_open = opening, True
            elif opening > high and float(row["Low"]) <= high:
                entry = high
            # Bandın altında açılışta yükseliş yönü/gerçekleşme sırası belirsiz:
            # gün içinde kovalamak yerine sonraki seans beklenir.
            else:
                continue
            entry_day = day
        # Geri çekilme girişinden önceki bar ekstremumları gerçekleşmiş
        # pozisyonun hareketi değildir. Bu bar için yalnız giriş/final kapanış.
        visited.append(row if day != entry_day or at_open else
                       {"High": max(entry, float(row["Close"])),
                        "Low": min(entry, float(row["Close"]))})
        if day != entry_day or at_open:
            if opening <= stop:
                outcome, exit_price = "STOP ÖNCE", opening
                break
            if opening >= target:
                outcome, exit_price = "HEDEF ÖNCE", target
                break
        if float(row["Low"]) <= stop:
            outcome, exit_price = "STOP ÖNCE", stop
            break
        if (day != entry_day or at_open) and float(row["High"]) >= target:
            outcome, exit_price = "HEDEF ÖNCE", target
            break
    if entry is None:
        return {"status": "GİRİŞ OLMADI" if len(data) >= duration else "GİRİŞ BEKLİYOR",
                "evaluation_version": EVALUATION_VERSION, "filled": False}
    if outcome == "AÇIK":
        if len(data) < duration:
            return {"status": "AÇIK", "filled": True, "entry_price": entry,
                    "entry_day": entry_day, "evaluation_version": EVALUATION_VERSION}
        outcome, exit_price = "SÜRESİ DOLDU", float(data["Close"].iloc[-1])
    # Çıkış barının içindeki ekstremum sırası bilinmediğinden yalnızca önceki
    # barlar ve gerçekleşen çıkış kullanılır; çıkıştan sonraki hareket sayılmaz.
    prior = visited[:-1]
    max_price = max([entry, exit_price] + [float(r["High"]) for r in prior])
    min_price = min([entry, exit_price] + [float(r["Low"]) for r in prior])
    cost = (2 * commission_bps + 2 * slippage_bps) / 100
    gross = (exit_price / entry - 1) * 100
    return {"status": outcome, "filled": True, "entry_price": round(entry, 4),
        "entry_day": entry_day, "hit_day": day, "evaluation_version": EVALUATION_VERSION,
        "max_up_pct": round((max_price / entry - 1) * 100, 2),
        "max_down_pct": round((min_price / entry - 1) * 100, 2),
        "excursion_method": "completed_bars_before_exit_and_fill_prices",
        "gross_return_pct": round(gross, 2), "net_return_pct": round(gross - cost, 2),
        "duration_accurate": outcome == "HEDEF ÖNCE" and int(signal.get("duration_low") or 1) <= day <= duration,
        "exit_price": round(exit_price, 4), "commission_bps": commission_bps, "slippage_bps": slippage_bps}


def sonucu_kaydet(signal: dict, ohlc: pd.DataFrame, path: Path | None = None, **costs) -> dict:
    with _LEDGER_LOCK:
        for event in olaylari_oku(path):
            if event.get("event_type") == "SIGNAL_OUTCOME" and event.get("signal_id") == signal.get("signal_id"):
                return event
        outcome = sonucu_hesapla(signal, ohlc, **costs)
        if outcome["status"] not in TERMINAL:
            return outcome
        return olay_ekle({"event_type": "SIGNAL_OUTCOME", "signal_id": signal.get("signal_id"),
            "symbol": signal.get("symbol"), "strategy_id": signal.get("strategy_id"), **outcome}, path)


def acik_tahminleri_sonuclandir(path: Path | None = None, provider=None) -> list[dict]:
    """Yalnızca sinyal oluşturulduktan sonraki tamamlanmış seansları değerlendirir."""
    if provider is None:
        from veri_saglayici import get_daily_ohlcv
        provider = lambda symbol: get_daily_ohlcv(symbol, "1y")[0]
    saved = []
    for signal in aktif_sinyaller(path):
        # Eski muhasebe kayıtlarını sessizce yeni yöntemle değiştirme.
        if signal.get("evaluation_version") != EVALUATION_VERSION:
            continue
        try:
            frame = provider(signal.get("symbol", ""))
            if frame is None or frame.empty or frame.attrs.get("stale_fallback") or not isinstance(frame.index, pd.DatetimeIndex):
                continue
            timestamps = []
            for key in ("data_time", "event_time"):
                stamp = pd.to_datetime(signal.get(key), errors="coerce")
                if pd.isna(stamp):
                    break
                stamp = stamp.tz_localize("Europe/Istanbul") if stamp.tzinfo is None else stamp.tz_convert("Europe/Istanbul")
                timestamps.append(stamp.date())
            if len(timestamps) != 2:
                continue
            index = frame.index
            index = index.tz_localize("Europe/Istanbul") if index.tz is None else index.tz_convert("Europe/Istanbul")
            frame = frame.loc[index.date > max(timestamps)]
            if frame.empty:
                continue
            result = sonucu_kaydet(signal, frame, path)
            if result.get("event_type") == "SIGNAL_OUTCOME":
                saved.append(result)
        except Exception:
            continue
    return saved


def performans_ozeti(path: Path | None = None, strategy_id: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    events = olaylari_oku(path)
    signals = {e.get("signal_id"): e for e in events if e.get("event_type") == "SIGNAL_CREATED"}
    if strategy_id is not None:
        signals = {key: value for key, value in signals.items() if value.get("strategy_id") == strategy_id}
    outcomes = list({e.get("signal_id"): e for e in events if e.get("event_type") == "SIGNAL_OUTCOME"}.values())
    rows = []
    for event in outcomes:
        if event.get("signal_id") not in signals:
            continue
        base = signals.get(event.get("signal_id"), {})
        rows.append({**base, **event, "evaluation_version": base.get("evaluation_version"),
                     "strategy_id": base.get("strategy_id")})
    all_detail = pd.DataFrame(rows)
    rows = [r for r in rows if r.get("evaluation_version") == EVALUATION_VERSION
            and r.get("filled") is True and r.get("status") in TERMINAL]
    detail = pd.DataFrame(rows)
    active_ids = {key for key, value in signals.items() if value.get("evaluation_version") == EVALUATION_VERSION}
    open_count = len(active_ids-{x.get("signal_id") for x in outcomes})
    if not all_detail.empty:
        all_detail["Ölçüme Dahil"] = all_detail["signal_id"].isin(set(detail.get("signal_id", [])))
    if detail.empty:
        summary = pd.DataFrame([{"Açık": open_count, "Tamamlanan": 0, "Başarılı": 0, "Başarısız": 0,
            "Süresi Dolan": 0, "Hedef Önce %": 0, "Stop Önce %": 0, "Ortalama Net %": 0,
            "Brier": None, "Örnek": 0, "Hariç Tutulan Eski/İşlemsiz": len(all_detail), "Net Kazanç Oranı %": None}])
        return summary, all_detail
    target = detail["status"].eq("HEDEF ÖNCE")
    stop = detail["status"].eq("STOP ÖNCE")
    p = pd.to_numeric(detail.get("calibrated_probability", pd.Series(index=detail.index, dtype=float)), errors="coerce")/100
    valid_p = p.between(0, 1)
    brier = float(((p[valid_p]-target[valid_p].astype(float))**2).mean()) if valid_p.any() else None
    summary = pd.DataFrame([{"Açık": open_count, "Tamamlanan": len(detail), "Başarılı": int(target.sum()),
        "Başarısız": int(stop.sum()), "Süresi Dolan": int(detail["status"].eq("SÜRESİ DOLDU").sum()),
        "Hedef Önce %": round(target.mean()*100, 2), "Stop Önce %": round(stop.mean()*100, 2),
        "Ortalama Yükseliş %": round(pd.to_numeric(detail["max_up_pct"], errors="coerce").mean(), 2),
        "Ortalama Düşüş %": round(pd.to_numeric(detail["max_down_pct"], errors="coerce").mean(), 2),
        "Ortalama Net %": round(pd.to_numeric(detail["net_return_pct"], errors="coerce").mean(), 2),
        "Net Kazanç Oranı %": round(pd.to_numeric(detail["net_return_pct"], errors="coerce").gt(0).mean()*100, 2),
        "Hariç Tutulan Eski/İşlemsiz": len(all_detail)-len(detail),
        "Brier": round(brier, 4) if brier is not None else None, "Örnek": len(detail)}])
    return summary, all_detail


def model_sagligi(path: Path | None = None, min_samples: int = 30, strategy_id: str = "general_scan") -> dict[str, Any]:
    summary, detail = performans_ozeti(path, strategy_id=strategy_id)
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


def kalibrasyon_gecmisi(path: Path | None = None) -> pd.DataFrame:
    """Yeni defterden strateji adı ve maliyeti korunmuş kapanmış kâğıt işlemler."""
    _, detail = performans_ozeti(path)
    if not detail.empty:
        detail = detail.loc[detail["Ölçüme Dahil"]].copy()
    return detail.rename(columns={"strategy_id": "Strateji", "status": "Durum",
        "calibrated_probability": "Kalibre Edilmiş Olasılık",
        "net_return_pct": "Net Getiri %"})
