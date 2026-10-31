"""Páxinas web gardadas (.html, .htm) a Markdown, SEN anonimizar
(`formatos/paxinas_html.py`, fase 4 do conversor a .md). Pensado para as
páxinas do BOE e do DOG gardadas."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador.formatos import paxinas_html


_PAXINA = """<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><title>BOE-A-2026-1 Ley de ejemplo</title>
<meta name="author" content="Autor Meta"><script>var seguimento = "TRACKING";</script>
<style>.x { color: red }</style></head>
<body>
<nav><ul><li><a href="/inicio">MENU-INICIO</a></li><li><a href="/buscar">MENU-BUSCAR</a></li></ul></nav>
<div id="cabecera" role="banner">BANNER-WEB</div>
<main>
<h1>Ley de ejemplo</h1>
<p class="parrafo">Artículo 1. <strong>Objeto</strong> de la ley, según el <a href="https://www.boe.es/eli/es/l/2026/1">texto oficial</a>.</p>
<h2>Capítulo I</h2>
<ul><li>Primer punto</li><li>Segundo punto<ul><li>Subpunto</li></ul></li></ul>
<ol><li>Uno</li><li>Dos</li></ol>
<table><tr><th>Concepto</th><th>Importe</th></tr><tr><td>Material</td><td>12 | 3</td></tr></table>
</main>
<footer>PIE-WEB</footer>
<!-- comentario escondido: SEGREDO-HTML -->
<script>document.write("OUTRO-SCRIPT")</script>
</body></html>"""


class TestHtml(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def md(self, html: str, nome="p.html", codificacion="utf-8") -> str:
        ruta = self.dir / nome
        ruta.write_bytes(html.encode(codificacion))
        return paxinas_html.a_markdown(str(ruta))

    def test_conserva_titulos_listas_taboas_e_ligazons(self):
        md = self.md(_PAXINA)
        self.assertIn("# Ley de ejemplo", md)
        self.assertIn("## Capítulo I", md)
        self.assertIn("- Primer punto", md)
        self.assertIn("- Segundo punto", md)
        self.assertIn("  - Subpunto", md)
        self.assertIn("1. Uno", md)
        self.assertIn("2. Dos", md)
        self.assertIn("**Objeto**", md)
        self.assertIn("[texto oficial](https://www.boe.es/eli/es/l/2026/1)", md)
        self.assertIn("| Concepto | Importe |", md)
        self.assertIn("| Material | 12 \\| 3 |", md)

    def test_quita_menus_scripts_estilos_pes_e_comentarios(self):
        md = self.md(_PAXINA)
        for lixo in ("MENU-INICIO", "MENU-BUSCAR", "BANNER-WEB", "PIE-WEB", "TRACKING",
                     "OUTRO-SCRIPT", "color: red", "SEGREDO-HTML", "Autor Meta"):
            self.assertNotIn(lixo, md)

    def test_so_o_titulo_da_cabeceira_cando_non_hai_h1(self):
        md = self.md("<html><head><title>Resolución de 1 de enero</title></head>"
                     "<body><p>Texto da resolución.</p></body></html>")
        self.assertTrue(md.startswith("# Resolución de 1 de enero"))
        self.assertIn("Texto da resolución.", md)

    def test_non_repite_o_titulo_se_hai_h1(self):
        md = self.md("<html><head><title>Título da pestana</title></head>"
                     "<body><h1>Título da páxina</h1><p>x</p></body></html>")
        self.assertNotIn("Título da pestana", md)

    def test_elementos_ocultos_non_saen(self):
        md = self.md("<body><p>Visible</p><p style='display:none'>OCULTO-ESTILO</p>"
                     "<div hidden>OCULTO-ATRIBUTO</div><p style='visibility: hidden'>OCULTO-VIS</p>"
                     "<noscript>OCULTO-NOSCRIPT</noscript><input type='hidden' value='OCULTO-INPUT'>"
                     "<p title='OCULTO-TITLE' data-x='OCULTO-DATA'>Co atributo</p></body>")
        self.assertIn("Visible", md)
        self.assertIn("Co atributo", md)
        for oculto in ("OCULTO-ESTILO", "OCULTO-ATRIBUTO", "OCULTO-VIS", "OCULTO-NOSCRIPT",
                       "OCULTO-INPUT", "OCULTO-TITLE", "OCULTO-DATA"):
            self.assertNotIn(oculto, md)

    def test_imaxes_marcanse_sen_arrastrar_a_url_nin_base64(self):
        md = self.md("<body><p>Antes <img src='data:image/png;base64,AAAA' alt='Plano da parcela'> "
                     "e <img src='x.png'> despois</p></body>")
        self.assertIn("[imaxe: Plano da parcela]", md)
        self.assertNotIn("base64", md)
        self.assertNotIn("x.png", md)

    def test_alt_que_e_un_nome_de_arquivo_non_e_texto_alternativo(self):
        md = self.md("<body><p>Texto <img src='a.png' alt='IMG_2043_Ana_Pena.jpg'></p></body>")
        self.assertNotIn("[imaxe", md)
        self.assertNotIn("Ana_Pena", md)

    def test_imaxes_sen_alt_omitense_e_avisase_do_total(self):
        ruta = self.dir / "p.html"
        ruta.write_text("<body><p>Texto <img src='a.png'> <img src='b.png' alt=''> "
                        "<img src='c.png' alt='Plano'></p></body>", encoding="utf-8")
        c = paxinas_html.convertir(str(ruta))
        self.assertEqual(c.markdown.count("[imaxe"), 1)
        self.assertEqual(len(c.avisos), 1)
        self.assertIn("2", c.avisos[0])

    def test_liñas_do_fonte_unense_nun_so_paragrafo(self):
        md = self.md("<body><p>Visto o expediente,\n   resolvo o\nseguinte.</p>"
                     "<pre>codigo\n  con sangria</pre></body>")
        self.assertIn("Visto o expediente, resolvo o seguinte.", md)
        self.assertIn("codigo\n  con sangria", md)

    def test_asteriscos_e_guions_baixos_do_texto_non_se_escapan(self):
        md = self.md("<body><p>Nota (*) e art_5 con 2 * 3</p></body>")
        self.assertIn("Nota (*) e art_5 con 2 * 3", md)

    def test_ligazons_internas_e_javascript_quedan_so_co_texto(self):
        md = self.md("<body><p><a href='#nota1'>nota 1</a> <a href='javascript:void(0)'>abrir</a> "
                     "<a href='https://x.es/a'>fóra</a></p></body>")
        self.assertIn("nota 1", md)
        self.assertIn("abrir", md)
        self.assertNotIn("(#nota1)", md)
        self.assertNotIn("javascript", md)
        self.assertIn("[fóra](https://x.es/a)", md)

    def test_prefire_main_se_hai_un(self):
        md = self.md("<body><div>RUIDO-FORA</div><main><p>Contido principal</p></main></body>")
        self.assertIn("Contido principal", md)
        self.assertNotIn("RUIDO-FORA", md)

    def test_boe_textoxslt(self):
        md = self.md("<body><div id='menu'>MENU-BOE</div><div id='textoxslt'>"
                     "<h3 class='capitulo'>CAPÍTULO I</h3><p class='articulo'>Artículo 1. Objeto.</p>"
                     "<p class='parrafo'>Texto del artículo.</p></div><div id='pie'>PIE-BOE</div></body>")
        self.assertIn("### CAPÍTULO I", md)
        self.assertIn("Artículo 1. Objeto.", md)
        self.assertNotIn("MENU-BOE", md)
        self.assertNotIn("PIE-BOE", md)

    def test_cabeceira_e_pe_de_dentro_dun_artigo_conservanse(self):
        md = self.md("<body><header>CAB-PAXINA</header><article><header><h2>Título interior</h2></header>"
                     "<p>Corpo</p><footer>Fonte: DOG</footer></article><article><p>Outro</p></article></body>")
        self.assertNotIn("CAB-PAXINA", md)
        self.assertIn("Título interior", md)
        self.assertIn("Fonte: DOG", md)
        self.assertIn("Outro", md)

    def test_taboa_de_maquetacion_dunha_celda_non_é_taboa(self):
        md = self.md("<body><table><tr><td><p>Primeiro parágrafo</p><p>Segundo parágrafo</p></td></tr></table></body>")
        self.assertIn("Primeiro parágrafo", md)
        self.assertIn("Segundo parágrafo", md)
        self.assertNotIn("|", md)

    def test_taboa_aniñada_non_duplica_texto(self):
        md = self.md("<body><table><tr><th>A</th><th>B</th></tr>"
                     "<tr><td>1</td><td><table><tr><td>interior</td><td>dato</td></tr></table></td></tr></table></body>")
        self.assertEqual(md.count("interior"), 1)
        self.assertIn("| A | B |", md)

    def test_colspan_enche_columnas(self):
        md = self.md("<body><table><tr><th colspan='2'>Título largo</th><th>C</th></tr>"
                     "<tr><td>1</td><td>2</td><td>3</td></tr></table></body>")
        self.assertIn("| Título largo |  | C |", md)
        self.assertIn("| 1 | 2 | 3 |", md)

    def test_sen_cabeceira_a_primeira_fila_fai_de_cabeceira(self):
        md = self.md("<body><table><tr><td>a</td><td>b</td></tr><tr><td>1</td><td>2</td></tr></table></body>")
        self.assertIn("| a | b |", md)
        self.assertIn("| 1 | 2 |", md)

    def test_codificacion_latin1_declarada(self):
        html = ("<html><head><meta http-equiv='Content-Type' content='text/html; charset=iso-8859-1'>"
                "</head><body><p>Año y niño: Muñiz</p></body></html>")
        self.assertIn("Año y niño: Muñiz", self.md(html, codificacion="latin-1"))

    def test_extension_htm_e_formatos(self):
        self.assertEqual(paxinas_html.FORMATOS, (".html", ".htm"))

    def test_baleiro(self):
        self.assertEqual(self.md("").strip(), "")

    def test_non_deixa_mais_dunha_liña_baleira_seguida(self):
        md = self.md("<body><p>a</p><br><br><br><p>b</p><div></div><div></div><p>c</p></body>")
        self.assertNotIn("\n\n\n", md)


if __name__ == "__main__":
    unittest.main()
