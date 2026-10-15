; Instalador de Windows do Anonimizador de expedientes xuridicos (NSIS, MUI2).
;
; Xérase en CROSS-COMPILE dende o Mac/Linux con `makensis`, chamado dende
; `instalador/crear-paquetes.sh windows` -- non se executa a man (precisa os
; -D de abaixo e os .nsh xerados por `xerar_arbore_nsh.py`).
;
;   -DVERSION=...       texto de versión (ex. 20260919-abc1234)
;   -DVERSION_NUM=a.b.c.d   versión numérica para as propiedades do .exe
;   -DXERADO=...        cartafol cos .nsh xerados por xerar_arbore_nsh.py (arbore.nsh
;                       -- un File por ficheiro do árbore FINAL a instalar: Python
;                       xa con tódalas librarías dentro, Tesseract, código, docs --,
;                       arbore-un.nsh, tamano.nsh)
;   -DSAIDA=...         ruta do .exe resultante
;   -DRECURSOS=...      cartafol instalador/windows (icona, imaxes)
;   -DPROBA=1           (só desenvolvemento) sen compresión, para iterar rápido
;
; O instalador NON executa pip nin crea ningún venv: copia un árbore xa
; feito, así a barra de progreso é a de verdade. Instálase POR USUARIO
; (sen UAC): programa en %LOCALAPPDATA%\Programs\Anonimizador, e os datos
; do usuario (datos_rexistro, log) en %LOCALAPPDATA%\Anonimizador.

Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"
!include "WinMessages.nsh"
!include "nsDialogs.nsh"

Var RutaPS1   ; ruta do pechar-programa.ps1 (o do instalador vive en $PLUGINSDIR, o do desinstalador en $INSTDIR\ferramentas)

!ifndef VERSION
  !define VERSION "dev"
!endif
!ifndef VERSION_NUM
  !define VERSION_NUM "1.0.0.0"
!endif
!ifndef RECURSOS
  !define RECURSOS "."
!endif

!define NOME_PROGRAMA "Anonimizador de expedientes xurídicos"
!define CLAVE_DESINSTALAR "Software\Microsoft\Windows\CurrentVersion\Uninstall\AnonimizadorXuridico"
!define NOME_DESINSTALADOR "Desinstalar-Anonimizador.exe"
!define CARTAFOL_INICIO "Anonimizador xurídico"
!define EDITOR "JL López"

Name "${NOME_PROGRAMA}"
OutFile "${SAIDA}"
InstallDir "$LOCALAPPDATA\Programs\Anonimizador"
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

; ------------------------------------------------------------ Propiedades do .exe
VIProductVersion "${VERSION_NUM}"
; (as chaves VIAddVersionKey van máis abaixo, xa co idioma definido)

; ------------------------------------------------------------ Páxinas
!define MUI_ICON "${RECURSOS}\anonimizador.ico"
!define MUI_UNICON "${RECURSOS}\anonimizador.ico"
!define MUI_WELCOMEFINISHPAGE_BITMAP "${RECURSOS}\asistente.bmp"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "${RECURSOS}\asistente.bmp"
!define MUI_ABORTWARNING
!define MUI_UNABORTWARNING

!define MUI_WELCOMEPAGE_TITLE "$(TXT_BENVIDA_TITULO)"
!define MUI_WELCOMEPAGE_TEXT "$(TXT_BENVIDA)"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
; Páxina propia coa clave e a contrasinal (03/10/2026): na de remate o texto
; longo quedaba tapado polas casiñas e o usuario non chegaba a lelo.
Page custom PaxinaClave

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
; Galego se esta versión de NSIS o inclúe (si), senón castelán.
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

