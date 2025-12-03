@echo off
REM Build script for QSO Predictor Windows executable
REM 
REM Prerequisites:
REM   Python 3.10+ installed
REM   PyInstaller (will be installed automatically if missing)
REM
REM Output: dist\QSO Predictor.exe

echo.
echo ========================================
echo  Building QSO Predictor
echo ========================================
echo.

REM Check if Python is available via the launcher
py --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found!
    echo Please install Python 3.10+ from python.org
    pause
    exit /b 1
)

REM Check if PyInstaller is installed
py -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo PyInstaller not found. Installing...
    py -m pip install pyinstaller
    if errorlevel 1 (
        echo ERROR: Failed to install PyInstaller
        pause
        exit /b 1
    )
)

REM Clean previous builds
echo Cleaning previous builds...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul

REM Build the executable
echo Building executable...
py -m PyInstaller qso_predictor.spec

if errorlevel 1 (
    echo.
    echo BUILD FAILED!
    pause
    exit /b 1
)

echo.
echo ========================================
echo  Build complete!
echo  Output: dist\QSO Predictor.exe
echo ========================================
echo.

REM Show file size
for %%A in ("dist\QSO Predictor.exe") do echo File size: %%~zA bytes

pause
