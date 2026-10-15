"""Modo corpus (plan interno de revisión do corpus): revisar documentos PÚBLICOS coa pantalla
de decisións e gardar cada decisión coma ETIQUETA (a referencia para medir).
Os documentos son sintéticos."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador import corpus_revision, web


def _pdf(ruta: Path, liñas: list) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    d = fitz.open()
    p = d.new_page()
    for i, liña in enumerate(liñas):
        p.insert_text((72, 100 + 24 * i), liña, fontsize=11)
    d.save(str(ruta))


class TestModoCorpus(unittest.TestCase):
    def setUp(self):
        web.SESIONS.clear()
        self._tmp = tempfile.TemporaryDirectory()
        self.lote = Path(self._tmp.name) / "lote"
        _pdf(self.lote / "docs" / "boe" / "BOE-A-1.pdf", [
            "Comparece don Xoán Páez Veiga ante o xulgado.",
            "Os veciños de Braña presentaron alegacións. A cadela chámase Fufa.",
        ])
        _pdf(self.lote / "docs" / "dog" / "DOG-1.pdf", ["Asina dona Ana Salcedo Roel."])
        (self.lote / "manifesto.json").write_text(json.dumps({"documentos": [
            {"fonte": "BOE", "id": "BOE-A-1", "data": "2025-01-02", "seccion": "3", "titulo": "t",
             "ficheiro": "boe/BOE-A-1.pdf"},
            {"fonte": "DOG", "id": "DOG-1", "data": "2025-01-03", "seccion": "VI. Anuncios", "titulo": "t",
             "ficheiro": "dog/DOG-1.pdf"},
        ]}), encoding="utf-8")
        corpus_revision.activar(self.lote, ["BOE-A-1", "DOG-1"])
        self.client = web.app.test_client()

    def tearDown(self):
        corpus_revision.desactivar()
        # A precarga do seguinte documento corre nun fío e pode estar aínda escribindo a
        # previa: agardar a que remate e borrar sen fallar por iso (non é o que se proba).
        import shutil
        import threading
        import time
        for fio in [f for f in threading.enumerate() if f is not threading.current_thread() and f.daemon]:
            fio.join(timeout=30)
        for _ in range(5):
            shutil.rmtree(self._tmp.name, ignore_errors=True)
            if not Path(self._tmp.name).exists():
                break
            time.sleep(0.5)

    def _abrir(self, doc_id: str) -> str:
        r = self.client.get(f"/corpus/{doc_id}", follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        return r.request.path.rsplit("/", 1)[-1]

    def test_cola_e_faixa_do_modo(self):
        html = self.client.get("/corpus/lista").get_data(as_text=True)
        self.assertIn("MODO CORPUS", html)
        self.assertIn("BOE-A-1", html)
        self.assertIn("0 de 2", html)
        # a páxina de inicio leva á cola
        self.assertIn("/corpus", self.client.get("/").headers.get("Location", ""))

    def test_fluxo_pechado(self):
        """Petición do usuario (piloto): empeza polo primeiro pendente e, ao
        gardar, pasa só ao seguinte; ao rematar, "todos revisados"."""
        r = self.client.get("/corpus")
        self.assertIn("/corpus/BOE-A-1", r.headers.get("Location", ""))
        for doc_id, seguinte in (("BOE-A-1", "/corpus"), ("DOG-1", "/corpus")):
            sid = self._abrir(doc_id)
            sesion = web.SESIONS[sid]
            r = self.client.post(f"/revisar/{sid}/confirmar", data={
                "rexistro_dir": sesion["rexistro_dir"], "decisions_v2": "1",
                "anonimizar": [p["codigo"] for p in sesion["informe"]["persoas"]]})
            self.assertEqual(r.status_code, 302)
            self.assertTrue(r.headers["Location"].endswith(seguinte))
        html = self.client.get("/corpus", follow_redirects=True).get_data(as_text=True)
        self.assertIn("Todos os documentos", html)

    def test_revisar_garda_a_etiqueta(self):
        sid = self._abrir("BOE-A-1")
        sesion = web.SESIONS[sid]
        codigo = sesion["informe"]["persoas"][0]["codigo"]
        self.client.post(f"/revisar/{sid}/confirmar", data={
            "rexistro_dir": sesion["rexistro_dir"], "texto_final": sesion["texto_anonimizado"],
            "decisions_v2": "1", "anonimizar": codigo, "fragmentos": "Fufa",
        })
        etiqueta = json.loads((self.lote / "revision" / "etiquetas" / "BOE-A-1.json").read_text(encoding="utf-8"))
        self.assertTrue(etiqueta["revisado"])
        self.assertEqual(etiqueta["fonte"], "BOE")
        self.assertEqual(len(etiqueta["sha256"]), 64)
        persoa = next(p for p in etiqueta["persoas"] if p["codigo"] == codigo)
        self.assertEqual(persoa["decision"], "persoa")
        self.assertIn("Xoán Páez Veiga", [m["texto"] for m in persoa["mencions"]])
        self.assertEqual([e["texto"] for e in etiqueta["engadidos"]], ["Fufa"])
        self.assertEqual(len(etiqueta["engadidos"][0]["mencions"]), 1)
        self.assertEqual(etiqueta["notas"], "")
        # a cola marca o documento coma revisado
        self.assertIn("1 de 2", self.client.get("/corpus/lista").get_data(as_text=True))

    def test_persoa_descartada_queda_coma_non_persoa(self):
        sid = self._abrir("BOE-A-1")
        sesion = web.SESIONS[sid]
        self.assertIn('name="notas"', self.client.get(f"/revisar/{sid}").get_data(as_text=True))
        self.client.post(f"/revisar/{sid}/confirmar", data={
            "rexistro_dir": sesion["rexistro_dir"], "texto_final": sesion["texto_anonimizado"],
            "decisions_v2": "1", "notas": "os enderezos de organismos non se tapan",
        })
        etiqueta = json.loads((self.lote / "revision" / "etiquetas" / "BOE-A-1.json").read_text(encoding="utf-8"))
        self.assertTrue(etiqueta["persoas"])
        self.assertTrue(all(p["decision"] == "non_persoa" for p in etiqueta["persoas"]))
        self.assertEqual(etiqueta["notas"], "os enderezos de organismos non se tapan")

    def test_rexistro_propio_e_saida_dentro_do_lote(self):
        sid = self._abrir("DOG-1")
        sesion = web.SESIONS[sid]
        self.assertTrue(Path(sesion["rexistro_dir"]).is_relative_to(self.lote / "revision"))
        self.client.post(f"/revisar/{sid}/confirmar", data={
            "rexistro_dir": sesion["rexistro_dir"], "texto_final": sesion["texto_anonimizado"],
            "decisions_v2": "1", "anonimizar": [p["codigo"] for p in sesion["informe"]["persoas"]],
        })
        self.assertTrue(Path(web.SESIONS[sid]["ruta_saida"]).is_relative_to(self.lote / "revision"))
        # o orixinal do corpus non se toca nin aparece un .anonimizado ao seu carón
        self.assertEqual(sorted(p.name for p in (self.lote / "docs" / "dog").iterdir()), ["DOG-1.pdf"])

    def test_pdf_orixinal_e_previa_servense_e_nada_mais(self):
        self._abrir("BOE-A-1")
        self.assertEqual(self.client.get("/corpus/ficheiro/BOE-A-1/orixinal").status_code, 200)
        self.assertEqual(self.client.get("/corpus/ficheiro/BOE-A-1/previa").status_code, 200)
        self.assertEqual(self.client.get("/corpus/ficheiro/BOE-A-1/outro").status_code, 404)
        self.assertEqual(self.client.get("/corpus/ficheiro/NON-EXISTE/orixinal").status_code, 404)

    def test_visor_lado_a_lado_con_imaxes_das_paxinas(self):
        """O navegador integrado non ten visor de PDF (ofrecía gardar o ficheiro):
        as páxinas amósanse coma imaxes, orixinal e anonimizado lado a lado."""
        self._abrir("BOE-A-1")
        html = self.client.get("/corpus/ver/BOE-A-1").get_data(as_text=True)
        self.assertIn("/corpus/paxina/BOE-A-1/orixinal/1.png", html)
        self.assertIn("/corpus/paxina/BOE-A-1/previa/1.png", html)
        r = self.client.get("/corpus/paxina/BOE-A-1/previa/1.png")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, "image/png")
        self.assertEqual(self.client.get("/corpus/paxina/BOE-A-1/previa/9.png").status_code, 404)

    def _sen_esperar_polo_bloqueo(self, pedir) -> None:
        """Executa `pedir()` mentres outro fío ten o bloqueo (coma a precarga
        dun documento longo) e falla se queda esperando por el."""
        import threading
        ocupado, soltar = threading.Event(), threading.Event()

        def precarga_longa():
            with corpus_revision.BLOQUEO:
                ocupado.set()
                soltar.wait(60)

        fio = threading.Thread(target=precarga_longa, daemon=True)
        fio.start()
        ocupado.wait(5)
        pedido = threading.Thread(target=pedir, daemon=True)
        pedido.start()
        pedido.join(60)
        soltar.set()
        fio.join(5)
        self.assertFalse(pedido.is_alive(), "quedou esperando polo bloqueo")

    def test_pantalla_de_revision_non_espera_pola_precarga(self):
        """Ao abrir un DOG de 37 páxinas, a redirección á pantalla de revisión
        agardaba ~2 min máis pola precarga do SEGUINTE (proba do 11/10/2026)."""
        sid = self._abrir("BOE-A-1")
        respostas = {}
        self._sen_esperar_polo_bloqueo(
            lambda: respostas.setdefault("revisar", self.client.get(f"/revisar/{sid}").status_code))
        self.assertEqual(respostas, {"revisar": 200})

    def test_visor_non_espera_polo_procesamento(self):
        """O DOG de 34 páxinas tardaba minutos: as imaxes das páxinas facían cola
        detrás do bloqueo mentres se precargaba o seguinte documento. Agora
        debúxanse noutro proceso (PyMuPDF propio) e non esperan polo bloqueo."""
        self._abrir("BOE-A-1")
        respostas = {}

        def pedir():
            respostas["ver"] = self.client.get("/corpus/ver/BOE-A-1").status_code
            r = self.client.get("/corpus/paxina/BOE-A-1/orixinal/1.png")
            respostas["paxina"] = (r.status_code, r.mimetype)
            respostas["fora"] = self.client.get("/corpus/paxina/BOE-A-1/orixinal/9.png").status_code

        self._sen_esperar_polo_bloqueo(pedir)
        self.assertEqual(respostas, {"ver": 200, "paxina": (200, "image/png"), "fora": 404})
        # as imaxes quedan en disco: a segunda vez non se volven debuxar
        self.assertTrue(list((self.lote / "revision" / "imaxes").rglob("1.png")))

    def test_sen_riscos_de_mosaico_no_modo_corpus(self):
        """Ruído para etiquetar persoas (petición do usuario): no modo corpus non
        se amosan os riscos de efecto mosaico; fóra del, si."""
        sid = self._abrir("BOE-A-1")
        web.SESIONS[sid]["informe"]["riscos_mosaico"] = [
            {"tipo": "idade", "frase": "ten 67 anos", "detalle": "idade exacta"}]
        html = self.client.get(f"/revisar/{sid}").get_data(as_text=True)
        self.assertNotIn("efecto mosaico", html)
        self.assertNotIn("ten 67 anos", html)
        # control: a mesma sesión fóra do modo corpus si os amosa
        web.SESIONS[sid].pop("corpus_id")
        html = self.client.get(f"/revisar/{sid}").get_data(as_text=True)
        self.assertIn("Riscos de efecto mosaico", html)
        self.assertIn("ten 67 anos", html)

    def test_precarga_o_documento_e_reutiliza_a_sesion(self):
        """Lentitude do piloto: o seguinte documento prepárase en segundo plano
        e, ao abrilo, úsase esa sesión xa feita (non se volve anonimizar)."""
        corpus_revision.preparar("DOG-1")
        sid = corpus_revision.MODO["preparadas"]["DOG-1"]
        self.assertIn(sid, web.SESIONS)
        self.assertEqual(self._abrir("DOG-1"), sid)

    def test_procesamento_serializado(self):
        """PyMuPDF non admite varios fíos á vez: no modo corpus todo o
        procesamento pasa por un único bloqueo."""
        self.assertTrue(hasattr(corpus_revision.BLOQUEO, "acquire"))

    def test_revisar_amosa_ligazons_aos_pdf(self):
        sid = self._abrir("BOE-A-1")
        html = self.client.get(f"/revisar/{sid}").get_data(as_text=True)
        self.assertIn("/corpus/ver/BOE-A-1", html)


class TestPropostasDeClaude(unittest.TestCase):
    """Fase 3: Claude deixa propostas; o usuario confírmaas ou cámbiaas; os
    documentos de CONTROL non levan proposta ningunha (control cego)."""

    def setUp(self):
        web.SESIONS.clear()
        self._tmp = tempfile.TemporaryDirectory()
        self.lote = Path(self._tmp.name) / "lote"
        for doc_id in ("BOE-A-1", "BOE-A-2"):
            _pdf(self.lote / "docs" / "boe" / f"{doc_id}.pdf", [
                "Comparece don Xoán Páez Veiga ante o xulgado.",
                "Os veciños de San Clodio presentaron alegacións. A cadela chámase Fufa.",
            ])
        (self.lote / "manifesto.json").write_text(json.dumps({"documentos": [
            {"fonte": "BOE", "id": i, "data": "2025-01-02", "seccion": "3", "titulo": "t",
             "ficheiro": f"boe/{i}.pdf"} for i in ("BOE-A-1", "BOE-A-2")
        ]}), encoding="utf-8")
        for doc_id in ("BOE-A-1", "BOE-A-2"):
            corpus_revision.gardar_proposta(self.lote, doc_id, non_persoas=["San Clodio"], engadidos=["Fufa"])
        corpus_revision.activar(self.lote, ["BOE-A-1", "BOE-A-2"], control=["BOE-A-2"])
        self.client = web.app.test_client()

    def tearDown(self):
        corpus_revision.desactivar()
        self._tmp.cleanup()

    def _abrir(self, doc_id):
        r = self.client.get(f"/corpus/{doc_id}", follow_redirects=True)
        return r.request.path.rsplit("/", 1)[-1], r.get_data(as_text=True)

    def test_a_pantalla_trae_as_propostas(self):
        sid, html = self._abrir("BOE-A-1")
        self.assertIn("proposta de Claude", html)
        self.assertIn(">Fufa</textarea>", html)
        codigos = {p["mencions"][0]: p["codigo"] for p in web.SESIONS[sid]["informe"]["persoas"]}
        if "San Clodio" in codigos:  # se o programa a tapa, a proposta desmárcaa
            self.assertNotIn(f'value="{codigos["San Clodio"]}" checked', html)
        self.assertIn(f'value="{codigos["Xoán Páez Veiga"]}" checked', html)

    def test_documento_de_control_non_trae_propostas(self):
        _, html = self._abrir("BOE-A-2")
        self.assertNotIn("proposta de Claude", html)
        self.assertNotIn(">Fufa</textarea>", html)

    def test_a_etiqueta_rexistra_a_proposta_e_o_control(self):
        sid, _ = self._abrir("BOE-A-1")
        sesion = web.SESIONS[sid]
        self.client.post(f"/revisar/{sid}/confirmar", data={
            "rexistro_dir": sesion["rexistro_dir"], "texto_final": sesion["texto_anonimizado"],
            "decisions_v2": "1", "anonimizar": [p["codigo"] for p in sesion["informe"]["persoas"]],
            "fragmentos": "Fufa",
        })
        etiqueta = json.loads((self.lote / "revision" / "etiquetas" / "BOE-A-1.json").read_text(encoding="utf-8"))
        self.assertFalse(etiqueta["control"])
        self.assertEqual(etiqueta["proposta"]["engadidos"], ["Fufa"])


class TestSenModoCorpus(unittest.TestCase):
    def test_rutas_do_corpus_non_existen_fora_do_modo(self):
        corpus_revision.desactivar()
        client = web.app.test_client()
        self.assertEqual(client.get("/corpus").status_code, 404)
        self.assertNotIn("MODO CORPUS", client.get("/").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
