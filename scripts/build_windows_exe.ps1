$ErrorActionPreference = "Stop"

Write-Host "Building audio-sync Windows package with PyInstaller..."
python -m PyInstaller --noconfirm --clean audio_sync.spec

Write-Host "Build complete. Output folder: dist/audio-sync"
