@echo off
REM One-click proof runner for Windows. Double-click this file.
setlocal
cd /d "%~dp0.."

where python >nul 2>nul && (set PY=python) || (set PY=py)

echo Installing required packages (first run may take a minute)...
%PY% -m pip install -r requirements.txt scipy matplotlib statsmodels

echo.
echo Running the proof...
echo.
%PY% proof\run_proof.py

echo.
echo ============================================================
echo  Done. Copy EVERYTHING above and send it back to review.
echo ============================================================
pause
