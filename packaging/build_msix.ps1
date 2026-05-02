# build_msix.ps1
# Assembles the MSIX package for QSO Predictor.
#
# Prerequisites:
#   1. PyInstaller onedir build completed: dist\QSO Predictor\ exists
#   2. MSIX icon assets generated: packaging\Assets\ exists (run make_msix_assets.py first)
#   3. AppxManifest.xml exists in packaging\
#   4. Windows SDK installed (for MakeAppx.exe)
#
# Run from repo root:
#   .\packaging\build_msix.ps1
#
# Output: packaging\QSOPredictor_2.5.5.0_x64.msix

$ErrorActionPreference = "Stop"

# --- Configuration ---
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$PackagingDir = Join-Path $RepoRoot "packaging"
$StagingDir = Join-Path $PackagingDir "staging"
$PyInstallerOutput = Join-Path $RepoRoot "dist\QSO Predictor"
$AssetsDir = Join-Path $PackagingDir "Assets"
$ManifestPath = Join-Path $PackagingDir "AppxManifest.xml"
$OutputMsix = Join-Path $PackagingDir "QSOPredictor_2.5.5.0_x64.msix"

# Find MakeAppx.exe (handle any SDK version)
$SdkBinRoot = "C:\Program Files (x86)\Windows Kits\10\bin"
$MakeAppx = Get-ChildItem -Path $SdkBinRoot -Recurse -Filter "makeappx.exe" `
    -ErrorAction SilentlyContinue | Where-Object { $_.Directory.Name -eq "x64" } `
    | Select-Object -First 1 -ExpandProperty FullName

if (-not $MakeAppx) {
    Write-Error "MakeAppx.exe not found under $SdkBinRoot. Is Windows SDK installed?"
    exit 1
}
Write-Host "Using MakeAppx: $MakeAppx" -ForegroundColor Cyan

# --- Pre-flight checks ---
Write-Host "`n--- Pre-flight checks ---" -ForegroundColor Yellow

if (-not (Test-Path $PyInstallerOutput)) {
    Write-Error "PyInstaller output not found: $PyInstallerOutput`nRun 'pyinstaller qso_predictor_msix.spec' first."
    exit 1
}
Write-Host "  [OK] PyInstaller onedir output found"

if (-not (Test-Path $AssetsDir)) {
    Write-Error "MSIX assets not found: $AssetsDir`nRun 'python make_msix_assets.py' first."
    exit 1
}
$AssetCount = (Get-ChildItem $AssetsDir -Filter "*.png").Count
Write-Host "  [OK] MSIX assets found ($AssetCount files)"

if (-not (Test-Path $ManifestPath)) {
    Write-Error "AppxManifest.xml not found: $ManifestPath"
    exit 1
}
Write-Host "  [OK] AppxManifest.xml found"

# --- Stage files ---
Write-Host "`n--- Staging files ---" -ForegroundColor Yellow

if (Test-Path $StagingDir) {
    Write-Host "  Removing old staging directory"
    Remove-Item -Recurse -Force $StagingDir
}
New-Item -ItemType Directory -Path $StagingDir -Force | Out-Null

Write-Host "  Copying PyInstaller output..."
Copy-Item -Path "$PyInstallerOutput\*" -Destination $StagingDir -Recurse -Force

Write-Host "  Copying AppxManifest.xml..."
Copy-Item -Path $ManifestPath -Destination "$StagingDir\AppxManifest.xml" -Force

Write-Host "  Copying Assets..."
$StagingAssetsDir = Join-Path $StagingDir "Assets"
New-Item -ItemType Directory -Path $StagingAssetsDir -Force | Out-Null
Copy-Item -Path "$AssetsDir\*" -Destination $StagingAssetsDir -Recurse -Force

# Verify key files in staging
if (-not (Test-Path "$StagingDir\QSO Predictor.exe")) {
    Write-Error "QSO Predictor.exe missing from staging directory"
    exit 1
}
if (-not (Test-Path "$StagingDir\AppxManifest.xml")) {
    Write-Error "AppxManifest.xml missing from staging directory"
    exit 1
}

Write-Host "  [OK] Staging complete"

# --- Build MSIX ---
Write-Host "`n--- Building MSIX ---" -ForegroundColor Yellow

if (Test-Path $OutputMsix) {
    Write-Host "  Removing previous MSIX: $OutputMsix"
    Remove-Item $OutputMsix -Force
}

& $MakeAppx pack /d $StagingDir /p $OutputMsix /o
if ($LASTEXITCODE -ne 0) {
    Write-Error "MakeAppx failed with exit code $LASTEXITCODE"
    exit 1
}

# --- Success ---
Write-Host "`n--- Success! ---" -ForegroundColor Green
Write-Host "MSIX package created: $OutputMsix"
$MsixSize = (Get-Item $OutputMsix).Length / 1MB
Write-Host "Size: $([math]::Round($MsixSize, 2)) MB"

Write-Host "`nNext steps:"
Write-Host "  1. To test locally:  Add-AppxPackage -Path '$OutputMsix'"
Write-Host "     (will fail without signing; that's expected for local test)"
Write-Host "  2. For local signed test: generate self-signed cert and sign the MSIX"
Write-Host "  3. For Store submission: upload directly to Partner Center (Store signs it)"
