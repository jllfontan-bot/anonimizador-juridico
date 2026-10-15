import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador import ner, resolution
from anonimizador.pipeline import anonimizar_texto
from anonimizador.registry import RexistroCorrespondencias

import tempfile


def _persoas(texto):
    entidades, _ = ner.detectar(texto)
    return [e.texto for e in entidades if e.etiqueta == "PERSOA"]


class TestLimiteEntidadePersoa(unittest.TestCase):
    def test_recorta_verbo_absorbido_polo_ner(self):
        """Caso real: o modelo estendía a entidade ata incluír o verbo
        seguinte ("Xoana Veiga Lucas presentou")."""
        texto = "Xoana Veiga Lucas presentou o escrito de alegacións o luns."
        self.assertEqual(_persoas(texto), ["Xoana Veiga Lucas"])

    def test_recorta_palabra_solta_absorbida(self):
        texto = "Segundo o atestado, Xoana Veiga Lucas non estaba presente no lugar."
        self.assertEqual(_persoas(texto), ["Xoana Veiga Lucas"])

    def test_mantén_conector_lexitimo_do_apelido(self):
        """"de", "do", "van"... son conectores válidos de apelidos compostos
        e non se deben recortar aínda que vaian en minúscula."""
        texto = "O avogado Xoán de Cominges representou á familia."
        self.assertEqual(_persoas(texto), ["Xoán de Cominges"])

    def test_non_toca_entidade_xa_ben_delimitada(self):
        texto = "Manuel Ferrándiz Salcedo, con DNI 30014811Z, declarou."
        self.assertEqual(_persoas(texto), ["Manuel Ferrándiz Salcedo"])

    def test_texto_anonimizado_mantén_a_gramatica(self):
        """O verbo xa non debe desaparecer do texto final xunto co nome."""
        with tempfile.TemporaryDirectory() as d:
            rexistro = RexistroCorrespondencias(d)
            texto = "Xoana Veiga Lucas presentou o escrito de alegacións o luns."
            anon, _ = anonimizar_texto(texto, rexistro)
            self.assertIn("presentou", anon)
            self.assertNotIn("Xoana Veiga Lucas", anon)

    def test_estende_entidade_demasiado_curta_por_conector(self):
        """Caso real: nun bloque de sinatura dun informe de arquitecto, o
        NER só detectaba "LEANDRO", deixando fóra sen redactar "DEL VALLE
        RESUA" (o apelido composto, unido por un conector). Corrixido
        estendendo cara adiante mentres o padrón sexa conector + 1 ou 2
        palabras en maiúscula (`_estender_entidade_persoa`, baseado en
        `_CONTINUACION_NOME_PERSOA`) -- así "RESUA" (o segundo apelido,
        pegado directamente despois de "RIO" sen outro conector) tamén
        queda incluído, sen necesidade de permitir cadeas arbitrarias de
        palabras en maiúsculas soltas (o que fundiría persoas distintas
        nunha lista, ver `test_dous_nomes_en_maiusculas_na_mesma_frase`)."""
        texto = "LEANDRO DEL VALLE RESUA               ARQUITECTO"
        persoas = _persoas(texto)
        self.assertEqual(len(persoas), 1)
        self.assertEqual(persoas[0], "LEANDRO DEL VALLE RESUA")

    def test_estende_con_inicial_solta_e_espazo_dobre(self):
        """Caso real atopado revisando unha sinatura escaneada real: unha
        inicial solta ("M.", segundo nome) e espazos DOBRES entre
        palabras (habitual no texto que sae de `page.get_text()` en
        columnas xustificadas) facían que a extensión non funcionase en
        absoluto -- o "seguinte token" de spaCy despois de "Leandro" era
        o propio espazo dobre, non "M.", así que a persoa quedaba só
        coma "Leandro"."""
        texto = "Leandro  M.  del  Valle  Resua,  arquitecto  colegiado  nº 1234"
        persoas = _persoas(texto)
        self.assertEqual(len(persoas), 1)
        self.assertEqual(persoas[0], "Leandro  M.  del  Valle  Resua")

    def test_recorta_profesion_sen_conector_diante(self):
        """"ARQUITECTO" (coma outras profesións/cargos habituais en
        sinaturas e certificados) está na listaxe de palabras funcionais,
        así que se recorta igual ca calquera outra palabra que non forma
        parte do nome -- e nunca se estende cara a ela por non ir precedida
        de conector ningún."""
        texto = "Manuel Ferrándiz Salcedo ARQUITECTO"
        persoas = _persoas(texto)
        self.assertTrue(all("ARQUITECTO" not in p for p in persoas))

    def test_apelido_composto_sen_conector_antes_de_profesion(self):
        """Caso real: un apelido composto SEN conector ningún ("Veiga
        Lucas") quedaba fóra do nome no recoñecedor ancorado por
        profesión, que só detectaba a última palabra antes da coma
        ("Lorenzo"). Ese anaco parcial quedaba "ocupado", bloqueando
        despois a spaCy de detectar o nome completo (o solapamento xa
        estaba marcado coma ocupado)."""
        texto = "Xoana Veiga Lucas, secretaria da comunidade de propietarios, asinou a acta."
        self.assertEqual(_persoas(texto), ["Xoana Veiga Lucas"])

    def test_detecta_nome_e_profesion_separados_por_espazo_sen_coma(self):
        """Caso real atopado nun informe técnico real COMPLETO (non
        illado, 43 páxinas): a cabeceira "LEANDRO DEL VALLE RESUA
        ARQUITECTO" repítese en TODAS as páxinas, sen coma ningunha.
        Visualmente ten moito espazo de aliñamento entre nome e profesión,
        pero ese espazo NON sobrevive á extracción de texto do PDF
        (`_ensamblar_texto` recompón as palabras cun ÚNICO espazo) -- o
        texto que chega aquí é "Leandro del Valle Resua arquitecto", un
        espazo só. Aínda que a mesma frase illada xa está cuberta por
        `test_estende_entidade_demasiado_curta_por_conector` (vía
        `_estender_entidade_persoa`), no documento real completo spaCy
        nin sequera propuña "Leandro" coma PER nese contexto (rodeado do
        resto do informe) -- a extensión nunca chegaba a activarse porque
        non había nada que estender. Proba aquí o recoñecedor de reserva
        por patrón directamente (sen spaCy), que non depende de que o
        modelo acerte."""
        texto = "LEANDRO DEL VALLE RESUA ARQUITECTO"
        texto_suavizado = ner._suavizar_ordinais_para_deteccion(ner._suavizar_maiusculas_para_deteccion(texto))
        atopadas = ner._detectar_persoas_por_profesion(texto, texto_suavizado, [False] * len(texto))
        self.assertEqual([e.texto for e in atopadas], ["LEANDRO DEL VALLE RESUA"])


class TestDeteccionEnMaiusculas(unittest.TestCase):
    """Caso real (o de maior impacto atopado en toda a proba): un
    certificado de poder tiña "D/Dª JOSE LUIS LOPEZ RABADAN CON NIF..." en
    maiúsculas -- e o nome NON se detectaba coma persoa en absoluto,
    quedando completamente sen anonimizar. É un patrón extremadamente
    habitual en notas de poder, notas simples rexistrais e sinaturas de
    documentos oficiais españois."""

    def test_nome_completo_todo_en_maiusculas(self):
        self.assertEqual(_persoas("JOSE LUIS LOPEZ RABADAN"), ["JOSE LUIS LOPEZ RABADAN"])

    def test_caso_real_certificado_de_poder(self):
        texto = "D/Dª JOSE LUIS LOPEZ RABADAN CON NIF 12345678A CON DOMICILIO EN SANTIAGO"
        persoas = _persoas(texto)
        self.assertEqual(len(persoas), 1)
        self.assertIn("JOSE LUIS LOPEZ RABADAN", persoas[0])

    def test_non_confunde_palabras_funcionais_con_continuacion_do_nome(self):
        """"CON", "NIF", "DOMICILIO"... non deben quedar arrastradas coma
        se fosen parte do nome, mesmo cando todo o arredor está en
        maiúsculas coma o nome."""
        texto = "MANUEL FERRANDIZ SALCEDO CON DNI 30014811Z CON DOMICILIO EN VIGO"
        persoas = _persoas(texto)
        self.assertEqual(persoas, ["MANUEL FERRANDIZ SALCEDO"])

    def test_dous_nomes_en_maiusculas_na_mesma_frase(self):
        texto = "DON JOSE LOZANO MELERO Y DOÑA RITA MARTORELL VILELA COMPARECEN ANTE MI"
        persoas = _persoas(texto)
        self.assertEqual(len(persoas), 2)
        self.assertTrue(any("JOSE LOZANO MELERO" in p for p in persoas))
        self.assertTrue(any("RITA MARTORELL VILELA" in p for p in persoas))
        # o pronome "MI" (de "ante mí") non debe quedar coma unha terceira "persoa"
        self.assertFalse(any(p.strip() in ("MI", "Mi") for p in persoas))

    def test_institucion_en_maiusculas_non_se_detecta_coma_persoa(self):
        self.assertEqual(_persoas("MINISTERIO DE JUSTICIA"), [])

    def test_pipeline_redacta_o_nome_en_maiusculas(self):
        with tempfile.TemporaryDirectory() as d:
            rexistro = RexistroCorrespondencias(d)
            texto = "D/Dª JOSE LUIS LOPEZ RABADAN CON NIF 12345678A CON DOMICILIO EN SANTIAGO"
            anon, informe = anonimizar_texto(texto, rexistro)
            self.assertNotIn("JOSE LUIS LOPEZ RABADAN", anon)
            self.assertIn("PERSOA_", anon)
            self.assertEqual(len(informe["persoas"]), 1)


class TestNomesEnMinuscula(unittest.TestCase):
    """Caso real de revisión (A19): unha acta transcrita a man ten o nome
    do comparecente INTEGRAMENTE en minúscula ("comparece xosé manuel
    castro pereira") -- sen maiúscula inicial ningunha, nin spaCy nin
    ningún dos patróns de arriba (todos esixen maiúscula nalgún punto)
    tiña forma de recoñecelo. Esíxense dous anclaxes á vez (verbo de
    comparecencia diante + nome de pía coñecido) para non disparar con
    calquera racha de prosa normal en minúscula."""

    def test_nome_en_minuscula_tras_comparece(self):
        texto = "Comparece xosé manuel castro pereira, con domicilio en Vigo."
        self.assertEqual(_persoas(texto), ["xosé manuel castro pereira"])

    def test_nome_en_minuscula_tras_manifiesta(self):
        texto = "manifiesta ana lópez vázquez que está conforme co acordado."
        self.assertEqual(_persoas(texto), ["ana lópez vázquez"])

    def test_non_confunde_prosa_normal_sen_verbo_introdutor(self):
        """Sen un verbo de comparecencia diante, unha racha de palabras en
        minúscula (aínda que empece por un nome de pía coñecido) non debe
        tomarse por unha persoa -- demasiado ambiguo."""
        texto = "o interesado di que ana pediu máis prazo para presentar o escrito."
        self.assertEqual(_persoas(texto), [])

    def test_recorta_prosa_que_segue_ao_apelido(self):
        """A continuación en minúscula pode arrastrar palabras que xa NON
        son parte do nome (ex. "con domicilio...") -- recórtanse igual có
        recoñecedor de maiúsculas."""
        texto = "declara xoana vázquez lorenzo con domicilio en Ourense."
        self.assertEqual(_persoas(texto), ["xoana vázquez lorenzo"])

    def test_pipeline_redacta_o_nome_en_minuscula(self):
        with tempfile.TemporaryDirectory() as d:
            rexistro = RexistroCorrespondencias(d)
            texto = "Comparece xosé manuel castro pereira, con domicilio en Vigo."
            anon, informe = anonimizar_texto(texto, rexistro)
            self.assertNotIn("xosé manuel castro pereira", anon)
            self.assertIn("PERSOA_", anon)


class TestOrdinaisEHonorificos(unittest.TestCase):
    """Casos reais atopados revisando unha certificación de burofax: o
    propio caracter "ª"/"º" (indicador ordinal, coma en "Mª", "Dª", "nº")
    confundía o modelo de NER, que chegaba a fundir a persoa cunha
    ORGANIZACIÓN da liña anterior en vez de recoñecela coma PER."""

    def test_honorifico_ma_non_confunde_o_modelo(self):
        texto = (
            "VOLUME INVESTMENTS & REAL STATE, S.L.\n"
            "Mª Pilar Camacho Briones, Directora Gerente de Postal y "
            "Paquetería de dicha Sociedad, con poder otorgado ante el "
            "Notario de Santiago."
        )
        persoas = _persoas(texto)
        self.assertTrue(any("Pilar Camacho Briones" in p for p in persoas))

    def test_recoñecedor_de_reserva_por_tratamento_honorifico(self):
        """Caso real: "Documentacion\\nPor D. José Luis López Rabadán"
        etiquetábase enteiro coma MISC (non PER) por mor do texto veciño
        -- o nome quedaba sen redactar en absoluto. O recoñecedor de
        reserva por tratamento honorífico ("D.", "Don", "Doña", "D/Dª")
        cobre este caso sen depender do que decida o modelo."""
        texto = (
            "y 6872011NH3467B0001BF.\nDOCUMENTACION\n"
            "Por  D.  José  Luis López Rabadán  se  facilitó  al técnico "
            "que  suscribe  copia  de  los\nsiguientes documentos:\n"
        )
        persoas = _persoas(texto)
        self.assertTrue(any("José" in p and "López Rabadán" in p for p in persoas))

    def test_conxuncion_y_non_activa_o_recoñecedor_de_reserva(self):
        """"Y" (maiúscula solta) non debe confundirse cunha inicial nin
        cun conector -- se non, o recoñecedor de reserva fundiría dúas
        persoas enumeradas coma "D. Xoán... y Dña. María..." nunha soa.
        Non se esixe un total exacto de persoas: o propio spaCy ás veces
        detecta o tratamento honorífico ("Dña") coma unha entidade PER
        propia e separada, ademais das dúas persoas reais -- inofensivo
        (non é un dato persoal), pero non forma parte do que este test
        comproba."""
        texto = "Comparecen D. Xoán Boan Páez y Dña. María Nieves Salcedo Pozo, maiores de edad."
        persoas = _persoas(texto)
        self.assertTrue(any("Xoán Boan Páez" == p for p in persoas))
        self.assertTrue(any("María Nieves Salcedo Pozo" == p for p in persoas))
        self.assertFalse(any("Xoán Boan Páez y" in p or "Boan Páez y Dña" in p for p in persoas))


