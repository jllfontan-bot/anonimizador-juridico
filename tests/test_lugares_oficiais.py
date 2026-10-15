"""Listas oficiais de lugares (INE + Nomenclátor de Galicia): un lugar non se
tapa coma persoa (lote 3 e 4, sobreanonimización dominante). Os casos son
sintéticos; os nomes de lugar son reais (as listas oficiais)."""
import os

# Estas probas escribíronse coa interface e os códigos en galego (PERSOA_...).
os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "datos" / "lugares"))

from anonimizador import lugares_oficiais, ner
from anonimizador.pipeline import anonimizar_texto
from anonimizador.recognizers import Entidade
from anonimizador.registry import RexistroCorrespondencias


def _persoas(texto):
    entidades, _ = ner.detectar(texto)
    return [e.texto for e in entidades if e.etiqueta == "PERSOA"]


def _anonimizar(texto):
    with tempfile.TemporaryDirectory() as d:
        return anonimizar_texto(texto, RexistroCorrespondencias(d))[0]


class TestTaboaDeLugares(unittest.TestCase):
    def test_contén_lugares_do_ine_e_de_galicia(self):
        lugares = lugares_oficiais.lugares()
        for nome in ["BRAÑA", "CARTELLE", "SAN CLODIO", "SANT FELIU DE LLOBREGAT", "ARENYS DE MAR",
                     "O ADRO", "ADRO", "LA NUCIA", "NUCIA", "CASTRO", "VILAR", "LUGO"]:
            self.assertIn(nome, lugares)

    def test_cabeceira_cita_fontes_e_licenza(self):
        cabeceira = (Path(lugares_oficiais.__file__).parent / "datos" / "lugares_oficiais.tsv").read_text(
            encoding="utf-8").split("\n\n")[0][:1500]
        for texto in ["INE", "Nomenclátor de Galicia", "CC BY-SA 4.0", "CC BY 4.0"]:
            self.assertIn(texto, cabeceira)

    def test_variantes_do_artigo_pospoñido_e_dos_nomes_bilingües(self):
        from xerar_lugares import variantes
        self.assertEqual(variantes("Adro, O"), {"ADRO", "O ADRO"})
        self.assertEqual(variantes("Camp de Mirra, el/Campo de Mirra"),
                         {"CAMP DE MIRRA", "EL CAMP DE MIRRA", "CAMPO DE MIRRA"})
        self.assertEqual(variantes("Toxa (Illa Da)"), {"TOXA"})

    def test_distingue_o_que_pode_ser_persoa(self):
        parece = lambda n: lugares_oficiais.parece_nome_de_persoa(n)
        self.assertTrue(parece("CASTRO"))   # apelido moi frecuente
        self.assertTrue(parece("LUGO"))
        self.assertTrue(parece("MANUEL CASTRO"))
        self.assertFalse(parece("CARTELLE"))
        self.assertFalse(parece("SAN CLODIO"))
        self.assertFalse(parece("SANT FELIU DE LLOBREGAT"))


class TestLugarNonSeTapaComaPersoa(unittest.TestCase):
    """Cada un destes tapábase coma PERSOA en main (956226d)."""

    def test_lugar_galego_nunha_enumeracion(self):
        self.assertEqual(_persoas("Los vecinos de Braña, Cartelle y San Clodio presentaron alegaciones."), [])

    def test_lugar_en_maiusculas(self):
        self.assertEqual(_persoas("LUGAR DE SAN CLODIO"), [])

    def test_municipios_catalans_cortados_pola_entidade(self):
        self.assertEqual(
            _persoas("Los juzgados de Sant Feliu de Llobregat, Arenys de Mar, Badalona, Berga y Mataró."), [])

    def test_vecino_de_lugar(self):
        self.assertEqual(_persoas("Vecino de Cartelle, con domicilio en Braña, nº 4."), [])

    def test_lugar_que_tamen_e_apelido_con_provincia_ao_lado(self):
        self.assertEqual(_persoas("Domicilio: Vilar, Lugo."), [])

    def test_artigo_da_seguinte_localidade_cortado_pola_entidade(self):
        """"El Milà, Els Guiamets" (BOE-A-2025-15413): a entidade era "Milà, Els"."""
        self.assertEqual(_persoas("Montferri, Mora d’Ebre, El Masroig, El Milà, Els Guiamets, Falset, Gandesa."), [])

    def test_dous_topónimos_seguidos_con_contexto_de_lugar(self):
        """"estudo de detalle en Cimadevila Darbo" (DOG AnuncioG2329-201025-1)."""
        self.assertEqual(_persoas("Aprobación do estudo de detalle en Cimadevila Darbo, concello de Cangas."), [])

    def test_o_texto_anonimizado_conserva_o_lugar(self):
        saida = _anonimizar("Los vecinos de Braña, Cartelle y San Clodio presentaron alegaciones.")
        self.assertIn("San Clodio", saida)


