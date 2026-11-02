"""Pantalla de escritorio do conversor (`pantalla_conversor.py`, fase 2b).

A clase `Api` chámase directamente, coma a chamaría a páxina por
`js_api`: os eventos que irían á páxina (`evaluate_js`) recóllense nunha
lista. Ao final, unha proba abre a xanela de verdade (oculta) e comproba
que o proceso non ten ningún porto aberto.

Todos os nomes e DNI son sintéticos.
"""

import os

os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")

import json
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import docx

_RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_RAIZ / "src"))

from anonimizador import aforro_ia, conversor, idioma, pantalla_conversor

_NOME = "Xoán Pérez Vázquez"
_DNI = "30014811Z"


def _docx(ruta: Path, texto: str = f"Comparece don {_NOME}, con DNI {_DNI}, ante o xulgado de Lugo.") -> Path:
    documento = docx.Document()
    documento.add_heading("Demanda", 1)
    documento.add_paragraph(texto)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    documento.save(str(ruta))
    return ruta


class _Base(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self._cwd = os.getcwd()
        os.chdir(self.dir)  # preferencias.json vai no cartafol de traballo
        self.eventos = []
        self.chegou = threading.Condition()
        self.api = pantalla_conversor.Api(emitir=self._emitir, rexistro_dir=str(self.dir / "rexistro"),
                                          usar_chaveiro=False)

    def tearDown(self):
        if self.api._fio is not None:
            self.api.cancelar()
            self.api._fio.join(30)
        os.chdir(self._cwd)
        shutil.rmtree(self.dir, ignore_errors=True)

    def _emitir(self, evento, datos):
        json.dumps(datos)  # o que vai á páxina ten que ser JSON
        with self.chegou:
            self.eventos.append((evento, datos))
            self.chegou.notify_all()

    def _agardar(self, evento, desde=0):
        """Datos do primeiro `evento` a partir da posición `desde`."""
        with self.chegou:
            ok = self.chegou.wait_for(
                lambda: any(e == evento for e, _ in self.eventos[desde:]), timeout=120)
        self.assertTrue(ok, f"non chegou «{evento}»: {[e for e, _ in self.eventos]}")
        return next(d for e, d in self.eventos[desde:] if e == evento)

    def _final(self):
        self.api._fio.join(120)
        self.assertFalse(self.api._fio.is_alive())
        return self.eventos[-1]


class TestPreferencias(_Base):
    def test_revision_por_defecto_e_automatico_gardado(self):
        self.assertEqual(self.api.estado_inicial()["modo_anonimizado"], "revisar")
        self.assertEqual(self.api.gardar_modo_anonimizado("automatico"), {"modo_anonimizado": "automatico"})
        self.assertEqual(json.loads((self.dir / "preferencias.json").read_text())["conversor_modo_anonimizado"],
                         "automatico")
        self.assertEqual(pantalla_conversor.Api().estado_inicial()["modo_anonimizado"], "automatico")
        self.assertIn("erro", self.api.gardar_modo_anonimizado("outro"))

    def test_rexistro_compartido_por_defecto(self):
        self.assertEqual(pantalla_conversor.Api().estado_inicial()["rexistro"], str(conversor.rexistro_por_defecto()))

    def test_cambiar_idioma_devolve_os_textos(self):
        self.api._xanela = mock.Mock()
        resposta = self.api.cambiar_idioma("es")
        self.assertEqual(resposta["textos"]["converter_anon"], "Convertir anonimizando")
        self.assertEqual(resposta["textos"]["titulo"], "Conversor de archivos para IA")
        self.api._xanela.set_title.assert_called_once_with("Conversor de archivos para IA")
        self.assertEqual(resposta["textos"]["revisar.persoas_titulo"], idioma.t("revisar.persoas_titulo", "es"))
        self.assertEqual(json.loads((self.dir / "preferencias.json").read_text())["idioma"], "es")


class TestHtml(_Base):
    def test_textos_dentro_e_nada_de_fora(self):
        html = pantalla_conversor.html()
        self.assertNotIn("__TEXTOS__", html)
        self.assertIn('"converter_anon": "Converter anonimizando"', html)
        self.assertIn("default-src 'none'", html)  # a páxina non pode pedir nada a ningures
        for externo in ('src="http', "src='http", 'href="http', "<link"):
            self.assertNotIn(externo, html)

    def test_mesmas_claves_en_galego_e_castelan(self):
        self.assertEqual(set(pantalla_conversor.textos_da_pantalla("gl")),
                         set(pantalla_conversor.textos_da_pantalla("es")))


class TestAcercaEManual(_Base):
    """Coma o anonimizador: versión, dobre licenza, autoría, código fonte e
    manual (requisitos xerais da Store)."""

    def test_acerca_con_version_licenzas_e_codigo(self):
        from anonimizador import web

        datos = self.api.acerca()
        self.assertEqual(datos["version"], conversor.VERSION)
        self.assertIn("GNU AFFERO GENERAL PUBLIC LICENSE", datos["licenza"])
        self.assertIn("v. 1.2", datos["licenza_eupl"])
        self.assertEqual(datos["url_codigo"], web._URL_CODIGO)
        textos = pantalla_conversor.textos_da_pantalla("gl")
        self.assertIn("EUPL-1.2 OR AGPL-3.0-only", textos["acerca.licenza"])
        self.assertIn("Anthropic", textos["acerca.ia"])
        self.assertIn('id="ligazon-acerca"', pantalla_conversor.html())

    def test_o_manual_esta_no_repositorio_nos_dous_idiomas(self):
        for nome in pantalla_conversor.MANUAL.values():
            self.assertTrue((_RAIZ / "docs" / nome).is_file(), nome)

    def test_abrir_codigo_so_abre_o_repositorio(self):
        with mock.patch.object(pantalla_conversor, "_abrir_fora") as abrir:
            self.assertEqual(self.api.abrir_codigo(), {"ok": True})
        abrir.assert_called_once_with(pantalla_conversor.URL_CODIGO)

    def test_manual_no_idioma_escollido_ou_aviso_se_non_esta(self):
        raiz = self.dir / "paquete" / "anonimizador-xuridico"
        with mock.patch.object(pantalla_conversor, "_RAIZ_CODIGO", raiz), \
                mock.patch.object(pantalla_conversor, "_abrir_fora") as abrir:
            self.assertFalse(self.api.estado_inicial()["hai_manual"])
            self.assertIn("erro", self.api.abrir_manual())
            for nome in pantalla_conversor.MANUAL.values():
                (raiz.parent / "docs" / nome).parent.mkdir(parents=True, exist_ok=True)
                (raiz.parent / "docs" / nome).write_bytes(b"%PDF")
            self.assertTrue(self.api.estado_inicial()["hai_manual"])
            for lingua in ("es", "gl"):
                with mock.patch.dict(os.environ, {"ANONIMIZADOR_IDIOMA": lingua}):
                    self.assertEqual(self.api.abrir_manual(), {"ok": True})
        es, gl = (Path(c.args[0]) for c in abrir.call_args_list)
        self.assertEqual((es.parent.name, gl.parent.name), ("es", "docs"))


class TestEntradas(_Base):
    def test_describir_rutas(self):
        ficheiro = _docx(self.dir / "a.docx")
        (self.dir / "x.zip").write_bytes(b"PK")
        descritas = self.api.describir_rutas([str(ficheiro), str(self.dir), str(self.dir / "x.zip"), "/non/existe"])
        self.assertEqual([d["tipo"] for d in descritas], ["ficheiro", "cartafol", "zip"])

    def test_soltar_usa_a_ruta_completa_de_pywebview(self):
        ficheiro = _docx(self.dir / "a.docx")
        self.api._ao_soltar({"dataTransfer": {"files": [{"name": "a.docx", "pywebviewFullPath": str(ficheiro)},
                                                         {"name": "sen_ruta.txt"}]}})
        self.assertEqual(self.eventos, [("soltadas", [{"ruta": str(ficheiro), "nome": "a.docx", "tipo": "ficheiro"}])])

    def test_erros_de_validacion(self):
        self.assertIn("erro", self.api.converter({"rutas": []}))
        self.assertIn("erro", self.api.converter({"rutas": [str(self.dir / "non.docx")]}))
        ficheiro = _docx(self.dir / "a.docx")
        self.assertIn("erro", self.api.converter({"rutas": [str(ficheiro)], "trocear": 5}))
        self.assertIsNone(self.api._fio)

    def test_abrir_carpeta(self):
        ficheiro = _docx(self.dir / "a.docx")
        with mock.patch.object(pantalla_conversor, "_abrir_no_sistema") as abrir:
            self.assertEqual(self.api.abrir_carpeta(str(ficheiro)), {"ok": True})
        abrir.assert_called_once_with(self.dir)
        self.assertIn("erro", self.api.abrir_carpeta(str(self.dir / "non" / "x.md")))


class TestSenAnonimizar(_Base):
    def test_progreso_resultado_tokens_e_aviso(self):
        raiz = self.dir / "expediente"
        _docx(raiz / "a.docx")
        _docx(raiz / "b.docx")
        (raiz / "plano.dwg").write_bytes(b"\x00")
        saida = self.dir / "saida"
        self.assertEqual(self.api.converter({"rutas": [str(raiz)], "anonimizar": False, "saida": str(saida)}),
                         {"ok": True})
        evento, datos = self._final()
        self.assertEqual(evento, "rematado")
        progreso = [d for e, d in self.eventos if e == "progreso"]
        self.assertEqual([(p["feito"], p["total"]) for p in progreso], [(0, 2), (1, 2), (2, 2)])
        self.assertEqual(sorted(Path(s).name for s in datos["saidas"]), ["a.docx.md", "b.docx.md"])
        self.assertEqual(datos["cartafoles"], [str(saida)])
        self.assertFalse(datos["anonimizado"])
        self.assertIn("tokens", datos["tokens"])
        self.assertEqual([o["nome"] for o in datos["omitidos"]], ["plano.dwg"])
        self.assertIn(_NOME, Path(datos["saidas"][0]).read_text(encoding="utf-8"))

    def test_opcions_un_so_md_sen_aforro_e_trocear(self):
        raiz = self.dir / "expediente"
        _docx(raiz / "a.docx", "Texto longo. " * 400)
        _docx(raiz / "b.docx")
        with mock.patch.object(conversor, "converter", wraps=conversor.converter) as espia:
            self.api.converter({"rutas": [str(raiz)], "un_so_md": True, "aforro": False, "trocear": 500})
            self._final()
        kwargs = espia.call_args.kwargs
        self.assertTrue(kwargs["un_so_md"])
        self.assertFalse(kwargs["aforro"])
        self.assertEqual(kwargs["caracteres_por_parte"], round(500 * aforro_ia.CARACTERES_POR_TOKEN))
        self.assertIn("expediente.indice.md", [Path(s).name for s in self.eventos[-1][1]["saidas"]])

    def test_varias_entradas_soltas(self):
        a = _docx(self.dir / "a.docx")
        b = _docx(self.dir / "b.docx")
        self.api.converter({"rutas": [str(a), str(b)]})
        evento, datos = self._final()
        self.assertEqual(len(datos["saidas"]), 2)
        self.assertEqual({p["entrada"] for e, p in self.eventos if e == "progreso"}, {0, 1})

    def test_cancelar_antes_de_empezar_un_documento(self):
        raiz = self.dir / "expediente"
        for nome in "abc":
            _docx(raiz / f"{nome}.docx")
        orixinal = conversor.converter

        def converter_lento(*args, progreso=None, **kwargs):
            def progreso_e_cancelar(feito, total, nome):
                progreso(feito, total, nome)
                if feito == 1:
                    self.api.cancelar()
            return orixinal(*args, progreso=progreso_e_cancelar, **kwargs)

        with mock.patch.object(conversor, "converter", converter_lento):
            self.api.converter({"rutas": [str(raiz)]})
            evento, datos = self._final()
        self.assertEqual(evento, "cancelado")
        self.assertEqual(datos["saidas"], [])
        self.assertEqual(sorted(p.name for p in raiz.iterdir()), ["a.docx", "b.docx", "c.docx"])

    def test_non_arrinca_dúas_veces(self):
        ficheiro = _docx(self.dir / "a.docx")
        self.api._fio = mock.Mock(is_alive=lambda: True)
        self.assertIn("erro", self.api.converter({"rutas": [str(ficheiro)]}))
        self.api._fio = None


class TestAnonimizando(_Base):
    def _md(self, datos):
        self.assertEqual(len(datos["saidas"]), 1)
        return Path(datos["saidas"][0]).read_text(encoding="utf-8")

    def test_revision_por_defecto_decisions_e_revisado_si(self):
        ficheiro = _docx(self.dir / "demanda.docx")
        self.api.converter({"rutas": [str(ficheiro)], "anonimizar": True})
        revision = self._agardar("revisar")
        self.assertEqual(revision["nome"], "demanda.docx")
        self.assertEqual(revision["motivo"], "revisar")
        codigos = [p["codigo"] for p in revision["persoas"]]
        self.assertTrue(codigos)
        self.assertNotIn(_NOME, revision["vista_previa"])
        self.api.confirmar_revision({"anonimizar": codigos, "fragmentos": "Lugo => [LUGAR]\nnon está aquí"})
        evento, datos = self._final()
        self.assertEqual(evento, "rematado")
        md = self._md(datos)
        self.assertIn("revisado: si\n", md)
        self.assertIn("xulgado de [LUGAR]", md)
        for dato in ("Xoán", "Pérez", _DNI):
            self.assertNotIn(dato, md)
        self.assertTrue(datos["documentos"][0]["revisado"])
        self.assertFalse(datos["automatico"])
        self.assertIn("non está aquí", " ".join(datos["avisos"][0]["avisos"]))

    def test_desmarcar_deixa_a_vista(self):
        """Desmarcar unha persoa ("non é persoa") quítaa do .md, coma en `web.confirmar`."""
        ficheiro = _docx(self.dir / "demanda.docx", f"Asina {_NOME} en Lugo.")
        self.api.converter({"rutas": [str(ficheiro)], "anonimizar": True, "modo": "revisar"})
        self._agardar("revisar")
        self.api.confirmar_revision({"anonimizar": [], "fragmentos": ""})
        _, datos = self._final()
        self.assertIn(f"Asina {_NOME} en Lugo.", self._md(datos))

    def test_cancelar_na_revision_non_escribe(self):
        ficheiro = _docx(self.dir / "demanda.docx")
        self.api.converter({"rutas": [str(ficheiro)], "anonimizar": True})
        self._agardar("revisar")
        self.api.cancelar()
        evento, datos = self._final()
        self.assertEqual(evento, "cancelado")
        self.assertEqual(sorted(p.name for p in self.dir.iterdir() if p.is_file()), ["demanda.docx"])

    def test_cancelar_mentres_se_anonimiza_non_queda_agardando(self):
        from anonimizador import pipeline

        orixinal = pipeline.anonimizar_texto_detallado

        def anonimizar_e_cancelar(*args, **kwargs):
            resultado = orixinal(*args, **kwargs)
            self.api.cancelar()  # a persoa cancela antes de chegar á revisión
            return resultado

        ficheiro = _docx(self.dir / "demanda.docx")
        with mock.patch.object(pipeline, "anonimizar_texto_detallado", anonimizar_e_cancelar):
            self.api.converter({"rutas": [str(ficheiro)], "anonimizar": True})
            self.api._fio.join(60)
        self.assertFalse(self.api._fio.is_alive())
        self.assertEqual(self.eventos[-1][0], "cancelado")
        self.assertNotIn("revisar", [e for e, _ in self.eventos])

    def test_automatico_revisado_non_e_resumo_das_marcadas(self):
        self.api.gardar_modo_anonimizado("automatico")
        ficheiro = _docx(self.dir / "demanda.docx")
        self.api.converter({"rutas": [str(ficheiro)], "anonimizar": True})
        evento, datos = self._final()
        self.assertEqual(evento, "rematado")
        self.assertNotIn("revisar", [e for e, _ in self.eventos])
        self.assertIn("revisado: non\n", self._md(datos))
        self.assertTrue(datos["automatico"])
        documento = datos["documentos"][0]
        self.assertFalse(documento["revisado"])
        self.assertGreaterEqual(documento["persoas"], 1)
        self.assertIn("marcadas", documento)

    def test_automatico_con_risco_alto_pasa_a_revision(self):
        ficheiro = _docx(self.dir / "con_risco.docx", "Comparece don Xoán Páez Veiga. Referencia 34867809 do expediente.")
        self.api.converter({"rutas": [str(ficheiro)], "anonimizar": True, "modo": "automatico"})
        revision = self._agardar("revisar")
        self.assertEqual(revision["motivo"], "fugas")
        self.assertIn("34867809", [f["texto"] for f in revision["fugas"]])
        self.api.confirmar_revision({"anonimizar": [p["codigo"] for p in revision["persoas"]],
                                     "fragmentos": "34867809 => [NÚMERO]"})
        _, datos = self._final()
        md = self._md(datos)
        self.assertIn("revisado: si\n", md)
        self.assertNotIn("34867809", md)


class TestXanelaSenServidor(unittest.TestCase):
    def test_carga_o_html_directamente_sen_servidor(self):
        """`html=` (nunca unha URL nin un ficheiro local) e `http_server=False`:
        con iso pywebview non arrinca o seu servidor HTTP."""
        import webview.util

        with mock.patch("webview.create_window") as crear, mock.patch("webview.start") as arrincar:
            pantalla_conversor.executar(rexistro_dir="/tmp/rexistro")
        args, kwargs = crear.call_args
        self.assertEqual(args[1:], ())
        self.assertNotIn("url", kwargs)
        self.assertIn("<html", kwargs["html"])
        self.assertIsInstance(kwargs["js_api"], pantalla_conversor.Api)
        self.assertFalse(webview.util.is_local_url(kwargs.get("url")))
        self.assertFalse(arrincar.call_args.kwargs["http_server"])


def _portos(pid: int) -> str:
    """Sockets de rede (TCP e UDP, escoitando ou non) do proceso `pid`."""
    return subprocess.run(["lsof", "-nP", "-a", "-p", str(pid), "-i"], capture_output=True, text=True).stdout.strip()


_SCRIPT_XANELA = r"""
import os, subprocess, sys, time
sys.path.insert(0, sys.argv[1])
import webview
from anonimizador import pantalla_conversor

orixinal = webview.start

def start(*args, **kwargs):
    def comprobar():
        try:
            xanela = webview.windows[0]
            # `loaded` e a API de Python actívanse xuntos (webview.util); cun equipo en repouso
            # ou ocupado pode pasar do minuto, así que hai marxe e anótase o que tardou.
            inicio = time.monotonic()
            print("CARGADA", xanela.events.loaded.wait(180), flush=True)
            print(f"TARDOU {time.monotonic() - inicio:.1f} s", flush=True)
            time.sleep(1)
            print("API", xanela.evaluate_js("typeof window.pywebview.api.converter"), flush=True)
            portos = subprocess.run(["lsof", "-nP", "-a", "-p", str(os.getpid()), "-i"],
                                    capture_output=True, text=True).stdout.strip()
            print("PORTOS<<" + portos + ">>", flush=True)
            print("SERVIDOR", webview.http.global_server, flush=True)
        finally:
            os._exit(0)
    kwargs["func"] = comprobar
    return orixinal(*args, **kwargs)

webview.start = start
pantalla_conversor.executar(rexistro_dir=sys.argv[2], usar_chaveiro=False, oculta=True)
"""


@unittest.skipUnless(sys.platform == "darwin" and shutil.which("lsof"),
                     "abre a xanela real: só en Mac (en Windows, netstat na lista de probas da versión)")
class TestSenPortosAbertos(unittest.TestCase):
    def test_a_xanela_real_non_abre_ningun_porto(self):
        # Primeiro, que `lsof` si ve un porto cando o hai (a proba non é baleira).
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            s.listen()
            self.assertIn("LISTEN", _portos(os.getpid()))
        with tempfile.TemporaryDirectory() as tmp:
            proceso = subprocess.run(
                [sys.executable, "-c", _SCRIPT_XANELA, str(_RAIZ / "src"), str(Path(tmp) / "rexistro")],
                capture_output=True, text=True, timeout=300, cwd=tmp,
            )
        saida = proceso.stdout
        self.assertIn("CARGADA True", saida, saida + proceso.stderr[-2000:])
        self.assertIn("API function", saida)
        self.assertIn("PORTOS<<>>", saida)
        self.assertIn("SERVIDOR None", saida)


if __name__ == "__main__":
    unittest.main()
