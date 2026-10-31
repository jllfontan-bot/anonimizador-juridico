import os

# Estas probas escribíronse coa interface e os códigos en galego (PERSOA_...).
os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")
import sys
import tempfile
import unittest
from pathlib import Path

from odf import teletype
from odf.opendocument import OpenDocumentText, load
from odf.text import LineBreak, P, S, Span, Tab

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador.pipeline import (
    anonimizar_texto,
    cargar_documento_estruturado,
    cargar_texto,
    gardar_documento_estruturado,
)
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


def _odt_cun_paragrafo(ruta: Path, pezas: list) -> None:
    """Un parágrafo feito de anacos: texto (str) ou elementos (salto,
    tabulador, espazos, span...) coma fillos directos."""
    documento = OpenDocumentText()
    paragrafo = P()
    for peza in pezas:
        if isinstance(peza, str):
            paragrafo.addText(peza)
        else:
            paragrafo.addElement(peza)
    documento.text.addElement(paragrafo)
    documento.save(str(ruta))


def _paragrafo_gardado(ruta: Path):
    return load(str(ruta)).getElementsByType(P)[0]


def _contar(paragrafo, clase) -> int:
    return len(paragrafo.getElementsByType(clase))


class TestSaltosTabuladoresEEspazosOdt(unittest.TestCase):
    """`text:line-break`, `text:tab` e `text:s` fillos DIRECTOS do
    parágrafo líanse coma "" (`teletype.extractText` só os converte cando
    van dentro do elemento que se lle pasa), e as palabras de cada lado
    chegaban pegadas á detección."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _gardar(self, pezas: list, texto_final=None, substitucions=None) -> object:
        entrada, saida = self.dir / "entrada.odt", self.dir / "saida.odt"
        _odt_cun_paragrafo(entrada, pezas)
        texto, contexto = cargar_documento_estruturado(str(entrada))
        if texto_final is None:
            texto_final = texto
        gardar_documento_estruturado(contexto, texto_final, str(saida), substitucions)
        return _paragrafo_gardado(saida)

    def test_leer_salto_tabulador_e_espazos(self):
        ruta = self.dir / "escrito.odt"
        _odt_cun_paragrafo(ruta, ["Nome:", Tab(), "Rúa Maior 5", LineBreak(), "Vigo", S(c=3), "fin"])
        self.assertEqual(cargar_texto(str(ruta)), "Nome:\tRúa Maior 5\nVigo   fin")

    def test_por_tramos_conserva_salto_e_tabulador(self):
        pezas = ["Nome:", Tab(), "Xoán Pérez", LineBreak(), "segue o texto"]
        paragrafo = self._gardar(pezas, "Nome:\tPERSOA_1\nsegue o texto", [(6, 16, "PERSOA_1")])
        self.assertEqual(teletype.extractText(paragrafo), "Nome:\tPERSOA_1\nsegue o texto")
        self.assertEqual(_contar(paragrafo, Tab), 1)
        self.assertEqual(_contar(paragrafo, LineBreak), 1)

    # O span con estilo propio só se conserva se se escribe por tramos (a
    # reserva deixa o parágrafo nun só anaco).
    def test_por_tramos_substitucion_que_cobre_un_tabulador(self):
        pezas = ["Xoán", Tab(), "Pérez ", Span(text="fin")]
        paragrafo = self._gardar(pezas, "PERSOA_1 fin", [(0, 10, "PERSOA_1")])
        self.assertEqual(teletype.extractText(paragrafo), "PERSOA_1 fin")
        self.assertEqual(_contar(paragrafo, Tab), 0)
        self.assertEqual(_contar(paragrafo, Span), 1)

    def test_por_tramos_substitucion_que_empeza_nun_tabulador(self):
        pezas = ["Xoán", Tab(), "Pérez ", Span(text="fin")]
        paragrafo = self._gardar(pezas, "XoánX fin", [(4, 10, "X")])
        self.assertEqual(teletype.extractText(paragrafo), "XoánX fin")
        self.assertEqual(_contar(paragrafo, Tab), 0)
        self.assertEqual(_contar(paragrafo, Span), 1)

    def test_reserva_escribe_salto_e_tabulador_coma_elementos(self):
        paragrafo = self._gardar(["Nome:", Tab(), "Xoán", LineBreak(), "fin"], "Nome:\teditado\nfin")
        self.assertEqual(teletype.extractText(paragrafo), "Nome:\teditado\nfin")
        self.assertEqual(_contar(paragrafo, Tab), 1)
        self.assertEqual(_contar(paragrafo, LineBreak), 1)

    def test_span_reescrito_conserva_o_seu_salto(self):
        span = Span()
        span.addText("Xoán")
        span.addElement(LineBreak())
        span.addText("Pérez")
        paragrafo = self._gardar([span, " fin"], "PERSOA_1\nPérez fin", [(0, 4, "PERSOA_1")])
        self.assertEqual(teletype.extractText(paragrafo), "PERSOA_1\nPérez fin")
        self.assertEqual(_contar(paragrafo, LineBreak), 1)


if __name__ == "__main__":
    unittest.main()