class TestDocumentosMoiLongos(unittest.TestCase):
    """Caso real: un documento técnico de 351 páxinas (1,3M caracteres)
    superaba o límite de 1.000.000 de caracteres de spaCy e facía fallar
    todo o pipeline cun ValueError."""

    def test_non_falla_por_riba_do_limite_de_spacy(self):
        texto_longo = "Manuel Ferrándiz Salcedo declarou perante o xulgado o día de hoxe. " * 20000
        self.assertGreater(len(texto_longo), 1_000_000)
        entidades, _ = ner.detectar(texto_longo)  # non debe lanzar ValueError
        persoas = [e for e in entidades if e.etiqueta == "PERSOA"]
        self.assertEqual(len(persoas), 20000)

    def test_non_rompe_unha_mencion_polo_medio_do_anaco(self):
        """Forzando anacos moi pequenos, ningunha mención debe quedar
        partida entre dous anacos."""
        tamano_orixinal = ner._TAMANO_MAXIMO_ANACO
        ner._TAMANO_MAXIMO_ANACO = 60
        try:
            texto = (
                "Manuel Ferrándiz Salcedo declarou perante o xulgado.\n"
                "Xoana Veiga Lucas presentou o escrito de alegacións.\n"
                "Rita Martorell Vilela foi testemuña do feito.\n"
            )
            self.assertGreater(len(ner._anacos_para_ner(texto)), 1)
            self.assertEqual(
                _persoas(texto),
                ["Manuel Ferrándiz Salcedo", "Xoana Veiga Lucas", "Rita Martorell Vilela"],
            )
        finally:
            ner._TAMANO_MAXIMO_ANACO = tamano_orixinal


def _exentos(texto):
    entidades, _ = ner.detectar(texto)
    return [e for e in entidades if e.etiqueta == "PERSOA_EXENTA_CARGO_PUBLICO"]


class TestCargoSoNonEPersoa(unittest.TestCase):
    """Gravidade Baixa (informe do 21/09/2026): a propia palabra dun
    cargo/profesión, SEN ningún nome real detrás, etiquetábase igual coma
    PERSOA -- caso real, "ante Notario" facía que "Notario" a secas
    saíse coma persoa (nin sequera coma exención por cargo público, xa
    que esa pasada precisa dun NOME ao que exentar -- ver
    `_e_soamente_prosa_ou_cargo`)."""

    def test_notario_a_secas_non_e_persoa(self):
        casos = [
            "Otorgado ante Notario en la ciudad de A Coruña.",
            "Comparece ante Notario para elevar a público el documento.",
            "La escritura se firmó ante Notario el día 5 de enero.",
            "El contrato consta en escritura pública ante Notario.",
        ]
        for texto in casos:
            with self.subTest(texto=texto):
                self.assertEqual(_persoas(texto), [])
                self.assertEqual(_exentos(texto), [])

    def test_notario_con_nome_real_segue_detectandose(self):
        texto = "Otorgado ante el Notario D. Xoán Páez Veiga en A Coruña."
        self.assertEqual(_persoas(texto), ["Xoán Páez Veiga"])


class TestExencionCargoPublico(unittest.TestCase):
    """Criterio da AEPD (Gabinete Xurídico N/REF 0049/2023, ver
    docs/criterios_anonimizacion_cendoj.pdf secc. 5): xuíces, maxistrados,
    letrados da Administración de Xustiza e médicos forenses, actuando en
    exercicio da súa función pública, non precisan anonimización."""

    def test_maxistrado_xuiz_antes_do_nome_con_honorifico(self):
        texto = "Vistos os autos polo Ilmo. Sr. Magistrado-Juez D. Xoán Páez Veiga, dítase a seguinte sentenza."
        self.assertEqual(_persoas(texto), [])
        exentos = _exentos(texto)
        self.assertEqual([e.texto for e in exentos], ["Xoán Páez Veiga"])
        self.assertIn("Magistrado-Juez", exentos[0].cargo)

    def test_laj_despois_do_nome_con_coma(self):
        texto = "María Lozano Veiga, Letrada de la Administración de Justicia, certifica o presente."
        self.assertEqual(_persoas(texto), [])
        self.assertEqual([e.texto for e in _exentos(texto)], ["María Lozano Veiga"])

    def test_medico_forense_exento_pero_medico_a_secas_non(self):
        texto = (
            "Recoñeceu o corpo o médico forense D. Antón Casal Rey.\n"
            "Tamén examinou a Xoana Veiga Lucas o médico de familia."
        )
        self.assertEqual(_persoas(texto), ["Xoana Veiga Lucas"])
        self.assertEqual([e.texto for e in _exentos(texto)], ["Antón Casal Rey"])

    def test_perito_non_se_exime(self):
        """Un perito (non funcionario público) SI hai que anonimizalo --
        a exención non debe alcanzar profesións comúns coma "arquitecto"."""
        texto = "Leandro del Valle Resua, arquitecto perito xudicial, presentou o informe."
        self.assertEqual(_persoas(texto), ["Leandro del Valle Resua"])
        self.assertEqual(_exentos(texto), [])

    def test_policia_identificado_por_nome_completo_non_se_exime(self):
        """A propia AEPD di que un axente identificado polo seu NOME
        COMPLETO (non só polo número profesional) SI hai que anonimizalo
        -- a exención NON debe cubrir "policía"/"garda civil"."""
        texto = "Acudiu ao lugar o Garda Civil D. Xoán Páez Veiga, que redactou o atestado."
        self.assertEqual(_persoas(texto), ["Xoán Páez Veiga"])
        self.assertEqual(_exentos(texto), [])

    def test_secretario_a_secas_non_se_exime(self):
        """"Secretario"/"secretaria" sen "xudicial"/"judicial" é un cargo
        habitual FÓRA do ámbito xudicial (empresa, comunidade de
        propietarios...) e non debe eximirse por confusión co LAJ."""
        texto = "Xoana Veiga Lucas traballa coma secretaria dunha comunidade de propietarios."
        self.assertEqual(_persoas(texto), ["Xoana Veiga Lucas"])
        self.assertEqual(_exentos(texto), [])

    def test_cargo_afastado_do_nome_non_se_exime(self):
        """O cargo ten que ir PEGADO ao nome -- unha mención afastada (outra
        frase, outra persoa polo medio) non debe arrastrar unha exención."""
        texto = (
            "O médico forense revisou o caso hai unhas semanas. "
            "Máis tarde, Xoana Veiga Lucas, veciña de Vigo, presentou unha reclamación."
        )
        self.assertEqual(_persoas(texto), ["Xoana Veiga Lucas"])
        self.assertEqual(_exentos(texto), [])

    def test_texto_anonimizado_non_redacta_o_exento_pero_si_a_outra_persoa(self):
        with tempfile.TemporaryDirectory() as d:
            rexistro = RexistroCorrespondencias(d)
            texto = (
                "Ante min, o Letrado da Administración de Xustiza D. Xoán Páez Veiga, "
                "comparece Xoana Veiga Lucas, que declara o seguinte."
            )
            anon, informe = anonimizar_texto(texto, rexistro)
            self.assertIn("Xoán Páez Veiga", anon)
            self.assertNotIn("Xoana Veiga Lucas", anon)
            self.assertEqual(
                [e["texto"] for e in informe["exentos_cargo_publico"]],
                ["Xoán Páez Veiga"],
            )


class TestEnumeracionDeAreasDunMinisterio(unittest.TestCase):
    """Corpus web 28/09/2026 (BOE/DOG reais): un ministerio ou consellería
    enumera as súas áreas coma "Ministerio de Educación, Formación
    Profesional y Deportes" -- casaba co patrón "Apelidos, Nome" e ningunha
    das dúas palabras era en si mesma un organismo coñecido
    (`_ORGANISMOS_RE`), así que quedaba tapada coma persoa."""

    def _anon(self, texto):
        with tempfile.TemporaryDirectory() as d:
            return anonimizar_texto(texto, RexistroCorrespondencias(d))

    def test_ministerio_castelan(self):
        anon, _ = self._anon(
            "puestos de trabajo en el Ministerio de Economía, Comercio y Empresa. "
            "De acuerdo con lo establecido en el artículo."
        )
        self.assertIn("Economía, Comercio y Empresa", anon)

    def test_ministerio_tres_areas(self):
        anon, _ = self._anon(
            "contiene los temas que el Ministerio de Educación, Formación Profesional "
            "y Deportes, en virtud de lo previsto."
        )
        self.assertIn("Educación, Formación Profesional", anon)

    def test_conselleria_galego(self):
        anon, _ = self._anon(
            "establece a estrutura orgánica da Consellería de Emprego, Comercio e "
            "Emigración, esta consellería asume o exercicio."
        )
        self.assertIn("Emprego, Comercio e", anon)

    def test_cabeceira_partida_en_varias_liñas(self):
        anon, _ = self._anon(
            "CONSELLERÍA\nDE\nEDUCACIÓN,\nCIENCIA,\nUNIVERSIDADES\nE\nFORMACIÓN PROFESIONAL\n"
            "ORDE do 6 de xullo de 2026."
        )
        self.assertIn("EDUCACIÓN,", anon)
        self.assertIn("CIENCIA,", anon)

    def test_non_afecta_a_persoas_reais_fora_de_organismo(self):
        """A garda só actúa cando hai un introdutor de organismo XUSTO
        antes -- unha enumeración de persoas normal segue a detectarse."""
        texto = "O xuíz chamou a Xoán Páez Veiga, María Lozano Duarte e Ana Salcedo Roel."
        self.assertEqual(
            _persoas(texto), ["Xoán Páez Veiga", "María Lozano Duarte", "Ana Salcedo Roel"])


class TestCargoAntesDoNomeSenHonorifico(unittest.TestCase):
    """Corpus web 28/09/2026 (BOE/DOG reais): un bloque de sinatura co
    cargo ANTES do nome, sen honorífico ("El Secretario General Técnico,
    Nome Apelidos") -- spaCy devolvía cargo+nome coma UNHA SOA entidade,
    redactando tamén o cargo (sobre-anonimización SEN marcar)."""

    def _mencions(self, texto):
        with tempfile.TemporaryDirectory() as d:
            _, informe = anonimizar_texto(texto, RexistroCorrespondencias(d))
        return [m for p in informe["persoas"] for m in p["mencions"]]

    def test_secretario_xeral_tecnico(self):
        self.assertEqual(
            self._mencions("El Secretario General Técnico, Juan Antonio Piedrafita Marín, resolvió el expediente."),
            ["Juan Antonio Piedrafita Marín"],
        )

    def test_subdirectora_xeral_con_de(self):
        self.assertEqual(
            self._mencions("La Subdirectora General de Planificación, Ana Marín Ferrer, firmó el acuerdo."),
            ["Ana Marín Ferrer"],
        )

    def test_titular_con_del(self):
        self.assertEqual(
            self._mencions("El Titular del Centro Concertado, Antonio Javier Aguilera Rubio, presentó la solicitud."),
            ["Antonio Javier Aguilera Rubio"],
        )

    def test_artigo_en_minuscula_no_medio_da_frase(self):
        """A entidade pode empezar en minúscula ("el") cando o bloque de
        sinatura non abre a frase ("...y el Secretario de Estado..."). O
        artigo importante é o do PROPIO INICIO da entidade, non a
        maiúscula/minúscula literal do texto."""
        self.assertEqual(
            self._mencions("y el Secretario de Estado de Cultura, Jordi Mateu Gea, firmó el convenio."),
            ["Jordi Mateu Gea"],
        )

    def test_non_afecta_a_persoas_normais(self):
        self.assertEqual(
            self._mencions("Comparece don Xoán Páez Veiga con DNI 30014811H."),
            ["Xoán Páez Veiga"],
        )

    def test_non_afecta_a_organismo_sen_persoa(self):
        self.assertEqual(self._mencions("El Ayuntamiento de Vigo, Pontevedra, convoca las ayudas."), [])


class TestListaxeApelidosNomeInverso(unittest.TestCase):
    """O recoñecedor de listaxes BOE "Apelidos, Nome" (`ner._detectar_
    persoas_apelidos_nome_inverso`) ten que distinguir un apelido real
    (1 ou 2 palabras) dunha soa palabra de prosa normal a inicio de
    frase que casualmente vai seguida de coma."""

    def test_palabra_solta_a_inicio_de_frase_non_se_confunde_co_apelido(self):
        """Caso real: unha soa palabra capitalizada de inicio de frase
        ("Despois,") seguida dun nome real confundíase coma se fose o
        "apelido" da listaxe, fundíndoa co nome ("Despois, Xoana
        Vázquez") e ademais recortando mal o final (perdendo "Lorenzo")."""
        texto = "Despois, Xoana Veiga Lucas, veciña de Vigo, presentou unha reclamación."
        self.assertEqual(_persoas(texto), ["Xoana Veiga Lucas"])

    def test_enumeracion_de_persoas_non_se_funde_nunha_soa(self):
        """A14 (revisión 21/09/2026): unha enumeración de varias persoas
        separadas por comas e rematada en "e"/"y" ("Xoán Páez Veiga,
        María Lozano Duarte e Ana Salcedo Roel") léase coma se fose UNHA soa
        entrada "Apelidos, Nome" de listaxe -- "Xoán Páez Veiga" coma
        apelidos e "María Lozano Duarte" coma nome, fundindo dúas persoas
        distintas nun só PERSOA_ e deixando a "Ana Salcedo Roel" á parte."""
        texto = "O xuíz chamou a Xoán Páez Veiga, María Lozano Duarte e Ana Salcedo Roel."
        self.assertEqual(
            _persoas(texto),
            ["Xoán Páez Veiga", "María Lozano Duarte", "Ana Salcedo Roel"],
        )

    def test_enumeracion_con_y_castelan_tampouco_se_funde(self):
        texto = "No rexistro constan Xoán Páez Veiga, María Lozano Duarte y Ana Salcedo Roel."
        self.assertEqual(
            _persoas(texto),
            ["Xoán Páez Veiga", "María Lozano Duarte", "Ana Salcedo Roel"],
        )

    def test_palabra_solta_tras_guion_non_se_funde_no_nome_veciño(self):
        """Bug real (medición v2, corpus sintético de 312 casos): nunha fila
        de listaxe "Apelidos, Nome - Turno" spaCy ás veces devolve "Nome -
        Turno" coma UNHA SOA entidade PER en vez de "Nome" e "Turno" á
        parte -- inconsistencia do propio modelo segundo o apelido (con
        "Barroso Cordeiro" spaCy SI as separa; con "Veiga Lucas" NON).
        Cando as funde, `_unir_con_persoa_existente` tratabao coma un
        apelido composto con guión ("Pérez-Vázquez") e absorbía "Turno" no
        nome da persoa veciña SEN deixar rastro -- nin redactado nin
        marcado para revisión, a diferenza do mesmo caso sen guión (onde
        "Turno" si queda coma mención "apelido solto" marcada). "Turno" ten
        que comportarse SEMPRE igual, tanto se spaCy a separa coma se non.
        Dende o 30/09/2026 (regra do INE) "Turno" xa nin se marca: non ten
        ningunha palabra nas táboas de nomes/apelidos, queda á vista nos
        dous casos e o nome da persoa segue enteiro redactado."""
        for apelidos in ("Barroso Cordeiro", "Veiga Lucas"):
            texto = f"Listaxe de persoal: {apelidos}, Sabela - Turno de mañá."
            with self.subTest(apelidos=apelidos):
                self.assertEqual(_persoas(texto), [f"{apelidos}, Sabela"])


