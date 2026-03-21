@echo off
REM PiClock3 Windows Development Setup
REM Run from the project root: scripts\install.bat

setlocal

set "PROJECT_DIR=%~dp0.."
cd /d "%PROJECT_DIR%"

echo === PiClock3 Windows Setup ===
echo.

REM Check Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.11+ from https://www.python.org
    exit /b 1
)

REM Create virtual environment
if not exist "venv" (
    echo [1/4] Creating virtual environment...
    python -m venv venv
) else (
    echo [1/4] Virtual environment already exists, skipping...
)

REM Activate and upgrade pip
echo [2/4] Upgrading pip...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip -q

REM Install dependencies
echo [3/4] Installing dependencies...
pip install -r requirements.txt -q

REM Create data directories
echo [4/4] Creating data directories...
if not exist "data\themes" mkdir "data\themes"
if not exist "data\sounds" mkdir "data\sounds"
if not exist "data\uploads" mkdir "data\uploads"

echo.
echo === Setup Complete ===
echo.
echo To run the clock:
echo   venv\Scripts\activate.bat
echo   python -m src.main
echo.
echo Web interface will be at http://localhost:8080

endlocal
