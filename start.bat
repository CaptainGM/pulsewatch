@echo off
setlocal
cd /d "%~dp0"
title PulseWatch

if /i "%~1"=="demo" set "MODE=demo"
if /i "%~1"=="normal" set "MODE=normal"

if not defined MODE (
  echo.
  echo PulseWatch - hangi veriyle acilsin?
  echo   1 - Normal: mevcut veritabani backend\data\pulsewatch.db
  echo   2 - Demo: ornek veriler backend\data\demo.db
  echo.
  choice /c 12 /n /m "Seciminiz: "
  if errorlevel 2 set "MODE=demo"
  if errorlevel 1 if not defined MODE set "MODE=normal"
)

where python >nul 2>&1
if errorlevel 1 (
  echo Python bulunamadi. Python 3.11 veya ustunu kurun.
  goto fail
)

where npm >nul 2>&1
if errorlevel 1 (
  echo Node.js bulunamadi. Node.js 20 veya ustunu kurun.
  goto fail
)

if not exist "backend\.venv\Scripts\python.exe" (
  echo Python sanal ortami olusturuluyor...
  python -m venv "backend\.venv"
  if errorlevel 1 goto fail
)

"backend\.venv\Scripts\python.exe" -m pip install -q -r "backend\requirements-dev.txt"
if errorlevel 1 goto fail

if not exist "frontend\node_modules\vite" (
  echo Arayuz paketleri kuruluyor, bu bir dakika surebilir...
  cd /d "%~dp0frontend"
  call npm ci
  cd /d "%~dp0"
)
if not exist "frontend\node_modules\vite" goto fail

"backend\.venv\Scripts\python.exe" scripts\servis.py baslat %MODE%
if errorlevel 1 goto fail

start "" "http://localhost:8010"
endlocal
exit /b 0

:fail
echo.
echo Bir sorun olustu. Kayitlar logs klasorunde.
if "%~1"=="" pause
endlocal
exit /b 1
