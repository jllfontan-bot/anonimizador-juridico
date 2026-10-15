"""Fai as capturas da interface web para o manual de uso (docs/fonte/img/).

Arrinca o programa nun porto de proba (5099) cun expediente de exemplo
SINTÉTICO (datos_exemplo.py) e captura cada pantalla con Chrome (Playwright).
Nunca se usan documentos reais.

Uso (dende a raíz do repo; playwright vén co python3 do sistema):
    python3 docs/fonte/capturar_pantallas.py [cartafol-base]
O cartafol-base (por defecto /Users/Shared) leva un cartafol Expediente_0142
e un datos_rexistro; bórranse ao acabar. As capturas da instalación en
Windows (asistente, SmartScreen, desinstalador) fixéronse a man nunha
máquina virtual Windows 11 e non se xeran con este script."""
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parents[2]
IMG = Path(__file__).resolve().parent / "img"
PORTO = 5099
URL = f"http://127.0.0.1:{PORTO}"
BASE = Path(sys.argv[1] if len(sys.argv) > 1 else "/Users/Shared")
PY = RAIZ / ".venv" / "bin" / "python"


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
    for _ in range(600):
        txt = pg.inner_text("#progreso-ficheiro") if pg.is_visible("#progreso") else ""
        m = re.match(r"Ficheiro (\d+) de", txt)
        if m and int(m.group(1)) >= minimo and "restante" in pg.inner_text("#progreso-detalle"):
            break
        time.sleep(0.03)
    if cancelar:
        pg.click("#progreso-cancelar")
    time.sleep(0.45)  # deixa rematar a animación da barra
    pg.screenshot(path=str(IMG / nome), clip={"x": 0, "y": 0, "width": 980, "height": 410})
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
    exp = Path(subprocess.check_output([str(PY), str(RAIZ / "docs/fonte/datos_exemplo.py"), str(BASE)], text=True).strip())
    rex = BASE / "datos_rexistro"
    shutil.rmtree(rex, ignore_errors=True)
    env = {"PYTHONPATH": str(RAIZ / "src"), "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
           "HOME": str(Path.home())}
    servidor = subprocess.Popen([str(PY), "-m", "anonimizador.cli", "servir", "--porto", str(PORTO)],
                                cwd=BASE, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        esperar_servidor()
        with sync_playwright() as p:
            nav = p.chromium.launch(channel="chrome")
            ctx = nav.new_context(viewport={"width": 980, "height": 700}, device_scale_factor=2, locale="gl-ES")
            pg = ctx.new_page()

            def foto(nome, **kw):
                pg.screenshot(path=str(IMG / nome), **kw)
                print("captura", nome)

            # 1. pantalla inicial (dous modos)
            pg.goto(URL + "/")
            foto("inicio_revisar.png", full_page=True)
            pg.check('input[name="modo"][value="automatico"]')
            foto("inicio_automatico.png", full_page=True)
            pg.check('input[name="modo"][value="revisar"]')

            # 2. explorador de cartafoles
            pg.fill("#ruta", str(exp))
            pg.click("text=Escoller cartafol…")
            pg.wait_for_selector("#exp-lista li")
            time.sleep(0.4)
            foto("explorador.png")
            pg.click("#exp-cancelar")

            # 3. progreso do lote en modo REVISAR (cartafol enteiro)
            pg.click("#boton-procesar")
            captura_progreso(pg, "progreso_revisar.png", minimo=3)
            pg.wait_for_url(re.compile(r".*/traballo/.*/resultado"), timeout=90000)
            time.sleep(0.8)
            foto("inicio_pendentes.png", full_page=True)

            # 4. pantalla de revisión dun documento (con posibles fugas)
            pg.goto(URL + "/")
            pg.fill("#ruta", str(exp / "03_notificacion_xulgado.pdf"))
            pg.click("#boton-procesar")
            pg.wait_for_url(re.compile(r".*/revisar/.*"), timeout=60000)
            time.sleep(0.6)
            foto("revision_fugas.png", clip={"x": 0, "y": 0, "width": 980, "height": 880})

            # 5. progreso do lote en modo AUTOMÁTICO + resultado
            limpar_saidas(exp)
            pg.goto(URL + "/")
            pg.fill("#ruta", str(exp))
            pg.check('input[name="modo"][value="automatico"]')
            pg.click("#boton-procesar")
            captura_progreso(pg, "progreso_automatico.png", minimo=3)
            pg.wait_for_url(re.compile(r".*/traballo/.*/resultado"), timeout=90000)
            time.sleep(0.6)
            foto("resultado_automatico.png", full_page=True)

            # 6. lote cancelado
            limpar_saidas(exp)
            pg.goto(URL + "/")
            pg.fill("#ruta", str(exp))
            pg.check('input[name="modo"][value="automatico"]')
            pg.click("#boton-procesar")
            captura_progreso(pg, "progreso_cancelar.png", minimo=3, cancelar=True)
            pg.wait_for_url(re.compile(r".*/traballo/.*/resultado"), timeout=90000)
            time.sleep(0.6)
            foto("resultado_cancelado.png", full_page=True)

            # 7. contrasinal de reversión e reversión controlada
            pg.goto(URL + "/definir-contrasinal")
            foto("definir_contrasinal.png", full_page=True)
            pg.fill("#nova", "contrasinal-exemplo-1")
            pg.fill("#confirmacion", "contrasinal-exemplo-1")
            pg.click("button[type=submit]")
            pg.goto(URL + "/reverter")
            pg.fill("#codigo", "PERSOA_000001")
            pg.fill("#motivo", "presentación do orixinal no xulgado")
            pg.fill("#contrasinal", "contrasinal-exemplo-1")
            foto("reversion.png", full_page=True)
            pg.click("button[type=submit]")
            time.sleep(0.5)
            foto("reversion_resultado.png", full_page=True)
            nav.close()
        for n in ("inicio_revisar", "inicio_automatico", "inicio_pendentes", "resultado_automatico",
                  "resultado_cancelado", "definir_contrasinal", "reversion", "reversion_resultado"):
            recortar_baleiro(n + ".png")
    finally:
        servidor.terminate()
        shutil.rmtree(rex, ignore_errors=True)
        shutil.rmtree(exp, ignore_errors=True)


if __name__ == "__main__":
    main()
