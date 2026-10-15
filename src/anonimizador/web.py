"""Interface de revisión humana (informe, sección 06 e Fase 3 do plan).

Aplicación web local (só en 127.0.0.1, nunca exposta á rede) onde un
letrado revisa as substitucións antes de aceptar a versión final:
confirma ou descarta os posibles homónimos que o sistema marcou, revisa
os riscos de efecto mosaico, e pode retocar o texto final antes de
gardalo.

As sesións de revisión viven en memoria (`SESIONS`) mentres o proceso está
en marcha -- é a vía rápida, sen tocar disco en cada clic -- pero tamén se
gardan cifradas en `<rexistro>/sesions.enc` (`registry.gardar_sesion`) para
sobrevivir a un reinicio do servidor sen perder o traballo do letrado. O
que NUNCA se garda en disco é `contexto` (o documento .docx/.odt orixinal
en memoria, aínda sen anonimizar): despois dun reinicio recárgase de novo
desde `ruta_orixe`, que segue intacto no disco ata que se confirma a
revisión.
"""

from __future__ import annotations

import getpass
import os
import re
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, jsonify, make_response, redirect, render_template, request, url_for

from . import corpus_revision, explorador, informe_pdf, ner, selector
from .pipeline import (
    _aplicar_substitucions_a_texto,
    anonimizar_e_gardar_detallado,
    aplicar_decisions,
    anonimizar_texto_detallado,
    cargar_documento_estruturado,
    conserva_formato,
    gardar_documento_estruturado,
    ler_fragmentos,
    listar_ficheiros_soportados,
    ruta_saida_por_defecto,
)
from .registry import RexistroCorrespondencias, substituir_con_reintentos

app = Flask(__name__)
app.register_blueprint(corpus_revision.bp)

SESIONS: dict = {}

# Decidido unha soa vez, ao arrancar o servidor (`executar`), a partir do
# flag `--chaveiro-sistema` do CLI -- non ten sentido que varíe por
# petición web: un rexistro xa creado sabe soamente el mesmo onde está a
# súa clave (ficheiro marcador `clave.chaveiro`), así que isto so afecta a
# rexistros NOVOS que se creen mentres o servidor está en marcha.
USAR_CHAVEIRO_SISTEMA = False


def _abrir_rexistro(rexistro_dir: str) -> RexistroCorrespondencias:
    return RexistroCorrespondencias(rexistro_dir, usar_chaveiro=USAR_CHAVEIRO_SISTEMA)

# Campos da sesion que se poden gardar tal cual en disco (cifrados en
# `sesions.enc`, via `registry.gardar_sesion`): exclue "contexto" a
# propósito -- ver nota no docstring do módulo.
_CAMPOS_PERSISTIBLES = (
    "ruta_orixe", "rexistro_dir", "cartafol_saida", "texto_anonimizado", "informe",
    "substitucions", "n_marcadas", "n_mosaico", "confirmado", "creado", "corpus_id", "corpus_control", "proposta", "corpus_posicion", "corpus_titulo",
    "ruta_saida_fixa",
)


def _sesion_persistible(sesion: dict) -> dict:
    return {k: sesion[k] for k in _CAMPOS_PERSISTIBLES if k in sesion}


def _recargar_contexto(ruta_orixe: str):
    """Reconstrue `contexto` (o documento .docx/.odt en memoria, necesario
    para conservar o formato ao gardar) recargando o ficheiro ORIXINAL, que
    segue intacto no disco mentres a revisión non se confirma. Devolve
    `None` se o ficheiro xa non existe ou non é .docx/.odt."""
    if not Path(ruta_orixe).exists():
        return None
    _, contexto = cargar_documento_estruturado(ruta_orixe)
    return contexto


def _obter_sesion(sid: str, rexistro_dir: str | None = None):
    """Busca a sesión primeiro en memoria (vía rápida, sen tocar disco); se
    non está (ex. o servidor reiniciouse) e se coñece o cartafol do
    rexistro, reconstrúea desde `sesions.enc` recargando ademais `contexto`
    desde o documento orixinal."""
    sesion = SESIONS.get(sid)
    if sesion is not None:
        return sesion

    if not rexistro_dir:
        return None

    rexistro = _abrir_rexistro(rexistro_dir)
    datos = rexistro.ler_sesions_pendentes().get(sid)
    if datos is None:
        return None

    sesion = dict(datos)
    sesion["contexto"] = _recargar_contexto(sesion["ruta_orixe"])
    SESIONS[sid] = sesion
    return sesion


def _pendentes(rexistro_dir: str) -> list:
    """Revisións sen confirmar: as que están en memoria e, se se indica
    un cartafol de rexistro, tamén as gardadas en disco para el (ex. tras
    reiniciar o servidor)."""
    pendentes = {
        sid: {"id": sid, **{k: s[k] for k in ("ruta_orixe", "n_marcadas", "n_mosaico")}}
        for sid, s in SESIONS.items() if not s["confirmado"]
    }
    # SÓ se o cartafol xa existe: abrilo CREA o rexistro (e a súa clave), así
    # que abrilo aquí convertía calquera erro de escritura na ruta -- ou o
    # simple feito de cargar a páxina de inicio -- nun rexistro baleiro novo
    # con clave propia, espallados polo disco. E se a clave está no chaveiro
    # e xa non se atopa (reinstalación do sistema, outro usuario), abrilo
    # lanza RuntimeError: antes iso deixaba a páxina de inicio nun erro 500,
    # sen explicar nada; agora a páxina cárgase e o aviso da clave explícao.
    if rexistro_dir and Path(rexistro_dir).exists():
        try:
            rexistro = _abrir_rexistro(rexistro_dir)
        except (RuntimeError, OSError, ValueError):
            return list(pendentes.values())
        for sid, datos in rexistro.ler_sesions_pendentes().items():
            if not datos["confirmado"] and sid not in pendentes:
                pendentes[sid] = {
                    "id": sid,
                    **{k: datos[k] for k in ("ruta_orixe", "n_marcadas", "n_mosaico")},
                }
    return list(pendentes.values())


