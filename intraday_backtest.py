"""Tekrar üretilebilir intraday işlem değerlendirme ve performans özeti."""
from __future__ import annotations

import math
import pandas as pd
import numpy as np


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
    return {"sonuc": reason, "cikis": exit_price, "brut_getiri": gross,
            "net_getiri": gross-cost, "maliyet": cost, "belirsiz": ambiguous, "bar_sayisi": bars_seen}


def ampirik_kanit(outcomes, min_samples: int = 30, prior_strength: int = 20) -> dict:
    """Zaman sıralı geçmiş sonuçlardan küçültülmüş olasılık ve sağlam aralık."""
    rows = pd.DataFrame(outcomes).copy()
    if rows.empty or "net_getiri" not in rows or "hedef_once" not in rows:
        return {"n": 0, "olasilik": None, "medyan_hareket": None, "p10": None, "p90": None,
                "kalibrasyon": "Yetersiz örnek"}
    rows = rows.dropna(subset=["net_getiri", "hedef_once"])
    n = len(rows)
    if n < min_samples:
        return {"n": n, "olasilik": None, "medyan_hareket": None, "p10": None, "p90": None,
                "kalibrasyon": "Yetersiz örnek"}
    wins = float(rows["hedef_once"].astype(float).sum())
    # Beta(1,1) taban oranına küçültme; keyfî olasılık aralığına sıkıştırma yok.
    base = 0.5
    probability = (wins + prior_strength * base) / (n + prior_strength)
    returns = rows["net_getiri"].astype(float).to_numpy()
    return {"n": n, "olasilik": probability*100, "medyan_hareket": float(np.median(returns))*100,
            "p10": float(np.quantile(returns, .10))*100, "p90": float(np.quantile(returns, .90))*100,
            "kalibrasyon": "Beta taban oranına küçültülmüş ampirik OOS"}


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
