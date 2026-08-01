@echo off
REM ===================================================================
REM  CitySentinel - Start frontend dashboard (Vite dev server)
REM  Backend must be running on port 8000 (see start-backend.bat).
REM ===================================================================
setlocal
cd /d "%~dp0"

where npm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm not found. Install Node.js 18+ from https://nodejs.org/
    pause
    exit /b 1
)

if not exist "frontend\node_modules" (
    echo [INFO] node_modules missing - installing dependencies first ...
    pushd frontend
    call npm install
    popd
)

echo.
echo ==========================================================
echo   CitySentinel Dashboard  ^|  http://localhost:5173
echo   ^(API calls are proxied to http://localhost:8000^)
echo   Press Ctrl+C to stop.
echo ==========================================================
echo.

cd frontend
call npm run dev
