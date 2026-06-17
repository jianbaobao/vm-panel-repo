@echo off
rem VM Panel — Windows 版快速启动
rem 用法: run.bat [--port PORT] [--debug]

set PORT=5000
set DEBUG=false

if "%1"=="--port" set PORT=%2
if "%1"=="--debug" set DEBUG=true
if "%1"=="-d" set DEBUG=true

cd /d "%~dp0..\.."

echo === VM Panel Windows Edition ===
echo Port: %PORT%  Debug: %DEBUG%
echo.

set VM_PANEL_PORT=%PORT%
set VM_PANEL_DEBUG=%DEBUG%
set VM_PANEL_HOST=127.0.0.1
set SIMULATE_LIBVIRT=true

python deploy\run.py

pause
