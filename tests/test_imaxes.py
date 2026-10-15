"""Imaxes soltas (`imaxes.py`): a saída é unha imaxe do MESMO formato e
tamaño en píxeles, sen o dato nos píxeles (comprobado con OCR de novo
sobre a imaxe final) e sen metadatos EXIF. Nomes inventados."""
import os

# Estas probas escribíronse coa interface e os códigos en galego (PERSOA_...).
os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")

import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador.pipeline import anonimizar_e_gardar, anonimizar_zip, ruta_saida_por_defecto
from anonimizador.registry import RexistroCorrespondencias

_TESSERACT_DISPOÑIBLE = shutil.which("tesseract") is not None
_TEXTO = "Manuel Ferrandiz Salcedo DNI 30014811Z"


def _imaxe_con_texto(texto: str = _TEXTO) -> Image.Image:
    documento = fitz.open()
    pagina = documento.new_page(width=900, height=300)
    pagina.insert_text((30, 100), texto, fontsize=28)
    pagina.insert_text((30, 200), "Consello de Contas", fontsize=28)
    pix = pagina.get_pixmap()
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def _reocr(ruta) -> str:
    import pytesseract
    with Image.open(ruta) as imaxe:
        return pytesseract.image_to_string(imaxe.convert("RGB").resize((imaxe.width * 3, imaxe.height * 3)), lang="spa")


@unittest.skipUnless(_TESSERACT_DISPOÑIBLE, "tesseract non instalado")
class TestImaxeConservaFormato(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.rexistro = RexistroCorrespondencias(str(self.dir / "rexistro"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _procesar(self, nome, **gardar):
        entrada = self.dir / nome
        _imaxe_con_texto().save(entrada, **gardar)
        saida = ruta_saida_por_defecto(str(entrada))
        anonimizar_e_gardar(str(entrada), saida, self.rexistro)
        return entrada, Path(saida)

    def _comprobar(self, entrada, saida, formato):
        self.assertEqual(saida.suffix, entrada.suffix)
        with Image.open(entrada) as a, Image.open(saida) as b:
            self.assertEqual(b.format, formato)
            self.assertEqual(b.size, a.size)
        texto = _reocr(saida)
        for dato in ("Manuel", "Ferrandiz", "30014811"):
            self.assertNotIn(dato, texto)
        self.assertIn("Consello de Contas", texto)

    def test_jpg(self):
        self._comprobar(*self._procesar("escaneo.jpg"), "JPEG")

    def test_png(self):
        self._comprobar(*self._procesar("captura.png"), "PNG")

    def test_tiff(self):
        self._comprobar(*self._procesar("fax.tiff"), "TIFF")

    def test_sen_metadatos_exif(self):
        exif = Image.Exif()
        exif[0x013B] = "Xoán Páez Veiga"  # Artist
        exif[0x010F] = "Cámara de proba"  # Make
        _entrada, saida = self._procesar("foto.jpg", exif=exif.tobytes())
        with Image.open(saida) as imaxe:
            self.assertEqual(dict(imaxe.getexif()), {})
        self.assertNotIn(b"Xo", saida.read_bytes().split(b"\xff\xda")[0])

    def test_imaxe_dentro_dun_zip(self):
        entrada = self.dir / "escaneo.png"
        _imaxe_con_texto().save(entrada)
        zip_entrada = self.dir / "expediente.zip"
        with zipfile.ZipFile(zip_entrada, "w") as z:
            z.write(entrada, "docs/escaneo.png")
        zip_saida = self.dir / "expediente.anonimizado.zip"
        informe = anonimizar_zip(str(zip_entrada), str(zip_saida), self.rexistro)
        self.assertEqual(informe["omitidos"], [])
        with zipfile.ZipFile(zip_saida) as z:
            nomes = z.namelist()
            self.assertEqual(len(nomes), 1)
            self.assertTrue(nomes[0].endswith(".anonimizado.png"))
            (self.dir / "saida.png").write_bytes(z.read(nomes[0]))
        self.assertNotIn("Ferrandiz", _reocr(self.dir / "saida.png"))


if __name__ == "__main__":
    unittest.main()
