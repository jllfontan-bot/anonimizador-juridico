#!/usr/bin/env python3
"""Compara o que TAPAN dúas versións do programa sobre os mesmos documentos dun lote.

Para medir un arranxo SEN SESGO: os filtros axústanse mirando uns documentos, e
medilos sobre eses mesmos documentos infla o resultado (petición do usuario,
11/10/2026). Por defecto úsanse só os documentos do lote que NINGUÉN revisou
(sen etiqueta en `LOTE/revision/etiquetas/` nin proposta en `.../propostas/`).

Cada versión é unha referencia de git (`main`, `a880bd9`...; extráese `src/` e
`config/` a un cartafol temporal con `git archive`) ou un cartafol con esa mesma
estrutura (`.` = o código actual, cos cambios sen gardar). Cada versión execútase
no seu propio proceso, de xeito que nunca se mesturan módulos das dúas.

Saída: DESTAPADOS (a versión nova deixa á vista algo que a vella tapaba) e NOVOS
TAPADOS, con contexto, para lelos palabra a palabra; e os documentos con erro.
Os textos levan nomes reais (documentos públicos): gárdese fóra de git.

Uso:
    .venv/bin/python medicion/comparar_tapados.py --lote LOTE --vello main --novo . --saida DIR
    ... --procesos 4             # documentos en paralelo (cada proceso carga o modelo)
    ... --n 50 --semente 1       # só unha mostra ao chou dos documentos non vistos
    ... --incluir-revisados      # todos os documentos do lote (medición SESGADA)

Substitúe os scripts soltos do 04/10 (`destapado*.py`, fóra de git) e o comparador
do 11/10 (`/tmp/cmp/tapados.py` + `dif.py`).
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import subprocess
import sys
import tarfile
import tempfile
from io import BytesIO
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CONTEXTO_ANTES, CONTEXTO_DESPOIS = 60, 40


# --- documentos -------------------------------------------------------------

def ids_a_excluir(ficheiro: Path) -> set:
    """Lista JSON de ids, ou un obxecto con "ids" (p. ex. `mostra_lectura.json` do
    lote 6: os docs que Claude leu para a proba de Windows)."""
    datos = json.loads(Path(ficheiro).read_text(encoding="utf-8"))
    return set(datos["ids"] if isinstance(datos, dict) else datos)


def documentos_do_lote(dir_lote: Path, incluir_revisados: bool = False,
                       n: int | None = None, semente: int = 0, excluir: set = frozenset()) -> list:
    """Ids do manifesto, en orde estable. Sen `incluir_revisados`, quítanse os que
    teñen etiqueta ou proposta (alguén os mirou: medir neles está sesgado), e
    sempre os de `excluir` (vistos por outra vía)."""
    manifesto = json.loads((dir_lote / "manifesto.json").read_text(encoding="utf-8"))
    ids = sorted(d["id"] for d in manifesto["documentos"] if d["id"] not in excluir)
    if not incluir_revisados:
        vistos = {p.stem for sub in ("etiquetas", "propostas")
                  for p in (dir_lote / "revision" / sub).glob("*.json")}
        ids = [i for i in ids if i not in vistos]
    if n is not None and n < len(ids):
        ids = sorted(random.Random(semente).sample(ids, n))
    return ids


# --- extracción (execútase DENTRO do proceso de cada versión) ----------------

def _tapados_dun_documento(args) -> tuple:
    ruta, doc_id = args
    from anonimizador.pipeline import anonimizar_texto_detallado, cargar_documento_estruturado
    from anonimizador.registry import RexistroCorrespondencias
    try:
        texto, contexto = cargar_documento_estruturado(ruta)
        with tempfile.TemporaryDirectory() as d:
            _, _, substitucions = anonimizar_texto_detallado(texto, RexistroCorrespondencias(d), contexto=contexto)
        return doc_id, [
            {"texto": texto[a:b], "tipo": novo.split("_")[0],
             "contexto": texto[max(0, a - CONTEXTO_ANTES):b + CONTEXTO_DESPOIS].replace("\n", " ")}
            for a, b, novo in sorted(substitucions)
        ]
    except Exception as e:  # un documento roto non para a medición: queda rexistrado
        return doc_id, f"ERRO {e!r}"


def extraer(dir_src: Path, dir_lote: Path, ids: list, saida: Path, procesos: int) -> None:
    sys.path.insert(0, str(dir_src))
    manifesto = json.loads((dir_lote / "manifesto.json").read_text(encoding="utf-8"))
    ficheiros = {d["id"]: d["ficheiro"] for d in manifesto["documentos"]}
    traballos = [(str(dir_lote / "docs" / ficheiros[i]), i) for i in ids]
    if procesos > 1:
        import multiprocessing
        with multiprocessing.get_context("spawn").Pool(procesos, initializer=sys.path.insert,
                                                       initargs=(0, str(dir_src))) as pool:
            resultado = dict(pool.imap_unordered(_tapados_dun_documento, traballos))
    else:
        resultado = dict(map(_tapados_dun_documento, traballos))
    saida.write_text(json.dumps({i: resultado[i] for i in ids}, ensure_ascii=False), encoding="utf-8")


# --- versións ----------------------------------------------------------------

def preparar_version(version: str, temporal: Path) -> tuple:
    """(cartafol `src`, descrición). Un cartafol úsase tal cal; unha referencia
    de git extráese (só `src/` e `config/`, que é o que le o programa)."""
    ruta = Path(version)
    if ruta.is_dir():
        if not (ruta / "src" / "anonimizador").is_dir():
            raise SystemExit(f"{ruta} non ten src/anonimizador")
        return ruta.resolve() / "src", f"{ruta.resolve()} (cartafol)"
    commit = subprocess.run(["git", "rev-parse", "--short", version], cwd=RAIZ,
                            capture_output=True, text=True)
    if commit.returncode != 0:
        raise SystemExit(f"Nin cartafol nin referencia de git: {version}")
    commit = commit.stdout.strip()
    destino = temporal / commit
    if not destino.exists():
        tar = subprocess.run(["git", "archive", commit, "src", "config"], cwd=RAIZ,
                             capture_output=True, check=True).stdout
        with tarfile.open(fileobj=BytesIO(tar)) as t:
            t.extractall(destino)
    return destino / "src", f"{version} ({commit})"


def executar_version(dir_src: Path, dir_lote: Path, ids: list, saida: Path, procesos: int) -> dict:
    ficheiro_ids = saida.with_suffix(".ids.json")
    ficheiro_ids.write_text(json.dumps(ids), encoding="utf-8")
    fillo = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--extraer", str(dir_src),
                              "--lote", str(dir_lote), "--ids", str(ficheiro_ids), "--saida", str(saida),
                              "--procesos", str(procesos)])
    try:
        if fillo.wait() != 0:
            raise SystemExit(f"Fallou a extracción con {dir_src} (saída {fillo.returncode})")
    finally:
        # Se se interrompe a comparación (Ctrl+C, kill), o fillo non queda traballando só.
        if fillo.poll() is None:
            fillo.terminate()
            fillo.wait()
    ficheiro_ids.unlink()
    return json.loads(saida.read_text(encoding="utf-8"))


def ficheiro_cache(cache: Path, version: str, dir_lote: Path, ids: list) -> Path | None:
    """Onde gardar/ler os tapados dunha versión de GIT (un cartafol pode cambiar:
    nunca se garda). A clave leva o CONTIDO de `src/` e `config/` (o que se executa:
    un commit que só toca documentación reutiliza o medido), o lote e os ids."""
    if Path(version).is_dir():
        return None
    arbores = subprocess.run(["git", "rev-parse", f"{version}:src", f"{version}:config"], cwd=RAIZ,
                             capture_output=True, text=True)
    if arbores.returncode != 0:
        return None
    import hashlib
    clave = hashlib.sha256(json.dumps([arbores.stdout.split(), str(Path(dir_lote).resolve()),
                                       sorted(ids)]).encode()).hexdigest()[:16]
    return Path(cache) / f"{clave}.json"


# --- comparación --------------------------------------------------------------

def comparar(vello: dict, novo: dict) -> dict:
    """Diferenzas por documento, contando cada (texto, tipo) coas súas
    repeticións: se a versión vella tapaba "Sala" 3 veces e a nova 1, son 2
    destapados. Os documentos con erro nalgunha versión van á parte."""
    erros = sorted(i for i in vello if isinstance(vello[i], str) or isinstance(novo.get(i), str) or i not in novo)
    destapados, novos = [], []
    for doc_id in vello:
        if doc_id in erros:
            continue
        contextos = {(m["texto"], m["tipo"]): m["contexto"] for m in vello[doc_id] + novo[doc_id]}
        conta_v = collections.Counter((m["texto"], m["tipo"]) for m in vello[doc_id])
        conta_n = collections.Counter((m["texto"], m["tipo"]) for m in novo[doc_id])
        for lista, diferenza in ((destapados, conta_v - conta_n), (novos, conta_n - conta_v)):
            for (texto, tipo), veces in sorted(diferenza.items()):
                lista.append({"doc": doc_id, "texto": texto, "tipo": tipo, "veces": veces,
                              "contexto": contextos[(texto, tipo)]})
    return {"documentos": len(vello), "erros": {i: vello.get(i) if isinstance(vello.get(i), str)
                                                  else novo.get(i, "falta") for i in erros},
            "destapados": destapados, "novos_tapados": novos}


def persoas_que_son_lugares(datos: dict) -> list:
    """Tapados coma PERSOA cuxo texto enteiro é un lugar oficial (municipio INE ou
    Nomenclátor de Galicia): candidatos a sobreanonimización para ler un a un
    (moitos son tamén apelidos: van coa frecuencia do INE). Substitúe
    `subst_en_lugares.py` (04/10, fóra de git). Usa as listas do código ACTUAL."""
    sys.path.insert(0, str(RAIZ / "src"))
    from anonimizador import lugares_oficiais, nomes_ine
    lugares, apelidos, nomes = lugares_oficiais.lugares(), nomes_ine.apelidos(), nomes_ine.nomes()
    atopados = []
    for doc_id, mencions in datos.items():
        if isinstance(mencions, str):
            continue
        for m in mencions:
            chave = lugares_oficiais.normalizar_lugar(m["texto"])
            if m["tipo"] == "PERSOA" and chave in lugares:
                atopados.append({"doc": doc_id, "texto": m["texto"], "orixes": lugares[chave],
                                 "apelido_ine": apelidos.get(chave, 0), "nome_ine": nomes.get(chave, 0),
                                 "contexto": m["contexto"]})
    return atopados


def informe(resultado: dict, cabeceira: list) -> str:
    liñas = list(cabeceira)
    liñas.append(f"Documentos: {resultado['documentos']} · erros: {len(resultado['erros'])} · "
                 f"DESTAPADOS: {sum(d['veces'] for d in resultado['destapados'])} · "
                 f"NOVOS TAPADOS: {sum(d['veces'] for d in resultado['novos_tapados'])}")
    for titulo, clave in (("DESTAPADOS (a nova deixa á vista)", "destapados"),
                          ("NOVOS TAPADOS (a nova tapa de máis)", "novos_tapados")):
        liñas += ["", f"== {titulo} =="]
        for d in resultado[clave]:
            liñas.append(f"{d['doc']}  {d['tipo']}  {d['texto']!r} x{d['veces']}  | {d['contexto']}")
    if resultado.get("lugares_tapados") is not None:
        liñas += ["", "== Na versión NOVA, tapados coma PERSOA que son un lugar oficial (ler un a un) =="]
        for d in resultado["lugares_tapados"]:
            liñas.append(f"{d['doc']}  {d['texto']!r} [{d['orixes']}; apelido INE {d['apelido_ine']}, "
                         f"nome INE {d['nome_ine']}]  | {d['contexto']}")
    if resultado["erros"]:
        liñas += ["", "== ERROS =="] + [f"{i}  {e}" for i, e in resultado["erros"].items()]
    return "\n".join(liñas) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--lote", type=Path, required=True, help="Lote do corpus (manifesto.json e docs/)")
    ap.add_argument("--vello", help="Versión de referencia: referencia de git ou cartafol")
    ap.add_argument("--novo", default=".", help="Versión a medir (por defecto, o código actual)")
    ap.add_argument("--saida", type=Path, required=True, help="Cartafol dos resultados (fóra de git)")
    ap.add_argument("--procesos", type=int, default=1)
    ap.add_argument("--n", type=int, help="Só unha mostra ao chou de N documentos")
    ap.add_argument("--semente", type=int, default=20261011)
    ap.add_argument("--excluir", type=Path, action="append", default=[],
                    help="JSON con ids xa vistos por outra vía (lista, ou obxecto con \"ids\"); repetible")
    ap.add_argument("--cache", type=Path,
                    help="Cartafol onde gardar e reutilizar os tapados de cada commit (fóra de git)")
    ap.add_argument("--incluir-revisados", action="store_true",
                    help="Usar tamén os documentos xa revisados (medición SESGADA)")
    ap.add_argument("--extraer", type=Path, help=argparse.SUPPRESS)
    ap.add_argument("--ids", type=Path, help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.extraer:  # proceso fillo: unha soa versión
        ids = json.loads(args.ids.read_text(encoding="utf-8"))
        extraer(args.extraer, args.lote, ids, args.saida, args.procesos)
        return
    if not args.vello:
        ap.error("falta --vello")
    import signal
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))  # `kill` tamén pecha o fillo (finally)

    excluir = set().union(*(ids_a_excluir(f) for f in args.excluir))
    ids = documentos_do_lote(args.lote, args.incluir_revisados, args.n, args.semente, excluir)
    if not ids:
        raise SystemExit("Non queda ningún documento sen revisar neste lote.")
    args.saida.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporal:
        versions = {}
        for nome, version in (("vello", args.vello), ("novo", args.novo)):
            dir_src, descricion = preparar_version(version, Path(temporal))
            gardado = ficheiro_cache(args.cache, version, args.lote, ids) if args.cache else None
            if gardado is not None and gardado.exists():
                print(f"[{nome}] {descricion}: reutilizado de {gardado}", flush=True)
                datos = json.loads(gardado.read_text(encoding="utf-8"))
                (args.saida / f"{nome}.json").write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
            else:
                print(f"[{nome}] {descricion}: {len(ids)} documentos...", flush=True)
                datos = executar_version(dir_src, args.lote, ids, args.saida / f"{nome}.json", args.procesos)
                if gardado is not None:
                    gardado.parent.mkdir(parents=True, exist_ok=True)
                    gardado.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
            versions[nome] = (descricion, datos)
    resultado = comparar(versions["vello"][1], versions["novo"][1])
    resultado["lugares_tapados"] = persoas_que_son_lugares(versions["novo"][1])
    texto = informe(resultado, [
        f"Lote: {args.lote}",
        f"Vello: {versions['vello'][0]}",
        f"Novo:  {versions['novo'][0]}",
        "Documentos: " + ("TODOS (inclúe revisados: SESGADO)" if args.incluir_revisados else "só os non revisados")
        + (f", mostra de {args.n} (semente {args.semente})" if args.n else "")
        + (f", excluídos {len(excluir)} de {', '.join(map(str, args.excluir))}" if excluir else ""),
    ])
    (args.saida / "comparacion.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    (args.saida / "comparacion.txt").write_text(texto, encoding="utf-8")
    print(texto)


if __name__ == "__main__":
    main()
