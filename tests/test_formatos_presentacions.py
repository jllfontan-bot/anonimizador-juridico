"""Presentacións (.pptx, .odp) a Markdown, SEN anonimizar
(`formatos/presentacions.py`, fase 4 do conversor a .md)."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

from odf.draw import Frame, Image as ImaxeOdp, Page, TextBox
from odf.namespaces import DRAWNS, PRESENTATIONNS
from odf.opendocument import OpenDocumentPresentation
from odf.presentation import Notes
from odf.style import DrawingPageProperties, Style
from odf.table import Table, TableCell, TableRow
from odf.text import List, ListItem, P
from pptx import Presentation
from pptx.util import Inches
from PIL import Image

os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador.formatos import presentacions


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def ruta(self, nome: str) -> str:
        return str(self.dir / nome)


class TestPptx(_Base):
    def _diapositiva(self, prs, titulo, puntos=()):
        d = prs.slides.add_slide(prs.slide_layouts[1])  # título e contido
        d.shapes.title.text = titulo
        cadro = d.placeholders[1].text_frame
        for i, punto in enumerate(puntos):
            parrafo = cadro.paragraphs[0] if i == 0 else cadro.add_paragraph()
            if isinstance(punto, tuple):
                parrafo.text, parrafo.level = punto
            else:
                parrafo.text = punto
        return d

    def test_unha_seccion_por_diapositiva_con_titulo_e_lista(self):
        prs = Presentation()
        self._diapositiva(prs, "Obxecto do contrato", ["Primeiro punto", ("Subpunto", 1), "Segundo punto"])
        self._diapositiva(prs, "Prazos", ["Tres meses"])
        ruta = self.ruta("p.pptx")
        prs.save(ruta)
        md = presentacions.a_markdown(ruta)
        self.assertIn("## Diapositiva 1: Obxecto do contrato", md)
        self.assertIn("- Primeiro punto", md)
        self.assertIn("  - Subpunto", md)
        self.assertIn("- Segundo punto", md)
        self.assertIn("## Diapositiva 2: Prazos", md)
        self.assertLess(md.index("Diapositiva 1"), md.index("Diapositiva 2"))

    def test_sen_titulo_so_leva_o_numero(self):
        prs = Presentation()
        d = prs.slides.add_slide(prs.slide_layouts[6])  # en branco
        caixa = d.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
        caixa.text_frame.text = "Texto solto"
        ruta = self.ruta("p.pptx")
        prs.save(ruta)
        md = presentacions.a_markdown(ruta)
        self.assertIn("## Diapositiva 1\n", md)
        self.assertIn("Texto solto", md)
        self.assertNotIn("- Texto solto", md)  # unha caixa de texto non é unha lista

    def test_taboas(self):
        prs = Presentation()
        d = self._diapositiva(prs, "Datos")
        taboa = d.shapes.add_table(2, 2, Inches(1), Inches(3), Inches(4), Inches(1)).table
        for (f, c), valor in {(0, 0): "Concepto", (0, 1): "Importe", (1, 0): "Material", (1, 1): "12 | 3"}.items():
            taboa.cell(f, c).text = valor
        ruta = self.ruta("p.pptx")
        prs.save(ruta)
        md = presentacions.a_markdown(ruta)
        self.assertIn("| Concepto | Importe |", md)
        self.assertIn("| Material | 12 \\| 3 |", md)

    def test_notas_do_orador(self):
        prs = Presentation()
        d = self._diapositiva(prs, "Tema", ["Algo"])
        d.notes_slide.notes_text_frame.text = "Lembrar o caso de Ana Pena"
        ruta = self.ruta("p.pptx")
        prs.save(ruta)
        md = presentacions.a_markdown(ruta)
        self.assertIn("Notas do orador", md)
        self.assertIn("Lembrar o caso de Ana Pena", md)
        self.assertLess(md.index("Algo"), md.index("Lembrar"))

    def test_diapositiva_oculta_omitese_e_avisase(self):
        prs = Presentation()
        self._diapositiva(prs, "Visible", ["a"])
        oculta = self._diapositiva(prs, "Descartada", ["dato escondido"])
        oculta._element.set("show", "0")
        ruta = self.ruta("p.pptx")
        prs.save(ruta)
        conv = presentacions.convertir(ruta)
        self.assertNotIn("dato escondido", conv.markdown)
        self.assertNotIn("Descartada", conv.markdown)
        self.assertTrue(any("2" in a for a in conv.avisos))

    def test_numeracion_non_salta_pola_oculta(self):
        prs = Presentation()
        oculta = self._diapositiva(prs, "Oculta", ["x"])
        oculta._element.set("show", "0")
        self._diapositiva(prs, "Segunda", ["y"])
        ruta = self.ruta("p.pptx")
        prs.save(ruta)
        self.assertIn("## Diapositiva 2: Segunda", presentacions.a_markdown(ruta))

    def test_metadatos_de_autor_non_saen(self):
        prs = Presentation()
        self._diapositiva(prs, "Tema", ["a"])
        prs.core_properties.author = "Autor Privado"
        prs.core_properties.last_modified_by = "Outra Persoa"
        prs.core_properties.comments = "Comentario interno"
        ruta = self.ruta("p.pptx")
        prs.save(ruta)
        md = presentacions.a_markdown(ruta)
        for segredo in ("Autor Privado", "Outra Persoa", "Comentario interno"):
            self.assertNotIn(segredo, md)

    def test_imaxe_marcase_con_texto_alternativo(self):
        png = self.dir / "i.png"
        Image.new("RGB", (4, 4), "red").save(png)
        prs = Presentation()
        d = self._diapositiva(prs, "Foto", ["a"])
        imaxe = d.shapes.add_picture(str(png), Inches(1), Inches(4))
        imaxe._element.nvPicPr.cNvPr.set("descr", "Plano da parcela")
        d.shapes.add_picture(str(png), Inches(3), Inches(4))
        ruta = self.ruta("p.pptx")
        prs.save(ruta)
        md = presentacions.a_markdown(ruta)
        self.assertIn("[imaxe: Plano da parcela]", md)
        self.assertIn("[imaxe]", md)

    def test_formas_agrupadas(self):
        prs = Presentation()
        d = prs.slides.add_slide(prs.slide_layouts[6])
        grupo = d.shapes.add_group_shape()
        caixa = grupo.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(1))
        caixa.text_frame.text = "Dentro do grupo"
        ruta = self.ruta("p.pptx")
        prs.save(ruta)
        self.assertIn("Dentro do grupo", presentacions.a_markdown(ruta))

    def test_salto_de_liña_manual_nun_paragrafo(self):
        prs = Presentation()
        d = prs.slides.add_slide(prs.slide_layouts[6])
        caixa = d.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(1))
        caixa.text_frame.text = "Rúa Maior 5\vVigo"
        ruta = self.ruta("p.pptx")
        prs.save(ruta)
        md = presentacions.a_markdown(ruta)
        self.assertIn("Rúa Maior 5  \nVigo", md)
        self.assertNotIn("\x0b", md)

    def test_texto_que_parece_markdown_escapase(self):
        prs = Presentation()
        d = prs.slides.add_slide(prs.slide_layouts[6])
        caixa = d.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(1))
        caixa.text_frame.text = "# non son un título"
        ruta = self.ruta("p.pptx")
        prs.save(ruta)
        self.assertIn("\\# non son un título", presentacions.a_markdown(ruta))

    def test_pe_de_diapositiva_e_numero_non_saen(self):
        prs = Presentation()
        d = self._diapositiva(prs, "Tema", ["a"])
        # Engade á man placeholders de pé e de número, como fai PowerPoint
        from lxml import etree
        ns = ('xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
              'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"')
        for i, tipo in enumerate(("ftr", "sldNum")):
            xml = (f'<p:sp {ns}><p:nvSpPr><p:cNvPr id="{90 + i}" name="x{i}"/><p:cNvSpPr/>'
                   f'<p:nvPr><p:ph type="{tipo}" sz="quarter" idx="{10 + i}"/></p:nvPr></p:nvSpPr>'
                   f'<p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>PE REPETIDO {tipo}'
                   f'</a:t></a:r></a:p></p:txBody></p:sp>')
            d.shapes._spTree.append(etree.fromstring(xml))
        ruta = self.ruta("p.pptx")
        prs.save(ruta)
        md = presentacions.a_markdown(ruta)
        self.assertNotIn("PE REPETIDO", md)
        self.assertIn("- a", md)


def _frame(clase, *fillos):
    f = Frame(width="10cm", height="2cm", x="0cm", y="0cm")
    f.setAttrNS(PRESENTATIONNS, "class", clase)
    for fillo in fillos:
        f.addElement(fillo)
    return f


def _caixa(*fillos):
    c = TextBox()
    for fillo in fillos:
        c.addElement(fillo)
    return c


class TestOdp(_Base):
    def _pagina(self, doc, nome, titulo=None, puntos=(), notas=None, oculta=False):
        p = Page(name=nome, masterpagename="Default")
        if oculta:
            # Como o garda LibreOffice: no estilo da páxina.
            estilo = Style(name=f"dp_{nome}", family="drawing-page")
            estilo.addElement(DrawingPageProperties())
            estilo.getElementsByType(DrawingPageProperties)[0].setAttrNS(
                PRESENTATIONNS, "visibility", "hidden")
            doc.automaticstyles.addElement(estilo)
            p.setAttrNS(DRAWNS, "style-name", f"dp_{nome}")
        if titulo:
            p.addElement(_frame("title", _caixa(P(text=titulo))))
        if puntos:
            lista = List()
            for punto in puntos:
                item = ListItem()
                if isinstance(punto, tuple):
                    sub = List()
                    sub_item = ListItem()
                    sub_item.addElement(P(text=punto[0]))
                    sub.addElement(sub_item)
                    item.addElement(sub)
                else:
                    item.addElement(P(text=punto))
                lista.addElement(item)
            p.addElement(_frame("outline", _caixa(lista)))
        if notas:
            n = Notes()
            n.addElement(_frame("notes", _caixa(P(text=notas))))
            p.addElement(n)
        doc.presentation.addElement(p)
        return p

    def test_unha_seccion_por_diapositiva(self):
        doc = OpenDocumentPresentation()
        self._pagina(doc, "page1", "Obxecto", ["Primeiro", ("Subpunto",), "Segundo"])
        self._pagina(doc, "page2", "Prazos", ["Tres meses"])
        ruta = self.ruta("p.odp")
        doc.save(ruta)
        md = presentacions.a_markdown(ruta)
        self.assertIn("## Diapositiva 1: Obxecto", md)
        self.assertIn("- Primeiro", md)
        self.assertIn("  - Subpunto", md)
        self.assertIn("- Segundo", md)
        self.assertIn("## Diapositiva 2: Prazos", md)

    def test_notas_do_orador(self):
        doc = OpenDocumentPresentation()
        self._pagina(doc, "page1", "Tema", ["Algo"], notas="Lembrar o caso de Ana Pena")
        ruta = self.ruta("p.odp")
        doc.save(ruta)
        md = presentacions.a_markdown(ruta)
        self.assertIn("Notas do orador", md)
        self.assertIn("Lembrar o caso de Ana Pena", md)

    def test_diapositiva_oculta_omitese_e_avisase(self):
        doc = OpenDocumentPresentation()
        self._pagina(doc, "page1", "Visible", ["a"])
        self._pagina(doc, "page2", "Descartada", ["dato escondido"], notas="nota escondida", oculta=True)
        ruta = self.ruta("p.odp")
        doc.save(ruta)
        conv = presentacions.convertir(ruta)
        self.assertNotIn("dato escondido", conv.markdown)
        self.assertNotIn("nota escondida", conv.markdown)
        self.assertTrue(any("2" in a for a in conv.avisos))

    def test_taboa(self):
        doc = OpenDocumentPresentation()
        p = self._pagina(doc, "page1", "Datos")
        taboa = Table(name="t")
        for fila in (["Concepto", "Importe"], ["Material", "12"]):
            tr = TableRow()
            for valor in fila:
                tc = TableCell(valuetype="string")
                tc.addElement(P(text=valor))
                tr.addElement(tc)
            taboa.addElement(tr)
        marco = Frame(width="10cm", height="3cm", x="0cm", y="3cm")
        marco.addElement(taboa)
        marco.addElement(ImaxeOdp(href="Pictures/TablePreview1.svm"))  # vista previa de LibreOffice
        p.addElement(marco)
        ruta = self.ruta("p.odp")
        doc.save(ruta)
        md = presentacions.a_markdown(ruta)
        self.assertIn("| Concepto | Importe |", md)
        self.assertIn("| Material | 12 |", md)
        self.assertNotIn("[imaxe]", md)

    def test_texto_solto_non_e_lista_e_sen_titulo_so_numero(self):
        doc = OpenDocumentPresentation()
        p = Page(name="page1", masterpagename="Default")
        marco = Frame(width="5cm", height="2cm", x="0cm", y="0cm")
        marco.addElement(_caixa(P(text="Texto solto")))
        p.addElement(marco)
        doc.presentation.addElement(p)
        ruta = self.ruta("p.odp")
        doc.save(ruta)
        md = presentacions.a_markdown(ruta)
        self.assertIn("## Diapositiva 1\n", md)
        self.assertIn("Texto solto", md)
        self.assertNotIn("- Texto solto", md)

    def test_pe_e_data_non_saen(self):
        doc = OpenDocumentPresentation()
        p = self._pagina(doc, "page1", "Tema", ["a"])
        p.addElement(_frame("footer", _caixa(P(text="PE REPETIDO"))))
        p.addElement(_frame("date-time", _caixa(P(text="DATA REPETIDA"))))
        ruta = self.ruta("p.odp")
        doc.save(ruta)
        md = presentacions.a_markdown(ruta)
        self.assertNotIn("PE REPETIDO", md)
        self.assertNotIn("DATA REPETIDA", md)

    def test_imaxe_marcase(self):
        doc = OpenDocumentPresentation()
        p = self._pagina(doc, "page1", "Foto", ["a"])
        marco = Frame(width="5cm", height="2cm", x="0cm", y="0cm")
        marco.addElement(ImaxeOdp(href="Pictures/x.png"))
        p.addElement(marco)
        ruta = self.ruta("p.odp")
        doc.save(ruta)
        self.assertIn("[imaxe]", presentacions.a_markdown(ruta))


if __name__ == "__main__":
    unittest.main()
