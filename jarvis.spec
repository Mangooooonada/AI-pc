# PyInstaller build spec — produces dist/JARVIS/JARVIS.exe
#
#   .venv\Scripts\python.exe -m PyInstaller jarvis.spec --noconfirm --clean
#
# Ships as a one-folder build: faster startup than one-file and the web assets
# stay readable on disk.
from pathlib import Path

block_cipher = None
ROOT = Path(SPECPATH)

datas = [
    (str(ROOT / "jarvis" / "web"), "jarvis/web"),
    (str(ROOT / "assets"), "assets"),
]
if (ROOT / ".env.example").exists():
    datas.append((str(ROOT / ".env.example"), "."))

hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "jarvis.skills.system",
    "jarvis.skills.apps",
    "jarvis.skills.media",
    "jarvis.skills.files",
    "jarvis.skills.web",
    "jarvis.skills.knowledge",
    "jarvis.skills.agenda",
    "webview.platforms.edgechromium",
    "clr_loader",
    "pythonnet",
    "pyttsx3.drivers",
    "pyttsx3.drivers.sapi5",
    "comtypes",
    "psutil",
]

a = Analysis(
    ["main.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "playwright", "pytest"],
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
    name="JARVIS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,                     # no console window — it's a real app
    disable_windowed_traceback=False,
    icon=str(ROOT / "assets" / "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="JARVIS",
)
