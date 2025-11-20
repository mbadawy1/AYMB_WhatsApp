@echo off
REM ============================================================
REM WhatsApp Transcriber UI Launcher
REM
REM Double-click this file to start the Streamlit UI.
REM Console window remains open to show logs for debugging.
REM ============================================================

setlocal enabledelayedexpansion

REM Get the directory where this batch file is located
set "SCRIPT_DIR=%~dp0"
set PYTHON_BIN=C:\Users\Dell\anaconda3\python.exe


REM Go to the repository root (parent of scripts/)
cd /d "%SCRIPT_DIR%.."

echo ============================================================
echo WhatsApp Transcriber UI Launcher
echo ============================================================
echo.

REM Check for virtualenv in common locations
set "PYTHON_EXE="

REM Check for custom PYTHON_BIN override first
if defined PYTHON_BIN (
    if exist "%PYTHON_BIN%" (
        set "PYTHON_EXE=%PYTHON_BIN%"
        echo Using custom Python: %PYTHON_EXE%
        goto :found_python
    ) else (
        echo WARNING: PYTHON_BIN set to "%PYTHON_BIN%" but file not found
        echo Falling back to auto-detection...
        echo.
    )
)

REM Check venv/Scripts/python.exe
if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
    echo Found virtualenv: venv
    goto :found_python
)

REM Check .venv/Scripts/python.exe
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
    echo Found virtualenv: .venv
    goto :found_python
)

REM Fall back to system Python
where python >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_EXE=python"
    echo Using system Python
    goto :found_python
)

REM No Python found
echo ERROR: Python not found!
echo.
echo Please ensure Python is installed and available in PATH,
echo or create a virtualenv in the project root.
echo.
pause
exit /b 1

:found_python

echo Working directory: %CD%
echo Python executable: %PYTHON_EXE%
echo.
echo Starting Streamlit UI...
echo Console will remain open for debugging.
echo Press Ctrl+C to stop the server.
echo ============================================================
echo.

REM Run the launcher script
%PYTHON_EXE% scripts\launcher.py

REM If we get here, the server has stopped
echo.
echo ============================================================
echo Server stopped. Press any key to close this window.
echo ============================================================
pause >nul