# A27 (revisión 21/09/2026): protección lixeira contra peticións doutras
# orixes, sen depender de ningunha libraría nova. Dous límites diferentes:
#   - Host non permitido: a app só escoita en 127.0.0.1, pero un dominio
#     público podería resolver TEMPORALMENTE a 127.0.0.1 (DNS rebinding)
#     e facer que o navegador trate esa páxina coma se fose a app local
#     -- comprobar o nome do host recibido pecha esa vía.
#   - CSRF: unha web maliciosa aberta no MESMO navegador podería enviar
#     un POST directamente a esta app (`fetch`/formulario cara a
#     `http://127.0.0.1:<porto>/...`) sen que o usuario o note -- p.ex.
#     definir a contrasinal de reversión antes de que o faga o usuario
#     lexítimo. Un navegador manda `Origin` (case xeral) ou polo menos
#     `Referer` en calquera POST cross-site; se ningunha das dúas
#     coincide coa propia orixe, recházase. Cando NON se manda ningunha
#     das dúas (petición feita por un script local, non por un
#     navegador) déixase pasar -- é unha barreira BLANDA, non un token
#     CSRF completo, coherente co resto do proxecto (ver tamén a
#     ventá de permiso de CENDOJ no conector boe-consolidada-mcp).
_HOSTS_PERMITIDOS = {"127.0.0.1", "localhost"}


def _orixe_e_de_confianza(cabeceira: str | None, host_propio: str) -> bool:
    """`cabeceira` (Origin ou Referer) é de confianza se falta (petición
    non feita por un navegador cross-site) ou se o seu hostname coincide
    co propio (`host_propio`, xa comprobado antes en `_HOSTS_PERMITIDOS`
    -- non se compara o porto, só o hostname, para non depender de coma
    o exprese cada navegador/cliente de proba)."""
    if not cabeceira:
        return True
    try:
        compoñentes = urlsplit(cabeceira)
    except ValueError:
        return False
    if not compoñentes.netloc:
        # Referer relativo (raro, pero posible con certas configuracións
        # de navegador): non hai orixe allea que comprobar.
        return True
    return compoñentes.hostname == host_propio.split(":")[0]


@app.before_request
def _protexer_contra_csrf_e_rebinding():
    host = request.host.split(":")[0]
    if host not in _HOSTS_PERMITIDOS:
        return "Host non permitido", 400

    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        if not _orixe_e_de_confianza(request.headers.get("Origin"), request.host):
            return "Orixe non permitida", 403
        if not request.headers.get("Origin") and not _orixe_e_de_confianza(
            request.headers.get("Referer"), request.host
        ):
            return "Orixe non permitida", 403


_REXISTRO_POR_DEFECTO = "./datos_rexistro"


def _estado_da_clave(rexistro_dir: str) -> dict:
    """Onde está (ou onde quedará) a clave que cifra o rexistro, SEN abrir
    nin crear nada -- só mirando que ficheiros hai no cartafol.

    O usuario avisou (27/09/2026) de que ao instalar de novo non se lle di
    en ningún momento que existe esa clave nin onde queda; sen ela o
    rexistro cifrado non se pode descifrar NUNCA MÁIS, así que ten que
    saber que hai que facerlle unha copia de seguridade. Nos manuais si
    estaba, pero non no propio programa.

    Non se abre o rexistro a propósito: abrilo crearíao (co que un simple
    erro de escritura no cartafol deixaría rexistros baleiros por aí) e,
    se a clave vive no chaveiro, macOS podería pedir confirmación só por
    cargar a páxina de inicio."""
    cartafol = Path(rexistro_dir or _REXISTRO_POR_DEFECTO)
    estado = {"cartafol": str(cartafol), "onde": None, "existe": False, "ruta_clave": None}
    if not cartafol.exists():
        estado["onde"] = "aínda_non_creado"
        return estado
    estado["existe"] = (cartafol / "rexistro.enc").exists()
    if (cartafol / "clave.key").exists():
        estado["onde"] = "ficheiro"
        estado["ruta_clave"] = str((cartafol / "clave.key").resolve())
    elif (cartafol / "clave.chaveiro").exists():
        estado["onde"] = "chaveiro"
    elif estado["existe"]:
        estado["onde"] = "descoñecido"
    else:
        estado["onde"] = "aínda_non_creado"
    return estado


def _render_index(**kwargs):
    """Renderiza a páxina de inicio enchendo SEMPRE os datos comúns.

    `index.html` amósase tamén dende as rutas de erro (`/procesar`,
    `/traballo/<id>/resultado`...): se cada unha ten que lembrar pasar o
    aviso da clave e o do modelo, tarde ou cedo unha esquécese e a páxina
    peta cun 500 (pasou xa ao engadir o aviso da clave o 27/09/2026).
    Todo o que sexa común pásase aquí unha soa vez."""
    rexistro_dir = kwargs.get("rexistro_dir", "")
    kwargs.setdefault("pendentes", [])
    kwargs.setdefault("clave", _estado_da_clave(rexistro_dir))
    kwargs.setdefault("aviso_modelo", ner.aviso_compatibilidade_modelo())
    return render_template("index.html", **kwargs)


@app.before_request
def _serializar_no_modo_corpus():
    # O que non usa PyMuPDF neste proceso non espera pola precarga do seguinte
    # documento, que ten o bloqueo minutos nun doc longo: o visor de páxinas
    # (corpus_imaxes) e a pantalla de revisión dunha sesión xa en memoria (sen
    # isto, ao abrir un DOG de 37 páxinas agardábase ~2 min máis). Unha sesión
    # que hai que reconstruír desde disco le o PDF: esa si pasa polo bloqueo.
    if corpus_revision.MODO is None or request.endpoint in corpus_revision.SEN_BLOQUEO:
        return
    if request.endpoint == "revisar" and (request.view_args or {}).get("sid") in SESIONS:
        return
    corpus_revision.BLOQUEO.acquire()
    request.environ["anonimizador.bloqueo_corpus"] = True


