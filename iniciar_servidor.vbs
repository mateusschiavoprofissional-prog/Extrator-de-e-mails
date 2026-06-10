' Script para iniciar o servidor em segundo plano (sem janela preta)
Set WshShell = CreateObject("WScript.Shell")
Dim strPath

' Obtem o caminho da pasta onde o script VBS esta
strPath = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)

' Executa o arquivo .bat de forma oculta (o parametro 0 esconde a janela)
WshShell.Run Chr(34) & strPath & "\iniciar_servidor.bat" & Chr(34), 0, False

Set WshShell = Nothing