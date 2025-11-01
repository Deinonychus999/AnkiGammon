# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for building AnkiGammon GUI executable.

Usage:
    pyinstaller ankigammon-gui.spec

This will create:
    - dist/ankigammon-gui.exe (Windows)
    - dist/AnkiGammon.app (macOS bundle)
"""

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['ankigammon/gui/app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('ankigammon/gui/resources', 'ankigammon/gui/resources'),
        # Include entire ankigammon package
        ('ankigammon', 'ankigammon'),
    ],
    hiddenimports=[
        # PySide6 imports
        'PySide6.QtCore',
        'PySide6.QtWidgets',
        'PySide6.QtGui',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebEngineCore',
        # ankigammon core
        'ankigammon.parsers.xg_text_parser',
        'ankigammon.parsers.gnubg_parser',
        'ankigammon.renderer.svg_board_renderer',
        'ankigammon.renderer.color_schemes',
        'ankigammon.renderer.animation_controller',
        'ankigammon.renderer.animation_helper',
        'ankigammon.anki.ankiconnect',
        'ankigammon.anki.apkg_exporter',
        'ankigammon.anki.card_generator',
        'ankigammon.anki.card_styles',
        'ankigammon.models',
        'ankigammon.settings',
        'ankigammon.utils.xgid',
        'ankigammon.utils.ogid',
        'ankigammon.utils.gnuid',
        'ankigammon.utils.move_parser',
        'ankigammon.utils.gnubg_analyzer',
        # ankigammon analysis
        'ankigammon.analysis',
        'ankigammon.analysis.score_matrix',
        # ankigammon GUI
        'ankigammon.gui',
        'ankigammon.gui.main_window',
        'ankigammon.gui.widgets',
        'ankigammon.gui.widgets.position_list',
        'ankigammon.gui.widgets.smart_input',
        'ankigammon.gui.dialogs',
        'ankigammon.gui.dialogs.settings_dialog',
        'ankigammon.gui.dialogs.export_dialog',
        'ankigammon.gui.dialogs.input_dialog',
        # External dependencies
        'genanki',
        'requests',
        'bs4',
        'lxml',
        'qtawesome',
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
    name='ankigammon',
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
    icon='ankigammon/gui/resources/icon.ico',
)

# For macOS, create an app bundle
if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='AnkiGammon.app',
        icon='ankigammon/gui/resources/icon.icns',
        bundle_identifier='com.ankigammon.app',
        info_plist={
            'NSHighResolutionCapable': 'True',
            'LSBackgroundOnly': 'False',
            'CFBundleShortVersionString': '1.1.0',
        },
    )