@app.teardown_request
def _liberar_no_modo_corpus(_erro=None):
    if request.environ.pop("anonimizador.bloqueo_corpus", False):
        corpus_revision.BLOQUEO.release()


@app.context_processor
def _modo_corpus_nas_plantillas():
    return {"modo_corpus": corpus_revision.MODO is not None}


@app.route("/")
def index():
    if corpus_revision.MODO is not None:
        return redirect(url_for("corpus.cola"))
    rexistro_dir = request.args.get("rexistro", "").strip()
    pendentes = _pendentes(rexistro_dir)

    n_creados = request.args.get("creados", type=int)
    omitidos = request.args.get("omitidos", type=int)
    aviso_cartafol = None
    if n_creados is not None:
        aviso_cartafol = f"{n_creados} documento(s) procesado(s), pendentes de revisión abaixo."
        if omitidos:
            aviso_cartafol += f" {omitidos} ficheiro(s) omitido(s) (formato non soportado ou resultados dunha pasada anterior, .anonimizado)."

    return _render_index(
        pendentes=pendentes, rexistro_dir=rexistro_dir,
        aviso_cartafol=aviso_cartafol,
        clave=_estado_da_clave(rexistro_dir),
        aviso_modelo=ner.aviso_compatibilidade_modelo(),
    )


@app.route("/escoller")
def escoller():
    """Abre o diálogo NATIVO do sistema operativo para escoller un
    ficheiro ou un cartafol (informe: "poder seleccionar carpeta dentro de
    finder"). `tipo` é "ficheiro" ou "cartafol"."""
    tipo = request.args.get("tipo", "ficheiro")
    ruta = selector.escoller(tipo if tipo == "cartafol" else "ficheiro")
    return jsonify({"ruta": ruta})


@app.route("/explorar")
def explorar():
    """Contido dun cartafol para o explorador da interface (cartafoles E
    ficheiros -- estes só informativos; ver `explorador.py`)."""
    return jsonify(explorador.listar(request.args.get("ruta", "").strip() or None))


@app.route("/explorar/nova-carpeta", methods=["POST"])
def explorar_nova_carpeta():
    try:
        ruta = explorador.crear_cartafol(
            request.form.get("pai", "").strip(), request.form.get("nome", "")
        )
    except ValueError as e:
        return jsonify({"erro": str(e)}), 400
    return jsonify({"ruta": ruta})


def _crear_sesion(ruta: str, rexistro_dir: str, cartafol_saida: str | None, rexistro) -> str:
    """Crea e persiste unha sesión de revisión para UN documento. Reutilizado
    tanto para un ficheiro solto coma para cada ficheiro atopado dentro dun
    cartafol (informe: "que anonimice todos os arquivos do cartafol" --
    mantendo unha revisión humana propia por documento, nunca en bloque)."""
    texto, contexto = cargar_documento_estruturado(ruta)
    texto_anonimizado, informe, substitucions = anonimizar_texto_detallado(texto, rexistro, contexto=contexto)

    sid = uuid.uuid4().hex[:12]
    sesion = {
        "ruta_orixe": ruta,
        "rexistro_dir": rexistro_dir,
        "cartafol_saida": cartafol_saida,
        "texto_anonimizado": texto_anonimizado,
        "informe": informe,
        "contexto": contexto,  # None, ou docx/odt en memoria para conservar formato
        "substitucions": substitucions,  # para conservar formato por tramos ao gardar
        "n_marcadas": sum(1 for p in informe["persoas"] if p["marcado_para_revision"]),
        "n_mosaico": len(informe["riscos_mosaico"]),
        "confirmado": False,
        "creado": datetime.now(timezone.utc).isoformat(),
    }
    SESIONS[sid] = sesion
    rexistro.gardar_sesion(sid, _sesion_persistible(sesion))
    return sid