class TestListaxeCelaPartidaEnDuasLinas(unittest.TestCase):
    """Corpus web 28/09/2026 (táboas reais do BOE en PDF): a cela
    "APELIDOS, NOME." pártese en dúas liñas e só se tapaba a segunda -- os
    apelidos quedaban á vista a carón do DNI parcial. Reprodución con
    nomes INVENTADOS."""

    def _anon(self, texto):
        with tempfile.TemporaryDirectory() as d:
            return anonimizar_texto(texto, RexistroCorrespondencias(d))

    def test_salto_despois_da_coma(self):
        anon, informe = self._anon("30\nBARROSO CORDEIRO,\nALDARA.\n***4521**\nA1\n")
        for resto in ("BARREIRO", "NOGUEIRA", "ALDARA"):
            self.assertNotIn(resto, anon)
        self.assertEqual(len(informe["persoas"]), 1)

    def test_un_so_apelido_non_se_detectaba_en_absoluto(self):
        anon, _ = self._anon("Puesto adjudicado\nOTERO,\nANTÍA.\n***1122**\n")
        self.assertNotIn("OTERO", anon)
        self.assertNotIn("ANTÍA", anon)

    def test_salto_dentro_dos_apelidos_tras_conector(self):
        anon, informe = self._anon("29\nVEIGA LUCAS DE LA\nTORRE, XOÁN.\n***9876**\nA1\n")
        for resto in ("VEIGA", "LUCAS", "TORRE", "XOÁN"):
            self.assertNotIn(resto, anon)
        self.assertEqual(len(informe["persoas"]), 1)

    def test_mesma_persoa_nunha_e_dúas_liñas_leva_o_mesmo_codigo(self):
        anon, informe = self._anon("BARROSO CORDEIRO,\nALDARA.\n***4521**\nBARROSO CORDEIRO, ALDARA\n")
        self.assertEqual(len(informe["persoas"]), 1)

    def test_cela_en_tres_linas_sen_conector(self):
        """Caso real: "CABAÑAS\\nGALAN,\\nCELIA." -- o primeiro apelido
        quedaba á vista (salto entre apelidos sen conector)."""
        anon, informe = self._anon("MADRID.\n28\nOTERO\nLORENZO,\nANTÍA.\n******8168\nA0011\n")
        for resto in ("OTERO", "LORENZO", "ANTÍA"):
            self.assertNotIn(resto, anon)
        self.assertIn("MADRID.", anon)
        self.assertEqual(len(informe["persoas"]), 1)

    def test_prosa_partida_non_se_toma_por_cela(self):
        """O nome ten que rematar a liña: prosa partida ao chou ("Despois,\\n
        María ... asinou") non ten forma de cela."""
        self.assertNotIn("Despois,\nMaría Lozano Duarte", _persoas("Despois,\nMaría Lozano Duarte asinou.\n"))
        self.assertEqual(
            [p for p in _persoas("o informe de Vázquez,\nque asinou o perito.\n") if "\n" in p], [])


class TestDniPorOrdeRespectivamente(unittest.TestCase):
    """A15 (revisión 21/09/2026): "persoa1 e persoa2, con DNI d1 e d2
    respectivamente" ten que emparellar POR ORDE, non polo veciño máis
    próximo (`resolution._asociar_dnis`) -- se non, os dous DNI
    intercámbianse entre as persoas."""

    def _dnis_por_nome(self, texto):
        entidades, _ = ner.detectar(texto)
        grupos = resolution.agrupar(entidades, texto)
        return {g.representante: g.dni for g in grupos}

    def test_non_intercambia_os_dni(self):
        texto = "Xoán Páez Veiga e María Lozano Duarte, con DNI 11111111H e 22222222J respectivamente"
        dnis = self._dnis_por_nome(texto)
        self.assertEqual(dnis["Xoán Páez Veiga"], "11111111H")
        self.assertEqual(dnis["María Lozano Duarte"], "22222222J")

    def test_tres_persoas_por_orde(self):
        texto = (
            "Xoán Páez Veiga, María Lozano Duarte e Ana Salcedo Roel, con DNI "
            "11111111H, 22222222J e 33333333P respectivamente"
        )
        dnis = self._dnis_por_nome(texto)
        self.assertEqual(dnis["Xoán Páez Veiga"], "11111111H")
        self.assertEqual(dnis["María Lozano Duarte"], "22222222J")
        self.assertEqual(dnis["Ana Salcedo Roel"], "33333333P")

    def test_sen_respectivamente_segue_usando_o_veciño_mais_preto(self):
        """Sen a palabra "respectivamente" non hai sinal de orde: o
        comportamento xeral (DNI asociado á mención máis próxima) non
        debe cambiar."""
        texto = "Comparece Xoán Páez Veiga. Máis tarde declara María Lozano Duarte, DNI 22222222J."
        dnis = self._dnis_por_nome(texto)
        self.assertIsNone(dnis["Xoán Páez Veiga"])
        self.assertEqual(dnis["María Lozano Duarte"], "22222222J")


def _anonimizar(texto):
    with tempfile.TemporaryDirectory() as d:
        anon, informe = anonimizar_texto(texto, RexistroCorrespondencias(d))
    return anon, informe


class TestNomesParciais(unittest.TestCase):
    """Fugas parciais de nomes: o recoñecedor por patrón (tratamento ou
    profesión) capturaba só un anaco do nome, e a entidade completa de
    spaCy descartábase por solapar con el -- o resto do nome quedaba en
    claro. Tamén nomes de pía que spaCy deixaba fóra da entidade."""

    CASOS = [
        ("Comparece D. Xoán de la Fuente Pérez, maior de idade.",
         ["Xoán", "Fuente", "Pérez"], ["Comparece D.", "maior de idade"]),
        ("Dña. María de las Nieves Salcedo Roel",
         ["María", "Nieves", "Salcedo", "Roel"], ["Dña."]),
        ("Comparece D. Xoán Pérez-Vázquez Souto, maior de idade.",
         ["Xoán", "Pérez", "Vázquez", "Souto"], ["Comparece D.", "maior de idade"]),
        ("Dña. Ana María Ortega y Gasset",
         ["Ana", "María", "Ortega", "Gasset"], ["Dña."]),
        ("D. Seán O'Donnell Pérez",
         ["Seán", "Donnell", "Pérez"], ["D."]),
        ("D. XOÁN DE LA FUENTE PÉREZ",
         ["XOÁN", "FUENTE", "PÉREZ"], ["D."]),
        ("Xoán Pérez-Vázquez Souto, arquitecto, asina.",
         ["Xoán", "Pérez", "Vázquez", "Souto"], ["arquitecto, asina"]),
        ("Informe Xosé Manuel Carballo Portela sobre a obra.",
         ["Xosé", "Manuel", "Castro", "Pereira"], ["Informe", "sobre a obra"]),
        ("Resolución 1332 de Xosé Manuel Carballo Portela.",
         ["Xosé", "Manuel", "Castro", "Pereira"], ["Resolución 1332 de"]),
    ]

    def test_ningunha_parte_do_nome_queda_en_claro(self):
        for texto, anacos_nome, contexto in self.CASOS:
            with self.subTest(texto=texto):
                anon, _ = _anonimizar(texto)
                for anaco in anacos_nome:
                    self.assertNotIn(anaco, anon)
                for anaco in contexto:
                    self.assertIn(anaco, anon)
                self.assertEqual(anon.count("PERSOA_"), 1, anon)

    def test_dous_comparecentes_con_apelidos_compostos_non_se_funden(self):
        texto = "Comparecen D. Xoán de la Fuente Pérez y Dña. María Pérez-Vázquez Souto."
        anon, informe = _anonimizar(texto)
        self.assertEqual(len(informe["persoas"]), 2, anon)
        self.assertIn(" y Dña. ", anon)


class TestExencionCargoPublicoPreposicion(unittest.TestCase):
    """En castelán "a" entre o cargo e o nome é preposición ("o
    Magistrado impúxolle a D. X"), non artigo: o nome non é o do cargo."""

    def test_preposicion_a_non_exime(self):
        casos = [
            ("Na vista, el Magistrado a D. Xoán Páez Veiga le impuso una multa.",
             "Xoán Páez Veiga"),
            ("Notificada por la jueza a la Sra. María Lozano Duarte la resolución.",
             "María Lozano Duarte"),
            ("Firma la LAJ a D. Xoán Páez Veiga", "Xoán Páez Veiga"),
        ]
        for texto, nome in casos:
            with self.subTest(texto=texto):
                self.assertEqual(_exentos(texto), [])
                anon, _ = _anonimizar(texto)
                self.assertNotIn(nome, anon)
                for palabra in nome.split():
                    self.assertNotIn(palabra, anon)

    def test_cargo_so_non_se_toma_por_persoa(self):
        anon, _ = _anonimizar("Firma la LAJ a D. Xoán Páez Veiga")
        self.assertIn("Firma la LAJ a D. ", anon)

    def test_exencion_galega_segue_funcionando(self):
        for texto, nome in [
            ("Ditou a sentenza o xuíz D. Xoán Páez Veiga.", "Xoán Páez Veiga"),
            ("Presidiu a vista a maxistrada Dª María Lozano Duarte.", "María Lozano Duarte"),
        ]:
            with self.subTest(texto=texto):
                self.assertEqual([e.texto for e in _exentos(texto)], [nome])


class TestPersoaNonCruzaLinas(unittest.TestCase):
    """Bug crítico (mestura de identidades): nun .docx os parágrafos
    únense con "\n" e spaCy devolvía UNHA soa PER que cruzaba varias
    liñas; tres persoas distintas acababan co mesmo código e co DNI dunha
    delas. Ningunha PERSOA pode conter un salto de liña ou de páxina."""

    TEXTO = (
        "Comparece tamén Brais Lorenzo Ogando Fandiño\n"
        "Testemuña: Rosa María Varela Doval\n"
        "Despacho de Xosé Manuel Carballo Portela, DNI 30014811Z"
    )
    NOMES = ["Brais Lorenzo Ogando Fandiño", "Rosa María Varela Doval", "Xosé Manuel Carballo Portela"]

    def _persoas_calquera(self, texto):
        entidades, _ = ner.detectar(texto)
        return entidades, [e for e in entidades if e.etiqueta.startswith("PERSOA")]

    def test_ningunha_persoa_contén_salto_de_lina(self):
        for texto in [
            self.TEXTO,
            "Demandante: D. Xoán Páez Veiga\nJuez: D. Luis Salcedo Roel",
            "Brais Lorenzo Ogando Fandiño\fRosa María Varela Doval, arquitecta",
        ]:
            with self.subTest(texto=texto):
                _, persoas = self._persoas_calquera(texto)
                self.assertTrue(persoas)
                for p in persoas:
                    self.assertNotIn("\n", p.texto)
                    self.assertNotIn("\f", p.texto)

    def test_tres_persoas_distintas_sen_etiquetas(self):
        entidades, persoas = self._persoas_calquera(self.TEXTO)
        self.assertEqual([p.texto for p in persoas], self.NOMES)
        self.assertTrue(all(p.etiqueta == "PERSOA" for p in persoas))
        grupos = resolution.agrupar(entidades, self.TEXTO)
        dni_por_nome = {g.representante: g.dni for g in grupos}
        self.assertEqual(dni_por_nome["Brais Lorenzo Ogando Fandiño"], None)
        self.assertEqual(dni_por_nome["Rosa María Varela Doval"], None)
        self.assertIsNotNone(dni_por_nome["Xosé Manuel Carballo Portela"])

    def test_pipeline_da_codigos_distintos(self):
        anon, informe = _anonimizar(self.TEXTO)
        for nome in self.NOMES:
            for palabra in nome.split():
                self.assertNotIn(palabra, anon)
        self.assertIn("\nTestemuña: ", anon)
        self.assertIn("\nDespacho de ", anon)
        codigos = [p["codigo"] for p in informe["persoas"]]
        self.assertEqual(len(codigos), 3)
        self.assertEqual(len(set(codigos)), 3)
        self.assertEqual(sorted(m for p in informe["persoas"] for m in p["mencions"]), sorted(self.NOMES))

    def test_nome_tras_tratamento_non_pasa_a_lina_seguinte(self):
        texto = "Demandante: D. Xoán Páez Veiga\nJuez: D. Luis Salcedo Roel"
        _, persoas = self._persoas_calquera(texto)
        textos = [p.texto for p in persoas]
        self.assertIn("Xoán Páez Veiga", textos)
        self.assertIn("Luis Salcedo Roel", textos)
        self.assertFalse(any("Juez" in t or "Demandante" in t for t in textos))
        # "Juez:" é a etiqueta da liña seguinte, non o cargo do demandante
        demandante = next(p for p in persoas if p.texto == "Xoán Páez Veiga")
        self.assertEqual(demandante.etiqueta, "PERSOA")
        anon, _ = _anonimizar(texto)
        self.assertNotIn("Xoán", anon)
        self.assertIn("Demandante: D. ", anon)
        self.assertIn("\nJuez: D. ", anon)

    def test_apelido_partido_por_axuste_de_marxe_segue_redactado(self):
        anon, _ = _anonimizar("Por D. José Luis López\nRabadán se facilitó copia.")
        for palabra in ["José", "Luis", "López", "Rabadán"]:
            self.assertNotIn(palabra, anon)


if __name__ == "__main__":
    unittest.main()


