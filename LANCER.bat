@echo off
chcp 65001 >nul
title Studio Medias
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo  Python n'est pas installe. Installe-le depuis https://www.python.org/downloads/
  echo  ^(coche "Add python.exe to PATH" pendant l'installation^), puis relance ce fichier.
  echo.
  pause
  exit /b
)
echo  Verification des composants...
python -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 ( echo  L'installation a echoue. & pause & exit /b )
if not exist data mkdir data
rem Navigateur pour lire les sites qui bloquent les robots : Chrome ou Edge suffisent, sinon on installe Chromium
if not exist data\.navigateur (
  if not exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" if not exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" python -m playwright install chromium
  echo ok> data\.navigateur
)
python app.py
pause
