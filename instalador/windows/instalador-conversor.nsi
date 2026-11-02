; Instalador de Windows do Reductor de tokens (NSIS, MUI2).
;
; O mesmo esquema có do anonimizador (instalador.nsi): cross-compile dende o
; Mac/Linux con `makensis`, chamado dende `instalador/crear-paquetes.sh
; windows-conversor`, cos mesmos -D (VERSION, VERSION_NUM, XERADO, SAIDA,
; RECURSOS, PROBA) e o mesmo árbore (Python, Tesseract, código), co lanzador,
; a icona e o manual do conversor.
;
; Instálase POR USUARIO (sen UAC) en %LOCALAPPDATA%\Programs\ConversorIA. Os
; datos (rexistro cifrado compartido co anonimizador e preferencias) viven en
; Documentos\Anonimizador e NUNCA os borra o desinstalador: son tamén do
; anonimizador.

Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"
!include "WinMessages.nsh"

Var RutaPS1

!ifndef VERSION
  !define VERSION "dev"
!endif
!ifndef VERSION_NUM
  !define VERSION_NUM "1.1.0.0"
!endif
!ifndef RECURSOS
  !define RECURSOS "."
!endif

!define NOME_PROGRAMA "Reductor de tokens"
!define CLAVE_DESINSTALAR "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConversorIA"
!define NOME_DESINSTALADOR "Desinstalar-Conversor.exe"
!define CARTAFOL_INICIO "Reductor de tokens"
!define EDITOR "JL López"

Name "${NOME_PROGRAMA}"
OutFile "${SAIDA}"
InstallDir "$LOCALAPPDATA\Programs\ConversorIA"
InstallDirRegKey HKCU "${CLAVE_DESINSTALAR}" "InstallLocation"
RequestExecutionLevel user
BrandingText "${NOME_PROGRAMA} ${VERSION}"
ManifestDPIAware true
SetOverwrite on

!ifdef PROBA
  SetCompress off
!else
  SetCompressor /SOLID lzma
  SetCompressorDictSize 64
!endif

VIProductVersion "${VERSION_NUM}"

; ------------------------------------------------------------ Páxinas
!define MUI_ICON "${RECURSOS}\conversor.ico"
!define MUI_UNICON "${RECURSOS}\conversor.ico"
!define MUI_WELCOMEFINISHPAGE_BITMAP "${RECURSOS}\asistente-conversor.bmp"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "${RECURSOS}\asistente-conversor.bmp"
!define MUI_ABORTWARNING
!define MUI_UNABORTWARNING

!define MUI_WELCOMEPAGE_TITLE "$(TXT_BENVIDA_TITULO)"
!define MUI_WELCOMEPAGE_TEXT "$(TXT_BENVIDA)"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES

!define MUI_FINISHPAGE_TITLE "$(TXT_FIN_TITULO)"
!define MUI_FINISHPAGE_TEXT "$(TXT_FIN)"
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "$(TXT_ABRIR)"
!define MUI_FINISHPAGE_RUN_FUNCTION LanzarPrograma
!define MUI_FINISHPAGE_SHOWREADME
!define MUI_FINISHPAGE_SHOWREADME_TEXT "$(TXT_ESCRITORIO)"
!define MUI_FINISHPAGE_SHOWREADME_FUNCTION CrearAccesoEscritorio
!define MUI_FINISHPAGE_SHOWREADME_NOTCHECKED
!insertmacro MUI_PAGE_FINISH

!define MUI_WELCOMEPAGE_TITLE "$(TXT_UN_BENVIDA_TITULO)"
!define MUI_WELCOMEPAGE_TEXT "$(TXT_UN_BENVIDA)"
!insertmacro MUI_UNPAGE_WELCOME
!insertmacro MUI_UNPAGE_INSTFILES
!define MUI_FINISHPAGE_TITLE "$(TXT_UN_FIN_TITULO)"
!define MUI_FINISHPAGE_TEXT "$(TXT_UN_FIN)"
!insertmacro MUI_UNPAGE_FINISH

; ------------------------------------------------------------ Idioma
!if /FileExists "${NSISDIR}/Contrib/Language files/Galician.nlf"
  !define GALEGO
  !insertmacro MUI_LANGUAGE "Galician"
  !define LANG_UI ${LANG_GALICIAN}
