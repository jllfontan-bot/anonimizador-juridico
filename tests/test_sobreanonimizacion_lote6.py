"""Sobreanonimización do lote 6 (500 PDF de 2024): patróns atopados na metade de
DESENVOLVEMENTO (`corpus_web_lote6_2024/revision/particion_sobreanonimizacion.json`);
a metade de PROBA só se usa para medir. Casos sintéticos co contexto do real; os
controis comproban que a persoa parecida segue tapada."""
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


def _persoas(texto):
    entidades, _ = ner.detectar(texto)
    return [e.texto for e in entidades if e.etiqueta == "PERSOA"]


def _anonimizar(texto):
    with tempfile.TemporaryDirectory() as d:
        saida, _, substitucions = anonimizar_texto_detallado(texto, RexistroCorrespondencias(d))
    return saida, [(texto[a:b], novo) for a, b, novo in sorted(substitucions)]


class TestPeDoDog(unittest.TestCase):
    """O OCR do logotipo do pé do DOG ("Dr RUA 3 [OSOS 5% XUNTA DE GALICIA") tapábase coma
    persoa: 47 veces nun só documento da metade de desenvolvemento."""

    def test_lixo_do_logotipo_antes_de_xunta(self):
        for texto in [
            "funcións das policías locais.\nCVE-DOG: d2qivz23-kpk0-ixu8-wjo3-y9kxcystv1x7\nDr RUA 3 [OSOS 5% XUNTA DE "
            "GALICIA\nDiario Oficial de Galicia",
            # tal como sae do PDF real: o lixo en varias liñas
            "funcións das policías locais.\nCVE-DOG: d2qivz23-kpk0-ixu8-wjo3-y9kxcystv1x7\nDr RUA 3\n[OSOS\n5% XUNTA\n"
            "DE GALICIA\nDiario Oficial de Galicia",
            "CONSELLERÍA DE\nEMPREGO, COMERCIO 54 DE GALICIA | E EMIGRACIÓN Ela [a] dE En ao 5% XUNTA DE GALICIA\n"
            "Diario Oficial de Galicia",
        ]:
            for p in _persoas(texto):
                self.assertNotIn("RUA", p)
                self.assertNotIn("Ela", p)

    def test_control_asinante_xusto_antes_do_pe(self):
        saida, _ = _anonimizar("Santiago, 3 de xuño de 2024\nAna Salcedo Roel\nXefa territorial\n"
                               "CVE-DOG: d2qivz23-kpk0-ixu8-wjo3-y9kxcystv1x7\n5% XUNTA DE GALICIA")
        self.assertNotIn("Salcedo", saida)


class TestMunicipioCoArtigoDetras(unittest.TestCase):
    """BOE-A-2024-1230: "Tramitación P.A. Coruña, A. A Coruña" (municipio co artigo detrás,
    coma nas listaxes oficiais) líase coma "Apelidos, Nome": 19 veces."""

    def test_coruna_a_e_porrino_o(self):
        texto = ("1 Juzgado de Primera Instancia N.º 2. Tramitación P.A. Coruña, A. A Coruña. 1 Juzgado de Primera "
                 "Instancia e Instrucción N.º 1 (Reg. Civil). Tramitación P.A. Porriño, O. Pontevedra. 2")
        for p in _persoas(texto):
            self.assertNotIn("Coruña", p)
            self.assertNotIn("Porriño", p)

    def test_control_apelidos_e_inicial_a(self):
        self.assertIn("Salcedo Roel, A.", _persoas("Relación de aspirantes:\nSalcedo Roel, A.\nPáez Veiga, M."))


