"""Kullanicinin gercek alis fiyati/tarihiyle yerel portfoy kaydi ve sade karar."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable
from datetime import date


@dataclass(frozen=True)
class PortfolioPosition:
    symbol: str
    quantity: int
    buy_price: float
    buy_date: str
    target: float | None = None
    stop: float | None = None

    @property
    def valid(self) -> bool:
        return bool(self.symbol and self.quantity>0 and self.buy_price>0 and self.buy_date)


def load_positions(path: str|Path) -> list[PortfolioPosition]:
    try:
        payload=json.loads(Path(path).read_text(encoding="utf-8"))
        rows=[]
        for item in payload.get("positions",[]):
            position=PortfolioPosition(**item)
            if position.valid: rows.append(position)
        return rows
    except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError):
        return []


def save_positions(path: str|Path, positions: Iterable[PortfolioPosition]) -> None:
    target=Path(path); target.parent.mkdir(parents=True,exist_ok=True)
    payload={"schema_version":1,"positions":[asdict(item) for item in positions if item.valid]}
    handle,name=tempfile.mkstemp(prefix=target.stem+"_",suffix=".tmp",dir=target.parent); os.close(handle)
    temp=Path(name)
    try:
        temp.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8"); temp.replace(target)
    finally:
        if temp.exists(): temp.unlink()


def upsert_position(path: str|Path, position: PortfolioPosition) -> None:
    if not position.valid: raise ValueError("Hisse, adet, alis fiyati ve tarihi zorunludur")
    date.fromisoformat(position.buy_date)
    rows={item.symbol.replace(".IS","").upper():item for item in load_positions(path)}
    key=position.symbol.replace(".IS","").upper(); rows[key]=PortfolioPosition(key,position.quantity,position.buy_price,
        position.buy_date,position.target,position.stop)
    save_positions(path,rows.values())


def remove_position(path: str|Path, symbol: str) -> None:
    key=str(symbol).replace(".IS","").upper()
    save_positions(path,[item for item in load_positions(path) if item.symbol.replace(".IS","").upper()!=key])


def portfolio_decision(position: PortfolioPosition, current_price: float|None, *,
                       momentum_weak: bool=False, trend_broken: bool=False) -> dict[str,Any]:
    """Portfoydeki hisse icin BEKLE/KAR AL/SAT; portfoy disina SAT uretmez."""
    if not position.valid or current_price is None or current_price<=0:
        return {"decision":"VERİ YETERSİZ","profit_pct":None,"reason":"Güncel fiyat veya geçerli portföy kaydı yok."}
    price=float(current_price); profit=(price/position.buy_price-1)*100
    if position.stop is not None and price<=position.stop:
        decision="SAT"; reason="Kayıtlı stop seviyesi kırıldı."
    elif trend_broken:
        decision="SAT"; reason="Ana yükseliş eğilimi bozuldu."
    elif position.target is not None and price>=position.target:
        if not momentum_weak:
            decision="BEKLE"; reason="Hedef geçildi; güç sürerken stop yükseltilerek izlenebilir."
        else:
            decision="KÂR AL"; reason="Hedef bölgesi görüldü ve fiyat gücü zayıflıyor."
    elif position.target is not None and price>=position.target*.98:
        decision="KÂR AL"; reason="Fiyat hedef bölgesine yaklaştı."
    elif momentum_weak and profit>0:
        decision="KÂR AL"; reason="Kârlı pozisyonda fiyat gücü zayıflıyor."
    else:
        decision="BEKLE"; reason="Stop kırılmadı ve ana senaryo korunuyor."
    return {"decision":decision,"profit_pct":round(profit,2),"reason":reason}
