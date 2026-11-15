"""Fuga grave atopada probando o reductor sobre unha demanda real (nov. 2026): no bloque de
enderezo dunha notificación do Catastro e nas táboas de titulares, o nome vai en orde
"APELIDO APELIDO NOME", todo en maiúsculas e sen coma, e spaCy etiquétao coma MISC/LOC en
~29 % das combinacións -> o nome quedaba enteiro á vista (ou só se tapaba o nome de pía).
A dirección "AV ROSALIA CASTRO 43" tampouco se detectaba ("AV" sen "avda") e o nome da rúa
acababa tomado por unha persoa. Nomes INVENTADOS que reproducen o fallo do modelo; os reais
non poden entrar no repositorio (é público)."""
import os

# Estas probas escribíronse coa interface e os códigos en galego (PERSOA_...).
os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador import ner
from anonimizador.pipeline import anonimizar_texto_detallado
from anonimizador.registry import RexistroCorrespondencias
from anonimizador.risco_residual import escanear_risco_residual

# Combinacións que spaCy (es_core_news_md) NON etiqueta coma PER.
NOMES_QUE_FALLAN = ("CAMPOS VILAR PABLO", "RIOS LEIRA LUIS", "VILAR QUINTAS MARTIN", "PAZOS CAMPOS PABLO")
# Control: esta si a colle spaCy; non debe cambiar.
NOME_CONTROL = "LEIRA RIOS LUIS"


def _bloque_catastro(nome):
    return (f"CT600023493357005390661\n- {nome}\n| - AV ROSALIA CASTRO 43 ES:1 PL:01 PT:DR\n"
            "15706 SANTIAGO DE COMPOSTELA (A\nCORUÑA)")


def _persoas(texto):
    entidades, _ = ner._detectar(texto)
    return [e.texto for e in entidades if e.etiqueta == "PERSOA"]


def _etiquetas(texto):
    entidades, _ = ner._detectar(texto)
    return [(e.texto, e.etiqueta) for e in entidades]


def _anonimizar(texto):
    with tempfile.TemporaryDirectory() as d:
        saida, _, _ = anonimizar_texto_detallado(texto, RexistroCorrespondencias(d))
    return saida


class TestNomeApelidosNomeSenComa(unittest.TestCase):

    def test_bloque_catastro_detecta_a_persoa_enteira(self):
        for nome in NOMES_QUE_FALLAN + (NOME_CONTROL,):
            with self.subTest(nome=nome):
                self.assertIn(nome, _persoas(_bloque_catastro(nome)))

    def test_bloque_catastro_non_deixa_nada_do_nome(self):
        for nome in NOMES_QUE_FALLAN + (NOME_CONTROL,):
            with self.subTest(nome=nome):
                saida = _anonimizar(_bloque_catastro(nome))
                for palabra in nome.split():
                    self.assertNotIn(palabra, saida)
                self.assertIn("SANTIAGO DE COMPOSTELA", saida)

    def test_taboa_de_titulares_non_deixa_apelidos_soltos(self):
        for nome in NOMES_QUE_FALLAN + (NOME_CONTROL,):
            with self.subTest(nome=nome):
                texto = f"(46) 33344455A {nome} 100,00"
                self.assertIn(nome, _persoas(texto))
                saida = _anonimizar(texto)
                for palabra in nome.split():
                    self.assertNotIn(palabra, saida)
                self.assertIn("100,00", saida)

    def test_segundo_nome_de_pia(self):
        self.assertIn("CAMPOS VILAR PABLO JOSE", _persoas("- CAMPOS VILAR PABLO JOSE\n"))

    def test_remates_aceptados(self):
        for remate in ("|", ",", ";", ")", " 25", " - X"):
            with self.subTest(remate=remate):
                self.assertIn("VILAR QUINTAS MARTIN", _persoas(f"(VILAR QUINTAS MARTIN{remate}"))