class TestCorpusWebHonorificoESinatura(unittest.TestCase):
    """Corpus web 28/09/2026 (BOE real), reproducido con nomes INVENTADOS."""

    def test_dona_en_minuscula_con_cargo_sen_coma(self):
        """"Nombrar a doña X Secretaria General del Consorcio": o nome non
        se detectaba en absoluto (tratamento en minúscula + cargo pegado)."""
        anon, _ = _anonimizar(
            "resuelvo: Nombrar a doña Uxía Barroso Cordeiro Secretaria General del Consorcio de la Zona Especial.")
        for resto in ("Uxía", "Barroso", "Cordeiro"):
            self.assertNotIn(resto, anon)
        self.assertIn("Secretaria General del Consorcio", anon)

    def test_don_en_minuscula_con_cargo_e_organismo(self):
        anon, _ = _anonimizar(
            "De una parte, don Breixo Fiolleda Outeiral Alcalde-Presidente del Ayuntamiento de Lalín.")
        for resto in ("Breixo", "Fiolleda", "Outeiral"):
            self.assertNotIn(resto, anon)
        self.assertIn("Alcalde-Presidente del Ayuntamiento", anon)

    def test_don_dona_en_minuscula_sen_nome_non_se_tocan(self):
        anon, informe = _anonimizar("Ten un don especial para a música. A dona da casa chegou tarde.")
        self.assertEqual(informe["persoas"], [])

    def test_apelido_da_sinatura_na_liña_seguinte(self):
        """"...–La Subsecretaria de Hacienda, Nome Apelido1\\nApelido2.": o
        segundo apelido quedaba á vista (spaCy tomábao coma lugar)."""
        anon, informe = _anonimizar(
            "Madrid, 2 de septiembre de 2026.–La Subsecretaria de Hacienda, Lidia Sáez\nMateu.\nANEXO\n")
        self.assertNotIn("Sánchez", anon)
        self.assertNotIn("Milán", anon)
        self.assertIn("ANEXO", anon)
        self.assertEqual(len(informe["persoas"]), 1)

    def test_cabeceira_institucional_partida_non_e_persoa(self):
        """Caso real (corpus web, 28/09/2026): a cabeceira "Educación,
        Ciencia, Universidades e Formación Profesional" dun DOG, partida en
        varias liñas polo axuste do PDF, casaba co patrón "Apelidos,\\nNome"
        ("Ciencia,\\nUniversidades") e quedaba SEN filtrar coma persoa --
        "universidade"/"universidad" non casaban co plural "universidades"
        en `_ORGANISMOS_RE` (o "s" final rompía o límite de palabra)."""
        anon, _ = _anonimizar(
            "CONSELLERÍA\nDE\nEDUCACIÓN,\nCIENCIA,\nUNIVERSIDADES\nE\nFORMACIÓN PROFESIONAL\n"
            "ORDE do 6 de xullo de 2026."
        )
        self.assertIn("UNIVERSIDADES", anon)
        self.assertIn("FORMACIÓN PROFESIONAL", anon)

    def test_epigrafe_tras_sinatura_non_se_absorbe(self):
        anon, _ = _anonimizar("Firmado por Antía Carballo Portela\nAnexo.\n")
        self.assertIn("Anexo.", anon)
        anon, _ = _anonimizar("O informe presentouno Xoán Páez Veiga\nMadrid, 3 de outubro.\n")
        self.assertIn("Madrid, 3 de outubro.", anon)


class TestCveDogNonEPersoa(unittest.TestCase):
    """Caso real (corpus web, 29/09/2026): o pé de páxina do DOG "CVE-DOG:
    <hash>" repítese en cada páxina dun documento. A suavización de
    maiúsculas (`_suavizar_maiusculas_para_deteccion`) deixaba "CVE-DOG" en
    Title Case ("Cve-Dog"), coa forma exacta dun apelido composto
    ("Pérez-Vázquez") -- spaCy clasificábao coma PERSOA en gran parte das
    aparicións, pero NON en todas: documento real de 147 páxinas, coa MESMA
    liña "CVE-DOG: <mesmo hash>" repetida 147 veces, 20 delas trocadas por
    un código de persoa e as outras 127 intactas -- a clasificación de
    spaCy depende do contexto veciño de cada páxina, non do texto en si.
    "CVE-DOG" é unha etiqueta de documento, nunca un dato persoal."""

    def test_unha_soa_aparicion_non_se_toca(self):
        anon, informe = _anonimizar(
            "RESOLUCIÓN do 5 de setembro de 2026.\n\nCVE-DOG: vkaucs15-xau1-2na8-hbq6-ncoqegbnjm18\n"
        )
        self.assertIn("CVE-DOG", anon)
        self.assertEqual(informe["persoas"], [])

    def test_repeticion_en_moitas_paxinas_variadas_non_se_toca(self):
        """Reproduce a inconsistencia real: sen o arranxo, spaCy marcaba
        coma PERSOA unha parte (non todas) das aparicións repetidas cando
        cada unha ía rodeada de contido distinto, coma páxinas dun DOG."""
        cabeceiras = [
            "DOG Núm. 198-Bis Xoves, 8 de outubro de 2026 Páx. {n}",
            "DOG Núm. 198 Mércores, 7 de outubro de 2026 Páx. {n}",
        ]
        frases = [
            "RESOLUCIÓN do 5 de setembro de 2026 pola que se convocan probas "
            "selectivas para o ingreso no corpo administrativo da Xunta de Galicia.",
            "A consellería de Facenda e Administración Pública fai pública a "
            "listaxe definitiva de persoas admitidas e excluídas no proceso.",
            "O tribunal cualificador estará composto por un presidente ou "
            "presidenta, catro vogais e un secretario ou secretaria.",
            "Contra esta resolución poderase interpoñer recurso potestativo de "
            "reposición ante o mesmo órgano que a ditou, no prazo dun mes.",
        ]
        sinaturas = [
            "Santiago de Compostela, 5 de outubro de 2026\nA directora xeral da Función Pública\n"
            "Ánxela Fernández Rodríguez",
            "Santiago de Compostela, 6 de outubro de 2026\nO secretario xeral técnico\n"
            "Xosé Manuel Iglesias Vilas",
        ]
        hash_cve = "vkaucs15-xau1-2na8-hbq6-ncoqegbnjm18"
        paxinas = []
        for n in range(60):
            cab = cabeceiras[n % len(cabeceiras)].format(n=12000 + n)
            corpo = " ".join(frases[i % len(frases)] for i in range(n, n + 3))
            sinatura = sinaturas[n % len(sinaturas)]
            paxinas.append(f"{cab}\n\n{corpo}\n\n{sinatura}\n\nCVE-DOG: {hash_cve}")
        texto = "\n\n".join(paxinas)

        anon, informe = _anonimizar(texto)
        self.assertEqual(anon.count("CVE-DOG"), 60)
        for persoa in informe["persoas"]:
            for mencion in persoa.get("mencions", []):
                self.assertNotIn("cve", mencion.lower())


class TestFalsosPositivosCorpusWeb(unittest.TestCase):
    """Corpus web 29/09/2026 (BOE/DOG reais), reproducido con texto
    sintético: etiquetas, siglas e normas tomadas por persoas."""

    def _sen_persoas(self, texto):
        anon, informe = _anonimizar(texto)
        self.assertEqual(informe["persoas"], [], anon)
        self.assertEqual(anon, texto)

    def test_marxe_cve_do_boe(self):
        self._sen_persoas("cve: BOE-A-2026-19351\nVerificable en https://www.boe.es")

    def test_sigla_boe_no_texto(self):
        self._sen_persoas("segundo o cal esta notificación ten que ser feita no BOE e a súa data de publicación.")
        self._sen_persoas("único (TEU) do Boletín Oficial del Estado (BOE).")

    def test_lei_en_galego(self):
        self._sen_persoas("De conformidade co disposto no artigo 46 da Lei 39/2015, do 1 de outubro.")
        self._sen_persoas("tigo 33.2 da Lei orgánica 2/1979, do 3 de outubro, do Tribunal Constitucional.")
        self._sen_persoas("condicións establecidas no artigo 28 do Regulamento da Lei 2/2016, do 10 de febreiro.")

    def test_presupuestos_generales_del_estado(self):
        self._sen_persoas("En virtud de la disposición adicional de la Ley 11/2020, de Presupuestos "
                          "Generales del Estado para el año 2021.")

    def test_logotipo_da_xunta_lido_por_ocr(self):
        self._sen_persoas("a 5% XUNTA\nPEE Pé DE GALICIA\nDOG Núm. 165")

    def test_rotulo_persoa_interesada(self):
        anon, informe = _anonimizar("Persoa interesada/DNI\nRosa Varela Doval")
        self.assertIn("Persoa interesada/DNI", anon)
        self.assertEqual(len(informe["persoas"]), 1)

    def test_nome_real_con_lei_segue_redactandose(self):
        anon, _ = _anonimizar("Comparece Lei Wang, con DNI 30014811H.")
        self.assertNotIn("Wang", anon)
        self.assertNotIn("Lei", anon)


class TestPendentesMenoresCorpusWeb(unittest.TestCase):
    """Corpus web 29/09/2026 (DOG real), reproducido con texto sintético."""

    def _persoas(self, texto):
        entidades, _ = ner.detectar(texto)
        return [e.texto for e in entidades if e.etiqueta == "PERSOA"]

    def test_verbo_a_inicio_de_frase_non_entra_no_nome(self):
        for verbo in ("Asina", "Informa", "Firma", "Comparece", "Declara", "Solicita"):
            texto = f"{verbo} Uxía Barroso Cordeiro o día de hoxe."
            self.assertEqual(self._persoas(texto), ["Uxía Barroso Cordeiro"], texto)
        anon, _ = _anonimizar("Asina Uxía Barroso Cordeiro.")
        self.assertEqual(anon, "Asina PERSOA_000001.")

    def test_marca_con_maiusculas_no_medio_non_e_persoa(self):
        for texto in (
            "Bases reguladoras das axudas da Axencia Galega de Innovación ao abeiro da convocatoria VInnovate Galicia",
            "Os proxectos desta convocatoria VInnovate Galicia deberán realizarse sempre en cooperación.",
            "Proxectos financiados no mecanismo de financiamento interrexional VInnovate que pertenzan a países distintos.",
        ):
            self.assertEqual(self._persoas(texto), [], texto)

    def test_topónimos_tras_monte_ou_parroquia_non_son_persoa(self):
        for texto in (
            "Límite proposto para o MVMC Acevedo",
            "REVISIÓN DE ESBOZO DO MVMC ACEVEDO",
            "Localización: Parroquia da Pereira, Concello de Entrimo - Ourense.",
        ):
            self.assertEqual(self._persoas(texto), [], texto)

    def test_persoa_con_apelido_de_lugar_segue_redactandose(self):
        self.assertEqual(self._persoas("Comparece Manuel Acevedo Pereira ante o xulgado."), ["Manuel Acevedo Pereira"])


class TestVocabularioDeFormulariosCorpusWeb(unittest.TestCase):
    """Corpus web 29/09/2026 (formularios en branco e bases do DOG): cabeceiras
    e verbos capitalizados que spaCy toma por persoas."""

    def _sen_persoas(self, texto):
        entidades, _ = ner.detectar(texto)
        self.assertEqual([e.texto for e in entidades if e.etiqueta == "PERSOA"], [], texto)

    def test_cabeceiras_de_formulario_en_maiusculas(self):
        self._sen_persoas("PERSOA SOLICITANTE OU REPRESENTANTE DECLARA que non solicitou outra axuda.")
        self._sen_persoas("1.1. PERSOAL PROPIO3\nTOTAL")
        self._sen_persoas("DESCRICIÓN DETALLADA CATEGORÍA (COMPRA OU LEASING) ACRÓNIMO DA ACTIVIDADE "
                          "IMPORTE DE ADQUISICIÓN DATA DE ADQUISICIÓN")

    def test_palabra_de_prosa_a_inicio_de_item(self):
        self._sen_persoas("1. Só no caso das pemes poderán subvencionarse os custos de persoal directivo.")
        self._sen_persoas("O prazo establecido na resolución de concesión da axuda.\n"
                          "Artigo 6. Prazo de presentación das solicitudes")

    def test_sigla_solta_de_duas_letras(self):
        self._sen_persoas("SY")

    def test_verbo_no_infinitivo_tras_marcador_de_lista(self):
        entidades, _ = ner.detectar("1. Nombrar al Dr. Francisco Javier Carracedo Cano para la plaza.")
        self.assertEqual([e.texto for e in entidades if e.etiqueta == "PERSOA"],
                         ["Francisco Javier Carracedo Cano"])

    def test_particula_minuscula_do_apelido_non_se_recorta(self):
        entidades, _ = ner.detectar("Comparece van der Berg Souto ante o xulgado.")
        self.assertEqual([e.texto for e in entidades if e.etiqueta == "PERSOA"], ["van der Berg Souto"])

    def test_fragmento_de_palabra_partida_a_final_de_liña(self):
        from anonimizador.recognizers import Entidade
        texto = "o contido parcial da Re-\nsolución do 7 de setembro"
        i = texto.index("Re-")
        self.assertTrue(ner._e_fragmento_de_palabra(Entidade(i, i + 3, "Re-", "PERSOA"), texto))
        texto2 = "Comparece Ana-\nMaría Pérez Souto"
        j = texto2.index("Ana-")
        self.assertFalse(ner._e_fragmento_de_palabra(Entidade(j, j + 4, "Ana-", "PERSOA"), texto2))

    def test_verbo_reflexivo_a_inicio_non_e_persoa(self):
        entidades, _ = ner.detectar("Publicouse no Diario Oficial o contido da resolución.")
        self.assertEqual([e.texto for e in entidades if e.etiqueta == "PERSOA"], [])

    def test_cargo_catedratico_so_non_e_persoa(self):
        entidades, _ = ner.detectar("Agregado a Catedrático contratado o Catedrática contratada, resuelvo:")
        self.assertEqual([e.texto for e in entidades if e.etiqueta == "PERSOA"], [])


