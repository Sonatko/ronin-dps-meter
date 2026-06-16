@echo off
chcp 65001 >nul
title Ronin DPS
cd /d "%~dp0"

if not exist "%~dp0venv\Scripts\python.exe" (
    echo [ERROR] Run 1-INSTALL.bat first.
    pause
    exit /b 1
)

REM On the FIRST run: drag a rectangle over the game area (the screen dims).
REM The region is saved to config.json - next time no need to draw.
REM To re-draw the area - run 3-SELECT-AREA.bat
"%~dp0venv\Scripts\python.exe" "%~dp0main.py"

if errorlevel 1 (
    echo.
    echo Something went wrong. Open the emulator with the game and try again.
    pause
)
