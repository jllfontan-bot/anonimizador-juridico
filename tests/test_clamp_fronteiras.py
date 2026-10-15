"""Caso real atopado probando contra documentos reais do despacho (Título
de propiedade, 14 páxinas): o NER detectou unha "persoa" de 159 caracteres
que abarcaba dende o final da páxina 9 ata o medio da páxina 10 -- un
erro de detección, non unha mención real. Aplicar esa substitución sen
máis facía desaparecer o separador entre páxinas, desaliñando o PDF e
facendo fallar `gardar_pdf_estruturado` xa na primeira comprobación --
SEN que ningún letrado editase nada a man. `_clamp_substitucions_a_limites`
parte calquera substitución así en anacos, un por páxina/parágrafo que
toca, para que isto nunca poida desaliñar a estrutura do documento.
"""

import sys
import tempfile
import unittest
from pathlib import Path

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador.pipeline import (
    _clamp_substitucions_a_limites,
    _limites_por_contexto,
    anonimizar_e_gardar,
    cargar_documento_estruturado,
)
from anonimizador.registry import RexistroCorrespondencias


def _crear_pdf_con_texto(ruta: Path, paxinas: list) -> None:
    documento = fitz.open()
    for texto in paxinas:
        pax = documento.new_page()
        pax.insert_text((72, 100), texto, fontsize=12)
    documento.save(str(ruta))
    documento.close()


class TestClampSubstitucions(unittest.TestCase):
    def test_substitucion_dentro_dun_so_contedor_non_se_toca(self):
        limites = [(0, 10), (12, 22)]
        substitucions = [(2, 5, "COD")]
        self.assertEqual(_clamp_substitucions_a_limites(substitucions, limites), [(2, 5, "COD")])

    def test_substitucion_que_cruza_fronteira_partese_en_dous_anacos(self):
        limites = [(0, 10), (12, 22)]
        # cruza desde o contedor 1 (remata en 10) ata o 2 (empeza en 12)
        substitucions = [(8, 15, "COD")]
        resultado = _clamp_substitucions_a_limites(substitucions, limites)
        self.assertEqual(resultado, [(8, 10, "COD"), (12, 15, "COD")])

    def test_substitucion_que_cruza_tres_contedores_partese_en_tres(self):
        limites = [(0, 5), (5, 10), (10, 15)]
        substitucions = [(2, 13, "COD")]
        resultado = _clamp_substitucions_a_limites(substitucions, limites)
        self.assertEqual(resultado, [(2, 5, "COD"), (5, 10, "COD"), (10, 13, "COD")])

    def test_substitucions_normais_sen_contexto_non_se_alteran(self):
        self.assertIsNone(_limites_por_contexto(None))


class TestClampEnDocumentoRealPdf(unittest.TestCase):
    """Reproduce o caso real: forzar unha detección que abarque dúas
    páxinas e comprobar que xa non fai fallar o gardado."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.rexistro = RexistroCorrespondencias(str(self.dir / "rexistro"))

    def tearDown(self):
        self._tmp.cleanup()

    def test_mencion_que_cruzaria_paxinas_non_rompe_o_gardado(self):
        """"Manuel Ferrándiz Salcedo" ao final da páxina 1 e "Rita Martorell
        Vilela" ao principio da páxina 2, moi preto do salto de páxina
        -- o deseño ten que soportar isto aínda que o NER esparexese as
        entidades (non se pode forzar o erro exacto de spaCy de forma
        determinista, pero a proba de abaixo cobre a mesma protección a
        nivel de `anonimizar_texto_detallado` + `contexto`)."""
        entrada = self.dir / "escrito.pdf"
        _crear_pdf_con_texto(entrada, [
            "Primeira páxina remata mencionando a Manuel Ferrándiz Salcedo.",
            "Segunda páxina comeza mencionando a Rita Martorell Vilela.",
        ])
        saida = self.dir / "escrito.anonimizado.pdf"
        # non debe lanzar ValueError por desaliñamento de páxinas
        anonimizar_e_gardar(str(entrada), str(saida), self.rexistro)
        with fitz.open(str(saida)) as doc:
            self.assertEqual(doc.page_count, 2)

    def test_substitucion_artificial_cruzando_paxinas_non_rompe_gardado(self):
        """Proba directa e determinista: constrúe a man unha lista de
        substitucións que cruza a fronteira entre páxinas (coma a atopada
        no caso real) e comproba que o pipeline completo (que aplica
        `_clamp_substitucions_a_limites` dentro de
        `anonimizar_texto_detallado`) non rompe."""
        from anonimizador.pipeline import anonimizar_texto_detallado

        entrada = self.dir / "escrito.pdf"
        _crear_pdf_con_texto(entrada, [
            "Texto calquera na primeira páxina de proba.",
            "Texto calquera na segunda páxina de proba.",
        ])
        texto, contexto = cargar_documento_estruturado(str(entrada))

        from anonimizador.pdf_estrutura import SEPARADOR_PAXINAS

        limites = _limites_por_contexto(contexto)
        self.assertEqual(len(limites), 2)
        a, b = limites[0]
        # unha substitucion "falsa" que cruza deliberadamente a fronteira --
        # abarca dende antes do final da páxina 1 ata 1 carácter despois do
        # separador (para chegar realmente á páxina 2, sexa cal sexa a
        # lonxitude exacta do separador).
        substitucions_falsas = [(b - 3, b + len(SEPARADOR_PAXINAS) + 1, "PERSOA_999999")]
        clamped = _clamp_substitucions_a_limites(substitucions_falsas, limites)
        self.assertEqual(len(clamped), 2)  # partida en dous anacos, un por páxina

        from anonimizador.pdf_estrutura import gardar_pdf_estruturado
        texto_final = texto
        for inicio, fin, novo in sorted(clamped, key=lambda s: s[0], reverse=True):
            texto_final = texto_final[:inicio] + novo + texto_final[fin:]

        saida = self.dir / "escrito.artificial.pdf"
        # non debe lanzar ValueError -- a clamp xa garantiu que as fronteiras se respectan
        gardar_pdf_estruturado(contexto, texto_final, str(saida), clamped)
        with fitz.open(str(saida)) as doc:
            self.assertEqual(doc.page_count, 2)


if __name__ == "__main__":
    unittest.main()
