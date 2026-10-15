"""Fugas críticas de datos persoais en PDF atopadas nunha auditoría con
documentos SINTÉTICOS (ningún dato real):

- A4: páxina con texto nativo abondo (>= `_LONGO_ABONDO`) que ademais
  leva unha IMAXE con datos (unha dilixencia escaneada pegada, unha
  captura...) -- nunca se facía OCR desa imaxe. Variante: escaneo cunha
  capa de OCR previa (texto invisible) DESALIÑADA respecto da imaxe.
- A5: páxinas con /Rotate 90/270 -- as coordenadas do render (OCR, QR,
  reserva de páxina completa) non se pasaban por `derotation_matrix` e o
  tachado caía noutro sitio.
- A6: contido oculto que se conservaba sen analizar: capa opcional (OCG)
  apagada, texto fóra do CropBox, texto invisible/branco curto.
- A3: nada se limpaba a nivel de DOCUMENTO: metadatos/XMP, marcadores,
  comentarios, campos de formulario, adxuntos, miniaturas,
  ActualText/Alt, ligazóns URI.
- A20: fontes sen táboa /ToUnicode -- o visor amosa o texto ben pero
  `get_text` devolve lixo, non casaba ningún patrón e a saída era
  idéntica á entrada (aínda que o OCR da propia saída si lía o nome).
- A21: escaneo DE LADO (imaxe xirada 90º sen o /Rotate do PDF) -- o OCR
  coa orientación orixinal non lía nada con sentido e non se tachaba
  nada.
- A22: letreado expandido (operador `Tc` alto) -- "J U A N  P E R E Z"
  chegaba ao texto letra a letra e non o recoñecía nin o NER nin os
  patróns nin a rede de seguridade de `risco_residual.py`.
- A25: texto e códigos convertidos a TRAZOS VECTORIAIS -- tapábanse cun
  recadro branco pero os trazos orixinais seguían dentro do ficheiro
  (`get_drawings()`), e o que sobresaía do recadro quedaba á vista.

Tódalas comprobacións fanse sobre a SAÍDA: texto extraíble, bytes
descomprimidos de TÓDOLOS obxectos do ficheiro e, cando o dato ía nunha
imaxe ou nun debuxo, OCR do render da páxina final.
"""

import io
import re
import shutil
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path

import cv2
import fitz  # PyMuPDF
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador.pdf_estrutura import cargar_pdf_estruturado, gardar_pdf_estruturado
from anonimizador.pipeline import anonimizar_e_gardar, anonimizar_texto_detallado
from anonimizador.registry import RexistroCorrespondencias

_TESSERACT_DISPOÑIBLE = shutil.which("tesseract") is not None

BASE = "Texto normal del expediente judicial numero uno de Lugo."
DNI = "12345678Z"


# -- construción de PDF sintéticos -------------------------------------------

def _fonte(tamano: int):
    for ruta in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if Path(ruta).exists():
            return ImageFont.truetype(ruta, tamano)
    return ImageFont.load_default()


def _png_texto(liñas: list, ancho: int = 2000, tamano: int = 60) -> bytes:
    alto = tamano * 2 * len(liñas) + 40
    imaxe = Image.new("RGB", (ancho, alto), "white")
    debuxo = ImageDraw.Draw(imaxe)
    fonte = _fonte(tamano)
    for i, liña in enumerate(liñas):
        debuxo.text((30, 20 + i * tamano * 2), liña, fill="black", font=fonte)
    saida = io.BytesIO()
    imaxe.save(saida, "PNG")
    return saida.getvalue()


_LIÑAS_DATOS = ["El demandante Juan Perez Garcia", f"con DNI {DNI}, vecino de Lugo."]


def _png_qr(contido: str) -> bytes:
    modulos = cv2.QRCodeEncoder.create().encode(contido)
    con_marxe = np.pad(modulos, 4, constant_values=255)
    grande = np.kron(con_marxe, np.ones((8, 8), dtype=np.uint8))
    return cv2.imencode(".png", grande)[1].tobytes()


# -- inspección da saída -----------------------------------------------------

def _bytes_descomprimidos(ruta) -> bytes:
    """O ficheiro en bruto + cada obxecto e cada fluxo DESCOMPRIMIDO +
    as cadeas hexadecimais decodificadas (PyMuPDF escribe o texto en hex
    `<...>` nos fluxos de contido) + versións UTF-16 decodificadas."""
    anacos = [Path(ruta).read_bytes()]
    with fitz.open(str(ruta)) as doc:
        for xref in range(1, doc.xref_length()):
            try:
                anacos.append(doc.xref_object(xref).encode("latin-1", "replace"))
            except Exception:
                pass
            try:
                if doc.xref_is_stream(xref):
                    anacos.append(doc.xref_stream(xref) or b"")
            except Exception:
                pass
        for nome in doc.embfile_names():
            anacos.append(doc.embfile_get(nome))
    bruto = b"\n".join(anacos)
    extra = []
    for m in re.finditer(rb"<([0-9a-fA-F\s]+)>", bruto):
        hexa = re.sub(rb"\s", b"", m.group(1))
        if len(hexa) % 2 == 0:
            try:
                extra.append(bytes.fromhex(hexa.decode()))
            except ValueError:
                pass
    todo = bruto + b"\n" + b"\n".join(extra)
    # UTF-16BE (metadatos/marcadores con BOM) -> quitar os NUL
    return todo + b"\n" + todo.replace(b"\x00", b"")


