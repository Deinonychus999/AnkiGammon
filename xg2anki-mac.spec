# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for building XG2Anki macOS executable.

Usage:
    pyinstaller xg2anki-mac.spec

This will create:
    - dist/xg2anki (macOS executable)
    - dist/xg2anki.app (macOS application bundle - optional)
"""

block_cipher = None

a = Analysis(
    ['xg2anki/cli.py'],
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

# Optional: Create macOS app bundle
# Uncomment the following to create a .app bundle
# app = BUNDLE(
#     exe,
#     name='xg2anki.app',
#     icon=None,
#     bundle_identifier='com.xg2anki.app',
#     info_plist={
#         'NSPrincipalClass': 'NSApplication',
#         'NSHighResolutionCapable': 'True',
#         'CFBundleShortVersionString': '0.1.0',
#     },
# )
