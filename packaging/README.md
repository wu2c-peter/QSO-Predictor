# MSIX Packaging

This directory contains files needed to build a Microsoft Store MSIX package
for QSO Predictor.

## Files

- `AppxManifest.xml` — MSIX package manifest with Partner Center identity values
- `build_msix.ps1` — PowerShell script to assemble and package the MSIX

## Prerequisites

- Windows 10/11 PC
- Python 3.11+ with Pillow (`pip install Pillow`)
- PyInstaller (`pip install pyinstaller`)
- Windows SDK (for MakeAppx.exe) — install from https://developer.microsoft.com/windows/downloads/windows-sdk/

## Build process

From the repo root on Windows:

```powershell
# 1. Build the PyInstaller onedir distribution
pyinstaller qso_predictor_msix.spec

# 2. Generate MSIX icon assets from logo.png
python make_msix_assets.py

# 3. Package into MSIX
.\packaging\build_msix.ps1
```

Output: `packaging\QSOPredictor_2.5.4.0_x64.msix`

## Versioning

When releasing a new version:

1. Update `Version` attribute in `AppxManifest.xml` to `X.Y.Z.0` (4-part, last segment must be 0 for Store)
2. Rebuild using the same steps above
3. Upload new MSIX to Partner Center

## Generated output, not checked in

These are produced during the build and ignored by git:

- `packaging/Assets/` — generated PNG icons (re-run make_msix_assets.py to regenerate)
- `packaging/staging/` — assembled package contents before packing
- `packaging/*.msix` — output MSIX packages

## Package identity

These values come from Partner Center and must not change:

- Package Name: `PeterHirstWU2C.QSOPredictor`
- Publisher: `CN=66D60A45-A38B-4C72-BFF6-F710FB0E496D`
- Publisher Display Name: `Peter Hirst (WU2C)`
- Store ID: `9MWCW2FTB866`

Full identity details documented in `docs/MICROSOFT_STORE_IDENTITY.md`.
