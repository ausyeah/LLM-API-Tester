@echo off
setlocal
rem Build the single-file application (with gauge icon) into dist\LLM-API-Tester.exe
cd /d "%~dp0"
python tools\make_icon.py
python -m PyInstaller --noconfirm --clean --onefile --windowed --name LLM-API-Tester --icon assets\app.ico --add-data "assets\app.ico;assets" main.py
if errorlevel 1 goto :build_failed
if not exist "%~dp0dist\LLM-API-Tester.exe" goto :output_missing
echo.
echo Build complete: %~dp0dist\LLM-API-Tester.exe
for %%F in ("%~dp0dist\LLM-API-Tester.exe") do echo Updated: %%~tF, size: %%~zF bytes
pause
exit /b 0

:build_failed
echo.
echo Build failed. Check the messages above.
pause
exit /b 1

:output_missing
echo.
echo Build failed: dist\LLM-API-Tester.exe was not generated.
pause
exit /b 1
