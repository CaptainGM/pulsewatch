@echo off
cd /d "%~dp0"
if not exist "backend\.venv\Scripts\python.exe" (
  echo Sanal ortam bulunamadi, PulseWatch zaten calismiyor olabilir.
  goto end
)
"backend\.venv\Scripts\python.exe" scripts\servis.py durdur
:end
ping -n 3 127.0.0.1 >nul
