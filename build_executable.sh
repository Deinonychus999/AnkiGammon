#!/bin/bash
# Build script for creating XG2Anki macOS/Linux executable
# Run this to create a standalone executable file

set -e  # Exit on error

echo "========================================"
echo "XG2Anki Executable Builder (macOS/Linux)"
echo "========================================"
echo ""

# Detect platform
PLATFORM=$(uname)
echo "Detected platform: $PLATFORM"
echo ""

# Check if PyInstaller is installed
if ! python3 -c "import PyInstaller" 2>/dev/null; then
    echo "PyInstaller not found. Installing..."
    pip3 install pyinstaller
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to install PyInstaller"
        exit 1
    fi
fi

# Clean previous builds
echo "Cleaning previous builds..."
rm -rf build dist

# Determine which spec file to use
if [ "$PLATFORM" == "Darwin" ]; then
    SPEC_FILE="xg2anki-mac.spec"
    echo "Using macOS spec file: $SPEC_FILE"
else
    SPEC_FILE="xg2anki.spec"
    echo "Using Linux spec file: $SPEC_FILE"
fi

# Build the executable
echo ""
echo "Building executable..."
pyinstaller "$SPEC_FILE"

if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: Build failed!"
    exit 1
fi

# Success message
echo ""
echo "========================================"
echo "Build completed successfully!"
echo "========================================"
echo ""
echo "Executable location: dist/xg2anki"
echo ""

# Make executable (just to be sure)
chmod +x dist/xg2anki

# macOS-specific instructions
if [ "$PLATFORM" == "Darwin" ]; then
    echo "macOS Users:"
    echo "  - First run may require: Right-click → Open"
    echo "  - Or: System Settings → Privacy & Security → Allow"
    echo ""
    echo "To allow running from anywhere:"
    echo "  xattr -cr dist/xg2anki"
    echo ""
fi

echo "You can now distribute this file to users."
echo "Users do NOT need Python installed."
echo ""

# Test the executable
echo "Testing executable..."
if ./dist/xg2anki --help > /dev/null 2>&1; then
    echo "✓ Executable test passed!"
else
    echo "⚠ Warning: Executable test failed. Please check manually."
fi
echo ""
