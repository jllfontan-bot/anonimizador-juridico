"""Sobreanonimización do lote 5 (revisión humana do 10/10/2026, 60 docs): termos que
NON son persoas e o programa tapaba. Cada caso é sintético, co mesmo contexto que o
documento real; os controis negativos comproban que unha persoa parecida segue tapada."""
import os

# Estas probas escribíronse coa interface e os códigos en galego (PERSOA_...).
os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador import ner


def _persoas(texto):
    entidades, _ = ner.detectar(texto)
    return [e.texto for e in entidades if e.etiqueta == "PERSOA"]


class TestPeUoLogoDeBoletin(unittest.TestCase):
    def test_logo_cira_do_pe_do_dog_non_e_persoa(self):
        texto = ("O prazo será de dez días.\nCVE-DOG: d7a5oeq6-bfc6-owm7-j2a3-bla8h5wh6bj0\nE sa\n[CIRA\n"
                 "5% XUNTA\nDE GALICIA\nDiario Oficial de Galicia\n\nDOG Núm. 9\nPáx. 3\nO prazo será de dez días.")
        self.assertNotIn("CIRA", _persoas(texto))


class TestEncabezadosDeAnexo(unittest.TestCase):
    def test_de_trabajo_en_encabezado_de_anexo(self):
        texto = ("ANEXO\nCONSEJ. DE TRABAJO, MIGR. Y SEG. SOCIAL\nCONSEJERIA DE TRABAJO, MIGRACIONES Y "
                 "SEGURIDAD SOCIAL\nApellidos y nombre NRP Grupo\n1 CONSEJ. DE TRABAJO, MIGR. Y SEG. SOCIAL.")
        for t in _persoas(texto):
            self.assertNotIn("TRABAJO", t)

    def test_consejera_de_trabajo_cargo_en_mayusculas(self):
        texto = "REPUBLICA DE CUBA - LA HABANA. CONSEJERO / CONSEJERA DE TRABAJO, MIGRACIONES Y SEGURIDAD SOCIAL (523581)"
        for t in _persoas(texto):
            self.assertNotIn("TRABAJO", t)

    def test_fiscal_de_sala_con_tratamiento(self):
        texto = "notifíquese a la Excma. Sra. Fiscal de Sala Jefa de la Inspección Fiscal, y a la jefatura."
        self.assertNotIn("Fiscal de Sala", _persoas(texto))

    def test_criterio_de_desempate_mellor(self):
        texto = "criterios de desempate: 1º. Mellor cualificación da primeira parte da proba PEE. 2º. Mellor nota media."
        self.assertNotIn("Mellor", _persoas(texto))

    def test_titulos_de_temario(self):
        texto = ("1. Constitución Española: Título Preliminar, Título I. De los derechos y deberes fundamentales. "
                 "Ley: Título I. Actuación de los poderes públicos.")
        for t in _persoas(texto):
            self.assertFalse(t.startswith("Título"), t)


class TestSiglasEVerbos(unittest.TestCase):
    def test_sigla_con_puntos_irpf(self):
        texto = "la declaración del I.R.P.F. en el ejercicio 2023 y no haber solicitado la devolución."
        self.assertNotIn("I.R.P.F.", _persoas(texto))

    def test_verbo_de_comezo_de_frase(self):
        texto = ("Deberán pertenecer a la carrera fiscal y contar con más de veinte años de antigüedad. "
                 "Simultanearán el ejercicio de las funciones propias del responsable.")
        self.assertNotIn("Simultanearán", _persoas(texto))

    def test_sala_dun_tribunal(self):
        texto = ("interpuesto ante el Tribunal Superior de Justicia Galicia, Sala de lo Contencioso-Administrativo, "
                 "Sección Primera. Para comparecer ante la referida Sala en el plazo de nueve días.")
        for t in _persoas(texto):
            self.assertNotIn("Sala", t)


class TestNomesDeProxectoEEspecies(unittest.TestCase):
    def test_nome_de_planta_solar(self):
        texto = ("del proyecto de la planta solar fotovoltaica Flix-Ascó II, promovido por Sanmad, en el término "
                 "municipal de Flix. Nombre instalación: «Planta solar fotovoltaica Flix-Ascó II».")
        for t in _persoas(texto):
            self.assertNotIn("Flix", t)

    def test_nome_de_planta_con_solar_no_nome(self):
        texto = "proyecto «Planta solar fotovoltaica Oleo Solar de 75 MW de potencia instalada, en el término municipal»"
        for t in _persoas(texto):
            self.assertNotIn("Oleo", t)

    def test_binomio_latino_de_especie(self):
        texto = ("cernícalo primilla (Falco naumanni), halcón peregrino (Falco peregrinus), acebuches (Olea oleaster) "
                 "y tarajales (Tamarix spp.)")
        for t in _persoas(texto):
            self.assertNotIn("Falco", t)
            self.assertNotIn("Olea", t)

    def test_accidente_xeografico(self):
        texto = "Punto de emplazamiento: Sierra de La Cabra, Ladera del Pico Doce Penas\nTérmino Municipal: Allande"
        for t in _persoas(texto):
            self.assertNotIn("Sierra", t)