def _texto_saida(ruta) -> str:
    """Texto visible + o que houbese fóra do CropBox (quitando o CropBox
    -- por defecto pasa a ser o MediaBox -- e recargando)."""
    with fitz.open(str(ruta)) as doc:
        partes = [pagina.get_text() for pagina in doc]
        for pagina in doc:
            doc.xref_set_key(pagina.xref, "CropBox", "null")
        with fitz.open("pdf", doc.tobytes()) as sen_crop:
            partes.extend(pagina.get_text() for pagina in sen_crop)
        return "\n".join(partes)


def _ocr_saida(ruta) -> str:
    import pytesseract

    with fitz.open(str(ruta)) as doc:
        partes = []
        for pagina in doc:
            pix = pagina.get_pixmap(dpi=200)
            imaxe = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            partes.append(pytesseract.image_to_string(imaxe, lang="spa"))
        return "\n".join(partes)


def _normalizar(texto: str) -> str:
    sen_tiles = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in sen_tiles if not unicodedata.combining(c)).casefold()


def _qr_decodificable(ruta) -> list:
    with fitz.open(str(ruta)) as doc:
        lidos = []
        for pagina in doc:
            pix = pagina.get_pixmap(dpi=200, colorspace=fitz.csGRAY)
            imaxe = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
            texto = cv2.QRCodeDetector().detectAndDecode(imaxe)[0]
            if texto:
                lidos.append(texto)
        return lidos


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.rexistro = RexistroCorrespondencias(str(self.dir / "rexistro"))

    def tearDown(self):
        self._tmp.cleanup()

    def _procesar(self, documento: "fitz.Document", nome: str) -> Path:
        entrada = self.dir / f"{nome}.pdf"
        documento.save(str(entrada))
        documento.close()
        saida = self.dir / f"{nome}.anonimizado.pdf"
        anonimizar_e_gardar(str(entrada), str(saida), self.rexistro)
        return saida

    def _sen_datos_en_texto_nin_bytes(self, saida, agullas=("Juan", "Perez", DNI)):
        texto = _normalizar(_texto_saida(saida))
        bruto = _bytes_descomprimidos(saida)
        for agulla in agullas:
            # assertFalse(... in ...) e non assertNotIn: esta última volcaría
            # o ficheiro enteiro na mensaxe de erro
            self.assertFalse(_normalizar(agulla) in texto, f"{agulla!r} no texto da saída")
            self.assertFalse(agulla.encode("latin-1") in bruto, f"{agulla!r} nos bytes da saída")

    def _sen_datos_no_ocr(self, saida):
        ocr = _normalizar(_ocr_saida(saida))
        self.assertNotRegex(ocr, r"1234\s?5678", f"DNI lexible no OCR da saída: {ocr!r}")
        self.assertNotIn("perez", ocr, f"apelido lexible no OCR da saída: {ocr!r}")


# -- A4 -----------------------------------------------------------------------

@unittest.skipUnless(_TESSERACT_DISPOÑIBLE, "require Tesseract")
class TestA4ImaxesEnPaxinaConTextoNativo(_Base):
    def test_imaxe_con_datos_en_paxina_con_texto_nativo(self):
        documento = fitz.open()
        pagina = documento.new_page()
        pagina.insert_text((72, 60), "Registro de entrada n. 2024/000123 de 01/02/2024", fontsize=10)
        pagina.insert_image(fitz.Rect(40, 100, 560, 250), stream=_png_texto(_LIÑAS_DATOS))
        saida = self._procesar(documento, "mixta")
        self._sen_datos_no_ocr(saida)
        # o texto nativo non sensible segue aí
        self.assertIn("Registro de entrada", _texto_saida(saida))

    def test_escaneo_con_capa_ocr_previa_desaliñada(self):
        documento = fitz.open()
        pagina = documento.new_page()
        pagina.insert_image(fitz.Rect(40, 60, 560, 210), stream=_png_texto(_LIÑAS_DATOS))
        # capa de texto invisible (a dun escáner con OCR), 400 pt máis abaixo
        pagina.insert_text((50, 500), "El demandante Juan Perez Garcia", fontsize=14, render_mode=3)
        pagina.insert_text((50, 530), f"con DNI {DNI}, vecino de Lugo.", fontsize=14, render_mode=3)
        saida = self._procesar(documento, "desaliñada")
        self._sen_datos_no_ocr(saida)
        self._sen_datos_en_texto_nin_bytes(saida)

    def test_non_duplica_texto_nativo_visible(self):
        """O texto nativo que se debuxa ENCIMA da imaxe tamén sae no render
        -- non debe aparecer dúas veces no texto de revisión."""
        documento = fitz.open()
        pagina = documento.new_page()
        pagina.insert_image(fitz.Rect(40, 100, 560, 250), stream=_png_texto(["Documento adjunto numero tres"]))
        pagina.insert_text((60, 240), "Registro de entrada numero cuatro de Lugo", fontsize=12)
        entrada = self.dir / "encima.pdf"
        documento.save(str(entrada))
        documento.close()
        texto, _contexto = cargar_pdf_estruturado(str(entrada))
        self.assertEqual(texto.count("Registro"), 1, texto)
        self.assertIn("adjunto", texto)


