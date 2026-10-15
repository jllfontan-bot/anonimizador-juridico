"""Fugas e erro de asociación atopados na proba do lote 6 (500 PDF de 2024, lectura de
Claude dunha mostra de 60, 11/10/2026; ids en `corpus_web_lote6_2024/mostra_lectura_claude.json`
na copia local, fóra de git). Cada caso é sintético, co mesmo contexto ca o documento real; os controis
comproban que o que non é persoa segue á vista."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador.pipeline import anonimizar_texto_detallado
from anonimizador.registry import RexistroCorrespondencias


def _anonimizar(texto):
    with tempfile.TemporaryDirectory() as d:
        saida, _, substitucions = anonimizar_texto_detallado(texto, RexistroCorrespondencias(d))
    return saida, [(texto[a:b], novo) for a, b, novo in sorted(substitucions)]


class TestApelidoPartidoConGuion(unittest.TestCase):
    """AnuncioG0427-200924-0004_gl: "Xoán Páez Es-\\nteiro" quedaba enteiro á vista e
    en "Brais Páez Estei-\\nro" só se tapaba "Brais Páez"."""

    def test_persoa_enteira_partida_con_guion_nunha_enumeracion(self):
        saida, _ = _anonimizar("1. O día 18 de setembro de 2024, Ana Salcedo Roel, Xoán Páez Es-\nteiro e "
                               "Brais Páez Esteiro solicitaron autorización para a transmisión.")
        for anaco in ("Xoán", "Es-", "teiro", "Ana Salcedo", "Brais"):
            self.assertNotIn(anaco, saida)

    def test_mesma_persoa_partida_e_enteira_leva_un_codigo(self):
        _, substitucions = _anonimizar("solicitaron Xoán Páez Es-\nteiro e Ana Salcedo Roel a transmisión. "
                                       "Titular: Xoán Páez Esteiro (12,5 % nu propietario).")
        codigos = dict(substitucions)
        self.assertEqual(codigos["Xoán Páez Es-\nteiro"], codigos["Xoán Páez Esteiro"], substitucions)
        self.assertEqual(len({n for _, n in substitucions if n.startswith("PERSOA_")}), 2, substitucions)

    def test_segundo_apelido_partido_con_guion(self):
        saida, _ = _anonimizar("titulares: Xoán Páez Esteiro (***1282**) (12,5 % nu propietario), Brais Pérez "
                               "Esté-\nvez (***1282**) (12,5 % nu propietario), Uxía Pérez Rey.")
        self.assertNotIn("Esté", saida)
        self.assertNotIn("vez (", saida)


class TestNomeDePiaParcial(unittest.TestCase):
    """Nome de pía á vista cos apelidos tapados (BOE-A-2024-14397, BOE-A-2024-13946)."""

    def casos(self):
        return {
            "Madrid, 4 de julio de 2024. –La Directora General para el Servicio Público de Justicia,\n"
            "Maria dels Àngels Fuster Viana.\nBOLETÍN OFICIAL DEL ESTADO": ["Maria", "dels"],
            "Vocal tercero/a D/D.ª: Marcel·Lí Del Pino Rubio, Catedrático/a de Universidad de la\n"
            "Universidad Autónoma de Madrid.": ["Marcel"],
            "Vocal primero/a D/D.ª: M.ªElena Benítez Bárcena, Catedrático/a de Universidad\nde la Universidad.":
                ["Elena"],
            "Vocal primero/a D/D.ª: M Luisa De La Peña Sáez, Catedrático/a de Universidad\nde la Universidad.":
                ["Luisa", "D/D.ª: M "],
            "Vocal tercero/a D/D.ª: Clara M Prado Losada, Catedrático/a de Universidad de la\nUniversidad.":
                ["Clara", " M PERSOA"],
            "representada en este acto por don Kamal M.R.F. Amin Kamal, con DNI\n*****26***, mayor de edad.":
                ["M.R.F."],
            "Vocal segundo/a D/D.ª: M Carmen Prado Losada, Catedrático/a de Universidad\nde la Universidad.":
                ["D/D.ª: M ", "Carmen"],
        }

    def test_nada_do_nome_queda_a_vista(self):
        for texto, prohibidos in self.casos().items():
            saida, substitucions = _anonimizar(texto)
            for anaco in prohibidos:
                self.assertNotIn(anaco, saida, (texto, substitucions))

    def test_un_so_codigo_por_persoa(self):
        for texto in self.casos():
            _, substitucions = _anonimizar(texto)
            self.assertEqual(len({n for _, n in substitucions if n.startswith("PERSOA_")}), 1, (texto, substitucions))


class TestDniDoAnexoNonEDoAsinante(unittest.TestCase):
    """AnuncioG0426-080324-0005_gl (e outros 2 da mostra): nun anuncio cun ANEXO só de DNI,
    o primeiro DNI levaba o código de quen asina xusto enriba -- a saída dicía que o
    denunciado era a xefa territorial."""

    TEXTO = ("A Coruña, 8 de marzo de 2024\nMaría Nieves Carballo Sarmiento\nXefa territorial da Coruña\nANEXO\n"
             "Expediente: MON-CO-0331-2023 FOR.\nDNI denunciado: 90818283T.\nActo de notificación: proposta de "
             "resolución.\nExpediente: MON-CO-0332-2023 FOR.\nDNI denunciado: 90819296R.\n")

    def test_o_dni_do_anexo_non_leva_o_codigo_da_asinante(self):
        _, substitucions = _anonimizar(self.TEXTO)
        codigo = dict(substitucions)
        self.assertNotEqual(codigo["90818283T"], codigo["María Nieves Carballo Sarmiento"], substitucions)
        self.assertFalse(codigo["90818283T"].startswith("PERSOA_"), substitucions)

    def test_control_dni_xunto_ao_nome_segue_asociado(self):
        _, substitucions = _anonimizar("Comparece don Xoán Páez Veiga, con DNI 90818283T, veciño de Lugo.")
        codigo = dict(substitucions)
        self.assertEqual(codigo["90818283T"], codigo["Xoán Páez Veiga"], substitucions)


class TestCargosNonPersoa(unittest.TestCase):
    """BOE-A-2024-20181, BOE-A-2024-7628, BOE-A-2024-18109: o nome do cargo tapábase coma persoa."""

    def test_cargo_con_calificativo(self):
        for texto, cargo in [
            ("Decreto del Fiscal General del Estado, por el\nque se nombra Fiscal Delegada para la Protección y "
             "Tutela de las Víctimas\nen el proceso penal en la Fiscalía.", "Fiscal Delegada"),
            ("28040 Madrid), en su\ncondición de Rector Magnífico de la misma, cargo para el que fue nombrado "
             "por Real\nDecreto 872/2021.", "Rector Magnífico"),
        ]:
            saida, substitucions = _anonimizar(texto)
            self.assertIn(cargo, saida, substitucions)

    def test_control_persoa_xunto_ao_cargo_segue_tapada(self):
        saida, _ = _anonimizar("por el que propone el nombramiento de Fiscal Delegado para la Protección y\n"
                               "tutela de las Víctimas en el proceso penal a doña Ana Salcedo Roel.")
        self.assertIn("Fiscal Delegado", saida)
        self.assertNotIn("Salcedo", saida)
        saida, _ = _anonimizar("Rector Magnífico de la Universidad, don Xoán Páez Veiga, en nombre de la misma.")
        self.assertNotIn("Páez", saida)


class TestControis(unittest.TestCase):
    def test_guion_que_non_parte_un_nome(self):
        saida, _ = _anonimizar("Nombrar a doña Ana Salcedo Roel, técnica de medio-\nambiente, con destino en Lugo.")
        self.assertIn("ambiente", saida)
        self.assertNotIn("Salcedo", saida)

    def test_d_entre_dous_nomes_e_o_tratamento_da_seguinte_persoa(self):
        _, substitucions = _anonimizar("Comparecen D. Xoán Páez Veiga D. Manuel Carballo Portela y otros.")
        self.assertEqual(len({n for _, n in substitucions if n.startswith("PERSOA_")}), 2, substitucions)

    def test_lugar_que_empeza_por_un_nome_de_pia(self):
        # "Puerto" tamén é nome de pía (María del Puerto): lote 5 sen ver, BOE-B-2025-1874.
        saida, substitucions = _anonimizar("el servicio portuario de recogida de desechos en el Puerto de la "
                                           "Bahía de Cádiz. Dando cumplimiento a lo preceptuado.")
        self.assertIn("Puerto de la", saida, substitucions)

    def test_maria_sen_apelidos_e_m_de_medida(self):
        saida, _ = _anonimizar("La parcela mide 300 M de fachada. Iglesia de Santa Maria dels Àngels.")
        self.assertIn("300 M de fachada", saida)


if __name__ == "__main__":
    unittest.main()
