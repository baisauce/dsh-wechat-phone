#Requires -Version 5.1
<#
.SYNOPSIS
    Make the WeChat collector start at logon with NO visible console window.

.DESCRIPTION
    Registers a Startup-folder shortcut for start-collector-bg.bat that goes
    through wscript.exe + tools\launch-hidden.vbs instead of pointing at the
    .bat directly.

    Why that matters: a shortcut that points at a .bat opens a visible cmd.exe
    window, and because the batch waits synchronously on collector-watchdog.ps1
    (an endless loop), that blank window stays on the desktop forever. Closing
    it kills watchdog -> run-once -> python, i.e. the collector silently dies
    and stays dead until the next logon.

    Idempotent: re-running repairs an existing bad shortcut in place. It never
    touches the collector's config, the running watchdog, or the repository.

.PARAMETER Uninstall
    Remove the startup shortcut instead of creating it.

.PARAMETER IncludeAstrBot
    Also create/repair a hidden startup shortcut for AstrBot itself. Requires
    -AstrBotRoot. AstrBot's own launcher has the same "closing the window kills
    the server" hazard as the collector.

.PARAMETER AstrBotRoot
    AstrBot working directory that contains start-astrbot.bat.
    Only used together with -IncludeAstrBot.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\install-autostart.ps1

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\install-autostart.ps1 `
        -IncludeAstrBot -AstrBotRoot "D:\Program Files\AstrBot"

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\install-autostart.ps1 -Uninstall
#>
[CmdletBinding()]
param(
    [switch]$Uninstall,
    [switch]$IncludeAstrBot,
    [string]$AstrBotRoot
)

$ErrorActionPreference = 'Stop'

$root    = Split-Path -Parent $PSScriptRoot                    # repository root
$vbs     = Join-Path $PSScriptRoot 'launch-hidden.vbs'
$bat     = Join-Path $root 'start-collector-bg.bat'
$startup = [Environment]::GetFolderPath('Startup')
$wscript = Join-Path $env:SystemRoot 'System32\wscript.exe'
$lnkName = 'AstrBot WeChat Collector.lnk'
$lnkPath = Join-Path $startup $lnkName

function Say-Ok   ([string]$m) { Write-Host "[  OK  ] $m" -ForegroundColor Green }
function Say-Info ([string]$m) { Write-Host "[ INFO ] $m" }
function Say-Warn ([string]$m) { Write-Host "[ WARN ] $m" -ForegroundColor Yellow }
function Say-Fail ([string]$m) { Write-Host "[ FAIL ] $m" -ForegroundColor Red }

# ---------------------------------------------------------------- sanity ----
if ([string]::IsNullOrWhiteSpace($startup) -or -not (Test-Path $startup)) {
    Say-Fail "Startup folder not found (resolved: '$startup')."
    exit 1
}

$shell = New-Object -ComObject WScript.Shell

function Get-LnkArgs([string]$Target) {
    return '"' + $vbs + '" "' + $Target + '"'
}

function Set-HiddenShortcut {
    param(
        [string]$LnkPath,
        [string]$Target,
        [string]$WorkingDir,
        [string]$Description
    )
    $s = $shell.CreateShortcut($LnkPath)
    $s.TargetPath       = $wscript
    $s.Arguments        = Get-LnkArgs $Target
    $s.WorkingDirectory = $WorkingDir
    $s.WindowStyle      = 7              # ignored by wscript, kept tidy
    $s.Description      = $Description
    $s.Save()
}

function Test-HiddenShortcut {
    param([string]$LnkPath, [string]$Target)
    if (-not (Test-Path $LnkPath)) { return 'missing' }
    $s = $shell.CreateShortcut($LnkPath)
    if ($s.TargetPath -ne $wscript) {
        return 'target is ' + $s.TargetPath + ' (expected wscript.exe)'
    }
    if ($s.Arguments -ne (Get-LnkArgs $Target)) {
        return 'arguments do not match the expected hidden launcher call'
    }
    return 'ok'
}

function Show-Shortcut {
    param([string]$LnkPath)
    $s = $shell.CreateShortcut($LnkPath)
    Say-Info  "  file      : $LnkPath"
    Say-Info  "  target    : $($s.TargetPath)"
    Say-Info  "  arguments : $($s.Arguments)"
    Say-Info  "  workdir   : $($s.WorkingDirectory)"
}

# ------------------------------------------------------------- uninstall ----
if ($Uninstall) {
    Say-Info 'Removing startup entries ...'

    foreach ($pair in @(
            @{ Lnk = $lnkPath; Label = 'collector' },
            @{ Lnk = (Join-Path $startup 'AstrBot.lnk'); Label = 'AstrBot' })) {
        if (Test-Path $pair.Lnk) {
            Say-Info "  looked at $($pair.Label): $($pair.Lnk)"
            # Only remove entries this tool owns (wscript + our vbs).
            $s = $shell.CreateShortcut($pair.Lnk)
            if ($s.TargetPath -eq $wscript -and $s.Arguments -like "*$vbs*") {
                Remove-Item -LiteralPath $pair.Lnk -Force
                Say-Ok "  removed $($pair.Label) startup shortcut"
            } else {
                Say-Warn "  kept $($pair.Label) (not created by this tool)"
            }
        }
    }

    Say-Ok 'Done. Nothing will auto-start at the next logon.'
    exit 0
}

# ---------------------------------------------------------------- install ----
Say-Info "Repository root : $root"
Say-Info "Startup folder  : $startup"
Write-Host ''

$problems = 0
foreach ($need in @(
        @{ Path = $vbs;     What = 'hidden launcher (tools\launch-hidden.vbs)' },
        @{ Path = $bat;     What = 'collector launcher (start-collector-bg.bat)' },
        @{ Path = $wscript; What = 'wscript.exe' })) {
    if (Test-Path $need.Path) {
        Say-Ok "$($need.What) found"
    } else {
        Say-Fail "$($need.What) missing: $($need.Path)"
        $problems++
    }
}
if ($problems -gt 0) {
    Say-Fail "Fix the missing file(s) above, then run this script again."
    exit 1
}

Write-Host ''
if (Test-Path $lnkPath) {
    $state = Test-HiddenShortcut -LnkPath $lnkPath -Target $bat
    if ($state -eq 'ok') {
        Say-Ok 'Collector startup shortcut already correct - refreshing it anyway'
    } else {
        Say-Warn "Existing collector shortcut is NOT the hidden kind ($state)"
        Say-Warn '  -> this is the "blank console window at boot" bug; repairing now'
    }
} else {
    Say-Info 'No collector startup shortcut yet - creating one'
}

Set-HiddenShortcut -LnkPath $lnkPath -Target $bat -WorkingDir $root `
    -Description 'AstrBot WeChat collector watchdog (hidden, no console)'

