import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador.recognizers import detectar


def _por_etiqueta(texto, etiqueta):
    return [e.texto for e in detectar(texto) if e.etiqueta == etiqueta]


class TestDniNie(unittest.TestCase):
    def test_dni_solto_normal(self):
        """A letra final RECALCÚLASE sempre a partir dos díxitos (ver
        comentario de `recognizers.detectar`) -- "30014811" ten "H" coma
        letra de control real, aínda que o texto orixinal poña outra."""
        self.assertEqual(
            _por_etiqueta("Manuel Ferrándiz Salcedo, con DNI 30014811Z, presentou o escrito.", "DNI_NIE"),
            ["30014811H"],
        )

    def test_dni_pegado_a_guion_baixo_en_nome_de_ficheiro(self):
        """Caso real: un certificado de apoderamento xudicial leva o nome
        do documento anexo incrustado no propio texto
        ("Solicitud_ApudActa_90817269K.pdf") -- o DNI real completo
        quedaba sen redactar porque "_" CONTA coma carácter "de palabra"
        (`\\w`/`\\b`), así que non había fronteira ningunha entre "_" e o
        primeiro díxito e o patrón antigo (baseado en `\\b`) nunca
        chegaba a probalo."""
        self.assertEqual(
            _por_etiqueta("OTROS DOCUMENTOS: Solicitud_ApudActa_90817269K.pdf", "DNI_NIE"),
            ["90817269K"],
        )

    def test_nie_pegado_a_guion_baixo(self):
        self.assertEqual(
            _por_etiqueta("adxunto_X1234567L_copia.pdf", "DNI_NIE"),
            ["X1234567L"],
        )

    def test_non_confunde_dixitos_pegados_a_letras_reais_cun_dni(self):
        """Un DNI pegado a letras REAIS (non "_") a ambos os dous lados
        segue sen ser un DNI de verdade -- só se relaxa a esixencia para
        "_", nunca para letras ou díxitos."""
        self.assertEqual(_por_etiqueta("ABC30014811Zxyz", "DNI_NIE"), [])


class TestTelefono(unittest.TestCase):
    def test_formato_espanol_sen_etiqueta(self):
        self.assertEqual(_por_etiqueta("chame ao 612 345 678", "TELEFONO"), ["612 345 678"])
        self.assertEqual(_por_etiqueta("chame ao 981 12 34 56", "TELEFONO"), ["981 12 34 56"])
        self.assertEqual(_por_etiqueta("chame ao 761 13 66 05", "TELEFONO"), ["761 13 66 05"])

    def test_con_etiqueta_calquera_prefixo(self):
        self.assertEqual(
            _por_etiqueta("Contacto no teléfono 755 617 041 de mañá.", "TELEFONO"), ["755 617 041"])
        self.assertEqual(_por_etiqueta("Tel. +34 701 659 376", "TELEFONO"), ["+34 701 659 376"])

    def test_na_columna_de_documentos_gaña_o_contexto(self):
        """Petición do usuario (28/09/2026): un documento de 9 cifras que
        empeza por 9 baixo "DNI/NIE/PAS" etiquetábase coma [TELEFONO]."""
        texto = "DNI/NIE/PAS\n100006\n987654321 (NIE Y7654321G)\n"
        self.assertEqual(_por_etiqueta(texto, "PASAPORTE"), ["987654321"])
        self.assertEqual(_por_etiqueta(texto, "TELEFONO"), [])

    def test_formato_3_3_3_xa_cuberto(self):
        """Formato xa recoñecido antes deste arranxo -- confirma que
        engadir o novo patrón non rompeu o existente."""
        self.assertEqual(
            _por_etiqueta("O seu teléfono é 666123456 para calquera dúbida.", "TELEFONO"),
            ["666123456"],
        )

    def test_formato_3_2_2_2_movil(self):
        """Caso real de revisión (A19): un teléfono dito/transcrito de
        dous en dous díxitos ("666 12 34 56") non casaba co patrón
        estrito de 3-3-3, que esixe un segundo e un terceiro grupo de
        EXACTAMENTE 3 díxitos seguidos."""
        self.assertEqual(
            _por_etiqueta("Chame ao 666 12 34 56 canto antes.", "TELEFONO"),
            ["666 12 34 56"],
        )

    def test_formato_3_2_2_2_fixo(self):
        self.assertEqual(
            _por_etiqueta("O fixo teléfono é 981 23 45 67 na oficina.", "TELEFONO"),
            ["981 23 45 67"],
        )


