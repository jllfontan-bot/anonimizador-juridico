"""Imaxes soltas (.jpg, .png, .tif...): anonimízanse e gárdanse NO MESMO
FORMATO (indicación do usuario, 29/09/2026: "que conserve o formato en
imaxe"), non coma texto.

Unha imaxe é, a efectos de detección, unha páxina escaneada: cada
fotograma pásase a unha páxina dun PDF en memoria e vai polo MESMO camiño
xa probado dos PDF escaneados (`pdf_estrutura`: OCR, tachado dos píxeles,
códigos QR/de barras). Ao gardar, esa páxina xa redactada rasterízase de
volta á resolución EXACTA en píxeles do orixinal.

A páxina dimensiónase a `_DPI_OCR`: o render do OCR coincide así cos
píxeles orixinais (nin se perde resolución nin se dispara a memoria cunha
foto de móbil marcada a 72 ppp).

Os metadatos (EXIF: GPS, autor, modelo de cámara...) NON se copian: poden
ser datos persoais, e a imaxe de saída constrúese de novo desde os
píxeles. Límite: HEIC/HEIF e RAW non se admiten (Pillow non os le sen
extensións).
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image, ImageOps, ImageSequence

from .pdf import _DPI_OCR
from .pdf_estrutura import cargar_pdf_estruturado, gardar_pdf_estruturado

# sufixo -> formato de Pillow
FORMATOS = {
    ".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".tif": "TIFF", ".tiff": "TIFF",
    ".bmp": "BMP", ".webp": "WEBP", ".gif": "GIF",
}
_CALIDADE_JPEG = 95


def _a_rgb(imaxe: Image.Image) -> Image.Image:
    """RGB sobre fondo branco: a transparencia non sobrevive ao PDF
    intermedio, e un fondo negro faría ilexible un documento."""
    if imaxe.mode in ("RGBA", "LA") or (imaxe.mode == "P" and "transparency" in imaxe.info):
        rgba = imaxe.convert("RGBA")
        return Image.alpha_composite(Image.new("RGBA", rgba.size, "white"), rgba).convert("RGB")
    return imaxe.convert("RGB")


def cargar(ruta: str) -> tuple:
    """Coma `pdf_estrutura.cargar_pdf_estruturado`, e ademais
    `contexto["imaxe"]` co necesario para gardar no formato orixinal."""
    with Image.open(ruta) as orixinal:
        formato = orixinal.format
        modo = orixinal.mode
        dpi = orixinal.info.get("dpi")
        fotogramas = [_a_rgb(ImageOps.exif_transpose(f.copy())) for f in ImageSequence.Iterator(orixinal)]

    documento = fitz.open()
    for fotograma in fotogramas:
        png = io.BytesIO()
        fotograma.save(png, "PNG")
        pagina = documento.new_page(
            width=fotograma.width * 72 / _DPI_OCR, height=fotograma.height * 72 / _DPI_OCR
        )
        pagina.insert_image(pagina.rect, stream=png.getvalue())

    texto, contexto = cargar_pdf_estruturado(None, documento=documento)
    contexto["imaxe"] = {
        "formato": formato, "modo": modo, "dpi": dpi, "tamanos": [f.size for f in fotogramas],
    }
    return texto, contexto


def conserva_formato(contexto: dict, ruta_saida: str) -> bool:
    return FORMATOS.get(Path(ruta_saida).suffix.lower()) == contexto["imaxe"]["formato"]


def gardar(contexto: dict, texto_final: str, ruta_saida: str, substitucions: list | None) -> None:
    info = contexto["imaxe"]
    with tempfile.TemporaryDirectory() as directorio:
        pdf = str(Path(directorio) / "imaxe.pdf")
        gardar_pdf_estruturado(contexto, texto_final, pdf, substitucions)
        fotogramas = []
        with fitz.open(pdf) as documento:
            for pagina, (ancho, alto) in zip(documento, info["tamanos"]):
                matriz = fitz.Matrix(ancho / pagina.rect.width, alto / pagina.rect.height)
                pix = pagina.get_pixmap(matrix=matriz, alpha=False)
                imaxe = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                if imaxe.size != (ancho, alto):
                    imaxe = imaxe.resize((ancho, alto))
                if info["modo"] in ("L", "1", "LA"):
                    imaxe = imaxe.convert("L")
                fotogramas.append(imaxe)

    formato = info["formato"]
    opcions = {}
    if info["dpi"]:
        opcions["dpi"] = info["dpi"]
    if formato == "JPEG":
        opcions["quality"] = _CALIDADE_JPEG
    elif formato == "TIFF":
        opcions["compression"] = "tiff_lzw"
    if len(fotogramas) > 1:
        opcions.update(save_all=True, append_images=fotogramas[1:])
    fotogramas[0].save(ruta_saida, formato, **opcions)
