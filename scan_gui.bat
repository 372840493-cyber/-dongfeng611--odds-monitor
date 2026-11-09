@echo off
chcp 65001 >nul
title DongFeng-61 Intercontinental Missile
cd /d "%~dp0"
rem 必须优先使用安装了 curl_cffi 的系统 Python；包管理器运行时可能缺少该组件。
set "PYEXE=C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe"
if exist "%PYEXE%" goto run
where python >nul 2>&1
if %errorlevel% equ 0 set "PYEXE=python"
if "%PYEXE%"=="python" goto run
echo 未找到 Python，请直接运行已打包的“东风-61洲际导弹.exe”
exit /b 1
:run
"%PYEXE%" scan_gui.py
