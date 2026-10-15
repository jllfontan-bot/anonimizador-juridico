"""Fai as capturas da interface web para o manual de uso, nun idioma.

Arrinca o programa nun porto de proba (5099) cun expediente de exemplo
SINTÉTICO (datos_exemplo.py) e captura cada pantalla con Chrome (Playwright).
Nunca se usan documentos reais.

Uso (dende a raíz do repo; playwright vén co python3 do sistema):
    python3 docs/fonte/capturar_pantallas.py [gl|es] [cartafol-base]
As capturas van a docs/fonte/img/ (galego) ou docs/fonte/img/es/ (castelán).
O cartafol-base (por defecto /tmp/Despacho) leva un cartafol Expediente_0142
e un datos_rexistro; bórranse ao acabar. O Python do programa é o de
`.venv/bin/python` ou o que diga a variable ANONIMIZADOR_PYTHON. As capturas
da instalación en Windows (asistente, SmartScreen, desinstalador) fixéronse
a man nunha máquina virtual e non se xeran con este script."""
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parents[2]
LINGUA = sys.argv[1] if len(sys.argv) > 1 else "gl"
IMG = Path(__file__).resolve().parent / ("img" if LINGUA == "gl" else f"img/{LINGUA}")
PORTO = 5099
URL = f"http://127.0.0.1:{PORTO}"
BASE = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/Despacho")
PY = Path(os.environ.get("ANONIMIZADOR_PYTHON", RAIZ / ".venv" / "bin" / "python"))

# Textos da interface que o script ten que atopar, e datos do formulario.
T = {
    "gl": {"escoller_cartafol": "Escoller cartafol…", "ficheiro": "Ficheiro", "locale": "gl-ES",
           "codigo": "PERSOA_000001", "motivo": "presentación do orixinal no xulgado",
           "contrasinal": "contrasinal-exemplo-1"},
    "es": {"escoller_cartafol": "Elegir carpeta…", "ficheiro": "Archivo", "locale": "es-ES",
           "codigo": "PERSONA_000001", "motivo": "presentación del original en el juzgado",
           "contrasinal": "contrasena-ejemplo-1"},
}[LINGUA]


CHAVEIRO_PROBA = """from keyring.backend import KeyringBackend


class Memoria(KeyringBackend):
    priority = 1
    _datos = {}

    def get_password(self, servizo, usuario):
        return self._datos.get((servizo, usuario))

    def set_password(self, servizo, usuario, contrasinal):
        self._datos[(servizo, usuario)] = contrasinal

    def delete_password(self, servizo, usuario):
        self._datos.pop((servizo, usuario), None)
"""


def esperar_servidor():
    for _ in range(60):
        try:
            urllib.request.urlopen(URL + "/", timeout=1)
            return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("o servidor non arrincou")


def captura_progreso(pg, nome, minimo=4, cancelar=False):
    """Agarda a que o lote vaia polo ficheiro `minimo` e fai a captura."""
    pg.evaluate("document.querySelectorAll('details').forEach(d => d.open = false); window.scrollTo(0, 0)")
    limite = time.time() + 600  # neste ordenador o primeiro ficheiro pode tardar bastante
    while time.time() < limite:
        txt = pg.inner_text("#progreso-ficheiro") if pg.is_visible("#progreso") else ""
        m = re.match(T["ficheiro"] + r" (\d+) de", txt)
        if m and int(m.group(1)) >= minimo and "restante" in pg.inner_text("#progreso-detalle"):
            break
        time.sleep(0.03)
    else:
        raise RuntimeError(f"{nome}: o lote non chegou ao ficheiro {minimo}")
    if cancelar:
        pg.click("#progreso-cancelar")
    time.sleep(0.45)  # deixa rematar a animación da barra
    caixa = pg.locator("#progreso").bounding_box()
    pg.screenshot(path=str(IMG / nome), clip={"x": 0, "y": 0, "width": 980, "height": caixa["y"] + caixa["height"] + 30})
    print("captura", nome)


