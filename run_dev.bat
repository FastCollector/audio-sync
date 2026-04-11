@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment not found.
  echo Run this first:
  echo powershell -ExecutionPolicy Bypass -File scripts\setup_windows_dev.ps1
  exit /b 1
)

.\.venv\Scripts\python.exe main.py