def _procesar_automatico(ruta: str, cartafol_saida: str | None, rexistro) -> dict:
    """Anonimiza e garda UN documento sen crear sesión de revisión --
    modo "automático" (informe: preguntar ao usuario se quere comprobar
    o proceso ou anonimización automática). Aplica sempre a decisión MÁIS
    SEGURA por defecto: `RexistroCorrespondencias.resolver_ou_crear` xa
    NUNCA fusiona un posible homónimo por conta propia (esixe confirmación
    explícita dun humano, vía `/revisar/<sid>/confirmar`) -- así que sen
    revisión un posible homónimo simplemente recibe un código novo, coma
    se un letrado tivese decidido "manter separadas". Devolve un resumo
    para amosar ao usuario, coa mesma información ca unha sesión de
    revisión (`n_marcadas`, `n_mosaico`).

    O nome de ficheiro anonimízase só DESPOIS de procesar o contido -- se
    se fixese antes, unha persoa mencionada tanto no nome coma no
    contido (con DNI) podería acabar con DOUS códigos distintos, xa que
    o rexistro aínda non coñecería a asociación DNI<->código ao mirar o
    nome de ficheiro en primeiro lugar (bug real atopado escribindo este
    mesmo arranxo)."""
    ruta_saida_provisional = ruta_saida_por_defecto(ruta, cartafol_saida)
    Path(ruta_saida_provisional).parent.mkdir(parents=True, exist_ok=True)
    texto_anonimizado, informe, substitucions = anonimizar_e_gardar_detallado(ruta, ruta_saida_provisional, rexistro)

    ruta_saida = ruta_saida_por_defecto(
        ruta, cartafol_saida, rexistro, informe["persoas"], ruta_saida_provisional
    )
    if ruta_saida != ruta_saida_provisional:
        substituir_con_reintentos(Path(ruta_saida_provisional), Path(ruta_saida))

    risco_residual = informe.get("risco_residual", [])
    n_risco_alto = sum(1 for r in risco_residual if r["confianza"] == "alta")
    # Botón "Revisar este documento" (decisión do usuario 10/10/2026): gárdase a
    # sesión de revisión cos MESMOS códigos (reprocesar daría códigos novos) e,
    # ao confirmar, o revisado substitúe a esta mesma saída.
    sid_revision = None
    if n_risco_alto:
        sid_revision = uuid.uuid4().hex[:12]
        sesion = {
            "ruta_orixe": ruta,
            "rexistro_dir": str(rexistro.directorio),
            "cartafol_saida": cartafol_saida,
            "texto_anonimizado": texto_anonimizado,
            "informe": informe,
            "contexto": _recargar_contexto(ruta),
            "substitucions": substitucions,
            "n_marcadas": sum(1 for p in informe["persoas"] if p["marcado_para_revision"]),
            "n_mosaico": len(informe["riscos_mosaico"]),
            "confirmado": False,
            "creado": datetime.now(timezone.utc).isoformat(),
            "ruta_saida_fixa": ruta_saida,
        }
        SESIONS[sid_revision] = sesion
        rexistro.gardar_sesion(sid_revision, _sesion_persistible(sesion))
    return {
        "sid_revision": sid_revision,
        "ruta_orixe": ruta,
        "ruta_saida": ruta_saida,
        "n_marcadas": sum(1 for p in informe["persoas"] if p["marcado_para_revision"]),
        "n_mosaico": len(informe["riscos_mosaico"]),
        "n_risco_alto": n_risco_alto,
        "n_exentos_cargo_publico": len(informe.get("exentos_cargo_publico", [])),
        "n_categoria_especial": len(informe.get("categoria_especial", [])),
    }


# -- Traballos en segundo plano (barra de progreso) ----------------------
#
# Procesar un cartafol enteiro (ou un PDF grande) pode tardar minutos. Coa
# ruta `/procesar` a petición quedaba aberta ata o final, sen ningunha
# indicación do que pasaba. A interface usa agora `/traballo` (POST, arrinca
# o traballo nun fío e devolve un id) + `/traballo/<id>/estado` (JSON que a
# páxina consulta cada pouco para amosar o ficheiro actual e o
# porcentaxe) + `/traballo/<id>/resultado` (a páxina final). `/procesar`
# segue existindo, síncrona, para navegadores sen JavaScript e para os tests.

TRABALLOS: dict = {}
_BLOQUEO_TRABALLOS = threading.Lock()
_VIDA_TRABALLO_REMATADO_S = 3600  # un traballo rematado esquécese pasada 1 hora


def _preparar_traballo(ruta: str, rexistro_dir: str, cartafol_saida: str | None, modo: str):
    """Valida a petición e crea (sen arrincar) o traballo. Devolve
    `(traballo, None)` ou `(None, mensaxe_de_erro)`."""
    ruta_p = Path(ruta)
    if not ruta_p.exists():
        return None, f"Non se atopa o ficheiro ou cartafol: {ruta}"
    if ruta_p.is_dir():
        ficheiros, omitidos = listar_ficheiros_soportados(ruta)
        if not ficheiros:
            return None, f"Non se atopou ningún documento soportado en: {ruta}"
    else:
        ficheiros, omitidos = [ruta], []

    return {
        "id": uuid.uuid4().hex[:12],
        "modo": modo,
        "ficheiros": ficheiros,
        "omitidos": len(omitidos),
        "e_cartafol": ruta_p.is_dir(),
        "rexistro_dir": rexistro_dir,
        "cartafol_saida": cartafol_saida,
        "estado": "en_curso",  # -> "rematado" | "cancelado" | "erro"
        "cancelar": threading.Event(),  # activado polo usuario: para ANTES do seguinte ficheiro
        "feitos": 0,
        "actual": None,
        "resultados": [],  # modo automático
        "sids": [],  # modo revisar
        "erros": [],  # ficheiros que fallaron (o resto segue)
        "erro": None,  # fallo xeral que abortou o traballo
        "inicio": time.time(),
        "fin": None,
    }, None


def _executar_traballo(traballo: dict) -> None:
    try:
        rexistro = _abrir_rexistro(traballo["rexistro_dir"])
        for ficheiro in traballo["ficheiros"]:
            if traballo["cancelar"].is_set():
                break
            traballo["actual"] = ficheiro
            try:
                if traballo["modo"] == "automatico":
                    traballo["resultados"].append(
                        _procesar_automatico(ficheiro, traballo["cartafol_saida"], rexistro)
                    )
                else:
                    traballo["sids"].append(
                        _crear_sesion(ficheiro, traballo["rexistro_dir"], traballo["cartafol_saida"], rexistro)
                    )
            except Exception as e:  # un ficheiro roto NON debe tirar o resto do lote
                traceback.print_exc()
                traballo["erros"].append({"ruta": ficheiro, "mensaxe": f"{type(e).__name__}: {e}"})
            traballo["feitos"] += 1
        traballo["estado"] = "cancelado" if traballo["cancelar"].is_set() and traballo["feitos"] < len(traballo["ficheiros"]) else "rematado"
    except Exception as e:
        traceback.print_exc()
        traballo["estado"] = "erro"
        traballo["erro"] = f"{type(e).__name__}: {e}"
    finally:
        traballo["actual"] = None
        traballo["fin"] = time.time()


def _esquecer_traballos_vellos() -> None:
    limite = time.time() - _VIDA_TRABALLO_REMATADO_S
    for jid in [j for j, t in TRABALLOS.items() if t["fin"] is not None and t["fin"] < limite]:
        TRABALLOS.pop(jid, None)


