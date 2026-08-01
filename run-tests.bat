@echo off
REM ===================================================================
REM  CitySentinel - Run the full test suite (105 tests)
REM  LLM is force-disabled during tests for deterministic results.
REM ===================================================================
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv not found. Run setup.bat first.
    pause
    exit /b 1
)

echo.
echo ==========================================================
echo   Running test suite ...
echo ==========================================================
echo.

".venv\Scripts\python.exe" -m pytest tests -q

echo.
pause
