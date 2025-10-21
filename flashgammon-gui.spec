# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for building FlashGammon GUI executable.

Usage:
    pyinstaller flashgammon-gui.spec

This will create:
    - dist/flashgammon-gui.exe (Windows)
    - dist/FlashGammon.app (macOS bundle)
"""

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['flashgammon/gui/app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('flashgammon/gui/resources', 'flashgammon/gui/resources'),
        # Include entire flashgammon package
        ('flashgammon', 'flashgammon'),
    ],
    hiddenimports=[
        # PySide6 imports
        'PySide6.QtCore',
        'PySide6.QtWidgets',
        'PySide6.QtGui',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebEngineCore',
        # flashgammon core
        'flashgammon.parsers.xg_text_parser',
        'flashgammon.parsers.gnubg_parser',
        'flashgammon.renderer.svg_board_renderer',
        'flashgammon.renderer.color_schemes',
        'flashgammon.renderer.animation_controller',
        'flashgammon.renderer.animation_helper',
        'flashgammon.anki.ankiconnect',
        'flashgammon.anki.apkg_exporter',
        'flashgammon.anki.card_generator',
        'flashgammon.anki.card_styles',
        'flashgammon.models',
        'flashgammon.settings',
        'flashgammon.utils.xgid',
        'flashgammon.utils.move_parser',
        'flashgammon.utils.gnubg_analyzer',
        # flashgammon GUI
        'flashgammon.gui',
        'flashgammon.gui.main_window',
        'flashgammon.gui.widgets',
        'flashgammon.gui.widgets.position_list',
        'flashgammon.gui.dialogs',
        'flashgammon.gui.dialogs.settings_dialog',
        'flashgammon.gui.dialogs.export_dialog',
        # External dependencies
        'genanki',
        'requests',
        'bs4',
        'lxml',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'IPython',
        'jupyter',
        'tkinter',
    ],
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
    name='flashgammon-gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window for GUI app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='flashgammon/gui/resources/icon.ico',
)

# For macOS, create an app bundle
if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='FlashGammon.app',
        icon='flashgammon/gui/resources/icon.png',  # Use PNG for now, convert to .icns on macOS
        bundle_identifier='com.flashgammon.app',
        info_plist={
            'NSHighResolutionCapable': 'True',
            'LSBackgroundOnly': 'False',
            'CFBundleShortVersionString': '1.0.0',
        },
    )
