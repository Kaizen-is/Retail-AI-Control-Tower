@echo off
setlocal
cd /d "%~dp0"
title Retail AI Control Tower
if not exist ".env" copy ".env.example" ".env" >nul

rem ---- find Python (py launcher first, then python)
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY goto nopython

rem ---- first run: create environment and install packages
if exist ".venv\installed.ok" goto run
echo.
echo [1/3] Creating the Python environment - first run only ...
if not exist ".venv\Scripts\python.exe" %PY% -m venv .venv
if not exist ".venv\Scripts\python.exe" goto venvfail
echo [2/3] Installing packages - this takes 3-5 minutes, please wait ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto pipfail
echo ok> ".venv\installed.ok"

:run
echo.
echo [3/3] Starting the app ... it opens at http://localhost:8501
echo        Keep this window open while you use the app. Close it to stop the app.
start "" cmd /c "timeout /t 8 >nul & start http://localhost:8501"
".venv\Scripts\python.exe" -m streamlit run app.py --server.port 8501 --server.headless true
echo.
echo The app stopped. If you see an error above, send a screenshot of this window.
pause
exit /b

:nopython
echo.
echo Python was not found on this computer.
echo Install Python 3.10 or newer from https://www.python.org/downloads/
echo During the install, tick "Add python.exe to PATH". Then double-click run.bat again.
pause
exit /b 1

:venvfail
echo.
echo Could not create the Python environment.
echo If Windows opened the Microsoft Store, install Python from https://www.python.org/downloads/ instead
echo and tick "Add python.exe to PATH". Then delete the .venv folder and run this file again.
pause
exit /b 1

:pipfail
echo.
echo Package installation failed - check your internet connection and run this file again.
echo If it keeps failing, send a screenshot of this window.
pause
exit /b 1
