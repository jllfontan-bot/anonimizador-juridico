import os

# Estas probas escribíronse coa interface e os códigos en galego (PERSOA_...).
os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")
import sys
import tempfile
import unittest
from pathlib import Path

from odf.opendocument import OpenDocumentText
from odf.text import P

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador.pipeline import anonimizar_texto, cargar_texto
from anonimizador.registry import RexistroCorrespondencias


def _crear_odt(ruta: Path, paragrafos: list) -> None:
    documento = OpenDocumentText()
    for texto in paragrafos:
        p = P(text=texto)
        documento.text.addElement(p)
    documento.save(str(ruta))


class TestLecturaOdt(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.rexistro = RexistroCorrespondencias(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_extrae_texto_de_odt(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "escrito.odt"
            _crear_odt(ruta, [
                "Manuel Ferrándiz Salcedo, con DNI 30014811Z, presenta este escrito.",
                "Segundo parágrafo, sen máis datos persoais.",
            ])
            texto = cargar_texto(str(ruta))
            self.assertIn("Manuel Ferrándiz Salcedo", texto)
            self.assertIn("Segundo parágrafo", texto)

    def test_pipeline_completo_desde_odt(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "escrito.odt"
            _crear_odt(ruta, ["Manuel Ferrándiz Salcedo, con DNI 30014811Z, presenta este escrito."])
            texto = cargar_texto(str(ruta))
            anon, informe = anonimizar_texto(texto, self.rexistro)
            self.assertEqual(len(informe["persoas"]), 1)
            self.assertNotIn("Manuel Ferrándiz Salcedo", anon)
            self.assertIn("PERSOA_", anon)


if __name__ == "__main__":
    unittest.main()
