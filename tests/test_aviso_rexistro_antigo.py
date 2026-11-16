"""Aviso (nunca fusión) cuando hay DOS registros cifrados distintos: el de
Documentos (que se usa) y el antiguo de %LOCALAPPDATA%. Caso real 16/11/2026."""
import os

os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador import arranque_windows as aw


class TestAvisoRexistroAntigo(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        raiz = Path(self._tmp.name)
        self.datos, self.antigo = raiz / "Documentos" / "Anonimizador", raiz / "Local" / "Anonimizador"
        self.datos.mkdir(parents=True)
        self.antigo.mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _rex(self, base: Path, contido: bytes):
        (base / "datos_rexistro").mkdir(exist_ok=True)
        (base / "datos_rexistro" / "rexistro.enc").write_bytes(contido)

    def _aviso(self):
        return self.datos / aw.AVISO_REXISTRO_ANTIGO

    def test_sen_rexistro_antigo_non_avisa(self):
        self._rex(self.datos, b"real")
        self.assertFalse(aw.avisar_se_rexistro_antigo_difire(self.datos, self.antigo))
        self.assertFalse(self._aviso().exists())

    def test_rexistros_iguais_non_avisan(self):
        self._rex(self.datos, b"mesmo"); self._rex(self.antigo, b"mesmo")
        self.assertFalse(aw.avisar_se_rexistro_antigo_difire(self.datos, self.antigo))

    def test_rexistros_distintos_avisan_e_non_tocan_ningun(self):
        self._rex(self.datos, b"real"); self._rex(self.antigo, b"proba")
        self.assertTrue(aw.avisar_se_rexistro_antigo_difire(self.datos, self.antigo))
        ruta, pegada = self._aviso().read_text(encoding="utf-8").splitlines()
        self.assertEqual(Path(ruta), self.antigo / "datos_rexistro")
        self.assertEqual(pegada, aw.pegada_rexistro(self.antigo / "datos_rexistro"))
        self.assertEqual((self.datos / "datos_rexistro" / "rexistro.enc").read_bytes(), b"real")
        self.assertEqual((self.antigo / "datos_rexistro" / "rexistro.enc").read_bytes(), b"proba")

    def test_visto_non_repite_pero_si_cambia_o_antigo_volve_avisar(self):
        self._rex(self.datos, b"real"); self._rex(self.antigo, b"proba")
        aw.avisar_se_rexistro_antigo_difire(self.datos, self.antigo)
        pegada = self._aviso().read_text(encoding="utf-8").splitlines()[1]
        (self.datos / aw.AVISO_REXISTRO_ANTIGO_VISTO).write_text(pegada, encoding="utf-8")
        self._aviso().unlink()
        self.assertFalse(aw.avisar_se_rexistro_antigo_difire(self.datos, self.antigo))
        self._rex(self.antigo, b"proba cambiada")
        self.assertTrue(aw.avisar_se_rexistro_antigo_difire(self.datos, self.antigo))

    def test_se_deixan_de_diferir_o_aviso_desaparece(self):
        self._rex(self.datos, b"real"); self._rex(self.antigo, b"proba")
        aw.avisar_se_rexistro_antigo_difire(self.datos, self.antigo)
        self._rex(self.antigo, b"real")
        self.assertFalse(aw.avisar_se_rexistro_antigo_difire(self.datos, self.antigo))
        self.assertFalse(self._aviso().exists())


class TestPaxinaWeb(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._cwd = os.getcwd()
        os.chdir(self._tmp.name)
        from anonimizador import web
        self.web = web
        self.client = web.app.test_client()

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def test_a_pantalla_amosa_o_aviso_e_pechalo_lembra_a_pegada(self):
        Path(aw.AVISO_REXISTRO_ANTIGO).write_text("C:\\antigo\\datos_rexistro\nabc123", encoding="utf-8")
        self.assertEqual(self.web._aviso_rexistro_antigo(), "C:\\antigo\\datos_rexistro")
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("C:\\antigo\\datos_rexistro", html)
        r = self.client.post("/aviso-rexistro-antigo/pechar")
        self.assertEqual(r.status_code, 302)
        self.assertFalse(Path(aw.AVISO_REXISTRO_ANTIGO).exists())
        self.assertEqual(Path(aw.AVISO_REXISTRO_ANTIGO_VISTO).read_text(encoding="utf-8"), "abc123")
        self.assertNotIn("C:\\antigo\\datos_rexistro", self.client.get("/").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
