# resolve-env.ps1 - the ONE place where machine-specific paths are discovered.
# Prints ASCII KEY=VALUE lines consumed by start-collector.bat and collector-watchdog.ps1.
# Search order: environment variable > collector\config.json > common layouts > PATH.
#
#   DSH_WX_PYTHON / DSH_WX_ADB  - explicit overrides, highest priority
#   collector\config.json       - "python" (optional) and "adb_path" (required anyway)
#   <AstrBot>\python\python.exe - embedded layout, when this repo sits inside the AstrBot dir
#   %LOCALAPPDATA%\uv\tools\astrbot\Scripts\python.exe - uv tool install route
#   <AstrBot>\tools\platform-tools\adb.exe
#
# Nothing here starts or stops anything - it only resolves paths.
# Caveat: values travel to .bat through a console pipe, so if your install path
# contains non-ASCII characters and cmd mangles them, skip the auto-discovery and
# set DSH_WX_PYTHON / DSH_WX_ADB (or "python" / "adb_path" in config.json) instead.
$ErrorActionPreference = 'SilentlyContinue'

$root = Split-Path -Parent $PSScriptRoot
$cfgPath = Join-Path $root 'collector\config.json'
$cfg = $null
if (Test-Path -LiteralPath $cfgPath) {
    try { $cfg = ConvertFrom-Json ([IO.File]::ReadAllText($cfgPath)) } catch { $cfg = $null }
}

function FirstExisting($cands) {
    foreach ($c in $cands) {
        if ($c -and (Test-Path -LiteralPath $c)) { return (Get-Item -LiteralPath $c).FullName }
    }
    return ''
}

# ---- python: prefer the interpreter next to AstrBot (saves a second install); any standalone venv also works ----
$pyCands = @()
if ($env:DSH_WX_PYTHON) { $pyCands += $env:DSH_WX_PYTHON }
if ($cfg -and $cfg.python) { $pyCands += [string]$cfg.python }
$pyCands += (Join-Path $env:LOCALAPPDATA 'uv\tools\astrbot\Scripts\python.exe')
$pyCands += (Join-Path (Split-Path -Parent $root) 'python\python.exe')
$pyCands += (Join-Path $root '.venv\Scripts\python.exe')
$py = FirstExisting $pyCands
if (-not $py) {
    $g = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($g) { $py = $g.Source }
}

# ---- adb ----
$adbCands = @()
if ($env:DSH_WX_ADB) { $adbCands += $env:DSH_WX_ADB }
if ($cfg -and $cfg.adb_path) { $adbCands += [string]$cfg.adb_path }
$adbCands += (Join-Path (Split-Path -Parent $root) 'tools\platform-tools\adb.exe')
$adb = FirstExisting $adbCands
if (-not $adb) {
    $g = Get-Command adb.exe -ErrorAction SilentlyContinue
    if ($g) { $adb = $g.Source }
}

$logDir = Join-Path $root 'logs'
if (-not (Test-Path -LiteralPath $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }

if (-not $py) { Write-Error 'python not found: set DSH_WX_PYTHON, or add "python" to collector\config.json' }
if (-not $adb) { Write-Warning 'adb not found: download Google platform-tools and set adb_path in collector\config.json' }

Write-Output ('ROOT=' + $root)
Write-Output ('MAIN=' + (Join-Path $root 'collector\main.py'))
Write-Output ('PY=' + $py)
Write-Output ('ADB=' + $adb)
Write-Output ('LOGDIR=' + $logDir)
Write-Output ('BOOT=' + (Join-Path $logDir 'collector-boot.out'))
