"""Membretes de organismos, aviso de modelo incompatible e aviso da clave.

Os tres casos veñen do que informou o usuario o 27/09/2026 probando o
programa xa instalado (Windows e Ubuntu):

1. anonimizábanse membretes ("XUNTA DE GALICIA", "Consellería de...") coma
   se fosen persoas;
2. a causa de fondo era que os paquetes levaban o modelo de idioma 3.8.0
   con spaCy 3.7.5 -- combinación que detecta peor sen dar ningún erro;
3. a quen instala o programa non se lle di nunca que existe unha clave de
   cifrado nin onde queda.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador import ner, sen_consola, web  # noqa: E402
from anonimizador.pipeline import anonimizar_texto  # noqa: E402
from anonimizador.registry import RexistroCorrespondencias  # noqa: E402


class TestMembretesDeOrganismos(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.rexistro = RexistroCorrespondencias(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _anonimizar(self, texto):
        return anonimizar_texto(texto, self.rexistro)[0]

    def test_membrete_da_xunta_non_se_anonimiza(self):
        for membrete in (
            "XUNTA DE GALICIA\nConsellería de Facenda e Administración Pública",
            "Xunta de Galicia. Consellería de Sanidade. Servizo Galego de Saúde.",
            "XUNTA DE GALICIA CONSELLERIA DO MEDIO RURAL Servizo de Montes",
        ):
            with self.subTest(membrete=membrete):
                self.assertEqual(self._anonimizar(membrete), membrete)

    def test_organos_xudiciais_non_se_anonimizan(self):
        for texto in (
            "Tribunal Superior de Xustiza de Galicia, Sala do Contencioso-Administrativo.",
            "Audiencia Provincial de Lugo, Sección 1ª.",
            "Xulgado do Social número 2 de Lugo.",
            "Universidade de Santiago de Compostela.",
        ):
            with self.subTest(texto=texto):
                self.assertNotIn("PERSOA_", self._anonimizar(texto))

    def test_persoa_pegada_a_un_organismo_si_se_anonimiza(self):
        """A guarda NON pode tapar un nome real que vaia canda o organismo."""
        saida = self._anonimizar(
            "Informe do Servizo Galego de Saúde asinado por Brais Ogando Fandiño."
        )
        self.assertIn("PERSOA_", saida)
        self.assertNotIn("Ogando Fandiño", saida)
        self.assertIn("Servizo Galego de Saúde", saida)

    def test_apelidos_que_parecen_organismos_seguen_sendo_persoas(self):
        """"Sala" é un apelido real: a guarda só actúa sobre "Sala do/de..."."""
        saida = self._anonimizar("Rosa Solana Viana e Manuel Illana Carballo comparecen.")
        self.assertNotIn("Solana Viana", saida)
        self.assertNotIn("Illana Carballo", saida)
        self.assertEqual(saida.count("PERSOA_"), 2)


class TestAvisoModeloIncompatible(unittest.TestCase):
    def test_modelo_instalado_e_compatible(self):
        self.assertIsNone(ner.aviso_compatibilidade_modelo())

    def test_modelo_doutra_serie_avisa(self):
        class NlpFalso:
            meta = {"spacy_version": ">=99.0.0,<100.0.0", "version": "99.0.0"}

        aviso = ner._comprobar_compatibilidade(NlpFalso())
        self.assertIsNotNone(aviso)
        self.assertIn("es_core_news_md", aviso)
        self.assertIn("99.0.0", aviso)

    def test_sen_metadatos_non_inventa_avisos(self):
        class NlpSenMeta:
            meta = {}

        self.assertIsNone(ner._comprobar_compatibilidade(NlpSenMeta()))


class TestSenConsolaEnWindows(unittest.TestCase):
    def test_en_mac_e_linux_non_toca_nada(self):
        if os.name == "nt":  # pragma: no cover -- este test é para POSIX
            self.skipTest("execútase en Windows")
        self.assertFalse(sen_consola.aplicar())

    def test_engade_create_no_window(self):
        """Simula Windows para comprobar que o parche engade a bandeira."""
        from pytesseract import pytesseract as pt

        orixinal = pt.subprocess
        nome_orixinal = os.name
        esperado = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        rexistro = {}

        class SubprocessFalso:
            def Popen(self, *a, **k):  # noqa: N802
                rexistro["popen"] = k.get("creationflags", 0)

            def check_output(self, *a, **k):
                rexistro["check_output"] = k.get("creationflags", 0)

        try:
            os.name = "nt"
            pt.subprocess = SubprocessFalso()
            self.assertTrue(sen_consola.aplicar())
            # as DÚAS vías polas que pytesseract lanza tesseract.exe: o OCR
            # (Popen) e a comprobación de versión (check_output)
            pt.subprocess.Popen(["tesseract"])
            pt.subprocess.check_output(["tesseract", "--version"])
            self.assertEqual(rexistro["popen"] & esperado, esperado)
            self.assertEqual(rexistro["check_output"] & esperado, esperado)
            # idempotente: chamalo outra vez non apila envoltorios
            envoltorio = pt.subprocess
            self.assertTrue(sen_consola.aplicar())
            self.assertIs(pt.subprocess, envoltorio)
        finally:
            os.name = nome_orixinal
            pt.subprocess = orixinal


class TestAvisoDaClaveNaPaxinaDeInicio(unittest.TestCase):
    def setUp(self):
        self.cliente = web.app.test_client()
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmp.cleanup()

    def test_cartafol_inexistente_non_se_crea_ao_abrir_a_paxina(self):
        """Abrir a páxina de inicio NON pode crear un rexistro (nin a súa
        clave): un erro de escritura na ruta enchía o disco de rexistros
        baleiros."""
        novo = Path(self._tmp.name) / "aínda-non-existe"
        resposta = self.cliente.get(f"/?rexistro={novo}")
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(novo.exists())
        self.assertIn("Aínda non hai rexistro", resposta.get_data(as_text=True))

    def test_clave_en_ficheiro_dise_onde_está(self):
        RexistroCorrespondencias(self._tmp.name)
        html = self.cliente.get(f"/?rexistro={self._tmp.name}").get_data(as_text=True)
        self.assertIn("nun ficheiro", html)
        self.assertIn("clave.key", html)

    def test_clave_no_chaveiro_que_xa_non_está_non_tumba_a_páxina(self):
        """Reinstalación do sistema ou outro usuario: o marcador segue aí
        pero a clave xa non. Antes a páxina de inicio daba un erro 500."""
        (Path(self._tmp.name) / "clave.chaveiro").write_text("marcador", encoding="utf-8")
        (Path(self._tmp.name) / "rexistro.enc").write_bytes(b"cifrado")
        resposta = self.cliente.get(f"/?rexistro={self._tmp.name}")
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("chaveiro do sistema", resposta.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