!else
  !insertmacro MUI_LANGUAGE "Spanish"
  !define LANG_UI ${LANG_SPANISH}
!endif

!macro TEXTO id gl es
  !ifdef GALEGO
    LangString ${id} ${LANG_UI} "${gl}"
  !else
    LangString ${id} ${LANG_UI} "${es}"
  !endif
!macroend

!insertmacro TEXTO TXT_BENVIDA_TITULO "Benvida ao instalador do Reductor de tokens" "Bienvenida al instalador del Reductor de tokens"
!insertmacro TEXTO TXT_BENVIDA "Este asistente instalará o ${NOME_PROGRAMA} no seu ordenador: pasa documentos a Markdown (.md), con ou sen anonimizar, para dárllelos a unha IA gastando menos tokens.$\r$\n$\r$\nO programa inclúe todo o necesario (Python, OCR e o modelo de idioma): non fai falta conexión a internet nin permisos de administrador.$\r$\n$\r$\nPreme Seguinte para continuar." "Este asistente instalará el ${NOME_PROGRAMA} en su ordenador: pasa documentos a Markdown (.md), con o sin anonimizar, para dárselos a una IA gastando menos tokens.$\r$\n$\r$\nEl programa incluye todo lo necesario (Python, OCR y el modelo de idioma): no hace falta conexión a internet ni permisos de administrador.$\r$\n$\r$\nPulse Siguiente para continuar."
!insertmacro TEXTO TXT_FIN_TITULO "Instalación completada" "Instalación completada"
!insertmacro TEXTO TXT_FIN "O ${NOME_PROGRAMA} quedou instalado. Pode abrilo dende o menú Inicio.$\r$\n$\r$\nPara desinstalalo: Configuración > Aplicacións > Aplicacións instaladas, ou o acceso Desinstalar do menú Inicio." "El ${NOME_PROGRAMA} ha quedado instalado. Puede abrirlo desde el menú Inicio.$\r$\n$\r$\nPara desinstalarlo: Configuración > Aplicaciones > Aplicaciones instaladas, o el acceso Desinstalar del menú Inicio."
!insertmacro TEXTO TXT_UN_FIN_TITULO "Desinstalación completada" "Desinstalación completada"
!insertmacro TEXTO TXT_UN_FIN "O ${NOME_PROGRAMA} foi eliminado deste ordenador. Os datos de Documentos\Anonimizador (compartidos co anonimizador) non se tocaron." "El ${NOME_PROGRAMA} ha sido eliminado de este ordenador. Los datos de Documentos\Anonimizador (compartidos con el anonimizador) no se han tocado."
!insertmacro TEXTO TXT_ABRIR "Abrir o Reductor de tokens agora" "Abrir el Reductor de tokens ahora"
!insertmacro TEXTO TXT_ESCRITORIO "Crear un acceso directo no escritorio" "Crear un acceso directo en el escritorio"
!insertmacro TEXTO TXT_UN_BENVIDA_TITULO "Desinstalar o Reductor de tokens" "Desinstalar el Reductor de tokens"
!insertmacro TEXTO TXT_UN_BENVIDA "Vaise desinstalar o ${NOME_PROGRAMA} de:$\r$\n$\r$\n$INSTDIR$\r$\n$\r$\nOs datos de Documentos\Anonimizador (o rexistro cifrado, compartido co anonimizador) non se borran.$\r$\n$\r$\nPreme Seguinte para continuar." "Se va a desinstalar el ${NOME_PROGRAMA} de:$\r$\n$\r$\n$INSTDIR$\r$\n$\r$\nLos datos de Documentos\Anonimizador (el registro cifrado, compartido con el anonimizador) no se borran.$\r$\n$\r$\nPulse Siguiente para continuar."
!insertmacro TEXTO TXT_ESTA_ABERTO "O Reductor de tokens está aberto. Para continuar hai que pechalo.$\r$\n$\r$\nPreme Aceptar para que o asistente o peche, ou Cancelar para saír." "El Reductor de tokens está abierto. Para continuar hay que cerrarlo.$\r$\n$\r$\nPulse Aceptar para que el asistente lo cierre, o Cancelar para salir."
!insertmacro TEXTO TXT_NON_SE_PECHOU "Non se puido pechar o Reductor de tokens. Péchao a man e volve tentalo." "No se pudo cerrar el Reductor de tokens. Ciérrelo a mano y vuelva a intentarlo."
!insertmacro TEXTO TXT_SO_64 "Este programa só funciona en Windows de 64 bits." "Este programa solo funciona en Windows de 64 bits."
!insertmacro TEXTO TXT_LIMPANDO "Preparando a instalación (eliminando a versión anterior, se a hai)..." "Preparando la instalación (eliminando la versión anterior, si la hay)..."
!insertmacro TEXTO TXT_INSTALANDO "Instalando o programa..." "Instalando el programa..."
!insertmacro TEXTO TXT_ACCESOS "Creando os accesos directos..." "Creando los accesos directos..."
!insertmacro TEXTO TXT_REXISTRO "Rexistrando o programa en Aplicacións instaladas..." "Registrando el programa en Aplicaciones instaladas..."
!insertmacro TEXTO TXT_DESINSTALANDO "Desinstalando o programa..." "Desinstalando el programa..."
!insertmacro TEXTO TXT_ACCESO_PROGRAMA "${NOME_PROGRAMA}" "${NOME_PROGRAMA}"
!insertmacro TEXTO TXT_ACCESO_MANUAL "Manual de uso" "Manual de uso"
!insertmacro TEXTO TXT_ACCESO_DESINSTALAR "Desinstalar" "Desinstalar"
!insertmacro TEXTO TXT_SEN_WEBVIEW2 "Non se atopou o compoñente de Windows «Microsoft Edge WebView2 Runtime», que o programa usa para amosar a súa xanela. En Windows 11 vén instalado; en Windows 10 pódese descargar gratis de Microsoft." "No se encontró el componente de Windows «Microsoft Edge WebView2 Runtime», que el programa usa para mostrar su ventana. En Windows 11 viene instalado; en Windows 10 se puede descargar gratis de Microsoft."