class TestApelidoJuzgado(unittest.TestCase):
    def test_juzgado_prieto_carlos_tapase_enteiro(self):
        texto = ("Apellidos y nombre\n**2726** RODRÍGUEZ RODRÍGUEZ, EMILIA.\n**4983** JUZGADO PRIETO, CARLOS.\n"
                 "**9303** NARRILLOS RUEDA, RAQUEL ARÁNZAZU.\n**5101** DURÁN GALÁN, PALOMA.")
        self.assertIn("JUZGADO PRIETO, CARLOS", _persoas(texto))

    def test_carlos_juzgado_prieto_nome_apelidos(self):
        texto = ("Relación de aprobados\n**4983** CARLOS JUZGADO PRIETO\n**9303** RAQUEL NARRILLOS RUEDA\n"
                 "**5101** PALOMA DURÁN GALÁN\n**2726** EMILIA RAMÍREZ ROMERO")
        self.assertIn("CARLOS JUZGADO PRIETO", _persoas(texto))

    def test_organismo_en_maiusculas_segue_sen_taparse(self):
        texto = "Remítase ao JUZGADO PRIMERA INSTANCIA, MADRID para os efectos oportunos."
        for t in _persoas(texto):
            self.assertNotIn("JUZGADO", t)


class TestControisNegativos(unittest.TestCase):
    """Persoas reais con palabras parecidas: seguen tapándose."""

    def test_persoa_con_mellor_trabajo_sala(self):
        for texto in ["Fdo.: don Xoán Ledo Páez, con DNI 12345678Z.",
                      "doña Marta Tejado Solana, vecina de Lugo.",
                      "Sra. Sala Pérez, abogada colegiada."]:
            self.assertTrue(_persoas(texto), texto)

    def test_nomes_de_pia_que_tamen_son_accidente_xeografico(self):
        # Llanos, Sierra, Valle, Monte son nomes de pía: firmante dun BOE real (lote 5, sen ver).
        for texto in ["Madrid, 5 de febrero de 2025. –La Subsecretaria de Vivienda, Llanos Carretero Ganuza.",
                      "Fdo.: doña Sierra Gil Páez, con DNI 12345678Z.",
                      "Fdo.: Valle Rivas Duarte, titular do expediente, residente en Vigo."]:
            self.assertTrue(any(p.split()[0] in ("Llanos", "Sierra", "Valle") for p in _persoas(texto)), texto)

    def test_iniciais_de_persoa_con_puntos(self):
        self.assertTrue(_persoas("Fdo.: don J.M. García López, en representación."))

    def test_apelido_arán(self):
        self.assertTrue(_persoas("doña Ana Marazán, titular do expediente, residente en Vigo."))


def _anonimizar(texto):
    import tempfile
    from anonimizador.pipeline import anonimizar_texto_detallado
    from anonimizador.registry import RexistroCorrespondencias
    with tempfile.TemporaryDirectory() as d:
        saida, _, substitucions = anonimizar_texto_detallado(texto, RexistroCorrespondencias(d))
    return saida, [(texto[a:b], novo) for a, b, novo in sorted(substitucions)]


class TestNomesDeInmoble(unittest.TestCase):
    """BOE-A-2025-3685 (revisión do 10/10): "Casería Don ..." e "Molino de Don ..."
    son nomes de vivendas rurais na contorna dunha planta solar, non persoas."""

    TEXTO = ("viviendas aisladas a menos de 100 m de la planta como el Cortijo La Ladera, a 7 m al oeste, "
             "Casería Don Bartolomé, a 9 m al este,\nMolinos de Calderón, a 58 m al sur, Cortijo Las Majadas, "
             "a 71 m al noroeste y Molino\nde Don Anselmo Valdivieso, a 99 m al oeste.")

    def test_caseria_e_molino_con_don_non_son_persoas(self):
        self.assertEqual(_persoas(self.TEXTO), [])

    def test_variantes_de_inmoble(self):
        for texto in ["La finca linda con Cortijo de Doña Remedios y con Hacienda Don Bartolomé Fraga.",
                      "se sitúa junto al Molino de Don Anselmo, en el término municipal."]:
            self.assertEqual(_persoas(texto), [], texto)


