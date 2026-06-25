@echo off
setlocal enabledelayedexpansion

echo ========================================
echo  WhatsApp Inviter - Build Script
echo ========================================
echo.

cd /d "%~dp0"

REM Prefer py launcher on Windows, fall back to python
where py >nul 2>&1
if %errorlevel%==0 (
    set PYTHON=py -3
) else (
    set PYTHON=python
)

if not exist "venv" (
    echo Creating virtual environment...
    %PYTHON% -m venv venv
    if errorlevel 1 (
        echo ERROR: Could not create virtual environment. Is Python installed?
        pause
        exit /b 1
    )
)

echo Activating virtual environment...
call venv\Scripts\activate.bat

echo Installing dependencies...
pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo Building executable...
pyinstaller app.spec --noconfirm
if errorlevel 1 (
    echo ERROR: PyInstaller build failed.
    pause
    exit /b 1
)

echo.
echo ========================================
echo  Build complete!
echo  Output: dist\WhatsAppInviter.exe
echo ========================================
echo.
pause