$state = Test-HiddenShortcut -LnkPath $lnkPath -Target $bat
if ($state -eq 'ok') {
    Say-Ok "Collector autostart installed: $lnkName"
    Show-Shortcut $lnkPath
} else {
    Say-Fail "Collector autostart verification failed: $state"
    exit 1
}

# ----------------------------------------------------------------- AstrBot ----
if ($IncludeAstrBot) {
    Write-Host ''
    if ([string]::IsNullOrWhiteSpace($AstrBotRoot)) {
        Say-Fail '-IncludeAstrBot needs -AstrBotRoot "<AstrBot directory>"'
        exit 1
    }
    $abBat = Join-Path $AstrBotRoot 'start-astrbot.bat'
    if (-not (Test-Path $abBat)) {
        Say-Fail "start-astrbot.bat not found under: $AstrBotRoot"
        exit 1
    }
    $abLnk = Join-Path $startup 'AstrBot.lnk'
    Set-HiddenShortcut -LnkPath $abLnk -Target $abBat -WorkingDir $AstrBotRoot `
        -Description 'AstrBot standalone (auto-start at logon, hidden, no console)'
    $state = Test-HiddenShortcut -LnkPath $abLnk -Target $abBat
    if ($state -eq 'ok') {
        Say-Ok 'AstrBot autostart installed: AstrBot.lnk'
        Show-Shortcut $abLnk
    } else {
        Say-Fail "AstrBot autostart verification failed: $state"
        exit 1
    }
}

Write-Host ''
Say-Ok 'All startup entries are hidden. Next logon will be silent.'
Say-Info 'They take effect at the next logon (or run the batch now to start the watchdog).'
Say-Info 'Verify later:  Get-Process cmd,wscript | Select Id,MainWindowTitle   (titles stay empty)'
Say-Info 'Remove them:   tools\install-autostart.ps1 -Uninstall'
exit 0