"""Aforro para IA (fase 3 do conversor a .md): funcións puras sobre o
Markdown de `copia_md.xerar` -- cabeceiras e pés repetidos, unir liñas
partidas, espazos, troceado e estimación de tokens.
"""

import os
import re
import shutil
import tempfile
import textwrap
import unittest
from collections import Counter
from pathlib import Path

import fitz  # PyMuPDF

from anonimizador import aforro_ia, copia_md, idioma, lectura

LOREM = (
    "A administración educativa disporá os medios necesarios para que todo o alumnado acade o máximo "
    "desenvolvemento persoal, intelectual, social e emocional, así como os obxectivos establecidos con "
    "carácter xeral nesta lei e na normativa de desenvolvemento que resulte de aplicación en cada caso"
)


def setUpModule():
    global _IDIOMA_ANTES
    _IDIOMA_ANTES = os.environ.get(idioma.VARIABLE)
    os.environ[idioma.VARIABLE] = "gl"


def tearDownModule():
    if _IDIOMA_ANTES is None:
        os.environ.pop(idioma.VARIABLE, None)
    else:
        os.environ[idioma.VARIABLE] = _IDIOMA_ANTES


def marca(n: int, lingua: str = "gl") -> str:
    return f"<!-- {idioma.t('copia_md.paxina', lingua, n=n)} -->"


def paxina(n: int, corpo: str, lingua: str = "gl") -> str:
    return marca(n, lingua) + "\n\n" + corpo


def documento(corpos: list, lingua: str = "gl") -> str:
    return "\n\n".join(paxina(i + 1, c, lingua) for i, c in enumerate(corpos)) + "\n"


def parrafo(texto: str, ancho: int = 78) -> str:
    return textwrap.fill(texto, ancho)


def letras(texto: str) -> Counter:
    """Letras e díxitos das liñas que non son comentarios (sen espazos nin
    guións): o que non se pode perder ao aforrar."""
    liñas = [l for l in texto.split("\n") if not l.lstrip().startswith("<!--")]
    return Counter(c for c in "".join(liñas) if c.isalnum())


def so(texto: str, **opcions) -> str:
    """Só as opcións pedidas; o resto, apagado."""
    base = dict(quitar_repetidas=False, unir_liñas=False, limpar_espazos=False)
    base.update(opcions)
    return aforro_ia.aforrar(texto, base).texto


def con_cabeceira(n_paxinas: int = 6, cabeceira=("DOG Núm. 165", "Martes, 1 de setembro de 2026"),
                  pe=("CVE-DOG: 2xlrgth5-ejn3", "Diario Oficial de Galicia"), contador=lambda n: f"Páx. {47406 + n}"):
    corpos = []
    for n in range(1, n_paxinas + 1):
        corpo = "\n".join(
            list(cabeceira) + [contador(n)] + [f"Texto único da páxina {n} sobre o asunto {n * 7}."]
            + [f"Segunda liña propia da páxina {n}."] + list(pe)
        )
        corpos.append(corpo)
    return documento(corpos)