# -- A5 -----------------------------------------------------------------------

@unittest.skipUnless(_TESSERACT_DISPOÑIBLE, "require Tesseract")
class TestA5PaxinasRotadas(_Base):
    def test_imaxe_en_paxina_rotada(self):
        for rotacion in (90, 270):
            with self.subTest(rotacion=rotacion):
                documento = fitz.open()
                pagina = documento.new_page()
                pagina.set_rotation(rotacion)
                pagina.insert_image(fitz.Rect(40, 100, 300, 700), stream=_png_texto(_LIÑAS_DATOS), rotate=rotacion)
                saida = self._procesar(documento, f"imaxe_rot{rotacion}")
                self._sen_datos_no_ocr(saida)

    def test_qr_en_paxina_rotada(self):
        documento = fitz.open()
        pagina = documento.new_page()
        pagina.insert_text((72, 80), BASE, fontsize=11)
        pagina.insert_image(fitz.Rect(400, 600, 520, 720), stream=_png_qr(f"DNI {DNI} Juan Perez Garcia"))
        pagina.set_rotation(90)
        saida = self._procesar(documento, "qr_rotado")
        self.assertEqual(_qr_decodificable(saida), [])

    def test_reserva_de_paxina_completa_en_paxina_rotada(self):
        """Edición a man na revisión -> a páxina enteira redáctase e
        reescríbese. Na páxina rotada quedaba sen tapar unha franxa: o pé
        orixinal (y=780) sobrevivía e saía DÚAS veces (orixinal + novo)."""
        for rotacion in (90, 270):
            with self.subTest(rotacion=rotacion):
                entrada = self.dir / f"reserva_rot{rotacion}.pdf"
                documento = fitz.open()
                pagina = documento.new_page()
                pagina.insert_text((72, 100), f"El demandante Juan Perez Garcia, con DNI {DNI}.", fontsize=11)
                pagina.insert_text((72, 780), "Pie de pagina final del escrito.", fontsize=11)
                pagina.set_rotation(rotacion)
                documento.save(str(entrada))
                documento.close()

                texto, contexto = cargar_pdf_estruturado(str(entrada))
                texto_anon, _inf, substitucions = anonimizar_texto_detallado(texto, self.rexistro, contexto=contexto)
                editado = texto_anon.replace("El demandante", "La parte demandante")  # -> reserva
                self.assertNotEqual(editado, texto_anon)
                saida = self.dir / f"reserva_rot{rotacion}.anonimizado.pdf"
                gardar_pdf_estruturado(contexto, editado, str(saida), substitucions)

                with fitz.open(str(saida)) as doc:
                    texto_final = doc[0].get_text()
                self.assertIn("La parte demandante", texto_final)
                self.assertEqual(texto_final.count("escrito"), 1, texto_final)
                self.assertFalse("12345678" in texto_final or "Perez" in texto_final)
                self.assertFalse(DNI.encode() in _bytes_descomprimidos(saida))


# -- A6 -----------------------------------------------------------------------

