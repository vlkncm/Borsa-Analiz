from __future__ import annotations

import math
from typing import Any, Dict

import numpy as np
import pandas as pd
from teknik_gostergeler import (bollinger_bands, cci as canonical_cci, cmf, ema, ichimoku as canonical_ichimoku,
    mfi as canonical_mfi, obv as canonical_obv, roc, rsi as canonical_rsi, sharpe as canonical_sharpe,
    sma, sortino as canonical_sortino, stochastic_rsi, supertrend as canonical_supertrend)


VADELER = {
    "kisa": (10, 0.04),
    "orta": (60, 0.10),
    "uzun": (180, 0.18),
}


def _son(series: pd.Series, default: float = 0.0) -> float:
    try:
        value = float(series.iloc[-1])
        return default if not math.isfinite(value) else value
    except Exception:
        return default


def _wilson_alt(kazanan: int, toplam: int, z: float = 1.2816) -> float:
    """Yaklaşık %80 güven düzeyinde Wilson alt sınırı."""
    if toplam <= 0:
        return 0.0
    p = kazanan / toplam
    payda = 1 + z * z / toplam
    merkez = p + z * z / (2 * toplam)
    fark = z * math.sqrt((p * (1 - p) + z * z / (4 * toplam)) / toplam)
    return max(0.0, (merkez - fark) / payda)


def _ileri_getiri(close: pd.Series, gun: int) -> pd.Series:
    return close.shift(-gun) / close - 1


def _broker_gostergeleri(work: pd.DataFrame) -> Dict[str, Any]:
    close, high, low = work["Close"], work["High"], work["Low"]
    cci = canonical_cci(work, 20)
    st = canonical_supertrend(work, 10, 3.0)
    supertrend, direction = st["SUPERTREND"], st["SUPERTREND_DIRECTION"]
    ichi = canonical_ichimoku(work)
    tenkan, kijun, span_a, span_b = ichi["TENKAN"], ichi["KIJUN"], ichi["SPAN_A"], ichi["SPAN_B"]
    cloud_top = pd.concat([span_a, span_b], axis=1).max(axis=1)
    cloud_bottom = pd.concat([span_a, span_b], axis=1).min(axis=1)
    ichimoku = "BULUT ÜSTÜ" if close.iloc[-1] > cloud_top.iloc[-1] else (
        "BULUT ALTI" if close.iloc[-1] < cloud_bottom.iloc[-1] else "BULUT İÇİ"
    )
    return {
        "cci_20": round(_son(cci), 2),
        "supertrend": round(_son(supertrend), 2),
        "supertrend_yonu": "POZİTİF" if direction.iloc[-1] > 0 else "NEGATİF",
        "ichimoku_durumu": ichimoku,
        "ichimoku_tenkan": round(_son(tenkan), 2),
        "ichimoku_kijun": round(_son(kijun), 2),
    }


def _bootstrap_senaryolari(close: pd.Series, paths: int = 5000) -> Dict[str, Any]:
    """Normal dağılım varsaymadan tarihsel günlük getirileri yeniden örnekler."""
    returns = close.pct_change().dropna().tail(504).to_numpy(dtype=float)
    returns = returns[np.isfinite(returns)]
    if len(returns) < 126:
        return {"monte_carlo_notu": "Monte Carlo için en az 126 getiri gerekli."}
    rng = np.random.default_rng(20260721)
    result: Dict[str, Any] = {}
    for ad, gun in (("1h", 5), ("1a", 20), ("3a", 60)):
        draws = rng.choice(returns, size=(paths, gun), replace=True)
        terminal = np.prod(1 + draws, axis=1) - 1
        result[f"mc_{ad}_yukselis"] = round(float(np.mean(terminal > 0) * 100), 1)
        result[f"mc_{ad}_medyan_getiri"] = round(float(np.median(terminal) * 100), 2)
        result[f"mc_{ad}_kotumser_getiri"] = round(float(np.quantile(terminal, 0.05) * 100), 2)
        result[f"mc_{ad}_iyimser_getiri"] = round(float(np.quantile(terminal, 0.95) * 100), 2)
    one_month = rng.choice(returns, size=(paths, 20), replace=True)
    terminal = np.prod(1 + one_month, axis=1) - 1
    var95 = float(np.quantile(terminal, 0.05))
    result["mc_var95_1a"] = round(max(0.0, -var95) * 100, 2)
    result["mc_cvar95_1a"] = round(max(0.0, -float(terminal[terminal <= var95].mean())) * 100, 2)
    result["monte_carlo_notu"] = "5.000 tarihsel bootstrap senaryosu; tahmin veya garanti değil, risk dağılımıdır."
    return result


