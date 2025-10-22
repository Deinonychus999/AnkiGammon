@echo off
REM Build script for creating AnkiGammon Windows executable
REM Run this to create a standalone .exe file

echo ========================================
echo AnkiGammon Executable Builder
echo ========================================
echo.

REM Check if PyInstaller is installed
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo PyInstaller not found. Installing...
    pip install pyinstaller
    if errorlevel 1 (
        echo ERROR: Failed to install PyInstaller
        pause
        exit /b 1
    )
)

REM Clean previous builds
echo Cleaning previous builds...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Build the executable
echo.
echo Building executable...
pyinstaller ankigammon.spec

if errorlevel 1 (
    echo.
    echo ERROR: Build failed!
    pause
    exit /b 1
)

REM Success message
echo.
echo ========================================
echo Build completed successfully!
echo ========================================
echo.
echo Executable location: dist\ankigammon.exe
echo.
echo You can now distribute this file to users.
echo Users do NOT need Python installed.
echo.
pause
