# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for building XG2Anki GUI executable.

Usage:
    pyinstaller xg2anki-gui.spec

This will create:
    - dist/xg2anki-gui.exe (Windows)
    - dist/XG2Anki.app (macOS bundle)
"""

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['xg2anki/gui/app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('xg2anki/gui/resources', 'xg2anki/gui/resources'),
        # Include entire xg2anki package
        ('xg2anki', 'xg2anki'),
    ],
    hiddenimports=[
        # PySide6 imports
        'PySide6.QtCore',
        'PySide6.QtWidgets',
        'PySide6.QtGui',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebEngineCore',
        # xg2anki core
        'xg2anki.parsers.xg_text_parser',
        'xg2anki.parsers.gnubg_parser',
        'xg2anki.renderer.svg_board_renderer',
        'xg2anki.renderer.color_schemes',
        'xg2anki.renderer.animation_controller',
        'xg2anki.renderer.animation_helper',
        'xg2anki.anki.ankiconnect',
        'xg2anki.anki.apkg_exporter',
        'xg2anki.anki.card_generator',
        'xg2anki.anki.card_styles',
        'xg2anki.models',
        'xg2anki.settings',
        'xg2anki.utils.xgid',
        'xg2anki.utils.move_parser',
        'xg2anki.utils.gnubg_analyzer',
        # xg2anki GUI
        'xg2anki.gui',
        'xg2anki.gui.main_window',
        'xg2anki.gui.widgets',
        'xg2anki.gui.widgets.position_list',
        'xg2anki.gui.dialogs',
        'xg2anki.gui.dialogs.settings_dialog',
        'xg2anki.gui.dialogs.export_dialog',
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
    name='xg2anki-gui',
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
    icon='xg2anki/gui/resources/icon.ico',
)

# For macOS, create an app bundle
if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='XG2Anki.app',
        icon='xg2anki/gui/resources/icon.png',  # Use PNG for now, convert to .icns on macOS
        bundle_identifier='com.xg2anki.app',
        info_plist={
            'NSHighResolutionCapable': 'True',
            'LSBackgroundOnly': 'False',
            'CFBundleShortVersionString': '1.0.0',
        },
    )