def profesyonel_analiz(df: pd.DataFrame, benchmark_df: pd.DataFrame | None = None) -> Dict[str, Any]:
    """Teknik, hacim ve istatistik katmanını ileri-bakışsız hesaplar.

    Olasılıklar, bugünkü duruma benzeyen geçmiş günlerin daha sonraki getirilerinden
    gelir. Küçük örnekte ham başarı oranı yerine Wilson alt sınırı kullanılır.
    """
    if df is None or len(df) < 220:
        return {"profesyonel_kanit_puani": 0, "profesyonel_not": "En az 220 günlük veri gerekli."}

    work = df.copy()
    close = pd.to_numeric(work["Close"], errors="coerce")
    high = pd.to_numeric(work["High"], errors="coerce")
    low = pd.to_numeric(work["Low"], errors="coerce")
    volume = pd.to_numeric(work.get("Volume", 0), errors="coerce").fillna(0)
    ret = close.pct_change()

    ema20, ema50, sma200 = ema(close, 20), ema(close, 50), sma(close, 200)
    bands = bollinger_bands(close)
    std20 = (bands["BB_UPPER"]-bands["BB_MIDDLE"])/2
    bb_z = (close-bands["BB_MIDDLE"])/std20.replace(0, np.nan)
    roc20 = roc(close, 20)
    momentum60 = roc(close, 60)

    delta = close.diff()
    rsi = canonical_rsi(close, 14)
    stoch_rsi = stochastic_rsi(close, 14)

    obv = canonical_obv(work)
    obv_trend = obv.diff(20)
    cmf20 = cmf(work, 20)
    mfi = canonical_mfi(work, 14)

    sharpe_value = canonical_sharpe(ret.tail(126))
    sortino_value = canonical_sortino(ret.tail(126))

    current = {
        "trend": bool(close.iloc[-1] > ema20.iloc[-1] > ema50.iloc[-1]),
        "long_trend": bool(close.iloc[-1] > sma200.iloc[-1]),
        "momentum": float(momentum60.iloc[-1]),
        "bb_z": float(bb_z.iloc[-1]),
        "cmf": float(cmf20.iloc[-1]),
    }
    regime = (
        (close > ema20) == current["trend"]
    ) & ((close > sma200) == current["long_trend"])
    regime &= (momentum60.sub(current["momentum"]).abs() <= 12)
    regime &= (bb_z.sub(current["bb_z"]).abs() <= 0.9)
    regime &= (cmf20.sub(current["cmf"]).abs() <= 0.18)

    result: Dict[str, Any] = {
        "bollinger_z": round(_son(bb_z), 3),
        "stoch_rsi": round(_son(stoch_rsi, 50), 2),
        "roc_20": round(_son(roc20), 2),
        "obv_trend_20": round(_son(obv_trend), 0),
        "cmf_20": round(_son(cmf20), 3),
        "mfi_14": round(_son(mfi, 50), 2),
        "sharpe_126": round(sharpe_value, 2),
        "sortino_126": round(sortino_value, 2),
    }
    result.update(_broker_gostergeleri(work))
    result.update(_bootstrap_senaryolari(close))

    if benchmark_df is not None and not benchmark_df.empty and "Close" in benchmark_df:
        bench = pd.to_numeric(benchmark_df["Close"], errors="coerce")
        aligned = pd.concat([close.rename("stock"), bench.rename("bench")], axis=1).dropna()
        for label, days in (("1a", 20), ("3a", 60), ("1y", 252)):
            if len(aligned) > days:
                stock_ret = aligned["stock"].iloc[-1] / aligned["stock"].iloc[-days - 1] - 1
                bench_ret = aligned["bench"].iloc[-1] / aligned["bench"].iloc[-days - 1] - 1
                result[f"goreceli_guc_{label}"] = round((stock_ret - bench_ret) * 100, 2)
        common_ret = aligned.pct_change().dropna().tail(252)
        if len(common_ret) >= 60:
            variance = common_ret["bench"].var()
            result["bist_beta_252"] = round(float(common_ret.cov().loc["stock", "bench"] / variance), 2) if variance > 0 else 0
    else:
        result["goreceli_guc_notu"] = "BIST 100 verisi alınamadı; göreceli güç puanlamaya katılmadı."

    alt_sinirlar = []
    for ad, (gun, esik) in VADELER.items():
        ileri = _ileri_getiri(close, gun)
        uygun = regime & ileri.notna()
        ornek = int(uygun.sum())
        kazanan = int((ileri[uygun] >= esik).sum())
        ham = kazanan / ornek if ornek else 0.0
        alt = _wilson_alt(kazanan, ornek)
        medyan = float(ileri[uygun].median()) if ornek else 0.0
        result[f"{ad}_tarihsel_olasilik"] = round(ham * 100, 1)
        result[f"{ad}_guvenli_olasilik"] = round(alt * 100, 1)
        result[f"{ad}_ornek"] = ornek
        result[f"{ad}_medyan_getiri"] = round(medyan * 100, 2)
        if ornek >= 20:
            alt_sinirlar.append(alt)

    hacim_puani = 100 * max(0.0, min(1.0, (_son(cmf20) + 0.25) / 0.5))
    trend_puani = 100 if current["trend"] and current["long_trend"] else (60 if current["long_trend"] else 25)
    risk_puani = max(0.0, min(100.0, 50 + sharpe_value * 15 + sortino_value * 8))
    kanit = (sum(alt_sinirlar) / len(alt_sinirlar) * 100) if alt_sinirlar else 0.0
    result["profesyonel_kanit_puani"] = round(kanit * 0.55 + trend_puani * 0.20 + hacim_puani * 0.10 + risk_puani * 0.15, 1)
    result["profesyonel_not"] = (
        "Benzer geçmiş rejimlerin ileri dönem sonuçları; küçük örnek Wilson alt sınırıyla cezalandırıldı."
        if alt_sinirlar else "Benzer rejimde en az 20 bağımsız örnek yok; güven düşük."
    )
    return result
