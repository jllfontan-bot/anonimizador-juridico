"""Idioma do programa (castelán por defecto, galego a escoller): códigos de
persoa e etiquetas que se escriben nos documentos, preferencia gardada e
reversión aceptando os dous prefixos. Datos inventados."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador import idioma  # noqa: E402
from anonimizador.pipeline import anonimizar_texto  # noqa: E402
from anonimizador.registry import RexistroCorrespondencias  # noqa: E402

_CONTRASINAL = "contrasinal_proba_1234"
_TEXTO = "Manuel Ferrándiz Salcedo, con DNI 30014811H, vive na rúa do Franco 12 de Santiago."


def _en(lingua):
    return mock.patch.dict(os.environ, {idioma.VARIABLE: lingua})


class TestPreferencia(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._cwd = os.getcwd()
        os.chdir(self._tmp.name)
        self._env = mock.patch.dict(os.environ)
        self._env.start()
        os.environ.pop(idioma.VARIABLE, None)

    def tearDown(self):
        self._env.stop()
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def test_sen_preferencia_e_castelan(self):
        self.assertEqual(idioma.actual(), "es")

    def test_a_preferencia_gardada_sobrevive(self):
        idioma.gardar("gl")
        self.assertEqual(idioma.actual(), "gl")
        idioma.gardar("es")
        self.assertEqual(idioma.actual(), "es")

    def test_preferencia_estragada_cae_ao_castelan(self):
        Path(idioma.FICHEIRO_PREFERENCIAS).write_text("{non é json", encoding="utf-8")
        self.assertEqual(idioma.actual(), "es")

    def test_idioma_descoñecido_non_se_garda(self):
        with self.assertRaises(ValueError):
            idioma.gardar("fr")

    def test_a_variable_de_contorno_manda(self):
        idioma.gardar("es")
        with _en("gl"):
            self.assertEqual(idioma.actual(), "gl")


class TestCodigos(unittest.TestCase):
    def test_visible_e_canonico(self):
        self.assertEqual(idioma.codigo_visible("PERSOA_000007", "es"), "PERSONA_000007")
        self.assertEqual(idioma.codigo_visible("PERSOA_000007", "gl"), "PERSOA_000007")
        for codigo in ("PERSONA_000007", "PERSOA_000007", "ID_000007"):
            self.assertEqual(idioma.codigo_canonico(codigo), "PERSOA_000007")
        self.assertEqual(idioma.codigo_canonico("[DNI_NIE]"), "[DNI_NIE]")

    def test_codigos_dentro_dun_texto(self):
        texto = "PERSOA_000001 e PERSONA_000002 (ID_000003)."
        self.assertEqual(idioma.codigos_visibles_no_texto(texto, "es"),
                         "PERSONA_000001 e PERSONA_000002 (PERSONA_000003).")


class TestDocumentoSegundoOIdioma(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.rexistro = RexistroCorrespondencias(self._tmp.name)
        self.rexistro.definir_contrasinal_reversion(_CONTRASINAL)

    def tearDown(self):
        self._tmp.cleanup()

    def test_castelan(self):
        with _en("es"):
            anon, _ = anonimizar_texto(_TEXTO, self.rexistro)
        self.assertIn("PERSONA_000001", anon)
        self.assertNotIn("PERSOA_", anon)
        self.assertIn("[DIRECCIÓN]", anon)
        self.assertNotIn("Ferrándiz", anon)

    def test_galego(self):
        with _en("gl"):
            anon, _ = anonimizar_texto(_TEXTO, self.rexistro)
        self.assertIn("PERSOA_000001", anon)
        self.assertIn("[ENDEREZO]", anon)

    def test_a_mesma_persoa_leva_o_mesmo_numero_nos_dous_idiomas(self):
        with _en("gl"):
            anon_gl, _ = anonimizar_texto(_TEXTO, self.rexistro)
        with _en("es"):
            anon_es, _ = anonimizar_texto(_TEXTO, self.rexistro)
        self.assertIn("PERSOA_000001", anon_gl)
        self.assertIn("PERSONA_000001", anon_es)

    def test_reverter_acepta_os_dous_prefixos(self):
        with _en("es"):
            anonimizar_texto(_TEXTO, self.rexistro)
        for codigo in ("PERSONA_000001", "PERSOA_000001", " PERSONA_000001 "):
            dados = self.rexistro.reverter(codigo, "proba", _CONTRASINAL)
            self.assertIn("Manuel Ferrándiz Salcedo", dados["nomes"])

    def test_fusionar_con_codigos_en_castelan(self):
        with _en("es"):
            anonimizar_texto("Comparece Uxía Roel Salcedo.", self.rexistro)
            anon, informe = anonimizar_texto("Asina Uxía Roel Salcedo.", self.rexistro)
        persoa = informe["persoas"][0]
        self.assertTrue(persoa["marcado_para_revision"])
        self.assertEqual(persoa["posibles_coincidencias"], ["PERSONA_000001"])
        self.assertIn("PERSONA_000001", persoa["motivo"])
        self.rexistro.fusionar("PERSONA_000001", persoa["codigo"])
        dados = self.rexistro.reverter(persoa["codigo"], "proba", _CONTRASINAL)
        self.assertEqual(dados["codigo_actual"], "PERSOA_000001")


if __name__ == "__main__":
    unittest.main()
