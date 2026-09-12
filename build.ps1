Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
pip install pyinstaller
pyinstaller --onefile --name GMailCtrlCli --console gmail_ctrl/cli.py
Write-Host "Build complete: dist\GMailCtrlCli.exe" -ForegroundColor Green
