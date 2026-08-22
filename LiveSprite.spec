# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for LiveSprite (clean rewrite).

One-folder build. assets/ and config/ are NOT bundled inside the exe;
the build script copies them next to LiveSprite.exe so they stay
editable (add sprites, save settings) without rebuilding.

Build with:  pyinstaller LiveSprite.spec
Output:      dist/LiveSprite/LiveSprite.exe
"""

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Heavy Qt/other modules this app never uses - keeps the build small
        'PyQt5.QtWebEngineWidgets',
        'PyQt5.QtWebEngineCore',
        'PyQt5.QtWebEngine',
        'PyQt5.QtQml',
        'PyQt5.QtQuick',
        'PyQt5.QtMultimedia',
        'PyQt5.QtSql',
        'PyQt5.QtTest',
        'PyQt5.QtBluetooth',
        'PyQt5.QtDesigner',
        'PyQt5.QtLocation',
        'PyQt5.QtPositioning',
        'PyQt5.QtSensors',
        'PyQt5.QtSerialPort',
        'tkinter',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='LiveSprite',
    debug=False,
    strip=False,
    upx=False,
    console=False,   # no terminal window
    icon='soda.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='LiveSprite',
)
