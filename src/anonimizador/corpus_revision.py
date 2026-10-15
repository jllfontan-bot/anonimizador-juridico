"""Modo corpus: revisar documentos PÚBLICOS (BOE/DOG do corpus de medición) coa
mesma pantalla de decisións e gardar cada decisión coma ETIQUETA -- a referencia
coa que se mide a precisión do programa (ver o plan interno de revisión do corpus).

Só se activa desde `medicion/corpus_revisar.py`; fóra dese modo as rutas
`/corpus...` non existen (404) e a aplicación normal non cambia en nada.

- Rexistro de correspondencias PROPIO e desbotable dentro do lote
  (`LOTE/revision/rexistro`), nunca o dun despacho.
- Saídas e etiquetas dentro de `LOTE/revision/` (fóra de git: os documentos son
  públicos pero levan nomes reais)."""

from __future__ import annotations

import getpass
import hashlib
import json
import re
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, Response, abort, redirect, render_template, send_file, url_for

bp = Blueprint("corpus", __name__)

# {"dir": Path do lote, "cola": [ids], "docs": {id: entrada do manifesto},
#  "control": {ids sen propostas de Claude}, "preparadas": {id: sid}} ou None
MODO: dict | None = None

# PyMuPDF non admite varios fíos á vez (piloto do 10/10/2026: textos lidos mal e un
# erro 500 ao abrir dous documentos seguidos). No modo corpus, TODO o procesamento
# (peticións e precarga) pasa por este bloqueo: un documento de cada vez.
BLOQUEO = threading.RLock()


def gardar_proposta(dir_lote: Path, doc_id: str, non_persoas: list, engadidos: list, nota: str | None = None) -> Path:
    """Proposta de Claude para un documento (plan interno de revisión do corpus, punto 6):
    mencións que cre que NON son persoa (por texto, non por código: os códigos
    asígnanse ao abrir a sesión) e fragmentos que faltaría tapar."""
    ruta = Path(dir_lote) / "revision" / "propostas" / f"{doc_id}.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps({"non_persoas": list(non_persoas), "engadidos": list(engadidos), "nota": nota},
                               ensure_ascii=False, indent=1), encoding="utf-8")
    return ruta


def _proposta(doc_id: str) -> dict | None:
    """A proposta do documento, ou None se non hai ou se é de CONTROL (cego)."""
    if doc_id in MODO["control"]:
        return None
    ruta = _revision() / "propostas" / f"{doc_id}.json"
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None


def activar(dir_lote: Path, cola: list, control=()) -> None:
    global MODO
    dir_lote = Path(dir_lote)
    manifesto = json.loads((dir_lote / "manifesto.json").read_text(encoding="utf-8"))
    docs = {d["id"]: d for d in manifesto["documentos"]}
    faltan = [i for i in cola if i not in docs]
    if faltan:
        raise ValueError(f"documentos que non están no manifesto: {faltan}")
    MODO = {"dir": dir_lote, "cola": list(cola), "docs": docs, "control": set(control), "preparadas": {}}


def desactivar() -> None:
    global MODO
    MODO = None
    with _BLOQUEO_DEBUXADOS:
        for proceso in _DEBUXADOS.values():
            if proceso.poll() is None:
                proceso.terminate()
                proceso.wait()
        _DEBUXADOS.clear()


def _revision() -> Path:
    return MODO["dir"] / "revision"


def rexistro_dir() -> str:
    return str(_revision() / "rexistro")


def _ruta_etiqueta(doc_id: str) -> Path:
    return _revision() / "etiquetas" / f"{doc_id}.json"


def _ruta_orixinal(doc_id: str) -> Path:
    return MODO["dir"] / "docs" / MODO["docs"][doc_id]["ficheiro"]


def _ruta_previa(doc_id: str) -> Path:
    return _revision() / "previa" / f"{doc_id}{_ruta_orixinal(doc_id).suffix}"


def _require_modo() -> None:
    if MODO is None:
        abort(404)


@bp.route("/corpus")
def cola():
    """Fluxo pechado (petición do usuario no piloto): abre directamente o
    primeiro documento pendente; se non queda ningún, a lista final."""
    _require_modo()
    seguinte = next((i for i in MODO["cola"] if not _ruta_etiqueta(i).exists()), None)
    if seguinte is not None:
        return redirect(url_for("corpus.abrir", doc_id=seguinte))
    return lista()


