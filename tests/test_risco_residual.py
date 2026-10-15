"""Rede de seguridade final: despois de anonimizar, busca no texto FINAL
patróns que aínda parezan datos persoais. Motivado por unha listaxe real
do BOE onde a detección normal (spaCy + patróns) fallou por completo
ante un formato non previsto (nomes en "Apelidos, Nome"); en vez de fiar
cegamente en que a detección é perfecta, isto dá ao letrado unha
listaxe concreta do que revisar a man."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador.risco_residual import escanear_risco_residual


def _por_tipo_e_confianza(texto, tipo, confianza):
    return [
        r.texto for r in escanear_risco_residual(texto)
        if r.tipo == tipo and r.confianza == confianza
    ]


class TestNomeEnOrdeInvertida(unittest.TestCase):
    def test_detecta_apelidos_nome_sen_redactar(self):
        texto = "PERSOA_000001 A0590 CRESPO GONZALEZ, ROSA ID_000001 01 9,2470"
        atopados = _por_tipo_e_confianza(texto, "nome_en_orde_invertida", "alta")
        self.assertTrue(any("CRESPO GONZALEZ, ROSA" in a for a in atopados))

    def test_texto_totalmente_anonimizado_non_marca_nada(self):
        """Caso base: se todo quedou ben redactado (códigos PERSOA_/ID_),
        o escaneo non debe atopar nada de alta confianza."""
        texto = "PERSOA_000001 A0590 PERSOA_000002 ID_000001 01 9,2470"
        self.assertEqual(_por_tipo_e_confianza(texto, "nome_en_orde_invertida", "alta"), [])

    def test_non_confunde_prosa_normal_con_nome_invertido(self):
        """Caso real atopado escribindo isto: sen a esixencia estrita de
        maiúscula inicial, unha frase normal en minúscula coma "de
        septiembre, por la" marcábase coma "posible nome"."""
        texto = (
            "ORDEN ESD/2749/2008, de 18 de septiembre, por la que, a "
            "propuesta de la Consejería, se nombran funcionarios."
        )
        self.assertEqual(_por_tipo_e_confianza(texto, "nome_en_orde_invertida", "alta"), [])

    def test_funciona_tamen_en_maiusculas(self):
        """O propio documento BOE que motivou isto ten os nomes en
        MAIÚSCULAS -- o escaneo suaviza antes de buscar, igual ca a
        detección normal."""
        texto = "3531490757 A0590 SOTO PRESAS, MARIA AMALIA 35314907 01 9,0362"
        atopados = _por_tipo_e_confianza(texto, "nome_en_orde_invertida", "alta")
        self.assertTrue(any("SOTO PRESAS, MARIA AMALIA" in a for a in atopados))

    def test_non_confunde_titulo_de_seccion_a_inicio_de_frase(self):
        """Mesmo bug ca en `ner._detectar_persoas_apelidos_nome_inverso`
        (xa arranxado alí): unha soa palabra capitalizada de inicio de
        frase seguida de coma confúndese co "apelido" da listaxe. Caso
        real atopado nun documento real (certificado dun rexistro da
        propiedade): un título de sección en maiúsculas disparaba coma
        se fose un nome sen redactar."""
        texto = "Lo que hago constar en Santiago de Compostela. COMPARECENCIAS, ALEGACIONES Y ACUERDOS:"
        self.assertEqual(_por_tipo_e_confianza(texto, "nome_en_orde_invertida", "alta"), [])


class TestNumeroSolto(unittest.TestCase):
    def test_detecta_numero_de_7_a_9_dixitos_solto(self):
        texto = "algo de contexto 34867809 mais contexto"
        self.assertEqual(_por_tipo_e_confianza(texto, "numero_solto", "alta"), ["34867809"])

    def test_non_marca_numero_xa_dentro_dun_codigo(self):
        texto = "PERSOA_000001 ID_000042"
        self.assertEqual(_por_tipo_e_confianza(texto, "numero_solto", "alta"), [])

    def test_non_marca_numeros_curtos_ou_longos_de_mais(self):
        texto = "ano 2024 referencia 123456789012"
        self.assertEqual(_por_tipo_e_confianza(texto, "numero_solto", "alta"), [])

    def test_non_marca_referencia_catastral_pegada_a_letras(self):
        """Caso real (documento de rexistro da propiedade): unha referencia
        catastral coma "6872011NH3467B0001BF" ten os primeiros 7 díxitos
        pegados a letras despois -- non é un número SOLTO, é o principio
        doutro identificador máis longo que non nos corresponde marcar
        aquí (nin é un DNI/NIE/NRP)."""
        texto = "Parcela con Referencia Catastral 1234567AB1234C0001XY según consta inscrita."
        self.assertEqual(_por_tipo_e_confianza(texto, "numero_solto", "alta"), [])

    def test_non_marca_parte_enteira_de_coordenada_utm_decimal(self):
        """Caso real (certificación rexistral con coordenadas UTM): "coma
        UTM": "4746999,76" ten os primeiros 7 díxitos pegados a unha coma
        seguida de máis díxitos -- é a parte enteira dun decimal, non un
        número solto."""
        texto = "Coordenadas UTM: 536672.5 4746999,76 según el plano adjunto."
        self.assertEqual(_por_tipo_e_confianza(texto, "numero_solto", "alta"), [])

    def test_marca_numero_solto_aínda_que_remate_a_frase_en_punto(self):
        """O punto final SÓ debe descartar o número cando vai seguido
        doutro díxito (notación decimal) -- un punto de fin de frase
        normal non debe ocultar un número solto real."""
        texto = "O código de referencia é 34867809."
        self.assertEqual(_por_tipo_e_confianza(texto, "numero_solto", "alta"), ["34867809"])


class TestRachaCapitalizadaBaixaConfianza(unittest.TestCase):
    def test_marca_racha_capitalizada_illada_coma_baixa_confianza(self):
        texto = "O informe foi asinado por Xoana Exemplo Sinfin nese día."
        atopados = _por_tipo_e_confianza(texto, "racha_capitalizada", "baixa")
        self.assertTrue(any("Xoana Exemplo Sinfin" in a for a in atopados))

    def test_ruido_coñecido_non_se_marca(self):
        texto = "CUERPO: 0590 PROFESORES DE ENSEÑANZA SECUNDARIA"
        atopados = escanear_risco_residual(texto)
        # nada de alta confianza, e o ruído coñecido non debe aparecer
        self.assertEqual([a for a in atopados if a.confianza == "alta"], [])


if __name__ == "__main__":
    unittest.main()