class TestLecturaHumanaMostraPdf(unittest.TestCase):
    """Marcas do usuario na lectura visual de 13 PDF reais (30/09/2026),
    reproducidas con texto sintético (os nomes son inventados)."""

    def _persoas(self, texto):
        entidades, _ = ner.detectar(texto)
        return [e.texto for e in entidades if e.etiqueta == "PERSOA"]

    def test_siglas_e_substantivos_sen_palabra_do_ine(self):
        for texto in (
            "computar como deuda en la CIR (Central de información de Riesgos) del Banco de España.",
            "El MAPA y ENISA coinciden en la convicción de que las pequeñas y medianas empresas.",
            "Quinto.\nLa entidad colaboradora deberá cumplir.",
            "(DOGC) y en el «Boletín Oficial del Estado» (BOE). En el caso de que la publicación",
            "Concelleira delegada de Normalización Lingüística, en funcións.",
            "3. Financiación de proyectos de energías renovables.\n10. Transición energética justa y Pobreza Energética.",
            "la Fundación EOI, F.S.P. (en adelante, EOI), para la puesta en marcha.",
        ):
            self.assertEqual(self._persoas(texto), [], texto)

    def test_nomes_reais_seguen_detectandose(self):
        self.assertEqual(self._persoas("Comparece Lei Wang, con DNI 30014811H."), ["Lei Wang"])
        self.assertEqual(self._persoas("Comparece don Kowalczyk ante o xulgado."), ["Kowalczyk"])
        self.assertEqual(self._persoas("la notario doña María del Rosario Alloza Wisniewski del 5 de"),
                         ["María del Rosario Alloza Wisniewski"])

    def test_tratamento_dr_non_entra_no_codigo(self):
        self.assertEqual(self._persoas("Nombrar al Dr. Francisco Javier Carracedo Cano para la plaza:"),
                         ["Francisco Javier Carracedo Cano"])

    def test_cargo_pegado_a_raia_e_iniciais_da_forma_xuridica(self):
        self.assertEqual(
            self._persoas("firmante.–El Director General de la Entidad Pública Empresarial, M.P., Miguel Ramiro Guillem."),
            ["Miguel Ramiro Guillem"])
        self.assertEqual(
            self._persoas("electrónica.–El Director General de Planificación y Gestión Educativa, "
                          "P. D. Orden EFD/335/2025, Javier Ramírez Tormo."),
            ["Javier Ramírez Tormo"])

    def test_toponimos_dunha_listaxe_de_parcelas(self):
        self.assertEqual(self._persoas(
            "Baza entre el apoyo Nº 1 y el apoyo nº 28, Parajes la Granja, Cortijo Grande,\nCanal del Jabalcón\n"), [])

    def test_titular_de_parcela_partido_en_duas_liñas(self):
        """Fuga real (BOE-B de expropiacións): "APELIDO1 APELIDO2\\nNOME" nunha
        cela estreita quedaba enteiro á vista (spaCy tomábao por lugar)."""
        texto = "Olivos regadío\n36,20\n24\nMORALES CABELLO\nRAMÓN\nBENAMAUREL\n13\n44\nCortijo Nuevo\n"
        self.assertEqual(self._persoas(texto), ["MORALES CABELLO\nRAMÓN"])

    def test_lista_de_organismos_ou_concellos_non_e_persoa(self):
        self.assertEqual(self._persoas("23\nCONFEDERACIÓN\nHIDROGRÁFICA\nDEL GUADALQUIVIR\nBENAMAUREL\n13\n"), [])
        self.assertEqual(self._persoas("LUGO OURENSE\nSANTIAGO\n"), [])

    def test_apelido_composto_con_minuscula_tras_o_guion(self):
        """Fuga real (BOE): "doña Marta Vall-llossera Ferran" deixaba
        "-llossera Ferran" á vista. Nomes inventados."""
        for texto, resto in (
            ("Y de otra parte, doña Uxía Vall-llossera Ferran, Presidenta del Consejo.", ("llossera", "Ferran")),
            ("Comparece Jordi Puig-serra Vidal ante el juzgado.", ("serra", "Vidal")),
            ("Firma don Pere Ribas-i-Soler en Barcelona.", ("Ribas", "Soler")),
        ):
            anon, _ = _anonimizar(texto)
            for r in resto:
                self.assertNotIn(r, anon, texto)

    def test_iniciais_do_nome_tras_coma_seguen_redactandose(self):
        """Regresión atopada na auditoría (30/09/2026): a partición por comas
        da regra do INE tiraba "M. I." de "Apelidos, M. I." coma se non fose
        do nome, e as iniciais quedaban á vista. Nomes inventados."""
        anon, _ = _anonimizar("quenda libre: Barroso Cordeiro, M. I. (****445**). "
                              "Castro Lamas, J. A.(***9778**). – Técnico.")
        for resto in ("Barroso", "M. I.", "Castro", "J. A."):
            self.assertNotIn(resto, anon)


class TestSegundaLecturaHumana(unittest.TestCase):
    """Segunda lectura visual do usuario (30/09/2026, BOE de declaración dun
    BIC e anuncio dun xulgado). Texto sintético do mesmo estilo."""

    def test_non_son_persoas(self):
        for texto in (
            "La villa romana estaba dedicada a los dioses Lares.",
            "fijado en base a la cartografía catastral vigente a la fecha de declaración del BIC, y se",
            "De 2 a 3: Linde entre parcelas 99 y 114, y entre la 99 y la 108.",
            "Sección Civil e Instrucción TI Haro. Plz.n 1.- Anuncio de subasta judicial.",
        ):
            anon, informe = _anonimizar(texto)
            self.assertEqual(anon, texto)

    def test_estradas_e_parcelas_non_son_enderezos(self):
        for texto in (
            "pavimentada de la carretera AS-374.",
            "el margen occidental de la carretera LL-3 y de la carretera LL-12 hasta alcanzar la divisoria.",
            "superados estos, por la linde al camino de la parcela 10115.",
        ):
            anon, _ = _anonimizar(texto)
            self.assertEqual(anon, texto)

    def test_domicilio_en_estrada_segue_redactandose(self):
        anon, _ = _anonimizar("Comparece Xoán Páez Veiga, con domicilio en Estrada N-550, km 12, de Santiago.")
        self.assertNotIn("N-550", anon)

    def test_apelido_frecuente_en_maiusculas_segue_sendo_persoa(self):
        anon, _ = _anonimizar("Declara ARIAS que non estaba.")
        self.assertNotIn("ARIAS", anon)


class TestIniciaisTrasTratamento(unittest.TestCase):
    """Corpus web lote 2 (30/09/2026, BOE-A-2026-14304): spaCy detectaba as
    iniciais ao chou e a mesma persoa quedaba á vista noutra aparición."""

    def test_todas_as_aparicions_das_iniciais_co_mesmo_codigo(self):
        anon, _ = _anonimizar(
            "Ante notario, don B. L. S. y doña T. G. C., vendieron la finca. Certificaba que "
            "don B. L. S. y doña T. G. C. eran titulares. Comparecen Don B. L. S. y Doña T. G. C., "
            "en nombre propio. Luego B.L.S. firmó."
        )
        self.assertNotRegex(anon, r"[BT]\. ?[LG]\. ?[SC]\.")
        self.assertIn(" y doña ", anon)  # o "y" entre os dous non se tapa
        self.assertEqual(len(set(re.findall(r"PERSOA_\d+", anon))), 2)


class TestCargoDeLugarNonEPersoa(unittest.TestCase):
    """Corpus web lote 2 (30/09/2026): "el Notario de Valencia" saía coma persoa."""

    def test_notario_de_lugar_sen_nome(self):
        texto = "Mediante escritura otorgada ante el Notario de Valencia, con el número 4.116 de protocolo."
        anon, _ = _anonimizar(texto)
        self.assertEqual(anon, texto)

    def test_notario_de_lugar_co_nome_detras(self):
        anon, _ = _anonimizar("Autorizada por el Notario de Boadilla del Monte Don Rafael Marín Dué, el día veintidós.")
        self.assertIn("Notario de Boadilla del Monte Don PERSOA_", anon)
        self.assertNotIn("Marín", anon)


class TestSobreanonimizacionLote2(unittest.TestCase):
    """Corpus web lote 2 (30/09/2026): entes, sociedades, lugares, ordinais e
    abreviaturas do BOE tapados coma persoa."""

    def _persoas(self, texto):
        return [e.texto for e in ner.detectar(texto)[0] if e.etiqueta == "PERSOA"]

    def test_non_son_persoas(self):
        for texto in (
            "Que los planes se aprobaron.\nSegundo.\nQue las partes acuerdan.",
            "Con fecha 23 de julio de 2025, el Instituto de Crédito Oficial, Entidad Pública\nEmpresarial, y la Fundación.",
            "Se notifica a la explotación Casa Raña SAT su inclusión.",
            "Lista: Isabella Sunset Club, S. L.; Red Eléctrica de España, SAU.",
            "el Ayuntamiento de Altsasu, el Ayuntamiento\nde Arbizu, el Ayuntamiento de Arruazu.",
            "Las CCAA a extraer son Aragón, Baleares, Cataluña, Navarra, País Vasco, Ceuta y Melilla.",
            "El Consejero de Hacienda, P. D. (Resolución de 20 de julio de 2026), la Directora.",
            "de la Entidad Pública Empresarial Augas\nde Ames, Ayuntamiento de Ames (A Coruña).",
            "Consta como vecino de Ames el interesado.",
            "CULTURA, LINGUA E XUVENTUDE\nSECRETARÍA XERAL TÉCNICA",
            "mediante Resolución del Consejero de Desarrollo Rural, Ganadería, Pesca\ny Alimentación, de 24 de octubre.",
        ):
            self.assertEqual(self._persoas(texto), [], texto)

    def test_persoas_seguen_detectandose(self):
        self.assertIn("Xoán Segundo Páez Veiga", self._persoas("Consta como titular Xoán Segundo Páez Veiga, vecino de Ames."))
        # "S. L." con espazo tamén son as iniciais dunha persoa
        self.assertTrue(self._persoas("Admitidos: Barroso Cordeiro, S. L.; y otros."))

    def test_apelido_con_conector_na_liña_seguinte(self):
        anon, _ = _anonimizar("Asiste don Xoán Pérez\nde Andrade.")
        self.assertNotIn("Andrade", anon)
        anon, _ = _anonimizar("Firmado por don Xoán Pérez\nde conformidad.")
        self.assertIn("de conformidad", anon)


class TestNomePartidoEnDousCodigos(unittest.TestCase):
    """Corpus web lote 2 (30/09/2026): a mesma persoa levaba dous códigos."""

    def _codigos(self, texto):
        anon, _ = _anonimizar(texto)
        return anon, set(re.findall(r"PERSOA_\d+", anon))

    def test_mesma_persoa_un_so_codigo(self):
        for texto in (
            "PO/2025/0070\n***030***\nSobrado Deza,Tamara\n3.380,52 €\n",
            "del Registrador número 5, don Manuel Galán-\nSiles Calabuig, por la que se suspende. "
            "Luego don Manuel Galán-Siles Calabuig calificó.",
            "autorizada en Barcelona por el notario don Eduardo\nBaltasar Blanco el 22 de julio de 2025.",
            "de Valencia número 8, doña Marta\nGorostiza Ferrándiz de Pinedo, a inscribir una escritura.",
            "autorizada por el Notario de Valencia, don Vicente Luis\nSoró Santacreu, posteriormente modificada.",
            "poder otorgado ante el Notario de Madrid don Pedro J. Benito Fuertes, el día 5.",
            "Don Manuel Iscar Molina interviene.\nEl Sr. Iscar Molina fue nombrado Presidente.",
            "don Pedro José Benito Fuertes, con el número 1.832. Luego el notario don Pedro-José Benito Fuertes.",
        ):
            anon, codigos = self._codigos(texto)
            self.assertEqual(len(codigos), 1, anon)
            self.assertNotIn("J.", anon)

    def test_sra_con_apelidos_non_queda_a_vista(self):
        anon, _ = self._codigos("La Sra. García López pregunta.")
        self.assertNotIn("García", anon)
        texto = "El Sr. Presidente abre la sesión. La Sra. Letrada da fe."
        self.assertEqual(_anonimizar(texto)[0], texto)

    def test_lista_con_d_sen_comas_segue_sendo_duas_persoas(self):
        _, codigos = self._codigos("Comparecen D. Xoán Páez Veiga D. Manuel Carballo Portela y otros.")
        self.assertEqual(len(codigos), 2)


class TestSinaturaEIniciaisLote2(unittest.TestCase):
    def test_cargo_sen_nome_na_sinatura_do_boe_non_se_tapa(self):
        anon, _ = _anonimizar(
            "Palacio del Congreso, 28 de abril de 2026.–El Presidente de la\nComisión, Juan Francisco "
            "Serrano Martínez.–El Secretario Primero de la Comisión,\nSalvador de Foronda Vaquero.\n"
        )
        self.assertIn("El Secretario Primero de la Comisión,", anon)
        self.assertNotIn("Foronda", anon)

    def test_m_a_abreviado_un_so_codigo(self):
        anon, _ = _anonimizar("117\n***2716**\nABRISKETA CARBALLO, M.ª CARMEN.\nGESTIÓN P.A.\n")
        self.assertNotIn("CARMEN", anon)
        self.assertEqual(len(set(re.findall(r"PERSOA_\d+", anon))), 1)


class TestLecturaClaudeLote2(unittest.TestCase):
    """Atopados na lectura visual de Claude (30/09/2026) sobre o lote 2."""

    def _persoas(self, texto):
        return [e.texto for e in ner.detectar(texto)[0] if e.etiqueta == "PERSOA"]

    def test_non_son_persoas(self):
        for texto in (
            "SANIDADE\nDIRECCIÓN XERAL DE RECURSOS\nECONÓMICOS\nS.X. DE ORZAMENTOS\nSA.S04.00.001.15770.002\n",
            "SANIDADE\nDIRECCIÓN XERAL DE SAÚDE PÚBLICA\nS.X. DE ESTILOS DE VIDA SAUDABLES\nSA.C03.00.002\n",
            "CENTRO DE DESTINO: D.X. DE GANDARÍA, AGRICULTURA E INDUSTRIAS\n",
            "DIRECCION GENERAL DE\nESTRATEGIAS DE MOVILIDAD.\nS. G. DE PLANIFICACION, RED\nTRANSEUROPEA Y\nLOGISTICA.\n",
            "una promoción inmobiliaria en San\nJuan de Alicante sobre un solar.",
            "Red Eléctrica de España, S. A. U., y la E. P. E. firman.",
            "elegido por las Cortes de Castilla y León en la sesión.",
        ):
            self.assertEqual(self._persoas(texto), [], texto)
        self.assertEqual(self._persoas("Comparece don Pedro San Juan Pérez."), ["Pedro San Juan Pérez"])

    def test_iniciais_soltas_sen_tratamento(self):
        self.assertIn("A. C. G.", self._persoas("expedido por «Banco Santander, SA», con la firma de «A. C. G.», quien certificaba."))

    def test_sinatura_de_convenio_sen_cargo_nin_territorio(self):
        persoas = self._persoas(
            "encabezamiento.–Por la Embajada, el Embajador de España, Juan Ignacio Mauri\n"
            "Vallecillo, P. S., el Encargado de Negocios a.i., Manuel Riaño Gallego.\n")
        # O segundo apelido na liña seguinte tamén (antes "Vallecillo" quedaba á vista; lote 6).
        self.assertIn("Juan Ignacio Mauri\nVallecillo", persoas)
        self.assertFalse(any("España" in p or "P." in p for p in persoas), persoas)

    def test_cif_dunha_entidade_non_e_dni(self):
        anon, _ = _anonimizar("constituida ante el Notario don José Luis Casado Romano, con CIF G-80743503 y en su nombre.")
        self.assertIn("G-80743503", anon)
        self.assertNotIn("Crespo", anon)


class TestLiñaElectricaNonEPersoa(unittest.TestCase):
    def test_nome_da_liña_tras_kv(self):
        for texto in ("compactado con el circuito\na 220 kV Itxaso-Elgea, por lo que el desmontaje.",
                      "LAAT 400 kV Itxaso-Castejón/Muruarte y desmontaje"):
            self.assertEqual([e for e in ner.detectar(texto)[0] if e.etiqueta == "PERSOA"], [], texto)


class TestRazonSocialEnMaiusculas(unittest.TestCase):
    def test_razon_social_con_forma_despois(self):
        t = ("B88503057\nMIA PIA IBERIA S.L.\n09/03/2026\nB16506362\nGRAM LAW, SOCIEDAD LIMITADA.\n24/03/2026\n"
             "U06509608\nUTE MANUEL TAMARGO, PEDRO MILLAN, Y JOSE ANGEL\nPARDO.\n13/03/2026\n")
        persoas = " ".join(e.texto for e in ner.detectar(t)[0] if e.etiqueta == "PERSOA")
        self.assertNotIn("MIA PIA", persoas)
        self.assertNotIn("GRAM LAW", persoas)
        self.assertIn("PEDRO MILLAN", persoas)