class TestCoordenadasUtmNonSonTelefono(unittest.TestCase):
    """Lote 3 (AnuncioG0765, 03/10/2026): "y = 4.694.887\n178" (coordenada UTM
    e o número da cela seguinte) tapábase coma [TELEFONO] e estragaba a táboa."""

    def test_coordenada_con_puntos_de_miles(self):
        texto = "p.q. 6+520 MD da\nPO-532\nx = 534.807\ny = 4.694.887\n178\n1.2\nTreito antigo"
        self.assertEqual(_por_etiqueta(texto, "TELEFONO"), [])
        self.assertEqual(_por_etiqueta("y = 4.694.940 186 m", "TELEFONO"), [])

    def test_telefono_con_puntos_segue(self):
        self.assertEqual(_por_etiqueta("chame ao 981.123.456 de mañá", "TELEFONO"), ["981.123.456"])


class TestEstradaConAdxectivoECodigo(unittest.TestCase):
    """Lote 3 (AnuncioG0765): "dous treitos antigos da estrada autonómica
    PO-532:" tapábase coma [ENDEREZO]; o adxectivo impedía ver o código."""

    def test_estrada_autonomica_con_codigo(self):
        self.assertEqual(_por_etiqueta("a transferencia de dous treitos antigos da estrada autonómica PO-532:\n",
                                       "ENDEREZO"), [])
        self.assertEqual(_por_etiqueta("tramo de la carretera nacional N-550, km 12, en Padrón", "ENDEREZO"), [])

    def test_con_domicilio_segue_sendo_enderezo(self):
        self.assertTrue(_por_etiqueta("con domicilio en carretera nacional N-550, 12, Padrón", "ENDEREZO"))


class TestIban(unittest.TestCase):
    def test_iban_agrupado_de_catro_en_catro(self):
        texto = "A conta bancaria é ES91 2100 0418 4502 0005 1332 para o ingreso."
        self.assertEqual(_por_etiqueta(texto, "IBAN"), ["ES91 2100 0418 4502 0005 1332"])

    def test_pipeline_redacta_o_iban(self):
        from anonimizador.pipeline import anonimizar_texto
        from anonimizador.registry import RexistroCorrespondencias
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            rexistro = RexistroCorrespondencias(d)
            texto = "A conta bancaria é ES91 2100 0418 4502 0005 1332 para o ingreso."
            anon, informe = anonimizar_texto(texto, rexistro)
            self.assertIn("[IBAN]", anon)
            self.assertNotIn("2100", anon)


class TestTarxeta(unittest.TestCase):
    def test_tarxeta_agrupada_de_catro_en_catro(self):
        texto = "Pagouse coa tarxeta 4111 2222 3333 4444 caducada en 2027."
        self.assertEqual(_por_etiqueta(texto, "TARXETA"), ["4111 2222 3333 4444"])

    def test_non_confunde_o_numero_dun_iban_cunha_tarxeta(self):
        """O IBAN redacta ANTES ca a tarxeta (ver `_PATRONS`), así que os
        seus propios grupos de 4 díxitos non deben quedar libres para que
        o recoñecedor de tarxeta os colla á parte."""
        texto = "IBAN ES91 2100 0418 4502 0005 1332 do cliente."
        self.assertEqual(_por_etiqueta(texto, "TARXETA"), [])


class TestReferenciaCatastral(unittest.TestCase):
    def test_referencia_catastral_con_etiqueta(self):
        texto = "A parcela ten referencia catastral 6872011NH3467B0001BF segundo consta."
        self.assertEqual(_por_etiqueta(texto, "REF_CATASTRAL"), ["6872011NH3467B0001BF"])

    def test_so_se_redacta_a_cifra_mantense_a_etiqueta(self):
        from anonimizador.pipeline import anonimizar_texto
        from anonimizador.registry import RexistroCorrespondencias
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            rexistro = RexistroCorrespondencias(d)
            texto = "A parcela ten referencia catastral 6872011NH3467B0001BF segundo consta."
            anon, informe = anonimizar_texto(texto, rexistro)
            self.assertIn("referencia catastral [REF_CATASTRAL]", anon)
            self.assertNotIn("6872011NH3467B0001BF", anon)


