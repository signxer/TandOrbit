"""py2app 打包配置"""
from setuptools import setup

setup(
    name="TandOrbit",
    version="1.0.0",
    install_requires=[],
    app=["app/main.py"],
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
            "excludes": [
                "tkinter", "matplotlib", "numpy", "scipy", "pandas",
                "PIL", "pillow", "cv2", "opencv", "torch", "tensorflow",
                "IPython", "jupyter", "notebook", "pytest", "unittest",
                "distutils", "setuptools", "pip", "wheel", "pkg_resources",
                "pydoc", "doctest", "test", "tests",
                "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DLogic",
                "PySide6.Qt3DInput", "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
                "PySide6.QtBluetooth", "PySide6.QtCharts", "PySide6.QtDataVisualization",
                "PySide6.QtHelp", "PySide6.QtLocation", "PySide6.QtMultimedia",
                "PySide6.QtMultimediaWidgets", "PySide6.QtNfc", "PySide6.QtPositioning",
                "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtQuick",
                "PySide6.QtQuick3D", "PySide6.QtQuickWidgets", "PySide6.QtRemoteObjects",
                "PySide6.QtScxml", "PySide6.QtSensors", "PySide6.QtSerialBus",
                "PySide6.QtSerialPort", "PySide6.QtSpatialAudio", "PySide6.QtSql",
                "PySide6.QtStateMachine", "PySide6.QtTest", "PySide6.QtTextToSpeech",
                "PySide6.QtVirtualKeyboard", "PySide6.QtWebChannel",
                "PySide6.QtWebEngine", "PySide6.QtWebEngineCore",
                "PySide6.QtWebEngineWidgets", "PySide6.QtWebSockets",
                "PySide6.QtXml", "PySide6.QtDesigner", "PySide6.QtUiTools",
                "shiboken6",
            ],
        }
    },
)
