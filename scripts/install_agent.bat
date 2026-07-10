@echo off
REM ============================================
REM  TandOrbit Windows 端 - 开机自启安装脚本
REM  以管理员身份运行此脚本
REM ============================================

echo ========================================
echo   TandOrbit Windows 端自启安装
echo ========================================
echo.

REM 检查管理员权限
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] 请以管理员身份运行此脚本！
    echo 右键点击 -^> 以管理员身份运行
    pause
    exit /b 1
)

REM 获取脚本所在目录
set SCRIPT_DIR=%~dp0
set AGENT_PATH=%SCRIPT_DIR%TandOrbit.exe

REM 检查程序是否存在
if not exist "%AGENT_PATH%" (
    echo [ERROR] 找不到 TandOrbit.exe
    echo 请将此脚本放在 TandOrbit.exe 同一目录下
    pause
    exit /b 1
)

echo [1/3] 创建 Windows 计划任务...

REM 删除已有的任务（如果存在）
schtasks /delete /tn "TandOrbit" /f >nul 2>&1

REM 创建开机自启任务
schtasks /create ^
    /tn "TandOrbit" ^
    /tr "\"%AGENT_PATH%\"" ^
    /sc onlogon ^
    /rl highest ^
    /f

if %errorLevel% equ 0 (
    echo [OK] 计划任务创建成功
) else (
    echo [ERROR] 计划任务创建失败
    pause
    exit /b 1
)

echo.
echo [2/3] 配置防火墙规则...

REM 添加防火墙入站规则
netsh advfirewall firewall delete rule name="TandOrbit" >nul 2>&1
netsh advfirewall firewall add rule ^
    name="TandOrbit" ^
    dir=in ^
    action=allow ^
    protocol=tcp ^
    localport=5000 ^
    program="%AGENT_PATH%" ^
    enable=yes

if %errorLevel% equ 0 (
    echo [OK] 防火墙规则添加成功
) else (
    echo [WARN] 防火墙规则添加失败，可能需要手动配置
)

echo.
echo [3/3] 启动 TandOrbit...

start "" "%AGENT_PATH%"

echo.
echo ========================================
echo   安装完成！
echo.
echo   TandOrbit 已配置为：
echo   - 开机自动启动
echo   - 监听端口 5000
echo   - 防火墙已放行
echo.
echo   Mac 端配置文件中填入此电脑的 IP：
echo   windows:
echo     host: "此电脑的IP地址"
echo     port: 5000
echo ========================================
echo.

REM 显示本机 IP
echo 本机 IP 地址：
ipconfig | findstr /i "IPv4"
echo.

pause