def _estado_publico(traballo: dict) -> dict:
    total = len(traballo["ficheiros"])
    feitos = traballo["feitos"]
    rematado = traballo["estado"] != "en_curso"
    seg_gastados = (traballo["fin"] or time.time()) - traballo["inicio"]
    seg_restantes = None
    if not rematado and feitos > 0:
        seg_restantes = round(seg_gastados / feitos * (total - feitos))
    return {
        "estado": traballo["estado"],
        "total": total,
        "feitos": feitos,
        "porcentaxe": 100 if traballo["estado"] == "rematado" else int(feitos * 100 / total) if total else 0,
        "actual": os.path.basename(traballo["actual"]) if traballo["actual"] else None,
        "n_erros": len(traballo["erros"]),
        "cancelando": traballo["cancelar"].is_set() and not rematado,
        "erro": traballo["erro"],
        "segundos_gastados": round(seg_gastados),
        "segundos_restantes": seg_restantes,
    }


@app.route("/traballo", methods=["POST"])
def iniciar_traballo():
    ruta = request.form.get("ruta", "").strip()
    rexistro_dir = request.form.get("rexistro", "./datos_rexistro").strip() or "./datos_rexistro"
    cartafol_saida = request.form.get("cartafol_saida", "").strip() or None
    modo = "automatico" if request.form.get("modo") == "automatico" else "revisar"

    traballo, erro = _preparar_traballo(ruta, rexistro_dir, cartafol_saida, modo)
    if erro:
        return jsonify({"erro": erro}), 400

    with _BLOQUEO_TRABALLOS:
        _esquecer_traballos_vellos()
        TRABALLOS[traballo["id"]] = traballo
    threading.Thread(target=_executar_traballo, args=(traballo,), daemon=True).start()
    return jsonify({"id": traballo["id"], **_estado_publico(traballo)})


@app.route("/traballo/<jid>/estado")
def estado_traballo(jid):
    traballo = TRABALLOS.get(jid)
    if traballo is None:
        return jsonify({"erro": "Traballo descoñecido (o programa reiniciouse?)"}), 404
    return jsonify(_estado_publico(traballo))


@app.route("/traballo/<jid>/cancelar", methods=["POST"])
def cancelar_traballo(jid):
    """Pide parar o lote. Non interrompe o ficheiro que se está a procesar
    (un PDF a medias non se pode deixar a medio gardar): remata ese e non
    empeza o seguinte. O que xa estaba feito queda feito."""
    traballo = TRABALLOS.get(jid)
    if traballo is None:
        return jsonify({"erro": "Traballo descoñecido (o programa reiniciouse?)"}), 404
    traballo["cancelar"].set()
    return jsonify(_estado_publico(traballo))


@app.route("/traballo/<jid>/resultado")
def resultado_traballo(jid):
    traballo = TRABALLOS.get(jid)
    if traballo is None or traballo["estado"] == "en_curso":
        return redirect(url_for("index"))

    rexistro_dir = traballo["rexistro_dir"]
    erros = traballo["erros"]

    if traballo["estado"] == "erro":
        return _render_index(
            pendentes=_pendentes(rexistro_dir), rexistro_dir=rexistro_dir,
            erro=f"O traballo non se puido completar: {traballo['erro']}",
        )

    cancelado = traballo["estado"] == "cancelado"

    if traballo["modo"] == "automatico":
        return render_template(
            "automatico.html", resultados=traballo["resultados"], omitidos=traballo["omitidos"],
            erros=erros, total=len(traballo["ficheiros"]), rexistro_dir=rexistro_dir,
            cancelado=cancelado, feitos=traballo["feitos"],
        )

    sids = traballo["sids"]
    if cancelado:
        return _render_index(
            pendentes=_pendentes(rexistro_dir), rexistro_dir=rexistro_dir,
            aviso_cartafol=(
                f"Proceso cancelado: {traballo['feitos']} de {len(traballo['ficheiros'])} ficheiro(s) "
                f"procesado(s) (pendentes de revisión abaixo); o resto non se tocou."
            ),
            erro=(
                f"{len(erros)} ficheiro(s) non se puideron procesar: "
                + "; ".join(f"{os.path.basename(e['ruta'])} ({e['mensaxe']})" for e in erros)
            ) if erros else None,
        )
    if not erros:
        if not traballo["e_cartafol"]:
            return redirect(url_for("revisar", sid=sids[0], rexistro=rexistro_dir))
        return redirect(url_for(
            "index", rexistro=rexistro_dir, creados=len(sids), omitidos=traballo["omitidos"]
        ))

    detalle = "; ".join(f"{os.path.basename(e['ruta'])} ({e['mensaxe']})" for e in erros)
    return _render_index(
        pendentes=_pendentes(rexistro_dir), rexistro_dir=rexistro_dir,
        aviso_cartafol=f"{len(sids)} documento(s) procesado(s), pendentes de revisión abaixo.",
        erro=f"{len(erros)} ficheiro(s) non se puideron procesar: {detalle}",
    )


