@echo off
chcp 65001 >nul
title DongFeng61-OddsApi
cd /d "%~dp0"
set "PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe"
if not exist "%PY%" set "PY=python"
:loop
"%PY%" odds_api.py >> "%~dp0odds_api.out.log" 2>> "%~dp0odds_api.err.log"
ping -n 11 127.0.0.1 >nul
goto loop
