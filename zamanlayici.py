"""Kullanıcının Windows hesabında kapanış sonrası tarama görevi kurar."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


TASK_NAME = "BorsaAnalizProMAX_AksamTarama"


def aksam_taramasi_planla(saat: str = "18:35") -> tuple[bool, str]:
    exe = Path(sys.executable).resolve()
    command = f'"{exe}" --gunsonu-tarama'
    args = ["schtasks", "/Create", "/TN", TASK_NAME, "/TR", command,
            "/SC", "DAILY", "/ST", saat, "/F", "/RL", "LIMITED"]
    completed = subprocess.run(args, capture_output=True, text=True, encoding="mbcs", errors="replace")
    if completed.returncode == 0:
        return True, f"Her iş günü kapanış sonrası tarama görevi {saat} için kuruldu. Görev adı: {TASK_NAME}"
    return False, (completed.stderr or completed.stdout or "Windows görev oluşturamadı.").strip()