@app.route("/procesar", methods=["POST"])
def procesar():
    ruta = request.form["ruta"].strip()
    rexistro_dir = request.form.get("rexistro", "./datos_rexistro").strip() or "./datos_rexistro"
    cartafol_saida = request.form.get("cartafol_saida", "").strip() or None
    modo = request.form.get("modo", "revisar")

    ruta_p = Path(ruta)
    if not ruta_p.exists():
        return _render_index(
            pendentes=[], rexistro_dir=rexistro_dir,
            erro=f"Non se atopa o ficheiro ou cartafol: {ruta}",
        )

    rexistro = _abrir_rexistro(rexistro_dir)

    if modo == "automatico":
        if ruta_p.is_dir():
            soportados, omitidos = listar_ficheiros_soportados(ruta)
            if not soportados:
                return _render_index(
                    pendentes=[], rexistro_dir=rexistro_dir,
                    erro=f"Non se atopou ningún documento soportado en: {ruta}",
                )
            resultados = [_procesar_automatico(f, cartafol_saida, rexistro) for f in soportados]
        else:
            resultados = [_procesar_automatico(ruta, cartafol_saida, rexistro)]
            omitidos = []
        return render_template(
            "automatico.html", resultados=resultados, omitidos=len(omitidos), rexistro_dir=rexistro_dir,
        )

    if ruta_p.is_dir():
        soportados, omitidos = listar_ficheiros_soportados(ruta)
        if not soportados:
            return _render_index(
                pendentes=[], rexistro_dir=rexistro_dir,
                erro=f"Non se atopou ningún documento soportado en: {ruta}",
            )
        for ficheiro in soportados:
            _crear_sesion(ficheiro, rexistro_dir, cartafol_saida, rexistro)
        return redirect(url_for(
            "index", rexistro=rexistro_dir, creados=len(soportados), omitidos=len(omitidos)
        ))

    sid = _crear_sesion(ruta, rexistro_dir, cartafol_saida, rexistro)
    return redirect(url_for("revisar", sid=sid, rexistro=rexistro_dir))


@app.route("/revisar/<sid>")
def revisar(sid):
    rexistro_dir = request.args.get("rexistro", "").strip()
    sesion = _obter_sesion(sid, rexistro_dir)
    if sesion is None:
        return redirect(url_for("index"))

    persoas_marcadas = [p for p in sesion["informe"]["persoas"] if p["marcado_para_revision"]]
    persoas_ok = [p for p in sesion["informe"]["persoas"] if not p["marcado_para_revision"]]
    return render_template(
        "revisar.html",
        sid=sid,
        sesion=sesion,
        rexistro_dir=sesion["rexistro_dir"],
        cartafol_saida=sesion.get("cartafol_saida") or "",
        persoas_marcadas=persoas_marcadas,
        persoas_ok=persoas_ok,
        # No modo corpus só se etiquetan persoas: os riscos de mosaico eran ruído (usuario, 10/10/2026).
        riscos_mosaico=[] if sesion.get("corpus_id") else sesion["informe"]["riscos_mosaico"],
        risco_residual=sesion["informe"].get("risco_residual", []),
        categoria_especial=sesion["informe"].get("categoria_especial", []),
        exentos_cargo_publico=sesion["informe"].get("exentos_cargo_publico", []),
    )


