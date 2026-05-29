@echo off
setlocal EnableDelayedExpansion
title PostureGuard — Build Installer

:: Keep window open on error
if "%1"=="--child" goto :main
cmd /k "%~f0" --child
exit /b

:main
cd /d "%~dp0"

echo.
echo  PostureGuard — Build Installer
echo  ================================
echo.

:: ── Проверить, что dist\PostureGuard.exe существует ──────────────────────
if not exist "..\dist\PostureGuard.exe" (
    echo  [ERROR] dist\PostureGuard.exe not found!
    echo          Run build_exe.bat first to build the application.
    echo.
    goto :end
)
echo  [OK] dist\PostureGuard.exe found.
echo.

:: ── Найти Inno Setup Compiler ────────────────────────────────────────────
set ISCC=
if exist "%PROGRAMFILES(X86)%\Inno Setup 7\ISCC.exe" set ISCC=%PROGRAMFILES(X86)%\Inno Setup 7\ISCC.exe
if exist "%PROGRAMFILES%\Inno Setup 7\ISCC.exe"      set ISCC=%PROGRAMFILES%\Inno Setup 7\ISCC.exe
if exist "%PROGRAMFILES%\Inno Setup 7 (x64)\ISCC.exe" set ISCC=%PROGRAMFILES%\Inno Setup 7 (x64)\ISCC.exe

if not defined ISCC (
    echo  [ERROR] Inno Setup 7 not found!
    echo.
    echo          Download and install it from:
    echo          https://jrsoftware.org/isdl.php
    echo.
    set /p OPEN="Open download page in browser? (y/n): "
    if /i "!OPEN!"=="y" start "" "https://jrsoftware.org/isdl.php"
    goto :end
)

echo  [OK] Inno Setup found: %ISCC%
echo.
echo  Building installer...
echo.

:: ── Собрать установщик ───────────────────────────────────────────────────
"!ISCC!" "%~dp0PostureGuard_Setup.iss"

if errorlevel 1 (
    echo.
    echo  [ERROR] Build failed. Check the output above for details.
) else (
    echo.
    echo  ============================================================
    echo    DONE!  installer\Output\PostureGuard_Setup_1.0.0.exe
    echo  ============================================================
    echo.
    set /p RUN="Run the installer now? (y/n): "
    if /i "!RUN!"=="y" start "" "%~dp0Output\PostureGuard_Setup_1.0.0.exe"
)

:end
echo.
echo  Press any key to close...
pause >nul