class TestMesmaPersoaEnDousAnacos(unittest.TestCase):
    """BOE-A-2024-7329 e -9426 ("Maria" e "Àngels Galán Viana": "dels" á vista) e
    AnuncioG0690-150124-0001_gl ("Antonio" e "Rodríguez Millán", dous códigos)."""

    def test_nome_catalan_cun_dels_no_medio(self):
        saida, substitucions = _anonimizar(
            "Madrid, 4 de marzo de 2024. –La Directora General para el Servicio Público de Justicia, Maria dels "
            "Àngels Fuster Viana. ANEXO I Pruebas selectivas")
        self.assertNotIn("dels", saida, substitucions)
        self.assertEqual(len({n for _, n in substitucions if n.startswith("PERSOA_")}), 1, substitucions)

    def test_nome_de_pia_nunha_liña_e_apelidos_na_seguinte(self):
        # FUGA na metade de desenvolvemento: na 2ª mención "Millán" quedaba á vista.
        saida, substitucions = _anonimizar(
            "DECRETO 2/2024, do 15 de xaneiro, polo que se dispón que cese Antonio\nFraga Millán como secretario "
            "xeral. Cesa, por petición propia, Antonio Fraga\nMillán como secretario xeral da Consellería.")
        self.assertNotIn("Millán", saida, substitucions)
        self.assertNotIn("Fraga", saida, substitucions)
        self.assertEqual(len({n for _, n in substitucions if n.startswith("PERSOA_")}), 1, substitucions)

    def test_control_lugar_e_data_na_liña_seguinte(self):
        saida, _ = _anonimizar("Asina Antonio Fraga\nMadrid, 3 de marzo de 2024.")
        self.assertIn("Madrid, 3 de marzo", saida)
        self.assertNotIn("Fraga", saida)

    def test_control_provincia_dunha_taboa_na_liña_seguinte(self):
        # Lote 5 sen ver (AnuncioG0759-090125-0007_gl): a columna da provincia, seguida do importe,
        # xuntábase ao nome coma se fose o segundo apelido ("Pontevedra" tamén é apelido do INE).
        saida, _ = _anonimizar("157 IF325B_2024-0564 ***6742** Carlos Abad Fontenla\nPontevedra 3.000,00 €\n-\n"
                               "158 IF325B_2024-0565 ***1822** Ana Salcedo Roel\nLugo 12.000,00 €")
        self.assertIn("Pontevedra 3.000,00", saida)
        self.assertIn("Lugo 12.000,00", saida)
        self.assertNotIn("Fraga", saida)

    def test_control_a_seguinte_liña_xa_e_outra_persoa_completa(self):
        _, substitucions = _anonimizar("Vogais: Ana Salcedo Roel\nBrais Páez Veiga\nUxía Castro Lago")
        self.assertEqual(len({n for _, n in substitucions if n.startswith("PERSOA_")}), 3, substitucions)

class TestDepartamentosEOrganismos(unittest.TestCase):
    """Nome dun departamento tras o cargo ou organismo, e "Autoridad Portuaria de ..."
    (metade de desenvolvemento do lote 6)."""

    def test_departamento_tras_cargo_ou_organismo(self):
        for texto, termo in [
            ("en la Instrucción de la Dirección General de Presupuestos y Fondos Europeos de 26 de diciembre de 2021 "
             "entre los entes.", "Fondos Europeos"),
            ("mediante a resolución da directora xeral do Tesouro e Política Financeira concedéuselle autorización.",
             "Tesouro"),
            ("Organismo Público: Autoridad Portuaria de Sevilla, Domicilio: Avda. de Moliní, nº 6.", "Sevilla"),
        ]:
            for p in _persoas(texto):
                self.assertNotIn(termo, p, texto)

    def test_control_persoa_tras_o_departamento(self):
        saida, _ = _anonimizar("La Directora General de Presupuestos y Fondos Europeos, Ana Salcedo Roel, firma el acuerdo.")
        self.assertNotIn("Salcedo", saida)
        self.assertIn("Fondos Europeos", saida)