@app.route("/revisar/<sid>/confirmar", methods=["POST"])
def confirmar(sid):
    rexistro_dir = request.form.get("rexistro_dir", "").strip()
    sesion = _obter_sesion(sid, rexistro_dir)
    if sesion is None:
        return redirect(url_for("index"))

    rexistro = _abrir_rexistro(sesion["rexistro_dir"])
    # Un navegador envía os saltos de liña dun <textarea> coma "\r\n"
    # (así o manda a especificación HTML), pero todo o texto interno usa
    # "\n" -- e o separador de páxina dun PDF ("\n\f\n") deixaba de
    # coincidir, polo que o PDF caía SEMPRE a texto plano en canto se
    # confirmaba unha revisión (bug real: "o texto ten 1 páxina(s) pero o
    # PDF orixinal ten 17"). En .docx/.odt tamén deixaba un "\r" solto ao
    # final de cada parágrafo.
    # A pantalla xa non ten edición libre (decisión do usuario 10/10/2026): sen
    # "texto_final", parte do resultado automático; as decisións fan o resto.
    texto_final = request.form.get("texto_final", sesion.get("texto_anonimizado") or "")
    texto_final = texto_final.replace("\r\n", "\n").replace("\r", "\n")
    substitucions = sesion.get("substitucions")

    for persoa in sesion["informe"]["persoas"]:
        if not persoa["marcado_para_revision"]:
            continue
        codigo = persoa["codigo"]
        decision = request.form.get(f"decision_{codigo}", "manter")
        if decision.startswith("fusionar:"):
            manter = decision.split(":", 1)[1]
            rexistro.fusionar(manter, codigo)
            texto_final = texto_final.replace(codigo, manter)
            if substitucions:
                substitucions = [
                    (i, f, manter) if novo == codigo else (i, f, novo)
                    for (i, f, novo) in substitucions
                ]
        else:
            comparacion = ", ".join(persoa.get("posibles_coincidencias") or ["ningunha suxestión"])
            rexistro.manter_separadas(codigo, comparacion)

    # Revisión por DECISIÓNS (formulario novo, `decisions_v2`): o documento
    # xérase desde o ORIXINAL + as decisións, así que conserva SEMPRE o
    # formato. A edición libre do texto (formulario antigo, ou o recadro
    # avanzado) segue funcionando; se rompe a estrutura, xa non cae a .txt:
    # gárdase o documento coas decisións e a edición vai a un .txt aparte.
    avisos = []
    edicion_aparte = None
    texto_orixinal = None
    substitucions_automaticas = list(substitucions or [])
    manter = {p["codigo"] for p in sesion["informe"]["persoas"]}
    fragmentos = []
    if Path(sesion["ruta_orixe"]).exists():
        texto_orixinal, _ = cargar_documento_estruturado(sesion["ruta_orixe"])
    editado_a_man = texto_final != (sesion.get("texto_anonimizado") or "").replace("\r\n", "\n")
    if request.form.get("decisions_v2") == "1" and texto_orixinal is not None and substitucions is not None:
        manter = set(request.form.getlist("anonimizar"))
        codigos = {p["codigo"] for p in sesion["informe"]["persoas"]}
        codigos = {c for c in codigos | {novo for (_, _, novo) in substitucions} if c.startswith("PERSOA_")}
        descartados = codigos - manter
        fragmentos = ler_fragmentos(request.form.get("fragmentos", ""))
        texto_decisions, substitucions, _ = aplicar_decisions(
            texto_orixinal, substitucions, rexistro, descartados, fragmentos, contexto=sesion.get("contexto"),
        )
        for codigo in sorted(descartados):
            rexistro.descartar_por_humano(codigo, "marcada coma non persoa na revisión")
        for fragmento, _ in fragmentos:
            if not re.search(r"(?<!\w)" + re.escape(fragmento) + r"(?!\w)", texto_orixinal):
                avisos.append(f"Non se atopou «{fragmento}» no documento orixinal (non se cambiou nada por el).")
        # Con decisións manda o documento xerado delas; unha edición libre
        # feita á vez non se mestura (podería contradicilas): gárdase aparte.
        if editado_a_man:
            edicion_aparte = texto_final
        texto_final = texto_decisions

    # Documento xa gardado en modo automático: o revisado substitúe esa saída.
    ruta_saida = sesion.get("ruta_saida_fixa") or ruta_saida_por_defecto(
        sesion["ruta_orixe"], sesion.get("cartafol_saida"), rexistro, sesion["informe"]["persoas"]
    )
    Path(ruta_saida).parent.mkdir(parents=True, exist_ok=True)
    aviso_formato = None
    contexto = sesion.get("contexto")

    if conserva_formato(contexto, ruta_saida):
        try:
            gardar_documento_estruturado(contexto, texto_final, ruta_saida, substitucions)
        except ValueError:
            if texto_orixinal is None or substitucions is None:
                ruta_saida = str(Path(ruta_saida).with_suffix("")) + ".txt"
                Path(ruta_saida).write_text(texto_final, encoding="utf-8")
                aviso_formato = (
                    "Non se puido conservar o formato orixinal (o ficheiro orixinal xa non está); "
                    f"gardouse coma texto plano en {ruta_saida}."
                )
            else:
                gardar_documento_estruturado(
                    contexto, _aplicar_substitucions_a_texto(texto_orixinal, substitucions), ruta_saida, substitucions
                )
                ruta_edicion = Path(ruta_saida).with_suffix(".edicion-manual.txt")
                ruta_edicion.write_text(texto_final, encoding="utf-8")
                aviso_formato = (
                    "A edición libre do texto cambiaba as liñas ou páxinas do documento, así que non se podía "
                    f"aplicar sobre o formato orixinal. O documento gardouse co seu formato en {ruta_saida} "
                    f"coas decisións da revisión, e a túa edición libre quedou en {ruta_edicion}."
                )
    else:
        Path(ruta_saida).write_text(texto_final, encoding="utf-8")
    if edicion_aparte is not None:
        ruta_edicion = Path(ruta_saida).with_suffix(".edicion-manual.txt")
        ruta_edicion.write_text(edicion_aparte, encoding="utf-8")
        avisos.insert(0, "O documento gardouse coas decisións da revisión; a túa edición libre do texto "
                         f"non se aplicou sobre el e quedou en {ruta_edicion}.")
    if avisos:
        aviso_formato = " ".join(([aviso_formato] if aviso_formato else []) + avisos)

    # Modo corpus (documentos públicos de medición): a decisión gárdase coma etiqueta.
    seguinte_corpus = None
    if sesion.get("corpus_id") and corpus_revision.MODO is not None and texto_orixinal is not None:
        exencions_ok = {int(i) for i in request.form.getlist("exencion_ok") if i.isdigit()}
        corpus_revision.gardar_etiqueta(sesion, texto_orixinal, substitucions_automaticas,
                                        manter, fragmentos, exencions_ok, request.form.get("notas", ""))
        corpus_revision.precargar_seguinte(excepto=sesion["corpus_id"])
        seguinte_corpus = url_for("corpus.cola")

    sesion["confirmado"] = True
    sesion["texto_final"] = texto_final
    sesion["ruta_saida"] = ruta_saida
    # xa non fai falta sobrevivir a un reinicio -- elimínase de disco, non só de memoria
    rexistro.eliminar_sesion(sid)
    # Modo corpus: fluxo pechado, ao seguinte documento sen pantalla intermedia
    # (salvo que haxa un aviso que ler, p. ex. un fragmento que non se atopou).
    if seguinte_corpus and not aviso_formato:
        return redirect(seguinte_corpus)
    return render_template(
        "confirmado.html", sesion=sesion, ruta_saida=ruta_saida, aviso_formato=aviso_formato,
        seguinte_corpus=seguinte_corpus,
    )


def _erro_rexistro_inexistente(ruta: str, que_falta: str) -> str | None:
    """A26 (revisión 21/09/2026): abrir directamente un `RexistroCorrespondencias`
    CREA a carpeta e un rexistro baleiro se non existía (comportamento correcto
    para procesar un documento NOVO, pero non nunha pantalla que só le identidades
    xa existentes) -- se o usuario escribiu mal a ruta dun rexistro xa existente,
    isto creaba en silencio un rexistro baleiro distinto, e o erro amosado despois
    ("aínda non hai contrasinal") non deixaba claro que en realidade non se abriu
    o rexistro que se pretendía. Comprobar ANTES de abrir nada -- usado por
    `/reverter` e `/listar-correspondencias`. Devolve a mensaxe de erro, ou
    `None` se o rexistro existe."""
    if (Path(ruta) / "rexistro.enc").exists():
        return None
    return (
        f"Non se atopou ningún rexistro en \"{ruta}\" -- "
        f"comproba a ruta (un rexistro novo baleiro non ten ningunha {que_falta})"
    )


def _sen_cache(resposta):
    """Unha páxina con identidades reais (reversión, listado completo) no
    caché de disco do navegador anularía parte do cifrado en repouso."""
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


