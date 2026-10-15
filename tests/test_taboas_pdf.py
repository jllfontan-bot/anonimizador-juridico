"""Detección POR COLUMNA nas táboas dos PDF (`taboas_pdf.py`).

Fugas reais do corpus web (BOE + DOG, 28/09/2026) reproducidas con táboas
SINTÉTICAS: a cela "APELIDOS, NOME" partida en varias liñas deixaba á
vista parte do nome ("VARELA" de "VARELA / DOVAL, / ANTÍA.", "Manuel" de
"Salcedo Roel, Brais / Manuel"), e o NRP enmascarado do BOE ("***4567**")
quedaba tal cal. Con detección por columna, a cabeceira ("Apellidos y
nombre", "NRP", "DNI/NIE/PAS") decide, non a forma do texto.

Compróbase SEMPRE no PDF de saída relido (capa de texto) e nos seus bytes,
e tamén o contrario: o que NON é dato persoal (outras columnas, "Desierto",
unha táboa sen esas cabeceiras) segue igual.
"""
import os

# Estas probas escribíronse coa interface e os códigos en galego (PERSOA_...).
os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import fitz  # PyMuPDF

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador import taboas_pdf
from anonimizador.pdf_estrutura import cargar_pdf_estruturado
from anonimizador.pipeline import anonimizar_e_gardar
from anonimizador.registry import RexistroCorrespondencias

_ALTO_FILA = 40


def _taboa(pagina, x0, y0, anchos, filas, tamano=8):
    """Táboa con bordos vectoriais, unha cela por `insert_textbox` (os "\\n"
    de cada texto son liñas dentro da cela, coma nas listaxes do BOE)."""
    y = y0
    for fila in filas:
        x = x0
        for ancho, texto in zip(anchos, fila):
            rect = fitz.Rect(x, y, x + ancho, y + _ALTO_FILA)
            pagina.draw_rect(rect, color=(0, 0, 0), width=0.5)
            if texto:
                sobra = pagina.insert_textbox(rect + (2, 2, -2, -2), texto, fontsize=tamano, fontname="helv")
                assert sobra >= 0, f"non cabe: {texto!r}"
            x += ancho
        y += _ALTO_FILA


_CABECEIRA = ["N.º orden", "Puesto", "Apellidos y nombre", "NRP", "DNI/NIE/PAS", "Situación"]
_ANCHOS = [40, 110, 110, 70, 80, 90]
_FILAS = [
    ["1", "Jefe de Sección\nde Gestión", "CASTRO BOUZAS,\nMARÍA XOSÉ.", "***4567**\nA1135", "BF718330", "Servicio\nactivo"],
    ["2", "Jefe de Negociado\nN18", "VARELA\nDOVAL,\nANTÍA.", "***1234**\nA1146", "P2921485", "Servicio\nactivo"],
    ["3", "Técnico Superior", "Salcedo Roel, Brais\nManuel", "***9876**\nA1135", "Y1234567X", "Servicio\nactivo"],
    ["4", "Analista", "Desierto", "", "", ""],
]
_DATOS = ("CASTRO", "BOUZAS", "XOSÉ", "VARELA", "DOVAL", "ANTÍA", "Salcedo", "Brais", "Manuel",
          "4567", "1234", "9876", "BF718330", "P2921485", "Y1234567X")
_NON_DATOS = ("Apellidos y nombre", "DNI/NIE/PAS", "Jefe de Sección", "N18", "Técnico Superior",
              "Servicio", "Desierto", "Analista")