class TestCasosSoltos(unittest.TestCase):
    """Casos soltos do lote 6 (petición do usuario do 12/10): non son persoas."""

    def casos(self):
        return [
            # concello só na súa liña nunha táboa (AnuncioG0692-250324-0015_gl); "Teo" tamén é nome de pía
            ("Alegacións\nOleiros\n90820312M\nEmenda solicitude\nTeo\nCVE-DOG: 2ag3kfx1-kfi3-xzq0-vyo6-x4g1yctmcvy9\n",
             "Teo"),
            # forma xurídica dunha fundación do sector público (BOE-B-2024-3210)
            ("Madrid, 24 de enero de 2024.- El Presidente de la Fundación Pluralismo y\nConvivencia, F. S.P., "
             "Brais Páez Veiga.\nID: A240003950-1", "F. S.P."),
            # rol e rótulo bilingüe (BOE-A-2024-4467)
            ("Ante este caso, el Técnico o Patrón de la tripulación avisará al Centro Coordinador.", "Patrón"),
            # formulario: cada rótulo na súa liña
            ("DATOS DE LA EMBARCACIÓN / RESCUE BOAT DETAILS\nNombre:\nName:\nMatrícula:\nRegistration nbr.:\n"
             "Indicativo:\nCall sign:\nPatrón:\nSkipper:\nN.º Póliza:\nInsurance nr.:\nCía. Aseguradora:\n", "Patrón"),
            ("DATOS DE LA EMBARCACIÓN / RESCUE BOAT DETAILS\nNombre:\nName:\nMatrícula:\nRegistration nbr.:\n"
             "Indicativo:\nCall sign:\nPatrón:\nSkipper:\nN.º Póliza:\nInsurance nr.:\nCía. Aseguradora:\n", "Póliza"),
            ("Correo electrónico:\nEmail address:\nN.º Póliza\nInssurance nr.\nTeléfono:\nTelephone nr.:\n", "Póliza"),
            # programa dun congreso (BOE-A-2024-9130)
            ("10:30 - 11:30 Sesiones Paralelas (I).\n11:30 - 12:00 Pausa café.\n12.00 - 14:00 Sesiones Paralelas.",
             "Pausa"),
            # titulación (AnuncioG0762-080524-...)
            ("da formación ou experiencia seguinte: 1º. Grao en Medicina. 2º. Grao en Enfermaría.", "Grao"),
            # planta fotovoltaica (BOE-A-2024-9382)
            ("Política Energética y Minas de 22 de noviembre de 2023 (FV Quilla Solar, SGEE/ PFot-172) y de 24 de abril",
             "Quilla"),
            # fondo europeo (AnuncioO92-271223-0001_gl)
            ("normas financeiras para os ditos fondos e para o Fondo de Asilo, Migración e Integración,\no Fondo de "
             "Seguridade Interior.", "Asilo"),
        ]

    def test_non_son_persoas(self):
        for texto, termo in self.casos():
            for p in _persoas(texto):
                self.assertNotIn(termo, p, texto)

    def test_controis(self):
        # o asinante da fundación segue tapado
        saida, _ = _anonimizar("El Presidente de la Fundación Pluralismo y\nConvivencia, F. S.P., Brais Páez Veiga.")
        self.assertNotIn("Páez", saida)
        # "Teo" coma nome dunha persoa, con apelidos, segue tapado
        saida, _ = _anonimizar("Comparece Teo Salcedo Roel, veciño de Ames, con DNI 12345678Z.")
        self.assertNotIn("Salcedo", saida)
        self.assertNotIn("Teo Salcedo", saida)
        # un nome tras unha franxa horaria (relator dun congreso) segue tapado
        saida, _ = _anonimizar("10:30 - 11:30 Conferencia inaugural: Ana Salcedo Roel.")
        self.assertNotIn("Salcedo", saida)


