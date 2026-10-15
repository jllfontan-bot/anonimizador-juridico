"""Revisión humana por DECISIÓNS: o documento de saída xérase sempre a partir
do ORIXINAL e das decisións (quen revisa marca persoa / non persoa, engade o que
faltaba, xeneraliza un dato), nunca a partir dun texto libre editado. Antes,
editar o cadro de texto desaliñaba as liñas e o PDF caía a un .txt."""
import os

# Estas probas escribíronse coa interface e os códigos en galego (PERSOA_...).
os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")
import sys
import tempfile
import unittest
from pathlib import Path

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador import web


def _texto_pdf(ruta) -> str:
    with fitz.open(str(ruta)) as d:
        return "\n".join(p.get_text() for p in d)


class TestRevisionPorDecisions(unittest.TestCase):
    TEXTO = "Comparece don Xoán Páez Veiga ante o xulgado. Vive en Rúa Real, e ten unha cadela chamada Fufa."

    def setUp(self):
        web.SESIONS.clear()
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.rexistro_dir = str(self.dir / "rexistro")
        self.client = web.app.test_client()

    def tearDown(self):
        self._tmp.cleanup()

    def _pdf(self, nome="doc.pdf") -> str:
        ruta = self.dir / nome
        d = fitz.open()
        p = d.new_page()
        p.insert_text((72, 100), "Comparece don Xoán Páez Veiga ante o xulgado.", fontsize=11)
        p.insert_text((72, 130), "Vive en Rúa Real, e ten unha cadela chamada Fufa.", fontsize=11)
        d.save(str(ruta))
        return str(ruta)

    def _txt(self, nome="doc.txt") -> str:
        ruta = self.dir / nome
        ruta.write_text(self.TEXTO, encoding="utf-8")
        return str(ruta)

    def _revisar(self, ruta: str) -> str:
        r = self.client.post("/procesar", data={"ruta": ruta, "rexistro": self.rexistro_dir}, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        return r.request.path.rsplit("/", 1)[-1]

    def _confirmar(self, sid: str, **campos):
        sesion = web.SESIONS[sid]
        datos = {"rexistro_dir": self.rexistro_dir, "texto_final": sesion["texto_anonimizado"]}
        datos.update(campos)
        return self.client.post(f"/revisar/{sid}/confirmar", data=datos)

    # -- o PDF sae sempre --------------------------------------------------

    def test_pdf_non_cae_a_txt_aínda_que_se_edite_o_texto_libre(self):
        sid = self._revisar(self._pdf())
        # Un bloque de páxina de máis: antes isto facía caer o PDF a .txt.
        editado = web.SESIONS[sid]["texto_anonimizado"] + "\n\f\nliña engadida a man"
        resposta = self._confirmar(sid, texto_final=editado)
        saida = web.SESIONS[sid]["ruta_saida"]
        self.assertTrue(saida.endswith(".pdf"), saida)
        self.assertNotIn("Xoán", _texto_pdf(saida))
        self.assertIn("PERSOA_000001", _texto_pdf(saida))
        # as edicións libres non se perden: quedan nun .txt xunto ao PDF
        txt = Path(saida).with_suffix(".edicion-manual.txt")
        self.assertTrue(txt.exists())
        self.assertIn("liña engadida a man", txt.read_text(encoding="utf-8"))
        self.assertIn("edición", resposta.get_data(as_text=True).lower())

    # -- decisións ----------------------------------------------------------

    def test_marcar_non_e_persoa_deixa_o_texto_a_vista_e_o_pdf_sae(self):
        sid = self._revisar(self._pdf())
        self._confirmar(sid, decisions_v2="1")  # ningunha persoa marcada para manter
        saida = web.SESIONS[sid]["ruta_saida"]
        self.assertTrue(saida.endswith(".pdf"))
        self.assertIn("Xoán Páez Veiga", _texto_pdf(saida))
        self.assertNotIn("PERSOA_000001", _texto_pdf(saida))

    def test_manter_a_persoa_marcada_anonimiza_coma_antes(self):
        sid = self._revisar(self._pdf())
        self._confirmar(sid, decisions_v2="1", anonimizar="PERSOA_000001")
        self.assertNotIn("Xoán", _texto_pdf(web.SESIONS[sid]["ruta_saida"]))

    def test_engadir_o_que_faltaba(self):
        sid = self._revisar(self._pdf())
        self._confirmar(sid, decisions_v2="1", anonimizar="PERSOA_000001", fragmentos="Fufa")
        texto = _texto_pdf(web.SESIONS[sid]["ruta_saida"])
        self.assertNotIn("Fufa", texto)
        self.assertNotIn("Xoán", texto)
        self.assertIn("PERSOA_000002", texto)

    def test_xeneralizar_un_dato_con_substituto(self):
        sid = self._revisar(self._pdf())
        self._confirmar(sid, decisions_v2="1", anonimizar="PERSOA_000001", fragmentos="Rúa Real => [ENDEREZO]")
        texto = _texto_pdf(web.SESIONS[sid]["ruta_saida"])
        self.assertNotIn("Rúa Real", texto)
        self.assertIn("[ENDEREZO]", texto)

    def test_txt_tamen_se_xera_das_decisions(self):
        sid = self._revisar(self._txt())
        self._confirmar(sid, decisions_v2="1", anonimizar="PERSOA_000001", fragmentos="Fufa")
        saida = Path(web.SESIONS[sid]["ruta_saida"]).read_text(encoding="utf-8")
        self.assertNotIn("Fufa", saida)
        self.assertNotIn("Xoán", saida)

    def test_a_decision_queda_na_auditoria_do_rexistro(self):
        sid = self._revisar(self._pdf())
        self._confirmar(sid, decisions_v2="1")  # descarta PERSOA_000001
        rexistro = web._abrir_rexistro(self.rexistro_dir)
        accions = [(e["accion"], e["codigo"]) for e in rexistro.ler_auditoria()]
        self.assertIn(("descartada_por_humano", "PERSOA_000001"), accions)

    def test_formulario_antigo_sen_decisions_v2_non_cambia_nada(self):
        sid = self._revisar(self._txt())
        self._confirmar(sid)  # coma antes: so texto_final
        self.assertNotIn("Xoán", Path(web.SESIONS[sid]["ruta_saida"]).read_text(encoding="utf-8"))

    def test_fragmento_que_non_esta_no_documento_avisa(self):
        sid = self._revisar(self._pdf())
        resposta = self._confirmar(sid, decisions_v2="1", anonimizar="PERSOA_000001", fragmentos="Zarzalejo")
        self.assertIn("Non se atopou", resposta.get_data(as_text=True))

    def test_decisions_e_edicion_libre_a_vez_mandan_as_decisions(self):
        sid = self._revisar(self._pdf())
        editado = web.SESIONS[sid]["texto_anonimizado"].replace("Fufa", "o can")
        self._confirmar(sid, decisions_v2="1", anonimizar="PERSOA_000001", fragmentos="Fufa", texto_final=editado)
        saida = web.SESIONS[sid]["ruta_saida"]
        self.assertTrue(saida.endswith(".pdf"))
        self.assertNotIn("Fufa", _texto_pdf(saida))
        self.assertIn("o can", Path(saida).with_suffix(".edicion-manual.txt").read_text(encoding="utf-8"))


class TestSenEdicionLibre(unittest.TestCase):
    """Decisión do usuario (10/10/2026): fóra a edición libre do texto; para
    borrar, "texto =>" (substituto baleiro); vista previa só de lectura."""

    def setUp(self):
        web.SESIONS.clear()
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.rexistro_dir = str(self.dir / "rexistro")
        self.client = web.app.test_client()
        ruta = self.dir / "doc.pdf"
        d = fitz.open()
        p = d.new_page()
        p.insert_text((72, 100), "Comparece don Xoán Páez Veiga ante o xulgado.", fontsize=11)
        p.insert_text((72, 130), "Nota interna: borrar esta liña.", fontsize=11)
        d.save(str(ruta))
        r = self.client.post("/procesar", data={"ruta": str(ruta), "rexistro": self.rexistro_dir},
                             follow_redirects=True)
        self.sid = r.request.path.rsplit("/", 1)[-1]
        self.html = r.get_data(as_text=True)

    def tearDown(self):
        self._tmp.cleanup()

    def test_non_hai_cadro_de_edicion_libre(self):
        self.assertNotIn('name="texto_final"', self.html)
        self.assertNotIn("edición libre", self.html.lower())
        self.assertIn("Vista previa", self.html)

    def test_confirmar_sen_texto_final(self):
        resposta = self.client.post(f"/revisar/{self.sid}/confirmar", data={
            "rexistro_dir": self.rexistro_dir, "decisions_v2": "1", "anonimizar": "PERSOA_000001"})
        self.assertEqual(resposta.status_code, 200)
        self.assertNotIn("Xoán", _texto_pdf(web.SESIONS[self.sid]["ruta_saida"]))

    def test_borrar_cun_substituto_baleiro(self):
        self.client.post(f"/revisar/{self.sid}/confirmar", data={
            "rexistro_dir": self.rexistro_dir, "decisions_v2": "1", "anonimizar": "PERSOA_000001",
            "fragmentos": "Nota interna: borrar esta liña. =>"})
        texto = _texto_pdf(web.SESIONS[self.sid]["ruta_saida"])
        self.assertNotIn("Nota interna", texto)
        self.assertNotIn("Xoán", texto)


if __name__ == "__main__":
    unittest.main()