class TestSeguridadeSocial(unittest.TestCase):
    def test_numero_de_afiliacion_con_etiqueta(self):
        texto = "Ten número de afiliación a la Seguridad Social 28/1234567890 vixente."
        self.assertEqual(_por_etiqueta(texto, "SEGURIDADE_SOCIAL"), ["28/1234567890"])

    def test_so_se_redacta_a_cifra_mantense_a_etiqueta(self):
        from anonimizador.pipeline import anonimizar_texto
        from anonimizador.registry import RexistroCorrespondencias
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            rexistro = RexistroCorrespondencias(d)
            texto = "Ten número de afiliación a la Seguridad Social 28/1234567890 vixente."
            anon, informe = anonimizar_texto(texto, rexistro)
            self.assertIn("número de afiliación a la Seguridad Social [SEGURIDADE_SOCIAL]", anon)
            self.assertNotIn("28/1234567890", anon)

    def test_etiquetas_e_formatos_que_se_escapaban(self):
        """Formas reais que quedaban SEN redactar ata o 27/09/2026: a etiqueta
        en galego, as siglas (NAF/NASS) e os tres xeitos de escribir o número
        (coas dúas barras, cunha soa ou sen ningunha)."""
        casos = [
            ("Número de afiliación á Seguridade Social 28/12345678/40.", "28/12345678/40"),
            ("NAF 28/1234567840.", "28/1234567840"),
            ("N.º de afiliación: 281234567840.", "281234567840"),
            ("Afiliación á Seguridade Social núm. 28/1234567840.", "28/1234567840"),
            ("NASS 28 1234567840.", "28 1234567840"),
            ("Número de la Seguridad Social 28-1234567840.", "28-1234567840"),
        ]
        for texto, esperado in casos:
            with self.subTest(texto=texto):
                self.assertEqual(_por_etiqueta(texto, "SEGURIDADE_SOCIAL"), [esperado])

    def test_sen_etiqueta_non_se_toca_nada(self):
        """A regra de ouro: sen etiqueta preto, un "díxitos/díxitos" pode ser
        un expediente, unha fracción ou un importe -- NON se redacta."""
        for texto in (
            "O expediente 28/1234567840 está pendente.",
            "Procedemento 12/12345678/40 do xulgado.",
            "A cifra 281234567840 aparece na táboa.",
        ):
            with self.subTest(texto=texto):
                self.assertEqual(_por_etiqueta(texto, "SEGURIDADE_SOCIAL"), [])


class TestMatriculas(unittest.TestCase):
    def test_formato_actual_sen_separador(self):
        self.assertEqual(
            _por_etiqueta("O vehículo con matrícula 1234BCD foi atopado.", "MATRICULA"),
            ["1234BCD"],
        )

    def test_formato_actual_con_guion(self):
        self.assertEqual(
            _por_etiqueta("O vehículo con matrícula 1234-BCD foi atopado.", "MATRICULA"),
            ["1234-BCD"],
        )

    def test_formato_antigo_con_provincia(self):
        """Matrículas anteriores a 2000: provincia + 4 díxitos + 2 letras."""
        self.assertEqual(
            _por_etiqueta("O coche, matrícula PO-1234-AB, estaba mal aparcado.", "MATRICULA"),
            ["PO-1234-AB"],
        )

    def test_non_redacta_calquera_numero_de_catro_cifras(self):
        """Un ano ou número de expediente solto non debe casar coma matrícula."""
        self.assertEqual(_por_etiqueta("Isto ocorreu no ano 2024 no despacho.", "MATRICULA"), [])


