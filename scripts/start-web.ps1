# 启动 Next.js Web 控制台前端（后台运行，先停旧实例再启动）
# 日志: logs/next-dev.log（标准输出）；logs/next-dev-err.log（错误输出）
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$console = Join-Path $root "personal-assistant-agent-web-console"
$logDir = Join-Path $root "logs"
$pidFile = Join-Path $logDir "next-dev.pid"
$outFile = Join-Path $logDir "next-dev.log"
$errFile = Join-Path $logDir "next-dev-err.log"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

if (-not (Test-Path -LiteralPath (Join-Path $console "node_modules"))) {
    throw "未找到 node_modules，请先在 $console 下执行 npm install"
}

# 1) 停止已存在的前端：按 PID 记录 + 按 3000 端口双保险
function Stop-ExistingWeb {
    $pids = New-Object System.Collections.Generic.List[int]
    if (Test-Path -LiteralPath $pidFile) {
        try { $pids.Add([int]((Get-Content -LiteralPath $pidFile -Raw).Trim())) } catch { }
    }
    $conn = Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue
    if ($conn) { foreach ($c in $conn) { $pids.Add([int]$c.OwningProcess) } }
    foreach ($procId in ($pids | Where-Object { $_ -gt 0 -and $_ -ne $PID } | Select-Object -Unique)) {
        try {
            & taskkill /PID $procId /T /F 2>$null | Out-Null
            Write-Host "已停止旧前端进程 $procId"
        } catch { }
    }
    Start-Sleep -Milliseconds 1000
}

# 2) 定位包管理器：优先真实 npm，其次 PATH，最后退回内置 pnpm
$pm = $null
foreach ($candidate in @("C:\Program Files\nodejs\npm.cmd")) {
    if (Test-Path -LiteralPath $candidate) { $pm = $candidate; break }
}
if (-not $pm) {
    foreach ($name in @("npm.cmd", "npm.exe", "npm", "pnpm.cmd", "pnpm.exe", "pnpm")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source -match '\.(exe|cmd|bat)$') { $pm = $cmd.Source; break }
    }
}
if (-not $pm) { throw "未找到 npm / pnpm，请先安装 Node.js" }
$pmArgs = if ($pm -match 'pnpm') { @("dev") } else { @("run", "dev") }
Write-Host "使用包管理器: $pm"

Stop-ExistingWeb

# 3) 后台启动并捕获输出
$proc = Start-Process -FilePath $pm -ArgumentList $pmArgs `
    -WorkingDirectory $console -WindowStyle Hidden `
    -RedirectStandardOutput $outFile -RedirectStandardError $errFile -PassThru
$proc.Id | Set-Content -Path $pidFile -Encoding ascii
Write-Host "前端已启动 (PID $($proc.Id), $([IO.Path]::GetFileName($pm))) -> http://localhost:3000"

# 4) 等待并验证端口
Start-Sleep -Seconds 10
$alive = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
$port = Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue
if ($alive -and $port) { Write-Host "OK 前端就绪 -> http://localhost:3000" -ForegroundColor Green }
else {
    Write-Host "[警告] 3000 端口未就绪，启动日志末尾:" -ForegroundColor Yellow
    Get-Content $errFile -Encoding UTF8 -Tail 20 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }
    Get-Content $outFile -Encoding UTF8 -Tail 10 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }
}
