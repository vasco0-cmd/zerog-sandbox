@echo off
setlocal
echo ==============================================================
echo        Starting ZeroG-Sandbox Local Interactive Demo          
echo ==============================================================
echo.

set PYTHONPATH=%~dp0
set PYTHONDONTWRITEBYTECODE=1

where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo [ZeroG] Launching Web UI with 'py'...
    py -m zerog_sandbox.cli ui --repo "%~dp0examples\sample_repo" --port 8484
    goto end
)

where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo [ZeroG] Launching Web UI with 'python'...
    python -m zerog_sandbox.cli ui --repo "%~dp0examples\sample_repo" --port 8484
    goto end
)

echo [ERROR] Neither 'py' nor 'python' was found in your PATH.
echo Please install Python 3.9+ from https://python.org
pause

:end
endlocal
