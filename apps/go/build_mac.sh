#!/usr/bin/env bash
set -e

echo "========================================"
echo " WhatsApp Inviter (Go) - macOS Build"
echo "========================================"
echo

cd "$(dirname "$0")"

if ! command -v go &>/dev/null; then
    echo "ERROR: Go is not installed. Install from https://go.dev/dl/"
    exit 1
fi

if ! command -v wails &>/dev/null; then
    echo "Installing Wails CLI..."
    go install github.com/wailsapp/wails/v2/cmd/wails@latest
fi

echo "Tidying Go modules..."
go mod tidy

echo "Building Wails app..."
wails build -clean

echo
echo "========================================"
echo " Build complete!"
echo " Output: build/bin/WhatsAppInviter.app"
echo "========================================"
