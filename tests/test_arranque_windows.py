"""Arranque do paquete MSIX (Microsoft Store): copia do rexistro da versión
anterior, aviso na pantalla de inicio e páxina "Acerca de"."""
import os

os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from anonimizador import arranque_windows, web


class TestCopiaDoRexistroAntigo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.antigo = base / "LocalAppData" / "Anonimizador"
        self.datos = base / "Documentos" / "Anonimizador"
        self.datos.mkdir(parents=True)
        (self.antigo / "datos_rexistro").mkdir(parents=True)
        (self.antigo / "datos_rexistro" / "rexistro.enc").write_bytes(b"cifrado")
        (self.antigo / "preferencias.json").write_text('{"idioma": "gl"}', encoding="utf-8")
        (self.antigo / "anonimizador.log").write_text("log vello", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_copia_rexistro_e_preferencias_e_deixa_o_orixinal(self):
        self.assertTrue(arranque_windows.copiar_rexistro_antigo(self.datos, self.antigo))
        self.assertEqual((self.datos / "datos_rexistro" / "rexistro.enc").read_bytes(), b"cifrado")
        self.assertTrue((self.datos / "preferencias.json").is_file())
        self.assertFalse((self.datos / "anonimizador.log").exists())
        self.assertTrue((self.antigo / "datos_rexistro" / "rexistro.enc").is_file())
        aviso = (self.datos / arranque_windows.AVISO_MIGRACION).read_text(encoding="utf-8")
        self.assertEqual(aviso, str(self.antigo / "datos_rexistro"))

    def test_nunca_pisa_un_rexistro_que_xa_hai_en_documentos(self):
        (self.datos / "datos_rexistro").mkdir()
        (self.datos / "datos_rexistro" / "rexistro.enc").write_bytes(b"novo")
        self.assertFalse(arranque_windows.copiar_rexistro_antigo(self.datos, self.antigo))
        self.assertEqual((self.datos / "datos_rexistro" / "rexistro.enc").read_bytes(), b"novo")
        self.assertFalse((self.datos / arranque_windows.AVISO_MIGRACION).exists())

    def test_sen_version_anterior_non_fai_nada(self):
        self.assertFalse(arranque_windows.copiar_rexistro_antigo(self.datos, self.datos.parent / "non_existe"))

    def test_entorno_de_tesseract(self):
        raiz = Path(self.tmp.name) / "paquete"
        with mock.patch.dict(os.environ, {"PATH": "orixinal"}):
            arranque_windows.preparar_entorno(raiz)
            self.assertEqual(os.environ["TESSDATA_PREFIX"], str(raiz / "runtime" / "tesseract" / "tessdata"))
            self.assertTrue(os.environ["PATH"].startswith(str(raiz / "runtime" / "tesseract" / "bin")))
            self.assertTrue(os.environ["PATH"].endswith("orixinal"))


class TestPantallas(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)
        self.client = web.app.test_client()

    def tearDown(self):
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def test_aviso_de_rexistro_copiado_ata_pechalo(self):
        Path(arranque_windows.AVISO_MIGRACION).write_text(r"C:\Users\x\AppData\Local\Anonimizador\datos_rexistro", encoding="utf-8")
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("Copiouse a <code>Documentos", html)
        self.assertIn(r"AppData\Local\Anonimizador", html)
        self.client.post("/aviso-migracion/pechar")
        self.assertFalse(Path(arranque_windows.AVISO_MIGRACION).exists())
        self.assertNotIn("Copiouse a", self.client.get("/").get_data(as_text=True))

    def test_acerca_de_con_licenza_version_e_codigo(self):
        html = self.client.get("/acerca").get_data(as_text=True)
        self.assertIn("AGPL-3.0", html)
        self.assertIn("José Luis López Fontán", html)
        self.assertIn("https://github.com/jllfontan-bot/anonimizador-juridico", html)
        self.assertIn("GNU AFFERO GENERAL PUBLIC LICENSE", html)
        version = (Path(web.__file__).resolve().parents[2] / "VERSION").read_text(encoding="utf-8").strip()
        self.assertIn(f"Versión {version}", html)

    def test_inicio_liga_o_manual_e_o_acerca_de(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('href="/acerca"', html)
        self.assertIn('href="/manual"', html)  # docs/03-Manual-de-uso.pdf existe no repo

    def test_ligazons_externas_so_as_coñecidas(self):
        with mock.patch.object(web, "_abrir_fora") as abrir:
            self.client.get("/abrir/codigo")
            self.client.get("/abrir/https%3A%2F%2Fexemplo.com")
        abrir.assert_called_once_with("https://github.com/jllfontan-bot/anonimizador-juridico")

    def test_manual_no_idioma_escollido(self):
        with mock.patch.object(web, "_abrir_fora") as abrir:
            with mock.patch.dict(os.environ, {"ANONIMIZADOR_IDIOMA": "es"}):
                self.client.get("/manual")
            with mock.patch.dict(os.environ, {"ANONIMIZADOR_IDIOMA": "gl"}):
                self.client.get("/manual")
        es, gl = (Path(c.args[0]) for c in abrir.call_args_list)
        self.assertEqual(es.parent.name, "es")
        self.assertEqual(gl.parent.name, "docs")


if __name__ == "__main__":
    unittest.main()