!insertmacro TEXTO TXT_BENVIDA_TITULO "Benvida ao instalador do Anonimizador" "Bienvenida al instalador del Anonimizador"
!insertmacro TEXTO TXT_BENVIDA "Este asistente instalará o ${NOME_PROGRAMA} no seu ordenador.$\r$\n$\r$\nO programa inclúe todo o necesario (Python, OCR e o modelo de idioma): non fai falta conexión a internet nin permisos de administrador.$\r$\n$\r$\nPreme Seguinte para continuar." "Este asistente instalará el ${NOME_PROGRAMA} en su ordenador.$\r$\n$\r$\nEl programa incluye todo lo necesario (Python, OCR y el modelo de idioma): no hace falta conexión a internet ni permisos de administrador.$\r$\n$\r$\nPulse Siguiente para continuar."
!insertmacro TEXTO TXT_FIN_TITULO "Instalación completada" "Instalación completada"
!insertmacro TEXTO TXT_FIN "O ${NOME_PROGRAMA} quedou instalado. Pode abrilo dende o menú Inicio.$\r$\n$\r$\nPara desinstalalo: Configuración > Aplicacións > Aplicacións instaladas, ou o acceso Desinstalar do menú Inicio." "El ${NOME_PROGRAMA} ha quedado instalado. Puede abrirlo desde el menú Inicio.$\r$\n$\r$\nPara desinstalarlo: Configuración > Aplicaciones > Aplicaciones instaladas, o el acceso Desinstalar del menú Inicio."
!insertmacro TEXTO TXT_CLAVE_TITULO "A clave e a contrasinal" "La clave y la contraseña"
!insertmacro TEXTO TXT_CLAVE_SUBTITULO "Como se gardan os nomes reais. Léeo antes de empezar." "Cómo se guardan los nombres reales. Léelo antes de empezar."
!insertmacro TEXTO TXT_CLAVE "Os nomes reais NON quedan nos documentos anonimizados: gárdanse nun rexistro CIFRADO que relaciona cada código (PERSOA_000001) coa persoa real e o seu DNI. Protéxeno DOUS segredos distintos:$\r$\n$\r$\n1) A CLAVE DO REXISTRO. Créaa o programa só e ninguén a escribe; queda no Administrador de credenciais de Windows. Sen ela o rexistro non se pode descifrar nunca máis. Fai copia de seguridade (a pantalla de inicio do programa di onde está).$\r$\n$\r$\n2) A CONTRASINAL DE REVERSIÓN. Escríbela ti unha vez, na pantalla de inicio do programa. Pídese cada vez que alguén quere ver unha identidade real, o listado completo de correspondencias ou o seu PDF CONFIDENCIAL, e cada uso queda nunha auditoría cifrada.$\r$\n$\r$\nO PDF do listado é un documento de extrema sensibilidade: non o envíes por correo nin o deixes nun cartafol compartido, e destrúeo cando xa non faga falta." "Los nombres reales NO quedan en los documentos anonimizados: se guardan en un registro CIFRADO que relaciona cada código (PERSOA_000001) con la persona real y su DNI. Lo protegen DOS secretos distintos:$\r$\n$\r$\n1) LA CLAVE DEL REGISTRO. La crea el programa y nadie la escribe; queda en el Administrador de credenciales de Windows. Sin ella el registro no se puede descifrar nunca más. Haz copia de seguridad (la pantalla de inicio del programa dice dónde está).$\r$\n$\r$\n2) LA CONTRASEÑA DE REVERSIÓN. La escribes tú una vez, en la pantalla de inicio del programa. Se pide cada vez que alguien quiere ver una identidad real, el listado completo de correspondencias o su PDF CONFIDENCIAL, y cada uso queda en una auditoría cifrada.$\r$\n$\r$\nEl PDF del listado es un documento de extrema sensibilidad: no lo envíes por correo ni lo dejes en una carpeta compartida, y destrúyelo cuando ya no haga falta."
!insertmacro TEXTO TXT_UN_FIN_TITULO "Desinstalación completada" "Desinstalación completada"
!insertmacro TEXTO TXT_UN_FIN "O ${NOME_PROGRAMA} foi eliminado deste ordenador." "El ${NOME_PROGRAMA} ha sido eliminado de este ordenador."
!insertmacro TEXTO TXT_ABRIR "Abrir o Anonimizador agora" "Abrir el Anonimizador ahora"
!insertmacro TEXTO TXT_ESCRITORIO "Crear un acceso directo no escritorio" "Crear un acceso directo en el escritorio"
!insertmacro TEXTO TXT_UN_BENVIDA_TITULO "Desinstalar o Anonimizador" "Desinstalar el Anonimizador"
!insertmacro TEXTO TXT_UN_BENVIDA "Vaise desinstalar o ${NOME_PROGRAMA} de:$\r$\n$\r$\n$INSTDIR$\r$\n$\r$\nOs rexistros cifrados de correspondencias non se borran sen preguntar antes.$\r$\n$\r$\nPreme Seguinte para continuar." "Se va a desinstalar el ${NOME_PROGRAMA} de:$\r$\n$\r$\n$INSTDIR$\r$\n$\r$\nLos registros cifrados de correspondencias no se borran sin preguntar antes.$\r$\n$\r$\nPulse Siguiente para continuar."
!insertmacro TEXTO TXT_ESTA_ABERTO "O Anonimizador está aberto. Para continuar hai que pechalo (garda antes o que estea a facer nel).$\r$\n$\r$\nPreme Aceptar para que o asistente o peche, ou Cancelar para saír." "El Anonimizador está abierto. Para continuar hay que cerrarlo (guarde antes lo que esté haciendo en él).$\r$\n$\r$\nPulse Aceptar para que el asistente lo cierre, o Cancelar para salir."
!insertmacro TEXTO TXT_NON_SE_PECHOU "Non se puido pechar o Anonimizador. Péchao a man e volve tentalo." "No se pudo cerrar el Anonimizador. Ciérrelo a mano y vuelva a intentarlo."
!insertmacro TEXTO TXT_SO_64 "Este programa só funciona en Windows de 64 bits." "Este programa solo funciona en Windows de 64 bits."
!insertmacro TEXTO TXT_LIMPANDO "Preparando a instalación (eliminando a versión anterior, se a hai)..." "Preparando la instalación (eliminando la versión anterior, si la hay)..."
!insertmacro TEXTO TXT_INSTALANDO "Instalando o programa..." "Instalando el programa..."
!insertmacro TEXTO TXT_ACCESOS "Creando os accesos directos..." "Creando los accesos directos..."
!insertmacro TEXTO TXT_REXISTRO "Rexistrando o programa en Aplicacións instaladas..." "Registrando el programa en Aplicaciones instaladas..."
!insertmacro TEXTO TXT_DESINSTALANDO "Desinstalando o programa..." "Desinstalando el programa..."
!insertmacro TEXTO TXT_ACCESO_PROGRAMA "${NOME_PROGRAMA}" "${NOME_PROGRAMA}"
!insertmacro TEXTO TXT_ACCESO_MANUAL "Manual de uso" "Manual de uso"
!insertmacro TEXTO TXT_ACCESO_DESINSTALAR "Desinstalar" "Desinstalar"
!insertmacro TEXTO TXT_SEN_WEBVIEW2 "Non se atopou o compoñente de Windows «Microsoft Edge WebView2 Runtime», que o programa usa para amosar a súa xanela. En Windows 11 vén instalado; en Windows 10 pódese descargar gratis de Microsoft. Se non está, o programa ofrecerá abrirse no navegador." "No se encontró el componente de Windows «Microsoft Edge WebView2 Runtime», que el programa usa para mostrar su ventana. En Windows 11 viene instalado; en Windows 10 se puede descargar gratis de Microsoft. Si no está, el programa ofrecerá abrirse en el navegador."
!insertmacro TEXTO TXT_PREGUNTA_DATOS "Queres borrar tamén os datos do programa?$\r$\n$\r$\nSon os rexistros cifrados de correspondencias (que nome real corresponde a cada marcador dos documentos anonimizados), en:$\r$\n$LOCALAPPDATA\Anonimizador\datos_rexistro$\r$\n$\r$\nATENCIÓN: sen eses rexistros NON se poderá reverter a anonimización dos documentos xa anonimizados. A clave de cifrado non se borra: queda no Administrador de credenciais de Windows.$\r$\n$\r$\nO recomendable é NON borralos, por se volves instalar o programa máis adiante." "¿Desea borrar también los datos del programa?$\r$\n$\r$\nSon los registros cifrados de correspondencias (qué nombre real corresponde a cada marcador de los documentos anonimizados), en:$\r$\n$LOCALAPPDATA\Anonimizador\datos_rexistro$\r$\n$\r$\nATENCIÓN: sin esos registros NO se podrá revertir la anonimización de los documentos ya anonimizados. La clave de cifrado no se borra: queda en el Administrador de credenciales de Windows.$\r$\n$\r$\nLo recomendable es NO borrarlos, por si vuelve a instalar el programa más adelante."

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
  Exec '"$WINDIR\System32\wscript.exe" "$INSTDIR\Iniciar-Anonimizador.vbs"'