@bp.route("/corpus/lista")
def lista():
    """Todos os documentos da mostra, para volver revisar un xa feito."""
    _require_modo()
    filas = [
        {"id": i, "fonte": MODO["docs"][i]["fonte"], "titulo": MODO["docs"][i].get("titulo", ""),
         "revisado": _ruta_etiqueta(i).exists()}
        for i in MODO["cola"]
    ]
    seguinte = next((f["id"] for f in filas if not f["revisado"]), None)
    return render_template("corpus_cola.html", filas=filas, seguinte=seguinte,
                           feitos=sum(f["revisado"] for f in filas), total=len(filas))


def _crear(doc_id: str) -> str:
    """Anonimiza o documento, crea a súa sesión de revisión e a previa (PDF do
    resultado automático para comparalo co orixinal). Devolve o sid."""
    from . import web
    from .pipeline import cargar_documento_estruturado, gardar_documento_estruturado

    with BLOQUEO:
        rexistro = web._abrir_rexistro(rexistro_dir())
        saida = _revision() / "saida"
        saida.mkdir(parents=True, exist_ok=True)
        sid = web._crear_sesion(str(_ruta_orixinal(doc_id)), rexistro_dir(), str(saida), rexistro)
        sesion = web.SESIONS[sid]
        sesion["corpus_id"] = doc_id
        sesion["corpus_control"] = doc_id in MODO["control"]
        sesion["proposta"] = _proposta(doc_id)
        sesion["corpus_posicion"] = f"{MODO['cola'].index(doc_id) + 1} de {len(MODO['cola'])}"
        sesion["corpus_titulo"] = MODO["docs"][doc_id].get("titulo", "")
        rexistro.gardar_sesion(sid, web._sesion_persistible(sesion))
        # Contexto fresco (gardar pode modificar o que leva a sesión en memoria).
        previa = _ruta_previa(doc_id)
        previa.parent.mkdir(parents=True, exist_ok=True)
        _, contexto = cargar_documento_estruturado(str(_ruta_orixinal(doc_id)))
        if contexto:
            gardar_documento_estruturado(contexto, sesion["texto_anonimizado"], str(previa), sesion["substitucions"])
        else:
            previa.write_text(sesion["texto_anonimizado"], encoding="utf-8")
        return sid


def preparar(doc_id: str) -> str:
    """Sesión lista para `doc_id` (a xa preparada se segue pendente, ou unha nova)."""
    from . import web
    with BLOQUEO:
        sid = MODO["preparadas"].get(doc_id)
        if sid is None or sid not in web.SESIONS or web.SESIONS[sid].get("confirmado"):
            sid = _crear(doc_id)
            MODO["preparadas"][doc_id] = sid
        return sid


def precargar_seguinte(excepto: str | None = None) -> None:
    """En segundo plano, prepara o seguinte documento pendente da cola: ao
    premer "Revisar o seguinte" xa está listo (lentitude do piloto)."""
    if MODO is None:
        return
    pendentes = [i for i in MODO["cola"] if i != excepto and not _ruta_etiqueta(i).exists()]
    if not pendentes:
        return

    def traballo(doc_id=pendentes[0]):
        try:
            if MODO is not None:
                preparar(doc_id)
                iniciar_imaxes(doc_id, "orixinal")
                iniciar_imaxes(doc_id, "previa")
        except Exception as e:  # a precarga nunca pode tirar o servidor
            print(f"Precarga de {doc_id} fallou: {e}")

    threading.Thread(target=traballo, daemon=True).start()


@bp.route("/corpus/<doc_id>")
def abrir(doc_id):
    _require_modo()
    if doc_id not in MODO["cola"]:
        abort(404)
    sid = preparar(doc_id)
    iniciar_imaxes(doc_id, "orixinal")
    iniciar_imaxes(doc_id, "previa")
    precargar_seguinte(excepto=doc_id)
    return redirect(url_for("revisar", sid=sid, rexistro=rexistro_dir()))


