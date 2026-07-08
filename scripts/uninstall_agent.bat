@echo off
REM ============================================
REM  TandOrbit Windows Agent - 卸载脚本
REM  以管理员身份运行此脚本
REM ============================================

echo ========================================
echo   TandOrbit Windows Agent 卸载
echo ========================================
echo.

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] 请以管理员身份运行此脚本！
    pause
    exit /b 1
)

echo [1/3] 停止 Agent 进程...
taskkill /IM TandOrbitAgent.exe /F >nul 2>&1
echo [OK]

echo [2/3] 删除计划任务...
schtasks /delete /tn "TandOrbitAgent" /f >nul 2>&1
echo [OK]

echo [3/3] 删除防火墙规则...
netsh advfirewall firewall delete rule name="TandOrbit Agent" >nul 2>&1
echo [OK]

echo.
echo ========================================
echo   卸载完成！
echo ========================================
pause
