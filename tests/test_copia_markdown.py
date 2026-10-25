"""Copia en Markdown do documento anonimizado (`copia_md.py`, pedido do
usuario 25/10/2026): para que Claude lea o resultado sen convertelo.

En TODOS os casos compróbase o principal: na copia non queda ningún dato
orixinal -- o texto sae do anonimizado; do orixinal só a estrutura.
"""

import os
import re
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import docx
import fitz  # PyMuPDF
from odf.opendocument import OpenDocumentText
from odf.style import Header, MasterPage, PageLayout
from odf.table import Table, TableCell, TableColumn, TableRow
from odf.text import H, List, ListItem, ListLevelStyleNumber, ListStyle, P

os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from anonimizador import cli, copia_md, idioma, web
from anonimizador.pdf_estrutura import SEPARADOR_PAXINAS, _PaxinaPdf
from anonimizador.pipeline import (
    anonimizar_e_gardar,
    anonimizar_zip,
    listar_ficheiros_soportados,
    ruta_saida_por_defecto,
)
from anonimizador.registry import RexistroCorrespondencias
from test_taboas_pdf import _ANCHOS, _CABECEIRA, _DATOS, _FILAS, _taboa

_NOME = "Xoán Pérez Vázquez"
_DNI = "33045521Z"
_NOME_TABOA = "Antía Varela Doval"
_DATOS_ORIXINAIS = ("Xoán", "Pérez", "Vázquez", _DNI, "Antía", "Varela", "Doval")


