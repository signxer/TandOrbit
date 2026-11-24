@echo off
setlocal
set "APP=%~dp0TandOrbit.exe"
if not exist "%APP%" (
  echo Put this script next to TandOrbit.exe.
  exit /b 1
)
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
powershell -NoProfile -NonInteractive -Command "$link = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $env:STARTUP 'TandOrbit.lnk')); $link.TargetPath = $env:APP; $link.WorkingDirectory = Split-Path $env:APP; $link.Save()"
if errorlevel 1 exit /b 1
echo TandOrbit is registered for your next Windows sign-in.
echo If Windows Firewall prompts, allow TandOrbit on the private network you use.
