# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

is_macos = sys.platform == 'darwin'

block_cipher = None
project_root = Path(SPECPATH)

ctk_datas, ctk_binaries, ctk_hiddenimports = collect_all('customtkinter')

a = Analysis(
    ['app.py'],
    pathex=[str(project_root)],
    binaries=ctk_binaries,
    datas=[
        (str(project_root / 'assets'), 'assets'),
        *ctk_datas,
    ],
    hiddenimports=[
        *ctk_hiddenimports,
        'openpyxl',
        'pywhatkit',
        'PIL',
        'PIL._tkinter_finder',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='WhatsAppInviter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

if is_macos:
    app = BUNDLE(
        exe,
        name='WhatsAppInviter.app',
        icon=None,
        bundle_identifier='nl.hsleiden.whatsappinviter',
        info_plist={
            'CFBundleName': 'WhatsApp Inviter',
            'CFBundleDisplayName': 'WhatsApp Inviter',
            'CFBundleShortVersionString': '1.0.0',
            'NSHighResolutionCapable': True,
        },
    )
