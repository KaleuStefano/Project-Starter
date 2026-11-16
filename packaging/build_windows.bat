@echo off
REM Build ProjectStarter.exe on Windows. Run from the project root: packaging\build_windows.bat
setlocal
cd /d "%~dp0\.."
if not exist .venv (
    python -m venv .venv || goto :fail
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip pyinstaller pytest >nul || goto :fail
python -m pytest -q || goto :fail
pyinstaller packaging\oneclick.spec --noconfirm || goto :fail
echo.
echo Done: dist\ProjectStarter.exe
exit /b 0
:fail
echo Build failed.
exit /b 1
