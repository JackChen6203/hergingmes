$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "請先執行 00_先點我_一鍵啟動.bat 安裝環境。"
    pause
    exit 1
}

& $VenvPython -m pip install -U pyinstaller
& $VenvPython -m PyInstaller --noconfirm --onefile --windowed --name HermesHFDesktop (Join-Path $Root "hermes_hf_desktop.py")
Write-Host "EXE 已產生於：$Root\dist\HermesHFDesktop.exe"
Write-Host "注意：EXE 只包桌面工具本體；Hermes Agent 仍可在工具內安裝到 .venv。"
pause
