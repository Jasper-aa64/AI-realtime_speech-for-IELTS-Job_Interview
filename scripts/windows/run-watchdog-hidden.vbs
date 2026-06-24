' Launch the IELTS stack watchdog with NO console window — no terminal/taskbar
' flash, even though the scheduled task runs in the interactive session.
'
' Why this exists: a scheduled task whose action is powershell.exe spawns a
' conhost window that briefly flashes on screen every time it fires, however
' "-WindowStyle Hidden" is set. wscript.exe itself has no console, and
' Shell.Run(cmd, 0, False) starts PowerShell with window style 0 (hidden) and
' returns immediately, so nothing ever appears.
Option Explicit
Dim shell, fso, here, ps1, cmd
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
ps1 = fso.BuildPath(here, "watchdog-ielts-stack.ps1")
cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & ps1 & """"
shell.Run cmd, 0, False
