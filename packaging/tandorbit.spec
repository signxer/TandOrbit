# -*- mode: python ; coding: utf-8 -*-
"""TandOrbit PyInstaller 打包配置（Mac / Windows 通用）"""

import sys
from pathlib import Path

# spec 在 packaging/ 下，项目根目录是上一级
ROOT = Path(__file__).resolve().parent.parent

block_cipher = None

a = Analysis(
    [str(ROOT / 'app' / 'main.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / 'config'), 'config'),
        (str(ROOT / 'resources'), 'resources'),
        (str(ROOT / 'resources' / 'icon.png'), '.'),
    ],
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'starlette',
        'uvicorn',
        'httpx',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TandOrbit',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TandOrbit',
)

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='TandOrbit.app',
        icon=str(ROOT / 'resources' / 'icon.icns'),
        bundle_identifier='com.tandorbit.app',
        info_plist={
            'CFBundleShortVersionString': '1.1.1',
            'CFBundleName': 'TandOrbit',
            'NSHighResolutionCapable': True,
            'LSUIElement': True,  # 后台运行，不显示 Dock 图标
        },
    )
