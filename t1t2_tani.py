"""T+1/T+2 veri ve sonuc izolasyonunu sembol bazinda tanilama araci."""
from __future__ import annotations

import argparse
import json

from bist_evreni import kap_menkul_turleri
from t1t2_tahmin_sistemi import load_artifacts, predict_symbol
from veri_saglayici import get_daily_ohlcv


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("symbols", nargs="+", help="Ornek: ASELS.IS THYAO.IS")
    parser.add_argument("--horizon", choices=("T+1", "T+2"), default="T+1")
    parser.add_argument("--model", default="models/t1t2_reference.json")
    args = parser.parse_args()
    artifacts, _metrics = load_artifacts(args.model)
    security_types = kap_menkul_turleri()
    for symbol in args.symbols:
        frame, meta = get_daily_ohlcv(symbol, "2y")
        if frame.empty:
            print(json.dumps({"symbol": symbol, "error": "MISSING_PRICE_DATA"}, ensure_ascii=False))
            continue
        prediction = predict_symbol(symbol, frame, frame.index[-1], args.horizon, artifacts,
                                    security_types.get(symbol, "BELIRSIZ"))
        record = prediction.dict()
        output = {
            "symbol": symbol,
            "as_of": prediction.as_of_timestamp,
            "ohlcv_rows": len(frame),
            "last_price": prediction.current_price,
            "feature_count": prediction.feature_count,
            "missing_features": prediction.missing_features,
            "feature_hash": prediction.feature_hash,
            "model": prediction.model_version,
            "model_path": args.model,
            "raw_score": prediction.raw_score,
            "probabilities": record["probabilities"],
            "cache_key": prediction.cache_key,
            "entry": prediction.entry_high,
            "target": prediction.target_7,
            "stop": prediction.stop,
            "net_ev_pct": prediction.net_ev_pct,
            "status": prediction.status,
            "reasons": prediction.reasons,
            "source": meta.source,
        }
        print(json.dumps(output, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
