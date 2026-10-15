import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador import web
from anonimizador.registry import RexistroCorrespondencias


class TestInterfaceRevision(unittest.TestCase):
    def setUp(self):
        web.SESIONS.clear()
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.rexistro_dir = str(self.dir / "rexistro")
        self.client = web.app.test_client()

    def tearDown(self):
        self._tmp.cleanup()

    def _crear_doc(self, nome: str, contido: str) -> str:
        ruta = self.dir / nome
        ruta.write_text(contido, encoding="utf-8")
        return str(ruta)

    def _procesar(self, ruta: str) -> str:
        resposta = self.client.post(
            "/procesar", data={"ruta": ruta, "rexistro": self.rexistro_dir}, follow_redirects=True
        )
        self.assertEqual(resposta.status_code, 200)
        # a URL final tras o redirect e /revisar/<sid>
        sid = resposta.request.path.rsplit("/", 1)[-1]
        return sid

    def test_index_carga(self):
        resposta = self.client.get("/")
        self.assertEqual(resposta.status_code, 200)
        self.assertIn(b"Anonimizador", resposta.data)

    def test_ficheiro_inexistente_amosa_erro(self):
        resposta = self.client.post(
            "/procesar", data={"ruta": "/non/existe.txt", "rexistro": self.rexistro_dir}
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("Non se atopa o ficheiro", resposta.get_data(as_text=True))

    def test_fluxo_completo_fusion_de_homonimo(self):
        doc1 = self._crear_doc("doc1.txt", "Manuel Ferrándiz Salcedo acudiu á vista sinalada.")
        doc2 = self._crear_doc("doc2.txt", "Manuel Ferrándiz Salcedo volveu declarar despois.")

        self._procesar(doc1)  # crea PERSOA_000001, sen marcar
        sid2 = self._procesar(doc2)  # mesmo nome, sen DNI -> PERSOA_000002 marcado

        pax_revision = self.client.get(f"/revisar/{sid2}")
        self.assertIn("PERSOA_000002", pax_revision.get_data(as_text=True))
        self.assertIn("fusionar:PERSOA_000001", pax_revision.get_data(as_text=True))

        sesion = web.SESIONS[sid2]
        resposta = self.client.post(
            f"/revisar/{sid2}/confirmar",
            data={
                "texto_final": sesion["texto_anonimizado"],
                "decision_PERSOA_000002": "fusionar:PERSOA_000001",
            },
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("Revisión confirmada", resposta.get_data(as_text=True))

        # o texto final gardado xa non debe conter o codigo eliminado
        ruta_saida = Path(doc2).with_suffix("").as_posix() + ".anonimizado.txt"
        texto_gardado = Path(ruta_saida).read_text(encoding="utf-8")
        self.assertIn("PERSOA_000001", texto_gardado)
        self.assertNotIn("PERSOA_000002", texto_gardado)

        # e o rexistro debe reflectir a fusion (o codigo eliminado xa non existe)
        rexistro = RexistroCorrespondencias(self.rexistro_dir)
        self.assertNotIn("PERSOA_000002", rexistro._estado["persoas"])
        self.assertIn("PERSOA_000002", rexistro._estado.get("alias", {}))

    def test_fluxo_completo_manter_persoas_distintas(self):
        doc1 = self._crear_doc("doc1.txt", "Manuel Ferrándiz Salcedo acudiu á vista sinalada.")
        doc2 = self._crear_doc("doc2.txt", "Manuel Ferrándiz Salcedo volveu declarar despois.")

        self._procesar(doc1)
        sid2 = self._procesar(doc2)
        sesion = web.SESIONS[sid2]

        self.client.post(
            f"/revisar/{sid2}/confirmar",
            data={
                "texto_final": sesion["texto_anonimizado"],
                "decision_PERSOA_000002": "manter",
            },
        )

        rexistro = RexistroCorrespondencias(self.rexistro_dir)
        self.assertIn("PERSOA_000001", rexistro._estado["persoas"])
        self.assertIn("PERSOA_000002", rexistro._estado["persoas"])

        auditoria = rexistro.ler_auditoria()
        self.assertTrue(any(e["accion"] == "confirmado_persoas_distintas" for e in auditoria))


class TestModoAutomatico(unittest.TestCase):
    """Informe: preguntar ao usuario se quere comprobar o proceso de
    anonimización (revisión, xa existente) ou anonimización automática
    (nova) -- esta última garda directamente, sen crear sesión de
    revisión nin pedir confirmación por cada posible homónimo."""

    def setUp(self):
        web.SESIONS.clear()
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.rexistro_dir = str(self.dir / "rexistro")
        self.client = web.app.test_client()

    def tearDown(self):
        self._tmp.cleanup()

    def _crear_doc(self, nome: str, contido: str) -> str:
        ruta = self.dir / nome
        ruta.write_text(contido, encoding="utf-8")
        return str(ruta)

    def test_ficheiro_solto_gardase_sen_crear_sesion(self):
        doc = self._crear_doc("doc.txt", "Manuel Ferrándiz Salcedo acudiu á vista sinalada.")
        resposta = self.client.post(
            "/procesar",
            data={"ruta": doc, "rexistro": self.rexistro_dir, "modo": "automatico"},
        )
        self.assertEqual(resposta.status_code, 200)
        texto = resposta.get_data(as_text=True)
        self.assertIn("anonimizado(s) sen revisión humana", texto)

        ruta_saida = Path(doc).with_suffix("").with_suffix(".anonimizado.txt")
        self.assertTrue(ruta_saida.exists())
        contido_saida = ruta_saida.read_text(encoding="utf-8")
        self.assertIn("PERSOA_", contido_saida)
        self.assertNotIn("Manuel Ferrándiz Salcedo", contido_saida)
        # non se creou ningunha sesión de revisión pendente
        self.assertEqual(web.SESIONS, {})

    def test_nome_de_ficheiro_con_nome_de_persoa_anonimizase_tamén(self):
        """Informe: "a veces os nomes dos arquivos teñen nomes de persoas
        ou DNI... hai que poñer o código de persoa correspondente" -- o
        propio nome do ficheiro gardado non debe deixar o nome real á
        vista, e ten que usar o MESMO código có do contido."""
        doc = self._crear_doc(
            "Certificado Manuel Ferrandiz Salcedo.txt",
            "Manuel Ferrándiz Salcedo, con DNI 30014811Z, presentou o escrito.",
        )
        resposta = self.client.post(
            "/procesar",
            data={"ruta": doc, "rexistro": self.rexistro_dir, "modo": "automatico"},
        )
        # a orixe amosada no resumo é o propio ficheiro local do usuario
        # (non hai fuga en mostrar iso) -- o que importa é que a SAÍDA
        # (o ficheiro realmente gardado) non leve o nome real.
        self.assertIn("Certificado PERSOA_", resposta.get_data(as_text=True))

        ficheiros_saida = [p.name for p in self.dir.glob("Certificado*.anonimizado.txt")]
        self.assertEqual(len(ficheiros_saida), 1)
        self.assertNotIn("Manuel", ficheiros_saida[0])
        self.assertNotIn("Ferrandiz", ficheiros_saida[0])
        self.assertIn("PERSOA_", ficheiros_saida[0])

    def test_posible_homonimo_non_se_fusiona_sen_revision(self):
        doc1 = self._crear_doc("doc1.txt", "Manuel Ferrándiz Salcedo acudiu á vista sinalada.")
        doc2 = self._crear_doc("doc2.txt", "Manuel Ferrándiz Salcedo volveu declarar despois.")

        self.client.post("/procesar", data={"ruta": doc1, "rexistro": self.rexistro_dir, "modo": "automatico"})
        resposta = self.client.post(
            "/procesar", data={"ruta": doc2, "rexistro": self.rexistro_dir, "modo": "automatico"}
        )
        self.assertIn("1 persoa(s) marcada", resposta.get_data(as_text=True))

        rexistro = RexistroCorrespondencias(self.rexistro_dir)
        # dous códigos distintos -- NUNCA se fusiona automaticamente
        self.assertIn("PERSOA_000001", rexistro._estado["persoas"])
        self.assertIn("PERSOA_000002", rexistro._estado["persoas"])

    def test_cartafol_procesa_todos_os_ficheiros_automaticamente(self):
        # o rexistro vive NUN CARTAFOL IRMÁN, non dentro do cartafol que se
        # vai procesar -- se non, os seus propios ficheiros internos
        # contaríanse coma "omitidos" ao percorrer o cartafol de entrada.
        cartafol_docs = self.dir / "documentos"
        cartafol_docs.mkdir()
        (cartafol_docs / "doc1.txt").write_text("Manuel Ferrándiz Salcedo acudiu á vista.", encoding="utf-8")
        (cartafol_docs / "doc2.txt").write_text("Xoana Veiga Lucas presentou o escrito.", encoding="utf-8")
        (cartafol_docs / "ignorar.bin").write_text("contido binario calquera", encoding="utf-8")

        resposta = self.client.post(
            "/procesar",
            data={"ruta": str(cartafol_docs), "rexistro": self.rexistro_dir, "modo": "automatico"},
        )
        self.assertEqual(resposta.status_code, 200)
        texto = resposta.get_data(as_text=True)
        self.assertIn("2 documento(s) anonimizado(s)", texto)
        self.assertIn("1 ficheiro(s) omitido(s)", texto)
        self.assertEqual(web.SESIONS, {})


class TestProteccionCsrfERebinding(unittest.TestCase):
    """A27 (revisión 21/09/2026): a web só escoita en 127.0.0.1, pero
    calquera páxina aberta no MESMO navegador pode enviar peticións (CSRF)
    e un dominio público podería resolver temporalmente a 127.0.0.1 (DNS
    rebinding) -- ver `web._protexer_contra_csrf_e_rebinding`."""

    def setUp(self):
        web.SESIONS.clear()
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.rexistro_dir = str(self.dir / "rexistro")
        self.client = web.app.test_client()

    def tearDown(self):
        self._tmp.cleanup()

    def test_host_alleo_recházase(self):
        # DNS rebinding: o navegador cre estar en "malicioso.example" pero
        # a petición chega igual a este servidor -- a cabeceira Host di a
        # verdade sobre a orixe que o navegador cre estar usando.
        resposta = self.client.get(
            "/", headers={"Host": "malicioso.example"},
        )
        self.assertEqual(resposta.status_code, 400)

    def test_host_127_0_0_1_permitese(self):
        resposta = self.client.get("/", headers={"Host": "127.0.0.1:5000"})
        self.assertEqual(resposta.status_code, 200)

    def test_post_con_origin_allea_recházase(self):
        # unha web maliciosa aberta noutra pestana enviaría a súa PROPIA
        # orixe en `Origin`, non a desta app -- é o que a distingue dun
        # formulario lexítimo desta mesma páxina.
        resposta = self.client.post(
            "/definir-contrasinal",
            data={"rexistro": self.rexistro_dir, "nova": "seguro123", "confirmacion": "seguro123"},
            headers={"Origin": "https://malicioso.example"},
        )
        self.assertEqual(resposta.status_code, 403)

    def test_post_con_referer_allea_recházase(self):
        resposta = self.client.post(
            "/definir-contrasinal",
            data={"rexistro": self.rexistro_dir, "nova": "seguro123", "confirmacion": "seguro123"},
            headers={"Referer": "https://malicioso.example/pagina.html"},
        )
        self.assertEqual(resposta.status_code, 403)

    def test_post_con_origin_propia_permitese(self):
        resposta = self.client.post(
            "/definir-contrasinal",
            data={"rexistro": self.rexistro_dir, "nova": "seguro123", "confirmacion": "seguro123"},
            headers={"Origin": "http://localhost"},
        )
        self.assertEqual(resposta.status_code, 200)

    def test_post_sen_origin_nin_referer_permitese(self):
        # petición local (script/curl), non un navegador -- barreira
        # BLANDA, non un token CSRF completo (ver comentario en web.py).
        resposta = self.client.post(
            "/definir-contrasinal",
            data={"rexistro": self.rexistro_dir, "nova": "seguro123", "confirmacion": "seguro123"},
        )
        self.assertEqual(resposta.status_code, 200)


if __name__ == "__main__":
    unittest.main()