class _Base(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.rexistro = RexistroCorrespondencias(str(self.dir / "rexistro.db"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _procesar(self, documento, nome="taboa.pdf"):
        entrada = self.dir / nome
        documento.save(str(entrada))
        saida = self.dir / ("anon_" + nome)
        texto, informe = anonimizar_e_gardar(str(entrada), str(saida), self.rexistro)
        return saida, texto, informe

    def _texto_pdf(self, ruta) -> str:
        with fitz.open(str(ruta)) as documento:
            return "\n".join(pagina.get_text() for pagina in documento)

    def _sen(self, ruta, agullas):
        texto = self._texto_pdf(ruta)
        datos = ruta.read_bytes()
        for agulla in agullas:
            self.assertNotIn(agulla, texto, f"{agulla!r} segue no texto do PDF")
            self.assertNotIn(agulla.encode(), datos, f"{agulla!r} segue nos bytes do PDF")

    def _con(self, ruta, agullas):
        texto = " ".join(self._texto_pdf(ruta).split())
        for agulla in agullas:
            self.assertIn(agulla, texto, f"{agulla!r} desapareceu (sobre-anonimización)")


class TestCabeceiras(unittest.TestCase):
    def test_cabeceiras_de_persoa(self):
        for cabeceira in ("Apellidos y nombre", "APELLIDOS Y NOMBRE", "Nome e apelidos", "NOME E APELIDOS(*)",
                          "Apelidos e nome", "Nombre completo", "1º apelido", "2º apelido", "Nome", "Nombre:",
                          "Primer apellido", "Persoa interesada/DNI"):
            self.assertEqual(taboas_pdf.papel_da_cabeceira(cabeceira), taboas_pdf.PERSOA, cabeceira)

    def test_cabeceiras_de_documento(self):
        for cabeceira in ("DNI", "D.N.I.", "NIF", "NRP", "DNI/NIE/PAS", "DNI / NIE", "DNI/NIF/CIF",
                          "DNI/NIE(*)", "Pasaporte", "Documento de identidad"):
            self.assertEqual(taboas_pdf.papel_da_cabeceira(cabeceira), taboas_pdf.DOCUMENTO, cabeceira)

    def test_cabeceiras_que_non_son_de_dato_persoal(self):
        # Mixtas (poden ser empresas) ou que só CONTEÑEN a palabra.
        for cabeceira in ("Titular", "NOME/RAZÓN SOCIAL", "NOME E APELIDOS/RAZÓN SOCIAL5",
                          "Nome da parcela", "DNI/NIE da persoa representante", "Puesto",
                          "TITULAR CATASTRAL DNI/Razón social/Nombre", "PAS", "", None):
            self.assertIsNone(taboas_pdf.papel_da_cabeceira(cabeceira), cabeceira)


class TestColumnaNomeEDocumento(_Base):
    def _documento(self):
        documento = fitz.open()
        pagina = documento.new_page()
        pagina.insert_text((50, 60), "ANEXO. Resolución de adjudicación de puestos.", fontsize=10)
        _taboa(pagina, 50, 80, _ANCHOS, [_CABECEIRA] + _FILAS)
        return documento

    def test_celas_partidas_en_varias_linas_non_escapan(self):
        saida, _texto, _informe = self._procesar(self._documento())
        self._sen(saida, _DATOS)
        self._con(saida, _NON_DATOS)

    def test_unha_persoa_por_cela(self):
        # "Salcedo Roel, Brais / Manuel" é UNHA persoa: antes quedaba en dúas
        # (e "Manuel" á vista); agora un só código por fila.
        _saida, _texto, informe = self._procesar(self._documento())
        mencions = sorted(" ".join(m.split()) for p in informe["persoas"] for m in p["mencions"])
        self.assertEqual(mencions, ["CASTRO BOUZAS, MARÍA XOSÉ", "Salcedo Roel, Brais Manuel", "VARELA DOVAL, ANTÍA"])

    def test_documentos_da_fila_levan_o_codigo_do_seu_titular(self):
        # Decisión do usuario (29/09/2026): nome e documento son datos da
        # MESMA persoa -> o mesmo código, ligados pola fila da táboa.
        _saida, texto, informe = self._procesar(self._documento())
        for persoa in informe["persoas"]:
            self.assertEqual(texto.count(persoa["codigo"]), 4)  # nome, NRP (2 anacos), DNI/NIE/PAS
        for etiqueta in ("[DNI_NIE]", "[PASAPORTE]", "[DOCUMENTO_IDENTIDADE]"):
            self.assertNotIn(etiqueta, texto)

    def test_offsets_das_celas_apuntan_ao_texto_da_cela(self):
        entrada = self.dir / "taboa.pdf"
        self._documento().save(str(entrada))
        texto, contexto = cargar_pdf_estruturado(str(entrada))
        persoas = [" ".join(texto[a:b] for a, b in c.pezas)
                   for c in contexto["celas_datos_persoais"] if c.tipo == taboas_pdf.PERSOA]
        self.assertEqual([" ".join(p.split()) for p in persoas],
                         ["CASTRO BOUZAS, MARÍA XOSÉ.", "VARELA DOVAL, ANTÍA.", "Salcedo Roel, Brais Manuel", "Desierto"])


class TestColumnasSeparadasDoNome(_Base):
    def test_apelidos_e_nome_en_columnas_distintas(self):
        documento = fitz.open()
        pagina = documento.new_page()
        _taboa(pagina, 50, 80, [90, 90, 90, 80, 110], [
            ["1º apelido", "2º apelido", "Nome", "NIF", "Posto"],
            ["Lucas", "Fandiño", "Uxía", "***5678**", "Xefatura de Servizo"],
            ["Pazos", "Rei", "Iago", "***8765**", "Negociado"],
        ])
        saida, _texto, informe = self._procesar(documento)
        self._sen(saida, ("Lucas", "Fandiño", "Uxía", "Pazos", "Iago", "5678", "8765"))
        self._con(saida, ("Xefatura de Servizo", "Negociado", "1º apelido"))
        # Os tres anacos da mesma fila son UNHA persoa (van seguidos no texto).
        self.assertEqual(len(informe["persoas"]), 2)


class TestColumnaMixtaPersoaDNI(_Base):
    def test_persoa_interesada_con_dni_na_mesma_cela(self):
        documento = fitz.open()
        pagina = documento.new_page()
        _taboa(pagina, 50, 80, [120, 200], [
            ["Credencial/expediente", "Persoa interesada/DNI"],
            ["EXP-2026/0001", "Rosa Varela Doval\n33445566Z"],
        ])
        saida, _texto, _informe = self._procesar(documento)
        self._sen(saida, ("Rosa", "Varela", "Doval", "33445566"))
        self._con(saida, ("Persoa interesada/DNI", "EXP-2026/0001"))


class TestTaboaQueContinua(_Base):
    def _paxina_continuacion(self, documento, anchos):
        pagina = documento.new_page()
        _taboa(pagina, 50, 50, anchos, [
            ["5", "Auxiliar", "OTERO\nFIGUEIRAS,\nIAGO.", "***2468**\nA1135", "XK551234", "Servicio\nactivo"],
        ])

    def test_continuacion_sen_cabeceira_coas_mesmas_columnas(self):
        documento = fitz.open()
        _taboa(documento.new_page(), 50, 80, _ANCHOS, [_CABECEIRA] + _FILAS[:1])
        self._paxina_continuacion(documento, _ANCHOS)
        saida, _texto, _informe = self._procesar(documento)
        self._sen(saida, ("OTERO", "FIGUEIRAS", "IAGO", "2468", "XK551234"))
        self._con(saida, ("Auxiliar",))

    def test_cabeceira_repetida_en_cada_paxina(self):
        documento = fitz.open()
        _taboa(documento.new_page(), 50, 80, _ANCHOS, [_CABECEIRA] + _FILAS[:1])
        pagina = documento.new_page()
        _taboa(pagina, 50, 50, _ANCHOS, [_CABECEIRA, _FILAS[1]])
        saida, _texto, _informe = self._procesar(documento)
        self._sen(saida, ("VARELA", "DOVAL", "ANTÍA", "P2921485"))

    def test_non_se_herda_se_as_columnas_cambian(self):
        # Outra táboa distinta na páxina seguinte (outras columnas): o que
        # hai na posición da antiga columna de nomes NON se toca.
        documento = fitz.open()
        _taboa(documento.new_page(), 50, 80, _ANCHOS, [_CABECEIRA] + _FILAS[:1])
        pagina = documento.new_page()
        _taboa(pagina, 50, 50, [60, 160, 100, 100], [
            ["Parcela", "Paraje", "Cultivo", "Superficie"],
            ["12", "Monte Grande", "Labradío", "1.200 m²"],
        ])
        saida, _texto, _informe = self._procesar(documento)
        self._con(saida, ("Monte Grande", "Labradío"))


class TestSenTaboaDeDatosPersoais(_Base):
    def test_taboa_sen_esas_cabeceiras_non_cambia(self):
        documento = fitz.open()
        pagina = documento.new_page()
        _taboa(pagina, 50, 80, [150, 100, 100], [
            ["Materia", "Créditos", "Carácter"],
            ["Derecho Civil\nPatrimonial", "6", "Obligatoria"],
            ["Historia del Derecho", "6", "Básica"],
        ])
        entrada = self.dir / "materias.pdf"
        documento.save(str(entrada))
        _texto, contexto = cargar_pdf_estruturado(str(entrada))
        self.assertEqual(contexto["celas_datos_persoais"], [])
        saida, _texto, _informe = self._procesar(documento)
        self._con(saida, ("Derecho Civil", "Historia del Derecho", "Obligatoria"))

    def test_cela_de_nome_que_non_e_nome(self):
        # Rótulos de formulario e textos en minúscula baixo "Nombre" non se
        # forzan coma persoa.
        documento = fitz.open()
        pagina = documento.new_page()
        _taboa(pagina, 50, 80, [200, 200], [
            ["Nombre", "Observaciones"],
            ["pendiente de designar", "Sin datos"],
            ["Vacante", "Sin datos"],
        ])
        saida, _texto, _informe = self._procesar(documento)
        self._con(saida, ("pendiente de designar", "Vacante"))


if __name__ == "__main__":
    unittest.main()


class TestColumnaPropietario(_Base):
    """BOE-B-2025-27849 (lote 4, FUGA confirmada polo usuario): relación de
    bens e dereitos dunha liña eléctrica, columna "Propietario" con varios
    titulares por cela separados por ";" e partidos en liñas; quedaban á
    vista anacos ("Herminda", "Panduro Galan", "Ramirez Paez Ramon").
    A columna é mixta (pode ser unha empresa ou un organismo): cada anaco só
    se toma por persoa se todas as súas palabras son nomes/apelidos do INE."""

    def _documento(self):
        documento = fitz.open()
        pagina = documento.new_page()
        pagina.insert_text((50, 60), "Relación de bienes y derechos de línea aérea y accesos", fontsize=10)
        _taboa(pagina, 50, 80, [40, 150, 90, 90], [
            ["Parcela\nnúmero", "Propietario", "Referencia\nCatastral", "Cultivo"],
            ["9", "Panduro Ferrer\nRuben; Panduro\nGalan Maria Luisa;", "52014A05200", "Pinar\nmaderable"],
            ["10", "Ramirez Aranda Maria\nCelestina; Ramirez\nPaez Ramon", "52014A05200", "Pinar\nmaderable"],
            ["11", "Vera Sastre Jose\nManuel (Herederos)", "52014A05200", "Eucaliptus"],
            ["12", "Principado de\nAsturias", "52014A05201", "Vía de\ncomunicación"],
            ["13", "Hidrocantábrico\nDistribución, SA", "52014A05202", "Matorral"],
        ])
        return documento

    def test_titulares_tapados_e_organismos_a_vista(self):
        saida, _, _ = self._procesar(self._documento())
        self._sen(saida, ("Ruben", "Panduro", "Maria Luisa", "Celestina", "Rodriguez", "Ramon", "Vera Sastre", "Jose"))
        self._con(saida, ("Principado de", "Asturias", "Hidrocantábrico", "Pinar", "Propietario"))