class _Base(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.rexistro = RexistroCorrespondencias(str(self.dir / "rexistro"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _sen_datos(self, md: str, datos=_DATOS_ORIXINAIS):
        for dato in datos:
            self.assertNotIn(dato, md, f"{dato!r} á vista na copia Markdown")

    def _anonimizar(self, ruta: Path) -> tuple:
        saida = ruta_saida_por_defecto(str(ruta))
        anonimizar_e_gardar(str(ruta), saida, self.rexistro, copia_md=True)
        copia = Path(saida + ".md")
        self.assertTrue(copia.exists(), "non se gardou a copia Markdown")
        return Path(saida), copia.read_text(encoding="utf-8")


class TestDocx(_Base):
    def _documento(self) -> Path:
        documento = docx.Document()
        documento.add_heading("Demanda de reclamación de cantidade", 1)
        documento.add_paragraph(f"Comparece don {_NOME}, con DNI {_DNI}, ante o xulgado.")
        documento.add_paragraph("Primeiro feito", style="List Number")
        documento.add_paragraph("Segundo feito", style="List Number")
        documento.add_paragraph("Unha viñeta", style="List Bullet")
        taboa = documento.add_table(rows=2, cols=2)
        taboa.cell(0, 0).text = "Nome"
        taboa.cell(0, 1).text = "Cargo"
        taboa.cell(1, 0).text = _NOME_TABOA
        taboa.cell(1, 1).text = "Secretaria"
        documento.add_paragraph("# Parágrafo despois da táboa")
        documento.sections[0].header.paragraphs[0].text = "Despacho de avogados Rúa Nova"
        ruta = self.dir / "escrito.docx"
        documento.save(str(ruta))
        return ruta

    def test_estrutura_e_sen_datos(self):
        saida, md = self._anonimizar(self._documento())
        self.assertTrue(saida.exists())
        self._sen_datos(md)
        self.assertIn("# Demanda de reclamación de cantidade", md)
        self.assertIn("1. Primeiro feito\n2. Segundo feito\n- Unha viñeta", md)
        self.assertIn("| Nome | Cargo |\n| --- | --- |\n| PERSOA_", md)
        self.assertIn("| Secretaria |", md)
        # o texto que empeza por "#" non se converte en título
        self.assertIn("\n\\# Parágrafo despois da táboa", md)
        # a táboa vai no seu sitio, non ao final
        self.assertLess(md.index("Segundo feito"), md.index("| Nome |"))
        self.assertLess(md.index("| Nome |"), md.index("Parágrafo despois"))
        # cabeceiras e pés, ao final
        self.assertTrue(md.rstrip().endswith("Despacho de avogados Rúa Nova"))

    def test_mesmo_codigo_ca_no_documento(self):
        saida, md = self._anonimizar(self._documento())
        codigos_docx = set(re.findall(r"PERSOA_\d+", "\n".join(p.text for p in docx.Document(str(saida)).paragraphs)))
        codigos_md = set(re.findall(r"PERSOA_\d+", md))
        self.assertTrue(codigos_docx)
        self.assertLessEqual(codigos_docx, codigos_md)

    def test_sen_opcion_non_hai_copia(self):
        ruta = self._documento()
        saida = ruta_saida_por_defecto(str(ruta))
        anonimizar_e_gardar(str(ruta), saida, self.rexistro)
        self.assertFalse(Path(saida + ".md").exists())


class TestOdt(_Base):
    def _documento(self) -> Path:
        documento = OpenDocumentText()
        disposicion = PageLayout(name="Disposicion")
        documento.automaticstyles.addElement(disposicion)
        mestra = MasterPage(name="Standard", pagelayoutname=disposicion)
        cabeceira = Header()
        cabeceira.addElement(P(text="Despacho de avogados Rúa Nova"))
        mestra.addElement(cabeceira)
        documento.masterstyles.addElement(mestra)
        numeracion = ListStyle(name="Numeracion")
        numeracion.addElement(ListLevelStyleNumber(level=1, numformat="1", numsuffix="."))
        documento.automaticstyles.addElement(numeracion)

        documento.text.addElement(H(outlinelevel=2, text="Feitos"))
        documento.text.addElement(P(text=f"Comparece don {_NOME}, con DNI {_DNI}, ante o xulgado."))
        lista = List(stylename=numeracion)
        for texto in ("Primeiro feito", "Segundo feito"):
            elemento = ListItem()
            elemento.addElement(P(text=texto))
            lista.addElement(elemento)
        documento.text.addElement(lista)
        taboa = Table(name="Taboa1")
        taboa.addElement(TableColumn(numbercolumnsrepeated=2))
        for fila in (("Nome", "Cargo"), (_NOME_TABOA, "Secretaria")):
            fila_xml = TableRow()
            for texto in fila:
                cela = TableCell()
                cela.addElement(P(text=texto))
                fila_xml.addElement(cela)
            taboa.addElement(fila_xml)
        documento.text.addElement(taboa)
        documento.text.addElement(P(text="Parágrafo final."))
        ruta = self.dir / "escrito.odt"
        documento.save(str(ruta))
        return ruta

    def test_estrutura_e_sen_datos(self):
        _saida, md = self._anonimizar(self._documento())
        self._sen_datos(md)
        self.assertIn("## Feitos", md)
        self.assertIn("1. Primeiro feito\n2. Segundo feito", md)
        self.assertIn("| Nome | Cargo |\n| --- | --- |\n| PERSOA_", md)
        self.assertLess(md.index("| Nome |"), md.index("Parágrafo final."))
        self.assertTrue(md.rstrip().endswith("Despacho de avogados Rúa Nova"))
        self.assertEqual(md.count("Despacho de avogados"), 1)


class TestPdf(_Base):
    def _documento(self) -> Path:
        documento = fitz.open()
        pagina = documento.new_page()
        pagina.insert_text((50, 60), "ANEXO. Resolución de adjudicación de puestos.", fontsize=10)
        _taboa(pagina, 50, 80, _ANCHOS, [_CABECEIRA] + _FILAS)
        pagina.insert_text((50, 330), "Texto despois da táboa.", fontsize=10)
        segunda = documento.new_page()
        segunda.insert_text((50, 60), f"Comparece don {_NOME}, con DNI {_DNI}.", fontsize=10)
        ruta = self.dir / "anexo.pdf"
        documento.save(str(ruta))
        return ruta

    def test_paxinas_taboa_e_sen_datos(self):
        _saida, md = self._anonimizar(self._documento())
        self._sen_datos(md)
        self._sen_datos(md, _DATOS)
        self.assertIn("<!-- páxina 1 -->", md)
        self.assertIn("<!-- páxina 2 -->", md)
        liñas = md.split("\n")
        cabeceira = next(l for l in liñas if l.startswith("| N.º orden"))
        self.assertIn("| Apellidos y nombre |", cabeceira)
        filas = [l for l in liñas if l.startswith("| ") and "PERSOA_" in l]
        self.assertEqual(len(filas), 3, md)
        self.assertTrue(any(l.startswith("| 4 | Analista | Desierto |") for l in liñas), md)
        # o texto de fóra da táboa segue no seu sitio, e unha soa vez
        self.assertEqual(md.count("Texto despois da táboa."), 1)
        self.assertLess(md.index("ANEXO."), md.index("| N.º orden"))
        self.assertLess(md.index("| N.º orden"), md.index("<!-- páxina 2 -->"))

    def test_imaxe_sen_marcas_de_paxina(self):
        contexto = {"tipo": "pdf", "imaxe": {"formato": "PNG"}, "documento": None,
                    "paxinas": [_PaxinaPdf(texto="Liña un\nLiña dous")]}
        self.assertEqual(copia_md.xerar(contexto, "Liña un\nLiña dous"), "Liña un\nLiña dous\n")

    def test_texto_revisado_que_non_casa_vai_sen_estrutura(self):
        contexto = {"tipo": "pdf", "documento": None,
                    "paxinas": [_PaxinaPdf(texto="a"), _PaxinaPdf(texto="b")]}
        md = copia_md.xerar(contexto, "a" + SEPARADOR_PAXINAS + "b" + SEPARADOR_PAXINAS + "c", [])
        self.assertEqual(md, "a\n\nb\n\nc\n")


class TestCastelan(_Base):
    """Co programa en castelán o texto anonimizado leva `PERSONA_000001` e os
    marcadores da copia saen tamén en castelán."""

    def setUp(self):
        super().setUp()
        parche = mock.patch.dict(os.environ, {idioma.VARIABLE: "es"})
        parche.start()
        self.addCleanup(parche.stop)

    def test_docx_con_cabeceira_en_castelan(self):
        documento = docx.Document()
        documento.add_paragraph(f"Comparece don {_NOME}, con DNI {_DNI}.")
        documento.sections[0].header.paragraphs[0].text = "Despacho de abogados Calle Nueva"
        ruta = self.dir / "escrito.docx"
        documento.save(str(ruta))
        _saida, md = self._anonimizar(ruta)
        self._sen_datos(md)
        self.assertIn("PERSONA_000001", md)
        self.assertNotIn("PERSOA_", md)
        self.assertIn("<!-- cabeceras y pies de página -->", md)
        self.assertNotIn("cabeceiras", md)

    def test_pdf_con_marca_de_pagina_en_castelan(self):
        documento = fitz.open()
        documento.new_page().insert_text((50, 60), f"Comparece don {_NOME}, con DNI {_DNI}.", fontsize=10)
        ruta = self.dir / "escrito.pdf"
        documento.save(str(ruta))
        _saida, md = self._anonimizar(ruta)
        self._sen_datos(md)
        self.assertIn("<!-- página 1 -->", md)
        self.assertNotIn("páxina", md)


class TestTextoEMd(_Base):
    def test_txt_escapa_titulos_e_raias(self):
        ruta = self.dir / "nota.txt"
        ruta.write_text(f"# Non é un título\n-----\nComparece don {_NOME}, con DNI {_DNI}.\n", encoding="utf-8")
        _saida, md = self._anonimizar(ruta)
        self._sen_datos(md)
        self.assertIn("\\# Non é un título\n\\-----\n", md)

    def test_md_de_entrada_sae_md_e_sen_copia(self):
        ruta = self.dir / "nota.md"
        ruta.write_text(f"# Escrito\n\nComparece don {_NOME}, con DNI {_DNI}.\n", encoding="utf-8")
        saida = ruta_saida_por_defecto(str(ruta))
        self.assertTrue(saida.endswith("nota.anonimizado.md"), saida)
        anonimizar_e_gardar(str(ruta), saida, self.rexistro, copia_md=True)
        resultado = Path(saida).read_text(encoding="utf-8")
        self._sen_datos(resultado)
        self.assertIn("# Escrito", resultado)
        self.assertEqual(sorted(p.name for p in self.dir.glob("nota*")), ["nota.anonimizado.md", "nota.md"])

    def test_cartafol_le_md_pero_non_as_copias(self):
        for nome in ("a.md", "a.anonimizado.md", "a.anonimizado.pdf.md", "b.anonimizado.txt.md", "c.pdf"):
            (self.dir / nome).write_text("x", encoding="utf-8")
        soportados, omitidos = listar_ficheiros_soportados(str(self.dir))
        self.assertEqual(sorted(Path(r).name for r in soportados), ["a.md", "c.pdf"])
        self.assertIn("a.anonimizado.pdf.md", [Path(r).name for r in omitidos])


class TestZipECli(_Base):
    def test_zip_leva_a_copia_canda_cada_documento(self):
        documento = docx.Document()
        documento.add_paragraph(f"Comparece don {_NOME}, con DNI {_DNI}.")
        documento.save(str(self.dir / "escrito.docx"))
        entrada = self.dir / "expediente.zip"
        with zipfile.ZipFile(entrada, "w") as z:
            z.write(self.dir / "escrito.docx", "carpeta/escrito.docx")
            z.writestr("nota.md", f"Comparece don {_NOME}.")
        saida = self.dir / "saida.zip"
        anonimizar_zip(str(entrada), str(saida), self.rexistro, copia_md=True)
        with zipfile.ZipFile(saida) as z:
            nomes = sorted(z.namelist())
            self.assertEqual(nomes, ["carpeta/escrito.anonimizado.docx", "carpeta/escrito.anonimizado.docx.md",
                                     "nota.anonimizado.md"])
            for nome in nomes[1:]:
                self._sen_datos(z.read(nome).decode("utf-8"))

    def test_cli_markdown_co_nome_anonimizado(self):
        ruta = self.dir / f"{_NOME}.txt"
        ruta.write_text(f"Comparece don {_NOME}, con DNI {_DNI}.", encoding="utf-8")
        argv = ["anonimizador", "anonimizar", str(ruta), "--rexistro", str(self.dir / "rexistro_cli"), "--markdown"]
        with mock.patch.object(sys, "argv", argv), mock.patch("builtins.print"):
            cli.main()
        copias = list(self.dir.glob("*.md"))
        self.assertEqual(len(copias), 1, list(self.dir.iterdir()))
        self.assertEqual(copias[0].name, "PERSOA_000001.anonimizado.txt.md")
        self._sen_datos(copias[0].read_text(encoding="utf-8"))


class TestWeb(_Base):
    def setUp(self):
        super().setUp()
        web.SESIONS.clear()
        self.rexistro_dir = str(self.dir / "rexistro_web")
        self.client = web.app.test_client()
        parche = mock.patch.object(idioma, "ficheiro_preferencias", lambda: self.dir / "preferencias.json")
        parche.start()
        self.addCleanup(parche.stop)

    def _docx(self, nome: str) -> Path:
        documento = docx.Document()
        documento.add_heading("Escrito", 1)
        documento.add_paragraph(f"Comparece don {_NOME}, con DNI {_DNI}.")
        ruta = self.dir / nome
        documento.save(str(ruta))
        return ruta

    def _procesar(self, ruta: Path, modo: str, **extra):
        return self.client.post("/procesar", data={
            "ruta": str(ruta), "rexistro": self.rexistro_dir, "modo": modo, **extra,
        })

    def test_automatico_con_casilla_garda_copia_co_nome_anonimizado(self):
        self._procesar(self._docx(f"{_NOME}.docx"), "automatico", copia_md="1")
        copias = list(self.dir.glob("*.md"))
        self.assertEqual([c.name for c in copias], ["PERSOA_000001.anonimizado.docx.md"])
        md = copias[0].read_text(encoding="utf-8")
        self._sen_datos(md)
        self.assertIn("# Escrito", md)

    def test_automatico_sen_casilla_non_garda_copia(self):
        self._procesar(self._docx("escrito.docx"), "automatico")
        self.assertEqual(list(self.dir.glob("*.md")), [])

    def test_revision_confirmada_garda_copia(self):
        r = self._procesar(self._docx("escrito.docx"), "revisar", copia_md="1")
        sid = re.search(r"/revisar/([0-9a-f]+)", r.headers["Location"]).group(1)
        self.assertEqual(list(self.dir.glob("*.md")), [])  # nada antes de confirmar
        html = self.client.post(f"/revisar/{sid}/confirmar", data={"rexistro_dir": self.rexistro_dir}).get_data(as_text=True)
        copia = self.dir / "escrito.anonimizado.docx.md"
        self.assertTrue(copia.exists())
        self.assertIn(str(copia), html)
        self._sen_datos(copia.read_text(encoding="utf-8"))

    def test_revision_desde_automatico_substitue_a_copia(self):
        ruta = self.dir / "con_risco.txt"
        ruta.write_text(f"Comparece don {_NOME}. Referencia 34867809 do expediente.", encoding="utf-8")
        html = self._procesar(ruta, "automatico", copia_md="1").get_data(as_text=True)
        copia = self.dir / "con_risco.anonimizado.txt.md"
        self.assertIn("34867809", copia.read_text(encoding="utf-8"))
        sid = re.search(r'href="/revisar/([0-9a-f]+)', html).group(1)
        self.client.post(f"/revisar/{sid}/confirmar", data={
            "rexistro_dir": self.rexistro_dir, "decisions_v2": "1", "anonimizar": "PERSOA_000001",
            "fragmentos": "34867809 => [NÚMERO]"})
        md = copia.read_text(encoding="utf-8")
        self.assertIn("[NÚMERO]", md)
        self.assertNotIn("34867809", md)
        self.assertEqual(len(list(self.dir.glob("*.md"))), 1)

    def test_a_casilla_lembrase(self):
        self.assertNotIn('name="copia_md" value="1" checked', self.client.get("/").get_data(as_text=True))
        self._procesar(self._docx("a.docx"), "automatico", copia_md="1", lembrar_copia_md="1")
        self.assertIn('name="copia_md" value="1" checked', self.client.get("/").get_data(as_text=True))
        self._procesar(self._docx("b.docx"), "automatico", lembrar_copia_md="1")
        self.assertNotIn('name="copia_md" value="1" checked', self.client.get("/").get_data(as_text=True))

    def test_a_copia_e_o_idioma_comparten_o_ficheiro_de_preferencias(self):
        idioma.gardar("gl")
        self._procesar(self._docx("a.docx"), "automatico", copia_md="1", lembrar_copia_md="1")
        self.assertEqual(idioma.ler_preferencia("idioma"), "gl")
        self.assertIs(idioma.ler_preferencia("copia_md"), True)
        idioma.gardar("es")  # cambiar o idioma non borra a copia
        self.assertIs(idioma.ler_preferencia("copia_md"), True)

    def test_a_pantalla_de_inicio_ten_a_casilla_nos_dous_idiomas(self):
        for lingua, texto in (("gl", "Gardar tamén unha copia en Markdown"), ("es", "Guardar también una copia en Markdown")):
            with mock.patch.dict(os.environ, {idioma.VARIABLE: lingua}):
                self.assertIn(texto, self.client.get("/").get_data(as_text=True), lingua)

    def test_sen_lembrar_non_se_escribe_preferencia(self):
        self._procesar(self._docx("a.docx"), "automatico", copia_md="1")
        self.assertFalse((self.dir / "preferencias.json").exists())


if __name__ == "__main__":
    unittest.main()
