# PyInstaller spec for packaging audio-sync on Windows.
# Produces a self-contained directory build; Python is not required on target machines.
# Run:  .venv\Scripts\pyinstaller audio_sync.spec

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# imageio_ffmpeg ships its own FFmpeg binary — must be included as data.
datas = collect_data_files("imageio_ffmpeg")

# librosa ships sample data / config files.
datas += collect_data_files("librosa")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # librosa loads backends via importlib at runtime
        "librosa",
        "librosa.core",
        "librosa.feature",
        "librosa.onset",
        "librosa.util",
        "audioread",
        "soundfile",
        "scipy.signal",
        "scipy.fft",
        "scipy._lib.messagestream",
        "numpy",
        # PySide6 multimedia — imported at runtime by Qt plugin loader
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Not needed at runtime — saves ~200 MB
        "matplotlib",
        "IPython",
        "jupyter",
        "notebook",
        "tkinter",
        "PySide6.QtWebEngine",
        "PySide6.QtWebEngineWidgets",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DRender",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="audio-sync",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="audio-sync",
)
