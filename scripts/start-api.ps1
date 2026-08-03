# 启动 Web API 后端（后台运行，先停旧实例再启动，保证加载最新代码）
# 日志: logs/web-api.log（uvicorn 轮转写入）；启动期报错: logs/web-api-console.log
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$pidFile = Join-Path $logDir "web-api.pid"
$outFile = Join-Path $logDir "web-api-console.log"
$errFile = Join-Path $logDir "web-api-console.err.log"

# 1) 停止已存在的后端：按 PID 记录 + 按 8000 端口双保险
function Stop-ExistingApi {
    $pids = New-Object System.Collections.Generic.List[int]
    if (Test-Path -LiteralPath $pidFile) {
        try { $pids.Add([int]((Get-Content -LiteralPath $pidFile -Raw).Trim())) } catch { }
    }
    $conn = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
    if ($conn) { foreach ($c in $conn) { $pids.Add([int]$c.OwningProcess) } }
    foreach ($procId in ($pids | Where-Object { $_ -gt 0 -and $_ -ne $PID } | Select-Object -Unique)) {
        try {
            Stop-Process -Id $procId -Force -ErrorAction Stop
            Write-Host "已停止旧后端进程 $procId"
        } catch { }
    }
    Start-Sleep -Milliseconds 1000
}

# 2) 定位 Python：优先已知安装路径，其次 PATH 中的 python.exe / py
$python = $null
foreach ($candidate in @(
    "C:\Users\ZCY\AppData\Local\Programs\Python\Python313\python.exe",
    "C:\Python313\python.exe",
    "C:\Python312\python.exe"
)) {
    if (Test-Path -LiteralPath $candidate) { $python = $candidate; break }
}
if (-not $python) {
    foreach ($name in @("python.exe", "python", "py.exe", "py")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source -match '\.(exe|cmd|bat)$') { $python = $cmd.Source; break }
    }
}
if (-not $python) { throw "未找到 Python，请先安装并加入 PATH（推荐 Python 3.13）" }
Write-Host "使用 Python: $python"

Stop-ExistingApi

# 3) 后台启动并捕获启动期输出（失败也能看到报错）
$proc = Start-Process -FilePath $python -ArgumentList "web_api.py" `
    -WorkingDirectory $root -WindowStyle Hidden `
    -RedirectStandardOutput $outFile -RedirectStandardError $errFile -PassThru
$proc.Id | Set-Content -Path $pidFile -Encoding ascii
Write-Host "Web API 已启动 (PID $($proc.Id)) -> http://127.0.0.1:8000"

# 4) 等待并验证端口（记忆模型加载较慢，轮询最多 40 秒，每 2 秒探测一次）
$ready = $false
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Seconds 2
    $port = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
    if ($port) { $ready = $true; break }
}
if ($ready) { Write-Host "OK Web API 就绪 (PID $($port.OwningProcess))" -ForegroundColor Green }
else {
    Write-Host "[警告] 8000 端口未就绪，启动日志末尾:" -ForegroundColor Yellow
    Get-Content $errFile -Encoding UTF8 -Tail 20 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }
    Get-Content $outFile -Encoding UTF8 -Tail 10 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }
}
