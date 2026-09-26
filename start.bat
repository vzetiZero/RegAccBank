@echo off
REM ============================================
REM RegAcc - Start Application
REM ============================================

echo.
echo ============================================
echo   RegAcc - Khoi dong ung dung
echo ============================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [LOI] Python chua duoc cai dat!
    echo Vui long chay install.bat truoc.
    pause
    exit /b 1
)

REM Check virtual environment
if not exist ".venv" (
    echo [CANH BAO] Virtual environment chua ton tai.
    echo Dang tao va cai dat tu dong...
    call install.bat
    if errorlevel 1 (
        pause
        exit /b 1
    )
)

REM Activate and run
echo [INFO] Dang khoi dung RegAcc...
call .venv\Scripts\activate.bat

echo [INFO] Khoi dong GPM Login API Client...
echo [INFO] Dam bao GPM Login dang chay tai http://localhost:9495
echo.

python main.py

if errorlevel 1 (
    echo.
    echo [LOI] Ung dung gap loi!
    pause
    exit /b 1
)

pause
