# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for QSO Predictor
# 
# To build:
#   pip install pyinstaller
#   pyinstaller qso_predictor.spec
#
# Output will be in dist/QSO Predictor.exe

import sys
from pathlib import Path

block_cipher = None

# Collect all Python source files
py_files = [
    'main.py',
    'analyzer.py',
    'band_map_widget.py',
    'config_manager.py',
    'mqtt_client.py',
    'udp_handler.py',
    'settings_dialog.py',
    'solar_client.py',
    'launcher.py',
]

# Data files to include (non-Python files)
datas = [
    ('VERSION', '.'),           # Version file for get_version()
    ('icon.ico', '.'),          # Application icon
    ('README.md', '.'),         # Documentation
]

# Hidden imports that PyInstaller might miss
hiddenimports = [
    'paho.mqtt.client',
    'paho.mqtt.enums',
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'numpy',
    'requests',                 # For update checker
    'urllib3',                  # requests dependency
    'charset_normalizer',       # requests dependency
    'certifi',                  # requests dependency
    'idna',                     # requests dependency
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    name='QSO Predictor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,                    # Compress executable (smaller file size)
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,               # No console window (windowed app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',             # Application icon
)
