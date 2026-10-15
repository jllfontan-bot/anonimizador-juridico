"""Selector nativo de ficheiro/cartafol (`selector.py`).

Non abre un diálogo real en ningún test -- bloquearía a suite agardando
por un clic humano que nunca chega. `subprocess.run` substitúese por un
dobre de proba."""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador import selector


class TestSelector(unittest.TestCase):
    def test_devolve_a_ruta_escollida(self):
        resultado = mock.Mock(stdout="/tmp/exemplo/declaracion.txt\n")
        with mock.patch.object(selector.subprocess, "run", return_value=resultado) as m:
            ruta = selector.escoller("ficheiro")
        self.assertEqual(ruta, "/tmp/exemplo/declaracion.txt")
        args = m.call_args[0][0]
        self.assertIn("ficheiro", args)

    def test_devolve_none_se_se_pecha_sen_escoller(self):
        resultado = mock.Mock(stdout="\n")
        with mock.patch.object(selector.subprocess, "run", return_value=resultado):
            self.assertIsNone(selector.escoller("cartafol"))

    def test_devolve_none_se_o_dialogo_falla(self):
        with mock.patch.object(selector.subprocess, "run", side_effect=OSError("sen interface gráfica")):
            self.assertIsNone(selector.escoller("ficheiro"))

    def test_devolve_none_se_esgota_o_tempo(self):
        import subprocess as sp
        with mock.patch.object(selector.subprocess, "run", side_effect=sp.TimeoutExpired(cmd="x", timeout=1)):
            self.assertIsNone(selector.escoller("cartafol"))


if __name__ == "__main__":
    unittest.main()
