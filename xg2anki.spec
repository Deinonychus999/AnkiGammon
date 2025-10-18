# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for building XG2Anki executable.

Usage:
    pyinstaller xg2anki.spec

This will create:
    - dist/xg2anki.exe (Windows)
    - dist/xg2anki (Mac/Linux)
"""

block_cipher = None

a = Analysis(
    ['xg2anki\\cli.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Include the entire xg2anki package
        ('xg2anki', 'xg2anki'),
    ],
    hiddenimports=[
        'xg2anki',
        'xg2anki.anki',
        'xg2anki.anki.ankiconnect',
        'xg2anki.anki.apkg_exporter',
        'xg2anki.anki.card_generator',
        'xg2anki.anki.card_styles',
        'xg2anki.parsers',
        'xg2anki.parsers.xg_text_parser',
        'xg2anki.renderer',
        'xg2anki.renderer.board_renderer',
        'xg2anki.renderer.color_schemes',
        'xg2anki.utils',
        'xg2anki.utils.xgid',
        'xg2anki.settings',
        'xg2anki.interactive',
        # External dependencies
        'click',
        'PIL',
        'PIL._imaging',
        'genanki',
        'requests',
        'bs4',
        'lxml',
        'numpy',
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
    name='xg2anki',
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
