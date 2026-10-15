"""`medicion/comparar_tapados.py`: comparar o que tapan dúas versións do programa
sobre os documentos NON revisados dun lote (medición sen sesgo). Documentos sintéticos."""
import os

# Estas probas escribíronse coa interface e os códigos en galego (PERSOA_...).
os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import fitz

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "medicion"))

import comparar_tapados  # noqa: E402


def _lote(dir_lote: Path, docs: dict) -> None:
    for doc_id, liña in docs.items():
        ruta = dir_lote / "docs" / "boe" / f"{doc_id}.pdf"
        ruta.parent.mkdir(parents=True, exist_ok=True)
        d = fitz.open()
        d.new_page().insert_text((72, 100), liña, fontsize=11)
        d.save(str(ruta))
    (dir_lote / "manifesto.json").write_text(json.dumps({"documentos": [
        {"fonte": "BOE", "id": i, "ficheiro": f"boe/{i}.pdf"} for i in docs]}), encoding="utf-8")


class TestSeleccion(unittest.TestCase):
    def test_quita_os_documentos_revisados_ou_con_proposta(self):
        with tempfile.TemporaryDirectory() as d:
            lote = Path(d)
            (lote / "manifesto.json").write_text(json.dumps({"documentos": [
                {"id": i, "ficheiro": f"{i}.pdf"} for i in ("C", "A", "B", "D")]}))
            for sub, i in (("etiquetas", "A"), ("propostas", "B")):
                (lote / "revision" / sub).mkdir(parents=True)
                (lote / "revision" / sub / f"{i}.json").write_text("{}")
            self.assertEqual(comparar_tapados.documentos_do_lote(lote), ["C", "D"])
            self.assertEqual(comparar_tapados.documentos_do_lote(lote, incluir_revisados=True), ["A", "B", "C", "D"])
            mostra = comparar_tapados.documentos_do_lote(lote, incluir_revisados=True, n=2, semente=1)
            self.assertEqual(len(mostra), 2)
            self.assertEqual(mostra, comparar_tapados.documentos_do_lote(lote, incluir_revisados=True, n=2, semente=1))
            (lote / "lidos.json").write_text(json.dumps({"semente": 1, "ids": ["C"]}))
            (lote / "lista.json").write_text(json.dumps(["D"]))
            excluir = comparar_tapados.ids_a_excluir(lote / "lidos.json") | comparar_tapados.ids_a_excluir(lote / "lista.json")
            self.assertEqual(comparar_tapados.documentos_do_lote(lote, excluir=excluir), [])
            self.assertEqual(comparar_tapados.documentos_do_lote(lote, incluir_revisados=True, excluir=excluir), ["A", "B"])


class TestComparar(unittest.TestCase):
    def test_conta_repeticions_e_aparta_os_erros(self):
        m = lambda t, tipo="PERSOA": {"texto": t, "tipo": tipo, "contexto": f"... {t} ..."}
        vello = {"D1": [m("Sala"), m("Sala"), m("Sala"), m("Xoán Pérez")], "D2": [m("Ana Rey")], "D3": "ERRO x"}
        novo = {"D1": [m("Sala"), m("Xoán Pérez"), m("Sierra del Toro")], "D2": [m("Ana Rey"), m("Ana Rey", "DNI")],
                "D3": []}
        r = comparar_tapados.comparar(vello, novo)
        self.assertEqual([(d["doc"], d["texto"], d["veces"]) for d in r["destapados"]], [("D1", "Sala", 2)])
        self.assertEqual([(d["doc"], d["texto"], d["tipo"]) for d in r["novos_tapados"]],
                         [("D1", "Sierra del Toro", "PERSOA"), ("D2", "Ana Rey", "DNI")])
        self.assertEqual(list(r["erros"]), ["D3"])
        texto = comparar_tapados.informe(r, ["cabeceira"])
        self.assertIn("DESTAPADOS: 2", texto)
        self.assertIn("NOVOS TAPADOS: 2", texto)


