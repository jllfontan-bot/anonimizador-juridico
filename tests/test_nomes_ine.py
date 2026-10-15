import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador import ner, nomes_ine
from anonimizador.pipeline import anonimizar_texto
from anonimizador.registry import RexistroCorrespondencias


def _so_taboa(texto):
    """Só o recoñecedor por táboa, sen spaCy nin os outros de reserva: así
    un control negativo comproba o que engade ESTE recoñecedor, non o que
    xa facía (ben ou mal) o resto do detector."""
    nlp = ner.cargar_modelo()
    suavizado = ner._suavizar_ordinais_para_deteccion(ner._suavizar_maiusculas_para_deteccion(texto))
    return [e.texto for e in ner._detectar_persoas_por_taboa(texto, suavizado, [False] * len(texto), nlp)]


def _anonimizar(texto):
    with tempfile.TemporaryDirectory() as d:
        return anonimizar_texto(texto, RexistroCorrespondencias(d))


class TestTaboasIne(unittest.TestCase):
    def test_normaliza_coma_o_ine(self):
        """O INE publica sen acentos pero coa Ñ ("MARTIÑO")."""
        self.assertEqual(nomes_ine.normalizar("Uxía"), "UXIA")
        self.assertEqual(nomes_ine.normalizar("Martiño"), "MARTIÑO")
        self.assertEqual(nomes_ine.normalizar("Outeiriño"), "OUTEIRIÑO")

    def test_nomes_galegos_pouco_frecuentes_estan_na_taboa(self):
        for nome in ["ROI", "XACOBE", "BREIXO", "LEDICIA", "COVADONGA", "TAREIXA"]:
            self.assertIn(nome, nomes_ine.nomes())

    def test_apelidos_galegos_estan_na_taboa(self):
        for apelido in ["OUTEIRIÑO", "BEADE", "RESUA", "SOUTO", "NOGUEIRA"]:
            self.assertIn(apelido, nomes_ine.apelidos())

    def test_filtro_quita_palabras_pouco_frecuentes_coma_nome(self):
        """"Sala" (22 persoas), "Mayo" (51), "Vigo" (37) están na lista do
        INE, pero nun documento xurídico case sempre son outra cousa."""
        validos = nomes_ine.nomes_para_detector(ner.cargar_modelo())
        for palabra in ["SALA", "MAYO", "VIGO", "DON", "SANTA", "CAMINO"]:
            self.assertNotIn(palabra, validos)
        for nome in ["ROI", "XACOBE", "LEDICIA", "TAREIXA", "FIZ", "SANTIAGO", "ROSA", "PAZ"]:
            self.assertIn(nome, validos)


