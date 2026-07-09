"""py2app 打包配置"""
from setuptools import setup

setup(
    name="TandOrbit",
    version="1.0.0",
    install_requires=[],
    app=["app/gui_main.py"],
    data_files=[
        ("resources", [
            "resources/apple.svg",
            "resources/windows.svg",
            "resources/mix.svg",
            "resources/sleep.svg",
            "resources/setting.svg",
            "resources/tray_icon.png",
            "resources/tray_icon@2x.png",
            "resources/icon.icns",
            "resources/icon.ico",
        ]),
        ("config", ["config/default.yaml"]),
        (".", ["icon.png"]),
    ],
    options={
        "py2app": {
            "iconfile": "icon.icns",
            "plist": {
                "CFBundleName": "TandOrbit",
                "CFBundleDisplayName": "TandOrbit",
                "CFBundleIdentifier": "com.tandorbit.app",
                "CFBundleVersion": "1.0",
                "CFBundleShortVersionString": "1.0",
                "NSHighResolutionCapable": True,
                "LSUIElement": True,
            },
            "packages": [
                "PySide6",
                "app",
                "plugins",
            ],
            "includes": [
                "PySide6.QtSvg",
                "PySide6.QtSvgWidgets",
                "starlette",
                "uvicorn",
                "httpx",
            ],
            "excludes": ["tkinter", "matplotlib", "numpy", "scipy"],
        }
    },
)
