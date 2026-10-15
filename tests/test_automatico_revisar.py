"""Botón "Revisar este documento" no modo automático (decisión do usuario
10/10/2026): os documentos con posibles fugas gardan a súa sesión de revisión
coa MESMA anonimización e os MESMOS códigos; ao confirmar, o resultado revisado
substitúe ao automático (nada de reprocesar: daría códigos novos)."""
import os

# Estas probas escribíronse coa interface e os códigos en galego (PERSOA_...).
os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador import web


class TestRevisarDesdeAutomatico(unittest.TestCase):
    def setUp(self):
        web.SESIONS.clear()
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.rexistro_dir = str(self.dir / "rexistro")
        self.client = web.app.test_client()

    def tearDown(self):
        self._tmp.cleanup()

    def _automatico(self, nome, texto):
        ruta = self.dir / nome
        ruta.write_text(texto, encoding="utf-8")
        r = self.client.post("/procesar", data={"ruta": str(ruta), "rexistro": self.rexistro_dir, "modo": "automatico"})
        return r.get_data(as_text=True)

    def test_documento_con_posible_fuga_ten_boton_e_reutiliza_os_codigos(self):
        html = self._automatico("con_risco.txt", "Comparece don Xoán Páez Veiga. Referencia 34867809 do expediente.")
        m = re.search(r'href="(/revisar/([0-9a-f]+)[^"]*)"', html)
        self.assertIsNotNone(m, "falta o botón Revisar este documento")
        self.assertIn("Revisar este documento", html)
        sid = m.group(2)
        sesion = web.SESIONS[sid]
        saida = Path(sesion["ruta_saida_fixa"])
        self.assertTrue(saida.exists())
        self.assertIn("PERSOA_000001", saida.read_text(encoding="utf-8"))
        # revisar: xeneralizar o número e confirmar
        self.client.post(f"/revisar/{sid}/confirmar", data={
            "rexistro_dir": self.rexistro_dir, "decisions_v2": "1", "anonimizar": "PERSOA_000001",
            "fragmentos": "34867809 => [NÚMERO]"})
        final = saida.read_text(encoding="utf-8")
        self.assertIn("[NÚMERO]", final)
        self.assertIn("PERSOA_000001", final)          # mesmo código, non un novo
        self.assertNotIn("PERSOA_000002", final)
        self.assertEqual(len(list(self.dir.glob("*.anonimizado*"))), 1)  # substitúe, non crea outro

    def test_documento_sen_avisos_non_garda_sesion(self):
        html = self._automatico("limpo.txt", "Comparece don Xoán Páez Veiga ante o xulgado.")
        self.assertNotIn("Revisar este documento", html)
        self.assertEqual(web.SESIONS, {})


if __name__ == "__main__":
    unittest.main()