class TestCabeceirasRepetidas(unittest.TestCase):
    def test_cabeceira_e_pe_repetidos_escribense_unha_vez(self):
        md = con_cabeceira()
        saida = so(md, quitar_repetidas=True)
        for liña in ("DOG Núm. 165", "Martes, 1 de setembro de 2026", "CVE-DOG: 2xlrgth5-ejn3",
                     "Diario Oficial de Galicia"):
            self.assertEqual(saida.count(liña), 1, liña)
        # ... ao principio, antes da primeira páxina
        self.assertLess(saida.index("DOG Núm. 165"), saida.index(marca(1)))
        self.assertLess(saida.index("Diario Oficial de Galicia"), saida.index(marca(1)))

    def test_o_texto_propio_de_cada_paxina_queda(self):
        saida = so(con_cabeceira(), quitar_repetidas=True)
        for n in range(1, 7):
            self.assertIn(f"Texto único da páxina {n} sobre o asunto {n * 7}.", saida)
            self.assertIn(f"Segunda liña propia da páxina {n}.", saida)

    def test_contadores_de_paxina_recoñécense_aínda_que_cambien(self):
        md = con_cabeceira(contador=lambda n: f"Páx. {47406 + n}")
        self.assertNotIn("Páx.", so(md, quitar_repetidas=True))
        md = con_cabeceira(contador=lambda n: f"Página {n} de 6")
        self.assertNotIn("Página", so(md, quitar_repetidas=True))
        md = con_cabeceira(contador=lambda n: f"- {n} -")
        self.assertNotIn("- 1 -", so(md, quitar_repetidas=True))
        md = con_cabeceira(contador=lambda n: str(n))
        saida = so(md, quitar_repetidas=True)
        self.assertNotIn("\n3\n", saida)

    def test_unha_frase_que_remata_en_paxina_n_non_é_un_contador(self):
        corpos = [f"Cab\nUnha frase longa do corpo que remata\nna páxina {n}\nPé" for n in range(1, 7)]
        saida = so(documento(corpos), quitar_repetidas=True)
        for n in range(1, 7):
            self.assertIn(f"\nna páxina {n}\n", saida)

    def test_contador_con_texto_antes_na_mesma_liña(self):
        md = con_cabeceira(contador=lambda n: f"Sec. II.B. Pág. {118030 + n}")
        self.assertNotIn("Pág.", so(md, quitar_repetidas=True))
        md = con_cabeceira(contador=lambda n: f"Sec. V-B. Pág. {63780 + n}")
        self.assertNotIn("Pág.", so(md, quitar_repetidas=True))

    def test_as_marcas_de_paxina_conservanse_todas_e_en_orde(self):
        saida = so(con_cabeceira(), quitar_repetidas=True)
        self.assertEqual(re.findall(r"<!-- páxina (\d+) -->", saida), [str(n) for n in range(1, 7)])

    def test_marcas_en_castelan(self):
        corpos = [f"Cabeceira común\nCorpo {n} único\nPé común" for n in range(1, 5)]
        saida = so(documento(corpos, "es"), quitar_repetidas=True)
        self.assertEqual(saida.count("Cabeceira común"), 1)
        self.assertEqual(saida.count("Pé común"), 1)
        self.assertEqual(re.findall(r"<!-- página (\d+) -->", saida), ["1", "2", "3", "4"])

    def test_non_se_quita_se_non_aparece_na_maioría_das_páxinas(self):
        corpos = [f"Corpo {n}\nLiña en poucas páxinas" if n <= 2 else f"Corpo {n}" for n in range(1, 7)]
        saida = so(documento(corpos), quitar_repetidas=True)
        self.assertEqual(saida.count("Liña en poucas páxinas"), 2)

    def test_unha_liña_do_corpo_con_número_distinto_non_é_contador(self):
        corpos = [f"Artigo {n}\nCorpo {n} único" for n in range(1, 7)]
        saida = so(documento(corpos), quitar_repetidas=True)
        for n in range(1, 7):
            self.assertIn(f"Artigo {n}\n", saida)

    def test_so_se_miran_as_liñas_do_comezo_e_do_final_da_páxina(self):
        miolo = [f"Liña de énfase {i} propia" for i in range(30)]
        corpos = []
        for n in range(1, 7):
            liñas = ["Cabeceira"] + miolo[:15] + ["Repetida no medio"] + miolo[15:] + ["Pé"]
            corpos.append("\n".join(l if "propia" not in l else f"{l} {n}" for l in liñas))
        saida = so(documento(corpos), quitar_repetidas=True)
        self.assertEqual(saida.count("Repetida no medio"), 6)
        self.assertEqual(saida.count("Cabeceira"), 1)

    def test_documento_sen_marcas_de_paxina_non_se_toca(self):
        md = "Mesma liña\n\nOutra cousa\n\nMesma liña\n\nMais\n\nMesma liña\n"
        self.assertEqual(so(md, quitar_repetidas=True), md)

    def test_con_menos_de_tres_paxinas_non_se_toca(self):
        md = documento(["Cab\nA", "Cab\nB"])
        self.assertEqual(so(md, quitar_repetidas=True).count("Cab"), 2)

    def test_as_táboas_non_se_tocan(self):
        taboa = "| a | b |\n| --- | --- |\n| 1 | 2 |"
        corpos = [f"Cab\n\n{taboa}\n\nCorpo {n}" for n in range(1, 6)]
        saida = so(documento(corpos), quitar_repetidas=True)
        self.assertEqual(saida.count("| 1 | 2 |"), 5)

    def test_nunca_se_perde_texto_que_non_sexa_repetido(self):
        md = con_cabeceira(8)
        resultado = aforro_ia.aforrar(md, dict(unir_liñas=False, limpar_espazos=False))
        antes = letras(md)
        despois = letras(resultado.texto) + letras("\n".join(resultado.eliminadas))
        self.assertEqual(antes, despois)
        self.assertTrue(resultado.eliminadas)

    def test_a_cabeceira_repetida_do_resultado(self):
        resultado = aforro_ia.aforrar(con_cabeceira(), dict(unir_liñas=False, limpar_espazos=False))
        self.assertIn("DOG Núm. 165", resultado.repetidas)
        self.assertIn("Diario Oficial de Galicia", resultado.repetidas)
        self.assertNotIn("Páx. 47407", resultado.repetidas)

    def test_o_bloque_das_cabeceiras_non_se_une_nin_ao_aforrar_dúas_veces(self):
        longa = "ISSN1130-9229 Depósito legal C.494-1998 https://www.xunta.gal/diario-oficial-galicia-con-moito-texto"
        corpos = [f"{longa}\nCVE-DOG: 2xlrgth5-ejn3-blt2-yqk3-2bfjmjy6fg21\n{parrafo(LOREM)}\nCorpo {n} único" for n in range(1, 6)]
        unha = aforro_ia.aforrar(documento(corpos)).texto
        self.assertIn(longa + "\nCVE-DOG:", unha)
        self.assertEqual(aforro_ia.aforrar(unha).texto, unha)

    def test_a_marca_das_cabeceiras_é_a_do_idioma(self):
        saida = so(con_cabeceira(), quitar_repetidas=True)
        self.assertIn(f"<!-- {idioma.t('copia_md.cabeceiras', 'gl')} -->", saida)


