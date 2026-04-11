$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "Creating .venv with Python 3.11..."
& py -3.11 -m venv .venv

Write-Host "Upgrading pip..."
& .\.venv\Scripts\python.exe -m pip install --upgrade pip

Write-Host "Installing requirements..."
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt

Write-Host "Launching audio-sync..."
& .\.venv\Scripts\python.exe main.py