class TestCargoDianteDeApelidosNome(unittest.TestCase):
    """FUGA (lote 5 sen ver, AnuncioG2018-220425-0002_gl, medindo fronte á versión do 4/10):
    nas comisións de concursos "Presidente Lamela Pedrón, Manuel" quedaba enteiro á vista e
    de "Secretario Pichel Campos, Juan Carlos" só se tapaba o nome de pía. O cargo
    entraba nos apelidos e o recorte do cargo levaba o anaco enteiro."""

    TEXTO = ("Comisión titular\nPresidente Salcedo Roel, Ana\nCatedrática de universidade\nUniversidade de Santiago\n"
             "Secretario Páez Veiga, Xoán Carlos\nCatedrático de universidade\n"
             "1ª Vogal Castro Lago, María Xosé\nCatedrática de universidade\n"
             "Presidenta suplente Fraga Sáez, Uxía\nProfesora titular\n")

    def test_nomes_tapados_e_cargos_a_vista(self):
        saida, substitucions = _anonimizar(self.TEXTO)
        for anaco in ("Salcedo", "Roel, Ana", "Páez", "Xoán", "Castro Lago", "Fraga", "Uxía"):
            self.assertNotIn(anaco, saida, substitucions)
        for cargo in ("Presidente", "Secretario", "Vogal", "Presidenta suplente"):
            self.assertIn(cargo, saida, substitucions)
        self.assertEqual(len({n for _, n in substitucions if n.startswith("PERSOA_")}), 4, substitucions)

    def test_nomes_estranxeiros_na_comision(self):
        # Xa fallaba na versión do 4/10: o que non está nas táboas do INE quedaba á vista.
        saida, substitucions = _anonimizar(
            "Universidade de Santiago de Compostela\n2ª Vogal Gillanderby, Carol Jean\nProfesora titular de "
            "universidade Universidade de Vigo\n3º Vogal Maalemson Nasrullo, Nadeen\nProfesor/a axudante doutor/a\n"
            "3º Vogal Takkoucho Souilamo, El Bahi\nProfesor/a titular de universidade Universidade da Coruña\n")
        for anaco in ("Gillanderby", "Carol", "Mallahson", "Nadeen", "Takkoucho", "Bahi"):
            self.assertNotIn(anaco, saida, substitucions)

    def test_a_profesion_da_liña_seguinte_queda_a_vista(self):
        saida, substitucions = _anonimizar(
            "Comisión titular\nPresidente Salcedo Roel, Ana\nCatedrática de universidade\nUniversidade de Santiago\n"
            "1ª Vogal Castro Lago, María Xosé\nProfesora titular de universidade\n")
        self.assertIn("Catedrática de universidade", saida, substitucions)
        self.assertIn("Profesora titular", saida, substitucions)

    def test_control_cargo_de_organismo_co_nome_detras(self):
        # Medindo (BOE-A-2024-11766): "El Presidente de la CNMV, Rodrigo ..." tapaba tamén "de la CNMV".
        saida, substitucions = _anonimizar("Madrid, 3 de mayo de 2024. –El Presidente de la CNMV, Brais Páez Veiga.")
        self.assertIn("Presidente de la CNMV", saida, substitucions)
        self.assertNotIn("Páez", saida, substitucions)

    def test_cargo_con_calificativo_non_e_de_comision_e_conector_partido(self):
        # BOE-B-2025-14097 (lote 5 sen ver): "Provincial" tapábase coma apelido e "del\nAldana"
        # (conector ao final da liña, apelido na seguinte) quedaba á vista.
        saida, substitucions = _anonimizar(
            "Sevilla, 10 de abril de 2025.- Secretario Provincial, Manuel Figueroa del\nAldana.\nID: A250016528-1")
        self.assertIn("Secretario Provincial", saida, substitucions)
        self.assertNotIn("Aldana", saida, substitucions)
        self.assertNotIn("Figueroa", saida, substitucions)

    def test_conector_partido_e_dous_apelidos_na_seguinte(self):
        # BOE-A-2025-6823 (lote 5 sen ver): "Lydia del\nCampo Serrano": "Serrano" quedaba á vista.
        saida, substitucions = _anonimizar(
            "Madrid, 2 de abril de 2025. –La Secretaria de Estado de Comunicación, Ana del\nCampo Serrano.\nBOLETÍN")
        self.assertNotIn("Serrano", saida, substitucions)
        self.assertNotIn("Campo", saida, substitucions)
        saida, substitucions = _anonimizar("Lo firma Manuel Figueroa del\nAldana Presidente del Consejo.")
        self.assertNotIn("Aldana", saida, substitucions)
        self.assertIn("Presidente del Consejo", saida, substitucions)

    def test_control_san_tras_o_conector_e_un_lugar(self):
        # AnuncioG0597-221124-0010_gl (lote 6, proba): "Estadio Municipal Verónica Boquete de\nSan Lázaro".
        saida, substitucions = _anonimizar("no Estadio Municipal Ana Ferreiro de\nSan Lázaro, situado na avenida.")
        self.assertIn("San Lázaro", saida, substitucions)

    def test_a_profesion_na_mesma_liña_queda_a_vista(self):
        saida, substitucions = _anonimizar(
            "Comisión suplente\nPresidente Salcedo Roel, Ana Profesor titular de escola universitaria Universidade de "
            "Vigo\n1º Vogal Castro Lago, Brais Asociado\n3ª Vogal Páez Veiga, Uxía Contratada doutora\n")
        for profesion in ("Profesor titular", "Asociado", "Contratada doutora"):
            self.assertIn(profesion, saida, substitucions)
        for anaco in ("Salcedo", "Ana", "Castro", "Brais", "Páez", "Uxía"):
            self.assertNotIn(anaco, saida, substitucions)


if __name__ == "__main__":
    unittest.main()
