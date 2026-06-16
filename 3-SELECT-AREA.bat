@echo off
chcp 65001 >nul
title Ronin DPS - Select area
cd /d "%~dp0"

if not exist "%~dp0venv\Scripts\python.exe" (
    echo [ERROR] Run 1-INSTALL.bat first.
    pause
    exit /b 1
)

REM Re-draw the game area with the mouse (if you changed window size/position).
"%~dp0venv\Scripts\python.exe" "%~dp0main.py" --pick

if errorlevel 1 pause
