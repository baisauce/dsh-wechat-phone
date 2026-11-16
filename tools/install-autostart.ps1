#Requires -Version 5.1
<#
.SYNOPSIS
    Make the WeChat collector start at logon with NO visible console window.

.DESCRIPTION
    Registers Startup-folder shortcuts that go through wscript.exe plus
    tools\launch-hidden.vbs instead of pointing at a .bat directly.

    Why that matters: a shortcut that points at a .bat opens a visible cmd.exe
    window, and because the batch waits synchronously on collector-watchdog.ps1
    (an endless loop), that blank window stays on the desktop forever. Closing
    it kills watchdog -> run-once -> python, i.e. the collector silently dies
    and stays dead until the next logon.

    The shortcuts are named so that Task Manager / Settings > Startup are
    self-explanatory:
        微信采集器（AI 收发消息）.lnk     -> the bot that reads the phone
        AstrBot 服务端（网页控制台）.lnk  -> the AstrBot server itself

    Idempotent: re-running repairs an existing bad shortcut in place and
    migrates the old, unclear names. It never touches the collector's config,
    the running watchdog, or the repository.

.PARAMETER Uninstall
    Remove the startup shortcuts instead of creating them.

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

# Friendly names: these are what the user sees in Task Manager / Settings.
$CollectorLnkName = '微信采集器（AI 收发消息）.lnk'
$AstrBotLnkName   = 'AstrBot 服务端（网页控制台）.lnk'

# Old, unclear names created by earlier versions of this script.
$LegacyCollectorLnkName = 'AstrBot WeChat Collector.lnk'
$LegacyAstrBotLnkName   = 'AstrBot.lnk'

$CollectorLnk = Join-Path $startup $CollectorLnkName
$AstrBotLnk   = Join-Path $startup $AstrBotLnkName

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
    Say-Info "  name      : $(Split-Path -Leaf $LnkPath)"
    Say-Info "  target    : $($s.TargetPath)"
    Say-Info "  arguments : $($s.Arguments)"
    Say-Info "  workdir   : $($s.WorkingDirectory)"
}

# Returns the batch a legacy shortcut launches, but only if that shortcut was
# created by this tool (wscript + our vbs). Anything else returns $null, so we
# never delete a startup entry that belongs to somebody else.
function Get-OwnedShortcutTarget {
    param([string]$LnkPath)
    if (-not (Test-Path $LnkPath)) { return $null }
    $s = $shell.CreateShortcut($LnkPath)
    if ($s.TargetPath -ne $wscript) { return $null }
    if ($s.Arguments -notlike "*$vbs*") { return $null }
    $m = [regex]::Matches($s.Arguments, '"([^"]+)"')
    if ($m.Count -ge 2) { return $m[1].Groups[1].Value }
    return $null
}

# ------------------------------------------------------------- uninstall ----
if ($Uninstall) {
    Say-Info 'Removing startup entries ...'

    $candidates = @(
        @{ Lnk = $CollectorLnk; Label = 'collector' },
        @{ Lnk = $AstrBotLnk;   Label = 'AstrBot' },
        @{ Lnk = (Join-Path $startup $LegacyCollectorLnkName); Label = 'collector (legacy name)' },
        @{ Lnk = (Join-Path $startup $LegacyAstrBotLnkName);   Label = 'AstrBot (legacy name)' }
    )

    foreach ($c in $candidates) {
        if (-not (Test-Path $c.Lnk)) { continue }
        if ($null -ne (Get-OwnedShortcutTarget $c.Lnk)) {
            Remove-Item -LiteralPath $c.Lnk -Force
            Say-Ok "  removed $($c.Label): $(Split-Path -Leaf $c.Lnk)"
        } else {
            Say-Warn "  kept $($c.Label) (not created by this tool): $(Split-Path -Leaf $c.Lnk)"
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
    Say-Fail 'Fix the missing file(s) above, then run this script again.'
    exit 1
}

Write-Host ''

# --- migrate the old unclear name (collector) -------------------------------
$legacyCollector = Join-Path $startup $LegacyCollectorLnkName
if ($null -ne (Get-OwnedShortcutTarget $legacyCollector)) {
    Say-Info "Migrating old startup entry: $LegacyCollectorLnkName"
    Remove-Item -LiteralPath $legacyCollector -Force
    Say-Ok  "  removed obsolete name $LegacyCollectorLnkName"
}

# --- migrate the old unclear name (AstrBot), preserving its target ----------
$legacyAstrBot = Join-Path $startup $LegacyAstrBotLnkName
$legacyAstrBotTarget = Get-OwnedShortcutTarget $legacyAstrBot
if ($null -ne $legacyAstrBotTarget) {
    Say-Info "Migrating old startup entry: $LegacyAstrBotLnkName"
    Set-HiddenShortcut -LnkPath $AstrBotLnk -Target $legacyAstrBotTarget `
        -WorkingDir (Split-Path -Parent $legacyAstrBotTarget) `
        -Description 'AstrBot 服务端：隐藏窗口，登录后自动启动'
    Remove-Item -LiteralPath $legacyAstrBot -Force
    Say-Ok "  renamed to $AstrBotLnkName"
}

# --- collector --------------------------------------------------------------
if (Test-Path $CollectorLnk) {
    $state = Test-HiddenShortcut -LnkPath $CollectorLnk -Target $bat
    if ($state -eq 'ok') {
        Say-Ok "Collector startup entry already correct: $CollectorLnkName"
    } else {
        Say-Warn "Existing collector entry is NOT the hidden kind ($state)"
        Say-Warn '  -> this is the "blank console window at boot" bug; repairing now'
        Set-HiddenShortcut -LnkPath $CollectorLnk -Target $bat -WorkingDir $root `
            -Description '微信采集器：隐藏窗口，登录后自动启动'
    }
} else {
    Say-Info 'No collector startup entry yet - creating one'
    Set-HiddenShortcut -LnkPath $CollectorLnk -Target $bat -WorkingDir $root `
        -Description '微信采集器：隐藏窗口，登录后自动启动'
}

$state = Test-HiddenShortcut -LnkPath $CollectorLnk -Target $bat
if ($state -eq 'ok') {
    Say-Ok "Collector autostart ready: $CollectorLnkName"
    Show-Shortcut $CollectorLnk
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
    Set-HiddenShortcut -LnkPath $AstrBotLnk -Target $abBat -WorkingDir $AstrBotRoot `
        -Description 'AstrBot 服务端：隐藏窗口，登录后自动启动'
    $state = Test-HiddenShortcut -LnkPath $AstrBotLnk -Target $abBat
    if ($state -eq 'ok') {
        Say-Ok "AstrBot autostart ready: $AstrBotLnkName"
        Show-Shortcut $AstrBotLnk
    } else {
        Say-Fail "AstrBot autostart verification failed: $state"
        exit 1
    }
}

Write-Host ''
Say-Ok 'All startup entries are hidden and clearly named.'
Say-Info 'They take effect at the next logon (or run the batch now to start the watchdog).'
Say-Info 'Note: these entries target wscript.exe on purpose - that is what keeps the'
Say-Info '      console window away. The friendly name is the shortcut file name.'
Say-Info 'Remove them:   tools\install-autostart.ps1 -Uninstall'
exit 0