class TestUnirLiñas(unittest.TestCase):
    def test_une_as_liñas_dun_parágrafo(self):
        md = parrafo(LOREM) + "\n"
        self.assertGreater(md.count("\n"), 2)
        saida = so(md + "\n" + parrafo(LOREM) + "\n", unir_liñas=True)
        self.assertEqual(saida, f"{LOREM}\n\n{LOREM}\n")

    def test_quita_o_guion_de_corte(self):
        md = "A adminis-\ntración do Estado e a protec-\nción dos dereitos. Unha liña longa que enche o ancho todo da páxina sen chegar ao final\n"
        saida = so(md + "\n" + parrafo(LOREM) + "\n", unir_liñas=True)
        self.assertIn("A administración do Estado e a protección dos dereitos.", saida)

    def test_o_guion_de_corte_non_precisa_liña_longa(self):
        saida = so(parrafo(LOREM) + "\n\nA adminis-\ntración.\n", unir_liñas=True)
        self.assertIn("A administración.", saida)

    def test_conserva_o_guion_de_decreto_ley(self):
        saida = so(parrafo(LOREM) + "\n\nSegundo o Real Decreto-\nley 5/2020 e a Lei.\n", unir_liñas=True)
        self.assertIn("Real Decreto-ley 5/2020 e a Lei.", saida)

    def test_guion_antes_de_maiúscula_é_dun_nome_composto(self):
        saida = so(parrafo(LOREM) + "\n\nD. Antonio Pérez-\nGarcía, titular.\n", unir_liñas=True)
        self.assertIn("Pérez-García, titular.", saida)

    def test_non_une_despois_de_punto_nin_cunha_liña_curta(self):
        corpo = parrafo(LOREM) + "\n"
        md = corpo + "\nCAPÍTULO I\nNormas xerais\nArtigo 1. Obxecto\n" + "Primeira frase do artigo que remata aquí.\nSegunda frase noutra liña."
        saida = so(md, unir_liñas=True)
        self.assertIn("CAPÍTULO I\nNormas xerais\nArtigo 1. Obxecto\n", saida)
        self.assertIn("remata aquí.\nSegunda frase", saida)

    def test_non_une_cun_elemento_de_lista_nin_cun_título_nin_cunha_marca(self):
        longa = parrafo(LOREM)
        ultima = longa.split("\n")[-2]  # unha liña de ancho completo
        base = "\n".join(longa.split("\n")[:-1])
        for seguinte in ("1. Primeiro punto da lista", "a) Primeira letra", "- viñeta", "CAPÍTULO II",
                         "Artigo 7. Algo", "# Título", "| a | b |"):
            md = base + "\n" + seguinte + "\n" + parrafo(LOREM) + "\n"
            saida = so(md, unir_liñas=True)
            self.assertIn("\n" + seguinte + "\n", saida, seguinte)

    def test_non_une_a_unha_táboa_nin_a_unha_marca(self):
        taboa = "| a | b |\n| --- | --- |\n| 1 | 2 |"
        md = parrafo(LOREM) + "\n\n" + taboa + "\n\n" + parrafo(LOREM) + "\n"
        saida = so(md, unir_liñas=True)
        self.assertIn(taboa, saida)
        md = documento([parrafo(LOREM), parrafo(LOREM)])
        saida = so(md, unir_liñas=True)
        self.assertEqual(re.findall(r"<!-- páxina \d+ -->", saida), [marca(1), marca(2)])

    def test_non_une_entre_páxinas_aínda_que_a_última_liña_estea_cortada(self):
        corpos = [parrafo(LOREM).rsplit("\n", 1)[0] + " de acordo co", "o que se establece neste texto."]
        md = documento(corpos)
        saida = so(md, unir_liñas=True)
        self.assertIn("de acordo co\n\n" + marca(2), saida)

    def test_non_une_se_o_texto_non_está_partido_a_man(self):
        # Parágrafos longos dunha soa liña (un .docx): non hai ancho de corte.
        longo = LOREM * 3
        md = f"{longo}\nNova liña dentro do parágrafo\n\n{longo}\n"
        self.assertEqual(so(md, unir_liñas=True), md)

    def test_a_liña_seguinte_con_barra_de_escape_desescapase_ao_unir(self):
        base = "\n".join(parrafo(LOREM).split("\n")[:-1])
        md = base + "\n\\# cancelo escapado ao comezo de liña.\n\n" + parrafo(LOREM) + "\n"
        saida = so(md, unir_liñas=True)
        self.assertNotIn("\\#", saida)
        self.assertIn(" # cancelo escapado ao comezo de liña.", saida)

    def test_unir_non_cambia_as_palabras(self):
        md = parrafo(LOREM) + "\n\n" + parrafo(LOREM[::-1].replace("-", " ")) + "\n"
        saida = so(md, unir_liñas=True)
        self.assertEqual(letras(saida), letras(md))