class TestLugaresTapados(unittest.TestCase):
    def test_persoa_que_e_un_lugar_oficial(self):
        m = lambda t, tipo="PERSOA": {"texto": t, "tipo": tipo, "contexto": t}
        datos = {"D1": [m("Lugo"), m("Xoán Páez Veiga"), m("Lugo", "ENDEREZO")], "D2": "ERRO x"}
        atopados = comparar_tapados.persoas_que_son_lugares(datos)
        self.assertEqual([(d["doc"], d["texto"]) for d in atopados], [("D1", "Lugo")])
        self.assertGreater(atopados[0]["apelido_ine"], 0)


class TestCache(unittest.TestCase):
    def test_clave_por_codigo_lote_e_ids_e_nunca_para_un_cartafol(self):
        # Precisa un repo de git con historia (o commit anterior ao último que tocou src/ ou config/).
        pai = subprocess.run(["git", "rev-parse", "--verify", "--quiet", "HEAD~1"], cwd=RAIZ,
                             capture_output=True, text=True)
        if pai.returncode != 0:
            self.skipTest("sen historia de git (copia sen .git ou cun só commit)")
        with tempfile.TemporaryDirectory() as d:
            cache, lote = Path(d) / "cache", Path(d) / "lote"
            self.assertIsNone(comparar_tapados.ficheiro_cache(cache, str(RAIZ), lote, ["A"]))
            a = comparar_tapados.ficheiro_cache(cache, "HEAD", lote, ["A", "B"])
            self.assertEqual(a, comparar_tapados.ficheiro_cache(cache, "HEAD", lote, ["B", "A"]))
            self.assertNotEqual(a, comparar_tapados.ficheiro_cache(cache, "HEAD", lote, ["A"]))
            # o último commit que tocou src/ ou config/ ten o mesmo código ca HEAD: mesma clave
            ultimo = subprocess.run(["git", "log", "-1", "--format=%H", "--", "src", "config"], cwd=RAIZ,
                                    capture_output=True, text=True).stdout.strip()
            self.assertEqual(a, comparar_tapados.ficheiro_cache(cache, ultimo, lote, ["A", "B"]))
            self.assertNotEqual(a, comparar_tapados.ficheiro_cache(cache, ultimo + "~1", lote, ["A", "B"]))
            self.assertEqual(a.parent, cache)


class TestDePuntaAPunta(unittest.TestCase):
    def test_mesma_version_sen_diferenzas_e_o_revisado_non_se_usa(self):
        with tempfile.TemporaryDirectory() as d:
            lote, saida = Path(d) / "lote", Path(d) / "saida"
            _lote(lote, {"BOE-A-1": "Comparece don Xoán Páez Veiga ante o xulgado.",
                         "BOE-A-2": "Asina dona Ana Salcedo Roel."})
            (lote / "revision" / "etiquetas").mkdir(parents=True)
            (lote / "revision" / "etiquetas" / "BOE-A-2.json").write_text("{}")
            r = subprocess.run([sys.executable, str(RAIZ / "medicion" / "comparar_tapados.py"), "--lote", str(lote),
                                "--vello", str(RAIZ), "--novo", str(RAIZ), "--saida", str(saida)],
                               capture_output=True, text=True, timeout=600)
            self.assertEqual(r.returncode, 0, r.stderr)
            vello = json.loads((saida / "vello.json").read_text(encoding="utf-8"))
            self.assertEqual(list(vello), ["BOE-A-1"])
            self.assertIn("Xoán Páez Veiga", [m["texto"] for m in vello["BOE-A-1"]])
            resultado = json.loads((saida / "comparacion.json").read_text(encoding="utf-8"))
            self.assertEqual((resultado["destapados"], resultado["novos_tapados"], resultado["erros"]), ([], [], {}))
            self.assertIn("só os non revisados", (saida / "comparacion.txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
