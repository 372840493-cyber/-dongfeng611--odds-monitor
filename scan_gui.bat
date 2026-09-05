@echo off
chcp 65001 >nul
title Over/Under Line Scanner
cd /d "%~dp0"
set "PYEXE=C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
where python >nul 2>&1
if %errorlevel% equ 0 set "PYEXE=python"
"%PYEXE%" scan_gui.py