class TestControisNegativos(unittest.TestCase):
    """O que SEGUE a taparse: persoas, aínda que o seu nome sexa un lugar."""

    def test_con_don_ou_dona_segue_sendo_persoa(self):
        self.assertEqual(_persoas("Compareció don Castro."), ["Castro"])
        self.assertEqual(_persoas("Se notificó a doña Cartelle en su domicilio."), ["Cartelle"])

    def test_apelido_que_e_lugar_sen_contexto_segue_sendo_persoa(self):
        self.assertEqual(_persoas("Fdo.: Castro"), ["Castro"])

    def test_nome_completo_cun_apelido_que_e_lugar(self):
        self.assertEqual(_persoas("Reunidos en Cartelle, el 5 de mayo, comparece Xoán Braña Pérez."),
                         ["Xoán Braña Pérez"])
        self.assertEqual(_persoas("Por el Ayuntamiento de Berga comparece Berga Pérez."), ["Berga Pérez"])

    def test_dous_apelidos_raros_que_son_lugares_sen_contexto_seguen_sendo_persoa(self):
        self.assertEqual(_persoas("Fdo.: Cartelle Ameixeiras"), ["Cartelle Ameixeiras"])

    def test_dobre_apelido_con_guion_non_e_unha_enumeracion_de_lugares(self):
        self.assertEqual(_persoas("Comparece doña Lucía Pérez-Castro."), ["Lucía Pérez-Castro"])


def _e_lugar(texto, fragmento):
    """`_e_lugar_oficial` sobre `fragmento` dentro de `texto` (a "persoa" que o modelo marcaría)."""
    i = texto.index(fragmento)
    return ner._e_lugar_oficial(Entidade(i, i + len(fragmento), fragmento, "PERSOA"), texto)


class TestContextosDeLugarDoCorpus(unittest.TestCase):
    """Casos reais do lote 3 e 4 (04/10/2026) que seguían tapados con esta rama."""

    CASOS = [
        ("Sentencia de la Audiencia Provincial de Valencia, Sección 3.ª, núm. 119/2020.", "Valencia"),
        ("Resolución de la Diputación Provincial de Albacete, Organismo Autónomo.", "Albacete"),
        ("otorgada ante el notario de Tarazona de la Mancha (Albacete) doña Ana", "Tarazona"),
        ("con domicilio en 18190 Cenes de la Vega, Granada, España. Ambas partes", "Granada"),
        ("no Edificio Administrativo de San Lázaro, s/n, da Consellería de Sanidade.", "San Lázaro"),
        ("Proxecto: LMTS e CS (3L). Concello: Carballo. Feitos: O día 12.10.2025", "Carballo"),
        ("do esbozo do MVMC Estelo, Braña e Toxiza. Examinado o recurso", "Braña"),
        ("Instituto de Investigación Sanitaria de Santiago de Compostela, Fundación", "Santiago de Compostela"),
    ]

    def test_cada_caso_le_se_coma_lugar(self):
        for texto, fragmento in self.CASOS:
            with self.subTest(fragmento=fragmento):
                self.assertTrue(_e_lugar(texto, fragmento))

    def test_sen_contexto_segue_sendo_persoa(self):
        self.assertFalse(_e_lugar("Fdo.: Valencia", "Valencia"))
        self.assertFalse(_e_lugar("Compareció Albacete en nombre propio", "Albacete"))

    def test_granada_nunha_direccion(self):
        self.assertEqual(_persoas("con domicilio en 18190 Cenes de la Vega, Granada, España. Ambas partes"), [])


