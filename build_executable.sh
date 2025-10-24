#!/bin/bash

# Build script for creating AnkiGammon GUI executable (macOS/Linux)
# Usage: ./build_executable.sh

echo "========================================"
echo "Building AnkiGammon GUI Executable"
echo "========================================"
echo

# Clean previous builds
if [ -d "build" ]; then
    echo "Cleaning build directory..."
    rm -rf build
fi
if [ -d "dist" ]; then
    echo "Cleaning dist directory..."
    rm -rf dist
fi

echo
echo "Running PyInstaller..."
pyinstaller ankigammon.spec

if [ $? -ne 0 ]; then
    echo
    echo "========================================"
    echo "Build FAILED"
    echo "========================================"
    exit 1
fi

echo
echo "========================================"
echo "Build completed successfully!"
echo "========================================"
echo

# Display executable location based on platform
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "Application bundle: dist/AnkiGammon.app"
else
    echo "Executable: dist/ankigammon"
fi
echo
