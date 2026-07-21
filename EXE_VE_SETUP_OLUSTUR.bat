@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title Borsa Analiz Pro MAX - Evrensel EXE ve SETUP

set "PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    where py >nul 2>nul || (
        echo HATA: Python bulunamadi.
        pause
        exit /b 1
    )
    py -m venv .venv || (
        echo HATA: Sanal ortam olusturulamadi.
        pause
        exit /b 1
    )
)

"%PYTHON%" -m pip install --upgrade pip || goto :paket_hatasi
"%PYTHON%" -m pip install -r requirements.txt || goto :paket_hatasi
"%PYTHON%" -m pip install pyinstaller || goto :paket_hatasi

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist SetupOutput rmdir /s /q SetupOutput
if exist BorsaAnalizProMAX.spec del /q BorsaAnalizProMAX.spec

"%PYTHON%" -m PyInstaller ^
--noconfirm ^
--clean ^
--onedir ^
--windowed ^
--name BorsaAnalizProMAX ^
--icon=logo.ico ^
--add-data "logo.png;." ^
--add-data "logo.ico;." ^
--add-data "bist_hisseleri_613_aktif.txt;." ^
--add-data "bist_hisseleri_dogrulanmis.txt;." ^
--hidden-import main ^
--hidden-import veri_saglayici ^
--hidden-import borsa_tarayici ^
--hidden-import pro_moduller ^
--hidden-import kap_modulu ^
--hidden-import backtest ^
--hidden-import mtf_grafik ^
--hidden-import olasilik_temettu ^
--hidden-import faaliyet_raporu ^
--hidden-import piyasa_guncelleme ^
--hidden-import sistem_kontrol ^
--hidden-import v4_puanlama ^
--hidden-import formasyon_motoru ^
--hidden-import takip_modulu ^
--hidden-import fibonacci_motoru ^
--hidden-import karar_motoru ^
--hidden-import satis_karar_motoru ^
--hidden-import vade_motoru ^
--hidden-import profesyonel_analiz ^
app_qt.py

if errorlevel 1 goto :pyinstaller_hatasi

if not exist "dist\BorsaAnalizProMAX\BorsaAnalizProMAX.exe" (
    echo HATA: Ana EXE bulunamadi.
    pause
    exit /b 1
)

set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"

if not exist "%ISCC%" (
    echo HATA: Inno Setup Compiler bulunamadi.
    pause
    exit /b 1
)

"%ISCC%" "BorsaAnalizProMAX_v2.iss"
if errorlevel 1 goto :inno_hatasi

set "SETUP_FILE="
for /f "delims=" %%F in ('dir /b /a-d /o-d "SetupOutput\*.exe" 2^>nul') do (
    if not defined SETUP_FILE set "SETUP_FILE=%~dp0SetupOutput\%%F"
)

if not defined SETUP_FILE (
    echo HATA: SetupOutput klasorunde kurulum EXE dosyasi bulunamadi.
    pause
    exit /b 1
)

echo.
echo ==================================================
echo HER SEY BASARILI
echo KURULUM DOSYASI:
echo !SETUP_FILE!
echo ==================================================
explorer "%~dp0SetupOutput"
pause
exit /b 0

:paket_hatasi
echo HATA: Python paketleri kurulurken hata olustu.
pause
exit /b 1

:pyinstaller_hatasi
echo HATA: PyInstaller EXE olusturamadi.
pause
exit /b 1

:inno_hatasi
echo HATA: Inno Setup kurulum dosyasini olusturamadi.
pause
exit /b 1
