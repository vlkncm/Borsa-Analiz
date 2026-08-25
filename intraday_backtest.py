"""Tekrar üretilebilir intraday işlem değerlendirme ve performans özeti."""
from __future__ import annotations

import math
import pandas as pd
import numpy as np
from trade_kanitlari import Outcome, label_trade_outcome, mfe_mae, three_way_oos_evidence


def islem_sonucu(bars: pd.DataFrame, entry: float, target: float, stop: float,
                 commission_rate: float = 0.001, slippage_rate: float = 0.0005) -> dict:
    """Hedef ve stop aynı barda ise kötümser şekilde stopu önce kabul eder."""
    exit_price, reason, bars_seen = float(bars.iloc[-1]["Close"]), "GÜN SONU", len(bars)
    ambiguous = False
    for i, row in enumerate(bars.itertuples()):
        hit_target, hit_stop = float(row.High) >= target, float(row.Low) <= stop
        if hit_target and hit_stop:
            exit_price, reason, ambiguous, bars_seen = stop, "STOP (AYNI BAR BELİRSİZ)", True, i + 1
            break
        if hit_stop:
            exit_price, reason, bars_seen = stop, "STOP", i + 1
            break
        if hit_target:
            exit_price, reason, bars_seen = target, "HEDEF", i + 1
            break
    gross = exit_price / entry - 1
    cost = commission_rate * 2 + slippage_rate * 2
    outcome, _ = label_trade_outcome(bars, target, stop)
    excursions = mfe_mae(bars.iloc[:bars_seen], entry)
    return {"sonuc": reason, "olay": outcome.value, "hedef_once": outcome == Outcome.HEDEF_ONCE,
            "cikis": exit_price, "brut_getiri": gross, "net_getiri": gross-cost,
            "maliyet": cost, "belirsiz": ambiguous, "bar_sayisi": bars_seen, **excursions}


def ampirik_kanit(outcomes, min_samples: int = 30, prior_strength: int = 20) -> dict:
    """Üç sonuçlu, Wilson aralıklı zaman sıralı OOS kanıtı; eski kayıtlarla uyumlu."""
    rows = pd.DataFrame(outcomes).copy()
    if "olay" not in rows and "hedef_once" in rows:
        result_text = rows["sonuc"].astype(str) if "sonuc" in rows else pd.Series("", index=rows.index)
        rows["olay"] = np.where(rows["hedef_once"].astype(bool), Outcome.HEDEF_ONCE.value,
                                 np.where(result_text.str.startswith("STOP"), Outcome.STOP_ONCE.value, Outcome.SURE_DOLDU.value))
    evidence = three_way_oos_evidence(rows, min_samples)
    returns = pd.to_numeric(rows["net_getiri"], errors="coerce").dropna() if "net_getiri" in rows else pd.Series(dtype=float)
    evidence.update({"olasilik": evidence["hedef_olasiligi_pct"],
                     "guven_araligi": evidence["hedef_guven_araligi_pct"],
                     "medyan_hareket": evidence["medyan_net_getiri_pct"],
                     "p10": float(returns.quantile(.10)*100) if evidence["yeterli"] else None,
                     "p90": float(returns.quantile(.90)*100) if evidence["yeterli"] else None})
    return evidence


def performans_ozeti(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {"toplam_islem": 0, "uyari": "Geçmiş performans, gelecek sonucu garanti etmez."}
    net = pd.to_numeric(trades["net_getiri"], errors="coerce").dropna()
    equity = (1 + net).cumprod()
    drawdown = equity/equity.cummax()-1
    gains, losses = net[net > 0].sum(), abs(net[net < 0].sum())
    probs = pd.to_numeric(trades.get("tahmin_olasiligi"), errors="coerce")
    actual = pd.to_numeric(trades.get("hedef_once"), errors="coerce")
    valid = probs.notna() & actual.notna()
    brier = float(((probs[valid]/100-actual[valid])**2).mean()) if valid.any() else None
    return {
        "toplam_islem": len(net), "hedef": int(trades["sonuc"].astype(str).eq("HEDEF").sum()),
        "stop": int(trades["sonuc"].astype(str).str.startswith("STOP").sum()),
        "gun_sonu": int(trades["sonuc"].astype(str).eq("GÜN SONU").sum()),
        "belirsiz": int(trades.get("belirsiz", False).sum()), "kazanma_orani": float((net > 0).mean()),
        "ortalama_net_getiri": float(net.mean()), "medyan_net_getiri": float(net.median()),
        "beklenen_deger": float(net.mean()), "profit_factor": None if losses == 0 else float(gains/losses),
        "maksimum_dusus": float(drawdown.min()), "brier_skoru": brier,
        "uyari": "Geçmiş performans, gelecek sonucu garanti etmez.",
    }


def walk_forward_tahminleri(outcomes: pd.DataFrame, min_train: int = 30) -> pd.DataFrame:
    """Her satırı yalnız kendisinden önceki sonuçlarla tahmin ederek sızıntıyı önler."""
    ordered = outcomes.sort_values("sinyal_zamani").reset_index(drop=True).copy()
    estimates = []
    for i in range(len(ordered)):
        evidence = ampirik_kanit(ordered.iloc[:i], min_samples=min_train)
        estimates.append(evidence["olasilik"])
    ordered["tahmin_olasiligi"] = estimates
    return ordered
