from __future__ import annotations

import math
from typing import Any, Dict

import numpy as np
import pandas as pd


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
    typical = (high + low + close) / 3
    cci = (typical - typical.rolling(20).mean()) / (0.015 * typical.rolling(20).apply(
        lambda x: np.mean(np.abs(x - np.mean(x))), raw=True
    ).replace(0, np.nan))

    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr10 = tr.ewm(alpha=0.1, adjust=False).mean()
    hl2 = (high + low) / 2
    upper = hl2 + 3 * atr10
    lower = hl2 - 3 * atr10
    supertrend = pd.Series(index=work.index, dtype=float)
    direction = pd.Series(index=work.index, dtype=float)
    supertrend.iloc[0], direction.iloc[0] = upper.iloc[0], -1
    for i in range(1, len(work)):
        if close.iloc[i] > upper.iloc[i - 1]:
            direction.iloc[i] = 1
        elif close.iloc[i] < lower.iloc[i - 1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i - 1]
            if direction.iloc[i] > 0:
                lower.iloc[i] = max(lower.iloc[i], lower.iloc[i - 1])
            else:
                upper.iloc[i] = min(upper.iloc[i], upper.iloc[i - 1])
        supertrend.iloc[i] = lower.iloc[i] if direction.iloc[i] > 0 else upper.iloc[i]

    tenkan = (high.rolling(9).max() + low.rolling(9).min()) / 2
    kijun = (high.rolling(26).max() + low.rolling(26).min()) / 2
    span_a = ((tenkan + kijun) / 2).shift(26)
    span_b = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)
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

    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    sma200 = close.rolling(200).mean()
    std20 = close.rolling(20).std(ddof=0)
    bb_z = (close - close.rolling(20).mean()) / std20.replace(0, np.nan)
    roc20 = close.pct_change(20) * 100
    momentum60 = close.pct_change(60) * 100

    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    stoch_rsi = (rsi - rsi.rolling(14).min()) / (rsi.rolling(14).max() - rsi.rolling(14).min()).replace(0, np.nan) * 100

    signed_volume = np.sign(delta.fillna(0)) * volume
    obv = signed_volume.cumsum()
    obv_trend = obv.diff(20)
    money_flow_multiplier = ((close - low) - (high - close)) / (high - low).replace(0, np.nan)
    cmf20 = (money_flow_multiplier * volume).rolling(20).sum() / volume.rolling(20).sum().replace(0, np.nan)
    typical = (high + low + close) / 3
    raw_flow = typical * volume
    positive_flow = raw_flow.where(typical.diff() > 0, 0).rolling(14).sum()
    negative_flow = raw_flow.where(typical.diff() < 0, 0).rolling(14).sum()
    mfi = 100 - 100 / (1 + positive_flow / negative_flow.replace(0, np.nan))

    ann_return = ret.rolling(126).mean() * 252
    ann_vol = ret.rolling(126).std(ddof=0) * math.sqrt(252)
    downside = ret.where(ret < 0, 0).rolling(126).std(ddof=0) * math.sqrt(252)
    sharpe = ann_return / ann_vol.replace(0, np.nan)
    sortino = ann_return / downside.replace(0, np.nan)

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
        "sharpe_126": round(_son(sharpe), 2),
        "sortino_126": round(_son(sortino), 2),
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
    risk_puani = max(0.0, min(100.0, 50 + _son(sharpe) * 15 + _son(sortino) * 8))
    kanit = (sum(alt_sinirlar) / len(alt_sinirlar) * 100) if alt_sinirlar else 0.0
    result["profesyonel_kanit_puani"] = round(kanit * 0.55 + trend_puani * 0.20 + hacim_puani * 0.10 + risk_puani * 0.15, 1)
    result["profesyonel_not"] = (
        "Benzer geçmiş rejimlerin ileri dönem sonuçları; küçük örnek Wilson alt sınırıyla cezalandırıldı."
        if alt_sinirlar else "Benzer rejimde en az 20 bağımsız örnek yok; güven düşük."
    )
    return result
