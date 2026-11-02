"""Conversor a .md para IA (ESTUDIO-CONVERSOR-MD, fase 2 sen a pantalla):
`conversor.py` (motor) e `cli_conversor.py` (liña de comandos).

Dous modos: sen anonimizar (só lectura + Markdown, sen spaCy) e
anonimizando (o mesmo pipeline do anonimizador). No modo anonimizado
compróbase sempre o principal: no .md non queda ningún dato orixinal, nin
no texto nin nos nomes de ficheiro ou cartafol.

Todos os nomes e DNI son sintéticos.
"""

import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest import mock
from contextlib import redirect_stdout
from pathlib import Path, PurePosixPath

import docx
import fitz  # PyMuPDF
from odf.opendocument import OpenDocumentText
from odf.text import H, P

os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")

_RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_RAIZ / "src"))

from anonimizador import arranque_windows, cli_conversor, conversor, idioma
from anonimizador.pipeline import anonimizar_e_gardar, ruta_saida_por_defecto
from anonimizador.registry import RexistroCorrespondencias

_NOME = "Xoán Pérez Vázquez"
_DNI = "30014811Z"
_NOME_CARTAFOL = "Antía Varela Doval"
_DATOS_ORIXINAIS = ("Xoán", "Pérez", "Vázquez", _DNI, "Antía", "Varela", "Doval")


def _docx(ruta: Path, titulo: str = "Demanda") -> Path:
    documento = docx.Document()
    documento.add_heading(titulo, 1)
    documento.add_paragraph(f"Comparece don {_NOME}, con DNI {_DNI}, ante o xulgado.")
    taboa = documento.add_table(rows=2, cols=2)
    taboa.cell(0, 0).text = "Concepto"
    taboa.cell(0, 1).text = "Importe"
    taboa.cell(1, 0).text = "Custas"
    taboa.cell(1, 1).text = "300 euros"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    documento.save(str(ruta))
    return ruta


def _odt(ruta: Path) -> Path:
    documento = OpenDocumentText()
    documento.text.addElement(H(outlinelevel=1, text="Feitos"))
    documento.text.addElement(P(text=f"O demandante, {_NOME}, con DNI {_DNI}, reside en Vigo."))
    ruta.parent.mkdir(parents=True, exist_ok=True)
    documento.save(str(ruta))
    return ruta


def _pdf(ruta: Path) -> Path:
    documento = fitz.open()
    documento.new_page().insert_text((50, 60), "Primeira páxina do escrito.", fontsize=11)
    documento.new_page().insert_text((50, 60), f"Comparece don {_NOME}, con DNI {_DNI}.", fontsize=11)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    documento.save(str(ruta))
    return ruta


