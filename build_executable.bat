@echo off
REM Build script for creating AnkiGammon GUI executable (Windows)
REM Usage: build_executable.bat

echo ========================================
echo Building AnkiGammon GUI Executable
echo ========================================
echo.

REM Clean previous builds
if exist build (
    echo Cleaning build directory...
    rmdir /s /q build
)
if exist dist (
    echo Cleaning dist directory...
    rmdir /s /q dist
)

echo.
echo Running PyInstaller...
pyinstaller ankigammon.spec

if %errorlevel% neq 0 (
    echo.
    echo ========================================
    echo Build FAILED
    echo ========================================
    exit /b 1
)

echo.
echo ========================================
echo Build completed successfully!
echo ========================================
echo.
echo Executable: dist\ankigammon.exe
echo.
