"""INVARIANTE: o rexistro cifrado de correspondencias vive SEMPRE en
`Documentos\\Anonimizador\\datos_rexistro`, tanto na Store coma no instalador
clásico, e as actualizacións e desinstalacións NUNCA o mudan nin o borran.

Por que: o rexistro relaciona cada código (PERSOA_000001) co nome real; se un
instalador ou unha actualización traballa noutro cartafol, as persoas reciben
códigos DISTINTOS e xa non se pode reverter nin manter a coherencia entre
documentos xa anonimizados (caso real, 16/11/2026: o lanzador clásico usaba
`%LOCALAPPDATA%\\Anonimizador` e o rexistro non coincidía co da Store).

Se algún día hai que moverlo (fase B: rexistro propio do Reductor), faise con
migración que COPIE (nunca mova) e cun aviso, e estas probas cámbianse
deliberadamente no mesmo cambio."""
import os

os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")

import re
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from anonimizador import arranque_windows, conversor


class TestUbicacionDoRexistro(unittest.TestCase):
    def test_o_cartafol_e_o_subcartafol_do_rexistro_non_cambian(self):
        self.assertEqual(arranque_windows.NOME_CARTAFOL, "Anonimizador")
        ruta = conversor.rexistro_por_defecto()
        self.assertEqual(ruta.name, "datos_rexistro")
        self.assertEqual(ruta.parent.name, "Anonimizador")
        self.assertEqual(ruta.parent.parent, arranque_windows.cartafol_documentos())

    def test_o_reductor_usa_o_mesmo_rexistro_ca_o_anonimizador(self):
        # ata a fase B (rexistro propio do Reductor, con migración)
        self.assertEqual(
            conversor.rexistro_por_defecto(),
            arranque_windows.cartafol_documentos() / arranque_windows.NOME_CARTAFOL / "datos_rexistro",
        )


class TestLanzadorClasico(unittest.TestCase):
    def setUp(self):
        self.vbs = (RAIZ / "instalador/windows/Iniciar-Anonimizador.vbs").read_text(encoding="ascii")
        self.codigo = "\n".join(l for l in self.vbs.splitlines() if not l.lstrip().startswith("'"))

    def test_usa_a_mesma_entrada_ca_a_store(self):
        self.assertIn("anonimizador.arranque_windows", self.codigo)

    def test_non_traballa_en_localappdata_nin_arrinca_pola_cli_antiga(self):
        self.assertNotIn("LOCALAPPDATA", self.codigo.upper())
        self.assertNotIn("anonimizador.cli", self.codigo)
        self.assertNotIn("datos_rexistro", self.codigo)

    def test_a_entrada_da_store_tamen_e_arranque_windows(self):
        usos = [p for p in (RAIZ / "instalador/msix").rglob("*") if p.is_file() and p.suffix in (".py", ".xml", ".in", ".txt", ".vbs")]
        self.assertTrue(any("arranque_windows" in p.read_text(encoding="utf-8", errors="ignore") for p in usos))


class TestDesinstaladorClasico(unittest.TestCase):
    def test_nunca_borra_documentos(self):
        nsi = (RAIZ / "instalador/windows/instalador.nsi").read_text(encoding="utf-8")
        lineas = [l for l in nsi.splitlines() if not l.lstrip().startswith(";")]
        for linea in lineas:
            if re.search(r"\b(RMDir|Delete)\b", linea):
                self.assertNotRegex(linea, r"(?i)Documentos|\$DOCUMENTS|\$PROFILE\\Documents", linea)

    def test_so_pregunta_polos_datos_antigos_de_localappdata(self):
        nsi = (RAIZ / "instalador/windows/instalador.nsi").read_text(encoding="utf-8")
        self.assertIn('StrCpy $1 "$LOCALAPPDATA\\Anonimizador"', nsi)


if __name__ == "__main__":
    unittest.main()