class TestA6ContidoOculto(_Base):
    def test_capa_opcional_apagada(self):
        documento = fitz.open()
        pagina = documento.new_page()
        oc = documento.add_ocg("Notas", on=False)
        pagina.insert_text((72, 80), BASE, fontsize=11)
        pagina.insert_text((72, 120), f"Nota interna: el demandante Juan Perez Garcia, DNI {DNI}.", fontsize=11, oc=oc)
        saida = self._procesar(documento, "ocg")
        self._sen_datos_en_texto_nin_bytes(saida)

    def test_texto_fora_do_cropbox(self):
        documento = fitz.open()
        pagina = documento.new_page()
        pagina.insert_text((72, 100), BASE, fontsize=11)
        pagina.insert_text((72, 800), f"Juan Perez Garcia DNI {DNI}", fontsize=11)
        pagina.set_cropbox(fitz.Rect(0, 0, 595, 600))
        saida = self._procesar(documento, "cropbox")
        self._sen_datos_en_texto_nin_bytes(saida)
        with fitz.open(str(saida)) as doc:  # o CropBox consérvase
            self.assertEqual(doc[0].cropbox, fitz.Rect(0, 0, 595, 600))
            self.assertIn("expediente", doc[0].get_text())

    def test_texto_fora_do_cropbox_con_mediabox_desprazado_e_rotacion(self):
        """MediaBox con orixe negativa + CropBox desprazado + /Rotate 90:
        as coordenadas da páxina xa non coinciden coas do PDF."""
        documento = fitz.open()
        pagina = documento.new_page()
        pagina.insert_text((72, 100), BASE, fontsize=11)
        pagina.insert_text((72, 800), f"Juan Perez Garcia DNI {DNI}", fontsize=11)
        documento.xref_set_key(pagina.xref, "MediaBox", "[-50 -50 595 842]")
        documento.xref_set_key(pagina.xref, "CropBox", "[40 300 595 842]")
        documento.xref_set_key(pagina.xref, "Rotate", "90")
        saida = self._procesar(documento, "cropbox_desprazado")
        self._sen_datos_en_texto_nin_bytes(saida)
        self.assertIn("expediente", _texto_saida(saida))

    def test_texto_invisible_curto(self):
        documento = fitz.open()
        pagina = documento.new_page()
        pagina.insert_text((72, 100), f"DNI {DNI}", fontsize=11, render_mode=3)
        saida = self._procesar(documento, "invisible")
        self._sen_datos_en_texto_nin_bytes(saida, agullas=(DNI,))

    def test_texto_branco_curto(self):
        documento = fitz.open()
        pagina = documento.new_page()
        pagina.insert_text((72, 100), f"DNI {DNI}", fontsize=11, color=(1, 1, 1))
        saida = self._procesar(documento, "branco")
        self._sen_datos_en_texto_nin_bytes(saida, agullas=(DNI,))


# -- A3 -----------------------------------------------------------------------

