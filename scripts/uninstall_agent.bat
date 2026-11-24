@echo off
setlocal
set "LINK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\TandOrbit.lnk"
if exist "%LINK%" del "%LINK%"
if errorlevel 1 exit /b 1
echo Removed TandOrbit from startup for this Windows account.
