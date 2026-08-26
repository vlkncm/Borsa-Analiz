"""T gününde yalnızca T'ye kadar bilgiyle T+1 hedeflerini üretir."""
from __future__ import annotations

import pandas as pd

from fiyat_limitleri import pay_fiyat_limitleri


def t1_etiketleri(ohlcv: pd.DataFrame) -> pd.DataFrame:
    required = {"Open", "High", "Low", "Close"}
    if not required.issubset(ohlcv.columns):
        raise ValueError(f"Eksik OHLC sütunları: {sorted(required-set(ohlcv.columns))}")
    out = pd.DataFrame(index=ohlcv.index)
    out["feature_cutoff"] = ohlcv.index
    out["previous_close"] = pd.to_numeric(ohlcv["Close"], errors="coerce")
    next_high = pd.to_numeric(ohlcv["High"], errors="coerce").shift(-1)
    next_low = pd.to_numeric(ohlcv["Low"], errors="coerce").shift(-1)
    next_close = pd.to_numeric(ohlcv["Close"], errors="coerce").shift(-1)
    out["t1_intraday_max_return"] = next_high / out["previous_close"] - 1
    out["t1_close_return"] = next_close / out["previous_close"] - 1
    out["t1_max_adverse_excursion"] = next_low / out["previous_close"] - 1
    out["t1_intraday_8"] = out["t1_intraday_max_return"].ge(.08).astype("Int64")
    out["t1_close_8"] = out["t1_close_return"].ge(.08).astype("Int64")
    ceilings = out["previous_close"].map(
        lambda x: float(pay_fiyat_limitleri(x).ust_limit) if pd.notna(x) and x > 0 else float("nan")
    )
    out["t1_ceiling_price"] = ceilings
    out["t1_hit_ceiling"] = next_high.ge(ceilings.sub(1e-9)).astype("Int64")
    # Son satırın T+1'i henüz yoktur; yanlışlıkla negatif örneğe dönüşmesin.
    out.loc[next_high.isna(), ["t1_intraday_8", "t1_close_8", "t1_hit_ceiling"]] = pd.NA
    return out


def ozellikleri_tarih_kesiminde_kisitla(frame: pd.DataFrame, cutoff) -> pd.DataFrame:
    """Backtest yardımcı koruması: kesim anından sonraki satırları reddeder."""
    cutoff = pd.Timestamp(cutoff)
    idx = pd.to_datetime(frame.index)
    if (idx > cutoff).any():
        raise ValueError("Gelecekten bilgi sızıntısı: özellik satırı veri kesiminden sonra")
    return frame.copy()

