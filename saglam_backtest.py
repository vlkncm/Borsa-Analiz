"""Zaman sıralı model doğrulama ve risk ölçümleri.

Araçlar veri sağlamaz; point-in-time evren/kurumsal aksiyon/KAP zaman damgası
alanlarını zorunlu doğrulama notu olarak raporlar.
"""
from __future__ import annotations

import math
from statistics import NormalDist
from typing import Iterable
import numpy as np
import pandas as pd


def purged_time_series_splits(n: int, folds: int = 5, purge: int = 5, embargo: int = 5):
    if n < folds * 3 or folds < 2:
        return []
    indices = np.arange(n)
    test_size = n // (folds + 1)
    splits = []
    for fold in range(folds):
        test_start = test_size * (fold + 1)
        test_end = n if fold == folds-1 else min(n, test_start+test_size)
        train_end = max(0, test_start-purge)
        train = indices[:train_end]
        test = indices[test_start:test_end]
        if embargo and test_end < n:
            # Gelecek veri zaten eğitimde kullanılmaz; embargo sınırı metadata olarak korunur.
            embargo_end = min(n, test_end+embargo)
        else:
            embargo_end = test_end
        if len(train) and len(test):
            splits.append({"train": train, "test": test, "purge": purge,
                           "embargo_start": test_end, "embargo_end": embargo_end})
    return splits


def walk_forward_splits(n: int, train_size: int, test_size: int, step: int | None = None, embargo: int = 0):
    step = step or test_size
    splits = []
    start = train_size
    while start+test_size <= n:
        splits.append((np.arange(0, start), np.arange(start+embargo, min(n, start+embargo+test_size))))
        start += step
    return [(a, b) for a, b in splits if len(a) and len(b)]


def performans_metrikleri(trades: pd.DataFrame, return_col: str = "Getiri %", outcome_col: str = "Sonuç") -> dict:
    if trades is None or trades.empty or return_col not in trades:
        return {"samples": 0, "precision": None, "false_positive_rate": None, "net_ev": None,
                "profit_factor": None, "max_drawdown": None, "target_before_stop": None}
    returns = pd.to_numeric(trades[return_col], errors="coerce").dropna()/100
    if returns.empty:
        return {"samples": 0}
    wins, losses = returns[returns > 0], returns[returns <= 0]
    equity = (1+returns).cumprod()
    drawdown = equity/equity.cummax()-1
    outcomes = trades.get(outcome_col, pd.Series("", index=trades.index)).astype(str)
    target = outcomes.str.contains("HEDEF", case=False, na=False)
    stop = outcomes.str.contains("STOP", case=False, na=False)
    resolved = target | stop
    precision = float(target[resolved].mean()) if resolved.any() else float((returns > 0).mean())
    pf = wins.sum()/abs(losses.sum()) if abs(losses.sum()) > 0 else math.inf
    return {"samples": len(returns), "precision": round(precision, 4),
        "false_positive_rate": round(1-precision, 4), "net_ev": round(float(returns.mean()*100), 4),
        "profit_factor": round(float(pf), 4) if math.isfinite(pf) else math.inf,
        "max_drawdown": round(float(drawdown.min()*100), 4),
        "target_before_stop": round(float(target[resolved].mean()), 4) if resolved.any() else None,
        "average_win": round(float(wins.mean()*100), 4) if len(wins) else 0,
        "average_loss": round(float(losses.mean()*100), 4) if len(losses) else 0}


def block_bootstrap(returns: Iterable[float], simulations: int = 1000, block_size: int = 5, seed: int = 42) -> dict:
    values = np.asarray(list(returns), dtype=float)
    values = values[np.isfinite(values)]
    if len(values) < max(10, block_size):
        return {"samples": len(values), "p05": None, "median": None, "p95": None}
    rng = np.random.default_rng(seed)
    totals = []
    for _ in range(simulations):
        sample = []
        while len(sample) < len(values):
            start = int(rng.integers(0, max(1, len(values)-block_size+1)))
            sample.extend(values[start:start+block_size])
        totals.append(np.prod(1+np.asarray(sample[:len(values)])/100)-1)
    return {"samples": len(values), "p05": round(float(np.percentile(totals, 5)*100), 3),
        "median": round(float(np.median(totals)*100), 3), "p95": round(float(np.percentile(totals, 95)*100), 3)}


def deflated_sharpe_ratio(returns: Iterable[float], trials: int = 1) -> float | None:
    values = np.asarray(list(returns), dtype=float)
    values = values[np.isfinite(values)]
    if len(values) < 20 or values.std(ddof=1) == 0:
        return None
    sr = values.mean()/values.std(ddof=1)*math.sqrt(252)
    expected_max = NormalDist().inv_cdf(1-1/max(2, trials)) if trials > 1 else 0
    standard_error = math.sqrt((1+0.5*sr*sr)/max(1, len(values)-1))
    return round(NormalDist().cdf((sr-expected_max)/standard_error), 4)


def probability_of_backtest_overfitting(train_scores: Iterable[float], test_scores: Iterable[float]) -> float | None:
    train, test = np.asarray(list(train_scores), dtype=float), np.asarray(list(test_scores), dtype=float)
    valid = np.isfinite(train) & np.isfinite(test)
    if valid.sum() < 4:
        return None
    train, test = train[valid], test[valid]
    winner_threshold = np.median(train)
    return round(float((test[train >= winner_threshold] < np.median(test)).mean()), 4)


def veri_butunlugu_kontrolu(frame: pd.DataFrame) -> dict:
    required = {"symbol", "date", "was_listed", "adjusted_for_splits", "dividend_adjusted"}
    missing = sorted(required-set(frame.columns if frame is not None else []))
    kap_ok = frame is not None and {"kap_published_at", "decision_time"}.issubset(frame.columns)
    return {"point_in_time_universe": not missing and bool(frame["was_listed"].fillna(False).all()),
        "corporate_actions_adjusted": not missing and bool(frame["adjusted_for_splits"].fillna(False).all()) and bool(frame["dividend_adjusted"].fillna(False).all()),
        "kap_publication_time_available": bool(kap_ok), "missing_fields": missing,
        "safe_for_model_selection": not missing and bool(kap_ok)}