VIAddVersionKey /LANG=${LANG_UI} "ProductName" "${NOME_PROGRAMA}"
VIAddVersionKey /LANG=${LANG_UI} "FileDescription" "Instalador do ${NOME_PROGRAMA}"
VIAddVersionKey /LANG=${LANG_UI} "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=${LANG_UI} "ProductVersion" "${VERSION}"
VIAddVersionKey /LANG=${LANG_UI} "CompanyName" "${EDITOR}"
VIAddVersionKey /LANG=${LANG_UI} "LegalCopyright" "© ${EDITOR}"

; ------------------------------------------------------------ Funcións comúns
; Refrescan o texto "NN %" baixo a barra de progreso lendo a POSICIÓN REAL
; da propia barra da páxina de instalación (control 1004; o texto de estado
; é o 1006), así o número e a barra nunca poden discrepar.
!macro DEFINIR_PCT PREF TEXTO
  Function ${PREF}ActualizarPct
    IfSilent fin
    Push $R0
    Push $R1
    Push $R2
    Push $R3
    FindWindow $R0 "#32770" "" $HWNDPARENT
    GetDlgItem $R1 $R0 1004
    SendMessage $R1 ${PBM_GETPOS} 0 0 $R2
    SendMessage $R1 ${PBM_GETRANGE} 0 0 $R3
    ${If} $R3 > 0
      IntOp $R2 $R2 * 100
      IntOp $R2 $R2 / $R3
      ${If} $R2 > 100
        StrCpy $R2 100
      ${EndIf}
      GetDlgItem $R1 $R0 1006
      SendMessage $R1 ${WM_SETTEXT} 0 "STR:${TEXTO} $R2 %"
    ${EndIf}
    Pop $R3
    Pop $R2
    Pop $R1
    Pop $R0
    fin:
  FunctionEnd
!macroend
!insertmacro DEFINIR_PCT "" "$(TXT_INSTALANDO)"
!insertmacro DEFINIR_PCT "un." "$(TXT_DESINSTALANDO)"

