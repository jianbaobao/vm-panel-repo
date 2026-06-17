@echo off
chcp 65001 >nul
title VM Panel — Windows Edition
cd /d "%~dp0"

echo ========================================
echo    VM Panel — Windows ^(便携版^)
echo ========================================
echo.

REM 检查 Python
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [^!^] 未检测到 Python，正在尝试安装...
    echo      请从 https://www.python.org/downloads/ 下载 Python 3.8+
    echo      安装时勾选 "Add Python to PATH"
    pause
    exit /b 1
)

REM 检查 Flask
python -c "import flask" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [*] 正在安装 Flask...
    python -m pip install flask -q
    if %ERRORLEVEL% NEQ 0 (
        echo [^!^] Flask 安装失败，请手动运行: pip install flask
        pause
        exit /b 1
    )
    echo [v] Flask 安装成功
)

echo [*] 启动 VM Panel...
echo.
echo     访问地址: http://localhost:5000
echo     按 Ctrl+C 停止服务
echo.

set VM_PANEL_PORT=5000
set VM_PANEL_DEBUG=false
set VM_PANEL_HOST=127.0.0.1
set SIMULATE_LIBVIRT=true

python deploy\run.py

pause