class TestEspazos(unittest.TestCase):
    def test_espazos_tabuladores_e_final_de_liña(self):
        md = "Un   texto\t con   espazos   raros   \nOutra liña  \n"
        self.assertEqual(so(md, limpar_espazos=True), "Un texto con espazos raros\nOutra liña\n")

    def test_liñas_baleiras_de_sobra(self):
        md = "A\n\n\n\n\nB\n\n   \n\nC\n\n\n"
        self.assertEqual(so(md, limpar_espazos=True), "A\n\nB\n\nC\n")

    def test_conserva_a_sangría_das_listas_e_as_táboas(self):
        md = "- a\n  - subapartado   con  espazos\n\n| a  |  b |\n| --- | --- |\n"
        saida = so(md, limpar_espazos=True)
        self.assertIn("\n  - subapartado con espazos\n", saida)
        self.assertIn("| a | b |", saida)

    def test_non_toca_o_texto_das_marcas(self):
        md = marca(1) + "\n\n\n\nTexto\n"
        self.assertEqual(so(md, limpar_espazos=True), marca(1) + "\n\nTexto\n")

    def test_remata_sempre_cun_salto_de_liña(self):
        self.assertEqual(so("A", limpar_espazos=True), "A\n")
        self.assertEqual(so("", limpar_espazos=True), "")


TAM = 40


