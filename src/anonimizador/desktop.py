"""Versión de escritorio: a MESMA interface web (`web.py`), nunha xanela
nativa do sistema operativo (`pywebview`) en vez de nunha pestana do
navegador -- sen chrome de navegador (barra de enderezos, pestanas...),
coma unha aplicación de escritorio normal. Non se reescribe ningunha
parte da interface: pywebview simplemente amosa a mesma app Flask, que
segue a correr só en 127.0.0.1 coma sempre.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path

_TAMANO_MAXIMO_LOG = 1_000_000  # bytes -- pasado isto o rexistro reinicíase, non medra sen límite


def _redirixir_saidas_se_non_hai_consola() -> Path | None:
    """`pythonw.exe` (Windows, sen consola -- coma lanza o acceso directo
    do programa instalado) deixa `sys.stdout`/`sys.stderr` en `None`: nin
    un `print` nin os avisos do servidor se ven en ningures, e un erro ao
    arrincar a xanela non deixaría rastro ningún. Nese caso redirixese
    todo a `anonimizador.log` no cartafol de traballo (o mesmo onde vive
    `datos_rexistro`). Se xa hai consola ou un ficheiro (ex. `> log`
    nun script de arranque), non se toca nada. Devolve a ruta do log, ou
    `None` se non fixo falta."""
    if sys.stdout is not None and sys.stderr is not None:
        return None

    ruta = Path.cwd() / "anonimizador.log"
    try:
        if ruta.exists() and ruta.stat().st_size > _TAMANO_MAXIMO_LOG:
            ruta.write_text("", encoding="utf-8")
        saida = open(ruta, "a", encoding="utf-8", buffering=1)  # 1 = liña a liña
    except OSError:
        saida = open(os.devnull, "w")

    if sys.stdout is None:
        sys.stdout = saida
    if sys.stderr is None:
        sys.stderr = saida
    print(f"--- arranque {datetime.now().isoformat(timespec='seconds')} ---")
    return ruta


# IMPORTANTE: antes de `import webview`. Ao importarse, pywebview (`webview/http.py`)
# substitúe `sys.stdout`/`sys.stderr` por `os.devnull` se son `None` -- despois
# diso xa non habería xeito de saber que non hai consola, e o log nunca se
# escribiría (bug real visto en Windows con `pythonw.exe`).
_redirixir_saidas_se_non_hai_consola()

import webview

from . import idioma, web

# O título da xanela e do botón vai no idioma escollido: idioma.t("app.nome").

# Por defecto pywebview manda AO NAVEGADOR DO SISTEMA calquera petición de
# "xanela nova" (target="_blank", window.open, Ctrl+clic ou clic co botón
# central sobre unha ligazón) -- así é como unha pestana do Edge/Chrome
# aparecía de súpeto, fóra da xanela do programa, ao premer nunha ligazón
# interna da propia aplicación. Aquí todas as ligazóns son internas
# (127.0.0.1): cárganse sempre na MESMA xanela.
webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = False


# -- Barra de tareas de Windows: anclar a app e volver abrila --------------------
#
# Sen isto, ao anclar á barra de tareas a app YA ABERTA, Windows ancla o
# executable do PROCESO que ten a xanela -- `pythonw.exe`, sen argumentos --, e
# ao pechar o programa e premer nesa icona non arrinca nada (só un pythonw
# baleiro). A solución oficial: (1) unha identidade propia (AppUserModelID) e
# (2) as propiedades "relanzamento" da xanela, que din a Windows QUE COMANDO
# executar ao premer a icona anclada (o lanzador `.vbs` do programa instalado),
# co seu nome e icona. Ver `instalador/windows/`.
_AUMID = "JLLopez.AnonimizadorXuridico"


def e_paquete_msix() -> bool:
    """`True` se o proceso corre dende un paquete MSIX (Microsoft Store).
    Aí Windows xa lle dá ao programa a identidade do paquete (botón da
    barra de tareas, anclar, reabrir): fixar outra rompería iso."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        lonxitude = ctypes.c_uint32(0)
        APPMODEL_ERROR_NO_PACKAGE = 15700
        return ctypes.windll.kernel32.GetCurrentPackageFullName(ctypes.byref(lonxitude), None) != APPMODEL_ERROR_NO_PACKAGE
    except Exception:
        return False


