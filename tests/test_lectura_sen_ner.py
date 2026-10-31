"""Ler un documento e xerar a súa copia Markdown sen spaCy (fase 1 do
conversor a .md, ESTUDIO-CONVERSOR-MD punto 13.1): `lectura` e `copia_md`
non deben importar `anonimizador.ner` nin `spacy`, para que un programa
que só converte non teña que levar o NER.

Execútase nun subproceso: neste xa están cargados `ner` e `spacy` polos
demais tests.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import docx
import fitz  # PyMuPDF
from odf.opendocument import OpenDocumentText
from odf.table import Table, TableCell, TableColumn, TableRow
from odf.text import H, P

_RAIZ = Path(__file__).resolve().parents[1]

# Bloquea `spacy` coma se non estivese instalado e comproba ao final que
# nin `spacy` nin `anonimizador.ner` chegaron a cargarse.
_CODIGO = """
import importlib.abc
import sys


class _SenSpacy(importlib.abc.MetaPathFinder):
    def find_spec(self, nome, ruta=None, obxectivo=None):
        if nome == "spacy" or nome.startswith("spacy."):
            raise ModuleNotFoundError("spacy non instalado (proba)", name=nome)
        return None


sys.meta_path.insert(0, _SenSpacy())

from anonimizador import copia_md, lectura

for ruta in sys.argv[1:]:
    texto, contexto = lectura.cargar_documento_estruturado(ruta)
    print("=== " + ruta)
    print(copia_md.xerar(contexto, texto))

cargados = sorted(m for m in sys.modules if m.split(".")[0] == "spacy" or m == "anonimizador.ner")
print("CARGADOS:" + ",".join(cargados))
"""


class TestLecturaSenNer(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _executar(self, *rutas) -> str:
        entorno = dict(os.environ, PYTHONPATH=str(_RAIZ / "src"), ANONIMIZADOR_IDIOMA="gl")
        resultado = subprocess.run(
            [sys.executable, "-c", _CODIGO, *map(str, rutas)],
            capture_output=True, text=True, encoding="utf-8", env=entorno, cwd=str(self.dir),
        )
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        return resultado.stdout

    def _docx(self) -> Path:
        documento = docx.Document()
        documento.add_heading("Demanda de reclamación", 1)
        documento.add_paragraph("Primeiro parágrafo do escrito.")
        taboa = documento.add_table(rows=2, cols=2)
        taboa.cell(0, 0).text = "Nome"
        taboa.cell(0, 1).text = "Cargo"
        taboa.cell(1, 0).text = "Persoa de proba"
        taboa.cell(1, 1).text = "Secretaria"
        documento.sections[0].header.paragraphs[0].text = "Cabeceira do despacho"
        ruta = self.dir / "escrito.docx"
        documento.save(str(ruta))
        return ruta

    def _odt(self) -> Path:
        documento = OpenDocumentText()
        documento.text.addElement(H(outlinelevel=2, text="Feitos"))
        documento.text.addElement(P(text="Texto do primeiro feito."))
        taboa = Table(name="Taboa1")
        taboa.addElement(TableColumn(numbercolumnsrepeated=2))
        for fila in (("Data", "Lugar"), ("hoxe", "Vigo")):
            fila_xml = TableRow()
            for texto in fila:
                cela = TableCell()
                cela.addElement(P(text=texto))
                fila_xml.addElement(cela)
            taboa.addElement(fila_xml)
        documento.text.addElement(taboa)
        ruta = self.dir / "escrito.odt"
        documento.save(str(ruta))
        return ruta

    def _pdf(self) -> Path:
        documento = fitz.open()
        for numero in (1, 2):
            paxina = documento.new_page(width=595, height=842)
            paxina.insert_text((72, 100), f"Texto da paxina {numero} do PDF.", fontsize=11)
        ruta = self.dir / "escrito.pdf"
        documento.save(str(ruta))
        return ruta

    def test_importar_sen_spacy(self):
        # a última liña (PyMuPDF pode avisar antes na saída estándar)
        self.assertEqual(self._executar().strip().split("\n")[-1], "CARGADOS:")

    def test_ler_e_xerar_markdown_sen_spacy(self):
        txt = _RAIZ / "ejemplos" / "declaracion.txt"
        saida = self._executar(self._docx(), self._odt(), self._pdf(), txt)
        self.assertTrue(saida.rstrip().endswith("CARGADOS:"), saida[-300:])
        # .docx: título, táboa e cabeceira
        self.assertIn("# Demanda de reclamación", saida)
        self.assertIn("| Nome | Cargo |\n| --- | --- |\n| Persoa de proba | Secretaria |", saida)
        self.assertIn("Cabeceira do despacho", saida)
        # .odt: título e táboa
        self.assertIn("## Feitos", saida)
        self.assertIn("| Data | Lugar |", saida)
        # PDF: as dúas páxinas, marcadas
        self.assertIn("Texto da paxina 1 do PDF.", saida)
        self.assertIn("<!-- páxina 2 -->", saida)
        # .txt: o texto tal cal
        primeira_liña = txt.read_text(encoding="utf-8").strip().split("\n")[0].strip()
        self.assertIn(primeira_liña, saida)


if __name__ == "__main__":
    unittest.main()
