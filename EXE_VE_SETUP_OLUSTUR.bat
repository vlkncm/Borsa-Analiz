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

"%PYTHON%" -m PyInstaller --noconfirm --clean BorsaAnalizProMAX.spec

if errorlevel 1 goto :pyinstaller_hatasi

"%PYTHON%" -m PyInstaller --noconfirm --clean BorsaTaramaMotoru.spec

if errorlevel 1 goto :pyinstaller_hatasi

copy /y "dist\BorsaTaramaMotoru\BorsaTaramaMotoru.exe" "dist\BorsaAnalizProMAX\BorsaTaramaMotoru.exe" >nul || goto :pyinstaller_hatasi

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
