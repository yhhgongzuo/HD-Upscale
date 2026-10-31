@echo off
setlocal
set "PYTHONNOUSERSITE=1"
set "PYTHONDONTWRITEBYTECODE=1"
"%~dp0assets\legacy-doubao\assets\art-fixed-enhance-win64\runtime\python.exe" "%~dp0scripts\bootstrap.py" %*
exit /b %errorlevel%