class TestA3LimpezaDocumento(_Base):
    def _doc_base(self):
        documento = fitz.open()
        pagina = documento.new_page()
        pagina.insert_text((72, 100), BASE, fontsize=11)
        return documento, pagina

    def test_metadatos_xmp_e_marcadores(self):
        documento, _pagina = self._doc_base()
        documento.set_metadata({
            "title": f"Demanda de Juan Perez Garcia {DNI}", "author": "Juan Perez Garcia",
            "subject": f"DNI {DNI}", "keywords": "Juan Perez", "creator": "Juan Perez",
        })
        documento.set_xml_metadata(
            '<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?><x:xmpmeta xmlns:x="adobe:ns:meta/">'
            '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description '
            f'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:creator>Juan Perez Garcia {DNI}</dc:creator>'
            '</rdf:Description></rdf:RDF></x:xmpmeta><?xpacket end="w"?>'
        )
        documento.set_toc([[1, f"Juan Perez Garcia {DNI}", 1]])
        saida = self._procesar(documento, "metadatos")
        self._sen_datos_en_texto_nin_bytes(saida)
        with fitz.open(str(saida)) as doc:
            self.assertEqual(doc.get_toc(), [])
            self.assertEqual(doc.get_xml_metadata(), "")
            for chave in ("title", "author", "subject", "keywords", "creator"):
                self.assertFalse(doc.metadata.get(chave), chave)

    def test_comentarios_formularios_e_ligazons(self):
        documento, pagina = self._doc_base()
        nota = pagina.add_text_annot((300, 300), f"Comentario: Juan Perez DNI {DNI}")
        nota.set_info(title="Juan Perez Garcia")
        nota.update()
        widget = fitz.Widget()
        widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        widget.field_name = "demandante"
        widget.field_value = f"Juan Perez Garcia {DNI}"
        widget.rect = fitz.Rect(72, 500, 400, 520)
        pagina.add_widget(widget)
        pagina.insert_link({
            "kind": fitz.LINK_URI, "from": fitz.Rect(72, 88, 200, 104),
            "uri": f"mailto:juan.perez@example.com?subject=DNI%20{DNI}",
        })
        pagina.insert_link({"kind": fitz.LINK_GOTO, "from": fitz.Rect(72, 120, 200, 134), "page": 0, "to": fitz.Point(0, 0)})
        saida = self._procesar(documento, "anotacions")
        self._sen_datos_en_texto_nin_bytes(saida, agullas=("Juan", "Perez", DNI, "juan.perez"))
        with fitz.open(str(saida)) as doc:
            pag = doc[0]
            self.assertEqual(list(pag.annots()), [])
            self.assertEqual(list(pag.widgets()), [])
            ligazons = pag.get_links()
            self.assertEqual([l["kind"] for l in ligazons], [fitz.LINK_GOTO])  # a interna consérvase

    def test_adxuntos(self):
        documento, pagina = self._doc_base()
        documento.embfile_add("demanda.txt", f"Demandante: Juan Perez Garcia DNI {DNI}".encode(), filename="demanda.txt")
        pagina.add_file_annot((72, 200), f"Anexo Juan Perez DNI {DNI}".encode(), "anexo.txt")
        saida = self._procesar(documento, "adxuntos")
        self._sen_datos_en_texto_nin_bytes(saida)
        with fitz.open(str(saida)) as doc:
            self.assertEqual(doc.embfile_count(), 0)
            self.assertEqual(list(doc[0].annots()), [])

    def test_miniatura(self):
        documento = fitz.open()
        pagina = documento.new_page()
        pagina.insert_text((72, 100), f"El demandante Juan Perez Garcia, DNI {DNI}.", fontsize=11)
        pix = pagina.get_pixmap(dpi=100)
        xref = documento.get_new_xref()
        documento.update_object(
            xref, f"<< /Type /XObject /Subtype /Image /Width {pix.width} /Height {pix.height} "
            "/ColorSpace /DeviceRGB /BitsPerComponent 8 >>"
        )
        documento.update_stream(xref, pix.samples)
        documento.xref_set_key(pagina.xref, "Thumb", f"{xref} 0 R")
        saida = self._procesar(documento, "miniatura")
        with fitz.open(str(saida)) as doc:
            self.assertEqual(doc.xref_get_key(doc[0].xref, "Thumb")[0], "null")
            for x in range(1, doc.xref_length()):
                self.assertNotEqual(doc.xref_get_key(x, "Subtype")[1], "/Image", "queda unha imaxe (miniatura)")

    def test_actualtext_e_alt(self):
        documento, pagina = self._doc_base()
        pagina.insert_text((72, 140), "Firma: J. P. G.", fontsize=11)
        contido = documento.xref_stream(pagina.get_contents()[0])
        documento.update_stream(
            pagina.get_contents()[0],
            f"/Span <</ActualText (Juan Perez Garcia DNI {DNI})>> BDC\n".encode() + contido + b"\nEMC\n",
        )
        elemento, raiz = documento.get_new_xref(), documento.get_new_xref()
        documento.update_object(
            elemento, f"<< /Type /StructElem /S /Figure /P {raiz} 0 R /Pg {pagina.xref} 0 R "
            f"/Alt (Fotografia del DNI de Juan Perez Garcia {DNI}) >>"
        )
        documento.update_object(raiz, f"<< /Type /StructTreeRoot /K [{elemento} 0 R] >>")
        documento.xref_set_key(documento.pdf_catalog(), "StructTreeRoot", f"{raiz} 0 R")
        saida = self._procesar(documento, "actualtext")
        self._sen_datos_en_texto_nin_bytes(saida)
        self.assertIn("expediente", _texto_saida(saida))


# -- A20 ----------------------------------------------------------------------

_DESPRAZAMENTO_GLIFOS = 3  # o código que vai no PDF é a letra real + 3


