"""Novidades pedidas sobre a interface web:
- escoller cartafol de saída distinto do orixinal (`ruta_saida_por_defecto`)
- anonimizar TODOS os ficheiros soportados dentro dun cartafol, cunha
  sesión de revisión propia por cada un (nunca en bloque sen revisión)
- selector nativo de ficheiro/cartafol conectado á ruta `/escoller`
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador import web
from anonimizador.pipeline import listar_ficheiros_soportados, ruta_saida_por_defecto
from anonimizador.registry import RexistroCorrespondencias


class TestRutaSaidaConCartafol(unittest.TestCase):
    def test_sen_cartafol_saida_mantén_o_comportamento_de_sempre(self):
        self.assertEqual(
            ruta_saida_por_defecto("/casos/doc1.txt"),
            "/casos/doc1.anonimizado.txt",
        )
        self.assertEqual(
            ruta_saida_por_defecto("/casos/escrito.docx"),
            "/casos/escrito.anonimizado.docx",
        )

    def test_con_cartafol_saida_vai_aí_en_vez_de_canda_o_orixinal(self):
        self.assertEqual(
            ruta_saida_por_defecto("/casos/doc1.txt", "/saidas"),
            str(Path("/saidas/doc1.anonimizado.txt")),
        )

    def test_con_cartafol_saida_conserva_extension_docx(self):
        self.assertEqual(
            ruta_saida_por_defecto("/casos/escrito.docx", "/saidas"),
            str(Path("/saidas/escrito.anonimizado.docx")),
        )


class TestListarFicheirosSoportados(unittest.TestCase):
    def test_non_volve_procesar_os_resultados_dunha_pasada_anterior(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "demanda.txt").write_text("x")
            (d / "demanda.anonimizado.txt").write_text("x")
            (d / "escrito.docx").write_bytes(b"x")
            (d / "escrito.anonimizado.docx").write_bytes(b"x")
            (d / "Informe.ANONIMIZADO.pdf").write_bytes(b"x")
            soportados, omitidos = listar_ficheiros_soportados(str(d))
        self.assertEqual([Path(f).name for f in soportados], ["demanda.txt", "escrito.docx"])
        self.assertEqual(
            sorted(Path(f).name for f in omitidos),
            ["Informe.ANONIMIZADO.pdf", "demanda.anonimizado.txt", "escrito.anonimizado.docx"],
        )

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_atopa_soportados_e_omite_o_resto_recursivamente(self):
        (self.dir / "doc1.txt").write_text("ola", encoding="utf-8")
        subcartafol = self.dir / "sub"
        subcartafol.mkdir()
        (subcartafol / "doc2.txt").write_text("ola de novo", encoding="utf-8")
        (subcartafol / "plano.dwg").write_bytes(b"\x00\x01")

        soportados, omitidos = listar_ficheiros_soportados(str(self.dir))

        nomes_soportados = {Path(p).name for p in soportados}
        nomes_omitidos = {Path(p).name for p in omitidos}
        self.assertEqual(nomes_soportados, {"doc1.txt", "doc2.txt"})
        self.assertEqual(nomes_omitidos, {"plano.dwg"})


class TestProcesarCartafolNaWeb(unittest.TestCase):
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

    def test_procesar_un_cartafol_crea_unha_sesion_por_ficheiro(self):
        entrada = self.dir / "entrada"
        entrada.mkdir()
        (entrada / "doc1.txt").write_text(
            "Manuel Ferrándiz Salcedo acudiu á vista.", encoding="utf-8"
        )
        (entrada / "doc2.txt").write_text(
            "Rita Martorell Vilela declarou tamén.", encoding="utf-8"
        )
        (entrada / "plano.dwg").write_bytes(b"\x00\x01")

        resposta = self.client.post(
            "/procesar",
            data={"ruta": str(entrada), "rexistro": self.rexistro_dir},
            follow_redirects=True,
        )
        self.assertEqual(resposta.status_code, 200)
        texto = resposta.get_data(as_text=True)
        self.assertIn("2 documento(s) procesado(s)", texto)
        self.assertIn("1 ficheiro(s) omitido(s)", texto)

        # as dúas sesións pendentes teñen que aparecer listadas
        self.assertIn("doc1.txt", texto)
        self.assertIn("doc2.txt", texto)
        self.assertEqual(
            sum(1 for s in web.SESIONS.values() if not s["confirmado"]), 2
        )

    def test_procesar_cartafol_baleiro_de_soportados_amosa_erro(self):
        entrada = self.dir / "entrada_baleira"
        entrada.mkdir()
        (entrada / "plano.dwg").write_bytes(b"\x00\x01")

        resposta = self.client.post(
            "/procesar", data={"ruta": str(entrada), "rexistro": self.rexistro_dir}
        )
        self.assertIn("Non se atopou ningún documento soportado", resposta.get_data(as_text=True))

    def test_cartafol_de_saida_distinto_do_orixinal(self):
        doc = self._crear_doc("declaracion.txt", "Manuel Ferrándiz Salcedo acudiu á vista.")
        saida = self.dir / "saidas"

        resposta = self.client.post(
            "/procesar",
            data={"ruta": doc, "rexistro": self.rexistro_dir, "cartafol_saida": str(saida)},
            follow_redirects=True,
        )
        sid = resposta.request.path.rsplit("/", 1)[-1]
        sesion = web.SESIONS[sid]

        self.client.post(
            f"/revisar/{sid}/confirmar",
            data={"texto_final": sesion["texto_anonimizado"], "rexistro_dir": self.rexistro_dir},
        )

        ruta_esperada = saida / "declaracion.anonimizado.txt"
        self.assertTrue(ruta_esperada.exists())
        self.assertFalse((self.dir / "declaracion.anonimizado.txt").exists())

    def test_dous_ficheiros_co_mesmo_nome_en_subcartafoles_non_se_sobrescriben(self):
        """A18 (revisión 21/09/2026): "A/demanda.pdf" e "B/demanda.pdf",
        procesados cara a un `cartafol_saida` PLANO, calculaban a MESMA
        ruta de saída -- o segundo sobrescribía o primeiro en silencio,
        sen aviso ningún (perda real de contido xa anonimizado)."""
        entrada = self.dir / "entrada"
        (entrada / "A").mkdir(parents=True)
        (entrada / "B").mkdir(parents=True)
        (entrada / "A" / "demanda.txt").write_text(
            "Manuel Ferrándiz Salcedo acudiu á vista.", encoding="utf-8"
        )
        (entrada / "B" / "demanda.txt").write_text(
            "Rita Martorell Vilela declarou tamén.", encoding="utf-8"
        )
        saida = self.dir / "saidas"

        resposta = self.client.post(
            "/procesar",
            data={"ruta": str(entrada), "rexistro": self.rexistro_dir, "modo": "automatico",
                  "cartafol_saida": str(saida)},
            follow_redirects=True,
        )
        self.assertEqual(resposta.status_code, 200)

        ficheiros_saida = sorted(p.name for p in saida.iterdir())
        self.assertEqual(len(ficheiros_saida), 2, f"esperábanse 2 ficheiros de saída, atopados: {ficheiros_saida}")

        contidos = {p.read_text(encoding="utf-8") for p in saida.iterdir()}
        self.assertIn("PERSOA_000001", " ".join(contidos))
        self.assertIn("PERSOA_000002", " ".join(contidos))
        # nomes distintos: ningún dos dous se perdeu por sobrescritura
        self.assertNotEqual(*ficheiros_saida)


class TestSelectorNaWeb(unittest.TestCase):
    def setUp(self):
        self.client = web.app.test_client()

    def test_devolve_a_ruta_escollida_como_json(self):
        with mock.patch.object(web.selector, "escoller", return_value="/tmp/escollido"):
            resposta = self.client.get("/escoller?tipo=cartafol")
        self.assertEqual(resposta.get_json(), {"ruta": "/tmp/escollido"})

    def test_devolve_ruta_none_se_se_pecha_sen_escoller(self):
        with mock.patch.object(web.selector, "escoller", return_value=None):
            resposta = self.client.get("/escoller?tipo=ficheiro")
        self.assertEqual(resposta.get_json(), {"ruta": None})


if __name__ == "__main__":
    unittest.main()