@bp.route("/corpus/ficheiro/<doc_id>/<cal>")
def ficheiro(doc_id, cal):
    _require_modo()
    if doc_id not in MODO["docs"] or cal not in ("orixinal", "previa"):
        abort(404)
    ruta = _ruta_orixinal(doc_id) if cal == "orixinal" else _ruta_previa(doc_id)
    if not ruta.exists():
        abort(404)
    return send_file(str(ruta))


_PPP_VISOR = 110
_PRAZO_IMAXES = 600  # segundos que unha petición agarda por unha páxina

# Rutas que NON pasan polo bloqueo (web._serializar_no_modo_corpus): non usan
# PyMuPDF neste proceso. As imaxes debúxaas `corpus_imaxes.py` noutro proceso.
# (`revisar` tampouco cando a sesión xa está en memoria: ver web.py.)
SEN_BLOQUEO = frozenset({"corpus.ver", "corpus.paxina", "corpus.ficheiro", "corpus.lista", "static"})

_DEBUXADOS: dict = {}  # cartafol de imaxes -> subprocess.Popen
_BLOQUEO_DEBUXADOS = threading.Lock()


def _cartafol_imaxes(doc_id: str, cal: str) -> Path | None:
    """Caché en disco das páxinas; o nome leva a data e o tamaño do PDF para que
    unha previa rexenerada non sirva imaxes vellas."""
    ruta = _ruta_orixinal(doc_id) if cal == "orixinal" else _ruta_previa(doc_id)
    if not ruta.exists() or ruta.suffix.lower() != ".pdf":
        return None
    st = ruta.stat()
    return _revision() / "imaxes" / doc_id / f"{cal}-{st.st_mtime_ns}-{st.st_size}"


def _completo(cartafol: Path) -> bool:
    try:
        n = int((cartafol / "paxinas.txt").read_text())
    except (OSError, ValueError):
        return False
    return all((cartafol / f"{i}.png").exists() for i in range(1, n + 1))


