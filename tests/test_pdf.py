import os

# Estas probas escribíronse coa interface e os códigos en galego (PERSOA_...).
os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import fitz  # PyMuPDF

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador.pdf import cargar_texto_pdf
from anonimizador.pipeline import anonimizar_texto, cargar_texto
from anonimizador.registry import RexistroCorrespondencias

_TESSERACT_DISPOÑIBLE = shutil.which("tesseract") is not None


def _crear_pdf_con_texto(ruta: Path, paxinas: list) -> None:
    documento = fitz.open()
    for texto in paxinas:
        paxina = documento.new_page()
        paxina.insert_text((72, 72), texto, fontsize=12)
    documento.save(str(ruta))
    documento.close()


def _crear_pdf_escaneado(ruta: Path, texto: str) -> None:
    """Simula unha paxina escaneada: debuxa o texto como imaxe (non como
    capa de texto seleccionable), que e o que un escaner real produce."""
    documento = fitz.open()
    paxina = documento.new_page()
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 900, 300))
    pix.set_rect(pix.irect, (255, 255, 255))
    imaxe_doc = fitz.open()
    imaxe_paxina = imaxe_doc.new_page(width=900, height=300)
    imaxe_paxina.insert_text((30, 100), texto, fontsize=28)
    pix_texto = imaxe_paxina.get_pixmap()
    paxina.insert_image(fitz.Rect(0, 0, 900, 300), pixmap=pix_texto)
    documento.save(str(ruta))
    documento.close()
    imaxe_doc.close()


class TestLecturaPdfNativo(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.rexistro = RexistroCorrespondencias(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_extrae_texto_nativo_sen_ocr(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "escrito.pdf"
            _crear_pdf_con_texto(ruta, [
                "Manuel Ferrándiz Salcedo, con DNI 30014811-Z, presenta este escrito.",
                "Segunda páxina do mesmo escrito, sen máis datos persoais.",
            ])
            texto = cargar_texto_pdf(str(ruta))
            self.assertIn("Manuel Ferrándiz Salcedo", texto)
            self.assertIn("Segunda páxina", texto)

    def test_pipeline_completo_desde_pdf(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "escrito.pdf"
            _crear_pdf_con_texto(ruta, [
                "Manuel Ferrándiz Salcedo, con DNI 30014811-Z, presenta este escrito.",
            ])
            texto = cargar_texto(str(ruta))
            anon, informe = anonimizar_texto(texto, self.rexistro)
            self.assertEqual(len(informe["persoas"]), 1)
            self.assertNotIn("Manuel Ferrándiz Salcedo", anon)
            self.assertIn("PERSOA_", anon)


@unittest.skipUnless(_TESSERACT_DISPOÑIBLE, "Tesseract non está instalado neste ordenador")
class TestOcr(unittest.TestCase):
    def test_ocr_paxina_escaneada(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "escaneado.pdf"
            _crear_pdf_escaneado(ruta, "CANGAS DO MORRAZO")
            texto = cargar_texto_pdf(str(ruta))
            self.assertIn("CANGAS", texto.upper())


if __name__ == "__main__":
    unittest.main()
