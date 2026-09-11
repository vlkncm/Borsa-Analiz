"""v10.3.3 KAP menkul türü okuyucusu; tarama evrenini değiştirmez."""
import os, json, re, tempfile
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
from bist30 import normalize_bist_sembolu
from bist_evreni import KAP_URL
MIN_GECERLI_EVREN = 400

def _atomik_json_yaz(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=path.stem + "_", suffix=".tmp", dir=path.parent)
    os.close(handle)
    temp = Path(name)
    try:
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()

def kap_menkul_turleri(cache_dir: str | Path | None = None, refresh: bool = False) -> dict[str, str]:
    """KAP BIST şirket tablosundan doğrulanmış şirket payı/GYO ayrımı üretir.

    KAP şirket tablosunda bulunmayan bülten kodları normal pay varsayılmaz.
    """
    folder = Path(cache_dir) if cache_dir else Path(os.getenv("LOCALAPPDATA") or (Path.home()/"AppData"/"Local"))/"BorsaAnalizProMAX"
    cache=folder/"menkul_turleri.json"; now=datetime.now()
    if cache.exists() and not refresh:
        try:
            payload=json.loads(cache.read_text(encoding="utf-8")); created=datetime.fromisoformat(payload["created_at"])
            if now-created<timedelta(hours=24): return dict(payload.get("types",{}))
        except (OSError,ValueError,KeyError,TypeError): pass
    try:
        tables=pd.read_html(KAP_URL); table=tables[0]
        code_col=next(column for column in table.columns if str(column).strip().lower()=="kod")
        title_col=next(column for column in table.columns if "nvan" in str(column).lower())
        types={}
        for code,title in zip(table[code_col],table[title_col]):
            code=str(code).strip().upper()
            if not re.fullmatch(r"[A-Z0-9]{2,12}",code): continue
            title=str(title).upper()
            if code.endswith("GYO") or ("GAYR" in title and "YATIRIM ORTAK" in title): kind="GYO"
            elif "YATIRIM ORTAK" in title: kind="YATIRIM_ORTAKLIGI"
            else: kind="NORMAL_PAY"
            types[normalize_bist_sembolu(code)]=kind
        if len(types)<MIN_GECERLI_EVREN: raise ValueError("KAP menkul türü tablosu yetersiz")
        _atomik_json_yaz(cache,{"created_at":now.isoformat(timespec="seconds"),"source":KAP_URL,"types":types})
        return types
    except Exception:
        try: return dict(json.loads(cache.read_text(encoding="utf-8")).get("types",{}))
        except Exception: return {}
