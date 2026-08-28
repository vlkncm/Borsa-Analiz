from pathlib import Path
import sys
from unittest.mock import patch

from app_qt import tarama_alt_sureci_komutu


def test_kaynak_calismada_scan_runner_ayri_python_surecidir():
    program,arguments=tarama_alt_sureci_komutu()
    assert Path(program).resolve()==Path(sys.executable).resolve()
    assert len(arguments)==1 and Path(arguments[0]).name=="scan_runner.py"
    assert Path(arguments[0]).is_file()


def test_paketli_program_kendi_exesini_headless_modda_baslatir():
    packaged=r"C:\Program Files\BorsaAnaliz\BorsaAnalizProMAX.exe"
    with patch.object(sys,"frozen",True,create=True),patch.object(sys,"executable",packaged):
        program,arguments=tarama_alt_sureci_komutu()
    assert program==packaged
    assert arguments==["--headless-scan"]
    assert "BorsaTaramaMotoru.exe" not in program