class TestEncabezadosEOrganismos(unittest.TestCase):
    """Cada un tapábase coma PERSOA en main (956226d): formularios, termos e organismos."""

    CASOS = [
        "E, NA SÚA REPRESENTACIÓN E, NA SÚA REPRESENTACIÓN (deberá acreditarse a representación fidedigna)",
        "PERSOA FÍSICA OU XURÍDICA PRIVADA ENTIDADE LOCAL Nº PROVEDOR/A Nº FACTURA DATA",
        "PALABRAS CHAVE (poucas palabras separadas por ',') ÁMBITO DE PRIORIDADE RIS3",
        "la Ilma. Sra. Fiscal Jefa de la Fiscalía Provincial de León adoptó el acuerdo.",
        "para la obtención del título de Traductor Jurado deberán presentarse en la citada sede.",
        "Autoridad Independiente de Responsabilidad Fiscal, AAI de conformidad con lo establecido",
        "da Xerencia da Área Sanitaria de Vigo, polo que se dá publicidade á resolución.",
        "a Área Sanitaria de Lugo, A Mariña e Monforte de Lemos e a Área Sanitaria da Coruña.",
        "Convenio entre el Centro Docente CIFP Reina Victoria Eugenia Público y la empresa",
    ]

    def test_non_son_persoas(self):
        for texto in self.CASOS:
            with self.subTest(texto=texto[:50]):
                self.assertEqual(_persoas(texto), [])

    def test_persoa_con_tratamento_ou_con_nome_real_segue_tapada(self):
        self.assertEqual(_persoas("Compareció doña Fiscal Páez Veiga."), ["Fiscal Páez Veiga"])
        self.assertEqual(_persoas("Fdo.: Xoán Social Rodríguez"), ["Xoán Social Rodríguez"])


class TestNomeDeCentroEducativo(unittest.TestCase):
    """IES, CIFP, CEIP... son centros públicos e levan un nome detrás das siglas
    ("CIFP Reina Victoria Eugenia", BOE-A-2025-24517; "IES Antonio Machado")."""

    CIFP = (
        "Resolución por la que se publica el Convenio con CEE Reina Sofía, para el desarrollo de estancias "
        "formativas en el Centro Integrado de\n"
        "Formación Profesional Reina Victoria Eugenia de Melilla.\n"
        "ANEXO\n"
        "Convenio entre el Centro Docente CIFP Reina Victoria Eugenia Público\n"
        "y la empresa u organismo equiparado CEE Reina Sofía de las Ciudades\n"
        "De una parte, don Xoán Páez Veiga como director/a del centro\n"
        "educativo CIFP Reina Victoria Eugenia, localizado en Melilla, provincia de Melilla, en\n"
        "El centro docente CIFP Reina Victoria Eugenia nombrará, para cada persona en\n"
    )

    def test_nome_do_cifp_non_se_tapa_e_o_director_si(self):
        self.assertEqual(_persoas(self.CIFP), ["Xoán Páez Veiga"])

    def test_ies_e_ceip(self):
        self.assertEqual(_persoas("Profesorado destinado no IES Antonio Machado e no CEIP Concepción Arenal."), [])

    def test_persoa_despois_do_centro_cunha_coma_segue_tapada(self):
        self.assertEqual(_persoas("A directora do IES Xelmírez I, Ana Páez Veiga, asina o convenio."),
                         ["Ana Páez Veiga"])


if __name__ == "__main__":
    unittest.main()
