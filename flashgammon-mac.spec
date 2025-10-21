# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for building FlashGammon macOS executable.

Usage:
    pyinstaller flashgammon-mac.spec

This will create:
    - dist/flashgammon (macOS executable)
    - dist/flashgammon.app (macOS application bundle - optional)
"""

block_cipher = None

a = Analysis(
    ['flashgammon/cli.py'],
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
        'flashgammon.renderer.board_renderer',
        'flashgammon.renderer.color_schemes',
        'flashgammon.utils',
        'flashgammon.utils.xgid',
        'flashgammon.settings',
        'flashgammon.interactive',
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

# Optional: Create macOS app bundle
# Uncomment the following to create a .app bundle
# app = BUNDLE(
#     exe,
#     name='flashgammon.app',
#     icon=None,
#     bundle_identifier='com.flashgammon.app',
#     info_plist={
#         'NSPrincipalClass': 'NSApplication',
#         'NSHighResolutionCapable': 'True',
#         'CFBundleShortVersionString': '0.1.0',
#     },
# )