class TestRotulosDeFormulario(unittest.TestCase):
    def test_rotulos_non_son_nomes(self):
        for rotulo in ("NOMBRE Y APELLIDOS", "DOMICILIO A EFECTOS DE NOTIFICACIÓN", "LOCALIDAD", "TELÉFONO",
                       "CORREO ELECTRÓNICO (obligatorio)", "CÓD. POSTAL"):
            self.assertFalse(ner._texto_de_cela_e_nome(rotulo), rotulo)
        self.assertTrue(ner._texto_de_cela_e_nome("Páez Veiga, Xoán"))

    def test_rotulos_do_formulario_do_lote3(self):
        """BOE-A-2026-685 (lote 3): "Empleo" e "CP" baixo "Nombre y apellidos"."""
        for rotulo in ("Empleo", "CP", "Fax"):
            self.assertFalse(ner._texto_de_cela_e_nome(rotulo), rotulo)


class TestLugarEDataDaSinatura(unittest.TestCase):
    def test_lugar_da_sinatura_non_e_persoa(self):
        persoas = [e.texto for e in ner.detectar(
            "las propias bases.\nAmes, 16 de julio de 2026.–El Presidente, José Blas Galán Portela.")[0]
            if e.etiqueta == "PERSOA"]
        self.assertEqual(persoas, ["José Blas Galán Portela"])


class TestMunicipioConTratamento(unittest.TestCase):
    def test_don_benito(self):
        t = "SERVICIO COMÚN DE TRAMITACIÓN DEL TRIBUNAL DE\nINSTANCIA.\nDON BENITO.\nBADAJOZ.\n"
        self.assertEqual([e for e in ner.detectar(t)[0] if e.etiqueta == "PERSOA"], [])
        self.assertEqual([e.texto for e in ner.detectar("Comparece don Benito Páez Veiga.")[0]
                          if e.etiqueta == "PERSOA"], ["Benito Páez Veiga"])


class TestNomeDeInstitucion(unittest.TestCase):
    def test_universidade_co_nome_dunha_persoa(self):
        t = ("Suplente: Carolina Magallon Cano. Profesorado Titular de Universidad. Universidad\n"
             "Carlos III de Madrid.\nSuplente: Antonio José Riera de Andrés. Catedráticos/as de Universidad.")
        self.assertEqual([e.texto for e in ner.detectar(t)[0] if e.etiqueta == "PERSOA"],
                         ["Carolina Magallon Cano", "Antonio José Riera de Andrés"])


class TestDAbreviadoNaCabeceira(unittest.TestCase):
    def test_d_foral_non_e_persoa(self):
        t = "Orden\nDNI\nApellidos y nombre\nTotal concurso\nEuskera\nD. Foral\nTotal\n"
        self.assertEqual([e for e in ner.detectar(t)[0] if e.etiqueta == "PERSOA"], [])
        self.assertEqual([e.texto for e in ner.detectar("Comparece D. Mohamed Benali Pérez.")[0]
                          if e.etiqueta == "PERSOA"], ["Mohamed Benali Pérez"])


class TestEntidadesDoBoe16636(unittest.TestCase):
    def test_non_son_persoas(self):
        for texto in ("Ayuntamiento de Urdain, I-DE Redes Eléctricas Inteligentes, SAU, Enagás, SA.",
                      "Greenpeace España, Ecologistas en Acción Navarra, el Grupo.",
                      "desde la SE Itxaso hasta el apoyo 12.",
                      "la Federación Navarra de Deportes de Montaña y Escalada, la Dirección General."):
            self.assertEqual([e.texto for e in ner.detectar(texto)[0] if e.etiqueta == "PERSOA"], [], texto)
        self.assertEqual([e.texto for e in ner.detectar("Contesta don Xoán Páez Veiga, en nombre propio.")[0]
                          if e.etiqueta == "PERSOA"], ["Xoán Páez Veiga"])


class TestCargoDeXustizaSenNome(unittest.TestCase):
    def test_letrado_sen_nome(self):
        t = "El Puerto de Santa Maria, 21 de mayo de 2026.- El Letrado de la\nAdministración de Justicia."
        self.assertEqual([e for e in ner.detectar(t)[0] if e.etiqueta.startswith("PERSOA")], [])

    def test_co_nome_sen_coma_exento_igual_ca_con_coma(self):
        # Decisión do usuario 01/10/2026 (criterio CENDOJ: o LAJ vese), con ou sen coma.
        for t in ("Firma doña Rosa Páez Veiga Letrada de la Administración de Justicia.",
                  "Firma doña Rosa Páez Veiga, Letrada de la Administración de Justicia."):
            anon, _ = _anonimizar(t)
            self.assertEqual(anon, t)
        anon, _ = _anonimizar("Comparece doña Rosa Páez Veiga, abogada, en nombre de su cliente.")
        self.assertNotIn("Veiga", anon)


class TestCargoAntesDeNomeMultiliña(unittest.TestCase):
    def test_cargo_recortase_co_apelido_na_liña_seguinte(self):
        t = "Rincón de la Victoria, 24 de julio de 2026. –El Alcalde, José Francisco Salido\nEscudero.\nBOLETÍN OFICIAL DEL ESTADO\n"
        self.assertEqual([e.texto for e in ner.detectar(t)[0] if e.etiqueta == "PERSOA"],
                         ["José Francisco Salido\nEscudero"])


class TestRuaCoNomeDunhaPersoa(unittest.TestCase):
    def test_rua_e_toponimo(self):
        t = "As instalacións obxecto deste expediente están situadas na rúa Manuel Ángel Terrón,\nno concello de Curtis."
        self.assertEqual([e for e in ner.detectar(t)[0] if e.etiqueta == "PERSOA"], [])


class TestVicepresidentaNonEPersoa(unittest.TestCase):
    def test_cargo_con_prefixo_vice_nunha_palabra(self):
        t = ("de junio de 2026. –La Vicepresidenta Segunda, Diputada Delegada de\nRecursos Humanos de la "
             "Diputación de Valencia, María del Remedio Maddaloni\nTellechea.\n")
        self.assertEqual([e.texto for e in ner.detectar(t)[0] if e.etiqueta == "PERSOA"],
                         ["María del Remedio Maddaloni\nTellechea"])


class TestLecturaHumanaLote2Final(unittest.TestCase):
    """BOE-A-2026-14956 (lectura humana 01/10/2026): "non hai persoas nin enderezos"."""

    def test_non_son_persoas_nin_enderezos(self):
        for texto in ("la letra e) del artículo 5 de la\nLey 29/1994, de 24 de noviembre, de Arrendamientos Urbanos, en los términos",
                      "Presentante: E. E., E.\nFundamentos de Derecho:\nSe suspende la inscripción",
                      "dicha presentación ha tenido\nlugar con posterioridad al 3 de abril de 2025, por lo que"):
            self.assertEqual([e for e in ner.detectar(texto)[0] if e.etiqueta in ("PERSOA", "ENDEREZO")], [], texto)

    def test_lugar_do_rural_segue_sendo_enderezo(self):
        self.assertTrue([e for e in ner.detectar("con domicilio en lugar de Vilanova 3, Lalín.")[0] if e.etiqueta == "ENDEREZO"])


class TestNomeDunPremio(unittest.TestCase):
    """Decisión do usuario (01/10/2026): o nome dun premio queda á vista."""

    def test_premio_queda_e_premiado_non(self):
        t = ("Solicitud del Premio de Investigación en Ciencias Puras y Aplicadas en Protección\n"
             "de Datos Personales «Ángela Ruiz Robles» de la Agencia Española de Protección")
        self.assertEqual([e for e in ner.detectar(t)[0] if e.etiqueta == "PERSOA"], [])
        t = ("las bases del Instituto Asturiano\nde Administración Pública «Adolfo Posada», que contiene las bases "
             "íntegras de la convocatoria.")
        self.assertEqual([e for e in ner.detectar(t)[0] if e.etiqueta == "PERSOA"], [])
        t = "El Premio Nacional de Investigación fue concedido a «Xoán Páez Veiga» por el jurado."
        self.assertEqual([e.texto for e in ner.detectar(t)[0] if e.etiqueta == "PERSOA"], ["Xoán Páez Veiga"])


class TestGuionNonSeparable(unittest.TestCase):
    """Lote 3 (03/10/2026), FUGA: o DOG compón algúns apelidos compostos co
    guión NON SEPARABLE U+2011 ("Ferrín‑Ulla"); só se tapaba ata o
    guión e o resto quedaba á vista."""

    def test_apelido_con_guion_u2011_enteiro(self):
        t = ("Nomeo presidenta do Padroado do Parque Nacional Marítimo‑Terrestre das Illas Atlán‑\n"
             "ticas de Galicia a Xiana Ferrín‑Ulla Bacarizo.\nSantiago de Compostela, seis de abril")
        self.assertEqual(_persoas(t), ["Xiana Ferrín‑Ulla Bacarizo"])
        with tempfile.TemporaryDirectory() as d:
            anon, _ = anonimizar_texto(t, RexistroCorrespondencias(d))
        self.assertNotIn("Albor", anon)
        self.assertNotIn("Bacarizo", anon)

    def test_mesma_persoa_con_guion_u2011_e_ascii(self):
        """Mesma persoa co guión normal no sumario e co U+2011 no corpo: un código."""
        t = ("Nomea a doña Xiana Ferrín-Ulla Bacarizo presidenta.\n"
             "Nomeo presidenta a doña Xiana Ferrín‑Ulla Bacarizo.")
        with tempfile.TemporaryDirectory() as d:
            anon, _ = anonimizar_texto(t, RexistroCorrespondencias(d))
        self.assertEqual(len(set(re.findall(r"PERSOA_\d+", anon))), 1, anon)
        self.assertNotIn("Albor", anon)

    def test_nome_de_pia_ao_final_da_liña_no_sumario(self):
        """Sumario do mesmo anuncio: "a Xiana\\nFerrín-Ulla Bacarizo", co
        nome enteiro no corpo."""
        t = ("Decreto 40/2026 polo que se nomea presidenta do Padroado do Parque Nacional a Xiana\n"
             "Ferrín-Ulla Bacarizo.\nO Consello da Xunta aprobou o decreto.\n"
             "Nomeo presidenta do Padroado a doña Xiana Ferrín\u2011Ulla Bacarizo.\n")
        with tempfile.TemporaryDirectory() as d:
            anon, _ = anonimizar_texto(t, RexistroCorrespondencias(d))
        self.assertNotIn("Xiana", anon)
        self.assertNotIn("Albor", anon)
        self.assertEqual(len(set(re.findall(r"PERSOA_\d+", anon))), 1, anon)


class TestMaxistradaVisibleEnTodas(unittest.TestCase):
    """Criterio CENDOJ (decisión do usuario 03/10/2026): xuíces, maxistrados
    e LAJ á vista en TODAS as aparicións (lote 3: BOE-A-2026-623, -2890)."""

    def _anon(self, t):
        with tempfile.TemporaryDirectory() as d:
            return anonimizar_texto(t, RexistroCorrespondencias(d))[0]

    def test_cargo_e_tratamento_en_liñas_distintas(self):
        t = ("Acuerdo del Consejo General del Poder Judicial, por el que se adscribe a la Magistrada\n"
             "doña Xiana Lucas Barcala a la Audiencia Provincial de Lugo.\n"
             "La Comisión ha acordado adscribir la magistrada Xiana Lucas Barcala, a la sección civil.")
        self.assertEqual(self._anon(t), t)

    def test_cargo_so_nunha_aparicion(self):
        t = ("Real Decreto por el que se nombra a la Magistrada doña Xiana\n"
             "Lucas Barcala.\nDe conformidad con lo establecido en la Ley Orgánica,\n"
             "Vengo en nombrar Presidenta de Sección del Tribunal de Instancia de Lugo, a\n"
             "doña Xiana Lucas Barcala, titular de la plaza número 2 de la Sección.")
        anon = self._anon(t)
        self.assertNotIn("PERSOA_", anon)
        self.assertEqual(anon.count("Xiana"), 2, anon)

    def test_parte_sen_cargo_segue_tapada(self):
        t = "La Magistrada doña Uxía Roel Salcedo dictó sentencia contra don Xoán Páez Veiga.\nXoán Páez Veiga recorre."
        anon = self._anon(t)
        self.assertIn("Uxía Roel Salcedo", anon)
        self.assertNotIn("Páez", anon)


class TestConectoresGalegosNonSonPersoa(unittest.TestCase):
    """Lote 3 (03/10/2026): "Segundo o previsto" (Segundo = nome de pía) e
    "Polo exposto" (Polo = apelido) tapábanse coma persoa en anuncios do DOG."""

    def test_segundo_e_polo_a_principio_de_frase(self):
        for t in ("Os membros cesarán segundo o que establece o artigo 28\ndesta lei.\nSegundo o previsto no artigo 33.2 da lei, nomeo titular.",
                  "A renovación ten efectos desde hoxe.\nSegundo o Acordo plenario do 17 de abril, a transferencia redúcese.",
                  "Delegou o exercicio das devanditas\ncompetencias.\nPolo exposto, en exercicio da facultade que me confire a lei,\nDISPOÑO:",
                  "Non houbo alegacións.\nPolo tanto, resolvo aprobar o proxecto."):
            self.assertEqual(_persoas(t), [], t)

    def test_letra_de_enumeracion_e_verbo(self):
        t = "Modifícase o convenio nos se-\nguintes termos:\nA. Engadese o parágrafo primeiro bis, co texto seguinte:"
        self.assertEqual(_persoas(t), [])

    def test_segundo_coma_nome_segue_sendo_persoa(self):
        t = "Comparece don Segundo Varela Castro, veciño de Lalín, e manifesta o seguinte."
        self.assertEqual(_persoas(t), ["Segundo Varela Castro"])


class TestTaboaDeCoordenadasDaEstrada(unittest.TestCase):
    """Lote 3 (AnuncioG0765): "MD da PO-532" (marxe dereita da estrada)
    tapábase coma persoa."""

    def test_marxe_e_estrada_non_son_persoa(self):
        t = ("• Treito antigo da PO-532 (A), con inicio na intersección coa EP-0004\n"
             "e final no p.q. 6+520 MD da PO-532.\nx = 534.647\ny = 4.694.895\np.q. 6+520 MD da\nPO-532\n")
        self.assertEqual(_persoas(t), [])


