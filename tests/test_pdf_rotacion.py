"""Caso real atopado nunha certificación de burofax: nunha marxe con texto
VERTICAL (moi habitual en rexistros mercantís/notariais -- o número de
inscrición impreso ao longo do lateral da folla), o código de substitución
inseríase sempre en HORIZONTAL, solapando e facendo ilexible tanto o
código coma o propio texto vertical orixinal ao seu redor.

`pdf_estrutura.py` detecta agora a orientación de cada liña de texto
NATIVO (`get_text("dict")`, campo "dir") e insire o código coa MESMA
rotación -- estes tests cobren as catro orientacións posibles (0/90/180/270).
"""

import sys
import tempfile
import unittest
from pathlib import Path

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador.pdf_estrutura import cargar_pdf_estruturado, gardar_pdf_estruturado
from anonimizador.pipeline import anonimizar_texto_detallado
from anonimizador.registry import RexistroCorrespondencias


def _crear_pdf_rotado(ruta: Path, texto: str, rotate: int, punto=(72, 400)) -> None:
    documento = fitz.open()
    pagina = documento.new_page(width=500, height=500)
    pagina.insert_text(punto, texto, fontsize=11, rotate=rotate)
    documento.save(str(ruta))
    documento.close()


class TestRotacionTextoNativo(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.rexistro = RexistroCorrespondencias(str(self.dir / "rexistro"))

    def tearDown(self):
        self._tmp.cleanup()

    # Puntos de ancoraxe elixidos para que o texto (que medra en distinta
    # dirección segundo a rotación -- cara á dereita, arriba, esquerda ou
    # abaixo) quede sempre dentro da páxina de proba (500x500).
    _PUNTOS_POR_ROTACION = {0: (72, 400), 90: (72, 480), 180: (430, 100), 270: (72, 20)}

    def _procesar(self, rotate: int, punto=None):
        if punto is None:
            punto = self._PUNTOS_POR_ROTACION[rotate]
        entrada = self.dir / f"rotado_{rotate}.pdf"
        _crear_pdf_rotado(entrada, "Rexistro de Manuel Ferrandiz Salcedo aqui", rotate, punto)
        texto, contexto = cargar_pdf_estruturado(str(entrada))
        texto_anon, informe, substitucions = anonimizar_texto_detallado(
            texto, self.rexistro, contexto=contexto
        )
        saida = self.dir / f"rotado_{rotate}.anonimizado.pdf"
        gardar_pdf_estruturado(contexto, texto_anon, str(saida), substitucions)
        return saida

    def _palabras_da_paxina(self, ruta_pdf):
        with fitz.open(str(ruta_pdf)) as doc:
            return doc[0].get_text("dict")["blocks"]

    def test_deteccion_de_rotacion_por_direccion(self):
        from anonimizador.pdf_estrutura import _rotacion_mais_preto
        self.assertEqual(_rotacion_mais_preto((1, 0)), 0)
        self.assertEqual(_rotacion_mais_preto((0, -1)), 90)
        self.assertEqual(_rotacion_mais_preto((-1, 0)), 180)
        self.assertEqual(_rotacion_mais_preto((0, 1)), 270)

    def _fontsize_do_codigo(self, ruta_pdf):
        """Devolve o "size" reportado por get_text("dict") para o span que
        contén "PERSOA_" -- serve para comprobar que se inseriu cun tamaño
        de letra razoable, non un valor dispar."""
        for bloque in self._palabras_da_paxina(ruta_pdf):
            for liña in bloque.get("lines", []):
                for span in liña["spans"]:
                    if "PERSOA_" in span["text"]:
                        return span["size"], liña["dir"]
        return None, None

    def test_rotacion_0_segue_horizontal(self):
        saida = self._procesar(0)
        fontsize, direccion = self._fontsize_do_codigo(saida)
        self.assertIsNotNone(fontsize)
        self.assertAlmostEqual(direccion[0], 1, places=1)
        self.assertAlmostEqual(direccion[1], 0, places=1)

    def test_rotacion_90_insire_en_vertical(self):
        saida = self._procesar(90)
        fontsize, direccion = self._fontsize_do_codigo(saida)
        self.assertIsNotNone(fontsize, "non se atopou o código inserido -- perdeuse a rotación?")
        self.assertAlmostEqual(direccion[0], 0, places=1)
        self.assertAlmostEqual(direccion[1], -1, places=1)

    def test_rotacion_180_insire_invertido(self):
        saida = self._procesar(180)
        fontsize, direccion = self._fontsize_do_codigo(saida)
        self.assertIsNotNone(fontsize)
        self.assertAlmostEqual(direccion[0], -1, places=1)
        self.assertAlmostEqual(direccion[1], 0, places=1)

    def test_rotacion_270_insire_en_vertical_invertido(self):
        saida = self._procesar(270)
        fontsize, direccion = self._fontsize_do_codigo(saida)
        self.assertIsNotNone(fontsize)
        self.assertAlmostEqual(direccion[0], 0, places=1)
        self.assertAlmostEqual(direccion[1], 1, places=1)

    def test_texto_orixinal_desaparece_en_calquera_rotacion(self):
        for rotate in (0, 90, 180, 270):
            with self.subTest(rotate=rotate):
                saida = self._procesar(rotate)
                with fitz.open(str(saida)) as doc:
                    texto_final = doc[0].get_text()
                self.assertNotIn("Manuel", texto_final)
                self.assertNotIn("Ferrandiz", texto_final)
                self.assertIn("PERSOA_", texto_final)


if __name__ == "__main__":
    unittest.main()