; Se o programa está en marcha (o seu pythonw.exe queda bloqueado contra
; escritura) pídese permiso para pechalo -- en modo silencioso (/S) péchase
; sen preguntar -- e péchase con pechar-programa.ps1 (só procesos que corren
; dende o cartafol "runtime" desta instalación, nunca outros Python do usuario).
!macro DEFINIR_PECHAR PREF
  Function ${PREF}ProgramaEnMarcha
    ; devolve 1 na pila se o executable está bloqueado, 0 se non
    ${IfNot} ${FileExists} "$INSTDIR\runtime\python\pythonw.exe"
      Push 0
      Return
    ${EndIf}
    ClearErrors
    FileOpen $0 "$INSTDIR\runtime\python\pythonw.exe" a
    ${If} ${Errors}
      Push 1
    ${Else}
      FileClose $0
      Push 0
    ${EndIf}
  FunctionEnd

  Function ${PREF}PecharPrograma
    Call ${PREF}ProgramaEnMarcha
    Pop $0
    ${If} $0 == 0
      Return
    ${EndIf}
    IfSilent +3
    MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION "$(TXT_ESTA_ABERTO)" IDOK +2
    Abort
    ${If} ${FileExists} "$RutaPS1"
      nsExec::Exec '"powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "$RutaPS1" -Ruta "$INSTDIR\runtime"'
      Pop $0
    ${EndIf}
    Sleep 1500
    Call ${PREF}ProgramaEnMarcha
    Pop $0
    ${If} $0 == 1
      Sleep 3000
      Call ${PREF}ProgramaEnMarcha
      Pop $0
      ${If} $0 == 1
        IfSilent +2
        MessageBox MB_OK|MB_ICONSTOP "$(TXT_NON_SE_PECHOU)"
        Abort
      ${EndIf}
    ${EndIf}
  FunctionEnd
!macroend
!insertmacro DEFINIR_PECHAR ""
!insertmacro DEFINIR_PECHAR "un."

; ------------------------------------------------------------ Instalador
Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_OK|MB_ICONSTOP "$(TXT_SO_64)"
    Abort
  ${EndIf}
FunctionEnd

Function LanzarPrograma
  Exec '"$WINDIR\System32\wscript.exe" "$INSTDIR\Iniciar-Conversor.vbs"'
FunctionEnd

Function CrearAccesoEscritorio
  SetOutPath "$INSTDIR"
  CreateShortcut "$DESKTOP\$(TXT_ACCESO_PROGRAMA).lnk" "$WINDIR\System32\wscript.exe" \
    '"$INSTDIR\Iniciar-Conversor.vbs"' "$INSTDIR\conversor.ico" 0 SW_SHOWNORMAL "" "${NOME_PROGRAMA}"
FunctionEnd

