@echo off
REM ===================================================================
REM  CitySentinel - One-time setup for new team members
REM  Creates .venv, installs backend deps, installs frontend deps.
REM  Safe to re-run.
REM ===================================================================
setlocal
cd /d "%~dp0"

echo.
echo ==========================================================
echo   CitySentinel Setup
echo ==========================================================
echo.

REM ---- 1. Locate a usable Python ----
REM Prefer 3.11/3.12 (the versions this project is validated against).
REM Very new releases (3.13+) may lack prebuilt wheels for some deps.
set "PY="
for %%V in (3.11 3.12 3.10) do (
    if not defined PY (
        py -%%V -c "import sys" >nul 2>&1
        if not errorlevel 1 set "PY=py -%%V"
    )
)

REM Fallback: any Python 3.10+ on PATH
if not defined PY (
    for %%P in (python python3 py) do (
        if not defined PY (
            %%P -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1
            if not errorlevel 1 set "PY=%%P"
        )
    )
    if defined PY (
        echo [NOTE] Preferred Python 3.11/3.12 not found; using the version below.
        echo        If dependency installation fails, install Python 3.11 and re-run.
    )
)

if not defined PY (
    echo [ERROR] No Python 3.10+ found on PATH.
    echo         Install Python 3.11 from https://www.python.org/downloads/
    echo         IMPORTANT: tick "Add Python to PATH" during install.
    pause
    exit /b 1
)

echo [1/3] Using Python:
%PY% --version

REM ---- 2. Create venv + install backend deps ----
if not exist ".venv\Scripts\python.exe" (
    echo [2/3] Creating virtual environment .venv ...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create venv.
        pause
        exit /b 1
    )
) else (
    echo [2/3] .venv already exists - reusing it.
)

echo       Installing backend dependencies ...
".venv\Scripts\python.exe" -m pip install --upgrade pip -q
".venv\Scripts\python.exe" -m pip install -r backend\requirements.txt -q
if errorlevel 1 (
    echo [ERROR] Backend dependency install failed.
    pause
    exit /b 1
)

REM ---- 3. Frontend deps ----
echo [3/3] Installing frontend dependencies ...
where npm >nul 2>&1
if errorlevel 1 (
    echo [WARN] npm not found. Install Node.js 18+ from https://nodejs.org/
    echo        Backend is ready; frontend install skipped.
) else (
    pushd frontend
    call npm install --silent
    popd
)

echo.
echo ==========================================================
echo   Setup complete.
echo.
echo   Next steps:
echo     start-backend.bat     - run API server  (port 8000)
echo     start-frontend.bat    - run dashboard   (port 5173)
echo     run-tests.bat         - run 105 tests
echo.
echo   Optional: copy .env.example to .env and add an LLM key.
echo   Without a key the system still runs using deterministic
echo   templates - every feature remains demonstrable.
echo ==========================================================
echo.
pause
