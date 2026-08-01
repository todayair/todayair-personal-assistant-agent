# 停止由 start-*.ps1 启动的后台服务（PID 记录 + 端口双保险）
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $root "logs"
$results = @()
$jobs = @(
    @{ Name = "web-api"; Port = 8000 },
    @{ Name = "next-dev"; Port = 3000 }
)
foreach ($job in $jobs) {
    $name = $job.Name
    $pids = New-Object System.Collections.Generic.List[int]
    $pidFile = Join-Path $logDir "$name.pid"
    if (Test-Path -LiteralPath $pidFile) {
        try { $pids.Add([int]((Get-Content -LiteralPath $pidFile -Raw).Trim())) } catch { }
        Remove-Item -LiteralPath $pidFile -Force
    }
    $conn = Get-NetTCPConnection -LocalPort $job.Port -State Listen -ErrorAction SilentlyContinue
    if ($conn) { foreach ($c in $conn) { $pids.Add([int]$c.OwningProcess) } }
    $done = $false
    foreach ($procId in ($pids | Where-Object { $_ -gt 0 } | Select-Object -Unique)) {
        $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
        if ($proc) {
            & taskkill /PID $procId /T /F 2>$null | Out-Null
            $results += "$name (PID $procId) 已停止"
            $done = $true
        }
    }
    if (-not $done) { $results += "$name 已不在运行" }
}
$results | ForEach-Object { Write-Host $_ }