class _Base(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _sen_datos(self, texto: str):
        for dato in _DATOS_ORIXINAIS:
            self.assertNotIn(dato, texto, f"{dato!r} á vista no .md")

    def _expediente(self) -> Path:
        """Cartafol con documentos, un subcartafol, un formato descoñecido e
        restos doutras pasadas (que non se deben volver converter)."""
        raiz = self.dir / "expediente"
        _docx(raiz / "demanda.docx")
        _odt(raiz / "probas" / "informe.odt")
        _pdf(raiz / "probas" / "escrito.pdf")
        (raiz / "notas.txt").write_text("# Non é un título\nNota simple.\n", encoding="utf-8")
        (raiz / "plano.dwg").write_bytes(b"\x00\x01")
        (raiz / "vello.pdf.md").write_text("conversión anterior", encoding="utf-8")
        return raiz


class TestSenAnonimizar(_Base):
    def test_docx(self):
        resultado = conversor.converter(str(_docx(self.dir / "demanda.docx")))
        self.assertEqual(resultado.saidas, [str(self.dir / "demanda.docx.md")])
        md = (self.dir / "demanda.docx.md").read_text(encoding="utf-8")
        self.assertTrue(md.startswith("---\norixe: demanda.docx\nanonimizado: non\n"), md[:200])
        self.assertIn("# Demanda", md)
        self.assertIn(f"Comparece don {_NOME}, con DNI {_DNI}", md)
        self.assertIn("| Concepto | Importe |\n| --- | --- |\n| Custas | 300 euros |", md)
        self.assertEqual(resultado.omitidos, [])

    def test_nome_do_programa_na_cabeceira(self):
        """Nome decidido polo usuario o 31/10/2026, un por idioma coma `app.nome`."""
        for lingua, nome in (("es", "Conversor de archivos para IA"), ("gl", "Conversor de ficheiros para IA")):
            with mock.patch.dict(os.environ, {idioma.VARIABLE: lingua}):
                conversor.converter(str(_docx(self.dir / f"demanda-{lingua}.docx")))
            md = (self.dir / f"demanda-{lingua}.docx.md").read_text(encoding="utf-8")
            self.assertIn(f", {nome} {conversor.VERSION}\n---", md)

    def test_odt(self):
        conversor.converter(str(_odt(self.dir / "informe.odt")))
        md = (self.dir / "informe.odt.md").read_text(encoding="utf-8")
        self.assertIn("anonimizado: non", md)
        self.assertIn("# Feitos", md)
        self.assertIn(f"O demandante, {_NOME}", md)

    def test_pdf_leva_paxinas(self):
        conversor.converter(str(_pdf(self.dir / "escrito.pdf")))
        md = (self.dir / "escrito.pdf.md").read_text(encoding="utf-8")
        self.assertIn("paxinas: 2\n", md.split("---")[1])
        self.assertIn("<!-- páxina 2 -->", md)
        self.assertIn(f"Comparece don {_NOME}", md)

    def test_md_de_entrada_tal_cal_e_sen_pisar_o_orixinal(self):
        ruta = self.dir / "notas.md"
        ruta.write_text("# Título\n\nTexto.\n", encoding="utf-8")
        conversor.converter(str(ruta))
        self.assertEqual(ruta.read_text(encoding="utf-8"), "# Título\n\nTexto.\n")
        md = (self.dir / "notas.md.md").read_text(encoding="utf-8")
        self.assertIn("\n# Título\n\nTexto.\n", md)

    def test_cartafol_de_saida(self):
        saida = self.dir / "saida"
        resultado = conversor.converter(str(_docx(self.dir / "demanda.docx")), saida=str(saida))
        self.assertEqual(resultado.saidas, [str(saida / "demanda.docx.md")])
        self.assertTrue((saida / "demanda.docx.md").exists())

    def test_cartafol(self):
        raiz = self._expediente()
        saida = self.dir / "saida"
        resultado = conversor.converter(str(raiz), saida=str(saida))
        self.assertEqual(
            sorted(Path(r).relative_to(saida).as_posix() for r in resultado.saidas),
            ["demanda.docx.md", "notas.txt.md", "probas/escrito.pdf.md", "probas/informe.odt.md"],
        )
        omitidos = dict(resultado.omitidos)
        self.assertEqual(omitidos["plano.dwg"], "formato")
        self.assertEqual(omitidos["vello.pdf.md"], "saida_anterior")
        self.assertIn("\\# Non é un título", (saida / "notas.txt.md").read_text(encoding="utf-8"))

    def test_cartafol_sen_saida_vai_canda_os_orixinais_e_repetir_non_dobra(self):
        raiz = self._expediente()
        conversor.converter(str(raiz))
        self.assertTrue((raiz / "probas" / "informe.odt.md").exists())
        resultado = conversor.converter(str(raiz))
        self.assertEqual(len(resultado.saidas), 4)
        self.assertFalse(list(raiz.rglob("*.md.md")))

    def test_zip(self):
        ruta_zip = self.dir / "expediente.zip"
        with zipfile.ZipFile(ruta_zip, "w") as z:
            z.write(_docx(self.dir / "orixe" / "demanda.docx"), "demanda.docx")
            z.write(_pdf(self.dir / "orixe" / "escrito.pdf"), "probas/escrito.pdf")
            z.writestr("plano.dwg", b"\x00")
            z.writestr("__MACOSX/._demanda.docx", b"\x00")
        resultado = conversor.converter(str(ruta_zip))
        cartafol = self.dir / "expediente-md"
        self.assertEqual(
            sorted(Path(r).relative_to(cartafol).as_posix() for r in resultado.saidas),
            ["demanda.docx.md", "probas/escrito.pdf.md"],
        )
        self.assertEqual(sorted(n for n, _ in resultado.omitidos), ["__MACOSX/._demanda.docx", "plano.dwg"])
        self.assertIn("<!-- páxina 2 -->", (cartafol / "probas" / "escrito.pdf.md").read_text(encoding="utf-8"))

    def test_un_so_md_dun_cartafol(self):
        raiz = self._expediente()
        resultado = conversor.converter(str(raiz), un_so_md=True)
        self.assertEqual(resultado.saidas, [str(self.dir / "expediente.md")])
        md = (self.dir / "expediente.md").read_text(encoding="utf-8")
        cabeceira = md.split("---")[1]
        self.assertIn("orixe: expediente\n", cabeceira)
        self.assertIn("ficheiros: 4\n", cabeceira)
        self.assertIn("anonimizado: non\n", cabeceira)
        self.assertIn("\n---\n\n# Índice\n\n1. ", md)
        # índice, unha sección por ficheiro e os títulos de cada documento un nivel máis abaixo
        indice = md.index("# Índice")
        for nome in ("demanda.docx", "notas.txt", "probas/escrito.pdf (2 páxinas)", "probas/informe.odt"):
            self.assertIn(nome, md[indice:md.index("\n# demanda.docx")])
        self.assertIn("\n# demanda.docx\n", md)
        self.assertIn("\n## Demanda\n", md)
        self.assertIn("\n# probas/informe.odt\n", md)
        self.assertIn("\n## Feitos\n", md)
        self.assertIn("<!-- páxina 2 -->", md)
        # o que non se converteu tamén consta
        self.assertIn("plano.dwg", md)
        self.assertEqual(list(raiz.rglob("*.md")), [raiz / "vello.pdf.md"])

    def test_un_so_md_dun_zip(self):
        ruta_zip = self.dir / "expediente.zip"
        with zipfile.ZipFile(ruta_zip, "w") as z:
            z.write(_docx(self.dir / "orixe" / "demanda.docx"), "demanda.docx")
            z.writestr("nota.txt", "Unha nota.")
        resultado = conversor.converter(str(ruta_zip), un_so_md=True)
        self.assertEqual(resultado.saidas, [str(self.dir / "expediente.zip.md")])
        md = Path(resultado.saidas[0]).read_text(encoding="utf-8")
        self.assertIn("orixe: expediente.zip\n", md)
        self.assertIn("\n# nota.txt\n\nUnha nota.\n", md)

    def test_non_carga_spacy_nin_o_pipeline(self):
        raiz = self._expediente()
        codigo = (
            "import importlib.abc, sys\n"
            "class _SenSpacy(importlib.abc.MetaPathFinder):\n"
            "    def find_spec(self, nome, ruta=None, obxectivo=None):\n"
            "        if nome == 'spacy' or nome.startswith('spacy.'):\n"
            "            raise ModuleNotFoundError('spacy non instalado (proba)', name=nome)\n"
            "sys.meta_path.insert(0, _SenSpacy())\n"
            "from anonimizador import cli_conversor\n"
            "cli_conversor.main([sys.argv[1], '--un-solo-md'])\n"
            "cli_conversor.main([sys.argv[1]])\n"
            "cargados = sorted(m for m in sys.modules if m.split('.')[0] == 'spacy'\n"
            "                  or m in ('anonimizador.ner', 'anonimizador.pipeline'))\n"
            "print('CARGADOS:' + ','.join(cargados))\n"
        )
        entorno = dict(os.environ, PYTHONPATH=str(_RAIZ / "src"), ANONIMIZADOR_IDIOMA="gl")
        resultado = subprocess.run(
            [sys.executable, "-c", codigo, str(raiz)],
            capture_output=True, text=True, encoding="utf-8", env=entorno, cwd=str(self.dir),
        )
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(resultado.stdout.strip().split("\n")[-1], "CARGADOS:", resultado.stdout[-500:])
        self.assertTrue((self.dir / "expediente.md").exists())
        self.assertTrue((raiz / "probas" / "escrito.pdf.md").exists())


class TestPuntosDeEnganche(_Base):
    def setUp(self):
        super().setUp()
        self._lectores = dict(conversor.LECTORES_EXTRA)

    def tearDown(self):
        conversor.LECTORES_EXTRA.clear()
        conversor.LECTORES_EXTRA.update(self._lectores)
        conversor.POSPROCESADOS.clear()
        super().tearDown()

    def test_lector_dun_formato_novo_so_sen_anonimizar(self):
        conversor.LECTORES_EXTRA[".csv"] = lambda ruta, **_: "| a | b |\n| --- | --- |\n| 1 | 2 |\n"
        raiz = self.dir / "cartafol"
        raiz.mkdir()
        (raiz / "taboa.csv").write_text("a;b\n1;2\n", encoding="utf-8")
        resultado = conversor.converter(str(raiz))
        self.assertEqual(resultado.omitidos, [])
        self.assertIn("| 1 | 2 |", (raiz / "taboa.csv.md").read_text(encoding="utf-8"))
        # anonimizando: sen proba de fugas, rexéitase (non se escribe nada)
        rexistro = RexistroCorrespondencias(str(self.dir / "rexistro"))
        resultado = conversor.converter(str(raiz), anonimizar=True, rexistro=rexistro, saida=str(self.dir / "s"))
        self.assertIn(("taboa.csv", "sen_proba_de_fugas"), resultado.omitidos)
        self.assertEqual(resultado.saidas, [])

    def test_posprocesado(self):
        conversor.POSPROCESADOS.append(lambda md: md.replace("ante o xulgado", "ANTE O XULGADO"))
        conversor.converter(str(_docx(self.dir / "demanda.docx")))
        md = (self.dir / "demanda.docx.md").read_text(encoding="utf-8")
        self.assertIn("ANTE O XULGADO", md)
        self.assertIn("anonimizado: non", md)  # a cabeceira non pasa polo posprocesado


class TestFormatosNovos(_Base):
    """Os lectores de `formatos/` (fase 4) enganchados ao motor: só sen
    anonimizar, e cos seus avisos (follas agochadas...) no resultado."""

    def _cartafol(self) -> Path:
        import openpyxl
        from pptx import Presentation

        raiz = self.dir / "formatos"
        raiz.mkdir()
        libro = openpyxl.Workbook()
        libro.active.title = "Contas"
        libro.active.append(["Concepto", "Importe"])
        libro.active.append(["Taxas", 120])
        agochada = libro.create_sheet("Interna")
        agochada.append(["dato", "agochado"])
        agochada.sheet_state = "hidden"
        libro.save(str(raiz / "contas.xlsx"))
        presentacion = Presentation()
        diapositiva = presentacion.slides.add_slide(presentacion.slide_layouts[1])
        diapositiva.shapes.title.text = "Resumo do caso"
        diapositiva.placeholders[1].text = "Primeiro punto"
        presentacion.save(str(raiz / "resumo.pptx"))
        (raiz / "norma.html").write_text(
            "<html><head><title>x</title><script>var a;</script></head>"
            "<body><h1>Lei de proba</h1><p>Artigo primeiro.</p></body></html>", encoding="utf-8")
        (raiz / "aviso.eml").write_bytes(
            b"Subject: Prazo de contestacion\nFrom: Ana Pena <ana@example.org>\n"
            b"Received: from IP-ESCONDIDA\n\nVence o luns.\n")
        return raiz

    def test_sen_anonimizar(self):
        raiz = self._cartafol()
        resultado = conversor.converter(str(raiz))
        self.assertEqual(resultado.omitidos, [])
        contas = (raiz / "contas.xlsx.md").read_text(encoding="utf-8")
        self.assertIn("| Taxas | 120 |", contas)
        self.assertNotIn("agochado", contas)
        self.assertIn("Resumo do caso", (raiz / "resumo.pptx.md").read_text(encoding="utf-8"))
        norma = (raiz / "norma.html.md").read_text(encoding="utf-8")
        self.assertIn("# Lei de proba", norma)
        self.assertNotIn("var a", norma)
        aviso = (raiz / "aviso.eml.md").read_text(encoding="utf-8")
        self.assertIn("# Prazo de contestacion", aviso)
        self.assertIn("Vence o luns.", aviso)
        self.assertNotIn("IP-ESCONDIDA", aviso)
        self.assertEqual(list(resultado.avisos), ["contas.xlsx"])
        self.assertIn("Interna", resultado.avisos["contas.xlsx"][0])

    def test_anonimizando_rexeitanse(self):
        raiz = self._cartafol()
        rexistro = RexistroCorrespondencias(str(self.dir / "rexistro"))
        resultado = conversor.converter(str(raiz), anonimizar=True, rexistro=rexistro, saida=str(self.dir / "s"))
        self.assertEqual(sorted(resultado.omitidos), [
            ("aviso.eml", "sen_proba_de_fugas"), ("contas.xlsx", "sen_proba_de_fugas"),
            ("norma.html", "sen_proba_de_fugas"),
            ("resumo.pptx", "sen_proba_de_fugas")])
        self.assertEqual(resultado.saidas, [])

    def test_liña_de_comandos_amosa_os_avisos(self):
        raiz = self._cartafol()
        saida = io.StringIO()
        with redirect_stdout(saida):
            cli_conversor.main([str(raiz / "contas.xlsx")])
        self.assertIn("Interna", saida.getvalue())

class TestCsvAparte(_Base):
    """Follas de máis de 500 filas: `.csv` á parte canda o `.md` (opción
    `csv_aparte`, por defecto si)."""

    def _folla(self, ruta: Path, filas: int = 600) -> Path:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text("id;importe\n" + "".join(f"{i};{i * 2}\n" for i in range(filas)), encoding="utf-8")
        return ruta

    def test_folla_grande_vai_a_csv_canda_o_md(self):
        raiz = self.dir / "expediente"
        self._folla(raiz / "contas" / "libro.csv")
        resultado = conversor.converter(str(raiz))
        md = raiz / "contas" / "libro.csv.md"
        csv_aparte = raiz / "contas" / "libro.datos.csv"
        self.assertTrue(csv_aparte.is_file())
        self.assertEqual(len(csv_aparte.read_text(encoding="utf-8").splitlines()), 601)
        texto = md.read_text(encoding="utf-8")
        self.assertIn("libro.datos.csv", texto)
        self.assertIn("importe", texto)
        self.assertNotIn("| 599 |", texto)
        self.assertEqual(resultado.csv, [str(csv_aparte)])
        self.assertIn(str(csv_aparte), " ".join(resultado.avisos["contas/libro.csv"]))
        self.assertEqual(resultado.saidas, [str(md)])

    def test_con_saida_e_un_so_md_o_csv_queda_canda_o_md(self):
        raiz = self.dir / "expediente"
        self._folla(raiz / "libro.csv")
        saida = self.dir / "saida"
        resultado = conversor.converter(str(raiz), saida=str(saida), un_so_md=True)
        self.assertTrue((saida / "expediente.md").is_file())
        self.assertTrue((saida / "libro.datos.csv").is_file())
        self.assertFalse((raiz / "libro.datos.csv").exists())
        self.assertEqual(resultado.csv, [str(saida / "libro.datos.csv")])

    def test_homonimos_en_un_so_md_non_se_pisan(self):
        raiz = self.dir / "expediente"
        self._folla(raiz / "a" / "libro.csv", 600)
        self._folla(raiz / "b" / "libro.csv", 700)
        saida = self.dir / "saida"
        resultado = conversor.converter(str(raiz), saida=str(saida), un_so_md=True)
        self.assertEqual(sorted(Path(r).name for r in resultado.csv), ["libro.datos-2.csv", "libro.datos.csv"])
        md = (saida / "expediente.md").read_text(encoding="utf-8")
        self.assertIn("libro.datos-2.csv", md)
        self.assertEqual(len((saida / "libro.datos-2.csv").read_text(encoding="utf-8").splitlines()), 701)

    def test_sen_a_opcion_a_taboa_sae_enteira_con_aviso(self):
        raiz = self.dir / "expediente"
        self._folla(raiz / "libro.csv")
        resultado = conversor.converter(str(raiz), csv_aparte=False)
        self.assertEqual(list(raiz.glob("*.datos.csv")), [])
        self.assertEqual(resultado.csv, [])
        self.assertIn("| 599 |", (raiz / "libro.csv.md").read_text(encoding="utf-8"))
        self.assertTrue(resultado.avisos["libro.csv"])

    def test_folla_pequena_non_xera_csv(self):
        raiz = self.dir / "expediente"
        self._folla(raiz / "libro.csv", 20)
        resultado = conversor.converter(str(raiz))
        self.assertEqual(list(raiz.glob("*.datos.csv")), [])
        self.assertEqual(resultado.csv, [])

    def test_cancelar_non_deixa_csv(self):
        raiz = self.dir / "expediente"
        self._folla(raiz / "a.csv")
        self._folla(raiz / "b.csv")
        chamadas = iter([False, True])
        with self.assertRaises(conversor.Cancelado):
            conversor.converter(str(raiz), cancelar=lambda: next(chamadas, True))
        self.assertEqual(sorted(p.name for p in raiz.glob("*.csv")), ["a.csv", "b.csv"])

    def test_anonimizando_non_escribe_csv(self):
        raiz = self.dir / "expediente"
        self._folla(raiz / "libro.csv")
        saida = self.dir / "saida"
        rexistro = RexistroCorrespondencias(str(self.dir / "rexistro"))
        resultado = conversor.converter(str(raiz), anonimizar=True, rexistro=rexistro, saida=str(saida),
                                        csv_aparte=True)
        self.assertEqual(resultado.omitidos, [("libro.csv", "sen_proba_de_fugas")])
        self.assertEqual(resultado.csv, [])
        self.assertEqual(sorted(p.name for p in raiz.rglob("*.csv")), ["libro.csv"])
        self.assertFalse(saida.exists() and list(saida.rglob("*")))
        # e se un lector chegase a executarse anonimizando, non recibe `dir_csv`
        recibido = {}

        def lector(ruta, **opcions):
            recibido.update(opcions)
            return "| a |\n"

        orixinal = dict(conversor.LECTORES_EXTRA)
        self.addCleanup(lambda: (conversor.LECTORES_EXTRA.clear(), conversor.LECTORES_EXTRA.update(orixinal)))
        conversor.LECTORES_EXTRA[".csv"] = lector
        doc = conversor._Documento(PurePosixPath("libro.csv"), raiz / "libro.csv")
        conversor._converter_documento(doc, False, None, None, self.dir / "x")
        self.assertEqual(recibido, {"dir_csv": str(self.dir / "x")})
        recibido.clear()
        with mock.patch.object(conversor, "lectura") as lectura:
            lectura.EXTENSIONS_SOPORTADAS = ()
            conversor._converter_documento(doc, True, rexistro, None, self.dir / "x")
        self.assertEqual(recibido, {})

    def test_liña_de_comandos(self):
        raiz = self.dir / "expediente"
        self._folla(raiz / "libro.csv")
        saida = io.StringIO()
        with redirect_stdout(saida):
            cli_conversor.main([str(raiz)])
        self.assertTrue((raiz / "libro.datos.csv").is_file())
        self.assertIn("libro.datos.csv", saida.getvalue())
        (raiz / "libro.datos.csv").unlink()
        with redirect_stdout(io.StringIO()):
            cli_conversor.main([str(raiz), "--sen-csv-aparte"])
        self.assertFalse((raiz / "libro.datos.csv").exists())


def _pdf_con_cabeceira(ruta: Path, paxinas: int = 4) -> Path:
    """Cada páxina co mesmo membrete arriba e un parágrafo distinto."""
    documento = fitz.open()
    for n in range(1, paxinas + 1):
        paxina = documento.new_page()
        paxina.insert_text((50, 40), "DIARIO OFICIAL DE GALICIA", fontsize=9)
        y = 90
        for i in range(12):
            paxina.insert_text((50, y), f"Texto da páxina {n}, liña {i}, sen máis contido relevante.", fontsize=10)
            y += 14
    ruta.parent.mkdir(parents=True, exist_ok=True)
    documento.save(str(ruta))
    return ruta


class TestAforro(_Base):
    """O aforro para IA (`aforro_ia`, fase 3) enganchado ao motor."""

    def test_por_defecto_cabeceira_repetida_unha_vez(self):
        resultado = conversor.converter(str(_pdf_con_cabeceira(self.dir / "dog.pdf")))
        md = (self.dir / "dog.pdf.md").read_text(encoding="utf-8")
        self.assertEqual(md.count("DIARIO OFICIAL DE GALICIA"), 1)
        self.assertLess(resultado.tokens_despois, resultado.tokens_antes)

    def test_sen_aforro(self):
        resultado = conversor.converter(str(_pdf_con_cabeceira(self.dir / "dog.pdf")), aforro=False)
        md = (self.dir / "dog.pdf.md").read_text(encoding="utf-8")
        self.assertEqual(md.count("DIARIO OFICIAL DE GALICIA"), 4)
        self.assertEqual(resultado.tokens_despois, resultado.tokens_antes)

    def test_trocear_con_cabeceira_en_cada_parte(self):
        raiz = self.dir / "expediente"
        _pdf_con_cabeceira(raiz / "memoria.pdf", paxinas=10)
        resultado = conversor.converter(str(raiz), caracteres_por_parte=1500)
        partes = sorted(raiz.glob("memoria.pdf.parte-*.md"))
        self.assertGreater(len(partes), 1)
        indice = raiz / "memoria.pdf.indice.md"
        self.assertTrue(indice.exists())
        self.assertFalse((raiz / "memoria.pdf.md").exists())
        self.assertEqual(sorted(resultado.saidas), sorted(map(str, [*partes, indice])))
        for ruta in [*partes, indice]:
            self.assertIn("anonimizado: non\n", ruta.read_text(encoding="utf-8"))
        # outra pasada polo cartafol non volve converter as partes nin o índice
        resultado = conversor.converter(str(raiz), caracteres_por_parte=1500)
        self.assertEqual({motivo for _, motivo in resultado.omitidos}, {"saida_anterior"})
        self.assertEqual(len(resultado.omitidos), len(partes) + 1)
        self.assertFalse(list(raiz.glob("*.md.md")))

    def test_un_so_md_troceado(self):
        raiz = self.dir / "expediente"
        _pdf_con_cabeceira(raiz / "a.pdf", paxinas=6)
        _pdf_con_cabeceira(raiz / "b.pdf", paxinas=6)
        conversor.converter(str(raiz), un_so_md=True, caracteres_por_parte=2000)
        self.assertTrue((self.dir / "expediente.indice.md").exists())
        self.assertGreater(len(list(self.dir.glob("expediente.parte-*.md"))), 1)

    def test_liña_de_comandos(self):
        ruta = _pdf_con_cabeceira(self.dir / "dog.pdf", paxinas=10)
        saida = io.StringIO()
        with redirect_stdout(saida):
            cli_conversor.main([str(ruta), "--trocear", "400"])
        self.assertIn("tokens", saida.getvalue())
        self.assertTrue((self.dir / "dog.pdf.indice.md").exists())
        with redirect_stdout(io.StringIO()):
            cli_conversor.main([str(ruta), "--sen-aforro"])
        self.assertEqual((self.dir / "dog.pdf.md").read_text(encoding="utf-8").count("DIARIO OFICIAL DE GALICIA"), 10)


class TestAnonimizando(_Base):
    def setUp(self):
        super().setUp()
        self.rexistro = RexistroCorrespondencias(str(self.dir / "rexistro"))

    def test_docx_sen_datos_e_nome_anonimizado(self):
        ruta = _docx(self.dir / f"Demanda {_NOME}.docx")
        resultado = conversor.converter(str(ruta), anonimizar=True, rexistro=self.rexistro)
        self.assertEqual(len(resultado.saidas), 1)
        saida = Path(resultado.saidas[0])
        self.assertTrue(saida.name.endswith(".anonimizado.docx.md"), saida.name)
        self._sen_datos(saida.name)
        md = saida.read_text(encoding="utf-8")
        self._sen_datos(md)
        self.assertIn("anonimizado: si\n", md)
        self.assertRegex(md, r"^---\norixe: Demanda PERSOA_\d{6}\.docx\n")
        self.assertRegex(md, r"Comparece don PERSOA_\d{6}")
        self.assertIn("| Custas | 300 euros |", md)
        self.assertEqual(list(resultado.informes), [saida.name[:-len(".anonimizado.docx.md")] + ".docx"])

    def test_odt_e_pdf_sen_datos(self):
        for ruta in (_odt(self.dir / "informe.odt"), _pdf(self.dir / "escrito.pdf")):
            resultado = conversor.converter(str(ruta), anonimizar=True, rexistro=self.rexistro)
            md = Path(resultado.saidas[0]).read_text(encoding="utf-8")
            self._sen_datos(md)
            self.assertRegex(md, r"PERSOA_\d{6}")
        self.assertTrue((self.dir / "informe.anonimizado.odt.md").exists())
        self.assertIn("<!-- páxina 2 -->", (self.dir / "escrito.anonimizado.pdf.md").read_text(encoding="utf-8"))

    def test_mesmo_codigo_ca_no_anonimizador(self):
        """Propostas 12.2: co mesmo rexistro, unha persoa recibe o mesmo
        código no anonimizador e no conversor."""
        ruta = _docx(self.dir / "demanda.docx")
        texto_anonimizador, _ = anonimizar_e_gardar(str(ruta), ruta_saida_por_defecto(str(ruta)), self.rexistro)
        codigo = texto_anonimizador.split("Comparece don ")[1].split(",")[0]
        conversor.converter(str(_odt(self.dir / "informe.odt")), anonimizar=True, rexistro=self.rexistro)
        md = (self.dir / "informe.anonimizado.odt.md").read_text(encoding="utf-8")
        self.assertIn(f"O demandante, {codigo}, con DNI", md)

    def test_cartafol_con_nome_de_persoa_e_un_so_md(self):
        raiz = self.dir / _NOME_CARTAFOL
        _docx(raiz / f"Poder {_NOME}.docx")
        _pdf(raiz / _NOME_CARTAFOL / "escrito.pdf")
        (raiz / f"foto {_NOME}.dwg").write_bytes(b"\x00")
        saida = self.dir / "saida"
        resultado = conversor.converter(
            str(raiz), anonimizar=True, un_so_md=True, rexistro=self.rexistro, saida=str(saida)
        )
        self.assertEqual(len(resultado.saidas), 1)
        md_ruta = Path(resultado.saidas[0])
        self.assertTrue(md_ruta.name.endswith(".anonimizado.md"), md_ruta.name)
        self._sen_datos(md_ruta.name)
        md = md_ruta.read_text(encoding="utf-8")
        self._sen_datos(md)
        self.assertIn("anonimizado: si\n", md)
        self.assertIn("ficheiros: 2\n", md)
        self.assertIn(".dwg", md)  # o omitido consta, co nome anonimizado
        self.assertEqual([p.name for p in saida.iterdir()], [md_ruta.name])

    def test_zip_un_md_por_ficheiro_sen_datos(self):
        ruta_zip = self.dir / f"expediente {_NOME}.zip"
        with zipfile.ZipFile(ruta_zip, "w") as z:
            z.write(_docx(self.dir / "orixe" / "demanda.docx"), f"{_NOME_CARTAFOL}/demanda.docx")
            z.write(_odt(self.dir / "orixe" / "informe.odt"), "informe.odt")
        saida = self.dir / "saida"
        resultado = conversor.converter(str(ruta_zip), anonimizar=True, rexistro=self.rexistro, saida=str(saida))
        self.assertEqual(len(resultado.saidas), 2)
        for ficheiro in saida.rglob("*"):
            self._sen_datos(str(ficheiro.relative_to(saida)))
            if ficheiro.is_file():
                self.assertTrue(ficheiro.name.endswith((".anonimizado.docx.md", ".anonimizado.odt.md")))
                self._sen_datos(ficheiro.read_text(encoding="utf-8"))

    def test_sen_rexistro_e_un_erro(self):
        with self.assertRaises(ValueError):
            conversor.converter(str(_docx(self.dir / "demanda.docx")), anonimizar=True)


class TestProgresoCancelarRevisar(_Base):
    """Os enganches da pantalla (fase 2b): progreso, cancelar e revisar."""

    def setUp(self):
        super().setUp()
        self.rexistro = RexistroCorrespondencias(str(self.dir / "rexistro"))
        self.raiz = self.dir / "expediente"
        _docx(self.raiz / "a.docx")
        _odt(self.raiz / "b.odt")

    def test_progreso_por_documento_e_final(self):
        chamadas = []
        conversor.converter(str(self.raiz), progreso=lambda *a: chamadas.append(a))
        self.assertEqual(chamadas, [(0, 2, "a.docx"), (1, 2, "b.odt"), (2, 2, "")])

    def test_cancelar_non_escribe_nada(self):
        chamadas = []
        with self.assertRaises(conversor.Cancelado):
            conversor.converter(str(self.raiz), progreso=lambda *a: chamadas.append(a),
                                cancelar=lambda: len(chamadas) > 0)
        self.assertEqual(sorted(p.name for p in self.raiz.iterdir()), ["a.docx", "b.odt"])

    def test_automatico_revisado_non_e_sen_anonimizar_sen_liña(self):
        resultado = conversor.converter(str(self.raiz / "a.docx"), anonimizar=True, rexistro=self.rexistro)
        self.assertIn("anonimizado: si\nrevisado: non\n", Path(resultado.saidas[0]).read_text(encoding="utf-8"))
        self.assertEqual(resultado.revisados, [])
        md = Path(conversor.converter(str(self.raiz / "a.docx")).saidas[0]).read_text(encoding="utf-8")
        self.assertNotIn("revisado", md.split("---")[1])

    def test_revisar_cambia_o_texto_e_marca_revisado(self):
        vistos = []

        def revisar(nome, texto, contexto, texto_anon, informe, substitucions):
            vistos.append((nome, len(informe["persoas"])))
            inicio = texto.index("xulgado")
            return (texto_anon.replace("xulgado", "[ÓRGANO]"),
                    [*substitucions, (inicio, inicio + len("xulgado"), "[ÓRGANO]")])

        resultado = conversor.converter(str(self.raiz / "a.docx"), anonimizar=True, rexistro=self.rexistro,
                                        revisar=revisar)
        md = Path(resultado.saidas[0]).read_text(encoding="utf-8")
        self.assertEqual(vistos, [("a.docx", 1)])
        self.assertIn("revisado: si\n", md)
        self.assertIn("ante o [ÓRGANO].", md)
        self._sen_datos(md)
        self.assertEqual(resultado.revisados, list(resultado.informes))

    def test_revisar_none_queda_sen_revisar_e_un_so_md_mixto(self):
        resultado = conversor.converter(
            str(self.raiz), anonimizar=True, un_so_md=True, rexistro=self.rexistro,
            revisar=lambda nome, *_: (_[2], _[4]) if nome == "a.docx" else None,
        )
        md = Path(resultado.saidas[0]).read_text(encoding="utf-8")
        self.assertIn("revisado: non\n", md)  # un só .md: "si" só se se revisaron todos
        self.assertEqual(len(resultado.revisados), 1)

    def test_revisar_pode_cancelar(self):
        def revisar(*_):
            raise conversor.Cancelado

        with self.assertRaises(conversor.Cancelado):
            conversor.converter(str(self.raiz), anonimizar=True, rexistro=self.rexistro, revisar=revisar)
        self.assertEqual(sorted(p.name for p in self.raiz.iterdir()), ["a.docx", "b.odt"])


class TestRexistroCompartido(unittest.TestCase):
    def test_mesmo_cartafol_ca_o_anonimizador_da_store(self):
        self.assertEqual(
            conversor.rexistro_por_defecto(),
            arranque_windows.cartafol_documentos() / arranque_windows.NOME_CARTAFOL / "datos_rexistro",
        )


class TestLiñaDeComandos(_Base):
    def _executar(self, *argumentos) -> tuple:
        saida = io.StringIO()
        with redirect_stdout(saida):
            codigo = cli_conversor.main([str(a) for a in argumentos])
        return codigo, saida.getvalue()

    def test_sen_anonimizar_avisa_dos_datos(self):
        ruta = _docx(self.dir / "demanda.docx")
        codigo, saida = self._executar(ruta)
        self.assertEqual(codigo, 0)
        self.assertIn("demanda.docx.md", saida)
        self.assertIn("conserva os datos persoais", saida)
        self.assertTrue((self.dir / "demanda.docx.md").exists())

    def test_anonimizando_avisa_de_que_e_automatico(self):
        raiz = self._expediente()
        codigo, saida = self._executar(
            raiz, "--anonimizar", "--un-solo-md", "--saida", self.dir / "saida", "--rexistro", self.dir / "rexistro"
        )
        self.assertEqual(codigo, 0)
        self.assertIn("automático", saida)
        self.assertIn("sen revisión humana", saida)
        self.assertIn("plano.dwg", saida)  # omitidos
        self.assertTrue((self.dir / "saida" / "expediente.anonimizado.md").exists())
        self._sen_datos((self.dir / "saida" / "expediente.anonimizado.md").read_text(encoding="utf-8"))

    def test_entrada_inexistente(self):
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as erro:
            cli_conversor.main([str(self.dir / "non_existe.pdf")])
        self.assertNotEqual(erro.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
