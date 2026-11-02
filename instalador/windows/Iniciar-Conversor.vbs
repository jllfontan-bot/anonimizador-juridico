' Lanzador do Reductor de tokens (Windows, instalador clasico).
'
' Arrinca a pantalla do conversor SEN ventana de consola: os accesos
' directos apuntan a "wscript.exe" con este ficheiro. (En ASCII a
' proposito: WScript le os .vbs coa paxina de codigos do sistema.)
'
' Tesseract e PYTHONPATH fixanse SO neste proceso. O cartafol de traballo
' (rexistro compartido co anonimizador e preferencias) e
' Documentos\Anonimizador: ponno `pantalla_conversor.main`, coma na Store.
' O conversor non abre ningun porto.

Option Explicit

Dim sh, fso, dirInst, entorno, pythonw

Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

dirInst = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = dirInst & "\runtime\python\pythonw.exe"

If Not fso.FileExists(pythonw) Then
    MsgBox "Non se atopa o programa en:" & vbCrLf & vbCrLf & dirInst & vbCrLf & vbCrLf & _
           "Volve executar o instalador do Reductor de tokens.", 16, "Reductor de tokens"
    WScript.Quit 1
End If

Set entorno = sh.Environment("Process")
entorno("TESSDATA_PREFIX") = dirInst & "\runtime\tesseract\tessdata"
entorno("PATH") = dirInst & "\runtime\tesseract\bin;" & entorno("PATH")
entorno("PYTHONPATH") = dirInst & "\anonimizador-xuridico\src"

sh.CurrentDirectory = dirInst

' Modo de venta 1 (normal) a proposito, coma no anonimizador: cun 0 a xanela
' de pywebview naceria invisible. False = non agardar a que remate.
sh.Run """" & pythonw & """ -m anonimizador.pantalla_conversor", 1, False
