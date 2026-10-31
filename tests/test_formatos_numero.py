"""Número tal e como o amosa unha cela de Excel (`formatos/formato_numero.py`)."""

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador.formatos.formato_numero import formatar


class TestFormatoNumero(unittest.TestCase):
    def test_millares_e_decimais_con_moeda(self):
        self.assertEqual(formatar(1234.5, '#,##0.00 "€"'), "1.234,50 €")
        self.assertEqual(formatar(1234.5, "#,##0.00\\ [$€-407]"), "1.234,50 €")
        self.assertEqual(formatar(1234.5, "$#,##0.00"), "$1.234,50")
        self.assertEqual(formatar(1234567, "#,##0"), "1.234.567")

    def test_porcentaxes(self):
        self.assertEqual(formatar(0.25, "0%"), "25%")
        self.assertEqual(formatar(0.256, "0.0%"), "25,6%")

    def test_ceros_a_esquerda_dos_codigos(self):
        self.assertEqual(formatar(123, "00000"), "00123")

    def test_redondeo_como_excel(self):
        self.assertEqual(formatar(2.5, "0"), "3")
        self.assertEqual(formatar(3.14159, "0.00"), "3,14")

    def test_decimais_opcionais(self):
        self.assertEqual(formatar(1234.5, "#,##0.0#"), "1.234,5")
        self.assertEqual(formatar(12, "#,##0.0#"), "12,0")

    def test_negativos_e_cero_con_seccions(self):
        self.assertEqual(formatar(-5, "0;(0)"), "(5)")
        self.assertEqual(formatar(-1234.5, "#,##0.00"), "-1.234,50")
        self.assertEqual(formatar(0, '0;-0;"cero"'), "cero")

    def test_texto_literal_despois_do_numero(self):
        self.assertEqual(formatar(7, '0 "uds"'), "7 uds")

    def test_formatos_que_non_se_saben_ler_devolven_none(self):
        for formato in ("General", "", "0.00E+00", "# ?/?", "0,", "dd/mm/yyyy", "@", "[>100]0;0"):
            self.assertIsNone(formatar(1234.5, formato), formato)


if __name__ == "__main__":
    unittest.main()
