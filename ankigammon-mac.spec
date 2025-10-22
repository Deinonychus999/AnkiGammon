# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for building AnkiGammon macOS executable.

Usage:
    pyinstaller ankigammon-mac.spec

This will create:
    - dist/ankigammon (macOS executable)
    - dist/ankigammon.app (macOS application bundle - optional)
"""

block_cipher = None

a = Analysis(
    ['ankigammon/cli.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Include the entire ankigammon package
        ('ankigammon', 'ankigammon'),
    ],
    hiddenimports=[
        'ankigammon',
        'ankigammon.anki',
        'ankigammon.anki.ankiconnect',
        'ankigammon.anki.apkg_exporter',
        'ankigammon.anki.card_generator',
        'ankigammon.anki.card_styles',
        'ankigammon.parsers',
        'ankigammon.parsers.xg_text_parser',
        'ankigammon.renderer',
        'ankigammon.renderer.board_renderer',
        'ankigammon.renderer.color_schemes',
        'ankigammon.utils',
        'ankigammon.utils.xgid',
        'ankigammon.settings',
        'ankigammon.interactive',
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
    name='ankigammon',
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
#     name='ankigammon.app',
#     icon=None,
#     bundle_identifier='com.ankigammon.app',
#     info_plist={
#         'NSPrincipalClass': 'NSApplication',
#         'NSHighResolutionCapable': 'True',
#         'CFBundleShortVersionString': '0.1.0',
#     },
# )
