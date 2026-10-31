"""Follas de cálculo (.xlsx, .ods, .csv) a Markdown, SEN anonimizar
(`formatos/follas.py`, fase 4 do conversor a .md)."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

import openpyxl
import xlsxwriter
from openpyxl.comments import Comment
from odf.namespaces import TABLENS
from odf.office import Annotation
from odf.opendocument import OpenDocumentSpreadsheet
from odf.style import Style, TableProperties
from odf.table import CoveredTableCell, Table, TableCell, TableColumn, TableRow
from odf.text import P

os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador.formatos import follas


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def ruta(self, nome: str) -> str:
        return str(self.dir / nome)


class TestXlsx(_Base):
    def _libro(self, nome="datos.xlsx"):
        libro = openpyxl.Workbook()
        folla = libro.active
        folla.title = "Persoal"
        folla.append(["Nome", "Cargo", "Idade"])
        folla.append(["Ana Pena", "Xefa", 41])
        folla.append(["Bruno Lois", "Técnico", 35])
        return libro, folla, self.ruta(nome)

    def test_cada_folla_e_unha_taboa_co_seu_nome(self):
        libro, _, ruta = self._libro()
        outra = libro.create_sheet("Gastos")
        outra.append(["Concepto", "Importe"])
        outra.append(["Material", 12.5])
        libro.save(ruta)
        md = follas.a_markdown(ruta)
        self.assertIn("## Persoal", md)
        self.assertIn("| Nome | Cargo | Idade |", md)
        self.assertIn("| Ana Pena | Xefa | 41 |", md)
        self.assertIn("## Gastos", md)
        self.assertIn("| Material | 12.5 |", md)
        self.assertLess(md.index("## Persoal"), md.index("## Gastos"))

    def test_folla_oculta_omitese_e_avisase(self):
        libro, _, ruta = self._libro()
        oculta = libro.create_sheet("Reservado")
        oculta.append(["Clave", "Valor"])
        oculta.append(["segredo", "DNI 12345678Z"])
        oculta.sheet_state = "hidden"
        libro.save(ruta)
        conv = follas.convertir(ruta)
        self.assertNotIn("12345678Z", conv.markdown)
        self.assertNotIn("Reservado", conv.markdown)
        self.assertTrue(any("Reservado" in a for a in conv.avisos))

    def test_folla_moi_oculta_omitese(self):
        libro, _, ruta = self._libro()
        oculta = libro.create_sheet("Fondo")
        oculta.append(["a", "b"])
        oculta.append(["dato escondido", 1])
        oculta.sheet_state = "veryHidden"
        libro.save(ruta)
        self.assertNotIn("dato escondido", follas.a_markdown(ruta))

    def test_filas_e_columnas_ocultas_omítense(self):
        libro, folla, ruta = self._libro()
        folla.append(["Carme Dopico", "Oculta", 50])
        folla.row_dimensions[4].hidden = True
        folla.column_dimensions["C"].hidden = True
        libro.save(ruta)
        conv = follas.convertir(ruta)
        self.assertNotIn("Carme Dopico", conv.markdown)
        self.assertNotIn("Idade", conv.markdown)
        self.assertIn("Ana Pena", conv.markdown)
        self.assertTrue(conv.avisos)

    def test_comentarios_de_cela_inclúense_sen_autor(self):
        libro, folla, ruta = self._libro()
        folla["B2"].comment = Comment("Pendente de confirmar", "Autor Secreto")
        libro.save(ruta)
        md = follas.a_markdown(ruta)
        self.assertIn("Pendente de confirmar", md)
        self.assertIn("B2", md)
        self.assertNotIn("Autor Secreto", md)

    def test_metadatos_de_autor_non_saen(self):
        libro, _, ruta = self._libro()
        libro.properties.creator = "Creador Privado"
        libro.properties.lastModifiedBy = "Outra Persoa"
        libro.properties.title = "Título interno"
        libro.save(ruta)
        md = follas.a_markdown(ruta)
        self.assertNotIn("Creador Privado", md)
        self.assertNotIn("Outra Persoa", md)

    def test_tipos_datas_enteiros_e_booleanos(self):
        import datetime
        libro, folla, ruta = self._libro()
        folla.append([datetime.datetime(2026, 10, 31), 3.0, True])
        folla.append([datetime.datetime(2026, 10, 31, 14, 30), 0.25, False])
        libro.save(ruta)
        md = follas.a_markdown(ruta)
        self.assertIn("| 2026-10-31 | 3 | TRUE |", md)
        self.assertIn("| 2026-10-31 14:30 | 0.25 | FALSE |", md)

    def test_numeros_co_formato_de_cela_que_ve_a_persoa(self):
        libro = openpyxl.Workbook()
        folla = libro.active
        folla.title = "Contas"
        folla.append(["Importe", "IVA", "Código", "Total"])
        folla.append([1234.5, 0.21, 123, 3.5])
        for cela, formato in zip(folla[2], ('#,##0.00 "€"', "0%", "00000", "General")):
            cela.number_format = formato
        ruta = self.ruta("contas.xlsx")
        libro.save(ruta)
        md = follas.a_markdown(ruta)
        self.assertIn("| 1.234,50 € | 21% | 00123 | 3.5 |", md)

    def test_formula_co_valor_gardado_e_sen_el(self):
        ruta = self.ruta("formulas.xlsx")
        libro = xlsxwriter.Workbook(ruta)
        folla = libro.add_worksheet("F")
        folla.write_row("A1", ["x", "y"])
        folla.write_row("A2", [1, 2])
        folla.write_formula("A3", "=SUM(A2:B2)", None, 3)
        folla.write_formula("B3", "=A2*10")  # sen valor gardado (0 por defecto)
        libro.close()
        md = follas.a_markdown(ruta)
        self.assertIn("| 3 |", md)
        self.assertNotIn("=SUM", md)

    def test_formula_sen_valor_gardado_sae_coma_formula(self):
        libro, folla, ruta = self._libro()
        folla["C4"] = "=SUM(C2:C3)"
        libro.save(ruta)  # openpyxl non garda o valor calculado
        self.assertIn("=SUM(C2:C3)", follas.a_markdown(ruta))

    def test_barras_e_saltos_nas_celas_non_rompen_a_taboa(self):
        libro, folla, ruta = self._libro()
        folla["B2"] = "Xefa | interina\nde zona"
        libro.save(ruta)
        md = follas.a_markdown(ruta)
        self.assertIn("Xefa \\| interina de zona", md)

    def test_folla_baleira_omitese(self):
        libro, _, ruta = self._libro()
        libro.create_sheet("Baleira")
        libro.save(ruta)
        self.assertNotIn("Baleira", follas.a_markdown(ruta))

    def test_folla_dunha_columna_non_se_perde(self):
        libro = openpyxl.Workbook()
        folla = libro.active
        folla.title = "Lista"
        for valor in ["Primeiro", "Segundo", "Terceiro"]:
            folla.append([valor])
        ruta = self.ruta("lista.xlsx")
        libro.save(ruta)
        md = follas.a_markdown(ruta)
        for valor in ["Primeiro", "Segundo", "Terceiro"]:
            self.assertIn(valor, md)

    def test_folla_grande_sen_cartafol_conserva_todo_e_avisa(self):
        libro, folla, ruta = self._libro()
        for i in range(10):
            folla.append([f"Fila{i}", "x", i])
        libro.save(ruta)
        conv = follas.convertir(ruta, max_filas=5)
        self.assertIn("Fila9", conv.markdown)
        self.assertTrue(any("Persoal" in a for a in conv.avisos))
        self.assertEqual(conv.ficheiros, [])

    def test_folla_grande_co_cartafol_vai_a_csv_aparte(self):
        libro, folla, ruta = self._libro()
        for i in range(10):
            folla.append([f"Fila{i}", "x", i])
        libro.save(ruta)
        saida = self.dir / "saida"
        saida.mkdir()
        conv = follas.convertir(ruta, max_filas=5, dir_csv=str(saida))
        self.assertNotIn("Fila9", conv.markdown)
        self.assertIn("Nome", conv.markdown)  # a cabeceira, para saber as columnas
        self.assertEqual(len(conv.ficheiros), 1)
        csv_aparte = Path(conv.ficheiros[0])
        self.assertEqual(csv_aparte.parent, saida)
        self.assertIn(csv_aparte.name, conv.markdown)
        contido = csv_aparte.read_text(encoding="utf-8")
        self.assertIn("Fila9,x,9", contido)
        self.assertIn("Ana Pena,Xefa,41", contido)

    def test_folla_pequena_con_cartafol_non_crea_csv(self):
        libro, _, ruta = self._libro()
        libro.save(ruta)
        saida = self.dir / "saida"
        saida.mkdir()
        conv = follas.convertir(ruta, dir_csv=str(saida))
        self.assertEqual(conv.ficheiros, [])
        self.assertEqual(list(saida.iterdir()), [])

    def test_limite_por_defecto_son_500_filas(self):
        self.assertEqual(follas.MAX_FILAS, 500)


class TestCsv(_Base):
    def _csv(self, contido, nome="datos.csv", codificacion="utf-8"):
        ruta = self.ruta(nome)
        Path(ruta).write_bytes(contido.encode(codificacion))
        return ruta

    def test_coma(self):
        md = follas.a_markdown(self._csv("Nome,Cargo\nAna,Xefa\nBruno,Técnico\n"))
        self.assertIn("| Nome | Cargo |", md)
        self.assertIn("| Bruno | Técnico |", md)

    def test_punto_e_coma_con_decimais_en_coma(self):
        md = follas.a_markdown(self._csv("Concepto;Importe\nMaterial;12,50\nViaxe;3,25\n"))
        self.assertIn("| Concepto | Importe |", md)
        self.assertIn("| Material | 12,50 |", md)

    def test_tabulador(self):
        md = follas.a_markdown(self._csv("a\tb\n1\t2\n"))
        self.assertIn("| a | b |", md)

    def test_campo_con_delimitador_entre_aspas(self):
        md = follas.a_markdown(self._csv('Nome;Nota\n"Pena; Ana";"di ""ola"""\nB;C\n'))
        self.assertIn("| Pena; Ana | di \"ola\" |", md)

    def test_cp1252_de_excel(self):
        md = follas.a_markdown(self._csv("Nome;Cidade\nMuñiz;Ourense\n", codificacion="cp1252"))
        self.assertIn("Muñiz", md)

    def test_utf8_con_bom(self):
        md = follas.a_markdown(self._csv("﻿Nome,Cargo\nAna,Xefa\n"))
        self.assertIn("| Nome | Cargo |", md)
        self.assertNotIn("﻿", md)

    def test_baleiro_da_markdown_baleiro(self):
        self.assertEqual(follas.a_markdown(self._csv("")).strip(), "")

    def test_csv_grande_co_cartafol_vai_aparte(self):
        filas = "\n".join(f"{i};x" for i in range(20))
        ruta = self._csv("id;valor\n" + filas + "\n", nome="grande.csv")
        saida = self.dir / "saida"
        saida.mkdir()
        conv = follas.convertir(ruta, max_filas=5, dir_csv=str(saida))
        self.assertNotIn("| 19 |", conv.markdown)
        self.assertEqual(len(conv.ficheiros), 1)
        self.assertIn("19;x", Path(conv.ficheiros[0]).read_text(encoding="utf-8")
                      .replace(",", ";"))
        self.assertNotEqual(Path(conv.ficheiros[0]), Path(ruta))


