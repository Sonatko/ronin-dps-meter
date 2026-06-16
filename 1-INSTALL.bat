@echo off
chcp 65001 >nul
title Ronin DPS - Install
cd /d "%~dp0"

echo ============================================
echo   Ronin DPS Meter - Installation
echo ============================================
echo.
echo This is needed ONCE. Downloading Python
echo libraries (~150 MB). Please wait...
echo.

REM --- Find a REAL Python (skip venv) ---
REM 1) Try the py launcher first (most reliable)
set PYCMD=
py -3 --version >nul 2>nul
if %errorlevel%==0 (
    set PYCMD=py -3
    goto have_python
)

REM 2) Otherwise look for python in PATH, skipping any venv
for /f "delims=" %%p in ('where python 2^>nul') do (
    echo %%p | findstr /i "\\venv\\ \\.venv\\" >nul
    if errorlevel 1 (
        set PYCMD="%%p"
        goto have_python
    )
)

echo [ERROR] Python not found.
echo.
echo Install Python 3.10+ from https://python.org
echo IMPORTANT: tick the checkbox "Add Python to PATH"
echo Then run this file again.
echo.
pause
exit /b 1

:have_python
echo [1/3] Python found: %PYCMD%
%PYCMD% --version
echo.

if not exist "%~dp0venv\Scripts\python.exe" (
    echo [2/3] Creating venv environment...
    %PYCMD% -m venv "%~dp0venv"
    if not exist "%~dp0venv\Scripts\python.exe" goto error_venv
) else (
    echo [2/3] venv already exists.
)

echo [3/3] Installing libraries...
echo.
"%~dp0venv\Scripts\python.exe" -m pip install --upgrade pip
"%~dp0venv\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 goto error_pip

echo.
echo ============================================
echo   DONE! Installation finished.
echo ============================================
echo.
echo Now launch the game in your emulator,
echo then double-click 2-RUN.bat
echo.
pause
exit /b 0

:error_venv
echo.
echo [ERROR] Failed to create venv.
echo Reinstall Python from python.org with
echo "Add Python to PATH" checked.
pause
exit /b 1

:error_pip
echo.
echo [ERROR] Failed to install libraries.
echo Check your internet connection and run again.
pause
exit /b 1
