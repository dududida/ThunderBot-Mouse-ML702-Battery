@echo off
cd /d "%~dp0"
set PY=C:\Users\Ky\AppData\Local\Python\bin\python.exe
"%PY%" -m PyInstaller --noconfirm --clean --onefile --windowed --name ML702Battery ^
  --distpath bin ^
  --workpath build ^
  --hidden-import=pystray._win32 ^
  --hidden-import=pystray._util.win32 ^
  --collect-all hidapi ^
  --collect-all hid ^
  tray_app.py
if errorlevel 1 exit /b 1
echo.
echo Built: "%~dp0bin\ML702Battery.exe"
