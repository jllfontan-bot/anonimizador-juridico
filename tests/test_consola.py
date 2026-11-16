"""Liñas de comandos en Windows con saída en cp1252 (16/11/2026): o aviso «⚠»
das posibles fugas facía saír `cli_conversor` con `UnicodeEncodeError` despois
de escribir o .md. `consola.saida_utf8()` pasa stdout/stderr a UTF-8."""
import os

os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")

import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import docx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador import cli, cli_conversor, consola, idioma


def _cp1252():
    """Coma a saída redirixida en Windows: un ficheiro de texto en cp1252, estrito."""
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")


class TestConsola(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_sen_reconfigurar_o_aviso_rompe_en_cp1252(self):
        # A condición do erro, para que o test de abaixo probe algo de verdade.
        texto = idioma.t("conversor.cli.fugas", nome="a.docx", n=1)
        self.assertTrue(any(ord(c) > 255 for c in texto), texto)
        with self.assertRaises(UnicodeEncodeError):
            print(texto, file=_cp1252())

    def test_saida_utf8_reconfigura_e_non_rompe(self):
        saida, erros = _cp1252(), _cp1252()
        with mock.patch.object(sys, "stdout", saida), mock.patch.object(sys, "stderr", erros):
            consola.saida_utf8()
            print("⚠ posibles fugas")
            print("\udcff", file=sys.stderr)  # nin sequera un carácter imposible
        self.assertEqual(saida.encoding, "utf-8")
        saida.flush()
        self.assertIn("⚠ posibles fugas", saida.buffer.getvalue().decode("utf-8"))

    def test_sen_consola_non_falla(self):
        with mock.patch.object(sys, "stdout", None), mock.patch.object(sys, "stderr", None):
            consola.saida_utf8()  # pythonw: non hai consola

    def test_cli_conversor_con_posibles_fugas_e_saida_cp1252(self):
        ruta = self.dir / "con_risco.docx"
        d = docx.Document()
        d.add_paragraph("Comparece don Xoán Páez Veiga. Referencia 34867809 do expediente.")
        d.save(str(ruta))
        saida, erros = _cp1252(), _cp1252()
        with mock.patch.object(sys, "stdout", saida), mock.patch.object(sys, "stderr", erros):
            codigo = cli_conversor.main([str(ruta), "--anonimizar", "--rexistro", str(self.dir / "rex")])
        self.assertEqual(codigo, 0)
        saida.flush()
        texto = saida.buffer.getvalue().decode("utf-8")
        self.assertIn("⚠", texto)
        self.assertTrue(list(self.dir.glob("*.anonimizado.docx.md")))

    def test_cli_do_anonimizador_reconfigura_ao_empezar(self):
        ruta = self.dir / "nota.txt"
        ruta.write_text("Comparece don Xoán Pérez Vázquez ante o xulgado.\n", encoding="utf-8")
        saida, erros = _cp1252(), _cp1252()
        argv = ["anonimizador", "anonimizar", str(ruta), "--rexistro", str(self.dir / "rex")]
        with mock.patch.object(sys, "stdout", saida), mock.patch.object(sys, "stderr", erros), \
                mock.patch.object(sys, "argv", argv):
            try:
                cli.main()
            except SystemExit as e:
                self.assertIn(e.code, (0, None))
        self.assertEqual(saida.encoding, "utf-8")


if __name__ == "__main__":
    unittest.main()
