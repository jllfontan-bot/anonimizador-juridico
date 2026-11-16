"""`copia_md` salta `find_tables` nas páxinas sen debuxos (16/11/2026, rendemento:
0,77 s/páxina nun PDF real de 351 páxinas). A premisa: coa estratexia «lines»
de PyMuPDF, sen `get_drawings()` non hai táboas. Compróbase a premisa en
páxinas variadas (texto en columnas, tabulado, con imaxe, con filete, con
táboa), que a copia sae idéntica á da versión anterior (que buscaba sempre) e
que noutra versión de PyMuPDF ou co analizador de maquetación se busca sempre."""
import os

os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import fitz
import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador import copia_md, lectura


def _paxinas():
    """Páxinas inventadas de varios tipos: (nome, páxina) nun documento en memoria."""
    doc = fitz.open()
    p = doc.new_page()
    for i in range(40):
        p.insert_text((50, 60 + i * 18), f"Liña {i}: comparece Brais Castro Lema, con DNI 87654321X.", fontsize=9)
    p = doc.new_page()  # texto tabulado, coma unha táboa sen liñas
    for i in range(20):
        for col, x in enumerate((50, 200, 350)):
            p.insert_text((x, 60 + i * 16), f"C{col}F{i} valor {i * 7}", fontsize=9)
    p = doc.new_page()  # dúas columnas
    for i in range(30):
        p.insert_text((50, 60 + i * 16), f"Esquerda {i} texto da columna", fontsize=9)
        p.insert_text((320, 60 + i * 16), f"Dereita {i} texto da columna", fontsize=9)
    p = doc.new_page()  # cunha imaxe e texto
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 40), 0)
    pix.clear_with(200)
    p.insert_image(fitz.Rect(50, 50, 150, 150), pixmap=pix)
    p.insert_text((50, 200), "Pé da imaxe con Uxía Rial Souto.", fontsize=9)
    p = doc.new_page()  # filete de cabeceira (un debuxo, pero sen táboa)
    p.draw_line((50, 40), (545, 40))
    p.insert_text((50, 60), "Texto baixo o filete.", fontsize=9)
    p = doc.new_page()  # táboa con liñas
    for f in range(5):
        p.draw_line((50, 60 + f * 20), (350, 60 + f * 20))
    for x in (50, 150, 250, 350):
        p.draw_line((x, 60), (x, 140))
    for f in range(4):
        for c, x in enumerate((55, 155, 255)):
            p.insert_text((x, 75 + f * 20), f"F{f}C{c}", fontsize=8)
    return doc


def _paxina_pdf_referencia(pagina, info, anon, locais):
    """A versión anterior: busca sempre as táboas."""
    with mock.patch.object(copia_md, "_pode_ter_taboas", lambda pagina: True):
        return copia_md._paxina_pdf(pagina, info, anon, locais)


class TestSenDebuxosNonHaiTaboas(unittest.TestCase):
    def test_premisa_sen_debuxos_find_tables_baleiro(self):
        doc = _paxinas()
        for i, pagina in enumerate(doc):
            with self.subTest(paxina=i):
                if not pagina.get_drawings():
                    self.assertEqual(pagina.find_tables().tables, [])
        self.assertTrue(doc[5].find_tables().tables)  # e a táboa con liñas si se atopa

    def test_a_copia_e_identica_a_da_version_anterior(self):
        doc = _paxinas()
        cartafol = tempfile.mkdtemp()
        ruta = Path(cartafol) / "paxinas.pdf"
        doc.save(str(ruta))
        try:
            texto, contexto = lectura.cargar_documento_estruturado(str(ruta))
            limites = copia_md._limites_paxinas(contexto["paxinas"])
            for i, info in enumerate(contexto["paxinas"]):
                inicio, _ = limites[i]
                # Unha substitución inventada por páxina (coma ao anonimizar), para que se busquen táboas.
                locais = [(0, 4, "XXXX")] if len(info.texto) > 4 else []
                anon = copia_md._aplicar_substitucions_a_texto(info.texto, locais)
                pagina = contexto["documento"][i]
                with self.subTest(paxina=i):
                    self.assertEqual(copia_md._paxina_pdf(pagina, info, anon, locais),
                                     _paxina_pdf_referencia(pagina, info, anon, locais))
        finally:
            shutil.rmtree(cartafol, ignore_errors=True)

    def test_noutra_version_ou_co_analizador_de_maquetacion_busca_sempre(self):
        pagina = _paxinas()[0]
        self.assertFalse(pagina.get_drawings())
        self.assertFalse(copia_md._pode_ter_taboas(pagina))
        with mock.patch.object(pymupdf, "VersionBind", "1.30.0"):
            self.assertTrue(copia_md._pode_ter_taboas(pagina))
        with mock.patch.object(pymupdf, "_get_layout", lambda *a, **k: None, create=True):
            self.assertTrue(copia_md._pode_ter_taboas(pagina))


if __name__ == "__main__":
    unittest.main()