FunctionEnd

Function CrearAccesoEscritorio
  SetOutPath "$INSTDIR"
  CreateShortcut "$DESKTOP\$(TXT_ACCESO_PROGRAMA).lnk" "$WINDIR\System32\wscript.exe" \
    '"$INSTDIR\Iniciar-Anonimizador.vbs"' "$INSTDIR\anonimizador.ico" 0 SW_SHOWNORMAL "" "${NOME_PROGRAMA}"
FunctionEnd


Function PaxinaClave
  !insertmacro MUI_HEADER_TEXT "$(TXT_CLAVE_TITULO)" "$(TXT_CLAVE_SUBTITULO)"
  nsDialogs::Create 1018
  Pop $0
  ${If} $0 == error
    Abort
  ${EndIf}
  ${NSD_CreateLabel} 0 0 100% 100% "$(TXT_CLAVE)"
  Pop $1
  nsDialogs::Show
FunctionEnd

Section "Anonimizador" SecPrincipal
  SectionIn RO
  InitPluginsDir
  SetDetailsPrint textonly

  ; 1) Pechar o programa se estivese aberto e limpar unha instalación previa
  ;    (evita ficheiros orfos dunha versión anterior; os datos do usuario
  ;    viven noutro cartafol e non se tocan).
  StrCpy $RutaPS1 "$PLUGINSDIR\pechar-programa.ps1"
  File "/oname=$RutaPS1" "${RECURSOS}\pechar-programa.ps1"
  Call PecharPrograma
  DetailPrint "$(TXT_LIMPANDO)"
  RMDir /r "$INSTDIR\runtime"
  RMDir /r "$INSTDIR\anonimizador-xuridico"
  RMDir /r "$INSTDIR\docs"
  RMDir /r "$INSTDIR\ferramentas"

  ; 2) Copiar o árbore (o texto "NN %" actualízao ActualizarPct)
  DetailPrint "$(TXT_INSTALANDO)"
  SetDetailsPrint none
  !include "${XERADO}\arbore.nsh"
  SetDetailsPrint textonly

  ; 3) Ferramenta para o desinstalador (que non pode extraer ficheiros)
  SetOutPath "$INSTDIR\ferramentas"
  File "${RECURSOS}\pechar-programa.ps1"
  SetOutPath "$INSTDIR"

  ; 4) Accesos directos do menú Inicio
  DetailPrint "$(TXT_ACCESOS)"
  SetDetailsPrint none   ; senón o texto de estado amosa "Criando diretoría: ..." en vez do noso
  CreateDirectory "$SMPROGRAMS\${CARTAFOL_INICIO}"
  CreateShortcut "$SMPROGRAMS\${CARTAFOL_INICIO}\$(TXT_ACCESO_PROGRAMA).lnk" "$WINDIR\System32\wscript.exe" \
    '"$INSTDIR\Iniciar-Anonimizador.vbs"' "$INSTDIR\anonimizador.ico" 0 SW_SHOWNORMAL "" "${NOME_PROGRAMA}"
  CreateShortcut "$SMPROGRAMS\${CARTAFOL_INICIO}\$(TXT_ACCESO_MANUAL).lnk" "$INSTDIR\docs\03-Manual-de-uso.pdf"
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
  WriteRegStr HKCU "${CLAVE_DESINSTALAR}" "DisplayIcon" "$INSTDIR\anonimizador.ico"
  WriteRegStr HKCU "${CLAVE_DESINSTALAR}" "UninstallString" '"$INSTDIR\${NOME_DESINSTALADOR}"'
  WriteRegStr HKCU "${CLAVE_DESINSTALAR}" "QuietUninstallString" '"$INSTDIR\${NOME_DESINSTALADOR}" /S'
  WriteRegDWORD HKCU "${CLAVE_DESINSTALAR}" "EstimatedSize" ${TAMANO_KB}
  WriteRegDWORD HKCU "${CLAVE_DESINSTALAR}" "NoModify" 1
  WriteRegDWORD HKCU "${CLAVE_DESINSTALAR}" "NoRepair" 1

  ; 6) Aviso (non bloqueante) se falta WebView2: sen el, a xanela do programa
  ;    non abre e o programa ofrece caer ao navegador.
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

  ; O pechar-programa.ps1 vén da instalación (o desinstalador non pode extraer ficheiros)
  StrCpy $RutaPS1 "$INSTDIR\ferramentas\pechar-programa.ps1"
  Call un.PecharPrograma

  ; Accesos directos
  Delete "$SMPROGRAMS\${CARTAFOL_INICIO}\$(TXT_ACCESO_PROGRAMA).lnk"
  Delete "$SMPROGRAMS\${CARTAFOL_INICIO}\$(TXT_ACCESO_MANUAL).lnk"
  Delete "$SMPROGRAMS\${CARTAFOL_INICIO}\$(TXT_ACCESO_DESINSTALAR).lnk"
  RMDir "$SMPROGRAMS\${CARTAFOL_INICIO}"
  Delete "$DESKTOP\$(TXT_ACCESO_PROGRAMA).lnk"

  ; Ficheiros do programa: cartafol a cartafol (a barra avanza de verdade).
  ; Bórrase SÓ o que puxo esta instalación -- nunca "$INSTDIR" enteiro, por se
  ; o usuario a puxo nun cartafol que xa tiña outras cousas.
  SetDetailsPrint none
  !include "${XERADO}\arbore-un.nsh"
  RMDir /r "$INSTDIR\runtime"
  RMDir /r "$INSTDIR\anonimizador-xuridico"
  RMDir /r "$INSTDIR\docs"
  SetDetailsPrint textonly
  Delete "$INSTDIR\Iniciar-Anonimizador.vbs"
  Delete "$INSTDIR\anonimizador.ico"
  RMDir /r "$INSTDIR\ferramentas"
  Delete "$INSTDIR\${NOME_DESINSTALADOR}"
  RMDir "$INSTDIR"

  DeleteRegKey HKCU "${CLAVE_DESINSTALAR}"

  ; Datos do usuario: NUNCA se borran sen preguntar (e en modo silencioso, nunca).
  StrCpy $1 "$LOCALAPPDATA\Anonimizador"
  ${If} ${FileExists} "$1\datos_rexistro"
    StrCpy $2 "NON"
    IfSilent +3
    MessageBox MB_YESNO|MB_ICONEXCLAMATION|MB_DEFBUTTON2 "$(TXT_PREGUNTA_DATOS)" IDNO +2
    StrCpy $2 "SI"
    ${If} $2 == "SI"
      RMDir /r "$1"
    ${EndIf}
  ${EndIf}
  ; Sen rexistros que conservar (ou sen borralos): só se quita o log de diagnóstico
  ; e o cartafol, se quedou baleiro.
  Delete "$1\anonimizador.log"
  Delete "$1\anonimizador.log.*"
  RMDir "$1"
  SetDetailsPrint both
SectionEnd
