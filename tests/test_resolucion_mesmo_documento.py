import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador import ner, resolution
from anonimizador.pipeline import anonimizar_texto
from anonimizador.registry import RexistroCorrespondencias


def _anonimizar(texto):
    with tempfile.TemporaryDirectory() as d:
        return anonimizar_texto(texto, RexistroCorrespondencias(d))


class TestMesmaPersoaNoMesmoDocumento(unittest.TestCase):
    """Nun escrito xurídico a persoa identifícase co DNI na PRIMEIRA mención
    e nas seguintes xa vai só co nome (indicación do usuario, 27/09/2026).
    Antes, a mención sen DNI quedaba coma persoa distinta (outro código,
    marcada coma posible homónimo) -- e en modo automático, sen revisión
    humana, ninguén o resolvía."""

    def test_mencions_posteriores_sen_dni_son_a_mesma_persoa(self):
        anon, informe = _anonimizar(
            "En el acto del juicio comparece Manuel Ferrándiz Salcedo, con DNI 71234569J.\n"
            "Consta en el informe que Manuel Ferrándiz Salcedo padece esclerosis múltiple.\n"
        )
        self.assertEqual(len(informe["persoas"]), 1)
        self.assertEqual(anon.count("PERSOA_000001"), 3)  # 2 nomes + o DNI
        self.assertNotIn("PERSOA_000002", anon)
        self.assertFalse(informe["persoas"][0]["marcado_para_revision"])

    def test_mencion_sen_dni_antes_da_que_o_leva(self):
        """A orde non importa: un encabezado co nome pode vir antes da
        comparecencia co DNI."""
        anon, informe = _anonimizar(
            "Recurso de Manuel Ferrándiz Salcedo.\n"
            "Comparece Manuel Ferrándiz Salcedo, con DNI 71234569J, y expone.\n"
        )
        self.assertEqual(len(informe["persoas"]), 1)
        self.assertEqual(anon.count("PERSOA_000001"), 3)  # 2 nomes + o DNI

    def test_dous_dni_distintos_mesmo_nome_mencion_sen_dni_segue_ambigua(self):
        """Pai e fillo co mesmo nome, cada un identificado co seu DNI: unha
        mención posterior só co nome NON se pode asignar a ningún dos dous
        con seguridade -- segue á parte e marcada, coma antes."""
        anon, informe = _anonimizar(
            "Comparece Manuel Ferrándiz Salcedo, con DNI 71234569J, y su hijo "
            "Manuel Ferrándiz Salcedo, con DNI 30014811H.\n"
            "Manuel Ferrándiz Salcedo declaró después sobre los hechos.\n"
        )
        codigos = {p["codigo"] for p in informe["persoas"]}
        self.assertEqual(len(codigos), 3)
        self.assertTrue(any(p["marcado_para_revision"] for p in informe["persoas"]))
        # Cada DNI queda xunto á mención que o leva, non á da liña seguinte.
        self.assertIn("su hijo PERSOA_000002, con DNI PERSOA_000002.", anon)
        marcadas = [p["codigo"] for p in informe["persoas"] if p["marcado_para_revision"]]
        self.assertEqual(marcadas, ["PERSOA_000003"])


class TestAsociacionDni(unittest.TestCase):
    def test_formulario_dni_antes_do_nome_na_liña_seguinte(self):
        """A penalización por fin de liña non debe impedir emparellar cando
        esa é a única mención: nun formulario o DNI pode ir primeiro."""
        anon, informe = _anonimizar("DNI: 71234569J\nNombre: Manuel Ferrándiz Salcedo\n")
        self.assertEqual(len(informe["persoas"]), 1)
        self.assertEqual(anon, "DNI: PERSOA_000001\nNombre: PERSOA_000001\n")


if __name__ == "__main__":
    unittest.main()


class TestDniDaPersoaAnterior(unittest.TestCase):
    """"Nome, con DNI X, e dona Outra" (auditoría do rexistro, 03/10/2026): o DNI
    ía para a persoa SEGUINTE por estar 1 carácter máis preto, e no rexistro a
    ficha dunha persoa quedaba co DNI doutra."""

    def test_con_dni_vai_coa_persoa_de_diante(self):
        t = "Comparece don Xoán Páez Veiga, con DNI 30014811H, e dona Uxía Roel Salcedo.\nXoán Páez Veiga asina."
        entidades, _ = ner.detectar(t)
        grupos = {g.representante: g.dni for g in resolution.agrupar(entidades, t)}
        self.assertEqual(grupos.get("Xoán Páez Veiga"), "30014811H")
        self.assertIsNone(grupos.get("Uxía Roel Salcedo"))


class TestDocumentoSenTitularNoAnexo(unittest.TestCase):
    """AnuncioG0759-281025-0002 (auditoría do rexistro, lote 4): nunha táboa do
    anexo con "Expediente | NIF/NIE/pasaporte" e SEN nomes, o pasaporte levaba o
    código da directora que asina xusto enriba do "ANEXO" -- no rexistro
    quedaba coma se fose dela."""

    def test_o_documento_do_anexo_non_e_da_asinante(self):
        t = ("Pontevedra, 28 de outubro de 2025\nBlanca Galán Alonso\nDirectora territorial de Pontevedra\n"
             "ANEXO\nExpediente\nNIF/NIE/pasaporte\nPO-PR212E/2025/01532\nFK9081726\nPO-PR212E/2025/01938\n90821317K\n")
        with tempfile.TemporaryDirectory() as d:
            anon, _ = anonimizar_texto(t, RexistroCorrespondencias(d))
        codigo = re.search(r"(PERSOA_\d+)\nDirectora", anon).group(1)
        self.assertNotIn(codigo, anon.split("ANEXO", 1)[1], anon)
        self.assertNotIn("FK9081726", anon)
        self.assertNotIn("90821317K", anon)
