' Lanzador do Anonimizador de expedientes xuridicos (Windows).
'
' Arrinca o programa SEN ningunha ventana de consola: os accesos directos
' do menu Inicio / escritorio apuntan a "wscript.exe" con este ficheiro.
' (Fixado a ASCII a proposito: WScript le os .vbs coa paxina de codigos
' do sistema, non en UTF-8.)
'
' Todo o entorno (Tesseract, PYTHONPATH) fixase SO neste proceso e nos seus
' fillos -- non se toca o PATH nin as variables do sistema do usuario.
' O cartafol de traballo e %LOCALAPPDATA%\Anonimizador: ahi vive
' "datos_rexistro" (rexistros cifrados de correspondencias) e o rexistro
' de erros "anonimizador.log". Coma esta fora do cartafol do programa,
' desinstalar ou actualizar o programa non toca eses datos.

Option Explicit

Dim sh, fso, dirInst, dirDatos, entorno, pythonw

Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

dirInst = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = dirInst & "\runtime\python\pythonw.exe"

If Not fso.FileExists(pythonw) Then
    MsgBox "Non se atopa o programa en:" & vbCrLf & vbCrLf & dirInst & vbCrLf & vbCrLf & _
           "Volve executar o instalador do Anonimizador.", 16, "Anonimizador de expedientes xuridicos"
    WScript.Quit 1
End If

dirDatos = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Anonimizador"
If Not fso.FolderExists(dirDatos) Then fso.CreateFolder dirDatos

Set entorno = sh.Environment("Process")
entorno("TESSDATA_PREFIX") = dirInst & "\runtime\tesseract\tessdata"
entorno("PATH") = dirInst & "\runtime\tesseract\bin;" & entorno("PATH")
entorno("PYTHONPATH") = dirInst & "\anonimizador-xuridico\src"

sh.CurrentDirectory = dirDatos

' pythonw.exe non abre consola, asi que non hai venta negra que ocultar.
' O modo de venta e 1 (normal) A PROPOSITO: cun 0 (oculta) Windows pasa
' "oculta" ao proceso fillo coma estado inicial da sua PRIMEIRA venta, e a
' xanela do programa (pywebview) naceria invisible -- o servidor arrinca
' pero non se ve nada. False = non agardar a que remate.
sh.Run """" & pythonw & """ -m anonimizador.cli escritorio --porto 5050 --chaveiro-sistema", 1, False