class TestSobreanonimizacionLote3(unittest.TestCase):
    """Lote 3 (lectura de Claude e do usuario, 03/10/2026): nada disto é persoa."""

    def _sen_persoas(self, t):
        self.assertEqual(_persoas(t), [], t)

    def test_sigla_dun_sistema_na_prosa(self):
        self._sen_persoas("Las solicitudes podrán presentarse a través de SIMENDEF, MENSADEF, GEISER o correo electrónico.")
        self._sen_persoas("Los gastos compartidos acordados, excluyendo IVA o impuestos locales, se abonarán en libras.")

    def test_abreviatura_en_maiusculas(self):
        self._sen_persoas("ANEXO\nS. DE E. TELECOMUNIC. E INFRAEST. DIGIT.\nSECRETARIA DE ESTADO\n")

    def test_reto_demografico(self):
        self._sen_persoas("Resolución de 2026, de la Consejería de Presidencia, Reto\nDemográfico, Igualdad y Turismo, por la que")

    def test_paises_e_cidades(self):
        self._sen_persoas("Sedes: Copenhagen Contemporary, Copenhague, Dinamarca; y KANAL, Bruselas, Bélgica; cada una la «Sede».")
        self._sen_persoas("con domicilio en Tate, Millbank, Londres\nSW1P 4RG, filial propiedad exclusiva")
        self._sen_persoas("en el Museo Nacional Centro de Arte Reina Sofía (MNCARS-Madrid) para la organización")
        self._sen_persoas("la mediación se llevará a\ncabo en Londres, Reino Unido, y el idioma de la mediación será el inglés.")

    def test_paises_en_galego(self):
        """AnuncioO92 (lote 3): listaxe de países do DOG."""
        self._sen_persoas("Investimentos nalgún dos seguintes países: Alemaña, Polonia, Hungría, República Checa, "
                          "México, Costa Rica, Cuba, República Dominicana, Porto Rico, El Salvador, Namibia, Israel, "
                          "Catar, Arabia Saudí, Omán, Asia Oriental, China, Xapón, Corea do Sur, Malaisia, India "
                          "(incluído Sikkim), Paquistán.")

    def test_secretaria_de_estado_abreviada(self):
        """BOE-A-2026-6433 (lote 3): "S. DE E. DE MEDIO AMBIENTE - D.G. DE LA COSTA"."""
        self._sen_persoas("ANEXO\nS. DE E. DE MEDIO AMBIENTE - D.G. DE LA COSTA Y EL MAR\nS.G. PARA LA PROTECCION DE LA COSTA\n")

    def test_domingo_dia_da_semana_e_letra_d_dunha_lista(self):
        """BOE-A-2026-4943 (lote 3): "Domingo (noche que...)" e "D. Permisos y
        beneficios" (o "D." da lista A., B., C., D. lido coma "don")."""
        self._sen_persoas("Sábado (noche que comienza el viernes).\nDomingo (noche que comienza el sábado).\n"
                          "Festivo (noche que comienza la víspera del festivo).")
        self._sen_persoas("A. Acceso al empleo.\nB. Formación, sensibilización y lenguaje.\n"
                          "C. Clasificación y promoción profesional.\nD. Permisos y beneficios sociales.\n"
                          "E. Entornos laborales diversos, seguros e inclusivos.")

    def test_sistema_con_letras_e_cifras(self):
        """AnuncioG0426 (lote 3): "certificado electrónico ou Chave365"."""
        self._sen_persoas("Só se poderá acceder á notificación co certificado electrónico ou Chave365.\n"
                          "Enviaranse avisos da posta á disposición da notificación.")

    def test_cidade_e_anuncio_pegados(self):
        """BOE-B-2026-8928 (control, lote 3): "c.sede Vigo.- Anuncio de subasta"."""
        self._sen_persoas("Sección Mercantil TI de Pontevedra. Plz.n 3, c.sede Vigo.- Anuncio de subasta\n"
                          "judicial concursal con número de identificación 4830000052021216.")

    def test_lugares_co_nome_dunha_persoa(self):
        """AnuncioG0256 (control, lote 3); decisión do usuario 01/10: rúas e lugares
        co nome dunha persoa quedan á vista."""
        self._sen_persoas("mellora integral das instalacións deportivas municipais existentes na ave-\n"
                          "nida Enrique Peinador para uso de turismo deportivo sostible")
        self._sen_persoas("acondicionamento e pavimentación de aparcadoiro público no\npolígono industrial «David Ferrer»\n")
        self._sen_persoas("o acondicionamento da contorna máis próxima ao mosteiro de San Clodio\n")

    def test_ordinal_e_minuscula(self):
        """BOE-A-2026-6004 (control, lote 3): "Sexto curso. Para poder matricularse"."""
        self._sen_persoas("al menos, 24 créditos ECTS de tercer curso.\nSexto curso. Para poder matricularse de sexto "
                          "curso, el estudiantado deberá haber superado todas las asignaturas.")

    def test_letra_d_dunha_taboa(self):
        """BOE-A-2026-9676 (control, lote 3): "D. Materias explosivas." nunha táboa."""
        self._sen_persoas("Abr-25\nMay-25\nJun-25\nD. Cabezas explosivas.\n153,133\n153,429\n154,702\n"
                          "H. Materiales textiles.\n114,846\n")
        self.assertEqual(_persoas("En el acto del juicio, D. Cabezas declaró.\nA continuación declaró el perito."),
                         ["Cabezas"])

    def test_provincias_nunha_enumeracion(self):
        """BOE-A-2026-5550 (control ciego de Claude, lote 3)."""
        self._sen_persoas("Instituto de Medicina Legal de Albacete, Cuenca y\nGuadalajara. Subdirección de Guadalajara.")
        self._sen_persoas("INSTITUTO DE MEDICINA LEGAL DE ÁVILA, BURGOS, SEGOVIA Y SORIA.\nDIRECCIÓN DE BURGOS.")
        self._sen_persoas("INSTITUTO DE MEDICINA LEGAL DE ILLES BALEARS. DIRECCIÓN DE\nPALMA DE MALLORCA.\n1")
        self._sen_persoas("El Ministro de la Presidencia, Justicia y Relaciones\ncon las Cortes, P. D. (Orden PJC/1062/2024)")
        self.assertEqual(_persoas("Comparece el Sr. Burgos, vecino de Lugo, y manifiesta."), ["Burgos"])

    def test_valedor_do_pobo(self):
        """AnuncioG2022-090226 (control ciego de Claude, lote 3)."""
        self._sen_persoas("a súa presidencia á persoa titular da institución do Valedor do Pobo.\nNo exercicio das funcións")

    def test_palabra_comun_con_maiuscula(self):
        self._sen_persoas("La Parte afectada por una reclamación\nde indemnización o Seguro, será responsable de negociar "
                          "con la compañía de seguro correspondiente.")

    def test_persoa_de_verdade_segue(self):
        self.assertEqual(_persoas("Comparece doña Uxía Roel Salcedo, con DNI 30014811Z, e asina."), ["Uxía Roel Salcedo"])
        self.assertEqual(_persoas("Comparece don Manuel GEISER LÓPEZ, veciño de Lugo."), ["Manuel GEISER LÓPEZ"])
        self.assertEqual(_persoas("La demanda fue presentada por doña Iva Seguro Castro en el juzgado."),
                         ["Iva Seguro Castro"])


class TestPrazaQueNonEEnderezo(unittest.TestCase):
    """Lote 3: "(plaza 026CUN25)" (código dunha praza de profesor) e "titular
    de la plaza número 2 de la Sección" tapábanse coma [ENDEREZO]."""

    def test_codigo_de_praza(self):
        for t in ("Departamento de Ingeniería de Comunicaciones\n(plaza 026CUN25).\nDon David",
                  "titular de la plaza número 2 de la Sección de\nViolencia sobre la Mujer"):
            self.assertEqual([e.texto for e in ner.detectar(t)[0] if e.etiqueta == "ENDEREZO"], [], t)

    def test_praza_con_codigo(self):
        """Lote 5, piloto da revisión do corpus (BOE-A-2025-2801): "en la plaza
        código 021132" é a praza dun catedrático, non un enderezo."""
        for t in ("adscrita al Departamento de Ciencias\nHistóricas y Teoría de las Artes, en la plaza código 021132.\nDon Carlos",
                  "nomeado para a praza co código 240314 do Departamento",
                  "en la plaza con código 0811 de la relación de puestos",
                  "provisión da praza n.º 12 do cadro de persoal"):
            self.assertEqual([e.texto for e in ner.detectar(t)[0] if e.etiqueta == "ENDEREZO"], [], t)

    def test_praza_de_verdade_segue(self):
        self.assertTrue([e for e in ner.detectar("con domicilio en la plaza Mayor, número 3, de Lugo.")[0]
                         if e.etiqueta == "ENDEREZO"])


class TestNomeDePiaAoFinalDaLiña(unittest.TestCase):
    """Lote 3 (AnuncioL135): "nomeouse a María\\nJesús Ferro Godos" levaba
    dous códigos (un para "María", outro para o resto)."""

    def test_un_so_codigo(self):
        t = ("Por Resolución da Alcaldía 231/2026, do 23 de febreiro, nomeouse a María\n"
             "Xesús Ferro Godos e Nuria Barcala Páez funcionarias de carreira do Concello.")
        with tempfile.TemporaryDirectory() as d:
            anon, _ = anonimizar_texto(t, RexistroCorrespondencias(d))
        self.assertNotIn("María", anon)
        self.assertEqual(len(set(re.findall(r"PERSOA_\d+", anon))), 2, anon)

    def test_tras_cargo_e_coma(self):
        """BOE-A-2026-2939 (control, lote 3): "Función Pública, María\nHilda Jurado Noguera"."""
        t = ("Madrid, 30 de enero de 2026.–La Directora General de la Función Pública, María\n"
             "Hilda Jurado Noguera.\nANEXO\nCorporación: Ayuntamiento de Móstoles.\n")
        with tempfile.TemporaryDirectory() as d:
            anon, _ = anonimizar_texto(t, RexistroCorrespondencias(d))
        self.assertNotIn("María", anon)
        self.assertIn("Función Pública,", anon)
        self.assertEqual(len(set(re.findall(r"PERSOA_\d+", anon))), 1, anon)


class TestNomeCompletoDentroDunhaEntidadeMalCortada(unittest.TestCase):
    """BOE-A-2026-1546 (lectura de Claude, 03/10/2026), FUGA xa existente en main:
    na sinatura "–Por y en nombre del Patronato de la Tate Gallery, Helen Lidd,"
    tapábase "del Patronato ... Helen" e quedaba "Lidd" á vista, aínda que
    "Helen Lidd" estaba detectada noutros sitios do documento."""

    def test_o_apelido_non_queda_a_vista(self):
        t = ("Entre Helen Lidd, Directora de la Tate Liverpool, en representación del Patronato.\n"
             "Los Comisarios de la Exposición son Helen Lidd, Directora de Tate Liverpool.\n"
             "Firmado por las partes en este convenio en la fecha indicada en su\n"
             "encabezamiento. –Por y en nombre del Patronato de la Tate Gallery, Helen Lidd,\n"
             "Directora de Tate Liverpool.")
        with tempfile.TemporaryDirectory() as d:
            anon, _ = anonimizar_texto(t, RexistroCorrespondencias(d))
        self.assertNotIn("Lidd", anon)
        # O que sobra ao recortar tras unha coma ("del Patronato...") non é persoa.
        self.assertIn("en nombre del Patronato de la Tate Gallery, PERSOA_", anon)

    def test_nome_mais_longo_non_se_recorta(self):
        """BOE-A-2026-4392 (auditoría final do lote 3), REGRESIÓN atopada e
        arranxada antes de subir: "José Antonio Benedicto" (corrección de erros)
        recortaba "José Antonio Bermudo Iribeñ" e deixaba "Iribeñ" á vista."""
        t = ("Donde dice:\n«Don José Antonio Benedicto, del Cuerpo Superior de Administradores Civiles del\n"
             "Estado.»\nDebe decir:\n«Don José Antonio Bermudo Iribeñ, del Cuerpo Superior de Administradores "
             "Civiles del Estado.»")
        with tempfile.TemporaryDirectory() as d:
            anon, _ = anonimizar_texto(t, RexistroCorrespondencias(d))
        self.assertNotIn("Iribeñ", anon)
        self.assertNotIn("Benedicto", anon)

    def test_resto_en_minuscula_non_queda_coma_persoa(self):
        """AnuncioG2022: "á valedora do Pobo, María Xosé Pardavila Galán"."""
        t = ("pola que se dispón o cesamento de\nMaría Xosé Pardavila Galán como adxunta á valedora do Pobo.\n"
             "Declarar o cesamento ex lege da adxunta á valedora do Pobo, María Xosé Pardavila Galán, agra-\n"
             "decéndolle os servizos prestados.")
        with tempfile.TemporaryDirectory() as d:
            anon, _ = anonimizar_texto(t, RexistroCorrespondencias(d))
        self.assertEqual(anon.count("valedora do Pobo"), 2, anon)
        self.assertNotIn("Pardavila", anon)


class TestListaxeDeProfesoradoTrasUniversidad(unittest.TestCase):
    """BOE-A-2026-7914 (control da lectura de Claude, lote 3, 03/10/2026), FUGA
    xa existente en main: "...Titulares de Universidad\\nAlcaraz Iborra, Manuel."
    tomábase polo nome da universidade (regra "Universidad\\nCarlos III") e
    "Biedermann, Anna Maria." perdía o apelido (apelido único a inicio de frase)."""

    def test_toda_a_listaxe_tapada(self):
        t = ("ANEXO\nPersonal del cuerpo de Profesores/as Titulares de Universidad\nAlcaraz Iborra, Manuel.\n"
             "DNI: ****5919*.\nÁrea de conocimiento: Psicología Evolutiva y de la Educación.\n"
             "Departamento: Psicología y Sociología.\nAsín Izquierdo, Laura.\nDNI: ****3264*.\n"
             "Área de conocimiento: Didáctica.\nBiedermann, Anna Maria.\nNIE: ****3376*.\n"
             "Área de conocimiento: Expresión Gráfica en la Ingeniería.\n")
        with tempfile.TemporaryDirectory() as d:
            anon, _ = anonimizar_texto(t, RexistroCorrespondencias(d))
        for nome in ("Alcaraz", "Iborra", "Manuel", "Asín", "Laura", "Biedermann", "Anna"):
            self.assertNotIn(nome, anon)
        self.assertEqual(len(set(re.findall(r"PERSOA_\d+", anon))), 3, anon)

    def test_universidad_co_nome_dunha_persoa_segue_a_vista(self):
        t = "con la Universidad\nCarlos III de Madrid y la Universidad Rovira i Virgili."
        self.assertEqual(_persoas(t), [])


