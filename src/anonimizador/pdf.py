"""Lectura de PDF: extraccion nativa do texto e, cando a paxina non ten capa
de texto (documento escaneado), OCR con Tesseract.

Non depende de Tesseract para PDF con texto nativo -- so o precisa cando
detecta unha paxina escaneada. Se Tesseract non esta instalado nese caso,
lanza un erro claro con instrucions, en vez dun fallo confuso.
"""

from __future__ import annotations

import shutil

import fitz  # PyMuPDF
import pytesseract
from PIL import Image, ImageOps

from . import sen_consola

# Sen consolas que parpadeen en Windows (ver `sen_consola.py`).
sen_consola.aplicar()

_LONGO_ABONDO = 20  # caracteres; por debaixo diso, a paxina considerase escaneada
_DPI_OCR = 300
_IDIOMAS_PREFERIDOS = ("spa+glg", "spa", "eng")
_CONFIG_TESSERACT = "--oem 1 --psm 6"  # LSTM só + bloque de texto uniforme


class TesseractNonInstalado(RuntimeError):
    def __init__(self):
        super().__init__(
            "Esta paxina do PDF parece escaneada (non ten capa de texto) e "
            "require OCR, pero Tesseract non esta instalado neste ordenador.\n"
            "Instalao con Homebrew e volve a intentalo:\n\n"
            "    /bin/bash -c \"$(curl -fsSL "
            "https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"\n"
            "    brew install tesseract tesseract-lang\n"
        )


def _idioma_dispoñible() -> str:
    try:
        instalados = set(pytesseract.get_languages(config=""))
    except Exception:
        return "eng"
    for combinacion in _IDIOMAS_PREFERIDOS:
        if all(idioma in instalados for idioma in combinacion.split("+")):
            return combinacion
    return "eng"


def _preprocesar(imaxe: Image.Image) -> Image.Image:
    """Escala de grises + autocontraste: reduce erros de OCR en
    dixitalizacions de pouco contraste sen risco de estragar texto xa
    nítido (probado: un filtro de nitidez adicional mellora escaneados
    borrosos pero pode facer ilexible texto xa ben definido, así que se
    descartou por non ser unha mellora fiable en xeral)."""
    gris = imaxe.convert("L")
    return ImageOps.autocontrast(gris, cutoff=1)


def _ocr_paxina(paxina: "fitz.Page") -> str:
    if shutil.which("tesseract") is None:
        raise TesseractNonInstalado()
    escala = _DPI_OCR / 72
    pix = paxina.get_pixmap(matrix=fitz.Matrix(escala, escala))
    imaxe = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    imaxe = _preprocesar(imaxe)
    return pytesseract.image_to_string(
        imaxe, lang=_idioma_dispoñible(), config=_CONFIG_TESSERACT
    )


def cargar_texto_pdf(ruta: str) -> str:
    """Devolve o texto de todas as paxinas dun PDF, unha paxina = un
    paragrafo (separadas por liña en branco).

    Delega en `pdf_estrutura.cargar_pdf_estruturado` para ler EXACTAMENTE
    o mesmo texto ca o fluxo que redacta: antes aquí só se facía OCR das
    paxinas con menos de `_LONGO_ABONDO` caracteres nativos, e perdíanse
    as imaxes con datos en paxinas con texto nativo, o texto invisible
    curto, as capas opcionais apagadas... (ver alí)."""
    from .pdf_estrutura import cargar_pdf_estruturado  # evita importación circular

    _texto, contexto = cargar_pdf_estruturado(ruta)
    try:
        return "\n\n".join(p.texto.strip() for p in contexto["paxinas"])
    finally:
        contexto["documento"].close()
