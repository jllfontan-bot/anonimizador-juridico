"""Títulos estruturais en PDF (Anexo, Capítulo, Artigo...) en negra ou
maiúsculas ao tamaño do corpo (fase 5, ampliación).

Con PDF REAIS do BOE e do DOG, nunca sintéticos: o corpus de medición non vai
ao repositorio, así que estes tests lense dende alí (pendrive ou SSD) e
sáltanse se non está. Mostra do que hai en cada un, medida o 31/10/2026:

- BOE-A-2026-4219 (convenio): `CAPÍTULO I`... en maiúsculas; `Artículo 1. Objeto.`
  en letra normal co nome en cursiva.
- BOE-A-2026-18411 e BOE-A-2025-21301: `ANEXO I` e `ANEXO II` en negra.
- BOE-A-2026-13711: unha liña en negra que COMEZA por «Artículo 48.4 de la Ley de
  Montes» (a mención dunha lei, non un título).
- BOE-A-2025-25943: mencións de «anexo I» e «artículo 89.3» en medio de frases.
- BOE-A-2026-3005: `Artículo N. Título.` en cursiva (o do BOE); BOE-A-2026-13002 e
  os do DOG AnuncioG0761-290726-0002, AnuncioG0767-270625-0001 (Artigo, Artigo único).
"""

import glob
import os
import re
import tempfile
import unittest
from pathlib import Path

import fitz  # PyMuPDF

os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")

from anonimizador import conversor, titulos_pdf  # noqa: E402
from anonimizador.registry import RexistroCorrespondencias  # noqa: E402

_RAICES = (
    "/Volumes/PENDRIVE/_CLAUDE_ARCHIVO_PORTATIL/proyectos/anonimizador-xuridico/corpus_web_orixinais/*/*/{}.pdf",
    "/Volumes/ext SSD MAC/_COPIAS_LOCALES/proyectos/anonimizador-xuridico/corpus_web*/docs/*/{}.pdf",
)


def _corpus(nome: str) -> str | None:
    for raiz in _RAICES:
        achados = sorted(glob.glob(raiz.format(nome)))
        if achados:
            return achados[0]
    return None


def _titulos(nome: str) -> list:
    """[(texto, nivel)] de `grupos_de_titulos` sobre o PDF real `nome`."""
    ruta = _corpus(nome)
    if ruta is None:
        raise unittest.SkipTest(f"{nome}.pdf non está no corpus (pendrive ou SSD)")
    return [(" ".join(l.texto for l, _ in g), g[0][1]) for g in titulos_pdf.grupos_de_titulos(fitz.open(ruta))]


