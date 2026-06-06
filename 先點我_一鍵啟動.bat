@echo off
setlocal enabledelayedexpansion
title Hermes Space Deployer Launcher

echo ==================================================
echo   Hermes Space Deployer Launcher
echo ==================================================

:: 1. Detect Python
echo [1/4] Detecting Python...
set "PYTHON_CMD="

call :detect_python

:found_python
if not defined PYTHON_CMD (
    echo Python not found. Trying to install Python 3.12 automatically...
    call :install_python
    call :detect_python
)

if not defined PYTHON_CMD (
    echo Error: Python not found and automatic install failed.
    echo Please install Python 3.11+ and check "Add Python to PATH" during installation.
    echo Download URL: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo Found Python: !PYTHON_CMD!

:: 2. Setup Virtual Environment
echo [2/4] Setting up Virtual Environment (.venv)...
set "VENV_DIR=%~dp0.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"

call :ensure_venv
if !errorlevel! neq 0 (
    pause
    exit /b 1
)

:: 3. Install Dependencies
echo [3/4] Installing / Updating Requirements...
set "REQ_FILE=%~dp0_internal\requirements-desktop.txt"
call :install_requirements
if !errorlevel! neq 0 (
    echo Existing virtual environment failed during dependency install.
    echo Recreating .venv and retrying once...
    if exist "%VENV_DIR%" rmdir /s /q "%VENV_DIR%"
    call :ensure_venv
    if !errorlevel! neq 0 (
        pause
        exit /b 1
    )
    call :install_requirements
    if !errorlevel! neq 0 (
        echo Error: Failed to install requirements.
        pause
        exit /b 1
    )
)

if /i "%HERMES_LAUNCHER_SKIP_GUI%"=="1" (
    echo HERMES_LAUNCHER_SKIP_GUI=1, skipping GUI launch.
    exit /b 0
)

:: 4. Run GUI App (using -u for unbuffered output to log file)
echo [4/4] Launching GUI App...
set "GUI_SCRIPT=%~dp0_internal\hermes_hf_desktop.py"
"!VENV_PYTHON!" -u "%GUI_SCRIPT%"
if !errorlevel! neq 0 (
    echo Error: Application crashed on exit!
    pause
    exit /b 1
)

echo Done!
pause
exit /b 0

:detect_python
set "PYTHON_CMD="
:: Check standard PATH using where to avoid Microsoft Store stub hang
for /f "tokens=*" %%I in ('where python 2^>nul') do (
    set "TEST_PATH=%%I"
    echo !TEST_PATH! | findstr /i "WindowsApps" >nul
    if !errorlevel! neq 0 (
        "!TEST_PATH!" -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
        if !errorlevel! equ 0 (
            set "PYTHON_CMD=!TEST_PATH!"
            exit /b 0
        )
    )
)

:: Check py launcher when available
for %%V in (3.12 3.13 3.11) do (
    if not defined PYTHON_CMD (
        py -%%V -c "import sys; print(sys.executable)" >nul 2>nul
        if !errorlevel! equ 0 (
            for /f "tokens=*" %%P in ('py -%%V -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON_CMD=%%P"
        )
    )
)

:: Check default Windows installer paths in a flat manner to avoid nested parenthesized GOTO bugs
if not defined PYTHON_CMD if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not defined PYTHON_CMD if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PYTHON_CMD if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not defined PYTHON_CMD if exist "C:\Python313\python.exe" set "PYTHON_CMD=C:\Python313\python.exe"
if not defined PYTHON_CMD if exist "C:\Python312\python.exe" set "PYTHON_CMD=C:\Python312\python.exe"
if not defined PYTHON_CMD if exist "C:\Python311\python.exe" set "PYTHON_CMD=C:\Python311\python.exe"
if not defined PYTHON_CMD if exist "%ProgramFiles%\Python313\python.exe" set "PYTHON_CMD=%ProgramFiles%\Python313\python.exe"
if not defined PYTHON_CMD if exist "%ProgramFiles%\Python312\python.exe" set "PYTHON_CMD=%ProgramFiles%\Python312\python.exe"
if not defined PYTHON_CMD if exist "%ProgramFiles%\Python311\python.exe" set "PYTHON_CMD=%ProgramFiles%\Python311\python.exe"
if not defined PYTHON_CMD if exist "%ProgramFiles(x86)%\Python313\python.exe" set "PYTHON_CMD=%ProgramFiles(x86)%\Python313\python.exe"
if not defined PYTHON_CMD if exist "%ProgramFiles(x86)%\Python312\python.exe" set "PYTHON_CMD=%ProgramFiles(x86)%\Python312\python.exe"
if not defined PYTHON_CMD if exist "%ProgramFiles(x86)%\Python311\python.exe" set "PYTHON_CMD=%ProgramFiles(x86)%\Python311\python.exe"
exit /b 0

:install_python
where winget >nul 2>nul
if !errorlevel! equ 0 (
    winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
    if !errorlevel! equ 0 exit /b 0
)

echo winget is unavailable or failed. Downloading Python installer directly...
set "PY_INSTALLER=%TEMP%\python-3.12.8-amd64.exe"
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe' -OutFile $env:PY_INSTALLER -UseBasicParsing; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"
if !errorlevel! neq 0 (
    echo Error: Failed to download Python installer.
    exit /b 1
)

"%PY_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_launcher=1
if !errorlevel! neq 0 (
    echo Error: Python installer failed.
    exit /b 1
)
exit /b 0

:ensure_venv
if exist "%VENV_DIR%" (
    if exist "%VENV_DIR%\pyvenv.cfg" (
        for /f "tokens=1,* delims==" %%A in ('findstr /b /i "home = executable =" "%VENV_DIR%\pyvenv.cfg" 2^>nul') do (
            set "CFG_VALUE=%%B"
            set "CFG_VALUE=!CFG_VALUE:~1!"
            if not exist "!CFG_VALUE!" (
                echo Existing virtual environment points to missing Python: !CFG_VALUE!
                echo Recreating .venv with detected Python...
                rmdir /s /q "%VENV_DIR%"
                goto :create_venv
            )
        )
    )
    "!VENV_PYTHON!" -c "import sys; print(sys.executable)" >nul 2>nul
    if !errorlevel! neq 0 (
        echo Existing virtual environment is not usable on this machine.
        echo Recreating .venv with detected Python...
        rmdir /s /q "%VENV_DIR%"
    ) else (
        "!VENV_PYTHON!" -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
        if !errorlevel! neq 0 (
            echo Existing virtual environment uses Python older than 3.11.
            echo Hermes Agent requires Python 3.11 or newer. Recreating .venv...
            rmdir /s /q "%VENV_DIR%"
        )
    )
)

:create_venv
if not exist "%VENV_DIR%" (
    echo Creating virtual environment...
    "!PYTHON_CMD!" -m venv "%VENV_DIR%"
    if !errorlevel! neq 0 (
        echo Error: Failed to create virtual environment.
        exit /b 1
    )
)
exit /b 0

:install_requirements
"!VENV_PYTHON!" -m pip install --upgrade pip
if !errorlevel! neq 0 exit /b 1
"!VENV_PYTHON!" -m pip install -r "%REQ_FILE%"
exit /b !errorlevel!
