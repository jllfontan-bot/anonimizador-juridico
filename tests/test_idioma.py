"""Idioma do programa (castelán por defecto, galego a escoller): códigos de
persoa e etiquetas que se escriben nos documentos, preferencia gardada e
reversión aceptando os dous prefixos. Datos inventados."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador import idioma  # noqa: E402
from anonimizador.pipeline import anonimizar_texto  # noqa: E402
from anonimizador.registry import RexistroCorrespondencias  # noqa: E402

_CONTRASINAL = "contrasinal_proba_1234"
_TEXTO = "Manuel Ferrándiz Salcedo, con DNI 30014811H, vive na rúa do Franco 12 de Santiago."


def _en(lingua):
    return mock.patch.dict(os.environ, {idioma.VARIABLE: lingua})


class TestPreferencia(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._cwd = os.getcwd()
        os.chdir(self._tmp.name)
        self._env = mock.patch.dict(os.environ)
        self._env.start()
        os.environ.pop(idioma.VARIABLE, None)

    def tearDown(self):
        self._env.stop()
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def test_sen_preferencia_e_castelan(self):
        self.assertEqual(idioma.actual(), "es")

    def test_a_preferencia_gardada_sobrevive(self):
        idioma.gardar("gl")
        self.assertEqual(idioma.actual(), "gl")
        idioma.gardar("es")
        self.assertEqual(idioma.actual(), "es")

    def test_preferencia_estragada_cae_ao_castelan(self):
        Path(idioma.FICHEIRO_PREFERENCIAS).write_text("{non é json", encoding="utf-8")
        self.assertEqual(idioma.actual(), "es")

    def test_idioma_descoñecido_non_se_garda(self):
        with self.assertRaises(ValueError):
            idioma.gardar("fr")

    def test_a_variable_de_contorno_manda(self):
        idioma.gardar("es")
        with _en("gl"):
            self.assertEqual(idioma.actual(), "gl")


class TestCodigos(unittest.TestCase):
    def test_visible_e_canonico(self):
        self.assertEqual(idioma.codigo_visible("PERSOA_000007", "es"), "PERSONA_000007")
        self.assertEqual(idioma.codigo_visible("PERSOA_000007", "gl"), "PERSOA_000007")
        for codigo in ("PERSONA_000007", "PERSOA_000007", "ID_000007"):
            self.assertEqual(idioma.codigo_canonico(codigo), "PERSOA_000007")
        self.assertEqual(idioma.codigo_canonico("[DNI_NIE]"), "[DNI_NIE]")

    def test_codigos_dentro_dun_texto(self):
        texto = "PERSOA_000001 e PERSONA_000002 (ID_000003)."
        self.assertEqual(idioma.codigos_visibles_no_texto(texto, "es"),
                         "PERSONA_000001 e PERSONA_000002 (PERSONA_000003).")


class TestDocumentoSegundoOIdioma(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.rexistro = RexistroCorrespondencias(self._tmp.name)
        self.rexistro.definir_contrasinal_reversion(_CONTRASINAL)

    def tearDown(self):
        self._tmp.cleanup()

    def test_castelan(self):
        with _en("es"):
            anon, _ = anonimizar_texto(_TEXTO, self.rexistro)
        self.assertIn("PERSONA_000001", anon)
        self.assertNotIn("PERSOA_", anon)
        self.assertIn("[DIRECCIÓN]", anon)
        self.assertNotIn("Ferrándiz", anon)

    def test_galego(self):
        with _en("gl"):
            anon, _ = anonimizar_texto(_TEXTO, self.rexistro)
        self.assertIn("PERSOA_000001", anon)
        self.assertIn("[ENDEREZO]", anon)

    def test_a_mesma_persoa_leva_o_mesmo_numero_nos_dous_idiomas(self):
        with _en("gl"):
            anon_gl, _ = anonimizar_texto(_TEXTO, self.rexistro)
        with _en("es"):
            anon_es, _ = anonimizar_texto(_TEXTO, self.rexistro)
        self.assertIn("PERSOA_000001", anon_gl)
        self.assertIn("PERSONA_000001", anon_es)

    def test_reverter_acepta_os_dous_prefixos(self):
        with _en("es"):
            anonimizar_texto(_TEXTO, self.rexistro)
        for codigo in ("PERSONA_000001", "PERSOA_000001", " PERSONA_000001 "):
            dados = self.rexistro.reverter(codigo, "proba", _CONTRASINAL)
            self.assertIn("Manuel Ferrándiz Salcedo", dados["nomes"])

    def test_fusionar_con_codigos_en_castelan(self):
        with _en("es"):
            anonimizar_texto("Comparece Uxía Roel Salcedo.", self.rexistro)
            anon, informe = anonimizar_texto("Asina Uxía Roel Salcedo.", self.rexistro)
        persoa = informe["persoas"][0]
        self.assertTrue(persoa["marcado_para_revision"])
        self.assertEqual(persoa["posibles_coincidencias"], ["PERSONA_000001"])
        self.assertIn("PERSONA_000001", persoa["motivo"])
        self.rexistro.fusionar("PERSONA_000001", persoa["codigo"])
        dados = self.rexistro.reverter(persoa["codigo"], "proba", _CONTRASINAL)
        self.assertEqual(dados["codigo_actual"], "PERSOA_000001")


class TestTextos(unittest.TestCase):
    def test_os_dous_idiomas_teñen_as_mesmas_claves_e_marcadores(self):
        import string
        gl, es = idioma.textos("gl"), idioma.textos("es")
        self.assertEqual(set(gl), set(es))
        campos = lambda texto: {c[1] for c in string.Formatter().parse(texto) if c[1]}  # noqa: E731
        for clave in gl:
            self.assertEqual(campos(gl[clave]), campos(es[clave]), clave)

    def test_mensaxes_coñecidas_tradúcense(self):
        self.assertEqual(idioma.traducir_mensaxe("contrasinal de reversión incorrecta", "es"),
                         "contraseña de reversión incorrecta")
        # str(KeyError(...)) vai entre comiñas
        self.assertEqual(idioma.traducir_mensaxe("'código descoñecido no rexistro: PERSONA_000009'", "es"),
                         "código desconocido en el registro: PERSONA_000009")
        self.assertEqual(idioma.traducir_mensaxe("contrasinal de reversión incorrecta", "gl"),
                         "contrasinal de reversión incorrecta")
        self.assertEqual(idioma.traducir_mensaxe("algo que non está no catálogo", "es"), "algo que non está no catálogo")


class TestInterfaceEnCastelan(unittest.TestCase):
    def setUp(self):
        from anonimizador import web
        self.web = web
        web.SESIONS.clear()
        self._tmp = tempfile.TemporaryDirectory()
        self._cwd = os.getcwd()
        os.chdir(self._tmp.name)  # preferencias.json e datos_rexistro van aquí
        self._env = mock.patch.dict(os.environ)
        self._env.start()
        os.environ.pop(idioma.VARIABLE, None)
        self.rexistro_dir = str(Path(self._tmp.name) / "rexistro")
        self.client = web.app.test_client()

    def tearDown(self):
        self._env.stop()
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def test_inicio_en_castelan_por_defecto_e_selector(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('lang="es"', html)
        self.assertIn("Anonimizador de expedientes jurídicos", html)
        self.assertIn("Elegir archivo…", html)
        self.assertIn("PERSONA_000001", html)  # exemplo do aviso da clave
        self.assertIn('value="gl"', html)

    def test_escoller_galego_queda_gardado(self):
        r = self.client.post("/idioma", data={"idioma": "gl"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(idioma.actual(), "gl")
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("Escoller ficheiro…", html)
        self.client.post("/idioma", data={"idioma": "xx"})  # descoñecido: non cambia nada
        self.assertEqual(idioma.actual(), "gl")

    def test_revision_con_codigos_persona(self):
        doc = Path(self._tmp.name) / "doc.txt"
        doc.write_text(_TEXTO, encoding="utf-8")
        r = self.client.post("/procesar", data={"ruta": str(doc), "rexistro": self.rexistro_dir, "modo": "revisar"})
        html = self.client.get(r.headers["Location"]).get_data(as_text=True)
        self.assertIn("Personas detectadas", html)
        self.assertIn("PERSONA_000001", html)
        self.assertNotIn("PERSOA_", html)

    def test_erro_do_rexistro_traducido(self):
        rexistro = RexistroCorrespondencias(self.rexistro_dir)
        anonimizar_texto(_TEXTO, rexistro)
        rexistro.definir_contrasinal_reversion(_CONTRASINAL)
        html = self.client.post("/reverter", data={
            "rexistro": self.rexistro_dir, "codigo": "PERSONA_000001", "motivo": "proba", "contrasinal": "errada"},
        ).get_data(as_text=True)
        self.assertIn("contraseña de reversión incorrecta", html)
        html = self.client.post("/reverter", data={
            "rexistro": self.rexistro_dir, "codigo": "PERSONA_000001", "motivo": "proba", "contrasinal": _CONTRASINAL},
        ).get_data(as_text=True)
        self.assertIn("Identidad recuperada", html)
        self.assertIn("Manuel Ferrándiz Salcedo", html)
        self.assertNotIn("Código vigente", html)  # PERSONA_000001 e PERSOA_000001 son o mesmo código

    def test_pdf_do_listado_en_castelan(self):
        import fitz
        from anonimizador import informe_pdf
        entradas = [{"codigo": "PERSOA_000001", "nomes": ["Persoa Proba"], "dni": None, "contexto": None,
                     "creado": "2026-10-15T10:00:00", "fusionados": ["PERSOA_000002"]}]
        pdf = informe_pdf.listado_correspondencias({"total": 1, "entradas": entradas, "alias_orfos": []}, motivo="proba")
        texto = "".join(p.get_text() for p in fitz.open(stream=pdf, filetype="pdf"))
        self.assertIn("PERSONA_000001", texto)
        self.assertIn("PERSONA_000002", texto)
        self.assertIn("Página 1 de 1", texto)
        self.assertNotIn("PERSOA_", texto)


if __name__ == "__main__":
    unittest.main()
