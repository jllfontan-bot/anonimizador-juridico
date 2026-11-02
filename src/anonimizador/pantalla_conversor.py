"""Pantalla de escritorio do Reductor de tokens (estudo, fase 2b).

SEN servidor local: a diferenza do anonimizador (`desktop.py`, que amosa a
app Flask de `web.py` en 127.0.0.1), aquí pywebview carga o HTML
directamente (`create_window(html=...)`, sen URL nin ficheiro local: con
calquera dos dous pywebview arrincaría o seu servidor HTTP interno) e a
páxina chama á clase `Api` (`js_api`) sen HTTP. O CSS e o JavaScript van
dentro do propio HTML (`templates/conversor.html`) polo mesmo motivo.
`tests/test_pantalla_conversor.py` comproba que o proceso non abre ningún
porto.

O traballo vai nun fío: o progreso chega á páxina con `evaluate_js`
(`recibir(evento, datos)`) e cancelar só marca un `Event` que `converter`
mira antes de cada documento.

Revisión (decisión 12.3 do usuario): anonimizando, por defecto cada
documento pasa pola pantalla de revisión; a persoa pode cambiar a
automático e a escolla gárdase (`preferencias.json`, coma o idioma). En
automático o documento leva `revisado: non` e a pantalla final resume as
persoas marcadas, pero un documento con risco residual alto pasa igual a
revisión. A revisión usa o motor do anonimizador (`pipeline.aplicar_decisions`,
`rexistro.manter_separadas`, `rexistro.descartar_por_humano`), coma
`web.confirmar`: o fío de traballo agarda no enganche `revisar` de
`converter` ata que a páxina chama `confirmar_revision`.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

from . import aforro_ia, conversor, idioma

PREFERENCIA_MODO = "conversor_modo_anonimizado"
MODOS = ("revisar", "automatico")
_PLANTILLA = Path(__file__).resolve().parent / "templates" / "conversor.html"
_VISTA_PREVIA_MAXIMA = 200_000  # caracteres do texto anonimizado na revisión
_RAIZ_CODIGO = Path(__file__).resolve().parents[2]
URL_CODIGO = "https://github.com/jllfontan-bot/anonimizador-juridico"  # o mesmo ca `web._URL_CODIGO`
MANUAL = {"gl": "10-Manual-do-conversor.pdf", "es": "es/10-Manual-del-conversor.pdf"}


def modo_anonimizado() -> str:
    """"revisar" (por defecto) ou "automatico", a escolla gardada."""
    modo = idioma.ler_preferencia(PREFERENCIA_MODO, "revisar")
    return modo if modo in MODOS else "revisar"


def textos_da_pantalla(lingua: str | None = None) -> dict:
    """Os textos da páxina: os seus (`pantalla_conversor.*`) e os da revisión
    do anonimizador (`revisar.*`, `categoria.*`, `mosaico.*`), os mesmos nos
    dous programas."""
    textos = idioma.textos_con_prefixo("pantalla_conversor.", lingua)
    for prefixo in ("revisar.", "categoria.", "mosaico.", "acerca."):
        textos.update({prefixo + c: v for c, v in idioma.textos_con_prefixo(prefixo, lingua).items()})
    textos["titulo"] = idioma.t("conversor.nome", lingua)
    return textos


def html() -> str:
    """A páxina enteira, cos textos dentro (sen pedir nada a ningún servidor)."""
    textos = json.dumps(textos_da_pantalla(), ensure_ascii=False).replace("</", "<\\/")
    return (_PLANTILLA.read_text(encoding="utf-8")
            .replace("__LINGUA__", idioma.actual())
            .replace("__TITULO__", idioma.t("conversor.nome"))
            .replace("__TEXTOS__", textos))


def manual_de_uso() -> Path | None:
    """O PDF do manual do conversor no idioma escollido (no paquete, `docs/`
    vai canda o código; no repositorio, na súa raíz)."""
    for docs in (_RAIZ_CODIGO.parent / "docs", _RAIZ_CODIGO / "docs"):
        pdf = docs / MANUAL["es" if idioma.actual() == "es" else "gl"]
        if pdf.is_file():
            return pdf
    return None


def _ler_licenza(nome: str) -> str | None:
    try:
        return (_RAIZ_CODIGO / nome).read_text(encoding="utf-8")
    except OSError:
        return None


def _abrir_fora(destino: str) -> None:
    """O PDF do manual co visor do sistema ou a ligazón no navegador, fóra da xanela."""
    if sys.platform == "win32" and not destino.startswith("http"):
        os.startfile(destino)  # noqa: S606 -- só o manual propio
    else:
        webbrowser.open(destino if destino.startswith("http") else Path(destino).as_uri())


def _tipo(ruta: Path) -> str:
    if ruta.is_dir():
        return "cartafol"
    return "zip" if ruta.suffix.lower() == ".zip" else "ficheiro"


def _abrir_no_sistema(cartafol: Path) -> None:
    if sys.platform == "win32":
        os.startfile(cartafol)  # noqa: S606 -- un cartafol que existe
    elif sys.platform == "darwin":
        subprocess.run(["open", str(cartafol)], check=False)
    else:
        subprocess.run(["xdg-open", str(cartafol)], check=False)


class Api:
    """O que a páxina pode chamar (`window.pywebview.api.<método>`). pywebview
    só expón os métodos públicos: o estado vai en atributos con `_`.

    `emitir(evento, datos)` substitúe o envío á páxina (tests); sen el, vai
    á xanela con `evaluate_js`."""

    def __init__(self, emitir=None, rexistro_dir: str | None = None, usar_chaveiro: bool = True):
        self._xanela = None
        self._emitir_externo = emitir
        self._rexistro_dir = Path(rexistro_dir) if rexistro_dir else None
        self._usar_chaveiro = usar_chaveiro
        self._fio = None
        self._cancelado = threading.Event()
        self._hai_resposta = threading.Event()
        self._resposta = None
        self._modo = "revisar"
        self._rexistro = None
        self._avisos_revision = {}

    # -- comunicación coa páxina ---------------------------------------------

    def _emitir(self, evento: str, datos) -> None:
        if self._emitir_externo is not None:
            self._emitir_externo(evento, datos)
        elif self._xanela is not None:
            self._xanela.evaluate_js(
                f"recibir({json.dumps(evento)}, {json.dumps(datos, ensure_ascii=False)})")

    def _ao_soltar(self, evento: dict) -> None:
        """Ficheiros ou cartafoles soltos na xanela: pywebview dá a súa ruta
        completa (`pywebviewFullPath`), que o navegador nunca lle dá á páxina."""
        ficheiros = (evento.get("dataTransfer") or {}).get("files") or []
        rutas = [f["pywebviewFullPath"] for f in ficheiros if f.get("pywebviewFullPath")]
        if rutas:
            self._emitir("soltadas", self.describir_rutas(rutas))

    # -- estado e preferencias -------------------------------------------------

    def _cartafol_rexistro(self) -> Path:
        return self._rexistro_dir or conversor.rexistro_por_defecto()

    def estado_inicial(self) -> dict:
        return {"modo_anonimizado": modo_anonimizado(), "lingua": idioma.actual(),
                "rexistro": str(self._cartafol_rexistro()), "hai_manual": manual_de_uso() is not None}

    # -- acerca de e manual ----------------------------------------------------

    def acerca(self) -> dict:
        """Versión, licenzas (dobre: EUPL-1.2 OR AGPL-3.0-only, os dous
        textos) e código fonte, coma o «Acerca de» do anonimizador."""
        return {"version": conversor.VERSION, "licenza": _ler_licenza("LICENSE"),
                "licenza_eupl": _ler_licenza("LICENCIA-EUPL-1.2.txt"), "url_codigo": URL_CODIGO}

    def abrir_codigo(self) -> dict:
        _abrir_fora(URL_CODIGO)
        return {"ok": True}

    def abrir_manual(self) -> dict:
        pdf = manual_de_uso()
        if pdf is None:
            return {"erro": idioma.t("pantalla_conversor.sen_manual")}
        _abrir_fora(str(pdf))
        return {"ok": True}

    def gardar_modo_anonimizado(self, modo: str) -> dict:
        if modo not in MODOS:
            return {"erro": idioma.t("pantalla_conversor.erro_modo")}
        idioma.gardar_preferencia(PREFERENCIA_MODO, modo)
        return {"modo_anonimizado": modo}

    def cambiar_idioma(self, lingua: str) -> dict:
        """Garda o idioma (o mesmo `preferencias.json` có anonimizador) e
        devolve os textos novos: a páxina cámbiaos sen recargarse."""
        try:
            idioma.gardar(lingua)
        except ValueError as e:
            return {"erro": str(e)}
        textos = textos_da_pantalla(lingua)
        if self._xanela is not None:
            self._xanela.set_title(textos["titulo"])
        return {"lingua": lingua, "textos": textos}

    # -- escoller ficheiros ------------------------------------------------------

    def describir_rutas(self, rutas: list) -> list:
        """As entradas que existen, co seu tipo (ficheiro, cartafol ou zip)."""
        descritas = []
        for ruta in rutas or []:
            ruta = Path(str(ruta))
            if ruta.exists():
                descritas.append({"ruta": str(ruta), "nome": ruta.name or str(ruta), "tipo": _tipo(ruta)})
        return descritas

    def escoller_entradas(self, cartafol: bool = False) -> list:
        import webview

        if self._xanela is None:
            return []
        tipo = webview.FileDialog.FOLDER if cartafol else webview.FileDialog.OPEN
        rutas = self._xanela.create_file_dialog(tipo, allow_multiple=not cartafol)
        return self.describir_rutas(list(rutas or []))

    def escoller_saida(self) -> str | None:
        import webview

        if self._xanela is None:
            return None
        rutas = self._xanela.create_file_dialog(webview.FileDialog.FOLDER)
        return str(rutas[0]) if rutas else None

    def abrir_carpeta(self, ruta: str) -> dict:
        ruta = Path(str(ruta))
        cartafol = ruta if ruta.is_dir() else ruta.parent
        if not cartafol.is_dir():
            return {"erro": idioma.t("pantalla_conversor.non_existe", ruta=str(ruta))}
        _abrir_no_sistema(cartafol)
        return {"ok": True}

    # -- conversión --------------------------------------------------------------

    def converter(self, opcions: dict) -> dict:
        """Arrinca a conversión nun fío. `opcions`: `rutas`, `anonimizar`,
        `un_so_md`, `aforro`, `csv_aparte` (por defecto si), `trocear` (tokens por parte ou nada), `saida`
        (cartafol ou nada) e, anonimizando, `modo` ("revisar"/"automatico")."""
        if self._fio is not None and self._fio.is_alive():
            return {"erro": idioma.t("pantalla_conversor.en_marcha")}
        rutas = [str(r) for r in opcions.get("rutas") or []]
        if not rutas:
            return {"erro": idioma.t("pantalla_conversor.sen_entradas")}
        for ruta in rutas:
            if not Path(ruta).exists():
                return {"erro": idioma.t("pantalla_conversor.non_existe", ruta=ruta)}
        trocear = opcions.get("trocear")
        try:
            trocear = int(trocear) if trocear not in (None, "", False) else None
        except (TypeError, ValueError):
            trocear = 0
        if trocear is not None and trocear < 100:
            return {"erro": idioma.t("pantalla_conversor.erro_trocear")}
        modo = opcions.get("modo") or modo_anonimizado()
        if modo not in MODOS:
            return {"erro": idioma.t("pantalla_conversor.erro_modo")}

        self._cancelado.clear()
        self._modo = modo
        self._avisos_revision = {}
        argumentos = {
            "anonimizar": bool(opcions.get("anonimizar")),
            "un_so_md": bool(opcions.get("un_so_md")),
            "saida": (opcions.get("saida") or "").strip() or None,
            "aforro": opcions.get("aforro", True) is not False,
            "csv_aparte": opcions.get("csv_aparte", True) is not False,
            "caracteres_por_parte": round(trocear * aforro_ia.CARACTERES_POR_TOKEN) if trocear else None,
        }
        self._fio = threading.Thread(target=self._traballo, args=(rutas, argumentos), daemon=True)
        self._fio.start()
        return {"ok": True}

    def cancelar(self) -> dict:
        self._cancelado.set()
        self._hai_resposta.set()  # se agarda unha revisión, que deixe de agardar
        return {"ok": True}

    def _traballo(self, rutas: list, argumentos: dict) -> None:
        total = conversor.Resultado()
        anonimizar = argumentos["anonimizar"]
        self._rexistro = None
        try:
            if anonimizar:
                from .registry import RexistroCorrespondencias

                # Coma a CLI e o anonimizador da Store: clave dun rexistro novo no chaveiro.
                self._rexistro = RexistroCorrespondencias(self._cartafol_rexistro(), usar_chaveiro=self._usar_chaveiro)
            for i, ruta in enumerate(rutas):
                def progreso(feito, n, nome, i=i):
                    self._emitir("progreso", {"entrada": i, "entradas": len(rutas), "feito": feito,
                                              "total": n, "nome": nome})

                resultado = conversor.converter(
                    ruta, rexistro=self._rexistro, progreso=progreso, cancelar=self._cancelado.is_set,
                    revisar=self._revisar if anonimizar else None, **argumentos,
                )
                _sumar(total, resultado, prefixo=Path(ruta).name if len(rutas) > 1 else "")
        except conversor.Cancelado:
            self._emitir("cancelado", self._resumo(total, anonimizar))
            return
        except Exception as e:  # noqa: BLE001 -- que a pantalla o diga en vez de quedar parada
            self._emitir("erro", {"mensaxe": idioma.traducir_mensaxe(f"{type(e).__name__}: {e}"),
                                  **self._resumo(total, anonimizar)})
            return
        self._emitir("rematado", self._resumo(total, anonimizar))

    # -- revisión ----------------------------------------------------------------

    def _revisar(self, nome, texto, contexto, texto_anon, informe, substitucions):
        """Enganche `revisar` de `converter`, no fío de traballo."""
        fugas = [r for r in informe.get("risco_residual", []) if r["confianza"] == "alta"]
        if self._modo == "automatico" and not fugas:
            return None
        self._resposta = None
        self._hai_resposta.clear()
        if self._cancelado.is_set():  # cancelado mentres se anonimizaba: o `set` de antes xa se borrou
            raise conversor.Cancelado
        self._emitir("revisar", _datos_revision(nome, texto_anon, informe, "fugas" if self._modo == "automatico" else "revisar"))
        self._hai_resposta.wait()
        if self._cancelado.is_set() or self._resposta is None:
            raise conversor.Cancelado
        return self._aplicar_decisions(nome, texto, contexto, informe, substitucions, self._resposta)

    def confirmar_revision(self, decisions: dict) -> dict:
        """`decisions`: `anonimizar` (os códigos que quedan tapados; os demais
        "non son persoa") e `fragmentos` (o cadro "engadir ou xeneralizar")."""
        self._resposta = {"anonimizar": [str(c) for c in decisions.get("anonimizar") or []],
                          "fragmentos": str(decisions.get("fragmentos") or "")}
        self._hai_resposta.set()
        return {"ok": True}

    def _aplicar_decisions(self, nome, texto, contexto, informe, substitucions, resposta) -> tuple:
        """O mesmo ca `web.confirmar` coas decisións (`decisions_v2`)."""
        from . import pipeline

        rexistro = self._rexistro
        # Un posible homónimo queda sempre coma persoa distinta (decisión do usuario, 15/10/2026).
        for persoa in informe["persoas"]:
            if persoa["marcado_para_revision"]:
                comparacion = ", ".join(persoa.get("posibles_coincidencias") or ["ningunha suxestión"])
                rexistro.manter_separadas(persoa["codigo"], comparacion)
        codigos = {p["codigo"] for p in informe["persoas"]} | {novo for (_, _, novo) in substitucions}
        codigos = {c for c in codigos if idioma.e_codigo_persoa(c)}
        descartados = codigos - set(resposta["anonimizar"])
        fragmentos = pipeline.ler_fragmentos(resposta["fragmentos"])
        texto_final, substitucions, _ = pipeline.aplicar_decisions(
            texto, substitucions, rexistro, descartados, fragmentos, contexto=contexto)
        for codigo in sorted(descartados):
            rexistro.descartar_por_humano(codigo, "marcada coma non persoa na revisión")
        for fragmento, _ in fragmentos:
            if not re.search(r"(?<!\w)" + re.escape(fragmento) + r"(?!\w)", texto):
                self._avisos_revision.setdefault(nome, []).append(
                    idioma.t("web.fragmento_non_atopado", fragmento=fragmento))
        return texto_final, substitucions

    # -- resumo final ------------------------------------------------------------

    def _resumo(self, total: conversor.Resultado, anonimizar: bool) -> dict:
        cartafoles = list(dict.fromkeys(str(Path(s).parent) for s in total.saidas))
        documentos = []
        for nome, informe in total.informes.items():
            marcadas = [p for p in informe["persoas"] if p["marcado_para_revision"]]
            documentos.append({
                "nome": nome,
                "persoas": len(informe["persoas"]),
                "marcadas": [{"codigo": p["codigo"], "mencions": list(dict.fromkeys(p["mencions"])),
                              "motivo": idioma.traducir_mensaxe(p["motivo"] or "")} for p in marcadas],
                "fugas": sum(1 for r in informe.get("risco_residual", []) if r["confianza"] == "alta"),
                "revisado": nome in total.revisados,
            })
        avisos = [{"nome": n, "avisos": a} for n, a in {**total.avisos, **self._avisos_revision}.items()]
        return {
            "anonimizado": anonimizar,
            "automatico": anonimizar and self._modo == "automatico",
            "saidas": total.saidas,
            "cartafoles": cartafoles,
            "tokens": total.resumo_tokens() if total.saidas else "",
            "avisos": avisos,
            "omitidos": [{"nome": n, "motivo": idioma.t("conversor.motivo." + m), "erro": total.erros.get(n, "")}
                         for n, m in total.omitidos],
            "documentos": documentos,
        }


def _sumar(total: conversor.Resultado, resultado: conversor.Resultado, prefixo: str = "") -> None:
    """Xunta o resultado dunha entrada ao de todas (varias entradas soltas)."""
    def nome(n):
        return f"{prefixo}/{n}" if prefixo and n != prefixo else n

    total.saidas += resultado.saidas
    total.omitidos += [(nome(n), m) for n, m in resultado.omitidos]
    total.erros.update({nome(n): e for n, e in resultado.erros.items()})
    total.informes.update(resultado.informes)
    total.avisos.update({nome(n): a for n, a in resultado.avisos.items()})
    total.revisados += resultado.revisados
    total.csv += resultado.csv
    total.tokens_antes += resultado.tokens_antes
    total.tokens_despois += resultado.tokens_despois


def _datos_revision(nome: str, texto_anon: str, informe: dict, motivo: str) -> dict:
    """O que amosa a pantalla de revisión dun documento (coma `revisar.html`)."""
    risco = informe.get("risco_residual", [])
    persoas = sorted(informe["persoas"], key=lambda p: not p["marcado_para_revision"])
    return {
        "nome": nome,
        "motivo": motivo,  # "revisar" (modo revisión) ou "fugas" (automático con risco alto)
        "persoas": [{"codigo": p["codigo"], "mencions": list(dict.fromkeys(p["mencions"])),
                     "marcado": p["marcado_para_revision"],
                     "motivo": idioma.traducir_mensaxe(p["motivo"] or "")} for p in persoas],
        "fugas": [{"tipo": r["tipo"], "texto": r["texto"], "contexto": r["contexto"]}
                  for r in risco if r["confianza"] == "alta"],
        "opcionais": [{"texto": r["texto"], "contexto": r["contexto"]} for r in risco if r["confianza"] == "baixa"],
        "categoria": informe.get("categoria_especial", []),
        "exentos": informe.get("exentos_cargo_publico", []),
        "mosaico": [{"tipo": r["tipo"], "frase": r["frase"], "detalle": idioma.traducir_mensaxe(r["detalle"])}
                    for r in informe.get("riscos_mosaico", [])],
        "vista_previa": texto_anon[:_VISTA_PREVIA_MAXIMA],
    }


# -- xanela ------------------------------------------------------------------------

def _ao_cargar(xanela, api: Api) -> None:
    from webview.dom import DOMEventHandler

    xanela.dom.document.events.drop += DOMEventHandler(api._ao_soltar, prevent_default=True, stop_propagation=True)


def executar(rexistro_dir: str | None = None, usar_chaveiro: bool = True, oculta: bool = False) -> None:
    """Abre a xanela. `html=` e `http_server=False`: pywebview non arrinca o
    seu servidor HTTP (só o fai cunha URL ou un ficheiro local)."""
    import webview

    api = Api(rexistro_dir=rexistro_dir, usar_chaveiro=usar_chaveiro)
    xanela = webview.create_window(idioma.t("conversor.nome"), html=html(), js_api=api,
                                   width=980, height=820, hidden=oculta)
    api._xanela = xanela
    xanela.events.loaded += lambda: _ao_cargar(xanela, api)
    webview.start(http_server=False, private_mode=True)


def main() -> None:
    """Coma o anonimizador da Store: cartafol de traballo `Documentos/Anonimizador`
    (o mesmo `preferencias.json` e o mesmo rexistro)."""
    from .arranque_windows import NOME_CARTAFOL, cartafol_documentos

    datos = cartafol_documentos() / NOME_CARTAFOL
    datos.mkdir(parents=True, exist_ok=True)
    os.chdir(datos)
    executar()


if __name__ == "__main__":
    main()
