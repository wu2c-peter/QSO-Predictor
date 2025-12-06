# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for QSO Predictor v2.0
# 
# To build:
#   pip install pyinstaller
#   pyinstaller qso_predictor.spec
#
# Output will be in dist/QSO Predictor.exe

import sys
from pathlib import Path

block_cipher = None

# Data files to include (non-Python files AND scripts run as subprocess)
datas = [
    ('VERSION', '.'),           # Version file for get_version()
    ('icon.ico', '.'),          # Application icon
    ('README.md', '.'),         # Documentation
    
    # Training scripts (run as subprocess via QProcess, not imported)
    ('training', 'training'),   # Include entire training folder
]

# Hidden imports that PyInstaller might miss
hiddenimports = [
    # MQTT
    'paho.mqtt.client',
    'paho.mqtt.enums',
    
    # PyQt6
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    
    # Core dependencies
    'numpy',
    'requests',
    'urllib3',
    'charset_normalizer',
    'certifi',
    'idna',
    
    # ML dependencies (for trained models)
    'sklearn',
    'sklearn.ensemble',
    'sklearn.ensemble._forest',
    'sklearn.ensemble._gb',
    'sklearn.tree',
    'sklearn.tree._tree',
    'sklearn.utils._cython_blas',
    'sklearn.neighbors._typedefs',
    'sklearn.utils._typedefs',
    'sklearn.utils._heap',
    'sklearn.utils._sorting',
    'sklearn.utils._vector_sentinel',
    'joblib',
    
    # Local intel modules
    'local_intel',
    'local_intel.models',
    'local_intel.session_tracker',
    'local_intel.predictor',
    'local_intel.model_manager',
    'local_intel.behavior_predictor',
    'local_intel.log_discovery',
    'local_intel.log_parser',
    
    # Training modules
    'training',
    'training.feature_builders',
    'training.trainer_process',
]

a = Analysis(
    ['main_v2.py'],              # v2 entry point
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