class TestOds(_Base):
    def _libro(self):
        doc = OpenDocumentSpreadsheet()
        return doc

    def _folla(self, doc, nome, filas, **args):
        folla = Table(name=nome, **args)
        for fila in filas:
            tr = TableRow()
            for valor in fila:
                tc = TableCell(valuetype="string")
                tc.addElement(P(text=str(valor)))
                tr.addElement(tc)
            folla.addElement(tr)
        doc.spreadsheet.addElement(folla)
        return folla

    def test_cada_folla_e_unha_taboa(self):
        doc = self._libro()
        self._folla(doc, "Persoal", [["Nome", "Cargo"], ["Ana Pena", "Xefa"]])
        self._folla(doc, "Gastos", [["Concepto", "Importe"], ["Material", "12"]])
        ruta = self.ruta("d.ods")
        doc.save(ruta)
        md = follas.a_markdown(ruta)
        self.assertIn("## Persoal", md)
        self.assertIn("| Ana Pena | Xefa |", md)
        self.assertIn("## Gastos", md)
        self.assertIn("| Material | 12 |", md)

    def test_usa_o_texto_mostrado_da_cela(self):
        doc = self._libro()
        folla = Table(name="F")
        tr = TableRow()
        for texto in ["Importe", "Prezo"]:
            tc = TableCell(valuetype="string")
            tc.addElement(P(text=texto))
            tr.addElement(tc)
        folla.addElement(tr)
        tr = TableRow()
        tc = TableCell(valuetype="float", value=1234.5)
        tc.addElement(P(text="1.234,50 €"))
        tr.addElement(tc)
        tc = TableCell(valuetype="float", value=3)
        tr.addElement(tc)  # sen texto mostrado: cae ao valor
        folla.addElement(tr)
        doc.spreadsheet.addElement(folla)
        ruta = self.ruta("d.ods")
        doc.save(ruta)
        self.assertIn("| 1.234,50 € | 3 |", follas.a_markdown(ruta))

    def test_folla_oculta_omitese_e_avisase(self):
        doc = self._libro()
        estilo = Style(name="taoculta", family="table")
        estilo.addElement(TableProperties(display="false"))
        doc.automaticstyles.addElement(estilo)
        self._folla(doc, "Visible", [["a", "b"], ["1", "2"]])
        self._folla(doc, "Segredo", [["a", "b"], ["clave", "DNI 12345678Z"]], stylename="taoculta")
        ruta = self.ruta("d.ods")
        doc.save(ruta)
        conv = follas.convertir(ruta)
        self.assertNotIn("12345678Z", conv.markdown)
        self.assertNotIn("Segredo", conv.markdown)
        self.assertTrue(any("Segredo" in a for a in conv.avisos))

    def test_fila_e_columna_ocultas_omítense(self):
        doc = self._libro()
        folla = Table(name="F")
        col = TableColumn()
        folla.addElement(col)
        col = TableColumn()
        col.setAttrNS(TABLENS, "visibility", "collapse")
        folla.addElement(col)
        for i, fila in enumerate([["a", "oculta-col"], ["1", "x"], ["2", "y"]]):
            tr = TableRow()
            if i == 2:
                tr.setAttrNS(TABLENS, "visibility", "collapse")
            for valor in fila:
                tc = TableCell(valuetype="string")
                tc.addElement(P(text=valor))
                tr.addElement(tc)
            folla.addElement(tr)
        doc.spreadsheet.addElement(folla)
        ruta = self.ruta("d.ods")
        doc.save(ruta)
        md = follas.a_markdown(ruta)
        self.assertNotIn("oculta-col", md)
        self.assertNotIn("| 2 |", md)

    def test_repeticions_de_filas_baleiras_non_explotan(self):
        doc = self._libro()
        folla = self._folla(doc, "F", [["a", "b"], ["1", "2"]])
        tr = TableRow(numberrowsrepeated=1048576)
        tr.addElement(TableCell(numbercolumnsrepeated=1024))
        folla.addElement(tr)
        ruta = self.ruta("d.ods")
        doc.save(ruta)
        md = follas.a_markdown(ruta)
        self.assertLess(len(md), 500)

    def test_celas_repetidas_e_combinadas(self):
        doc = self._libro()
        folla = Table(name="F")
        tr = TableRow()
        tc = TableCell(valuetype="string", numbercolumnsrepeated=2)
        tc.addElement(P(text="igual"))
        tr.addElement(tc)
        tc = TableCell(valuetype="string", numbercolumnsspanned=1)
        tc.addElement(P(text="fin"))
        tr.addElement(tc)
        folla.addElement(tr)
        tr = TableRow()
        for v in ["1", "2"]:
            tc = TableCell(valuetype="string")
            tc.addElement(P(text=v))
            tr.addElement(tc)
        tr.addElement(CoveredTableCell())
        folla.addElement(tr)
        doc.spreadsheet.addElement(folla)
        ruta = self.ruta("d.ods")
        doc.save(ruta)
        md = follas.a_markdown(ruta)
        self.assertIn("| igual | igual | fin |", md)
        self.assertIn("| 1 | 2 |  |", md)

    def test_comentarios_de_cela_sen_autor_nin_data(self):
        doc = self._libro()
        folla = Table(name="F")
        tr = TableRow()
        tc = TableCell(valuetype="string")
        tc.addElement(P(text="a"))
        nota = Annotation()
        from odf.dc import Creator, Date
        nota.addElement(Creator(text="Autor Secreto"))
        nota.addElement(Date(text="2026-01-02T10:00:00"))
        nota.addElement(P(text="Revisar co cliente"))
        tc.addElement(nota)
        tr.addElement(tc)
        tc = TableCell(valuetype="string")
        tc.addElement(P(text="b"))
        tr.addElement(tc)
        folla.addElement(tr)
        tr = TableRow()
        for v in ["1", "2"]:
            tc = TableCell(valuetype="string")
            tc.addElement(P(text=v))
            tr.addElement(tc)
        folla.addElement(tr)
        doc.spreadsheet.addElement(folla)
        ruta = self.ruta("d.ods")
        doc.save(ruta)
        md = follas.a_markdown(ruta)
        self.assertIn("Revisar co cliente", md)
        self.assertIn("A1", md)
        self.assertNotIn("Autor Secreto", md)
        self.assertNotIn("2026-01-02", md)
        self.assertIn("| a | b |", md)  # o comentario non ensucia a cela

    def test_folla_grande_vai_a_csv_aparte(self):
        doc = self._libro()
        filas = [["id", "valor"]] + [[str(i), "x"] for i in range(12)]
        self._folla(doc, "Datos", filas)
        ruta = self.ruta("grande.ods")
        doc.save(ruta)
        saida = self.dir / "saida"
        saida.mkdir()
        conv = follas.convertir(ruta, max_filas=5, dir_csv=str(saida))
        self.assertNotIn("| 11 |", conv.markdown)
        self.assertIn("11,x", Path(conv.ficheiros[0]).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
