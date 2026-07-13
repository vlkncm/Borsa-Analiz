@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Borsa Analiz Pro MAX v4.2.1 - EXE ve SETUP Olustur

echo.
echo ==================================================
echo  BORSA ANALIZ PRO MAX v4.2.1
echo  EXE ve SETUP OLUSTURMA
echo ==================================================
echo.

set "PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo Yeni Python ortami olusturuluyor...
    where py >nul 2>nul
    if errorlevel 1 (
        echo.
        echo HATA: Python bulunamadi.
        echo Python 3.11 veya 3.12 kurulu olmali.
        pause
        exit /b 1
    )

    py -m venv .venv
    if errorlevel 1 (
        echo.
        echo HATA: Python sanal ortami olusturulamadi.
        pause
        exit /b 1
    )
)

echo.
echo Gerekli paketler kuruluyor...
"%PYTHON%" -m pip install --upgrade pip
if errorlevel 1 goto :paket_hatasi

"%PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 goto :paket_hatasi

"%PYTHON%" -m pip install pyinstaller
if errorlevel 1 goto :paket_hatasi

echo.
echo Eski derleme dosyalari temizleniyor...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist BorsaAnalizProMAX.spec del /q BorsaAnalizProMAX.spec
if exist SetupOutput rmdir /s /q SetupOutput

echo.
echo Hizli uygulama klasoru olusturuluyor...
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
app_qt.py

if errorlevel 1 goto :pyinstaller_hatasi

if not exist "dist\BorsaAnalizProMAX\BorsaAnalizProMAX.exe" (
    echo.
    echo HATA: PyInstaller tamamlandi ancak EXE bulunamadi.
    echo Beklenen:
    echo %~dp0dist\BorsaAnalizProMAX\BorsaAnalizProMAX.exe
    pause
    exit /b 1
)

echo.
echo EXE BASARILI:
echo %~dp0dist\BorsaAnalizProMAX\BorsaAnalizProMAX.exe
echo.

set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"

if not exist "%ISCC%" (
    echo.
    echo HATA: Inno Setup Compiler bulunamadi.
    echo Inno Setup 6 kurulu olmali.
    pause
    exit /b 1
)

if not exist "BorsaAnalizProMAX_v2.iss" (
    echo.
    echo HATA: BorsaAnalizProMAX_v2.iss bulunamadi.
    pause
    exit /b 1
)

echo Windows kurulum dosyasi olusturuluyor...
"%ISCC%" "BorsaAnalizProMAX_v2.iss"
if errorlevel 1 goto :inno_hatasi

set "SETUP_FILE="

if exist "SetupOutput\Setup_Borsa_Analiz_Pro_MAX_v4.2.1.exe" (
    set "SETUP_FILE=%~dp0SetupOutput\Setup_Borsa_Analiz_Pro_MAX_v4.2.1.exe"
) else (
    for %%F in ("SetupOutput\*.exe") do (
        if exist "%%~F" set "SETUP_FILE=%%~fF"
    )
)

if not defined SETUP_FILE (
    echo.
    echo HATA: Kurulum tamamlandi ancak Setup dosyasi bulunamadi.
    echo SetupOutput klasorunu kontrol et.
    pause
    exit /b 1
)

echo.
echo ==================================================
echo  HER SEY BASARILI
echo  PAYLASILACAK TEK DOSYA:
echo  %SETUP_FILE%
echo ==================================================
explorer "%~dp0SetupOutput"
pause
exit /b 0

:paket_hatasi
echo.
echo ==================================================
echo HATA: Gerekli Python paketleri kurulamad.
echo Internet baglantisini ve requirements.txt dosyasini kontrol et.
echo ==================================================
pause
exit /b 1

:pyinstaller_hatasi
echo.
echo ==================================================
echo HATA: PyInstaller EXE olustururken hata verdi.
echo Yukaridaki son hata satirlarini kontrol et.
echo ==================================================
pause
exit /b 1

:inno_hatasi
echo.
echo ==================================================
echo HATA: Inno Setup kurulum dosyasini olusturamadi.
echo Yukaridaki son hata satirlarini kontrol et.
echo ==================================================
pause
exit /b 1