def _establecer_identidade_windows() -> None:
    """Debe chamarse ANTES de crear a xanela."""
    if sys.platform != "win32" or e_paquete_msix():
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(_AUMID)
    except Exception as e:  # nunca romper o arranque por isto
        print(f"Non se puido fixar a identidade da app na barra de tareas: {e!r}")


def _comando_de_relanzamento() -> tuple[str, str | None] | None:
    """(comando, icona) co que Windows debe reabrir o programa dende a barra
    de tareas, ou `None` se non é unha instalación (desenvolvemento)."""
    instalacion = Path(__file__).resolve().parents[3]
    lanzador = instalacion / "Iniciar-Anonimizador.vbs"
    if not lanzador.is_file():
        return None
    wscript = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "wscript.exe"
    icona = instalacion / "anonimizador.ico"
    return f'"{wscript}" "{lanzador}"', (f"{icona},0" if icona.is_file() else None)


def _configurar_boton_da_barra(hwnd: int) -> bool:
    """Fixa na xanela `hwnd` a identidade e o comando de relanzamento. Devolve
    `True` se se gardaron; nunca lanza (só escribe no rexistro)."""
    if sys.platform != "win32":
        return False
    try:
        import pythoncom
        from win32com.propsys import propsys, pscon

        pythoncom.CoInitialize()
        almacen = propsys.SHGetPropertyStoreForWindow(hwnd, propsys.IID_IPropertyStore)
        almacen.SetValue(pscon.PKEY_AppUserModel_ID, propsys.PROPVARIANTType(_AUMID))
        relanzamento = _comando_de_relanzamento()
        if relanzamento is not None:
            comando, icona = relanzamento
            almacen.SetValue(pscon.PKEY_AppUserModel_RelaunchCommand, propsys.PROPVARIANTType(comando))
            almacen.SetValue(pscon.PKEY_AppUserModel_RelaunchDisplayNameResource, propsys.PROPVARIANTType(idioma.t("app.nome")))
            if icona:
                almacen.SetValue(pscon.PKEY_AppUserModel_RelaunchIconResource, propsys.PROPVARIANTType(icona))
        almacen.Commit()
        return True
    except Exception as e:
        print(f"Non se puido configurar o botón da barra de tareas: {e!r}")
        return False


def _ao_amosar_xanela(xanela) -> None:
    try:
        _configurar_boton_da_barra(int(xanela.native.Handle.ToInt64()))
    except Exception as e:
        print(f"Non se puido obter a xanela nativa para a barra de tareas: {e!r}")


def _preguntar_abrir_no_navegador(motivo: Exception) -> bool:
    """En Windows a xanela do programa NUNCA debería caer en silencio ao
    navegador -- unha pestana de Edge que aparece soa, sen avisar, parece
    un fallo do programa. Se a xanela nativa non pode abrirse (ex. falta o
    compoñente WebView2), pregúntase ao usuario, co motivo, se quere usar o
    navegador. Noutros sistemas (Linux sen GTK/WebKit2, o caso normal
    desta reserva) segue a abrirse o navegador directamente, sen preguntar."""
    if sys.platform != "win32":
        return True
    import ctypes

    MB_YESNO, MB_ICONWARNING, IDYES = 0x04, 0x30, 6
    texto = idioma.t("desktop.sen_xanela", motivo=idioma.traducir_mensaxe(str(motivo)))
    return ctypes.windll.user32.MessageBoxW(None, texto, idioma.t("app.nome"), MB_YESNO | MB_ICONWARNING) == IDYES


def _icona() -> str | None:
    """`anonimizador.ico` na raíz do programa instalado (Windows, ver
    `instalador/windows/`): sen isto a xanela e a barra de tarefas amosan a
    icona xenérica de Python. En desenvolvemento non existe -> `None`."""
    candidata = Path(__file__).resolve().parents[3] / "anonimizador.ico"
    return str(candidata) if candidata.is_file() else None