class TestCargoAntesDeNomeConComa(unittest.TestCase):
    """BOE-A-2025-6472: "La Ministra de Vivienda y Agenda Urbana, Isabel Ramírez
    Galán" tapábase coma un só anaco: "Agenda Urbana" líase coma os apelidos dunha
    listaxe "Apelidos, Nome". O nome do ministerio forma parte do cargo."""

    def test_nome_do_ministerio_fora_da_persoa(self):
        for texto in ["Madrid, 21 de marzo de 2025. –La Ministra de Vivienda y Agenda Urbana, Begoña\n"
                      "Marín Sabucedo.\nBOLETÍN OFICIAL DEL ESTADO",
                      "Madrid, 2 de abril de 2025. –El Ministro de Hacienda y Función Pública, Begoña Marín Sabucedo.",
                      "Santiago, 3 de marzo de 2025. A conselleira de Política Social e Igualdade, Begoña Marín Sabucedo."]:
            persoas = _persoas(texto)
            self.assertTrue(any("Marín Sabucedo" in p for p in persoas), (texto, persoas))
            for p in persoas:
                self.assertFalse(re.search(r"Agenda|Urbana|Hacienda|Función|Pública|Igualdade", p), (texto, p))


class TestSegundoApelidoNaLiñaSeguinte(unittest.TestCase):
    """BOE-A-2025-9720: "doña Elena Esperanza Ramírez\nDuarte (Elena E. Ramírez Duarte)":
    o salto de liña partía o nome e o segundo apelido levaba outro código (no
    sintético, quedaba á vista). O nome completo ten que ser UN anaco, e a forma
    abreviada entre parénteses XUSTO DETRÁS é a mesma persoa: mesmo código
    (decisión do usuario, 11/10/2026)."""

    TEXTO = ("c) Vocales:\nA propuesta de la Real Academia de la Historia: doña Marta Lucía Fraga\n"
             "Sabucedo (Marta L. Fraga Sabucedo).\nA propuesta de la Real Academia de Bellas Artes.")

    def test_nome_completo_nun_so_anaco_e_nada_a_vista(self):
        saida, substitucions = _anonimizar(self.TEXTO)
        self.assertNotIn("Sabucedo", saida)
        self.assertNotIn("Fraga", saida)
        self.assertEqual([t for t, novo in substitucions if novo.startswith("PERSOA_")],
                         ["Marta Lucía Fraga\nSabucedo", "Marta L. Fraga Sabucedo"])
        self.assertEqual(len({novo for _, novo in substitucions if novo.startswith("PERSOA_")}), 1, substitucions)

    def test_parentese_que_non_e_a_mesma_persoa_queda_a_parte(self):
        for texto in ["doña Marta Lucía Fraga Sabucedo (Ana L. Fraga Sabucedo), vocal.",
                      "doña Marta Lucía Fraga Sabucedo (Marta L. Fraga Sáez), vocal.",
                      # non vai xusto detrás: sen sinal abondo, non se fusiona
                      "doña Marta Lucía Fraga Sabucedo, vocal. Asiste tamén Marta L. Fraga Sabucedo."]:
            _, substitucions = _anonimizar(texto)
            self.assertEqual(len({novo for _, novo in substitucions if novo.startswith("PERSOA_")}), 2,
                             (texto, substitucions))

    def test_nome_e_primeiro_apelido_antes_do_salto(self):
        # Mesma fuga cun só nome de pía (atopada escribindo os controis).
        saida, _ = _anonimizar("Nombrar a doña Marta Fraga\nSabucedo, funcionaria de carrera.")
        self.assertNotIn("Sabucedo", saida)


class TestControisNegativosRestantes(unittest.TestCase):
    """Persoas reais en contextos parecidos aos de arriba: seguen tapándose."""

    def test_persoa_propietaria_dunha_caseria(self):
        for texto in ["Comparece don Bartolomé Fraga Sáez, propietario de la casería.",
                      "la casería de don Anselmo Valdivieso Rubio linda con el camino.",
                      "Molino propiedad de don Anselmo Valdivieso Rubio, con DNI 12345678Z."]:
            self.assertTrue(any("Valdivieso" in p or "Fraga" in p for p in _persoas(texto)), texto)

    def test_listaxe_apelidos_nome_segue_sendo_unha_persoa(self):
        self.assertEqual(_persoas("Relación de aspirantes:\nFraga Sáez, Bartolomé.\nValdivieso Rubio, Anselmo."),
                         ["Fraga Sáez, Bartolomé", "Valdivieso Rubio, Anselmo"])

    def test_lugar_e_data_na_liña_seguinte_non_se_unen_ao_nome(self):
        persoas = _persoas("Lo firma doña Marta Lucía Fraga\nMadrid, 3 de marzo de 2025.")
        self.assertTrue(any("Fraga" in p for p in persoas), persoas)
        self.assertFalse(any("Madrid" in p for p in persoas), persoas)

    def test_cargo_na_liña_seguinte_non_se_une_ao_nome(self):
        persoas = _persoas("Nombrar a doña Marta Lucía Fraga\nPresidenta del Consejo Asesor.")
        self.assertTrue(any("Fraga" in p for p in persoas), persoas)
        self.assertFalse(any("Presidenta" in p for p in persoas), persoas)


if __name__ == "__main__":
    unittest.main()