Section "Reductor de tokens" SecPrincipal
  SectionIn RO
  InitPluginsDir
  SetDetailsPrint textonly

  ; 1) Pechar o programa se estivese aberto e limpar unha instalación previa
  StrCpy $RutaPS1 "$PLUGINSDIR\pechar-programa.ps1"
  File "/oname=$RutaPS1" "${RECURSOS}\pechar-programa.ps1"
  Call PecharPrograma
  DetailPrint "$(TXT_LIMPANDO)"
  RMDir /r "$INSTDIR\runtime"
  RMDir /r "$INSTDIR\anonimizador-xuridico"
  RMDir /r "$INSTDIR\docs"
  RMDir /r "$INSTDIR\ferramentas"

  ; 2) Copiar o árbore
  DetailPrint "$(TXT_INSTALANDO)"
  SetDetailsPrint none
  !include "${XERADO}\arbore.nsh"
  SetDetailsPrint textonly

  ; 3) Ferramenta para o desinstalador
  SetOutPath "$INSTDIR\ferramentas"
  File "${RECURSOS}\pechar-programa.ps1"
  SetOutPath "$INSTDIR"

  ; 4) Accesos directos do menú Inicio
  DetailPrint "$(TXT_ACCESOS)"
  SetDetailsPrint none
  CreateDirectory "$SMPROGRAMS\${CARTAFOL_INICIO}"
  CreateShortcut "$SMPROGRAMS\${CARTAFOL_INICIO}\$(TXT_ACCESO_PROGRAMA).lnk" "$WINDIR\System32\wscript.exe" \
    '"$INSTDIR\Iniciar-Conversor.vbs"' "$INSTDIR\conversor.ico" 0 SW_SHOWNORMAL "" "${NOME_PROGRAMA}"
  !ifdef GALEGO
    CreateShortcut "$SMPROGRAMS\${CARTAFOL_INICIO}\$(TXT_ACCESO_MANUAL).lnk" "$INSTDIR\docs\10-Manual-do-conversor.pdf"
  !else
    CreateShortcut "$SMPROGRAMS\${CARTAFOL_INICIO}\$(TXT_ACCESO_MANUAL).lnk" "$INSTDIR\docs\es\10-Manual-del-conversor.pdf"
  !endif
  CreateShortcut "$SMPROGRAMS\${CARTAFOL_INICIO}\$(TXT_ACCESO_DESINSTALAR).lnk" "$INSTDIR\${NOME_DESINSTALADOR}" \
    "" "$INSTDIR\${NOME_DESINSTALADOR}" 0
  SetDetailsPrint textonly

  ; 5) Desinstalador + entrada en Aplicacións instaladas (só HKCU: sen UAC)
  DetailPrint "$(TXT_REXISTRO)"
  WriteUninstaller "$INSTDIR\${NOME_DESINSTALADOR}"
  !include "${XERADO}\tamano.nsh"
  WriteRegStr HKCU "${CLAVE_DESINSTALAR}" "DisplayName" "${NOME_PROGRAMA}"
  WriteRegStr HKCU "${CLAVE_DESINSTALAR}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${CLAVE_DESINSTALAR}" "Publisher" "${EDITOR}"
  WriteRegStr HKCU "${CLAVE_DESINSTALAR}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${CLAVE_DESINSTALAR}" "DisplayIcon" "$INSTDIR\conversor.ico"
  WriteRegStr HKCU "${CLAVE_DESINSTALAR}" "UninstallString" '"$INSTDIR\${NOME_DESINSTALADOR}"'
  WriteRegStr HKCU "${CLAVE_DESINSTALAR}" "QuietUninstallString" '"$INSTDIR\${NOME_DESINSTALADOR}" /S'
  WriteRegDWORD HKCU "${CLAVE_DESINSTALAR}" "EstimatedSize" ${TAMANO_KB}
  WriteRegDWORD HKCU "${CLAVE_DESINSTALAR}" "NoModify" 1
  WriteRegDWORD HKCU "${CLAVE_DESINSTALAR}" "NoRepair" 1

  ; 6) Aviso (non bloqueante) se falta WebView2
  ReadRegStr $0 HKLM "SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
  ${If} $0 == ""
    ReadRegStr $0 HKCU "Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
  ${EndIf}
  ${If} $0 == ""
    DetailPrint "$(TXT_SEN_WEBVIEW2)"
    IfSilent +2
    MessageBox MB_OK|MB_ICONINFORMATION "$(TXT_SEN_WEBVIEW2)"
  ${EndIf}
  SetDetailsPrint both
SectionEnd

; ------------------------------------------------------------ Desinstalador
Section "Uninstall"
  SetDetailsPrint textonly
  DetailPrint "$(TXT_DESINSTALANDO)"
  StrCpy $RutaPS1 "$INSTDIR\ferramentas\pechar-programa.ps1"
  Call un.PecharPrograma

  Delete "$SMPROGRAMS\${CARTAFOL_INICIO}\$(TXT_ACCESO_PROGRAMA).lnk"
  Delete "$SMPROGRAMS\${CARTAFOL_INICIO}\$(TXT_ACCESO_MANUAL).lnk"
  Delete "$SMPROGRAMS\${CARTAFOL_INICIO}\$(TXT_ACCESO_DESINSTALAR).lnk"
  RMDir "$SMPROGRAMS\${CARTAFOL_INICIO}"
  Delete "$DESKTOP\$(TXT_ACCESO_PROGRAMA).lnk"

  ; Só o que puxo esta instalación, nunca "$INSTDIR" enteiro.
  SetDetailsPrint none
  !include "${XERADO}\arbore-un.nsh"
  RMDir /r "$INSTDIR\runtime"
  RMDir /r "$INSTDIR\anonimizador-xuridico"
  RMDir /r "$INSTDIR\docs"
  SetDetailsPrint textonly
  Delete "$INSTDIR\Iniciar-Conversor.vbs"
  Delete "$INSTDIR\conversor.ico"
  RMDir /r "$INSTDIR\ferramentas"
  Delete "$INSTDIR\${NOME_DESINSTALADOR}"
  RMDir "$INSTDIR"

  DeleteRegKey HKCU "${CLAVE_DESINSTALAR}"
  ; Os datos de Documentos\Anonimizador son tamén do anonimizador: non se tocan.
  SetDetailsPrint both
SectionEnd
