# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for building FlashGammon executable.

Usage:
    pyinstaller flashgammon.spec

This will create:
    - dist/flashgammon.exe (Windows)
    - dist/flashgammon (Mac/Linux)
"""

block_cipher = None

a = Analysis(
    ['flashgammon\\cli.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Include the entire flashgammon package
        ('flashgammon', 'flashgammon'),
    ],
    hiddenimports=[
        'flashgammon',
        'flashgammon.anki',
        'flashgammon.anki.ankiconnect',
        'flashgammon.anki.apkg_exporter',
        'flashgammon.anki.card_generator',
        'flashgammon.anki.card_styles',
        'flashgammon.parsers',
        'flashgammon.parsers.xg_text_parser',
        'flashgammon.renderer',
        'flashgammon.renderer.svg_board_renderer',
        'flashgammon.renderer.animation_controller',
        'flashgammon.renderer.animation_helper',
        'flashgammon.renderer.color_schemes',
        'flashgammon.utils',
        'flashgammon.utils.xgid',
        'flashgammon.settings',
        'flashgammon.interactive',
        'flashgammon.models',
        # External dependencies
        'click',
        'PIL',
        'PIL._imaging',
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
        'pandas',
        'scipy',
        'IPython',
        'jupyter',
        'numpy',
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
    name='flashgammon',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