class TestNegativosNomeSenComa(unittest.TestCase):
    """O que non é un nome (ou non vai nesa orde) segue igual."""

    def test_toponimos_e_titulos_en_maiusculas(self):
        for texto in (
            "15706 SANTIAGO DE COMPOSTELA (A CORUÑA)",
            "ACUERDO DE ALTERACIÓN DE TITULARIDAD\n",
            "GERENCIA REGIONAL DEL CATASTRO DE GALICIA\n",
            "JUZGADO DE PRIMERA INSTANCIA NUM. 3 DE SANTIAGO\n",
            "AUDIENCIA PROVINCIAL DE PONTEVEDRA\n",
            "SALA DE LO CONTENCIOSO-ADMINISTRATIVO\n",
        ):
            with self.subTest(texto=texto):
                self.assertEqual(_persoas(texto), [])

    def test_titulo_que_segue_tras_o_tramo_non_e_nome(self):
        # Seguido doutra palabra capitalizada: é un título, non un nome.
        detectadas = ner._detectar_persoas_apelidos_nome_sen_coma(
            "CAMPOS VILAR PABLO MOTOR\n", "Campos Vilar Pablo Motor\n", [False] * 25, ner.cargar_modelo())
        self.assertEqual(detectadas, [])

    def test_prosa_seguida_de_minuscula_non_e_nome(self):
        texto = "CAMPOS VILAR PABLO presentou"
        detectadas = ner._detectar_persoas_apelidos_nome_sen_coma(
            texto, "Campos Vilar Pablo presentou", [False] * len(texto), ner.cargar_modelo())
        self.assertEqual(detectadas, [])

    def test_title_case_queda_fora_deste_reconecedor(self):
        # Decisión deliberada: só maiúsculas (o fallo medido). En Title Case decide spaCy.
        texto = "- Campos Vilar Pablo\n"
        detectadas = ner._detectar_persoas_apelidos_nome_sen_coma(
            texto, texto, [False] * len(texto), ner.cargar_modelo())
        self.assertEqual(detectadas, [])

    def test_nome_de_via_non_e_persoa(self):
        texto = "CALLE CAMPOS VILAR PABLO 4\n"
        suavizado = ner._suavizar_maiusculas_para_deteccion(texto)
        detectadas = ner._detectar_persoas_apelidos_nome_sen_coma(
            texto, suavizado, [False] * len(texto), ner.cargar_modelo())
        self.assertEqual(detectadas, [])

    def test_nome_en_orde_normal_segue_detectado(self):
        saida = _anonimizar("Comparece PABLO CAMPOS VILAR, con DNI 33344455A.")
        for palabra in ("PABLO", "CAMPOS", "VILAR"):
            self.assertNotIn(palabra, saida)


class TestEnderezoAbreviado(unittest.TestCase):

    def test_av_sen_punto_e_con_punto(self):
        for texto, esperado in (
            ("| - AV ROSALIA CASTRO 43 ES:1 PL:01 PT:DR", "AV ROSALIA CASTRO 43"),
            ("- AV. ROSALIA CASTRO 43\n", "AV. ROSALIA CASTRO 43"),
            ("CL NOVA 5, 2º", "CL NOVA 5"),
            ("PZA MAIOR 2\n", "PZA MAIOR 2"),
            ("con domicilio en av. Rosalía de Castro 43", "av. Rosalía de Castro 43"),
            ("AVD GALICIA 12", "AVD GALICIA 12"),
        ):
            with self.subTest(texto=texto):
                self.assertIn((esperado, "ENDEREZO"), _etiquetas(texto))

    def test_nome_da_rua_non_se_toma_por_persoa(self):
        for texto in ("| - AV ROSALIA CASTRO 43 ES:1", "- AV. ROSALIA CASTRO 43\n"):
            with self.subTest(texto=texto):
                self.assertEqual(_persoas(texto), [])
                self.assertNotIn("PERSOA_", _anonimizar(texto))

    def test_negativos_de_abreviatura(self):
        for texto in (
            "Bebeu 33 cl de agua e 2 de viño.",
            "Unha botella de 5 cl",
            "o informe av o 3 de maio",
            "tomou 33 cl de auga e 5 de viño",
        ):
            with self.subTest(texto=texto):
                self.assertNotIn("ENDEREZO", [e for _, e in _etiquetas(texto)])

    def test_avenida_completa_segue_igual(self):
        self.assertIn(("Avenida Rosalía de Castro 43", "ENDEREZO"),
                      _etiquetas("con domicilio en Avenida Rosalía de Castro 43, Santiago"))


class TestCasoOrixinalDePuntaAPunta(unittest.TestCase):

    def test_sen_aviso_alto_de_orde_invertida(self):
        texto = ("NOTIFICACIÓN\n" + _bloque_catastro("CAMPOS VILAR PABLO")
                 + "\nACUERDO DE ALTERACIÓN DE TITULARIDAD\n(46) 33344455A RIOS LEIRA LUIS 100,00\n")
        saida = _anonimizar(texto)
        for palabra in ("CAMPOS", "VILAR", "PABLO", "RIOS", "LEIRA", "LUIS", "ROSALIA"):
            self.assertNotIn(palabra, saida)
        altos = [r for r in escanear_risco_residual(saida) if r.confianza == "alta"]
        self.assertEqual(altos, [], altos)


if __name__ == "__main__":
    unittest.main()
