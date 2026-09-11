"""Tarama sayaclari ve makine-okunabilir sonuc nedenleri."""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class TaramaOzeti:
    aktif_bist_evreni: int = 0
    taranmaya_calisilan: int = 0
    basariyla_veri_alinan: int = 0
    yeni_halka_arz: int = 0
    standart_model: int = 0
    yeni_halka_arz_modeli: int = 0
    veri_yetersiz: int = 0
    veri_alinamayan: int = 0
    filtrelenen: int = 0
    gosterilen_aday: int = 0

    def kaydet(self, row: dict, data_received: bool) -> None:
        self.taranmaya_calisilan += 1
        if data_received:
            self.basariyla_veri_alinan += 1
        else:
            self.veri_alinamayan += 1
        path, code = row.get("Model Yolu"), row.get("Neden Kodu")
        if path == "YENI_HALKA_ARZ":
            self.yeni_halka_arz += 1
            self.yeni_halka_arz_modeli += 1
        elif path == "STANDART":
            self.standart_model += 1
        if code == "INSUFFICIENT_HISTORY":
            self.veri_yetersiz += 1
        if code in {"MISSING_PRICE_DATA", "SYMBOL_MAPPING_FAILED", "STALE_DATA"} and data_received:
            self.veri_alinamayan += 1
            self.basariyla_veri_alinan -= 1
        if code in {"REJECTED_LOW_SCORE", "REJECTED_LIQUIDITY", "REJECTED_HIGH_RISK"}:
            self.filtrelenen += 1
        if code in {"INCLUDED_STANDARD", "INCLUDED_IPO"}:
            self.gosterilen_aday += 1

    def dogrula(self) -> None:
        if self.taranmaya_calisilan != self.basariyla_veri_alinan + self.veri_alinamayan:
            raise AssertionError("Tarama ozeti veri sayaclari tutarsiz")
        if self.yeni_halka_arz_modeli + self.standart_model > self.basariyla_veri_alinan:
            raise AssertionError("Model sayaclari basarili veri sayisini asamaz")

    def dict(self) -> dict:
        self.dogrula()
        return asdict(self)

    def metin(self) -> str:
        d = self.dict()
        return " | ".join([
            f"Aktif BIST: {d['aktif_bist_evreni']}", f"Denenen: {d['taranmaya_calisilan']}",
            f"Veri alinan: {d['basariyla_veri_alinan']}", f"Yeni halka arz: {d['yeni_halka_arz']}",
            f"Standart: {d['standart_model']}", f"IPO modeli: {d['yeni_halka_arz_modeli']}",
            f"Veri yetersiz: {d['veri_yetersiz']}", f"Veri alinamayan: {d['veri_alinamayan']}",
            f"Filtrelenen: {d['filtrelenen']}", f"Gosterilen aday: {d['gosterilen_aday']}",
        ])
