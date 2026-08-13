# -*- mode: python ; coding: utf-8 -*-
"""
Optimized Production PyInstaller Spec Configuration for TinySA Ultra Spectrum Analyzer.
Windowed GUI mode (no console window pop-up on launch).
"""

import sys
import os

block_cipher = None

datas = [('resources', 'resources')]
hiddenimports = [
    'serial',
    'serial.tools',
    'serial.tools.list_ports',
    'numpy',
    'PIL',
    'PIL.Image',
    'PySide6',
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'pyqtgraph',
]

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'scipy', 'setuptools', 'pkg_resources', 'jaraco',
        'torch', 'torchvision', 'torchaudio',
        'tensorflow', 'tensorboard',
        'tkinter', 'unittest', 'IPython',
        'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.QtQuick', 'PySide6.QtQml'
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
    name='TinySA_Ultra_Suite',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Windowed GUI app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='resources/icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TinySA_Ultra_Suite',
)
