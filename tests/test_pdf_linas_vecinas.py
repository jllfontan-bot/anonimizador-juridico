"""A redacción dunha substitución non pode levar texto das liñas veciñas.

Distorsión real (corpus web BOE, 29/09/2026): a caixa de cada palabra mide
o alto da fonte (14,3 pt) pero as liñas van a 12 pt, e `apply_redactions`
borra calquera carácter que toque o rectángulo -- cada substitución
deixaba en branco tamén anacos da liña de enriba e da de debaixo. E unha
entidade partida en dúas liñas redactábase coa UNIÓN dos seus rectángulos,
que collía as dúas liñas enteiras de lado a lado.

Reprodúcese con PDF sintético (nomes inventados), relendo o PDF de saída.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import fitz  # PyMuPDF

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador.pipeline import anonimizar_e_gardar
from anonimizador.registry import RexistroCorrespondencias

_INTERLINEADO = 12
_TAMANO = 10.5


def _paragrafo(liñas, imaxe_de_fondo=False):
    documento = fitz.open()
    pagina = documento.new_page()
    if imaxe_de_fondo:
        # Plano/mapa: unha imaxe a toda a páxina co texto NATIVO por riba.
        fondo = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 60, 84), False)
        fondo.set_rect(fondo.irect, (235, 240, 235))
        pagina.insert_image(pagina.rect, pixmap=fondo)
    for i, liña in enumerate(liñas):
        pagina.insert_text((72, 100 + i * _INTERLINEADO), liña, fontsize=_TAMANO, fontname="helv")
    return documento


class TestLiñasVeciñas(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _procesar(self, documento):
        entrada = self.dir / "entrada.pdf"
        documento.save(str(entrada))
        with fitz.open(str(entrada)) as d:
            alturas = {round(w[3] - w[1], 1) for w in d[0].get_text("words")}
        # Precondición: as caixas das palabras solápanse coas liñas veciñas.
        self.assertTrue(all(a > _INTERLINEADO for a in alturas), alturas)
        saida = self.dir / "saida.pdf"
        _, informe = anonimizar_e_gardar(
            str(entrada), str(saida), RexistroCorrespondencias(str(self.dir / "rexistro")))
        with fitz.open(str(saida)) as d:
            texto = " ".join(" ".join(p.get_text() for p in d).split())
        return texto, informe

    def test_nome_nunha_liña_non_borra_as_de_enriba_e_debaixo(self):
        texto, informe = self._procesar(_paragrafo([
            "En virtud de la disposición adicional sexagésima segunda de la Ley 11/2020,",
            "de diciembre, comparece don Xoán Páez Veiga para el año 2021 (DA 62",
            "LPGE 2021), se creó una línea de financiación destinada a favorecer la",
        ]))
        self.assertEqual(len(informe["persoas"]), 1)
        for dato in ("Xoán", "Páez", "Veiga"):
            self.assertNotIn(dato, texto)
        for veciño in ("disposición adicional sexagésima segunda de la Ley",
                       "se creó una línea de financiación destinada a favorecer"):
            self.assertIn(veciño, texto)

    def test_nome_partido_en_duas_liñas_non_borra_o_resto_das_liñas(self):
        texto, _ = self._procesar(_paragrafo([
            "Primeira liña de contexto que non se debe tocar en ningún caso.",
            "O informe foi elaborado e asinado por don Xoán Páez",
            "Veiga e remitido ao órgano competente da Xunta de Galicia.",
            "Última liña de contexto que tampouco se debe tocar.",
        ]))
        for dato in ("Xoán", "Páez", "Veiga"):
            self.assertNotIn(dato, texto)
        for veciño in ("O informe foi elaborado e asinado por don",
                       "e remitido ao órgano competente da Xunta de Galicia",
                       "Primeira liña de contexto", "Última liña de contexto"):
            self.assertIn(veciño, texto)

    def test_con_imaxe_de_fondo_tamen_se_recorta(self):
        """Caixetín dun plano (corpus web): a imaxe de fondo abarca toda a
        páxina, pero o dato é texto NATIVO -- non hai tinta en píxeles que
        cubrir, así que as liñas veciñas non se poden levar por diante."""
        texto, _ = self._procesar(_paragrafo([
            "En virtud de la disposición adicional sexagésima segunda de la Ley 11/2020,",
            "de diciembre, comparece don Xoán Páez Veiga para el año 2021 (DA 62",
            "LPGE 2021), se creó una línea de financiación destinada a favorecer la",
        ], imaxe_de_fondo=True))
        for dato in ("Xoán", "Páez", "Veiga"):
            self.assertNotIn(dato, texto)
        for veciño in ("disposición adicional sexagésima segunda de la Ley",
                       "se creó una línea de financiación destinada a favorecer"):
            self.assertIn(veciño, texto)


class TestPalabrasOcrNonPisanAsNativas(unittest.TestCase):
    """Un rectángulo de palabras dun OCR (logotipo, escaneo dentro dunha
    páxina con texto) non pode levar por diante texto NATIVO da mesma liña
    que só o roza (corpus web: o pé "ISSN... Depósito legal..." xunto ao
    logotipo da Xunta)."""

    def _palabra(self, x0, x1, ocr):
        from anonimizador.pdf_estrutura import _PalabraPaxina
        return _PalabraPaxina(0, 1, (x0, 100.0, x1, 112.0), 0, ocr)

    def test_recorta_polo_lado_que_roza_a_nativa(self):
        from anonimizador.pdf_estrutura import _sen_invadir_nativas
        propia = self._palabra(40, 200, True)
        nativa = self._palabra(190, 300, False)
        recortado = _sen_invadir_nativas(fitz.Rect(propia.rect), 0, [propia, nativa], frozenset({id(propia)}))
        self.assertLess(recortado.x1, 190)
        self.assertEqual(recortado.x0, 40)

    def test_nativa_dentro_do_rectangulo_non_se_recorta(self):
        from anonimizador.pdf_estrutura import _sen_invadir_nativas
        propia = self._palabra(40, 200, True)
        nativa = self._palabra(60, 180, False)  # o mesmo texto que o OCR lía: duplicado
        recortado = _sen_invadir_nativas(fitz.Rect(propia.rect), 0, [propia, nativa], frozenset({id(propia)}))
        self.assertEqual(tuple(recortado), (40, 100, 200, 112))


class TestEspazoTipografico(unittest.TestCase):
    """"b)<EM SPACE>Actividades": MuPDF devolve UNHA palabra, e redactar
    "Actividades" borraba tamén o marcador da lista (corpus web, BOE)."""

    def test_parte_a_palabra_e_o_rectangulo(self):
        from anonimizador.pdf_estrutura import _partes_por_espazos_tipograficos
        partes = _partes_por_espazos_tipograficos("b)\u2003Actividades", (0.0, 0.0, 140.0, 10.0), 0, [])
        self.assertEqual([t for t, _ in partes], ["b)", "Actividades"])
        (_, r1), (_, r2) = partes
        self.assertLessEqual(r1[2], r2[0])
        self.assertEqual((r1[0], r2[2]), (0.0, 140.0))

    def test_usa_as_caixas_exactas_das_letras(self):
        from anonimizador.pdf_estrutura import _partes_por_espazos_tipograficos
        letras = [
            {"c": "b", "bbox": (0, 0, 5, 10)}, {"c": ")", "bbox": (5, 0, 9, 10)},
            {"c": "\u2003", "bbox": (9, 0, 19, 10)},
            {"c": "A", "bbox": (19, 0, 27, 10)}, {"c": "c", "bbox": (27, 0, 33, 10)},
        ]
        partes = _partes_por_espazos_tipograficos("b)\u2003Ac", (0.0, 0.0, 33.0, 10.0), 0, letras)
        self.assertEqual(partes, [("b)", (0.0, 0.0, 9.0, 10.0)), ("Ac", (19.0, 0.0, 33.0, 10.0))])

    def test_palabra_normal_non_se_toca(self):
        from anonimizador.pdf_estrutura import _partes_por_espazos_tipograficos
        self.assertEqual(
            _partes_por_espazos_tipograficos("Actividades", (1.0, 2.0, 3.0, 4.0), 0, []),
            [("Actividades", (1.0, 2.0, 3.0, 4.0))])


class TestBordosDeTaboaConservanse(unittest.TestCase):
    """O tachado dunha cela non pode borrar os bordos da táboa (corpus web:
    formularios cos recadros arredor das celas redactadas desaparecidos)."""

    def test_bordos_da_cela_redactada_seguen_no_pdf(self):
        dir_ = Path(tempfile.mkdtemp())
        try:
            documento = fitz.open()
            pagina = documento.new_page()
            # Celda estreita: o recadro é de tamaño "comparable" ao texto, que é
            # o caso no que o tachado ampliado o levaba por diante.
            for i, texto in enumerate(["Concepto", "don Xoán Páez Veiga", "Total"]):
                celda = fitz.Rect(72, 100 + i * 24, 200, 124 + i * 24)
                pagina.draw_rect(celda, color=(0, 0, 0), width=0.5)
                pagina.insert_text((78, 116 + i * 24), texto, fontsize=10, fontname="helv")
            entrada = dir_ / "e.pdf"
            documento.save(str(entrada))
            antes = len([d for d in fitz.open(str(entrada))[0].get_drawings() if d.get("color") == (0.0, 0.0, 0.0)])
            saida = dir_ / "s.pdf"
            anonimizar_e_gardar(str(entrada), str(saida), RexistroCorrespondencias(str(dir_ / "rex")))
            with fitz.open(str(saida)) as d:
                despois = len([x for x in d[0].get_drawings() if x.get("color") == (0.0, 0.0, 0.0)])
                self.assertNotIn("Xoán", d[0].get_text())
            self.assertEqual(antes, 3)
            self.assertEqual(despois, antes)
        finally:
            shutil.rmtree(dir_, ignore_errors=True)


class TestReixaDeTaboaNonPasaPorOcr(unittest.TestCase):
    """Formulario do DOG (corpus web): unha táboa debuxada con moitos trazos
    pequenos parece "texto vectorizado" (A25), o OCR lía a reixa coma lixo
    ("AAA IEA III") e o NER tomábao por persoas. Se a zona xa ten texto
    nativo dentro, non é un nome vectorizado."""

    def test_zona_de_trazos_con_texto_nativo_non_se_le_por_ocr(self):
        from anonimizador.pdf_estrutura import _extraer_paxina
        documento = fitz.open()
        pagina = documento.new_page()
        cabeceiras = ["IMPORTE DE", "DATA DE", "COTA DE", "MESES", "CUSTO", "TOTAL"]
        for c, texto in enumerate(cabeceiras):
            x = 72 + c * 70
            pagina.insert_text((x + 4, 118), texto, fontsize=6, fontname="helv")
            for k in range(0, 70, 3):  # reixa de trazos curtos, coma a dos formularios
                pagina.draw_line((x + k, 108), (x + k + 2, 108), width=0.3)
                pagina.draw_line((x + k, 124), (x + k + 2, 124), width=0.3)
            for k in range(108, 124, 3):
                pagina.draw_line((x, k), (x, k + 2), width=0.3)
        paxina = _extraer_paxina(pagina)
        self.assertFalse(any(p.ocr for p in paxina.palabras), paxina.texto)
        self.assertIn("IMPORTE", paxina.texto)


class TestCodigoEnTextoDiminuto(unittest.TestCase):
    """Lenda dun plano a 1,5 pt (corpus web): o código inseríase a 4 pt e
    desbordaba sobre as celas veciñas."""

    def test_codigo_non_moito_maior_co_texto_orixinal(self):
        dir_ = Path(tempfile.mkdtemp())
        try:
            documento = fitz.open()
            pagina = documento.new_page()
            pagina.insert_text((72, 100), "Autor: don Xoán Páez Veiga, enxeñeiro", fontsize=1.5, fontname="helv")
            pagina.insert_text((72, 500), "Comparece don Xoán Páez Veiga en Lugo.", fontsize=11, fontname="helv")
            entrada, saida = dir_ / "e.pdf", dir_ / "s.pdf"
            documento.save(str(entrada))
            anonimizar_e_gardar(str(entrada), str(saida), RexistroCorrespondencias(str(dir_ / "rex")))
            with fitz.open(str(saida)) as d:
                codigos = [w for w in d[0].get_text("words") if w[4].startswith("PERSOA_")]
            alturas = sorted(round(w[3] - w[1], 1) for w in codigos)
            self.assertEqual(len(alturas), 2)
            self.assertLess(alturas[0], 3.0)   # o da lenda diminuta
            self.assertGreater(alturas[1], 8.0)  # o do texto normal segue lexible
        finally:
            shutil.rmtree(dir_, ignore_errors=True)


class TestUrlNonEsTextoRoto(unittest.TestCase):
    """O pé de TODAS as páxinas do DOG leva unha URL de 44 caracteres; a regra
    A20 ("ningún espazo en 40 caracteres = texto roto") tomaba as 322 páxinas
    do corpus por lixo e facía OCR da páxina enteira (ruído -> persoas falsas)."""

    def test_url_longa_non_marca_a_paxina_coma_rota(self):
        from anonimizador.pdf_estrutura import _texto_semella_real
        texto = ("Esta orde terá vixencia temporal para o curso académico, desde o día 1 de setembro. " * 3
                 + "ISSN1130-9229 Depósito legal C.494-1998 https://www.xunta.gal/diario-oficial-galicia")
        self.assertTrue(_texto_semella_real(texto, False))

    def test_lixo_de_glifos_segue_detectandose(self):
        from anonimizador.pdf_estrutura import _texto_semella_real
        self.assertFalse(_texto_semella_real("Ho#ghpdqgdqwh#Mxdq#Shuh}#frq#GQL#6637;;;;#pdqlilhvwd#txh#hvwd", True))


if __name__ == "__main__":
    unittest.main()


class TestPuntoERaiaNaSinatura(unittest.TestCase):
    """Sinatura do BOE (corpus web lote 2, 30/09/2026): "Martínez.–El" é unha
    soa palabra para PyMuPDF e tapar o apelido levaba ".–El" consigo."""

    def test_raia_e_artigo_seguen_no_pdf(self):
        directorio = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directorio, True)
        documento = fitz.open()
        pagina = documento.new_page()
        # "helv" non ten a raia (sae "·"): fonte embebida de PyMuPDF que si a ten.
        pagina.insert_font(fontname="F0", fontbuffer=fitz.Font("cjk").buffer)
        pagina.insert_text((72, 100), "Madrid, 28 de abril de 2026.–El Presidente de la", fontsize=_TAMANO, fontname="F0")
        pagina.insert_text((72, 112), "Comisión, Xoán Páez Veiga.–El Secretario Primero de la Comisión,", fontsize=_TAMANO, fontname="F0")
        entrada, saida = directorio / "entrada.pdf", directorio / "saida.pdf"
        documento.save(str(entrada))
        anonimizar_e_gardar(str(entrada), str(saida), RexistroCorrespondencias(str(directorio / "rexistro")))
        with fitz.open(str(saida)) as d:
            texto = d[0].get_text()
        self.assertNotIn("Veiga", texto)
        self.assertIn("–El Secretario Primero de la Comisión", texto)


class TestLiñaXustificadaPalabraAPalabra(unittest.TestCase):
    """BOE-A-2026-13616 (lectura de Claude, 30/09/2026): nunha liña
    xustificada PyMuPDF dá unha "liña" por palabra e o último apelido
    quedaba á vista ("Itziar Romanillos Camarasaltas")."""

    def test_mesma_liña_visual_une_con_espazo(self):
        from anonimizador import pdf_estrutura as pe
        a = ("Romanillos", 6, 6, (202.3, 323.6, 254.5, 337.9), 0)
        b = ("Camarasaltas.", 6, 7, (265.6, 323.6, 326.7, 337.9), 0)
        texto, _ = pe._ensamblar_texto([a, b])
        self.assertEqual(texto, "Romanillos Camarasaltas.")
        outro_bloque = ("GESTIÓN", 7, 0, (265.6, 323.6, 326.7, 337.9), 0)
        self.assertEqual(pe._ensamblar_texto([a, outro_bloque])[0], "Romanillos\nGESTIÓN")
