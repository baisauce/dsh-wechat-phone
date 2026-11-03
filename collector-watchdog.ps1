# Portable WeChat collector watchdog (hidden, single-instance, auto-restart).
# ALL machine-specific paths come from tools\resolve-env.ps1 - do not hardcode here.
# Stop order when taking the collector down: this watchdog first, then the cmd wrapper,
# then python (otherwise the 15s restart loop just brings it back).
$ErrorActionPreference = 'Continue'
$root = $PSScriptRoot
$mutex = New-Object System.Threading.Mutex($false, 'Local\AstrBotWxCollector')
if (-not $mutex.WaitOne(0)) { exit 0 }
try {
    foreach ($line in (& (Join-Path $root 'tools\resolve-env.ps1'))) {
        if ($line -match '^([A-Z_]+)=(.*)$') { Set-Item -Path ('Env:' + $Matches[1]) -Value $Matches[2] }
    }
    if (-not $env:PY) {
        Write-Error 'collector watchdog: python not resolved (set DSH_WX_PYTHON or config.json "python")'
        exit 4
    }
    $log = Join-Path $root 'logs\collector.log'
    $run = Join-Path $root 'collector\run-once.cmd'
    # Back off when the child dies instantly and repeatedly (phone unplugged =>
    # main.py exits at once with "no adb device"). Without this the loop writes
    # ~8 log lines a minute and spins for hours until the cable comes back.
    $streak = 0
    while ($true) {
        $t0 = Get-Date
        & cmd.exe /c $run
        $secs = ((Get-Date) - $t0).TotalSeconds
        if ($secs -lt 20) { $streak++ } else { $streak = 0 }
        $wait = if ($streak -ge 3) { 60 } else { 15 }
        try {
            Add-Content -LiteralPath $log -Value ('[watchdog] collector exited after ' +
                [math]::Round($secs, 1) + 's, restart in ' + $wait + 's ' + (Get-Date)) -ErrorAction Stop
        } catch { }
        Start-Sleep -Seconds $wait
    }
} finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
