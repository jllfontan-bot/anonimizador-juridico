"""Medición contra a referencia do corpus (medicion/corpus_metricas.py): as
etiquetas xéranse co fluxo real do modo corpus sobre documentos sintéticos."""
import os

# Estas probas escribíronse coa interface e os códigos en galego (PERSOA_...).
os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")
import json
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "medicion"))
sys.path.insert(0, str(RAIZ / "tests"))

import corpus_metricas  # noqa: E402
from anonimizador import corpus_revision, web  # noqa: E402
from test_corpus_revision import _pdf  # noqa: E402


class TestCorpusMetricas(unittest.TestCase):
    def setUp(self):
        web.SESIONS.clear()
        self._tmp = tempfile.TemporaryDirectory()
        self.lote = Path(self._tmp.name) / "lote"
        _pdf(self.lote / "docs" / "boe" / "BOE-A-1.pdf", [
            "Comparece don Xoán Páez Veiga ante o xulgado.",
            "Os veciños de Braña presentaron alegacións. A cadela chámase Fufa.",
        ])
        (self.lote / "manifesto.json").write_text(json.dumps({"documentos": [
            {"fonte": "BOE", "id": "BOE-A-1", "data": "2025-01-02", "seccion": "3", "titulo": "t",
             "ficheiro": "boe/BOE-A-1.pdf"},
        ]}), encoding="utf-8")
        corpus_revision.activar(self.lote, ["BOE-A-1"])
        self.client = web.app.test_client()

    def tearDown(self):
        corpus_revision.desactivar()
        self._tmp.cleanup()

    def _etiquetar(self, **decisions) -> dict:
        r = self.client.get("/corpus/BOE-A-1", follow_redirects=True)
        sid = r.request.path.rsplit("/", 1)[-1]
        sesion = web.SESIONS[sid]
        datos = {"rexistro_dir": sesion["rexistro_dir"], "texto_final": sesion["texto_anonimizado"],
                 "decisions_v2": "1"}
        datos.update(decisions)
        if datos.get("anonimizar") == "TODAS":
            datos["anonimizar"] = [p["codigo"] for p in sesion["informe"]["persoas"]]
        self.client.post(f"/revisar/{sid}/confirmar", data=datos)
        return json.loads((self.lote / "revision" / "etiquetas" / "BOE-A-1.json").read_text(encoding="utf-8"))

    def _avaliar(self, etiqueta) -> dict:
        return corpus_metricas.avaliar_documento(etiqueta, self.lote / "docs" / "boe" / "BOE-A-1.pdf")

    def test_persoa_que_faltaba_conta_coma_fuga(self):
        r = self._avaliar(self._etiquetar(anonimizar="TODAS", fragmentos="Fufa"))
        self.assertEqual(r["fugas"], 1)
        self.assertEqual(r["sobre"], 0)
        self.assertEqual(r["persoas_ref"], 2)
        self.assertEqual([d["texto"] for d in r["detalle"]], ["Fufa"])

    def test_todo_correcto_e_perfecto(self):
        resumo = corpus_metricas.resumir([self._avaliar(self._etiquetar(anonimizar="TODAS"))])
        self.assertEqual(resumo["fugas"], 0)
        self.assertEqual(resumo["sobreanonimizacions"], 0)
        self.assertEqual(resumo["documentos_perfectos"]["n"], 1)
        self.assertEqual(resumo["precision"]["valor"], 1.0)

    def test_persoa_desmarcada_conta_coma_sobreanonimizacion(self):
        r = self._avaliar(self._etiquetar())  # ningunha marcada coma persoa
        self.assertGreater(r["sobre"], 0)
        self.assertEqual(r["persoas_ref"], 0)

    def test_texto_cambiado_non_se_compara(self):
        etiqueta = self._etiquetar(anonimizar="TODAS")
        etiqueta["sha256_texto"] = "0" * 64
        self.assertIn("erro", self._avaliar(etiqueta))

    def test_wilson(self):
        baixo, alto = corpus_metricas.wilson(59, 60)
        self.assertAlmostEqual(baixo, 0.911, places=2)
        self.assertLessEqual(alto, 1.0)
        self.assertLess(baixo, 59 / 60)


if __name__ == "__main__":
    unittest.main()
