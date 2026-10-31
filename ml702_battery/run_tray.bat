@echo off
cd /d "%~dp0"
if exist "%~dp0bin\ML702Battery.exe" (
  start "" "%~dp0bin\ML702Battery.exe"
) else (
  "C:\Users\Ky\AppData\Local\Python\bin\python.exe" tray_app.py
)
