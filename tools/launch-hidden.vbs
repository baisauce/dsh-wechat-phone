' launch-hidden.vbs - start a .bat/.cmd with NO visible console window.
'
' Why this exists
' ---------------
' A shortcut (or Run key) that points straight at a .bat gives it a visible
' cmd.exe window. The collector's launcher runs its child SYNCHRONOUSLY, and
' that child (collector-watchdog.ps1) is an endless loop - so the blank console
' window stays on the desktop forever. Worse: closing that window kills the
' whole tree (watchdog -> run-once -> python), which looks exactly like
' "the bot randomly stopped working after a reboot".
'
' wscript.exe has no console of its own, and Run(cmd, 0, False) starts the
' batch with a hidden window and returns immediately. Nothing to see, nothing
' to close by accident.
'
' Usage (shortcut target / Run key / scheduled task action)
' --------------------------------------------------------
'   wscript.exe "<folder>\launch-hidden.vbs" "<folder>\start-collector-bg.bat"
'
' Exit codes: 0 ok, 2 no argument, 3 target does not exist,
'             4 failed to start (see Err.Number).

Option Explicit

Dim fso, shell, target, rc

If WScript.Arguments.Count < 1 Then
    WScript.Quit 2
End If

target = WScript.Arguments(0)

Set fso = CreateObject("Scripting.FileSystemObject")
If Not fso.FileExists(target) Then
    WScript.Quit 3
End If

Set shell = CreateObject("WScript.Shell")
On Error Resume Next
' 0 = hidden window, False = do not wait for the batch to finish
shell.Run """" & target & """", 0, False
rc = Err.Number
On Error GoTo 0

If rc <> 0 Then
    WScript.Quit 4
End If

WScript.Quit 0