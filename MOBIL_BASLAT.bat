@echo off
cd /d "%~dp0"
title Borsa Analiz Mobil
python mobile_app.py
if errorlevel 1 (
  echo.
  echo Uygulama baslatilamadi. Python ve gereksinimlerin kurulu oldugunu kontrol edin.
  pause
)