# GUIDs de EdgeUpdate onde WebView2 rexistra a versión instalada (`pv`):
# runtime normal, beta, dev e canary -- os mesmos que mira pywebview.
_GUIDS_WEBVIEW2 = (
    "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
    "{2CD8A007-E189-409D-A2C8-9AF4EF3C72AA}",
    "{0D50BFEC-CD6A-4F9A-964C-C7416E3ACB10}",
    "{65C35B14-6C1D-4122-AC46-7148CC9D6497}",
)


def _webview2_instalado() -> bool:
    """Só Windows. Sen o compoñente «Microsoft Edge WebView2 Runtime»
    (Windows 10 sen actualizar; en Windows 11 vén de serie) pywebview NON
    falla: cae EN SILENCIO ao motor de Internet Explorer (MSHTML), que non
    soporta esta páxina e deixaría unha xanela rota, sen ningún erro que
    `executar` puidese atrapar. Por iso hai que comprobalo antes. Noutros
    sistemas devolve sempre `True`."""
    if sys.platform != "win32":
        return True
    import winreg

    raices = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE"),
    )
    for guid in _GUIDS_WEBVIEW2:
        for raiz, base in raices:
            try:
                with winreg.OpenKey(raiz, rf"{base}\Microsoft\EdgeUpdate\Clients\{guid}") as clave:
                    versión, _ = winreg.QueryValueEx(clave, "pv")
            except OSError:
                continue
            if versión and versión != "0.0.0.0":
                return True
    return False


def _agardar_servidor(porto: int, intentos: int = 50, espera: float = 0.1) -> None:
    """O servidor Flask arranca nun fío á parte -- agarda a que responda
    antes de abrir a xanela, para non amosar un erro de conexión por
    chegar unhas décimas de segundo demasiado pronto."""
    url = f"http://127.0.0.1:{porto}/"
    for _ in range(intentos):
        try:
            urllib.request.urlopen(url, timeout=0.5)
            return
        except Exception:
            time.sleep(espera)


def executar(porto: int = 5000, usar_chaveiro: bool = False) -> None:
    fio_servidor = threading.Thread(
        target=web.executar,
        kwargs={"porto": porto, "usar_chaveiro": usar_chaveiro},
        daemon=True,  # remata coa xanela, sen deixar un proceso solto
    )
    fio_servidor.start()
    _agardar_servidor(porto)
    url = f"http://127.0.0.1:{porto}/"

    if not _webview2_instalado():
        motivo = RuntimeError("falta o compoñente de Windows «Microsoft Edge WebView2 Runtime»")
        print(f"Non se puido abrir a xanela de escritorio: {motivo}")
        if _preguntar_abrir_no_navegador(motivo):
            print("Abrindo no navegador.")
            webbrowser.open(url)
            fio_servidor.join()
        return

    try:
        _establecer_identidade_windows()
        xanela = webview.create_window(idioma.t("app.nome"), url, width=1100, height=800)
        if sys.platform == "win32" and not e_paquete_msix():
            xanela.events.shown += lambda: _ao_amosar_xanela(xanela)
        webview.start(icon=_icona())
    except Exception as e:
        # Reserva: en Linux, pywebview precisa GTK+WebKit2 (ou Qt) xa
        # instalados no sistema -- se faltan, `webview.start()` falla en
        # tempo de execución (non ao importar o paquete). Non deixar o
        # programa sen abrir por iso: cae ao comportamento de sempre
        # (navegador), có servidor xa arrincado no fío de fondo. En
        # Windows pregúntase antes (ver `_preguntar_abrir_no_navegador`).
        print(f"Non se puido abrir a xanela de escritorio: {e!r}")
        if not _preguntar_abrir_no_navegador(e):
            return
        print("Abrindo no navegador.")
        webbrowser.open(url)
        fio_servidor.join()