class TestEnderezos(unittest.TestCase):
    def test_rua_galega_con_numero(self):
        self.assertEqual(
            _por_etiqueta("A vítima reside na Rúa do Franco, número 12.", "ENDEREZO"),
            ["Rúa do Franco, número 12"],
        )

    def test_calle_castela_con_numero(self):
        """O propio informe pericial real usaba "calle" (castelán), non "rúa"."""
        self.assertEqual(
            _por_etiqueta("O domicilio está na calle Escultor Xosé Esmoris, número 10.", "ENDEREZO"),
            ["calle Escultor Xosé Esmoris, número 10"],
        )

    def test_lugar_rural_con_sen_numero(self):
        self.assertEqual(
            _por_etiqueta("Vive no Lugar de Bembrive, s/n, Vigo.", "ENDEREZO"),
            ["Lugar de Bembrive, s/n"],
        )

    def test_numero_sen_marcador_explicito(self):
        self.assertEqual(
            _por_etiqueta("Reside na Praza do Rei, 3.", "ENDEREZO"),
            ["Praza do Rei, 3"],
        )

    def test_abreviatura_c_barra(self):
        """"c/" é a abreviatura máis común de "calle" en textos administrativos."""
        self.assertEqual(
            _por_etiqueta("Ten domicilio en c/ Rosalía de Castro, 43.", "ENDEREZO"),
            ["c/ Rosalía de Castro, 43"],
        )

    def test_ordinal_mal_lido_polo_ocr_como_aspa(self):
        """Caso real dun PDF escaneado do despacho: o OCR leu "nº5" coma
        `n”5` (aspa curva en vez do símbolo º)."""
        texto = "Ten domicilio profesional en Rúa Pitelos n”5 2* de Santiago."
        self.assertEqual(_por_etiqueta(texto, "ENDEREZO"), ["Rúa Pitelos n”5"])

    def test_numero_con_letra_de_piso_pegada(self):
        """Caso real de revisión (A19): "Rúa Nova 12B" quedaba SEN
        detectar en absoluto (non só sen a letra) -- o `\\b` final do
        patrón esixía fronteira de palabra despois do número, pero entre
        un díxito e unha letra pegada directamente NON hai fronteira
        ningunha (os dous contan coma `\\w`)."""
        self.assertEqual(
            _por_etiqueta("O domicilio está na Rúa Nova 12B, segundo consta no rexistro.", "ENDEREZO"),
            ["Rúa Nova 12B"],
        )

    def test_numero_con_letra_pegada_tras_numero_explicito(self):
        self.assertEqual(
            _por_etiqueta("Reside na Praza do Rei, número 3B.", "ENDEREZO"),
            ["Praza do Rei, número 3B"],
        )

    def test_mencion_de_rua_sen_numero_non_se_redacta(self):
        """Sen número, non hai enderezo completo que redactar aquí (queda
        para o módulo de efecto mosaico se combina con outros datos)."""
        self.assertEqual(
            _por_etiqueta("A empresa ten sede na Rúa Nova, preto do concello.", "ENDEREZO"), []
        )

    def test_pipeline_redacta_enderezo_e_mantén_o_resto_do_texto(self):
        from anonimizador.pipeline import anonimizar_texto
        from anonimizador.registry import RexistroCorrespondencias
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            rexistro = RexistroCorrespondencias(d)
            texto = "Manuel Ferrándiz Salcedo reside na calle Escultor Xosé Esmoris, número 10, en Santiago."
            anon, informe = anonimizar_texto(texto, rexistro)
            self.assertIn("PERSOA_", anon)
            self.assertIn("[ENDEREZO]", anon)
            self.assertNotIn("Manuel Ferrándiz Salcedo", anon)
            self.assertNotIn("Escultor Xosé Esmoris", anon)
            self.assertIn("en Santiago", anon)  # o resto do texto non se toca


class TestColexiado(unittest.TestCase):
    def test_colegiado_numero_completo(self):
        texto = "poseedor del título de Arquitecto, colegiado número 2481 del COAG."
        self.assertEqual(_por_etiqueta(texto, "COLEXIADO"), ["2481"])

    def test_colegiado_no_abreviado(self):
        self.assertEqual(_por_etiqueta("colegiado nº 1234 do colexio de avogados.", "COLEXIADO"), ["1234"])

    def test_colexiada_con_punto_antes_do_ordinal(self):
        """"n.º" (punto antes do símbolo) é outra forma habitual da abreviatura."""
        self.assertEqual(_por_etiqueta("é colexiada n.º 987 no ICA.", "COLEXIADO"), ["987"])

    def test_ordinal_mal_lido_polo_ocr(self):
        self.assertEqual(_por_etiqueta('colegiada n”55 do ICA.', "COLEXIADO"), ["55"])

    def test_so_se_redacta_a_cifra_mantense_o_contexto(self):
        """Pedido explícito: "colegiado número"/"colegiado nº" queda visible,
        só desaparece o número."""
        from anonimizador.pipeline import anonimizar_texto
        from anonimizador.registry import RexistroCorrespondencias
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            rexistro = RexistroCorrespondencias(d)
            texto = "Ramón Blanco, colegiado número 2481 del COAG, emitiu o informe."
            anon, informe = anonimizar_texto(texto, rexistro)
            self.assertIn("colegiado número [COLEXIADO] del COAG", anon)
            self.assertNotIn("2481", anon)
            self.assertTrue(any(d["tipo"] == "COLEXIADO" for d in informe["identificadores_directos"]))


