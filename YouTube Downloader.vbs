' Silent launcher - starts the app with no console window at all.
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = here
sh.Run """" & here & "\.venv\Scripts\pythonw.exe"" """ & here & "\main.py", 0, False
