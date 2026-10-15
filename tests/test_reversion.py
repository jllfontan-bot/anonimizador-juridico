import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador.pipeline import anonimizar_texto
from anonimizador.registry import RexistroCorrespondencias
from anonimizador import web


_CONTRASINAL_PROBA = "contrasinal_proba_1234"


class TestReversion(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.rexistro = RexistroCorrespondencias(self._tmp.name)
        self.rexistro.definir_contrasinal_reversion(_CONTRASINAL_PROBA)

    def tearDown(self):
        self._tmp.cleanup()

    def test_reverter_sen_motivo_falla(self):
        anonimizar_texto("Manuel Ferrándiz Salcedo, con DNI 30014811-Z, declarou.", self.rexistro)
        with self.assertRaises(ValueError):
            self.rexistro.reverter("PERSOA_000001", "", _CONTRASINAL_PROBA)

    def test_reverter_codigo_descoñecido_falla(self):
        with self.assertRaises(KeyError):
            self.rexistro.reverter("PERSOA_999999", "proba", _CONTRASINAL_PROBA)

    def test_reverter_sen_contrasinal_definida_falla(self):
        outro = RexistroCorrespondencias(tempfile.mkdtemp())
        anonimizar_texto("Manuel Ferrándiz Salcedo, con DNI 30014811-Z, declarou.", outro)
        with self.assertRaises(ValueError):
            outro.reverter("PERSOA_000001", "proba", "calquera")

    def test_reverter_contrasinal_incorrecta_falla_e_queda_na_auditoria(self):
        anonimizar_texto("Manuel Ferrándiz Salcedo, con DNI 30014811-Z, declarou.", self.rexistro)
        with self.assertRaises(ValueError):
            self.rexistro.reverter("PERSOA_000001", "proba", "contrasinal errada")
        auditoria = self.rexistro.ler_auditoria()
        self.assertTrue(any(e["accion"] == "reversion_denegada" for e in auditoria))

    def test_reverter_devolve_identidade_real(self):
        anonimizar_texto("Manuel Ferrándiz Salcedo, con DNI 30014811-Z, declarou.", self.rexistro)
        dados = self.rexistro.reverter("PERSOA_000001", "presentación en xulgado", _CONTRASINAL_PROBA)
        self.assertIn("Manuel Ferrándiz Salcedo", dados["nomes"])
        self.assertEqual(dados["dni"], "30014811H")  # letra recalculada, non a "Z" orixinal (inválida)
        self.assertEqual(dados["codigo_actual"], "PERSOA_000001")

    def test_reverter_acepta_codigo_id(self):
        """A26 (revisión 21/09/2026): o que se VE redactado xunto a un DNI
        é o código ID_..., non PERSOA_... -- antes deste arranxo, pegar
        "ID_000001" na pantalla de reversión daba sempre "código
        descoñecido", aínda que a persoa existise co código PERSOA_000001."""
        anonimizar_texto("Manuel Ferrándiz Salcedo, con DNI 30014811-Z, declarou.", self.rexistro)
        dados = self.rexistro.reverter("ID_000001", "presentación en xulgado", _CONTRASINAL_PROBA)
        self.assertIn("Manuel Ferrándiz Salcedo", dados["nomes"])
        self.assertEqual(dados["codigo_actual"], "PERSOA_000001")
        self.assertEqual(dados["codigo_solicitado"], "ID_000001")

    def test_reversion_queda_na_auditoria(self):
        anonimizar_texto("Manuel Ferrándiz Salcedo, con DNI 30014811-Z, declarou.", self.rexistro)
        self.rexistro.reverter(
            "PERSOA_000001", "presentación en xulgado", _CONTRASINAL_PROBA, solicitante="proba_test"
        )
        auditoria = self.rexistro.ler_auditoria()
        eventos = [e for e in auditoria if e["accion"] == "reversion"]
        self.assertEqual(len(eventos), 1)
        self.assertIn("presentación en xulgado", eventos[0]["motivo"])
        self.assertIn("proba_test", eventos[0]["motivo"])

    def test_reverter_segue_alias_tras_fusion(self):
        """Se un código foi fusionado noutro, reverter debe seguir o alias
        e devolver a identidade do código vixente."""
        doc1 = "Manuel Ferrándiz Salcedo acudiu á vista sinalada."
        doc2 = "Manuel Ferrándiz Salcedo volveu declarar despois."
        anonimizar_texto(doc1, self.rexistro)
        anonimizar_texto(doc2, self.rexistro)  # crea PERSOA_000002, marcado

        self.rexistro.fusionar("PERSOA_000001", "PERSOA_000002")

        dados = self.rexistro.reverter("PERSOA_000002", "verificación", _CONTRASINAL_PROBA)
        self.assertEqual(dados["codigo_actual"], "PERSOA_000001")
        self.assertEqual(dados["codigo_solicitado"], "PERSOA_000002")
        self.assertIn("Manuel Ferrándiz Salcedo", dados["nomes"])


class TestListadoCorrespondencias(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.rexistro = RexistroCorrespondencias(self._tmp.name)
        self.rexistro.definir_contrasinal_reversion(_CONTRASINAL_PROBA)

    def tearDown(self):
        self._tmp.cleanup()

    def test_listar_sen_motivo_falla(self):
        anonimizar_texto("Manuel Ferrándiz Salcedo, con DNI 30014811-Z, declarou.", self.rexistro)
        with self.assertRaises(ValueError):
            self.rexistro.listar_correspondencias("", _CONTRASINAL_PROBA)
        # un formulario incompleto non é un intento de acceso -- non queda na auditoría
        self.assertFalse(any(
            e["accion"].startswith("listado_completo") for e in self.rexistro.ler_auditoria()
        ))

    def test_listar_sen_contrasinal_definida_falla(self):
        outro = RexistroCorrespondencias(tempfile.mkdtemp())
        anonimizar_texto("Manuel Ferrándiz Salcedo, con DNI 30014811-Z, declarou.", outro)
        with self.assertRaises(ValueError):
            outro.listar_correspondencias("proba", "calquera")

    def test_listar_contrasinal_incorrecta_falla_e_queda_na_auditoria(self):
        anonimizar_texto("Manuel Ferrándiz Salcedo, con DNI 30014811-Z, declarou.", self.rexistro)
        with self.assertRaises(ValueError):
            self.rexistro.listar_correspondencias("auditoría", "contrasinal errada")
        auditoria = self.rexistro.ler_auditoria()
        self.assertTrue(any(e["accion"] == "listado_completo_denegado" for e in auditoria))
        self.assertFalse(any(e["accion"] == "listado_completo" for e in auditoria))

    def test_listar_devolve_todas_as_correspondencias(self):
        anonimizar_texto("Manuel Ferrándiz Salcedo, con DNI 30014811-Z, declarou.", self.rexistro)
        anonimizar_texto("Xoana Veiga Lucas presentou o escrito.", self.rexistro)
        resultado = self.rexistro.listar_correspondencias("auditoría interna", _CONTRASINAL_PROBA)
        self.assertEqual(resultado["total"], 2)
        primeira = resultado["entradas"][0]
        self.assertEqual(primeira["codigo"], "PERSOA_000001")
        self.assertEqual(primeira["codigo_id"], "ID_000001")
        self.assertIn("Manuel Ferrándiz Salcedo", primeira["nomes"])
        self.assertEqual(primeira["dni"], "30014811H")
        self.assertIn("creado", primeira)

    def test_listado_ordenado_por_numero(self):
        doc1 = "Manuel Ferrándiz Salcedo acudiu á vista sinalada."
        doc2 = "Xoana Veiga Lucas presentou o escrito."
        doc3 = "Brais Lorenzo Ogando Fandiño asinou a acta."
        anonimizar_texto(doc1, self.rexistro)
        anonimizar_texto(doc2, self.rexistro)
        anonimizar_texto(doc3, self.rexistro)
        resultado = self.rexistro.listar_correspondencias("proba", _CONTRASINAL_PROBA)
        codigos = [e["codigo"] for e in resultado["entradas"]]
        self.assertEqual(codigos, ["PERSOA_000001", "PERSOA_000002", "PERSOA_000003"])

    def test_listado_de_rexistro_baleiro(self):
        resultado = self.rexistro.listar_correspondencias("proba", _CONTRASINAL_PROBA)
        self.assertEqual(resultado["total"], 0)
        self.assertEqual(resultado["entradas"], [])
        # aínda así, o acceso queda auditado
        auditoria = self.rexistro.ler_auditoria()
        self.assertTrue(any(e["accion"] == "listado_completo" for e in auditoria))

    def test_codigo_fusionado_non_aparece_coma_fila_propia(self):
        doc1 = "Manuel Ferrándiz Salcedo acudiu á vista sinalada."
        doc2 = "Manuel Ferrándiz Salcedo volveu declarar despois."
        anonimizar_texto(doc1, self.rexistro)
        anonimizar_texto(doc2, self.rexistro)  # crea PERSOA_000002
        self.rexistro.fusionar("PERSOA_000001", "PERSOA_000002")

        resultado = self.rexistro.listar_correspondencias("proba", _CONTRASINAL_PROBA)
        self.assertEqual(resultado["total"], 1)
        self.assertEqual(resultado["entradas"][0]["codigo"], "PERSOA_000001")
        self.assertEqual(resultado["entradas"][0]["fusionados"], ["PERSOA_000002"])

    def test_cadea_de_fusions_resolvese(self):
        doc1 = "Manuel Ferrándiz Salcedo acudiu á vista sinalada."
        doc2 = "Manuel Ferrándiz Salcedo volveu declarar despois."
        doc3 = "Manuel Ferrándiz Salcedo asinou tamén a acta."
        anonimizar_texto(doc1, self.rexistro)
        anonimizar_texto(doc2, self.rexistro)
        anonimizar_texto(doc3, self.rexistro)
        self.rexistro.fusionar("PERSOA_000002", "PERSOA_000003")  # 3 -> 2
        self.rexistro.fusionar("PERSOA_000001", "PERSOA_000002")  # 2 -> 1 (cadea 3->2->1)

        resultado = self.rexistro.listar_correspondencias("proba", _CONTRASINAL_PROBA)
        self.assertEqual(resultado["total"], 1)
        self.assertEqual(
            sorted(resultado["entradas"][0]["fusionados"]), ["PERSOA_000002", "PERSOA_000003"]
        )

    def test_listado_queda_na_auditoria_e_distinguese_dunha_reversion(self):
        anonimizar_texto("Manuel Ferrándiz Salcedo, con DNI 30014811-Z, declarou.", self.rexistro)
        self.rexistro.listar_correspondencias(
            "auditoría interna", _CONTRASINAL_PROBA, solicitante="proba_test"
        )
        auditoria = self.rexistro.ler_auditoria()
        eventos = [e for e in auditoria if e["accion"] == "listado_completo"]
        self.assertEqual(len(eventos), 1)
        self.assertIn("auditoría interna", eventos[0]["motivo"])
        self.assertIn("proba_test", eventos[0]["motivo"])
        self.assertFalse(any(e["accion"] == "reversion" for e in auditoria))

    def test_paxinacion_desde_e_limite(self):
        anonimizar_texto("Manuel Ferrándiz Salcedo, con DNI 30014811-Z, declarou.", self.rexistro)
        anonimizar_texto("Xoana Veiga Lucas presentou o escrito.", self.rexistro)
        resultado = self.rexistro.listar_correspondencias(
            "proba", _CONTRASINAL_PROBA, desde=1, limite=1
        )
        self.assertEqual(resultado["total"], 2)  # o total é sempre o real
        self.assertEqual(len(resultado["entradas"]), 1)
        self.assertEqual(resultado["entradas"][0]["codigo"], "PERSOA_000002")
        eventos = [e for e in self.rexistro.ler_auditoria() if e["accion"] == "listado_completo"]
        self.assertIn("1 de 2", eventos[-1]["motivo"])
        self.assertIn("desde 1", eventos[-1]["motivo"])


class TestContrasinalReversion(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.rexistro = RexistroCorrespondencias(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_non_ten_contrasinal_ao_crear(self):
        self.assertFalse(self.rexistro.ten_contrasinal_reversion())

    def test_definir_contrasinal_curta_falla(self):
        with self.assertRaises(ValueError):
            self.rexistro.definir_contrasinal_reversion("curta")

    def test_definir_e_verificar_contrasinal(self):
        self.rexistro.definir_contrasinal_reversion(_CONTRASINAL_PROBA)
        self.assertTrue(self.rexistro.ten_contrasinal_reversion())
        self.assertTrue(self.rexistro._verificar_contrasinal_reversion(_CONTRASINAL_PROBA))
        self.assertFalse(self.rexistro._verificar_contrasinal_reversion("outra cousa"))

    def test_cambiar_contrasinal_esixe_a_actual(self):
        self.rexistro.definir_contrasinal_reversion(_CONTRASINAL_PROBA)
        with self.assertRaises(ValueError):
            self.rexistro.definir_contrasinal_reversion("nova_contrasinal_1234", actual="errada")
        self.rexistro.definir_contrasinal_reversion("nova_contrasinal_1234", actual=_CONTRASINAL_PROBA)
        self.assertTrue(self.rexistro._verificar_contrasinal_reversion("nova_contrasinal_1234"))


class TestReversionWeb(unittest.TestCase):
    def setUp(self):
        web.SESIONS.clear()
        self._tmp = tempfile.TemporaryDirectory()
        self.rexistro_dir = str(Path(self._tmp.name) / "rexistro")
        self.client = web.app.test_client()

    def tearDown(self):
        self._tmp.cleanup()

    def test_formulario_carga(self):
        resposta = self.client.get("/reverter")
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("Reversión controlada", resposta.get_data(as_text=True))

    def test_reversion_sen_motivo_amosa_erro(self):
        rexistro = RexistroCorrespondencias(self.rexistro_dir)
        anonimizar_texto("Manuel Ferrándiz Salcedo, con DNI 30014811-Z, declarou.", rexistro)

        resposta = self.client.post(
            "/reverter",
            data={"rexistro": self.rexistro_dir, "codigo": "PERSOA_000001", "motivo": ""},
        )
        self.assertIn("motivo", resposta.get_data(as_text=True).lower())

    def test_reversion_completa_amosa_identidade(self):
        rexistro = RexistroCorrespondencias(self.rexistro_dir)
        anonimizar_texto("Manuel Ferrándiz Salcedo, con DNI 30014811-Z, declarou.", rexistro)
        rexistro.definir_contrasinal_reversion(_CONTRASINAL_PROBA)

        resposta = self.client.post(
            "/reverter",
            data={
                "rexistro": self.rexistro_dir,
                "codigo": "PERSOA_000001",
                "motivo": "proba de revisión",
                "contrasinal": _CONTRASINAL_PROBA,
            },
        )
        texto = resposta.get_data(as_text=True)
        self.assertIn("Manuel Ferrándiz Salcedo", texto)
        self.assertIn("30014811H", texto)

    def test_reversion_con_ruta_de_rexistro_inexistente_amosa_erro_claro(self):
        """A26 (revisión 21/09/2026): antes deste arranxo, apuntar a unha
        ruta de rexistro escrita mal (que non existe) creaba en silencio
        un rexistro NOVO baleiro nesa ruta, e o erro amosado era "aínda
        non hai contrasinal de reversión definida" -- confuso, porque o
        problema real é que non era ESE rexistro. Agora ten que quedar
        claro que non se atopou ningún rexistro nesa ruta."""
        ruta_mal_escrita = str(Path(self._tmp.name) / "rexistro_qeu_non_existe")
        resposta = self.client.post(
            "/reverter",
            data={
                "rexistro": ruta_mal_escrita,
                "codigo": "PERSOA_000001",
                "motivo": "proba",
                "contrasinal": "calquera",
            },
        )
        texto = resposta.get_data(as_text=True)
        self.assertIn("Non se atopou ningún rexistro", texto)
        # e sobre todo: NON debe crear un rexistro novo baleiro nesa ruta
        self.assertFalse((Path(ruta_mal_escrita) / "rexistro.enc").exists())

    def test_definir_contrasinal_web_primeira_vez(self):
        resposta = self.client.post(
            "/definir-contrasinal",
            data={
                "rexistro": self.rexistro_dir,
                "nova": _CONTRASINAL_PROBA,
                "confirmacion": _CONTRASINAL_PROBA,
            },
        )
        texto = resposta.get_data(as_text=True)
        self.assertIn("definida correctamente", texto)
        rexistro = RexistroCorrespondencias(self.rexistro_dir)
        self.assertTrue(rexistro.ten_contrasinal_reversion())


class TestListadoCorrespondenciasWeb(unittest.TestCase):
    def setUp(self):
        web.SESIONS.clear()
        self._tmp = tempfile.TemporaryDirectory()
        self.rexistro_dir = str(Path(self._tmp.name) / "rexistro")
        self.client = web.app.test_client()

    def tearDown(self):
        self._tmp.cleanup()

    def test_formulario_listado_carga(self):
        resposta = self.client.get("/listar-correspondencias")
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("Listado completo de correspondencias", resposta.get_data(as_text=True))

    def test_listado_sen_confirmar_non_abre_o_rexistro(self):
        rexistro = RexistroCorrespondencias(self.rexistro_dir)
        anonimizar_texto("Manuel Ferrándiz Salcedo, con DNI 30014811-Z, declarou.", rexistro)
        rexistro.definir_contrasinal_reversion(_CONTRASINAL_PROBA)

        resposta = self.client.post(
            "/listar-correspondencias",
            data={
                "rexistro": self.rexistro_dir, "motivo": "proba",
                "contrasinal": _CONTRASINAL_PROBA,
            },
        )
        texto = resposta.get_data(as_text=True)
        self.assertNotIn("Manuel Ferrándiz Salcedo", texto)
        self.assertFalse(any(
            e["accion"].startswith("listado_completo") for e in rexistro.ler_auditoria()
        ))

    def test_listado_con_ruta_de_rexistro_inexistente_amosa_erro_claro(self):
        ruta_mal_escrita = str(Path(self._tmp.name) / "rexistro_qeu_non_existe")
        resposta = self.client.post(
            "/listar-correspondencias",
            data={
                "rexistro": ruta_mal_escrita, "motivo": "proba",
                "contrasinal": "calquera", "confirmo": "1",
            },
        )
        texto = resposta.get_data(as_text=True)
        self.assertIn("Non se atopou ningún rexistro", texto)
        self.assertFalse((Path(ruta_mal_escrita) / "rexistro.enc").exists())

    def test_listado_completo_amosa_tabla(self):
        rexistro = RexistroCorrespondencias(self.rexistro_dir)
        anonimizar_texto("Manuel Ferrándiz Salcedo, con DNI 30014811-Z, declarou.", rexistro)
        rexistro.definir_contrasinal_reversion(_CONTRASINAL_PROBA)

        resposta = self.client.post(
            "/listar-correspondencias",
            data={
                "rexistro": self.rexistro_dir, "motivo": "auditoría interna",
                "contrasinal": _CONTRASINAL_PROBA, "confirmo": "1",
            },
        )
        texto = resposta.get_data(as_text=True)
        self.assertIn("PERSOA_000001", texto)
        self.assertIn("ID_000001", texto)
        self.assertIn("Manuel Ferrándiz Salcedo", texto)
        self.assertIn("30014811H", texto)

    def test_listado_con_contrasinal_incorrecta_non_filtra_ningun_nome(self):
        rexistro = RexistroCorrespondencias(self.rexistro_dir)
        anonimizar_texto("Manuel Ferrándiz Salcedo, con DNI 30014811-Z, declarou.", rexistro)
        rexistro.definir_contrasinal_reversion(_CONTRASINAL_PROBA)

        resposta = self.client.post(
            "/listar-correspondencias",
            data={
                "rexistro": self.rexistro_dir, "motivo": "proba",
                "contrasinal": "errada", "confirmo": "1",
            },
        )
        texto = resposta.get_data(as_text=True)
        self.assertNotIn("Manuel Ferrándiz Salcedo", texto)
        self.assertIn("incorrecta", texto.lower())

    def test_listado_sen_motivo_amosa_erro(self):
        rexistro = RexistroCorrespondencias(self.rexistro_dir)
        rexistro.definir_contrasinal_reversion(_CONTRASINAL_PROBA)
        resposta = self.client.post(
            "/listar-correspondencias",
            data={
                "rexistro": self.rexistro_dir, "motivo": "",
                "contrasinal": _CONTRASINAL_PROBA, "confirmo": "1",
            },
        )
        self.assertIn("motivo", resposta.get_data(as_text=True).lower())

    def test_listado_rexeita_origin_allea(self):
        resposta = self.client.post(
            "/listar-correspondencias",
            data={"rexistro": self.rexistro_dir, "motivo": "proba", "contrasinal": "x", "confirmo": "1"},
            headers={"Origin": "https://malicioso.example"},
        )
        self.assertEqual(resposta.status_code, 403)

    def test_listado_rexeita_host_alleo(self):
        resposta = self.client.get(
            "/listar-correspondencias", headers={"Host": "malicioso.example"}
        )
        self.assertEqual(resposta.status_code, 400)

    def test_paxinacion_web(self):
        rexistro = RexistroCorrespondencias(self.rexistro_dir)
        anonimizar_texto("Manuel Ferrándiz Salcedo acudiu á vista sinalada.", rexistro)
        anonimizar_texto("Xoana Veiga Lucas presentou o escrito.", rexistro)
        rexistro.definir_contrasinal_reversion(_CONTRASINAL_PROBA)

        tamano_orixinal = web._FILAS_POR_PAXINA
        web._FILAS_POR_PAXINA = 1
        try:
            resposta = self.client.post(
                "/listar-correspondencias",
                data={
                    "rexistro": self.rexistro_dir, "motivo": "proba",
                    "contrasinal": _CONTRASINAL_PROBA, "confirmo": "1",
                },
            )
            texto = resposta.get_data(as_text=True)
            self.assertIn("Manuel Ferrándiz Salcedo", texto)
            self.assertNotIn("Xoana Veiga Lucas", texto)
            self.assertIn("Amosando 1 de 2", texto)
            self.assertIn("Ver as seguintes", texto)
        finally:
            web._FILAS_POR_PAXINA = tamano_orixinal


if __name__ == "__main__":
    unittest.main()
