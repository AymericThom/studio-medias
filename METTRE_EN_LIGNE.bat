@echo off
chcp 65001 >nul
title Mise en ligne du studio sur GitHub
cd /d "%~dp0"
set "PATH=%PATH%;C:\Program Files\Git\cmd;C:\Program Files\GitHub CLI"
set PYTHONIOENCODING=utf-8

where git >nul 2>nul
if errorlevel 1 (
  echo Installation de Git ^(gratuit, officiel^)...
  winget install --id Git.Git -e
)
where gh >nul 2>nul
if errorlevel 1 (
  echo Installation de GitHub CLI ^(gratuit, officiel^)...
  winget install --id GitHub.cli -e
)

python installer_github.py
echo.
pause