class TestFugasNomesGalegos(unittest.TestCase):
    """As 9 fugas reais da medición do 28/09/2026: spaCy etiquetaba estes
    nomes coma LOC/ORG/MISC e quedaban sen redactar."""

    CASOS = [
        ("Otorga poder de representación Roi del Valle Resua a favor de su letrado.", "Roi del Valle Resua"),
        ("En el acto del juicio declara la testigo Roi del Valle Resua, quien manifiesta no haber "
         "presenciado los hechos.", "Roi del Valle Resua"),
        ("Roi Fiolleda Outeiral presenta un informe médico donde consta que padece un trastorno "
         "bipolar desde hace años.", "Roi Fiolleda Outeiral"),
        ("Covadonga Ferrándiz Salcedo declaró que profesa la religión musulmana y acude a su lugar de "
         "culto cada semana.", "Covadonga Ferrándiz Salcedo"),
        ("Consta que Roi Barroso Cordeiro es afiliado del sindicato CCOO desde hace varios años.",
         "Roi Barroso Cordeiro"),
        ("Consta que Xacobe Ferrándiz Salcedo es afiliado del sindicato UGT desde hace varios años.",
         "Xacobe Ferrándiz Salcedo"),
        ("Consta que Xacobe Fiolleda Outeiral es afiliado del sindicato USO desde hace varios años.",
         "Xacobe Fiolleda Outeiral"),
        ("Comparece como letrado de la parte contraria don Breixo Ferrándiz Salcedo, en el turno de "
         "intervenciones.", "Breixo Ferrándiz Salcedo"),
        ("Comparece como testigo doña Ledicia Falcón Bande, quien nada aportó de relevancia.",
         "Ledicia Falcón Bande"),
    ]

    def test_os_nove_nomes_quedan_redactados(self):
        for texto, nome in self.CASOS:
            with self.subTest(nome=nome):
                anon, _ = _anonimizar(texto)
                for palabra in nome.split():
                    if palabra != "del":
                        self.assertNotIn(palabra, anon)

    def test_nome_en_maiusculas(self):
        anon, _ = _anonimizar("ROI BARROSO CORDEIRO comparece ante este juzgado.")
        self.assertNotIn("ROI", anon)
        self.assertNotIn("NOGUEIRA", anon)

    def test_preposicion_a_a_inicio_de_frase_non_e_toponimo(self):
        """"A" a inicio de frase pode ser a preposición, non o artigo dun
        topónimo coma "A Mariña"."""
        self.assertEqual(_so_taboa("A Roi Barroso Cordeiro se le notificó la resolución."),
                         ["Roi Barroso Cordeiro"])

    def test_apelido_raro_fora_da_taboa_non_queda_a_vista(self):
        """"Fiolleda" non está na táboa do INE (menos de 20 persoas), pero
        vai con "Outeiral", que si: o nome enteiro redáctase igual."""
        self.assertEqual(_so_taboa("Declara Xiana Outeiral Fiolleda en calidad de testigo."),
                         ["Xiana Outeiral Fiolleda"])

    def test_palabra_corrente_tras_o_apelido_non_entra_no_nome(self):
        self.assertEqual(_so_taboa("autor Leticia Viana Letrada aprobou"), ["Leticia Viana"])

    def test_limite_sen_ningun_apelido_da_taboa_non_se_detecta(self):
        """Límite coñecido e deliberado: sen polo menos un apelido da táboa
        oficial, este recoñecedor non actúa (queda para spaCy)."""
        self.assertEqual(_so_taboa("Declara Lúa Vilaboi en calidad de testigo."), [])


class TestControisNegativosTaboa(unittest.TestCase):
    """Topónimos, vías, centros e marcas que coinciden con "nome + apelido"
    da táboa. Compróbase SÓ o recoñecedor novo: algúns destes xa os
    redactaba spaCy antes (ver medicion/README.md)."""

    def test_toponimos_e_lugares_non_son_persoas(self):
        textos = [
            "La vista se celebró en Santiago de Compostela el pasado martes.",
            "Recorrió la Costa da Morte y vivía en A Mariña Lucense.",
            "Compró un Mercedes Benz de segunda mano en Lugo.",
            "El partido se jugó en el estadio Santiago Bernabéu.",
            "La Sala Primera del Tribunal Supremo desestimó el recurso.",
            "Colaboró como voluntario con Cruz Roja durante la emergencia.",
            "El local está en la calle Rosalía de Castro de Vigo.",
            "Ten domicilio en Avda. Rosalía de Castro sen número.",
            "La sede está en la rúa Concepción Arenal de Ferrol.",
            "Fue trasladado al Hospital Álvaro Cunqueiro de Vigo.",
            "La concentración tuvo lugar en la Praza de María Pita.",
            "La procesión de la Virgen del Pilar pasó por la plaza.",
            "El hotel Sol Meliá de Sanxenxo cerró la temporada.",
            "Factura emitida por Rosa Castro S.L. el pasado mes.",
        ]
        for texto in textos:
            with self.subTest(texto=texto):
                self.assertEqual(_so_taboa(texto), [])

    def test_cargo_publico_segue_exento(self):
        """A exención de cargos públicos (`_CARGOS_EXENTOS_RE`) aplícase
        tamén ás persoas atopadas pola táboa."""
        entidades, _ = ner.detectar(
            "Dictó la resolución la magistrada Antía Queiruga Vilariño, titular del juzgado.")
        exenta = [e for e in entidades if e.texto == "Antía Queiruga Vilariño"]
        self.assertEqual(len(exenta), 1)
        self.assertEqual(exenta[0].etiqueta, "PERSOA_EXENTA_CARGO_PUBLICO")


if __name__ == "__main__":
    unittest.main()
