@echo off
REM ===================================================================
REM  CitySentinel - Run the backend and frontend test suites.
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
if errorlevel 1 exit /b 1

if not exist "frontend\node_modules\.bin\vitest.cmd" (
    echo [ERROR] Frontend dependencies not found. Run setup.bat first.
    exit /b 1
)

pushd frontend
call npm test
set "FRONTEND_TEST_EXIT=%ERRORLEVEL%"
popd
if not "%FRONTEND_TEST_EXIT%"=="0" exit /b %FRONTEND_TEST_EXIT%

echo.
echo ==========================================================
echo   All backend and frontend tests passed.
echo ==========================================================

echo.
pause