def _paxinas_longas(n: int, corpo_por_paxina: int = 400) -> str:
    corpos = []
    for i in range(1, n + 1):
        palabras = [f"palabra{i}x{j}" for j in range(corpo_por_paxina // 10)]
        corpos.append(parrafo(" ".join(palabras)))
    return documento(corpos)


class TestTroceado(unittest.TestCase):
    def test_trocea_polas_marcas_de_paxina(self):
        md = _paxinas_longas(10)
        resultado = aforro_ia.aforrar(md, dict(caracteres_por_parte=1300), nome_base="memoria")
        self.assertGreater(len(resultado.partes), 2)
        for parte in resultado.partes:
            self.assertLessEqual(len(parte.texto), 1300 + 150)  # 150: o comentario da parte
            corpo = re.sub(r"\A<!--.*?-->\n\n", "", parte.texto)
            self.assertTrue(corpo.startswith("<!-- páxina "), parte.nome)
        self.assertEqual([p.nome for p in resultado.partes][:2], ["memoria.parte-01.md", "memoria.parte-02.md"])

    def test_as_partes_xuntas_son_o_texto_enteiro(self):
        md = _paxinas_longas(10)
        resultado = aforro_ia.aforrar(md, dict(caracteres_por_parte=1300))
        corpos = [re.sub(r"\A<!--.*?-->\n\n", "", p.texto, count=1) for p in resultado.partes]
        self.assertEqual("\n\n".join(c.strip("\n") for c in corpos).strip(), resultado.texto.strip())

    def test_nunca_corta_unha_táboa(self):
        filas = "\n".join(f"| fila {i} | valor {i} |" for i in range(60))
        taboa = "| a | b |\n| --- | --- |\n" + filas
        md = parrafo(LOREM) + "\n\n" + taboa + "\n\n" + parrafo(LOREM) + "\n"
        resultado = aforro_ia.aforrar(md, dict(caracteres_por_parte=600, unir_liñas=False))
        con_taboa = [p for p in resultado.partes if "| fila 0 |" in p.texto]
        self.assertEqual(len(con_taboa), 1)
        self.assertIn("| fila 59 |", con_taboa[0].texto)
        self.assertIn("| --- | --- |", con_taboa[0].texto)

    def test_trocea_polos_títulos_se_non_hai_páxinas(self):
        seccions = [f"# Sección {i}\n\n" + parrafo(" ".join(f"s{i}p{j}" for j in range(60))) for i in range(8)]
        md = "\n\n".join(seccions) + "\n"
        resultado = aforro_ia.aforrar(md, dict(caracteres_por_parte=1000, unir_liñas=False))
        self.assertGreater(len(resultado.partes), 2)
        for parte in resultado.partes:
            corpo = re.sub(r"\A<!--.*?-->\n\n", "", parte.texto)
            self.assertTrue(corpo.startswith("# Sección "), parte.nome)

    def test_sen_títulos_nin_páxinas_corta_entre_parágrafos(self):
        md = "\n\n".join(f"Parágrafo {i} " + "texto " * 40 for i in range(12)) + "\n"
        resultado = aforro_ia.aforrar(md, dict(caracteres_por_parte=900, unir_liñas=False))
        self.assertGreater(len(resultado.partes), 2)
        for parte in resultado.partes:
            self.assertTrue(re.sub(r"\A<!--.*?-->\n\n", "", parte.texto).startswith("Parágrafo "))

    def test_se_cabe_nunha_parte_non_se_trocea(self):
        resultado = aforro_ia.aforrar(_paxinas_longas(2), dict(caracteres_por_parte=100000))
        self.assertEqual(resultado.partes, [])
        self.assertIsNone(resultado.indice)

    def test_sen_a_opción_non_se_trocea(self):
        self.assertEqual(aforro_ia.aforrar(_paxinas_longas(30)).partes, [])

    def test_unha_táboa_máis_grande_ca_unha_parte_vai_enteira(self):
        filas = "\n".join(f"| fila {i} | valor {i} |" for i in range(200))
        md = "Antes\n\n| a | b |\n| --- | --- |\n" + filas + "\n\nDespois\n"
        resultado = aforro_ia.aforrar(md, dict(caracteres_por_parte=500))
        self.assertEqual(sum("| fila 199 |" in p.texto for p in resultado.partes), 1)
        self.assertEqual(sum("| fila 0 |" in p.texto for p in resultado.partes), 1)
        taboa = [p for p in resultado.partes if "| fila 0 |" in p.texto][0]
        self.assertIn("| fila 199 |", taboa.texto)

    def test_o_índice_lista_cada_parte_coas_súas_páxinas(self):
        resultado = aforro_ia.aforrar(_paxinas_longas(10), dict(caracteres_por_parte=1300), nome_base="memoria")
        self.assertIsNotNone(resultado.indice)
        for parte in resultado.partes:
            self.assertIn(f"[{parte.nome}]({parte.nome})", resultado.indice)
        primeira, ultima = resultado.partes[0], resultado.partes[-1]
        self.assertEqual(primeira.paxina_inicial, 1)
        self.assertEqual(ultima.paxina_final, 10)
        self.assertEqual(resultado.nome_indice, "memoria.indice.md")
        self.assertIn("páxinas 1-", resultado.indice)
        # Cada parte comeza na páxina seguinte á que remata a anterior.
        for anterior, seguinte in zip(resultado.partes, resultado.partes[1:]):
            self.assertEqual(seguinte.paxina_inicial, anterior.paxina_final + 1)

    def test_o_índice_di_o_primeiro_título_de_cada_parte(self):
        seccions = [f"# Sección {i}\n\n" + parrafo(" ".join(f"s{i}p{j}" for j in range(60))) for i in range(8)]
        resultado = aforro_ia.aforrar("\n\n".join(seccions) + "\n", dict(caracteres_por_parte=1000, unir_liñas=False))
        self.assertIn("Sección 0", resultado.indice)

    def test_cada_parte_di_que_parte_é(self):
        resultado = aforro_ia.aforrar(_paxinas_longas(10), dict(caracteres_por_parte=1300))
        n = len(resultado.partes)
        self.assertTrue(resultado.partes[1].texto.startswith(f"<!-- parte 2 de {n}"))

    def test_nunca_se_perde_texto_ao_trocear(self):
        md = _paxinas_longas(12)
        resultado = aforro_ia.aforrar(md, dict(caracteres_por_parte=1000))
        todo = "\n".join(p.texto for p in resultado.partes)
        self.assertEqual(letras(todo), letras(md))


class TestEstimacion(unittest.TestCase):
    def test_tres_e_media_caracteres_por_token(self):
        self.assertEqual(aforro_ia.estimar_tokens(""), 0)
        self.assertEqual(aforro_ia.estimar_tokens("a" * 35), 10)
        self.assertEqual(aforro_ia.estimar_tokens("a" * 36), 11)  # redondea por riba

    def test_o_resultado_leva_antes_e_despois(self):
        md = con_cabeceira(10)
        r = aforro_ia.aforrar(md)
        self.assertEqual(r.caracteres_antes, len(md))
        self.assertEqual(r.caracteres_despois, len(r.texto))
        self.assertEqual(r.tokens_antes, aforro_ia.estimar_tokens(md))
        self.assertEqual(r.tokens_despois, aforro_ia.estimar_tokens(r.texto))
        self.assertLess(r.tokens_despois, r.tokens_antes)
        self.assertGreater(r.aforro_porcentaxe, 0)

    def test_o_resumo_di_que_é_unha_estimación(self):
        r = aforro_ia.aforrar(con_cabeceira(10))
        for lingua, palabra in (("gl", "estimación"), ("es", "estimación")):
            resumo = r.resumo(lingua)
            self.assertIn(palabra, resumo.lower())
            self.assertIn("3,5", resumo)
        self.assertNotEqual(r.resumo("gl"), r.resumo("es"))

    def test_resumo_sen_aforro_non_divide_por_cero(self):
        r = aforro_ia.aforrar("")
        self.assertEqual(r.aforro_porcentaxe, 0)
        self.assertIn("estimación", r.resumo("gl").lower())


class TestEntrada(unittest.TestCase):
    def test_sen_opcións_aplica_as_tres_transformacións_e_non_trocea(self):
        def corpo(n):
            liñas = [f"{l} [{n}]" for l in parrafo(LOREM).split("\n")]
            return "Cab\n" + "\n".join(liñas) + "\n\n\n\nPé"
        r = aforro_ia.aforrar(documento([corpo(n) for n in range(1, 6)]))
        self.assertEqual(r.texto.count("Cab"), 1)
        self.assertNotIn("\n\n\n", r.texto)
        pax3 = r.texto.split(marca(3))[1].split(marca(4))[0].strip()
        self.assertNotIn("\n", pax3)
        self.assertTrue(pax3.startswith("A administración") and pax3.endswith("[3]"))
        self.assertEqual(r.partes, [])

    def test_con_todo_apagado_non_cambia_nada(self):
        md = con_cabeceira(5)
        self.assertEqual(so(md), md)

    def test_acepta_un_obxecto_opcions_ou_un_dict(self):
        md = con_cabeceira(5)
        a = aforro_ia.aforrar(md, aforro_ia.Opcions(unir_liñas=False)).texto
        b = aforro_ia.aforrar(md, dict(unir_liñas=False)).texto
        self.assertEqual(a, b)

    def test_opción_descoñecida_dá_erro(self):
        with self.assertRaises(TypeError):
            aforro_ia.aforrar("x", dict(troceo=True))

    def test_é_idempotente(self):
        corpos = ["Cab\n" + "\n".join(f"{l} [{n}]" for l in parrafo(LOREM).split("\n")) + "\n\nPé" for n in range(1, 6)]
        unha = aforro_ia.aforrar(documento(corpos)).texto
        self.assertEqual(aforro_ia.aforrar(unha).texto, unha)

    def test_escribir_un_so_ficheiro(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "memoria.md"
            r = aforro_ia.aforrar(con_cabeceira(5), nome_base="memoria")
            escritos = aforro_ia.escribir(r, ruta)
            self.assertEqual(escritos, [str(ruta)])
            self.assertEqual(ruta.read_text(encoding="utf-8"), r.texto)

    def test_escribir_partes_e_índice(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "memoria.md"
            r = aforro_ia.aforrar(_paxinas_longas(10), dict(caracteres_por_parte=1300), nome_base="memoria")
            escritos = aforro_ia.escribir(r, ruta)
            nomes = sorted(Path(e).name for e in escritos)
            self.assertIn("memoria.indice.md", nomes)
            self.assertIn("memoria.parte-01.md", nomes)
            self.assertEqual(len(nomes), len(r.partes) + 1)
            self.assertFalse(ruta.exists())
            self.assertEqual((Path(d) / "memoria.parte-02.md").read_text(encoding="utf-8"), r.partes[1].texto)

    def test_nome_base_da_ruta(self):
        self.assertEqual(aforro_ia.nome_base("/a/b/demanda.anonimizado.pdf.md"), "demanda.anonimizado.pdf")
        self.assertEqual(aforro_ia.nome_base("memoria.md"), "memoria")


class TestConPdfDeVerdade(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_cabeceira_e_pe_dun_pdf_xerado_escríbense_unha_vez(self):
        ruta = self.dir / "acta.pdf"
        doc = fitz.open()
        for n in range(1, 6):
            pax = doc.new_page()
            pax.insert_text((72, 40), "DIARIO OFICIAL DE PROBA", fontsize=9)
            pax.insert_text((72, 54), f"Páxina {n} de 5", fontsize=9)
            pax.insert_text((72, 120), f"Corpo único da páxina {n} con texto propio.", fontsize=11)
            pax.insert_text((72, 140), f"Outra frase distinta número {n * 13} do corpo.", fontsize=11)
            pax.insert_text((72, 800), "Verificable en https://exemplo.test/proba", fontsize=8)
        doc.save(str(ruta))
        doc.close()
        texto, contexto = lectura.cargar_documento_estruturado(str(ruta))
        md = copia_md.xerar(contexto, texto)
        self.assertEqual(md.count("DIARIO OFICIAL DE PROBA"), 5)
        r = aforro_ia.aforrar(md)
        self.assertEqual(r.texto.count("DIARIO OFICIAL DE PROBA"), 1)
        self.assertEqual(r.texto.count("Verificable en https://exemplo.test/proba"), 1)
        self.assertNotIn("Páxina 3 de 5", r.texto)
        for n in range(1, 6):
            self.assertIn(f"Corpo único da páxina {n} con texto propio.", r.texto)
        self.assertEqual(len(re.findall(r"<!-- p[áa]xina \d+ -->", r.texto)), 5)


if __name__ == "__main__":
    unittest.main()
