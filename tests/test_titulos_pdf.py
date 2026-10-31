"""Títulos en PDF con texto, polo tamaño da letra (fase 5 do conversor).

PDF sintéticos: un título que se detecta e textos que NON son títulos (negra,
maiúsculas, cabeceiras, números de páxina, frases en letra grande). Os
títulos só van ao .md do conversor: a copia .md do anonimizador non os leva.

Todos os nomes son sintéticos.
"""

import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import fitz  # PyMuPDF

os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")

from anonimizador import conversor, copia_md, lectura, titulos_pdf  # noqa: E402
from anonimizador.registry import RexistroCorrespondencias  # noqa: E402

_CORPO = [
    "O demandante presentou o escrito no prazo legal e acompañou os documentos",
    "que acreditan a súa lexitimación para actuar neste procedemento xudicial.",
    "A parte demandada contestou á demanda alegando a falta de proba dos feitos",
    "e solicitou a desestimación íntegra das pretensións da parte contraria.",
    "Practicada a proba, quedaron os autos conclusos para ditar a sentenza.",
    "Os feitos probados resultan dos documentos achegados polas dúas partes.",
    "Non consta que a parte demandante cumprise os requisitos esixidos na lei.",
    "En consecuencia, procede estimar parcialmente a demanda presentada.",
]


def _pdf(ruta: Path, paxinas: list) -> Path:
    """`paxinas`: por páxina, lista de (texto, tamaño, y, fonte). O corpo
    (tamaño 11) engádeo cada test cos seus `_corpo()`."""
    documento = fitz.open()
    for liñas in paxinas:
        paxina = documento.new_page()
        for texto, tamano, y, *fonte in liñas:
            paxina.insert_text((72, y), texto, fontsize=tamano, fontname=fonte[0] if fonte else "helv")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    documento.save(str(ruta))
    return ruta


def _corpo(y0: float = 200, n: int = 8, tamano: float = 11) -> list:
    return [(_CORPO[i % len(_CORPO)], tamano, y0 + 16 * i) for i in range(n)]


