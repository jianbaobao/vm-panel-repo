# VM Panel — Windows 开发版安装脚本
# 用法: powershell -ExecutionPolicy Bypass -File install.ps1

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " VM Panel — Windows 版安装" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 1. 检查 Python
try {
    $py = Get-Command python -ErrorAction Stop
    $ver = & python --version
    Write-Host "[1/3] ✅ Python: $ver" -ForegroundColor Green
} catch {
    Write-Host "[!] 请先安装 Python 3.8+: https://python.org" -ForegroundColor Red
    exit 1
}

# 2. 安装 Flask
Write-Host "[2/3] 安装依赖..." -ForegroundColor Yellow
& python -m pip install flask -q
if ($LASTEXITCODE -eq 0) {
    Write-Host "      ✅ Flask 安装成功" -ForegroundColor Green
} else {
    Write-Host "      ⚠️  pip 安装失败，尝试手动安装: pip install flask" -ForegroundColor Red
}

# 3. 创建快捷方式
Write-Host "[3/3] 创建快捷方式..." -ForegroundColor Yellow
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Resolve-Path "$scriptPath\..\.."
$shortcutPath = "$env:USERPROFILE\Desktop\VM Panel.lnk"

$wshell = New-Object -ComObject WScript.Shell
$shortcut = $wshell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "$env:windir\system32\cmd.exe"
$shortcut.Arguments = "/c cd /d `"$projectRoot`" && deploy\windows\run.bat"
$shortcut.WorkingDirectory = $projectRoot
$shortcut.Description = "VM Management Panel - Windows Edition"
$shortcut.Save()

Write-Host "      ✅ 桌面快捷方式已创建" -ForegroundColor Green

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " ✅ VM Panel Windows 版安装完成!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  启动方式:" -ForegroundColor White
Write-Host "    1. 双击桌面 [VM Panel] 快捷方式" -ForegroundColor White
Write-Host "    2. 或运行: deploy\windows\run.bat" -ForegroundColor White
Write-Host "  访问地址: http://localhost:5000" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan
