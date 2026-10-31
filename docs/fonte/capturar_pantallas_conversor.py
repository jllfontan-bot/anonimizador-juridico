"""Fai as capturas da pantalla do Conversor de archivos para IA para o seu
manual, nun idioma.

A páxina é a real (`pantalla_conversor.html()`) e as chamadas da páxina van
á clase `Api` real, coma na xanela de pywebview: aquí Chrome (Playwright)
fai de xanela e unha ponte (`window.__api`) substitúe `js_api`. Os eventos
que a Api manda á páxina (progreso, revisión, resultado) chegan por unha
cola e pásanse á páxina dende o fío principal. Documentos SINTÉTICOS
(textos de `datos_exemplo.py`), nunca reais; rexistro e chaveiro de proba.

Uso (dende a raíz do repo, co Python do proxecto, que ten Playwright):
    .venv/bin/python docs/fonte/capturar_pantallas_conversor.py [gl|es] [cartafol-base]
As capturas van a docs/fonte/img/conversor/ (galego) ou
docs/fonte/img/es/conversor/ (castelán). O cartafol-base (por defecto
/tmp/Conversor) bórrase ao acabar. Deixa tamén alí, mentres corre, os .md
de exemplo que cita o manual.
"""

import json
import os
import queue
import shutil
import sys
import textwrap
import time
from email.message import EmailMessage
from pathlib import Path

LINGUA = sys.argv[1] if len(sys.argv) > 1 else "gl"
os.environ["ANONIMIZADOR_IDIOMA"] = LINGUA
RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import docx  # noqa: E402
import fitz  # noqa: E402
import openpyxl  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

import datos_exemplo  # noqa: E402
from anonimizador import pantalla_conversor  # noqa: E402

IMG = Path(__file__).resolve().parent / ("img/conversor" if LINGUA == "gl" else f"img/{LINGUA}/conversor")
BASE = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/Conversor")
ANCHO, ALTO, ESCALA = 980, 820, 2  # o tamaño da xanela do programa
# Coa variable CAPTURAS_STORE=<cartafol>: capturas para a ficha da Store, de
# 1920x1080 (a xanela enteira, sen recortes), nese cartafol.
STORE = os.environ.get("CAPTURAS_STORE")
if STORE:
    IMG = Path(STORE) / LINGUA
    ANCHO, ALTO, ESCALA = 1200, 675, 1.6

T = {
    "gl": {"pdf": "sentenza.pdf", "cabeceira": "XULGADO DE PRIMEIRA INSTANCIA N.º 2 DE LUGO", "sentenza": "SENTENZA 214/2026",
           "feitos": "ANTECEDENTES DE FEITO", "fundamentos": "FUNDAMENTOS DE DEREITO",
           "parrafo": "O xulgado examinou as probas achegadas polas partes no procedemento, ",
           "asunto": "Documentación do expediente 0142", "corpo": "Bo día:\n\nEnvío a documentación pendente do expediente.\n\nSaúdos,\nMarta",
           "concepto": "Concepto", "importe": "Importe", "taxas": "Taxas xudiciais", "perito": "Informe pericial",
           "interna": "Notas internas"},
    "es": {"pdf": "sentencia.pdf", "cabeceira": "JUZGADO DE PRIMERA INSTANCIA N.º 2 DE LUGO", "sentenza": "SENTENCIA 214/2026",
           "feitos": "ANTECEDENTES DE HECHO", "fundamentos": "FUNDAMENTOS DE DERECHO",
           "parrafo": "El juzgado ha examinado las pruebas aportadas por las partes en el procedimiento, ",
           "asunto": "Documentación del expediente 0142", "corpo": "Buenos días:\n\nEnvío la documentación pendiente del expediente.\n\nUn saludo,\nMarta",
           "concepto": "Concepto", "importe": "Importe", "taxas": "Tasas judiciales", "perito": "Informe pericial",
           "interna": "Notas internas"},
}[LINGUA]


def crear_documentos(exp: Path) -> list:
    exp.mkdir(parents=True)
    textos = datos_exemplo.TEXTOS[LINGUA]
    datos_exemplo.crear_docx(exp / "declaracion.docx", textos["DECLARACION"])
    # Texto distinto en cada páxina (liñas iguais en todas tomaríanse por
    # cabeceiras repetidas); só a cabeceira do xulgado e o número se repiten.
    corpo = textwrap.wrap(" ".join((textos["NOTIFICACION"] + " " + textos["INFORME"] + " "
                                    + textos["DECLARACION"]).split()), 92)
    pdf = fitz.open()
    for n in range(1, 4):
        paxina = pdf.new_page()
        paxina.insert_text((72, 50), T["cabeceira"], fontsize=8)
        y = 110
        if n == 1:
            paxina.insert_text((72, y), T["sentenza"], fontsize=16)
            y += 40
        if n != 2:
            paxina.insert_text((72, y), T["feitos"] if n == 1 else T["fundamentos"], fontsize=13)
            y += 30
        for liña in corpo[(n - 1) * 6:n * 6]:
            paxina.insert_text((72, y), liña, fontsize=10)
            y += 15
        paxina.insert_text((290, 800), f"{n}", fontsize=8)
    pdf.save(exp / T["pdf"])
    libro = openpyxl.Workbook()
    libro.active.title = "Contas"
    for fila in ([T["concepto"], T["importe"]], [T["taxas"], 180], [T["perito"], 650]):
        libro.active.append(fila)
    oculta = libro.create_sheet(T["interna"])
    oculta.append(["-", "-"])
    oculta.sheet_state = "hidden"
    libro.save(exp / "contas.xlsx")
    correo = EmailMessage()
    correo["Subject"] = T["asunto"]
    correo["From"] = "Marta Lourenzo Vidal <marta.lourenzo@exemplo.invalid>"
    correo["To"] = "despacho@exemplo.invalid"
    correo["Date"] = "Fri, 30 Oct 2026 12:40:00 +0100"
    correo.set_content(T["corpo"])
    correo.add_attachment(b"%PDF-1.4 " + b"0" * 90000, maintype="application", subtype="pdf",
                          filename="informe_pericial.pdf")
    (exp / "correo.eml").write_bytes(bytes(correo))
    return [exp / "declaracion.docx", exp / T["pdf"], exp / "contas.xlsx", exp / "correo.eml"]


PONTE = """
window.pywebview = {api: new Proxy({}, {get: (_, metodo) => (...args) => window.__api(metodo, args)})};
"""


class Capturador:
    def __init__(self, paxina, api, eventos):
        self.paxina, self.api, self.eventos = paxina, api, eventos

    def agardar_evento(self, nome, segundos=180):
        """Pasa á páxina os eventos da Api ata que chega `nome`."""
        limite = time.time() + segundos
        while time.time() < limite:
            try:
                evento, datos = self.eventos.get(timeout=0.2)
            except queue.Empty:
                continue
            self.paxina.evaluate("([e, d]) => recibir(e, d)", [evento, datos])
            if evento == nome:
                return datos
        raise SystemExit(f"Non chegou o evento «{nome}»")

    def foto(self, nome, selector=None):
        IMG.mkdir(parents=True, exist_ok=True)
        self.paxina.wait_for_timeout(300)
        if STORE:
            self.paxina.evaluate("window.scrollTo(0, 0)")
            self.paxina.screenshot(path=str(IMG / nome))
        elif selector:
            self.paxina.locator(selector).screenshot(path=str(IMG / nome))
        else:
            self.paxina.screenshot(path=str(IMG / nome), full_page=True)
        print("  ", IMG / nome)


def main() -> None:
    shutil.rmtree(BASE, ignore_errors=True)
    exp = BASE / "Expediente_0142"
    documentos = crear_documentos(exp)
    os.chdir(BASE)  # preferencias.json de proba, nunca o do usuario
    eventos = queue.Queue()
    api = pantalla_conversor.Api(emitir=lambda e, d: eventos.put((e, json.loads(json.dumps(d)))),
                                 rexistro_dir=str(BASE / "datos_rexistro"), usar_chaveiro=False)

    with sync_playwright() as p:
        navegador = p.chromium.launch(channel="chrome")  # o Chrome instalado (coma xerar_pdfs.py)
        contexto = navegador.new_context(viewport={"width": ANCHO, "height": ALTO}, device_scale_factor=ESCALA,
                                         bypass_csp=True, locale="gl-ES" if LINGUA == "gl" else "es-ES")
        paxina = contexto.new_page()
        paxina.expose_function("__api", lambda metodo, args: getattr(api, metodo)(*args))
        paxina.set_content(pantalla_conversor.html())
        # `set_content` non é unha navegación (non corre `add_init_script`): a ponte
        # ponse despois e avísase coma pywebview, co evento `pywebviewready`.
        paxina.evaluate(PONTE + "window.dispatchEvent(new Event('pywebviewready'));")
        paxina.wait_for_function("document.querySelector('input[name=modo]:checked') !== null")
        c = Capturador(paxina, api, eventos)

        # 1. Inicio cos documentos escollidos
        paxina.evaluate("(e) => engadirEntradas(e)", api.describir_rutas([str(d) for d in documentos]))
        c.foto("inicio.png")
        # 2. Opcións
        paxina.click("details.opcions summary")
        c.foto("opcions.png", "details.opcions")
        paxina.click("details.opcions summary")

        # 3. Converter sen anonimizar: progreso e resultado
        paxina.click("#converter")
        progreso = None
        while progreso is None:
            evento, datos = eventos.get(timeout=120)
            paxina.evaluate("([e, d]) => recibir(e, d)", [evento, datos])
            if evento == "progreso" and datos.get("feito", 0) >= 1:
                progreso = datos
        c.foto("progreso.png", "#progreso .tarxeta")
        c.agardar_evento("rematado")
        c.foto("resultado.png")
        for md in sorted(exp.glob("*.md")):
            shutil.copy(md, BASE / f"exemplo-{md.name}")

        # 4. Converter anonimizando, con revisión: só a declaración
        paxina.evaluate("() => { entradas = []; pintarEntradas(); amosar('inicio'); }")
        paxina.evaluate("(e) => engadirEntradas(e)", api.describir_rutas([str(documentos[0])]))
        paxina.check("input[name=modo][value=revisar]")
        paxina.click("#converter-anon")
        c.agardar_evento("revisar")
        c.foto("revision.png")
        paxina.click("#confirmar-revision")
        c.agardar_evento("rematado")
        c.foto("resultado_anonimizado.png")
        for md in sorted(exp.glob("*.anonimizado.*.md")):
            shutil.copy(md, BASE / f"exemplo-{md.name}")

        # 5. Acerca de
        paxina.click("#ligazon-acerca")
        paxina.wait_for_selector("#acerca:not([hidden]) .tarxeta")
        c.foto("acerca.png")
        navegador.close()


if __name__ == "__main__":
    main()