class _Base(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _titulos(self, paxinas: list) -> list:
        """[(texto, nivel)] segundo `grupos_de_titulos`."""
        documento = fitz.open(str(_pdf(self.dir / "t.pdf", paxinas)))
        return [(" ".join(l.texto for l, _ in g), g[0][1]) for g in titulos_pdf.grupos_de_titulos(documento)]

    def _md(self, paxinas: list) -> str:
        ruta = _pdf(self.dir / "escrito.pdf", paxinas)
        conversor.converter(str(ruta), aforro=False)
        return (self.dir / "escrito.pdf.md").read_text(encoding="utf-8")


class TestDeteccion(_Base):
    def test_titulo_en_letra_maior_detectase(self):
        self.assertEqual(
            self._titulos([[("CONTRATO DE ARRENDAMENTO", 16, 120)] + _corpo()]),
            [("CONTRATO DE ARRENDAMENTO", 1)],
        )

    def test_titulo_un_punto_maior_ca_o_corpo(self):
        # Como o DOG: corpo en 11 pt, seccións en 12 pt.
        self.assertEqual(
            self._titulos([[("VI. ANUNCIOS", 12, 120)] + _corpo()]),
            [("VI. ANUNCIOS", 1)],
        )

    def test_niveis_polo_tamano(self):
        titulos = self._titulos([[("CONTRATO", 20, 110), ("Obxecto do contrato", 15, 150)] + _corpo()])
        self.assertEqual(titulos, [("CONTRATO", 1), ("Obxecto do contrato", 2)])

    def test_tamanos_case_iguais_son_o_mesmo_nivel(self):
        # BOE: a sección en 15 pt e o organismo en 15,7 pt.
        titulos = self._titulos([[("II. AUTORIDADES Y PERSONAL", 15, 110), ("ADMINISTRACIÓN LOCAL", 15.7, 150)] + _corpo()])
        self.assertEqual([nivel for _, nivel in titulos], [1, 1])

    def test_negra_do_tamano_do_corpo_non_e_titulo(self):
        self.assertEqual(self._titulos([[("HECHOS", 11, 120, "hebo")] + _corpo()]), [])

    def test_maiusculas_do_tamano_do_corpo_non_son_titulo(self):
        self.assertEqual(self._titulos([[("PRIMEIRO. DEMANDANTE", 11, 120)] + _corpo()]), [])

    def test_negra_e_maiusculas_nun_documento_con_titulo_real(self):
        titulos = self._titulos([[("ESCRITO DE DEMANDA", 16, 110), ("ANEXO", 11, 140, "hebo")] + _corpo(180)])
        self.assertEqual(titulos, [("ESCRITO DE DEMANDA", 1)])

    def test_todo_nun_tamano_sen_titulos(self):
        self.assertEqual(self._titulos([_corpo(120, 12)]), [])

    def test_titulo_en_varias_liñas_e_un_so(self):
        titulos = self._titulos([[("CONSELLERÍA DE EDUCACIÓN, CIENCIA", 16, 110), ("E FORMACIÓN PROFESIONAL", 16, 128)] + _corpo()])
        self.assertEqual(titulos, [("CONSELLERÍA DE EDUCACIÓN, CIENCIA E FORMACIÓN PROFESIONAL", 1)])

    def test_cabeceira_repetida_en_letra_grande_non_e_titulo(self):
        paxinas = [[("BOLETÍN OFICIAL", 20, 110)] + _corpo(), [("BOLETÍN OFICIAL", 20, 110)] + _corpo()]
        self.assertEqual(self._titulos(paxinas), [])

    def test_membrete_na_marxe_dunha_soa_paxina_non_e_titulo(self):
        self.assertEqual(self._titulos([[("BOLETÍN OFICIAL DEL ESTADO", 20, 36)] + _corpo()]), [])

    def test_numero_de_paxina_grande_non_e_titulo(self):
        self.assertEqual(self._titulos([[("18399", 14, 120)] + _corpo()]), [])

    def test_frase_longa_en_letra_grande_non_e_titulo(self):
        frase = "Resolución do 25 de xuño de 2024 pola que se fai pública a relación de postos de traballo do persoal"
        self.assertEqual(self._titulos([[(frase + ".", 14, 120)] + _corpo()]), [])

    def test_campo_de_formulario_non_e_titulo(self):
        self.assertEqual(self._titulos([[("CENTRO DE DESTINO: SECRETARÍA XERAL", 14, 120)] + _corpo()]), [])

    def test_cabeceira_de_columnas_na_mesma_fila_non_e_titulo(self):
        documento = fitz.open()
        paxina = documento.new_page()
        paxina.insert_text((72, 120), "DOG Núm. 131", fontsize=14)
        paxina.insert_text((300, 120), "Luns, 8 de xullo de 2024", fontsize=14)
        paxina.insert_text((480, 120), "Páx. 40938", fontsize=14)
        for texto, tamano, y in _corpo():
            paxina.insert_text((72, y), texto, fontsize=tamano)
        self.assertEqual(titulos_pdf.grupos_de_titulos(documento), [])

    def test_formula_con_letras_matematicas_non_e_titulo(self):
        self.assertEqual(self._titulos([[("𝑁𝑃𝑃 = 𝑁𝑃𝐶 − 𝑁𝑃𝐼", 14, 120)] + _corpo()]), [])

    def test_mais_dun_cuarto_do_texto_en_letra_grande_sen_titulos(self):
        grande = [(f"Epígrafe curto número {i}", 16, 100 + 24 * i) for i in range(10)]
        self.assertEqual(self._titulos([grande + _corpo(400, 4)]), [])


class TestMarkdownDoConversor(_Base):
    def test_titulo_sae_como_cabeceira_markdown(self):
        md = self._md([[("CONTRATO DE ARRENDAMENTO", 16, 120)] + _corpo()])
        self.assertIn("\n# CONTRATO DE ARRENDAMENTO\n", md)
        self.assertEqual(len(re.findall(r"^#", md, re.MULTILINE)), 1)

    def test_niveis_en_markdown(self):
        md = self._md([[("CONTRATO", 20, 110), ("Obxecto do contrato", 15, 150)] + _corpo()])
        self.assertIn("\n# CONTRATO\n", md)
        self.assertIn("\n## Obxecto do contrato\n", md)

    def test_negra_e_maiusculas_quedan_como_texto(self):
        md = self._md([[("ESCRITO", 16, 110), ("HECHOS", 11, 140, "hebo"), ("PRIMEIRO. DEMANDANTE", 11, 156)] + _corpo(190)])
        self.assertIn("\n# ESCRITO\n", md)
        self.assertNotRegex(md, r"(?m)^#+ (HECHOS|PRIMEIRO)")
        self.assertIn("HECHOS", md)

    def test_titulo_partido_vai_nunha_liña(self):
        md = self._md([[("CONSELLERÍA DE EDUCACIÓN, CIENCIA", 16, 110), ("E FORMACIÓN PROFESIONAL", 16, 128)] + _corpo()])
        self.assertIn("\n# CONSELLERÍA DE EDUCACIÓN, CIENCIA E FORMACIÓN PROFESIONAL\n", md)

    def test_titulos_en_varias_paxinas(self):
        md = self._md([[("PRIMEIRA PARTE", 16, 110)] + _corpo(), [("SEGUNDA PARTE", 16, 110)] + _corpo()])
        self.assertLess(md.index("# PRIMEIRA PARTE"), md.index("<!-- páxina 2 -->"))
        self.assertGreater(md.index("# SEGUNDA PARTE"), md.index("<!-- páxina 2 -->"))

    def test_un_so_md_baixa_un_nivel_os_titulos(self):
        _pdf(self.dir / "caixa" / "a.pdf", [[("CONTRATO DE ARRENDAMENTO", 16, 120)] + _corpo()])
        conversor.converter(str(self.dir / "caixa"), un_so_md=True, aforro=False)
        md = (self.dir / "caixa.md").read_text(encoding="utf-8")
        self.assertIn("\n## CONTRATO DE ARRENDAMENTO\n", md)

    def test_aforro_non_desfai_os_titulos(self):
        ruta = _pdf(self.dir / "escrito.pdf", [[("CONTRATO DE ARRENDAMENTO", 16, 120)] + _corpo()])
        conversor.converter(str(ruta))
        self.assertIn("\n# CONTRATO DE ARRENDAMENTO\n", (self.dir / "escrito.pdf.md").read_text(encoding="utf-8"))

    def test_pdf_sen_titulos_non_cambia(self):
        ruta = _pdf(self.dir / "escrito.pdf", [_corpo(120, 12)])
        texto, contexto = lectura.cargar_documento_estruturado(str(ruta))
        md = copia_md.xerar(contexto, texto)
        self.assertEqual(titulos_pdf.marcar_titulos_md(md, contexto, texto), md)

    def test_anonimizando_o_titulo_sae_anonimizado(self):
        titulo = "DEMANDA DE ANTONIO PÉREZ GARCÍA"
        ruta = _pdf(self.dir / "escrito.pdf", [[(titulo, 16, 120)] + _corpo()])
        conversor.converter(str(ruta), anonimizar=True, rexistro=RexistroCorrespondencias(str(self.dir / "rexistro")), aforro=False)
        md = next(self.dir.glob("*.anonimizado.pdf.md")).read_text(encoding="utf-8")
        self.assertNotIn("ANTONIO", md)
        self.assertNotIn("PÉREZ GARCÍA", md)
        self.assertRegex(md, r"(?m)^# DEMANDA DE ")


class TestAnonimizadorSenCambios(_Base):
    """Os títulos son só do conversor: a copia .md do anonimizador segue igual."""

    def test_copia_md_do_anonimizador_non_leva_titulos(self):
        ruta = _pdf(self.dir / "escrito.pdf", [[("CONTRATO DE ARRENDAMENTO", 16, 120)] + _corpo()])
        texto, contexto = lectura.cargar_documento_estruturado(str(ruta))
        md = copia_md.xerar(contexto, texto)
        self.assertNotRegex(md, r"(?m)^#")
        self.assertIn("CONTRATO DE ARRENDAMENTO", md)

    def test_so_o_conversor_importa_titulos_pdf(self):
        src = Path(__file__).resolve().parent.parent / "src" / "anonimizador"
        usuarios = {p.name for p in src.glob("*.py") if re.search(r"\btitulos_pdf\b", p.read_text(encoding="utf-8"))}
        self.assertEqual(usuarios, {"conversor.py"})


if __name__ == "__main__":
    unittest.main()
