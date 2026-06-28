#!/usr/bin/env bash
set -e

echo "========================================"
echo " WhatsApp Inviter - macOS Build Script"
echo "========================================"
echo

cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

echo "Activating virtual environment..."
source venv/bin/activate

echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo
echo "Building app bundle..."
pyinstaller app.spec --noconfirm

echo
echo "========================================"
echo " Build complete!"
echo " Output: dist/WhatsAppInviter.app"
echo "========================================"
echo
echo "To distribute, zip the .app:"
echo "  ditto -c -k --keepParent dist/WhatsAppInviter.app dist/WhatsAppInviter-mac.zip"
