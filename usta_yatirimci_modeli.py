"""Kamuya açık yatırım ilkelerinden türetilmiş şeffaf çoklu-model sıralama.
Bu, yatırımcıların özel/kapalı işlem sistemleri değildir.
"""
from __future__ import annotations
from typing import Any, Iterable
import pandas as pd


def _n(x: Any) -> float:
    try: return float(x) if pd.notna(x) else 0.0
    except (TypeError, ValueError): return 0.0


def _clip(x: float) -> float: return round(max(0, min(100, x)), 1)


def usta_model_portfoyu(results: Iterable[dict[str, Any]], adet: int = 10) -> pd.DataFrame:
    rows = []
    for item in results:
        fk, pb, roe = _n(item.get("fk")), _n(item.get("pddd")), _n(item.get("roe"))
        margin, debt, growth = _n(item.get("kar_marji")), _n(item.get("borc_ozsermaye")), _n(item.get("kar_buyume"))
        liquidity, momentum = _n(item.get("ortalama_gunluk_islem_tutari")), _n(item.get("v4_momentum_puani"))
        if fk <= 0 or pb <= 0 or roe <= 0 or liquidity <= 0: continue
        # Buffett: kalıcı kârlılık ve ölçülü borç; Graham: değer/güvenlik marjı.
        buffett = _clip(roe * 220 + max(margin, 0) * 180 + max(0, 1 - debt / 300) * 25)
        graham = _clip((1 / fk) * 350 + (1 / pb) * 35)
        # Lynch: büyüme F/K'yı destekliyorsa GARP puanı; büyüme yoksa sıfır.
        peg = fk / max(growth * 100, 1)
        lynch = _clip((1 / peg) * 55 if growth > 0 else 0)
        # Simons: kamuya açık veriyle yalnızca nicel likidite/momentum vekili.
        simons = _clip(momentum + min(25, liquidity / 50_000_000 * 25))
        # Soros: rejim negatif veya olağandışı/KAP riski varsa korumacı indirim.
        risk_text = f"{item.get('piyasa_rejimi','')} {item.get('kap_etiket','')} {item.get('olaganustu_not','')}".lower()
        soros_risk = 0 if any(x in risk_text for x in ("düşüş", "olumsuz", "risk", "olağanüstü")) else 80
        score = 0.30*buffett + 0.25*graham + 0.20*lynch + 0.15*simons + 0.10*soros_risk
        rows.append({"Hisse": str(item.get("symbol", "")).replace(".IS", ""), "Sektör": item.get("sector", "Bilinmiyor"),
                     "Buffett Kalite": buffett, "Graham Değer": graham, "Lynch GARP": lynch,
                     "Simons Nicel": simons, "Soros Risk Kapısı": soros_risk,
                     "Usta Model Skoru": round(score, 1), "F/K": fk, "ROE": roe, "Kâr Büyüme": growth,
                     "20 Günlük İşlem Tutarı": liquidity})
    df = pd.DataFrame(rows)
    if df.empty: return df
    df = df.nlargest(100, "20 Günlük İşlem Tutarı").sort_values("Usta Model Skoru", ascending=False)
    selected, sector_count = [], {}
    for _, row in df.iterrows():
        sector = str(row["Sektör"])
        if sector_count.get(sector, 0) >= 2: continue
        selected.append(row); sector_count[sector] = sector_count.get(sector, 0) + 1
        if len(selected) == adet: break
    out = pd.DataFrame(selected)
    if not out.empty:
        out["Portföy Ağırlığı %"] = round(100 / len(out), 2)
        out["Metodoloji"] = "Uzun vade için çoklu kalite/değer/büyüme/nicel-risk filtresi; getiri garantisi değildir."
    return out.reset_index(drop=True)
