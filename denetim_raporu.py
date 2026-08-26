"""Excel ve günlük özet için açıklanabilir denetim tabloları."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable
import pandas as pd

from strateji_kalibrasyon import olasilik_kalibrasyonu


def denetim_tablosu(results: Iterable[Dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for item in results:
        row = {"Hisse": item.get("symbol", ""), "Karar": item.get("yatirim_karari", ""), "Doğrulanmış Olasılık %": item.get("dogrulanmis_olasilik", 0), "Örnek Sayısı": item.get("dogrulama_ornek_sayisi", 0), "Strateji": item.get("strateji", ""), "Canlı Kanıt": item.get("canli_kanit_durumu", ""), "Canlı Kanıt İşlem": item.get("canli_kanit_islem", 0), "Net Canlı Getiri %": item.get("canli_kanit_net_getiri", 0), "Kilit Nedeni": item.get("canli_kanit_kilit_nedeni", ""), "Likidite": item.get("likidite_seviyesi", ""), "Temel Risk": item.get("temel_risk_notu", ""), "Uyarılar": item.get("canli_uyarilar", ""), "Neden": item.get("karar_nedenleri", "")}
        horizons = item.get("probability_by_horizon", {}) or {}
        for day in (1, 3, 5):
            value = horizons.get(day, horizons.get(str(day), {})) or {}
            row.update({f"{day} Gün Olasılık %": value.get("probability"),
                        f"{day} Gün OOS Örnek": value.get("sample_size", 0),
                        f"{day} Gün GA Alt %": value.get("ci_low"), f"{day} Gün GA Üst %": value.get("ci_high")})
        row.update({"Olasılık Tarihi": item.get("probability_as_of"),
                    "Başarılılarda Medyan Süre": item.get("median_target_time_success_days"),
                    "Brier Skoru": item.get("brier_skoru"), "Strateji Sürümü": item.get("strategy_version")})
        rows.append(row)
    return pd.DataFrame(rows)


def gunluk_ozet_yaz(output_dir: Path, results: Iterable[Dict[str, Any]], history: pd.DataFrame) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    audit = denetim_tablosu(results)
    calibration = olasilik_kalibrasyonu(history)
    path = output_dir / "Gunluk_Denetim_Ozeti.md"
    lines = ["# Günlük Denetim Özeti", "", f"Toplam taranan sonuç: {len(audit)}"]
    if not audit.empty:
        lines.extend([f"Doğrulama sonrası işlem senaryosu: {(audit['Karar'] == 'BUGÜN AL').sum()}", f"Uyarı içeren sonuç: {(audit['Uyarılar'].fillna('') != '').sum()}"])
    if not calibration.empty:
        # ``to_markdown`` ek ``tabulate`` bağımlılığı gerektirir; günlük rapor
        # kurulum gerektirmeden çalışsın diye sade CSV görünümü kullanılır.
        lines.extend(["", "## Olasılık Kalibrasyonu", "```", calibration.to_csv(index=False).strip(), "```"])
    lines.extend(["", "Bu rapor yatırım tavsiyesi veya getiri garantisi değildir."])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