class TestMuseoReinaSofia(unittest.TestCase):
    """BOE-A-2026-1546, lectura humana do usuario (03/10/2026): "Museo Nacional
    Centro de Arte Reina\\nSofía, Manuel Sobral Lourido, Director": a persoa é só
    "Manuel Sobral Lourido"; "Sofía" (do museo) tapábase e a persoa levaba 2 códigos."""

    def test_so_a_persoa_e_un_codigo(self):
        t = ("Madrid, 25 de noviembre de 2025.–El Director del Museo Nacional Centro de Arte\n"
             "Reina Sofía, Manuel Sobral Lourido.\nANEXO\n"
             "Y Manuel Sobral, en su calidad de Director del Museo Nacional Centro de Arte\n"
             "Firmado por las partes.–Por y en nombre del Museo Nacional Centro de Arte Reina\n"
             "Sofía, Manuel Sobral Lourido, Director del Museo Nacional Centro de Arte Reina Sofía.\n")
        with tempfile.TemporaryDirectory() as d:
            anon, _ = anonimizar_texto(t, RexistroCorrespondencias(d))
        self.assertNotIn("Sobral", anon)
        self.assertNotIn("Lourido", anon)
        self.assertEqual(anon.count("Sofía"), 3, anon)
        self.assertEqual(len(set(re.findall(r"PERSOA_\d+", anon))), 1, anon)


class TestPendentesLote3(unittest.TestCase):
    """Pendentes do lote 3 que xa estaban en main (decisión do usuario 03/10/2026)."""

    def _sen_persoas(self, t):
        self.assertEqual(_persoas(t), [], t)

    def test_sala_coma_organo(self):
        """BOE-A-2026-5479."""
        self._sen_persoas("toma conocimiento y ordena hacer público el acuerdo de Sala\nde Gobierno del Tribunal Superior")
        self._sen_persoas("en cuyo caso, quien ejerza la presidencia de la Sala designara nuevo ponente\nentre quienes")
        self.assertEqual(_persoas("Comparece doña Ana Sala Pérez, vecina de Lugo."), ["Ana Sala Pérez"])

    def test_cargo_con_xenero(self):
        """BOE-A-2026-2939: "Denominación del puesto: Tesorero/a."."""
        self._sen_persoas("Corporación: Ayuntamiento de Móstoles.\nDenominación del puesto: Tesorero/a.\nComplemento específico")

    def test_catalogo_de_moedas(self):
        """BOE-A-2026-7022."""
        self._sen_persoas("Orden por la que se ejercita el derecho de tanteo sobre 7 lotes de monedas de Emerita Augusta, "
                          "subastados por la sala\nTauler y Fau, en Madrid.\n")
        self._sen_persoas("Lote 428. –Emerita Augusta. Época de Augusto. As. 27 a.C. Mérida (Badajoz).\n"
                          "(Abh-987 var). (Acip-4436n). Anv.: Cabeza desnuda de Augusto a derecha, alrededor\n"
                          "CAESAR. AVGVST. TRIBVN. POTEST. Rev.: En el centro P. CARISIVS.\n"
                          "Lote 433. –Emerita Augusta. Época de Augusto. Semis. 22 a.C. –14 d.C. Mérida\n"
                          "Lote 438. –Emerita Augusta. Época de Tiberio. As. 14-36 d.C. Mérida (Badajoz).\n"
                          "(Abh-1061). (Acip-3411a). Anv.: Cabeza laureada de Tiberio a izquierda, alrededor TI.\n")

    def test_termos_definidos_no_convenio(self):
        """BOE-A-2026-1546: «TATE», «Parte», «Per Diem» son termos definidos do convenio."""
        t = ("del Patronato de la Tate Gallery, nombrado por resolución del Patronato (en lo sucesivo,\n«TATE»);\n"
             "En lo sucesivo, cada uno de ellos una «Parte» y conjuntamente, las «Partes».\n"
             "– «Per Diem» significa la dieta diaria destinada a cubrir los gastos de subsistencia;\n"
             "Al finalizar la itinerancia de la Exposición, la TATE organizará y financiará la eliminación.\n"
             "Dirigido a: Director, Tate Liverpool, Mann Island, Liverpool, L3 1BP.\n"
             "En caso de fuerza mayor, la Parte que se retire deberá abonar su parte proporcional.\n")
        self.assertEqual([p for p in _persoas(t) if re.search(r"Tate|TATE|Parte|Per Diem", p)], [])

    def test_alias_dunha_persoa_segue_tapado(self):
        t = ("Don Xoán Páez Veiga (en adelante, «Xoán»), mayor de edad.\nXoán declara que acepta el cargo.")
        with tempfile.TemporaryDirectory() as d:
            anon, _ = anonimizar_texto(t, RexistroCorrespondencias(d))
        self.assertNotIn("Páez", anon)

    def test_rua_sen_tipo_de_via_con_codigo_postal(self):
        """BOE-A-2026-1546: "Reina Sofía, Santa Isabel, 52,\\n28012 Madrid" é o enderezo do museo."""
        t = "Dirigido a: Director del Museo Nacional Centro de Arte Reina Sofía, Santa Isabel, 52,\n28012 Madrid, España.\n"
        entidades = ner.detectar(t)[0]
        self.assertEqual([e.texto for e in entidades if e.etiqueta == "PERSOA"], [])
        self.assertTrue([e for e in entidades if e.etiqueta == "ENDEREZO" and "Santa Isabel" in e.texto])


class TestFugasLote4(unittest.TestCase):
    """Lote 4 virxe (03/10/2026), fugas parciais confirmadas polo usuario."""

    def _anon(self, t):
        with tempfile.TemporaryDirectory() as d:
            return anonimizar_texto(t, RexistroCorrespondencias(d))[0]

    def test_apelido_con_letras_de_fora_do_español(self):
        """BOE-A-2025-19570 e -21164: "don Pavol Šinál", "doña Suzana Marija Curic\\nŠpehar"."""
        for t, resto in (("Gescrap, representada en este acto por don Pavol Šinál, con DNI eslovaco ****13**, mayor de edad.", "Šinál"),
                         ("representada en este acto por doña Suzana Marija Curic\nŠpehar, quien actúa en su condición de apoderada.", "Špehar")):
            self.assertNotIn(resto, self._anon(t), t)

    def test_apostrofo_tipografico(self):
        """BOE-A-2025-25943: "Don Pascual Ferrándiz O´Dempsey"."""
        anon = self._anon("Vocales:\nDon Pascual Ferrándiz O´Dempsey, personal laboral de la Universidad de Cádiz.")
        self.assertNotIn("Dempsey", anon)

    def test_conxuncion_catala_nos_apelidos(self):
        """BOE-A-2025-14523: "El Alcalde, Josep Maria Vallès i Navarro."."""
        anon = self._anon("Sant Cugat del Vallès, 3 de julio de 2025. –El Alcalde, Josep Maria Vallès i Navarro.\n")
        self.assertNotIn("Navarro", anon)
        self.assertIn("Sant Cugat del Vallès", anon)

    def test_primeiro_nome_de_pia_nunha_taboa(self):
        """BOE-B-2025-40131: "Florencio Julio Latorre García Calle Lepanto, nº 6",
        "Mª Mercedes Guillamón Duch Calle Irún, 7"."""
        t = ("Labor regadío 25 de noviembre 09:00\n7\n32\n529\nFlorencio Julio Latorre García Calle Lepanto, nº 6\n46300\nUtiel\n"
             "Labor regadío 24 de noviembre 12:30\n6\n32\n528\nMª Mercedes Guillamón Duch Calle Irún, 7, planta 4ª, puerta CD 28008\nMadrid\n")
        anon = self._anon(t)
        self.assertNotIn("Florencio", anon)
        self.assertNotIn("Mª", anon)

    def test_apelido_que_e_un_mes(self):
        """BOE-B-2025-35020: "Peticionario: Eduardo Guerrero Mayo\nCauce: ..."."""
        anon = self._anon("Expediente: 2025-A-19\nPeticionario: Eduardo Guerrero Mayo\nCauce: Arroyo Prado Medio\n"
                          "Término municipal: Ávila\n")
        self.assertNotIn("Marzo", anon)
        self.assertIn("Arroyo Prado Medio", anon)
        anon = self._anon("Resolución de 3 de marzo de 2025.\nMadrid, 3 de Marzo de 2025.\nFirmado: Xoán Páez Veiga\n")
        self.assertIn("3 de Marzo de 2025", anon)

    def test_primeira_persoa_dunha_enumeracion(self):
        """AnuncioC3K1-180825-0001: "de Eloy Sáez Herrero, Marisol Anta Cerdeira\ne Luis ..."."""
        t = ("O presidente do devandito comité comunicou a proposta de modificación da\nsúa composición, consistente:\n"
             "1. Na renuncia, por petición propia, de Eloy Sáez Herrero, Marisol Anta Cerdeira\n"
             "e Luis Ablanedo Galán.\n2. Na proposta de nomeamento, en substitución das persoas anteriores, de:\n")
        anon = self._anon(t)
        for nome in ("Eloy", "Sánchez", "Marisol", "Cerdeira", "Ablanedo"):
            self.assertNotIn(nome, anon)

    def test_primeira_persoa_dunha_enumeracion_noutra_aparicion(self):
        """O mesmo, co texto real: as persoas detéctanse por separado noutra
        aparición ("O cesamento de ...") e a pasada de mesma persoa recortaba a
        entidade "de Eloy Sáez Herrero, Marisol..." deixando "Eloy..." á vista."""
        t = ("1. Na renuncia, por petición propia, de Eloy Sáez Herrero, Marisol Anta Cerdeira\n"
             "e Luis Ablanedo Galán.\nRESOLVO:\nO cesamento de Eloy Sáez Herrero, Marisol Anta Cerdeira e Luis "
             "Ablanedo García como membros do comité.\n")
        anon = self._anon(t)
        for nome in ("Eloy", "Sánchez", "Marisol", "Ablanedo"):
            self.assertNotIn(nome, anon)


class TestSobreanonimizacionLote4(unittest.TestCase):
    """Lote 4 (lectura do usuario, 03/10/2026)."""

    def test_area_xeografica_con_guions(self):
        """AnuncioC3K1-180825-0001: "Comité Territorial de Ética da Investigación de Pontevedra-Vigo-Ourense"."""
        t = "Comité Territorial de Ética da Investigación de Pontevedra-Vigo-Ourense e nomeáronse\ncomo membros as persoas."
        self.assertEqual(_persoas(t), [])

    def test_listaxe_de_municipios(self):
        """BOE-A-2025-22094: só tres persoas; o resto son municipios cataláns."""
        t = ("Carrera Judicial a:\nMaría José Llera del Prado, para el cargo de jueza sustituta de los juzgados de\n"
             "Barcelona, Arenys de Mar, Badalona, Berga, Cerdanyola del Vallès, Cornellà de\n"
             "Llobregat, Esplugues de Llobregat, Gavà, Granollers, Hospitalet de Llobregat (L'),\n"
             "Igualada, Manresa, Martorell, Mataró, Mollet del Vallès, Prat de Llobregat (El), Rubí,\n"
             "Sabadell, Sant Boi de Llobregat, Sant Feliu de Llobregat, Santa Coloma de Gramenet,\n"
             "Terrassa, Vic, Vilafranca del Penedès, Vilanova i la Geltrú (Barcelona), Girona, Bisbal\n"
             "d'Empordà (La), Blanes, Figueres, Olot, Puigcerdà, Ripoll, Sant Feliu de Guíxols, Santa\n"
             "Coloma de Farners (Girona), Lleida, Balaguer, Cervera, Seu d'Urgell (La), Solsona,\n"
             "Tremp, Vielha e Mijaran (Lleida) y Tarragona, Amposta, Falset, Gandesa, Reus, Tortosa,\n"
             "Valls, Vendrell (El) (Tarragona);\n"
             "Francisco Javier Sáez Bellido, para el cargo de juez sustituto de los juzgados de\n"
             "Tarragona, Amposta, Falset, Gandesa, Reus, Tortosa, Valls, Vendrell (El) (Tarragona).\n")
        self.assertEqual(sorted(_persoas(t)), ["Francisco Javier Sáez Bellido", "María José Llera del Prado"])

    def test_listaxe_de_persoas_sen_tratamento_segue_tapada(self):
        t = ("Asisten a la reunión: Juan Pérez Gil, Ana López Sanz, Luis Gil Díaz, Eva Sanz Mora, "
             "Pío Díaz Rey, Marta Rey Vidal y Carmen Vidal Ruiz.\n")
        with tempfile.TemporaryDirectory() as d:
            anon, _ = anonimizar_texto(t, RexistroCorrespondencias(d))
        for nome in ("Juan", "Pérez", "Ana", "López", "Luis", "Eva", "Sanz", "Pío", "Marta", "Carmen", "Ruiz"):
            self.assertNotIn(nome, anon)


class TestApelidoPartidoConGuionNaTaboa(unittest.TestCase):
    """BOE-A-2025-15144 (lote 4), FUGA que xa estaba en main: nunha táboa en
    maiúsculas "17 REVUELTA SANCHEZ-\nBEATO, M. AURORA" deixaba á vista a
    primeira parte do apelido partido con guión ao final da liña."""

    def test_primeira_parte_do_apelido_tapada(self):
        t = ("GABINETE SECR. DE ESTADO.\nMADRID/MADRID.\n17 REVUELTA SANCHEZ-\nBEATO, M. AURORA\n"
             "***5495*** A1146\nC2 C. GENERAL AUXILIAR\n")
        with tempfile.TemporaryDirectory() as d:
            anon, _ = anonimizar_texto(t, RexistroCorrespondencias(d))
        for nome in ("REVUELTA", "SANCHEZ", "BEATO", "AURORA"):
            self.assertNotIn(nome, anon)
        self.assertEqual(len(set(re.findall(r"PERSOA_\d+", anon))), 1, anon)


class TestMariaAbreviadaComaPrimeiroNome(unittest.TestCase):
    """BOE-B-2025-42645 (comparación de versións, 04/10/2026), FUGA que xa estaba
    na versión do 27/09 e en main: "M.ª del Carmen Berrocal Gil (No se dispone de
    DNI válido)" nunha listaxe de expropiación quedaba enteiro á vista."""

    def test_m_a_del_carmen_tapada(self):
        t = ("Ayuntamiento de Morón de la\nFrontera\nM.ª del Carmen Berrocal Gil (No se dispone de DNI válido)\n"
             "09/12/2025\n13:45\n80\n45\n77\nMorón de la Frontera\n"
             "Ayuntamiento de Arahal\nM.ª del Carmen Marín Rojas (No se dispone de DNI válido)\n16/12/2025\n"
             "La Puebla de Cazalla\nM ª Josefa Rubio Carmona\n11\n54\n6\n")
        with tempfile.TemporaryDirectory() as d:
            anon, _ = anonimizar_texto(t, RexistroCorrespondencias(d))
        for nome in ("Berrocal", "Marín", "Rojas", "M.ª del Carmen", "Josefa", "Carmona"):
            self.assertNotIn(nome, anon)
        self.assertIn("Morón de la Frontera", anon)
