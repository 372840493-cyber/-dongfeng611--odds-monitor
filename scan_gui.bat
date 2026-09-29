@echo off
chcp 65001 >nul
title DongFeng-61 Intercontinental Missile
cd /d "%~dp0"
set "PYEXE=C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%PYEXE%" goto run
where python >nul 2>&1
if %errorlevel% equ 0 set "PYEXE=python"
if not exist "%PYEXE%" if "%PYEXE%"=="python" goto run
:run
"%PYEXE%" scan_gui.py
