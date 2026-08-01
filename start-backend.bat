@echo off
REM ===================================================================
REM  CitySentinel - Start backend API server
REM  Uses .venv explicitly, so it never picks up the wrong Python.
REM  Usage:  start-backend.bat  [port]     (default 8000)
REM ===================================================================
setlocal
cd /d "%~dp0"

set "PORT=%~1"
if "%PORT%"=="" set "PORT=8000"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv not found. Run setup.bat first.
    pause
    exit /b 1
)

REM ---- Warn if the port is already taken by another process ----
netstat -ano | findstr /R /C:"LISTENING" | findstr /C:":%PORT% " >nul 2>&1
if not errorlevel 1 (
    echo.
    echo ==========================================================
    echo   [WARNING] Port %PORT% is already in use.
    echo ==========================================================
    echo   Something else is listening on %PORT%. If you start now
    echo   it will fail, or the dashboard may talk to the WRONG app.
    echo.
    echo   Who is using it:
    for /f "tokens=5" %%A in ('netstat -ano ^| findstr /C:":%PORT% " ^| findstr /C:"LISTENING"') do (
        for /f "tokens=1,*" %%B in ('tasklist /fi "PID eq %%A" /nh 2^>nul') do echo     PID %%A  -  %%B
    )
    echo.
    echo   Options:
    echo     1^) Stop that process, then re-run this script
    echo     2^) Use another port:   start-backend.bat 8010
    echo        ^(then update frontend/vite.config.ts proxy target^)
    echo.
    pause
    exit /b 1
)

echo.
echo ==========================================================
echo   CitySentinel API  ^|  http://localhost:%PORT%
echo   Docs: http://localhost:%PORT%/docs
echo   Press Ctrl+C to stop.
echo ==========================================================
echo.

cd backend
"..\.venv\Scripts\python.exe" -m uvicorn app.api.main:app --reload --port %PORT%
