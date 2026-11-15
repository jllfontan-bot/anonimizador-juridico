"""Carpeta temporal que non tira abaixo o traballo se Windows non deixa borrala
(WinError 32: PDF aínda aberto por PyMuPDF; caso real do 15/11/2026)."""
import os

os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")

import shutil
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador import temporales
from anonimizador.temporales import DirectorioTemporal


class TestDirectorioTemporal(unittest.TestCase):
    def test_borra_o_cartafol_ao_saír(self):
        with DirectorioTemporal() as tmp:
            (Path(tmp) / "a.txt").write_text("x")
            ruta = Path(tmp)
        self.assertFalse(ruta.exists())

    def test_reintenta_se_o_ficheiro_esta_en_uso_e_ao_final_borra(self):
        real = shutil.rmtree
        chamadas = []

        def rmtree(ruta, *a, **k):
            chamadas.append(1)
            if len(chamadas) < 3:
                raise PermissionError(32, "usado por outro proceso")
            return real(ruta, *a, **k)

        with mock.patch.object(temporales.shutil, "rmtree", rmtree), mock.patch.object(temporales.time, "sleep"):
            with DirectorioTemporal() as tmp:
                ruta = Path(tmp)
        self.assertGreaterEqual(len(chamadas), 3)
        self.assertFalse(ruta.exists())

    def test_se_nunca_se_pode_borrar_non_lanza_erro(self):
        real = shutil.rmtree

        def rmtree(ruta, *a, **k):
            if k.get("ignore_errors"):
                return None
            raise PermissionError(32, "usado por outro proceso")

        with mock.patch.object(temporales.shutil, "rmtree", rmtree), mock.patch.object(temporales.time, "sleep"):
            with DirectorioTemporal() as tmp:
                ruta = Path(tmp)
            # non lanzou: o resultado do traballo non se perde
        real(ruta, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
