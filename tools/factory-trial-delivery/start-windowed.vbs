Option Explicit
Dim shell, files, root, python, command, result
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
root = files.GetParentFolderName(WScript.ScriptFullName)
python = files.BuildPath(root, "runtime\pythonw.exe")
If Not files.FileExists(python) Or Not files.FileExists(files.BuildPath(root, "windowed_start.py")) Then
    MsgBox "Package incomplete. Extract the whole ZIP to a local folder.", 16, "Local trial"
    WScript.Quit 2
End If
shell.CurrentDirectory = root
shell.Environment("PROCESS")("PYTHONUTF8") = "1"
shell.Environment("PROCESS")("PYTHONDONTWRITEBYTECODE") = "1"
command = Chr(34) & python & Chr(34) & " -X utf8 " & Chr(34) & files.BuildPath(root, "windowed_start.py") & Chr(34)
On Error Resume Next
result = shell.Run(command, 0, True)
If Err.Number <> 0 Then
    MsgBox "Unable to start: " & Err.Description & vbCrLf & "Try START.cmd.", 16, "Local trial"
    WScript.Quit 1
End If
On Error GoTo 0
If result <> 0 Then
    MsgBox "Startup failed. Please send data\startup-console.log and data\startup-error.log.", 16, "Local trial"
    If files.FileExists(files.BuildPath(root, "data\startup-console.log")) Then
        shell.Run "notepad.exe " & Chr(34) & files.BuildPath(root, "data\startup-console.log") & Chr(34), 1, False
    End If
End If
WScript.Quit result
