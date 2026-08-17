# -*- mode: python ; coding: utf-8 -*-
"""TandOrbit PyInstaller 打包配置（Mac / Windows 通用）"""

import os
import sys

# SPECPATH 是 PyInstaller 内置变量，指向 spec 文件所在目录
# spec 在 packaging/ 下，项目根目录是上一级
ROOT = os.path.dirname(os.path.normpath(SPECPATH))

# 版本号统一从 app/updater.py 读取，避免打包版本与运行时版本不一致
sys.path.insert(0, ROOT)
from app.updater import __version__ as APP_VERSION  # noqa: E402

block_cipher = None

a = Analysis(
    [os.path.join(ROOT, 'app', 'main.py')],
    pathex=[ROOT],
    binaries=[],
    datas=[
        (os.path.join(ROOT, 'config'), 'config'),
        (os.path.join(ROOT, 'resources'), 'resources'),
    ],
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'starlette',
        'uvicorn',
        'httpx',
        # sqlite3 的 C 扩展（PyInstaller 有时漏收，缺了会报 No module named '_sqlite3'）
        'sqlite3',
        '_sqlite3',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 未使用的大模块，减小打包体积
        'tkinter',
        'unittest',
        'pydoc',
        'test',
        'PySide6.QtQml',
        'PySide6.QtQuick',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtNetworkAuth',
        'PySide6.QtMultimedia',
        'PySide6.Qt3DCore',
        'PySide6.QtCharts',
        'PySide6.QtDataVisualization',
        'PySide6.QtPdf',
        'PySide6.QtSensors',
        'PySide6.QtSerialPort',
        'PySide6.QtSql',
        'PySide6.QtTest',
        'PySide6.QtWebChannel',
        'PySide6.QtWebSockets',
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
    # Windows 图标（macOS 在下方 BUNDLE 中单独设置 icon.icns）
    icon=os.path.join(ROOT, 'resources', 'icon.ico'),
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
        icon=os.path.join(ROOT, 'resources', 'icon.icns'),
        bundle_identifier='com.tandorbit.app',
        info_plist={
            'CFBundleShortVersionString': APP_VERSION,
            'CFBundleName': 'TandOrbit',
            'NSHighResolutionCapable': True,
            'LSUIElement': True,  # 后台运行，不显示 Dock 图标
        },
    )