@app.route("/reverter", methods=["GET", "POST"])
def reverter():
    resultado = None
    erro = None
    valores = {"rexistro": "./datos_rexistro", "codigo": "", "motivo": ""}

    if request.method == "POST":
        valores["rexistro"] = request.form.get("rexistro", "").strip() or "./datos_rexistro"
        valores["codigo"] = request.form.get("codigo", "").strip()
        valores["motivo"] = request.form.get("motivo", "").strip()
        contrasinal = request.form.get("contrasinal", "")
        erro = _erro_rexistro_inexistente(valores["rexistro"], "identidade que reverter")
        if erro is None:
            try:
                rexistro = _abrir_rexistro(valores["rexistro"])
                resultado = rexistro.reverter(
                    valores["codigo"], valores["motivo"], contrasinal, solicitante=getpass.getuser()
                )
            except (KeyError, ValueError) as e:
                erro = str(e)

    resposta = make_response(
        render_template("reverter.html", valores=valores, resultado=resultado, erro=erro)
    )
    return _sen_cache(resposta)


_FILAS_POR_PAXINA = 200


@app.route("/listar-correspondencias", methods=["GET", "POST"])
def listar_correspondencias():
    resultado = None
    erro = None
    valores = {"rexistro": "./datos_rexistro", "motivo": ""}

    if request.method == "POST":
        valores["rexistro"] = request.form.get("rexistro", "").strip() or "./datos_rexistro"
        valores["motivo"] = request.form.get("motivo", "").strip()
        contrasinal = request.form.get("contrasinal", "")
        desde = max(0, request.form.get("desde", type=int) or 0)

        if not request.form.get("confirmo"):
            erro = (
                "Tes que confirmar que entendes que este listado amosa TODAS as "
                "identidades reais deste rexistro de golpe."
            )
        else:
            erro = _erro_rexistro_inexistente(valores["rexistro"], "correspondencia que listar")
        if erro is None:
            try:
                rexistro = _abrir_rexistro(valores["rexistro"])
                resultado = rexistro.listar_correspondencias(
                    valores["motivo"], contrasinal, solicitante=getpass.getuser(),
                    desde=desde, limite=_FILAS_POR_PAXINA,
                )
            except (KeyError, ValueError) as e:
                erro = str(e)

    resposta = make_response(
        render_template(
            "listar_correspondencias.html", valores=valores, resultado=resultado, erro=erro,
            filas_por_paxina=_FILAS_POR_PAXINA,
        )
    )
    return _sen_cache(resposta)


@app.route("/listar-correspondencias/pdf", methods=["POST"])
def listar_correspondencias_pdf():
    """O mesmo listado en PDF CONFIDENCIAL (ver `informe_pdf`). Ademais do
    motivo, da contrasinal e da confirmación, pide un aviso expreso de que é
    un documento de extrema sensibilidade, e o acceso queda na auditoría
    coma "PDF" (petición do usuario, 03/10/2026)."""
    rexistro_dir = request.form.get("rexistro", "").strip() or "./datos_rexistro"
    motivo = request.form.get("motivo", "").strip()
    erro = None
    if not request.form.get("confirmo") or not request.form.get("aviso_pdf"):
        erro = ("Para xerar o PDF tes que confirmar a autorización e marcar que entendes que é un "
                "documento de extrema sensibilidade.")
    else:
        erro = _erro_rexistro_inexistente(rexistro_dir, "correspondencia que listar")
    if erro is None:
        try:
            rexistro = _abrir_rexistro(rexistro_dir)
            resultado = rexistro.listar_correspondencias(
                f"{motivo} | XERADO PDF CONFIDENCIAL", request.form.get("contrasinal", ""),
                solicitante=getpass.getuser(),
            )
        except (KeyError, ValueError) as e:
            erro = str(e)
    if erro is not None:
        resposta = make_response(render_template(
            "listar_correspondencias.html", valores={"rexistro": rexistro_dir, "motivo": motivo},
            resultado=None, erro=erro, filas_por_paxina=_FILAS_POR_PAXINA))
        return _sen_cache(resposta)
    pdf = informe_pdf.listado_correspondencias(resultado, motivo=motivo, solicitante=getpass.getuser())
    nome = f"correspondencias-CONFIDENCIAL-{datetime.now():%Y%m%d-%H%M}.pdf"
    resposta = make_response(pdf)
    resposta.headers["Content-Type"] = "application/pdf"
    resposta.headers["Content-Disposition"] = f'attachment; filename="{nome}"'
    return _sen_cache(resposta)


@app.route("/definir-contrasinal", methods=["GET", "POST"])
def definir_contrasinal():
    rexistro_dir = request.values.get("rexistro", "./datos_rexistro").strip() or "./datos_rexistro"
    erro = None
    feito = False

    rexistro = _abrir_rexistro(rexistro_dir)
    xa_existe = rexistro.ten_contrasinal_reversion()

    if request.method == "POST":
        rexistro_dir = request.form.get("rexistro", rexistro_dir).strip() or rexistro_dir
        rexistro = _abrir_rexistro(rexistro_dir)
        xa_existe = rexistro.ten_contrasinal_reversion()
        actual = request.form.get("actual", "")
        nova = request.form.get("nova", "")
        confirmacion = request.form.get("confirmacion", "")
        if nova != confirmacion:
            erro = "As dúas contrasinais non coinciden."
        else:
            try:
                rexistro.definir_contrasinal_reversion(nova, actual=actual or None)
                feito = True
            except ValueError as e:
                erro = str(e)

    return render_template(
        "definir_contrasinal.html",
        rexistro_dir=rexistro_dir,
        xa_existe=xa_existe,
        erro=erro,
        feito=feito,
        orixe_clave=rexistro.orixe_clave,
    )


def executar(porto: int = 5000, debug: bool = False, usar_chaveiro: bool = False):
    """So en 127.0.0.1 -- nunca exposto á rede local nin a internet."""
    global USAR_CHAVEIRO_SISTEMA
    USAR_CHAVEIRO_SISTEMA = usar_chaveiro
    app.run(host="127.0.0.1", port=porto, debug=debug)
