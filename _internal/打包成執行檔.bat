@echo off
chcp 65001 >nul
setlocal
set SCRIPT_DIR=%~dp0
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%04_打包成執行檔.ps1"
if errorlevel 1 pause
