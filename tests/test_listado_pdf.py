"""Listado de correspondencias: táboa en pantalla e PDF CONFIDENCIAL
(petición do usuario, 03/10/2026: "que cando o pida, saia unha táboa bonita";
"opción de xerar un PDF, advertindo de que é un documento de extrema
sensibilidade, cunha marca de auga de Confidencial")."""

import sys
import tempfile
import unittest
from pathlib import Path

import fitz  # PyMuPDF

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador import informe_pdf, web
from anonimizador.pipeline import anonimizar_texto
from anonimizador.registry import RexistroCorrespondencias

_CONTRASINAL = "proba-contrasinal-1234"
_TEXTO = ("Comparece don Xoán Páez Veiga, con DNI 30014811H, veciño de Lugo, e dona Uxía Roel Salcedo.\n"
          "Asina a avogada dona Antía Varela Doval.\n")


class _Base(unittest.TestCase):
    def setUp(self):
        web.SESIONS.clear()
        self._tmp = tempfile.TemporaryDirectory()
        self.rexistro_dir = str(Path(self._tmp.name) / "rexistro")
        rexistro = RexistroCorrespondencias(self.rexistro_dir)
        anonimizar_texto(_TEXTO, rexistro)
        rexistro.definir_contrasinal_reversion(_CONTRASINAL)
        self.client = web.app.test_client()

    def tearDown(self):
        self._tmp.cleanup()

    def _datos(self, **extra):
        datos = {"rexistro": self.rexistro_dir, "motivo": "proba", "contrasinal": _CONTRASINAL, "confirmo": "1"}
        datos.update(extra)
        return datos


class TestXerarPdf(unittest.TestCase):
    def test_marca_de_auga_en_cada_paxina_e_datos(self):
        entradas = [{"codigo": f"PERSOA_{i:06d}", "nomes": [f"Persoa Proba {i}"], "dni": None, "contexto": None,
                     "creado": "2026-10-03T10:00:00", "fusionados": []} for i in range(1, 121)]
        pdf = informe_pdf.listado_correspondencias({"total": 120, "entradas": entradas, "alias_orfos": []},
                                                   motivo="auditoría 1/2026", solicitante="xllopez")
        with fitz.open(stream=pdf, filetype="pdf") as d:
            self.assertGreater(len(d), 1)
            for paxina in d:
                self.assertIn("CONFIDENCIAL", paxina.get_text())
            texto = "".join(p.get_text() for p in d)
        for agulla in ("PERSOA_000001", "Persoa Proba 120", "auditoría 1/2026", "xllopez", "extrema sensibilidade"):
            self.assertIn(agulla, texto)


class TestListadoWeb(_Base):
    def test_taboa_sen_codigo_de_dni_para_quen_non_ten_dni(self):
        html = self.client.post("/listar-correspondencias", data=self._datos()).get_data(as_text=True)
        self.assertIn("Xoán Páez Veiga", html)
        self.assertIn("30014811H", html)
        self.assertEqual(html.count("ID_0000"), 1, "o código de DNI só para quen ten DNI")

    def test_pdf_require_aviso_contrasinal_e_queda_na_auditoria(self):
        url = "/listar-correspondencias/pdf"
        sen_aviso = self.client.post(url, data=self._datos())
        self.assertNotEqual(sen_aviso.mimetype, "application/pdf")
        mala = self.client.post(url, data=self._datos(contrasinal="mala-contrasinal-99", aviso_pdf="1"))
        self.assertNotEqual(mala.mimetype, "application/pdf")
        boa = self.client.post(url, data=self._datos(aviso_pdf="1"))
        self.assertEqual(boa.mimetype, "application/pdf")
        self.assertIn("CONFIDENCIAL", boa.headers.get("Content-Disposition", ""))
        self.assertIn("no-store", boa.headers.get("Cache-Control", ""))
        with fitz.open(stream=boa.data, filetype="pdf") as d:
            self.assertIn("Uxía Roel Salcedo", "".join(p.get_text() for p in d))
        auditoria = RexistroCorrespondencias(self.rexistro_dir).ler_auditoria()
        self.assertTrue(any("PDF" in (e.get("motivo") or "") for e in auditoria), auditoria[-3:])


if __name__ == "__main__":
    unittest.main()