class TestPasaporte(unittest.TestCase):
    """O formato dun pasaporte (letras + díxitos) é demasiado xenérico
    para recoñecelo sen contexto -- esíxese a etiqueta "pasaporte" preto,
    igual ca colexiado/referencia/CSV."""

    def test_pasaporte_con_numero(self):
        texto = "Comparece con pasaporte número PAA123456 en la sala."
        self.assertEqual(_por_etiqueta(texto, "PASAPORTE"), ["PAA123456"])

    def test_pasaporte_sen_a_palabra_numero(self):
        self.assertEqual(_por_etiqueta("Comparece con pasaporte PAA123456.", "PASAPORTE"), ["PAA123456"])

    def test_pasaporte_con_ordinal(self):
        self.assertEqual(_por_etiqueta("pasaporte nº AB1234567 caducado.", "PASAPORTE"), ["AB1234567"])

    def test_so_se_redacta_a_cifra_mantense_a_etiqueta(self):
        from anonimizador.pipeline import anonimizar_texto
        from anonimizador.registry import RexistroCorrespondencias
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            rexistro = RexistroCorrespondencias(d)
            texto = "Manuel Ríos, con pasaporte número PAA123456, presentou o escrito."
            anon, informe = anonimizar_texto(texto, rexistro)
            self.assertIn("pasaporte número PERSOA_", anon)  # mesmo código ca o titular
            self.assertNotIn("PAA123456", anon)
            self.assertTrue(any(d["tipo"] == "PASAPORTE" for d in informe["identificadores_directos"]))

    def test_sen_etiqueta_non_se_toca(self):
        """Sen a palabra "pasaporte" preto, un código así de xenérico
        (letras + díxitos) podería ser calquera outra cousa -- non se
        redacta sen contexto, igual ca CSV/referencia/catastral."""
        self.assertEqual(_por_etiqueta("O código PAA123456 aparece na táboa.", "PASAPORTE"), [])

    def test_pasaporte_estranxeiro_con_etiqueta(self):
        """Corpus web 28/09/2026: os pasaportes estranxeiros non seguen o
        formato español (1 letra + 8 díxitos, só díxitos...)."""
        self.assertEqual(
            _por_etiqueta("Presentou o pasaporte número P99887766 na oficina.", "PASAPORTE"), ["P99887766"])
        self.assertEqual(_por_etiqueta("pasaporte: 334455667", "PASAPORTE"), ["334455667"])

    def test_documento_do_representante(self):
        texto = "100003\nQ7T8R2PQXA0004123 (representante 334455667)\n3.6.2026"
        self.assertIn("334455667", _por_etiqueta(texto, "PASAPORTE"))

    def test_columna_dni_nie_pas_caso_real_sintetico(self):
        """Reprodución SINTÉTICA do anexo real do DOG (persoas non
        aseguradas): baixo a columna "DNI/NIE/PAS" só se tapaban os NIE
        con formato; os pasaportes quedaban todos á vista. Os números de
        expediente (6 díxitos) e as datas deben quedar."""
        from anonimizador.pipeline import anonimizar_texto
        from anonimizador.registry import RexistroCorrespondencias
        import tempfile

        texto = (
            "Número de expediente\nDNI/NIE/PAS\nData da resolución\n"
            "100001\nK12345678 (NIE X1234567L)\n2.6.2026\n"
            "100002\nQW123456\n2.6.2026\n"
            "100003\n7T8R2PQXA00041234567B (representante 334455667)\n3.6.2026\n"
            "100004\nRepresentante 445566778\n3.6.2026\n"
            "100005\nB0998877\n4.6.2026\n"
        )
        with tempfile.TemporaryDirectory() as d:
            anon, _ = anonimizar_texto(texto, RexistroCorrespondencias(d))
        for dato in ("K12345678", "X1234567L", "QW123456", "7T8R2PQXA00041234567B",
                     "334455667", "445566778", "B0998877"):
            self.assertNotIn(dato, anon)
        for contexto in ("100001", "100005", "2.6.2026", "DNI/NIE/PAS", "Número de expediente"):
            self.assertIn(contexto, anon)

    def test_sen_cabeceira_de_columna_non_se_tocan_codigos_a_inicio_de_liña(self):
        texto = "Relación de lotes\nQW123456\nB0998877 (lote 2)\n"
        self.assertEqual(_por_etiqueta(texto, "PASAPORTE"), [])


