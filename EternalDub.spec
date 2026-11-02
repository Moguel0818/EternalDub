# -*- mode: python ; coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# EternalDub.spec - receita do PyInstaller para gerar o EternalDub como programa (sem precisar de Python).
#
#   Uma pasta com o EternalDub.exe (padrao: abre mais rapido) ... pyinstaller EternalDub.spec --noconfirm --clean
#   Um unico EternalDub.exe .................................... set ETERNALDUB_UM_ARQUIVO=1   e o mesmo comando
#
# No Windows basta dar dois cliques em Gerar_EXE.bat. O FFmpeg NAO vai junto: o programa o procura ao lado do
# EternalDub.exe (ffmpeg.exe e ffprobe.exe), no PATH e nas pastas onde o winget o instala.
import os
import sys

UM_ARQUIVO = os.environ.get("ETERNALDUB_UM_ARQUIVO", "0") == "1"
ICONE = "EternalDub.ico" if sys.platform == "win32" else None

# Partes do Qt que o EternalDub nao usa (deixam o programa muito maior sem servir para nada)
QT_QUE_NAO_USA = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
    "PySide6.QtWebSockets", "PySide6.QtWebView", "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic", "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
    "PySide6.QtQuickControls2", "PySide6.QtQml", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtGraphs", "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtSql", "PySide6.QtTest",
    "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtDesigner",
    "PySide6.QtHelp", "PySide6.QtLocation", "PySide6.QtPositioning", "PySide6.QtRemoteObjects",
    "PySide6.QtScxml", "PySide6.QtSpatialAudio", "PySide6.QtTextToSpeech", "PySide6.QtVirtualKeyboard",
    "PySide6.QtHttpServer", "PySide6.QtStateMachine", "PySide6.QtUiTools", "PySide6.QtXml",
]

a = Analysis(
    ["EternalDub_gui.py"],
    pathex=["."],
    binaries=[],
    datas=[("idiomas", "idiomas"), ("icone.png", "."), ("LICENSE", "."), ("README.md", "."),
           ("README.pt-BR.md", "."), ("CREDITS.md", "."), ("CHANGELOG.md", ".")],
    hiddenimports=["EternalDub_core", "EternalDub_emendas", "EternalDub_audio", "EternalDub_i18n", "detectar_atraso"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "pandas", "IPython", "pytest", "PIL"] + QT_QUE_NAO_USA,
    noarchive=False,
)
pyz = PYZ(a.pure)

if UM_ARQUIVO:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="EternalDub", debug=False, strip=False, upx=False,
              runtime_tmpdir=None, console=False, icon=ICONE)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="EternalDub", debug=False, strip=False, upx=False,
              console=False, icon=ICONE)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="EternalDub")