def _fonte_type3_sen_tounicode(documento, liñas: list) -> int:
    """Fonte Type3 (glifos definidos coma debuxos, non coma caracteres)
    SEN /ToUnicode e cun /Differences de nomes inventados (/g068...), que
    é o que non sabe traducir ningún extractor. Cada glifo debuxa a letra
    REAL con Helvetica, pero o código que se escribe no fluxo de contido
    é a letra desprazada tres posicións: así o visor (e o OCR do render)
    len "El demandante Juan Perez Garcia" mentres que `get_text` devolve
    "Ho#ghpdqgdqwh#Mxdq#Shuh}#Jdufld" -- exactamente o síntoma atopado na
    auditoría."""
    xref_helvetica = documento.get_new_xref()
    documento.update_object(xref_helvetica, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    codigos = sorted({ord(c) + _DESPRAZAMENTO_GLIFOS for liña in liñas for c in liña})
    charprocs = {}
    for codigo in codigos:
        real = chr(codigo - _DESPRAZAMENTO_GLIFOS)
        xref = documento.get_new_xref()
        documento.update_object(xref, "<<>>")
        corpo = b"600 0 d0\n"
        if real != " ":
            corpo += b"BT /H 1000 Tf 0 0 Td (" + real.encode("latin-1") + b") Tj ET\n"
        documento.update_stream(xref, corpo, new=True)
        charprocs[codigo] = xref

    xref_fonte = documento.get_new_xref()
    documento.update_object(xref_fonte, (
        "<< /Type /Font /Subtype /Type3 /FontBBox [0 0 1000 1000] "
        "/FontMatrix [0.001 0 0 0.001 0 0] "
        "/CharProcs << " + " ".join(f"/g{c:03d} {charprocs[c]} 0 R" for c in codigos) + " >> "
        "/Encoding << /Type /Encoding /Differences ["
        + " ".join(f"{c} /g{c:03d}" for c in codigos) + "] >> "
        f"/FirstChar {codigos[0]} /LastChar {codigos[-1]} "
        "/Widths [" + " ".join("600" for _ in range(codigos[0], codigos[-1] + 1)) + "] "
        f"/Resources << /Font << /H {xref_helvetica} 0 R >> >> >>"
    ))
    return xref_fonte


def _engadir_fonte_aos_recursos(documento, pagina, nome: str, xref_fonte: int) -> None:
    """/Resources (e /Font dentro del) poden ser obxectos indirectos, e
    `xref_set_key` non atravesa indireccións -- hai que resolvelas."""
    xref, prefixo = pagina.xref, "Resources/"
    tipo, valor = documento.xref_get_key(pagina.xref, "Resources")
    if tipo == "xref":
        xref, prefixo = int(valor.split()[0]), ""
    tipo, valor = documento.xref_get_key(xref, f"{prefixo}Font")
    if tipo == "xref":
        documento.xref_set_key(int(valor.split()[0]), nome, f"{xref_fonte} 0 R")
    else:
        documento.xref_set_key(xref, f"{prefixo}Font/{nome}", f"{xref_fonte} 0 R")


def _pdf_sen_tounicode(liñas: list, tamano: int = 20):
    documento = fitz.open()
    pagina = documento.new_page()
    xref_fonte = _fonte_type3_sen_tounicode(documento, liñas)
    _engadir_fonte_aos_recursos(documento, pagina, "T3", xref_fonte)

    partes = [b"\n"]
    y = 700
    for liña in liñas:
        codificada = "".join(chr(ord(c) + _DESPRAZAMENTO_GLIFOS) for c in liña).encode("latin-1")
        partes.append(
            b"BT /T3 " + str(tamano).encode() + b" Tf 40 " + str(y).encode()
            + b" Td (" + codificada + b") Tj ET\n"
        )
        y -= 40
    # A páxina está baleira: non hai fluxo de contido ningún ao que
    # engadir, así que se crea un (a propósito NON se escribe antes texto
    # normal con `insert_text`: enturbiaría o único texto extraíble da
    # páxina, que ten que ser o lixo da fonte rota).
    xref_contido = documento.get_new_xref()
    documento.update_object(xref_contido, "<<>>")
    documento.update_stream(xref_contido, b"".join(partes), new=True)
    documento.xref_set_key(pagina.xref, "Contents", f"{xref_contido} 0 R")
    return documento, pagina


class TestA20FontesSenToUnicode(_Base):
    def test_texto_extraido_roto_detectase(self):
        from anonimizador.pdf_estrutura import _texto_semella_real

        lixo = "Ho#ghpdqgdqwh#Mxdq#Shuh}#Jdufld frq#GQL#456789:;]#frpsduhfh"
        self.assertFalse(_texto_semella_real(lixo, sen_tounicode=True))
        self.assertFalse(_texto_semella_real(lixo, sen_tounicode=False))

    def test_texto_real_non_se_confunde_con_lixo(self):
        """O contrario importa igual: se calquera páxina normal disparase
        esta comprobación, todo PDF pasaría por OCR sen necesidade (e nun
        ordenador sen Tesseract deixaría de funcionar)."""
        from anonimizador.pdf_estrutura import _texto_semella_real

        for texto in (
            "El demandante Juan Perez Garcia, con DNI 12345678Z, comparece ante este juzgado.",
            "NA VILA DE PONTEVEDRA, A VINTE E TRES DE SETEMBRO DE DOUS MIL VINTECINCO",
            "Registro de entrada n. 2024/000123 de 01/02/2024 - Expediente 45/2024",
        ):
            with self.subTest(texto=texto[:30]):
                self.assertTrue(_texto_semella_real(texto, sen_tounicode=True))

    @unittest.skipUnless(_TESSERACT_DISPOÑIBLE, "require Tesseract")
    def test_fonte_sen_tounicode_recorre_ao_ocr(self):
        documento, _pagina = _pdf_sen_tounicode([
            "El demandante Juan Perez Garcia", f"con DNI {DNI} comparece",
        ])
        saida = self._procesar(documento, "sen_tounicode")

        self._sen_datos_no_ocr(saida)
        # o texto desprazado do orixinal tampouco pode quedar no ficheiro:
        # desfacer o desprazamento é trivial para quen queira lelo
        self.assertFalse(b"Mxdq" in _bytes_descomprimidos(saida), "queda o texto orixinal en cru")


# -- A21 ----------------------------------------------------------------------

def _png_de_lado(liñas: list, xiro: int = 90) -> bytes:
    """A mesma folla de sempre pero XIRADA: o que sae dun escáner de
    alimentación automática cando a folla entra tombada. O PDF non leva
    /Rotate ningún -- o visor non ten forma de saber que vai de lado."""
    imaxe = Image.open(io.BytesIO(_png_texto(liñas)))
    saida = io.BytesIO()
    imaxe.rotate(-xiro, expand=True).save(saida, "PNG")
    return saida.getvalue()


def _ocr_saida_xirada(ruta, xiro: int = 90) -> str:
    import pytesseract

    with fitz.open(str(ruta)) as doc:
        partes = []
        for pagina in doc:
            pix = pagina.get_pixmap(dpi=200)
            imaxe = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            partes.append(pytesseract.image_to_string(imaxe.rotate(xiro, expand=True), lang="spa"))
        return _normalizar("\n".join(partes))


@unittest.skipUnless(_TESSERACT_DISPOÑIBLE, "require Tesseract")
class TestA21EscaneoDeLado(_Base):
    def test_escaneo_xirado_sen_rotate(self):
        for xiro in (90, 270):
            with self.subTest(xiro=xiro):
                documento = fitz.open()
                pagina = documento.new_page()
                pagina.insert_image(pagina.rect, stream=_png_de_lado(_LIÑAS_DATOS, xiro))
                saida = self._procesar(documento, f"de_lado_{xiro}")

                # a comprobación que importa: ler a saída COMO SE LE DE
                # VERDADE, é dicir, xirándoa ata poñela dereita
                lido = _ocr_saida_xirada(saida, xiro)
                self.assertNotIn("perez", lido, f"apelido lexible xirando a saída: {lido!r}")
                self.assertNotRegex(lido, r"1234\s?5678", f"DNI lexible xirando a saída: {lido!r}")

    def test_paxina_dereita_non_se_xira_por_riba(self):
        """Non debe haber falso positivo: unha páxina escaneada NORMAL ten
        que seguir léndose (e tachándose) na súa orientación de sempre."""
        documento = fitz.open()
        pagina = documento.new_page()
        pagina.insert_image(pagina.rect, stream=_png_texto(_LIÑAS_DATOS))
        saida = self._procesar(documento, "dereita")

        self._sen_datos_no_ocr(saida)
        self.assertIn("PERSOA_", _texto_saida(saida))


# -- A22 ----------------------------------------------------------------------

def _pdf_con_letreado(liñas: list, tc: float = 6, tamano: int = 12):
    """Texto co operador `Tc` (espazado entre caracteres) moi alto, o
    recurso tipográfico que produce "D E M A N D A N T E"."""
    documento = fitz.open()
    pagina = documento.new_page()
    pagina.insert_text((72, 60), BASE, fontsize=11)  # crea o recurso /Helv
    partes = [b"\n"]
    y = 100
    for liña in liñas:
        partes.append(
            b"BT /Helv " + str(tamano).encode() + b" Tf " + str(tc).encode() + b" Tc 72 "
            + str(y).encode() + b" Td (" + liña.encode("latin-1") + b") Tj ET\n"
        )
        y += 30
    xref = pagina.get_contents()[0]
    documento.update_stream(xref, documento.xref_stream(xref) + b"".join(partes))
    return documento, pagina


class TestA22LetreadoExpandido(_Base):
    def test_letreado_expandido_anonimizase(self):
        documento, _pagina = _pdf_con_letreado([
            "DEMANDANTE: JUAN PEREZ GARCIA", f"DNI {DNI}",
        ])
        saida = self._procesar(documento, "letreado")

        texto_final = _texto_saida(saida)
        self.assertNotIn("PEREZ", texto_final)
        self.assertNotIn("GARCIA", texto_final)
        self.assertNotIn("12345678", texto_final)
        self.assertIn("PERSOA_", texto_final)

    def test_o_texto_de_revision_ve_as_palabras_enteiras(self):
        """O letrado revisa o texto reconstruído: se alí segue a poñer
        "J U A N", nin el nin o NER poden facer nada."""
        entrada = self.dir / "letreado_revision.pdf"
        documento, _pagina = _pdf_con_letreado(["DEMANDANTE: JUAN PEREZ GARCIA"])
        documento.save(str(entrada))
        documento.close()

        texto, contexto = cargar_pdf_estruturado(str(entrada))
        contexto["documento"].close()
        self.assertIn("JUAN PEREZ GARCIA", texto)

    def test_columnas_dun_so_caracter_non_se_pegan(self):
        """Falso positivo a evitar: unha fila de táboa con celas dun só
        carácter tamén chega coma "letras soltas", pero separadas moito
        máis ca a altura da letra -- non se debe colapsar en "12345"."""
        from anonimizador.pdf_estrutura import _ensamblar_texto

        fila = [
            (str(n), 0, 0, (50.0 * n, 100.0, 50.0 * n + 6.0, 110.0), 0)
            for n in range(1, 7)
        ]
        texto, _palabras = _ensamblar_texto(fila)
        self.assertEqual(texto, "1 2 3 4 5 6")


# -- A25 ----------------------------------------------------------------------

def _debuxar_texto_vectorial(pagina, texto: str, rect, tamano: int = 30) -> None:
    """Debuxa `texto` coma TRAZOS pechados (contornos dos glifos), non
    coma texto: é o que fan os programas de deseño ao "vectorizar" e
    certos conversores de escaneos. Na páxina non queda ningún carácter
    -- só camiños -- pero para o ollo (e para o OCR) lese igual."""
    documento_aux = fitz.open()
    auxiliar = documento_aux.new_page(width=int(rect.width * 4), height=int(rect.height * 4))
    auxiliar.insert_text((2, auxiliar.rect.height - 8), texto, fontsize=tamano * 4 * 0.9)
    pix = auxiliar.get_pixmap()
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    _limiar, binaria = cv2.threshold(cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY), 128, 255, cv2.THRESH_BINARY_INV)
    contornos, _xerarquia = cv2.findContours(binaria, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    documento_aux.close()

    escala_x, escala_y = rect.width / pix.width, rect.height / pix.height
    for contorno in contornos:
        if len(contorno) < 3:
            continue
        puntos = [
            fitz.Point(rect.x0 + px * escala_x, rect.y0 + py * escala_y)
            for px, py in contorno[:, 0, :]
        ]
        forma = pagina.new_shape()
        forma.draw_polyline(puntos + [puntos[0]])
        forma.finish(color=(0, 0, 0), fill=(0, 0, 0), even_odd=True)
        forma.commit()


def _trazos_negros(ruta) -> list:
    with fitz.open(str(ruta)) as doc:
        return [
            fitz.Rect(debuxo["rect"])
            for pagina in doc for debuxo in pagina.get_drawings()
            if debuxo.get("fill") == (0.0, 0.0, 0.0)
        ]


@unittest.skipUnless(_TESSERACT_DISPOÑIBLE, "require Tesseract")
class TestA25TrazosVectoriais(_Base):
    def test_nome_vectorizado_non_deixa_trazos_no_ficheiro(self):
        documento = fitz.open()
        pagina = documento.new_page()
        pagina.insert_text((72, 60), BASE, fontsize=11)
        _debuxar_texto_vectorial(pagina, "Juan Perez Garcia", fitz.Rect(40, 80, 420, 110))
        saida = self._procesar(documento, "vectorizado")

        self.assertEqual(_trazos_negros(saida), [], "quedan os trazos do nome no ficheiro")
        self._sen_datos_no_ocr(saida)

    def test_unha_raia_de_taboa_que_cruza_o_tachado_non_se_perde(self):
        """O contrapeso do arranxo anterior: eliminar TODO o que toque o
        tachado borraría as liñas das táboas (o formato que este módulo
        existe para conservar). A raia ten que seguir alí."""
        documento = fitz.open()
        pagina = documento.new_page()
        pagina.insert_text((72, 100), f"El demandante Juan Perez Garcia, DNI {DNI}.", fontsize=11)
        pagina.draw_line(fitz.Point(20, 96), fitz.Point(560, 96), color=(0, 0, 0))
        saida = self._procesar(documento, "raia_taboa")

        with fitz.open(str(saida)) as doc:
            anchos = [fitz.Rect(d["rect"]).width for d in doc[0].get_drawings()]
        self.assertTrue(any(ancho > 400 for ancho in anchos), f"perdeuse a raia da táboa: {anchos}")
        self._sen_datos_en_texto_nin_bytes(saida)

    def test_codigo_debuxado_en_vectorial_desaparece_do_ficheiro(self):
        """Un QR DEBUXADO módulo a módulo (non incrustado coma imaxe):
        detectábase e tapábase, pero o debuxo seguía no ficheiro."""
        documento = fitz.open()
        pagina = documento.new_page()
        pagina.insert_text((72, 80), BASE, fontsize=11)
        modulos = cv2.QRCodeEncoder.create().encode(f"DNI {DNI} Juan Perez Garcia")
        lado = 100 / (modulos.shape[0] + 8)
        forma = pagina.new_shape()
        for i in range(modulos.shape[0]):
            for j in range(modulos.shape[0]):
                if modulos[i, j] == 0:
                    forma.draw_rect(fitz.Rect(
                        400 + (j + 4) * lado, 500 + (i + 4) * lado,
                        400 + (j + 5) * lado, 500 + (i + 5) * lado,
                    ))
        forma.finish(color=None, fill=(0, 0, 0))
        forma.commit()
        saida = self._procesar(documento, "qr_vectorial")

        self.assertEqual(_qr_decodificable(saida), [])
        self.assertEqual(_trazos_negros(saida), [], "queda o debuxo do QR no ficheiro")


if __name__ == "__main__":
    unittest.main()
