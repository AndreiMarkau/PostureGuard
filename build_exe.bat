@echo off
setlocal EnableDelayedExpansion

:: Keep window open on any error or exit
if "%1"=="--child" goto :main
cmd /k "%~f0" --child
exit /b

:main
cd /d "%~dp0"
set LOGFILE=%~dp0build_log.txt
echo PostureGuard Build Log > "%LOGFILE%"
echo Started: %DATE% %TIME% >> "%LOGFILE%"
echo. >> "%LOGFILE%"

:: ════════════════════════════════════════════════════════════════
echo === STEP 1: Find Python 3.10-3.12 ===
echo [STEP 1] >> "%LOGFILE%"

set PYEXE=

:: Try python from PATH
python -c "import sys;v=sys.version_info;exit(0 if v.major==3 and 10<=v.minor<=12 else 1)" >nul 2>&1
if not errorlevel 1 set PYEXE=python

:: Try python3 from PATH
if not defined PYEXE (
    python3 -c "import sys;v=sys.version_info;exit(0 if v.major==3 and 10<=v.minor<=12 else 1)" >nul 2>&1
    if not errorlevel 1 set PYEXE=python3
)

:: Try known install paths one by one
if not defined PYEXE call :try_python "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PYEXE call :try_python "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not defined PYEXE call :try_python "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
if not defined PYEXE call :try_python "C:\Python312\python.exe"
if not defined PYEXE call :try_python "C:\Python311\python.exe"
if not defined PYEXE call :try_python "C:\Python310\python.exe"
if not defined PYEXE call :try_python "%PROGRAMFILES%\Python312\python.exe"
if not defined PYEXE call :try_python "%PROGRAMFILES%\Python311\python.exe"
if not defined PYEXE call :try_python "%PROGRAMFILES%\Python310\python.exe"

if defined PYEXE goto :python_found

:: Download Python 3.12
echo   Python 3.10-3.12 not found. Downloading 3.12.9...
set PY_INSTALLER=%TEMP%\python-3.12.9-amd64.exe
set PY_URL=https://www.python.org/ftp/python/3.12.9/python-3.12.9-amd64.exe
set PY_DIR=%LOCALAPPDATA%\Programs\Python\Python312
curl -L --progress-bar -o "%PY_INSTALLER%" "%PY_URL!" 2>&1
if not exist "%PY_INSTALLER%" (
    echo   [ERROR] Download failed. Get it from https://www.python.org/downloads/
    goto :end
)
echo   Installing...
"%PY_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_doc=0
timeout /t 10 /nobreak >nul
if exist "%PY_DIR%\python.exe" (
    set PYEXE=%PY_DIR%\python.exe
    echo   [OK] Python 3.12 installed.
) else (
    echo   [ERROR] Install failed. Open a NEW cmd window and retry.
    goto :end
)

:python_found
echo   [OK] Found: !PYEXE!
echo   [OK] !PYEXE! >> "%LOGFILE%"
echo.

:: ════════════════════════════════════════════════════════════════
echo === STEP 2: Upgrade pip ===
echo [STEP 2] >> "%LOGFILE%"
"!PYEXE!" -m pip install --upgrade pip --quiet --no-warn-script-location >> "%LOGFILE%" 2>&1
echo   [OK] pip done.
echo.

:: ════════════════════════════════════════════════════════════════
echo === STEP 3: Install dependencies ===
echo   First time: 5-15 min. Do not close this window!
echo [STEP 3] >> "%LOGFILE%"
echo.
"!PYEXE!" -m pip install -r "%~dp0requirements.txt" --quiet --no-warn-script-location >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    echo   [ERROR] Dependencies failed. See: %LOGFILE%
    goto :end
)
echo   [OK] Dependencies installed.
echo.

:: ════════════════════════════════════════════════════════════════
echo === STEP 4: PyInstaller ===
echo [STEP 4] >> "%LOGFILE%"
"!PYEXE!" -m pip install pyinstaller --quiet --no-warn-script-location >> "%LOGFILE%" 2>&1
echo   [OK] PyInstaller ready.
echo.

:: ════════════════════════════════════════════════════════════════
echo === STEP 5: Alert sound ===
echo [STEP 5] >> "%LOGFILE%"
"!PYEXE!" "%~dp0generate_alert.py" >> "%LOGFILE%" 2>&1
echo   [OK] alert.wav ready.
echo.

:: ════════════════════════════════════════════════════════════════
echo === STEP 6: Kill old EXE if running ===
echo [STEP 6] >> "%LOGFILE%"
tasklist /FI "IMAGENAME eq PostureGuard.exe" 2>nul | find /I "PostureGuard.exe" >nul
if not errorlevel 1 (
    echo   Closing running PostureGuard.exe...
    taskkill /F /IM PostureGuard.exe >nul 2>&1
    timeout /t 2 /nobreak >nul
    echo   [OK] Closed.
) else (
    echo   [OK] Not running.
)
if exist "%~dp0dist\PostureGuard.exe" (
    del /F /Q "%~dp0dist\PostureGuard.exe" >nul 2>&1
    if exist "%~dp0dist\PostureGuard.exe" (
        echo   [ERROR] Cannot delete old EXE — close it manually and retry.
        goto :end
    )
    echo   [OK] Old EXE removed.
)
echo.

:: ════════════════════════════════════════════════════════════════
echo === STEP 7: Build EXE (2-5 min) ===
echo [STEP 7] >> "%LOGFILE%"
echo   Building...
echo.
"!PYEXE!" -m PyInstaller "%~dp0posture_guard.spec" --noconfirm >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    echo   [ERROR] Build failed. Last 30 lines:
    echo   ────────────────────────────────────────
    powershell -Command "Get-Content '%LOGFILE%' | Select-Object -Last 30"
    echo   ────────────────────────────────────────
    echo   Full log: %LOGFILE%
    goto :end
)

echo.
if exist "%~dp0dist\PostureGuard.exe" (
    echo   =============================================
    echo     DONE!  dist\PostureGuard.exe is ready
    echo   =============================================
    echo.
    set /p RUN="Launch now? (y/n): "
    if /i "!RUN!"=="y" start "" "%~dp0dist\PostureGuard.exe"
) else (
    echo   [ERROR] EXE not found after build. See: %LOGFILE%
)

:end
echo.
echo Press any key to close...
pause >nul
goto :eof

:: ════════════════════════════════════════════════════════════════
:try_python
if exist "%~1" (
    "%~1" -c "import sys;v=sys.version_info;exit(0 if v.major==3 and 10<=v.minor<=12 else 1)" >nul 2>&1
    if not errorlevel 1 set PYEXE=%~1
)
goto :eof
