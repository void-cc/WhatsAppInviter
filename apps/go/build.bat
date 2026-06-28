@echo off
setlocal enabledelayedexpansion

echo ========================================
echo  WhatsApp Inviter (Go) - Build Script
echo ========================================
echo.

cd /d "%~dp0"

where go >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Go is not installed. Install from https://go.dev/dl/
    pause
    exit /b 1
)

where wails >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing Wails CLI...
    go install github.com/wailsapp/wails/v2/cmd/wails@latest
)

echo Tidying Go modules...
go mod tidy
if errorlevel 1 (
    echo ERROR: go mod tidy failed.
    pause
    exit /b 1
)

echo Building Wails app...
wails build -clean
if errorlevel 1 (
    echo ERROR: Wails build failed.
    pause
    exit /b 1
)

echo.
echo ========================================
echo  Build complete!
echo  Output: build\bin\WhatsAppInviter.exe
echo ========================================
echo.
pause
