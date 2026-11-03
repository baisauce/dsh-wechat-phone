# AstrBot WeChat collector watchdog (hidden, single-instance, auto-restart).
$ErrorActionPreference = 'Continue'
$mutex = New-Object System.Threading.Mutex($false, 'Local\AstrBotWxCollector')
if (-not $mutex.WaitOne(0)) { exit 0 }
$py = 'D:\Program Files\AstrBot\python\python.exe'
$main = 'D:\Program Files\AstrBot\dsh-wechat-phone\collector\main.py'
$adb = 'D:\Program Files\AstrBot\tools\platform-tools\adb.exe'
$log = 'D:\Program Files\AstrBot\dsh-wechat-phone\logs\collector.log'
$run = 'D:\Program Files\AstrBot\dsh-wechat-phone\collector\run-once.cmd'
try {
    while ($true) {
        & cmd.exe /c """$run"""
        try {
            Add-Content -LiteralPath $log -Value ("[watchdog] collector exited, restart in 15s " + (Get-Date)) -ErrorAction Stop
        } catch { }
        Start-Sleep -Seconds 15
    }
} finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
