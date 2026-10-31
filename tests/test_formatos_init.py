"""Punto de enganche do paquete `formatos` (extensión -> lector)."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador import formatos
from anonimizador.formatos import follas, paxinas_html, presentacions


class TestFormatos(unittest.TestCase):
    def test_cada_extension_apunta_ao_seu_modulo(self):
        self.assertEqual(
            set(formatos.LECTORES),
            {".xlsx", ".ods", ".csv", ".pptx", ".odp", ".html", ".htm"},
        )
        for ext in follas.FORMATOS:
            self.assertIs(formatos.LECTORES[ext], follas)
        for ext in presentacions.FORMATOS:
            self.assertIs(formatos.LECTORES[ext], presentacions)
        for ext in paxinas_html.FORMATOS:
            self.assertIs(formatos.LECTORES[ext], paxinas_html)

    def test_extensions_soportadas(self):
        self.assertEqual(formatos.EXTENSIONS, tuple(sorted(formatos.LECTORES)))

    def test_a_markdown_despacha_pola_extension_sen_distinguir_maiusculas(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "DATOS.CSV"
            ruta.write_text("a,b\n1,2\n", encoding="utf-8")
            self.assertIn("| a | b |", formatos.a_markdown(str(ruta)))

    def test_convertir_pasa_as_opcions_so_a_quen_as_entende(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "pax.html"
            ruta.write_text("<h1>Titulo</h1><p>texto</p>", encoding="utf-8")
            # `max_filas` e `dir_csv` son das follas: o HTML ignóraos
            conv = formatos.convertir(str(ruta), max_filas=3, dir_csv=d)
            self.assertIn("# Titulo", conv.markdown)

    def test_extension_descoñecida_levanta_erro_claro(self):
        with self.assertRaises(ValueError):
            formatos.a_markdown("algo.xyz")

    def test_formatos_que_so_valen_sen_anonimizar(self):
        # En modo anonimizado rexéitanse ata ter os seus tests de fugas (punto 6).
        self.assertEqual(formatos.EXTENSIONS_SO_SEN_ANONIMIZAR, formatos.EXTENSIONS)


if __name__ == "__main__":
    unittest.main()
