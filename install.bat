@echo off
REM ============================================
REM RegAcc - Auto Install Dependencies
REM ============================================

echo.
echo ============================================
echo   RegAcc - Cai dat tu dong
echo ============================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [LOI] Python chua duoc cai dat hoac khong co trong PATH!
    echo Vui long cai dat Python 3.10+ tu https://python.org
    pause
    exit /b 1
)

echo [OK] Python da duoc cai dat
python --version
echo.

REM Create virtual environment
if not exist ".venv" (
    echo [INFO] Dang tao virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [LOI] Khong the tao virtual environment!
        pause
        exit /b 1
    )
    echo [OK] Da tao virtual environment
) else (
    echo [INFO] Virtual environment da ton tai
)
echo.

REM Activate and install dependencies
echo [INFO] Dang cai dat thu vien...
call .venv\Scripts\activate.bat

python -m pip install --upgrade pip
pip install -r requirements.txt

if errorlevel 1 (
    echo [LOI] Cai dat that bai!
    pause
    exit /b 1
)

echo.
echo ============================================
echo [OK] Cai dat hoan tat!
echo ============================================
echo.
echo Nhan phim bat ky de thoat...
pause