def iniciar_imaxes(doc_id: str, cal: str) -> Path | None:
    """Pon a debuxar as páxinas en segundo plano (se non están xa ou en curso) e
    devolve o cartafol onde irán aparecendo; None se non hai PDF que debuxar."""
    import shutil
    import sys

    cartafol = _cartafol_imaxes(doc_id, cal)
    if cartafol is None:
        return None
    with _BLOQUEO_DEBUXADOS:
        proceso = _DEBUXADOS.get(cartafol)
        if (proceso is not None and proceso.poll() is None) or _completo(cartafol):
            return cartafol
        for vello in cartafol.parent.glob(f"{cal}-*"):
            if vello != cartafol:
                shutil.rmtree(vello, ignore_errors=True)
        cartafol.mkdir(parents=True, exist_ok=True)
        _DEBUXADOS[cartafol] = subprocess.Popen(
            [sys.executable, "-I", str(Path(__file__).with_name("corpus_imaxes.py")),
             str(_ruta_orixinal(doc_id) if cal == "orixinal" else _ruta_previa(doc_id)),
             str(cartafol), str(_PPP_VISOR)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        return cartafol


def _agardar(ficheiro: Path) -> bool:
    """Agarda a que o proceso de debuxo cree `ficheiro`; False se remata sen el."""
    import time
    limite = time.monotonic() + _PRAZO_IMAXES
    while time.monotonic() < limite:
        if ficheiro.exists():
            return True
        with _BLOQUEO_DEBUXADOS:
            proceso = _DEBUXADOS.get(ficheiro.parent)
            vivo = proceso is not None and proceso.poll() is None
        if not vivo:
            return ficheiro.exists()
        time.sleep(0.05)
    return False


def _n_paxinas(doc_id: str, cal: str) -> int | None:
    cartafol = iniciar_imaxes(doc_id, cal)
    if cartafol is None or not _agardar(cartafol / "paxinas.txt"):
        return None
    return int((cartafol / "paxinas.txt").read_text())


@bp.route("/corpus/ver/<doc_id>")
def ver(doc_id):
    """Orixinal e anonimizado lado a lado, páxina a páxina, coma IMAXES: o
    navegador integrado non ten visor de PDF (ofrecía gardar o ficheiro).
    As imaxes van aparecendo segundo se debuxan (noutro proceso)."""
    _require_modo()
    if doc_id not in MODO["docs"] or not _ruta_previa(doc_id).exists():
        abort(404)
    if _ruta_orixinal(doc_id).suffix.lower() != ".pdf":
        return send_file(str(_ruta_previa(doc_id)), mimetype="text/plain")
    iniciar_imaxes(doc_id, "previa")
    n = _n_paxinas(doc_id, "orixinal")
    if n is None:
        abort(500)
    return render_template("corpus_ver.html", doc_id=doc_id, paxinas=range(1, n + 1))


@bp.route("/corpus/paxina/<doc_id>/<cal>/<int:n>.png")
def paxina(doc_id, cal, n):
    _require_modo()
    if doc_id not in MODO["docs"] or cal not in ("orixinal", "previa"):
        abort(404)
    total = _n_paxinas(doc_id, cal)
    if total is None or not 1 <= n <= total:
        abort(404)
    png = _cartafol_imaxes(doc_id, cal) / f"{n}.png"
    if not _agardar(png):
        abort(500)
    return send_file(str(png), mimetype="image/png", max_age=0)


def _commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=Path(__file__).parent,
                              capture_output=True, text=True, timeout=5).stdout.strip() or "descoñecido"
    except (OSError, subprocess.SubprocessError):
        return "descoñecido"


def gardar_etiqueta(sesion: dict, texto_orixinal: str, substitucions_automaticas: list,
                    manter: set, fragmentos: list, exencions_ok: set, notas: str = "") -> Path:
    """Garda a decisión de quen revisou coma etiqueta do documento.

    `substitucions_automaticas`: as do programa ANTES das decisións (posicións no
    texto orixinal); `manter`: códigos que quen revisa deixou marcados coma
    persoa; `fragmentos`: [(texto, substituto|None)] engadidos ("faltaba");
    `exencions_ok`: índices das exencións por cargo que confirmou coma correctas."""
    doc_id = sesion["corpus_id"]
    persoas: dict = {}
    identificadores = []
    for inicio, fin, novo in sorted(substitucions_automaticas):
        mencion = {"inicio": inicio, "fin": fin, "texto": texto_orixinal[inicio:fin]}
        if novo.startswith("PERSOA_"):
            persoas.setdefault(novo, []).append(mencion)
        else:
            identificadores.append({**mencion, "tipo": novo})
    ocupado = [(a, b) for a, b, _ in substitucions_automaticas]
    engadidos = []
    for texto, substituto in fragmentos:
        mencions = [
            {"inicio": m.start(), "fin": m.end()}
            for m in re.finditer(r"(?<!\w)" + re.escape(texto) + r"(?!\w)", texto_orixinal)
            if not any(m.start() < b and a < m.end() for a, b in ocupado)
        ]
        engadidos.append({"texto": texto, "substituto": substituto, "mencions": mencions})
    exentos = [
        {"texto": e["texto"], "cargo": e.get("cargo"),
         "decision": "correcta" if i in exencions_ok else "incorrecta"}
        for i, e in enumerate(sesion["informe"].get("exentos_cargo_publico", []))
    ]
    entrada = MODO["docs"][doc_id]
    etiqueta = {
        "id": doc_id,
        "fonte": entrada["fonte"],
        "seccion": entrada.get("seccion"),
        "ficheiro": entrada["ficheiro"],
        "sha256": hashlib.sha256(_ruta_orixinal(doc_id).read_bytes()).hexdigest(),
        # As posicións refírense a ESTE texto extraído: se un cambio futuro do
        # lector o altera, a medición avisa en vez de casar posicións erradas.
        "sha256_texto": hashlib.sha256(texto_orixinal.encode("utf-8")).hexdigest(),
        "commit": _commit(),
        "data": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "revisor": getpass.getuser(),
        "revisado": True,
        "control": bool(sesion.get("corpus_control")),
        "proposta": sesion.get("proposta"),
        "persoas": [
            {"codigo": c, "decision": "persoa" if c in manter else "non_persoa", "mencions": m}
            for c, m in persoas.items()
        ],
        "identificadores": identificadores,
        "engadidos": engadidos,
        "exentos": exentos,
        "notas": notas.strip(),
    }
    ruta = _ruta_etiqueta(doc_id)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(etiqueta, ensure_ascii=False, indent=1), encoding="utf-8")
    return ruta
