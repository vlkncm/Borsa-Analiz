@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Borsa Analiz Pro MAX v2 - EXE ve SETUP Olustur

echo.
echo ==================================================
echo  BORSA ANALIZ PRO MAX v4.4.0
echo  EXE ve SETUP OLUSTURMA
echo ==================================================
echo.

set "PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo Yeni Python ortami olusturuluyor...
    where py >nul 2>nul
    if errorlevel 1 (
        echo HATA: Python bulunamadi.
        echo PyCharm icinden bu klasoru proje olarak acip Python kurmalisin.
        pause
        exit /b 1
    )
    py -m venv .venv
)

echo Gerekli paketler kuruluyor...
"%PYTHON%" -m pip install --upgrade pip
if errorlevel 1 goto :hata

"%PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 goto :hata

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
--hidden-import formasyon_motoru ^
--hidden-import takip_modulu ^
--collect-submodules PySide6.QtWidgets ^
--collect-submodules PySide6.QtCore ^
--collect-submodules PySide6.QtGui ^
app_qt.py

if not exist "dist\BorsaAnalizProMAX\BorsaAnalizProMAX.exe" goto :hata

echo.
echo EXE BASARILI:
echo %~dp0dist\BorsaAnalizProMAX\BorsaAnalizProMAX.exe
echo.

set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"

if not exist "%ISCC%" (
    echo HATA: Inno Setup Compiler bulunamadi.
    echo Inno Setup 6 kurulu olmali.
    pause
    exit /b 1
)

echo Windows kurulum dosyasi olusturuluyor...
"%ISCC%" "BorsaAnalizProMAX_v2.iss"
if errorlevel 1 goto :hata

if exist "SetupOutput\Setup_Borsa_Analiz_Pro_MAX_v4.4.0.1.exe" (
    echo.
    echo ==================================================
    echo  HER SEY BASARILI
    echo  PAYLASILACAK TEK DOSYA:
    echo  %~dp0SetupOutput\Setup_Borsa_Analiz_Pro_MAX_v4.4.0.1.exe
    echo ==================================================
    explorer "%~dp0SetupOutput"
    pause
    exit /b 0
)

:hata
echo.
echo ==================================================
echo HATA: Derleme tamamlanamadi.
echo Yukaridaki son hata satirlarini kontrol et.
echo ==================================================
pause
exit /b 1