class TestEstruturais(unittest.TestCase):
    def test_capitulos_en_maiusculas(self):
        titulos = _titulos("BOE-A-2026-4219")
        capitulos = [(t, n) for t, n in titulos if t.startswith("CAPÍTULO")]
        romanos = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII")
        self.assertEqual([t for t, _ in capitulos], [f"CAPÍTULO {r}" for r in romanos])

    def test_baixan_un_nivel_dos_titulos_por_tamano(self):
        titulos = _titulos("BOE-A-2026-4219")
        por_tamano = [n for t, n in titulos if not t.startswith(("CAPÍTULO", "ANEXO", "Artículo", "Disposición"))]
        niveis = {t.split()[0]: n for t, n in titulos if t.startswith(("CAPÍTULO", "ANEXO"))}
        self.assertEqual(niveis["ANEXO"], max(por_tamano) + 1)
        self.assertEqual(niveis["CAPÍTULO"], niveis["ANEXO"] + 1)  # o anexo vai por riba do capítulo
        artigos = {n for t, n in titulos if t.startswith("Artículo")}
        self.assertEqual(artigos, {niveis["CAPÍTULO"] + 1})  # e o capítulo por riba do artigo

    def test_anexos_en_negra(self):
        titulos = [t for t, _ in _titulos("BOE-A-2026-18411")]
        self.assertIn("ANEXO I", titulos)
        self.assertIn("ANEXO II", titulos)

    def test_mencion_dunha_lei_en_negra_non_e_titulo(self):
        # «Artículo 48.4 de la Ley de Montes» en negra: segue «de la Ley...», é unha frase.
        titulos = [t for t, _ in _titulos("BOE-A-2026-13711")]
        self.assertFalse([t for t in titulos if t.startswith("Artículo")], titulos)

    def test_mencions_en_medio_de_frase_non_son_titulo(self):
        titulos = [t for t, _ in _titulos("BOE-A-2025-25943")]
        self.assertFalse([t for t in titulos if re.match(r"(?i)(art[ií]culo|anexo) ", t) and t != t.upper()], titulos)
        self.assertEqual([t for t in titulos if t.upper().startswith("ANEXO")], ["ANEXO I", "ANEXO II", "ANEXO III"])

    def test_artigo_en_cursiva_detectase_por_defecto(self):
        titulos = _titulos("BOE-A-2026-3005")
        artigos = [(t, n) for t, n in titulos if t.startswith("Artículo")]
        capitulos = {n for t, n in titulos if t.startswith("CAPÍTULO")}
        self.assertGreaterEqual(len(artigos), 10)
        self.assertEqual({n for _, n in artigos}, {max(capitulos) + 1})
        # O título partido en dúas liñas sae completo, nunha soa.
        self.assertIn("Artículo 16. Coordinación con equipos de medios adecuados de solución de controversias.",
                      [t for t, _ in artigos])

    def test_artigo_en_cursiva_co_interruptor_apagado(self):
        antes = titulos_pdf._ADMITE_CURSIVA
        titulos_pdf._ADMITE_CURSIVA = False
        try:
            titulos = _titulos("BOE-A-2026-3005")
        finally:
            titulos_pdf._ADMITE_CURSIVA = antes
        self.assertFalse([t for t, _ in titulos if t.startswith("Artículo")], titulos)

    def test_artigos_do_dog_en_galego(self):
        titulos = [t for t, _ in _titulos("AnuncioG0761-290726-0002_gl")]
        self.assertEqual([t for t in titulos if t.startswith("Artigo")], ["Artigo 1. Cesamentos.", "Artigo 2. Nomeamentos"])

    def test_artigo_unico_do_dog(self):
        titulos = [t for t, _ in _titulos("AnuncioG0767-270625-0001_gl")]
        self.assertEqual([t for t in titulos if t.startswith("Artigo")], ["Artigo único. Nomeamento de vogal"])

    def test_mencion_dun_artigo_nunha_frase_non_e_titulo_con_cursiva(self):
        # «artículo 48 del mencionado reglamento.»: empeza en minúscula (frase partida).
        titulos = [t for t, _ in _titulos("BOE-A-2026-18516")]
        self.assertFalse([t for t in titulos if re.match(r"(?i)art[ií]culo", t)], titulos)

    def test_demasiado_texto_como_titulo_non_marca_estruturais(self):
        antes = titulos_pdf._FRACCION_MAXIMA
        titulos_pdf._FRACCION_MAXIMA = 0.0001
        try:
            titulos = _titulos("BOE-A-2026-4219")
        finally:
            titulos_pdf._FRACCION_MAXIMA = antes
        self.assertFalse([t for t, _ in titulos if t.startswith("CAPÍTULO")])


class TestMarkdownEstruturais(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)

    def _copia(self, nome: str) -> Path:
        ruta = _corpus(nome)
        if ruta is None:
            raise unittest.SkipTest(f"{nome}.pdf non está no corpus (pendrive ou SSD)")
        destino = self.dir / f"{nome}.pdf"
        destino.write_bytes(Path(ruta).read_bytes())
        return destino

    def test_anexos_no_md_do_boe(self):
        conversor.converter(str(self._copia("BOE-A-2025-21301")), aforro=False)
        md = (self.dir / "BOE-A-2025-21301.pdf.md").read_text(encoding="utf-8")
        self.assertRegex(md, r"(?m)^#{2,} ANEXO I$")
        self.assertRegex(md, r"(?m)^#{2,} ANEXO II$")

    def test_un_so_md_baixa_un_nivel_o_anexo(self):
        carpeta = self.dir / "caixa"
        carpeta.mkdir()
        (carpeta / "a.pdf").write_bytes(self._copia("BOE-A-2025-21301").read_bytes())
        conversor.converter(str(carpeta), un_so_md=True, aforro=False)
        md = (self.dir / "caixa.md").read_text(encoding="utf-8")
        self.assertRegex(md, r"(?m)^#{3,} ANEXO I$")

    def test_artigos_no_md_do_boe(self):
        conversor.converter(str(self._copia("BOE-A-2026-13002")), aforro=False)
        md = (self.dir / "BOE-A-2026-13002.pdf.md").read_text(encoding="utf-8")
        self.assertRegex(md, r"(?m)^#{2,} Artículo 1\. Veda\.$")
        self.assertRegex(md, r"(?m)^#{2,} Artículo 2\. Régimen sancionador\.$")
        self.assertRegex(md, r"(?m)^#{2,} Disposición final primera\. Título competencial\.$")

    def test_anonimizando_o_anexo_segue_a_ser_titulo(self):
        ruta = self._copia("BOE-A-2025-21301")
        conversor.converter(str(ruta), anonimizar=True, rexistro=RexistroCorrespondencias(str(self.dir / "rexistro")), aforro=False)
        md = next(self.dir.glob("*.anonimizado.pdf.md")).read_text(encoding="utf-8")
        self.assertRegex(md, r"(?m)^#{2,} ANEXO I$")


if __name__ == "__main__":
    unittest.main()
