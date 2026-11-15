"""Explorador: os atallos e o punto de partida usan as carpetas REAIS do
usuario en Windows (Escritorio, Documentos, Descargas), non `~/Desktop`...

Caso real (portátil con Windows 11, 15/11/2026): as carpetas de usuario están
redirixidas a outro disco (Escritorio en `D:\\Escritorio`, Documentos en
`D:\\Documentos`), pero `C:\\Users\\<usuario>\\Documents` e `Desktop` seguen a
existir, baleiras. O explorador abría nesa carpeta baleira e os atallos
levaban a carpetas baleiras: parecía que non funcionaba.
"""
import os

# Estas probas escribíronse coa interface e os códigos en galego (PERSOA_...).
os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador import explorador, idioma


class TestCarpetasDeUsuarioRedirixidas(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        raiz = Path(self._tmp.name)
        # "C:\Users\admin": as carpetas existen pero están baleiras...
        self.casa = raiz / "C" / "admin"
        for nome in ("Documents", "Desktop", "Downloads"):
            (self.casa / nome).mkdir(parents=True)
        # ...e as de verdade están noutro disco.
        self.reais = {
            "documentos": raiz / "D" / "Documentos",
            "escritorio": raiz / "D" / "Escritorio",
            "descargas": raiz / "D" / "Descargas",
        }
        for ruta in self.reais.values():
            ruta.mkdir(parents=True)
        (self.reais["documentos"] / "demanda.pdf").write_bytes(b"%PDF-1.4")

    def tearDown(self):
        self._tmp.cleanup()

    def _windows(self):
        return (
            mock.patch.object(explorador.Path, "home", return_value=self.casa),
            mock.patch.object(explorador, "_carpeta_conocida", side_effect=lambda clave: self.reais.get(clave)),
        )

    def _atallos(self):
        return {a["nome"]: a["ruta"] for a in explorador._atallos()}

    def test_atallos_levan_ás_carpetas_reais_e_non_ás_baleiras(self):
        casa, conocida = self._windows()
        with casa, conocida:
            atallos = self._atallos()
        self.assertEqual(atallos[idioma.t("exp.escritorio")], str(self.reais["escritorio"]))
        self.assertEqual(atallos[idioma.t("exp.documentos")], str(self.reais["documentos"]))
        self.assertEqual(atallos[idioma.t("exp.descargas")], str(self.reais["descargas"]))

    def test_non_ofrece_a_carpeta_baleira_de_c_coma_atallo_repetido(self):
        casa, conocida = self._windows()
        with casa, conocida:
            rutas = [a["ruta"] for a in explorador._atallos()]
        self.assertNotIn(str(self.casa / "Documents"), rutas)
        self.assertNotIn(str(self.casa / "Desktop"), rutas)
        self.assertNotIn(str(self.casa / "Downloads"), rutas)

    def test_empeza_en_documentos_reais_cos_seus_ficheiros(self):
        casa, conocida = self._windows()
        with casa, conocida:
            self.assertEqual(explorador._ruta_inicial(), self.reais["documentos"])
            r = explorador.listar(None)
        self.assertEqual(Path(r["ruta"]), self.reais["documentos"])
        self.assertEqual([e["nome"] for e in r["entradas"]], ["demanda.pdf"])

    def test_sen_a_api_de_windows_usa_as_carpetas_da_carpeta_persoal(self):
        with mock.patch.object(explorador.Path, "home", return_value=self.casa), \
                mock.patch.object(explorador, "_carpeta_conocida", return_value=None):
            self.assertEqual(explorador._ruta_inicial(), self.casa / "Documents")
            atallos = self._atallos()
        self.assertEqual(atallos[idioma.t("exp.escritorio")], str(self.casa / "Desktop"))

    def test_carpeta_conocida_non_existe_fora_de_windows(self):
        with mock.patch.object(explorador.sys, "platform", "linux"):
            for clave in ("documentos", "escritorio", "descargas"):
                self.assertIsNone(explorador._carpeta_conocida(clave))

    def test_carpeta_conocida_ignora_unha_clave_descoñecida(self):
        self.assertIsNone(explorador._carpeta_conocida("musica"))

    def test_carpeta_conocida_que_xa_non_existe_cae_na_persoal(self):
        borrada = self.reais["documentos"].parent / "Borrada"
        with mock.patch.object(explorador.Path, "home", return_value=self.casa), \
                mock.patch.object(explorador, "_carpeta_conocida", return_value=borrada):
            self.assertEqual(explorador._ruta_inicial(), self.casa / "Documents")


@unittest.skipUnless(sys.platform == "win32", "só en Windows: pregunta de verdade á API do sistema")
class TestCarpetaConocidaEnWindows(unittest.TestCase):
    def test_devolve_rutas_que_existen(self):
        for clave in ("documentos", "escritorio", "descargas"):
            ruta = explorador._carpeta_conocida(clave)
            self.assertTrue(ruta is None or Path(ruta).is_dir(), (clave, ruta))


if __name__ == "__main__":
    unittest.main()
