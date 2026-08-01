# 一键启动 Web API + 前端（任一失败不阻塞另一个）
$ErrorActionPreference = "Continue"
try { & (Join-Path $PSScriptRoot "start-api.ps1") }
catch { Write-Host "[警告] Web API 启动失败: $($_.Exception.Message)" -ForegroundColor Yellow }
try { & (Join-Path $PSScriptRoot "start-web.ps1") }
catch { Write-Host "[警告] 前端启动失败: $($_.Exception.Message)" -ForegroundColor Yellow }
Write-Host ""
Write-Host "正在打开浏览器..."
Start-Process "http://localhost:3000"