class TestCsv(unittest.TestCase):
    """Un CSV (Código Seguro de Verificación) permite recuperar o documento
    ORIXINAL sen anonimizar no portal do organismo emisor -- deixalo
    visible anula a anonimización aínda que se borren nomes e DNI."""

    def test_codigo_antes_da_etiqueta_caso_real(self):
        """Caso real: nun certificado do Ministerio de Xustiza o CSV vai
        NUNHA LIÑA e a etiqueta "Código Seguro de Verificación" na seguinte."""
        texto = (
            "E04799402-AJ:Pq3q-KihB-ids2-wZq2-K\n"
            "Código Seguro de Verificación\n"
            "Puede verificar este documento en \"https://sedejudicial.justicia.es\""
        )
        self.assertEqual(_por_etiqueta(texto, "CSV"), ["E04799402-AJ:Pq3q-KihB-ids2-wZq2-K"])

    def test_etiqueta_antes_do_codigo(self):
        texto = "Código Seguro de Verificación: E04799402-AJ:Pq3q-KihB-ids2-wZq2-K"
        self.assertEqual(_por_etiqueta(texto, "CSV"), ["E04799402-AJ:Pq3q-KihB-ids2-wZq2-K"])

    def test_abreviatura_csv(self):
        self.assertEqual(_por_etiqueta("CSV: 13525722606135712345", "CSV"), ["13525722606135712345"])

    def test_abreviatura_con_puntos_caso_real(self):
        """Caso real: un certificado de Registradores de España usa
        "C.S.V." (con puntos entre cada letra) -- "CSV" a secas NON o
        recoñece, son literalmente caracteres distintos. Sen isto, o CSV
        quedaba sen redactar en dúas páxinas dun documento real."""
        self.assertEqual(
            _por_etiqueta("C.S.V. : 21502327516EFFB9", "CSV"), ["21502327516EFFB9"]
        )
        self.assertEqual(
            _por_etiqueta("C.S.V.: 21502327516EFFB9", "CSV"), ["21502327516EFFB9"]
        )

    def test_pipeline_mantén_a_etiqueta_e_redacta_so_o_codigo(self):
        from anonimizador.pipeline import anonimizar_texto
        from anonimizador.registry import RexistroCorrespondencias
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            rexistro = RexistroCorrespondencias(d)
            texto = (
                "E04799402-AJ:Pq3q-KihB-ids2-wZq2-K\n"
                "Código Seguro de Verificación\n"
                "Puede verificar este documento en la sede."
            )
            anon, informe = anonimizar_texto(texto, rexistro)
            self.assertIn("[CSV]", anon)
            self.assertNotIn("E04799402", anon)
            self.assertIn("Código Seguro de Verificación", anon)
            self.assertTrue(any(d["tipo"] == "CSV" for d in informe["identificadores_directos"]))