def recortar_baleiro(nome, marxe=40):
    """Quita o baleiro sobrante ao pé das capturas de páxina completa."""
    from PIL import Image, ImageChops
    im = Image.open(IMG / nome).convert("RGB")
    fondo = Image.new("RGB", im.size, im.getpixel((2, im.height - 2)))
    caixa = ImageChops.difference(im, fondo).getbbox()
    if caixa:
        im.crop((0, 0, im.width, min(im.height, caixa[3] + marxe * 2))).save(IMG / nome)


def limpar_saidas(exp):
    """Borra os .anonimizado.* dun lote anterior (senón o seguinte lote tamén os procesa)."""
    for f in exp.rglob("*.anonimizado.*"):
        f.unlink()


def main():
    IMG.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(BASE, ignore_errors=True)
    BASE.mkdir(parents=True)
    saida = subprocess.check_output(
        [str(PY), str(RAIZ / "docs/fonte/datos_exemplo.py"), str(BASE), LINGUA], text=True)
    exp = Path(saida.strip().splitlines()[-1])  # PyMuPDF pode escribir avisos antes da ruta
    rex = BASE / "datos_rexistro"
    # A clave vai nun "chaveiro" en memoria, coma a do programa instalado en
    # Windows (Administrador de credenciais); así as pantallas din o mesmo
    # ca alí e non se toca o chaveiro real de quen fai as capturas.
    (BASE / "chaveiro_proba.py").write_text(CHAVEIRO_PROBA)
    env = {"PYTHONPATH": f"{RAIZ / 'src'}:{BASE}", "PATH": "/usr/bin:/bin:/usr/local/bin",
           "HOME": str(Path.home()), "ANONIMIZADOR_IDIOMA": LINGUA,
           "PYTHON_KEYRING_BACKEND": "chaveiro_proba.Memoria"}
    servidor = subprocess.Popen([str(PY), "-m", "anonimizador.cli", "servir", "--porto", str(PORTO),
                                 "--chaveiro-sistema"],
                                cwd=BASE, env=env, stdout=subprocess.DEVNULL, stderr=open(BASE / "servidor.log", "w"))
    try:
        esperar_servidor()
        with sync_playwright() as p:
            nav = p.chromium.launch(channel="chrome")
            ctx = nav.new_context(viewport={"width": 980, "height": 700}, device_scale_factor=2, locale=T["locale"])
            pg = ctx.new_page()

            def foto(nome, **kw):
                pg.screenshot(path=str(IMG / nome), **kw)
                print("captura", nome)

            def revisar(ruta, rexistro=None):
                pg.goto(URL + "/")
                pg.fill("#ruta", str(ruta))
                pg.fill("#rexistro", str(rexistro or rex))
                pg.click("#boton-procesar")
                pg.wait_for_url(re.compile(r".*/revisar/.*"), timeout=300000)
                time.sleep(0.6)

            def confirmar():
                pg.click("form[action*='confirmar'] button[type=submit]")
                pg.wait_for_load_state()
                time.sleep(0.5)

            # 1. pantalla inicial (dous modos)
            pg.goto(URL + "/")
            foto("inicio_revisar.png", full_page=True)
            pg.check('input[name="modo"][value="automatico"]')
            foto("inicio_automatico.png", full_page=True)
            pg.check('input[name="modo"][value="revisar"]')

            # 2. explorador de cartafoles
            pg.fill("#ruta", str(exp))
            pg.fill("#rexistro", str(rex))
            pg.click(f"text={T['escoller_cartafol']}")
            pg.wait_for_selector("#exp-lista li")
            time.sleep(0.4)
            foto("explorador.png")
            pg.click("#exp-cancelar")

            # 3. progreso do lote en modo REVISAR (cartafol enteiro)
            pg.click("#boton-procesar")
            captura_progreso(pg, "progreso_revisar.png", minimo=3)
            pg.wait_for_url(re.compile(r".*/traballo/.*/resultado"), timeout=900000)
            time.sleep(0.8)
            foto("inicio_pendentes.png", full_page=True)
            # as mesmas revisións, recuperadas co campo "Ver revisións pendentes"
            pg.goto(URL + "/?rexistro=" + str(rex))
            pg.locator("ul.pendentes").scroll_into_view_if_needed()
            foto("pendentes_sesions.png")

            # 4. pantalla de revisión dun documento (con posibles fugas)
            revisar(exp / "03_notificacion_xulgado.pdf")
            foto("revision_fugas.png", clip={"x": 0, "y": 0, "width": 980, "height": 880})

            # 5. progreso do lote en modo AUTOMÁTICO + resultado
            limpar_saidas(exp)
            pg.goto(URL + "/")
            pg.fill("#ruta", str(exp))
            pg.fill("#rexistro", str(rex))
            pg.check('input[name="modo"][value="automatico"]')
            pg.click("#boton-procesar")
            captura_progreso(pg, "progreso_automatico.png", minimo=3)
            pg.wait_for_url(re.compile(r".*/traballo/.*/resultado"), timeout=900000)
            time.sleep(0.6)
            foto("resultado_automatico.png", full_page=True)

            # 6. lote cancelado
            limpar_saidas(exp)
            pg.goto(URL + "/")
            pg.fill("#ruta", str(exp))
            pg.fill("#rexistro", str(rex))
            pg.check('input[name="modo"][value="automatico"]')
            pg.click("#boton-procesar")
            captura_progreso(pg, "progreso_cancelar.png", minimo=3, cancelar=True)
            pg.wait_for_url(re.compile(r".*/traballo/.*/resultado"), timeout=900000)
            time.sleep(0.6)
            foto("resultado_cancelado.png", full_page=True)

            # 7. confirmación dun documento sen dúbidas, nun rexistro novo
            rex_h = BASE / "rexistro_homonimos"
            revisar(exp / "Anexos" / "anexo_a_testemuno.txt", rex_h)
            confirmar()
            foto("confirmado_1.png", full_page=True)

            # 8. homónimos: a acta nomea as dúas persoas SEN DNI e xa están nese
            # rexistro -> códigos novos, avisados coma posibles homónimos (quedan
            # sempre coma persoas distintas: a revisión xa non fusiona)
            limpar_saidas(exp)
            revisar(exp / "05_acta_reunion.docx", rex_h)
            foto("rev_homonimo.png", full_page=True)

            # 9. un PDF: revisión e confirmación (gárdase coma .pdf)
            revisar(exp / "07_resolucion.pdf")
            foto("pdf_revision.png", clip={"x": 0, "y": 0, "width": 980, "height": 700})
            confirmar()
            foto("pdf_confirmado.png", full_page=True)

            # 10. contrasinal de reversión e reversión controlada
            pg.goto(URL + "/definir-contrasinal?rexistro=" + str(rex))
            foto("definir_contrasinal.png", full_page=True)
            pg.fill("#nova", T["contrasinal"])
            pg.fill("#confirmacion", T["contrasinal"])
            pg.click("button[type=submit]")
            pg.goto(URL + "/reverter")
            pg.fill("#rexistro", str(rex))
            pg.fill("#codigo", T["codigo"])
            pg.fill("#motivo", T["motivo"])
            pg.fill("#contrasinal", T["contrasinal"])
            foto("reversion.png", full_page=True)
            pg.click("button[type=submit]")
            time.sleep(0.5)
            foto("reversion_resultado.png", full_page=True)
            nav.close()
        for n in ("inicio_revisar", "inicio_automatico", "inicio_pendentes", "resultado_automatico",
                  "resultado_cancelado", "definir_contrasinal", "reversion", "reversion_resultado",
                  "rev_homonimo", "confirmado_1", "pdf_confirmado"):
            recortar_baleiro(n + ".png")
    finally:
        servidor.terminate()
        shutil.rmtree(BASE, ignore_errors=True)


if __name__ == "__main__":
    main()