class TestReferencia(unittest.TestCase):
    """Caso real atopado revisando un certificado de apoderamento xudicial:
    "número de referencia" é outra clave de consulta a un portal oficial,
    co mesmo risco de reidentificación cá CSV."""

    def test_numero_solto(self):
        texto = "consta la siguiente información en relación con el apoderamiento con número de referencia 4880840"
        self.assertEqual(_por_etiqueta(texto, "REFERENCIA"), ["4880840"])

    def test_referencia_alfanumerica_con_barra(self):
        self.assertEqual(_por_etiqueta("Número de Referencia: AB-12345/2024", "REFERENCIA"), ["AB-12345/2024"])

    def test_pipeline_mantén_a_etiqueta_e_redacta_so_o_numero(self):
        from anonimizador.pipeline import anonimizar_texto
        from anonimizador.registry import RexistroCorrespondencias
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            rexistro = RexistroCorrespondencias(d)
            texto = "Consta el apoderamiento con número de referencia 4880840 en la base de datos."
            anon, informe = anonimizar_texto(texto, rexistro)
            self.assertIn("número de referencia [REFERENCIA]", anon)
            self.assertNotIn("4880840", anon)
            self.assertTrue(any(d["tipo"] == "REFERENCIA" for d in informe["identificadores_directos"]))


class TestDniConPuntos(unittest.TestCase):
    """Caso real (escrito xudicial, instalación de Windows): os DNI con
    puntos de millares ("12.345.678- V") quedaban SEN anonimizar. Datos
    sintéticos; a letra sempre se recalcula (12345678 -> Z)."""

    def _dnis(self, texto):
        return _por_etiqueta(texto, "DNI_NIE")

    def test_puntos_hifen_espazo_e_letra(self):
        self.assertEqual(
            self._dnis("con DNI 12.345.678- V y doña Ana con DNI 87.654.321-G, vecina"),
            ["12345678Z", "87654321X"],
        )

    def test_salto_de_linha_entre_o_hifen_e_a_letra(self):
        """En PDF a letra pode caer na liña seguinte."""
        self.assertEqual(self._dnis("con DNI 12.345.678-\nV y"), ["12345678Z"])

    def test_letra_pegada_e_letra_separada_sen_hifen(self):
        self.assertEqual(self._dnis("D. Pedro, DNI 12.345.678Z."), ["12345678Z"])
        self.assertEqual(self._dnis("titular 12.345.678 Z de Vigo"), ["12345678Z"])  # letra de control válida

    def test_sen_letra_pero_con_a_palabra_dni_diante(self):
        self.assertEqual(self._dnis("titular del DNI 12.345.678 y domicilio"), ["12345678Z"])
        self.assertEqual(self._dnis("NIF: 12.345.678"), ["12345678Z"])

    def test_dni_antigo_de_7_digitos(self):
        self.assertEqual(self._dnis("NIF: 1.234.567-L"), ["01234567L"])

    def test_nie_con_puntos(self):
        self.assertEqual(self._dnis("NIE X-1.234.567-L residente"), ["X1234567L"])

    def test_mesma_persoa_con_e_sen_puntos_da_o_mesmo_dni_normalizado(self):
        self.assertEqual(self._dnis("DNI 12.345.678-Z"), self._dnis("DNI 12345678Z"))

    def test_importes_e_expedientes_con_puntos_non_son_dni(self):
        for texto in ("abonó 1.234.567 y otros gastos", "expediente 12.345.678 a favor",
                      "capital de 12.345.678 euros", "cifra 1.234.567.890 total"):
            with self.subTest(texto=texto):
                self.assertEqual(self._dnis(texto), [])

    def test_dni_normal_con_hifen_espaciado(self):
        self.assertEqual(self._dnis("DNI 12345678 - Z"), ["12345678Z"])


if __name__ == "__main__":
    unittest.main()


class TestDataNunhaTaboaNonEDni(unittest.TestCase):
    """BOE-A-2026-15923 (lectura de Claude, 30/09/2026): "20200703 Técnicas"
    (data AAAAMMDD + cela seguinte) daba un DNI e borraba a data e o "T"."""

    def test_data_e_palabra_con_til(self):
        from anonimizador import recognizers
        for texto in ("116\n20200703 Técnicas para la búsqueda", "122\n20040101 Búsqueda activa"):
            self.assertEqual(recognizers.detectar(texto), [], texto)


class TestColexiadoOrdeInversa(unittest.TestCase):
    def test_numero_de_colexiado_con_miles(self):
        from anonimizador import recognizers
        self.assertEqual([(e.etiqueta, e.texto) for e in recognizers.detectar(
            "esp. Eléctrica, número de colexiado 1.905 da Coruña.")], [("COLEXIADO", "1.905")])
