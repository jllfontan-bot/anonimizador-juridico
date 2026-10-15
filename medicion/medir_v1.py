#!/usr/bin/env python3
"""Medición de referencia (liña base) da v1 contra o corpus sintético.

Punto 5 do plan interno da v2: antes de integrar calquera IA hai que ter
unha forma de comparar. Este script executa `anonimizar_texto` de cada caso
do corpus e comproba dúas métricas SEMPRE xuntas (nunca unha soa):

  - FUGA: un anaco que `debe_desaparecer` segue presente no texto anonimizado.
  - SOBRE-ANONIMIZACIÓN: un anaco que `debe_permanecer` xa NON está no texto
    anonimizado (redactouse algo que non era un dato persoal).

Os casos de categoría "categoria_especial" e "papel_persoa" non teñen
`debe_desaparecer` propio deses conceptos (a v1 non ten recoñecedor ningún
para categoría especial nin papel) -- quedan coma métrica INFORMATIVA
(cantos detecta hoxe a v1 por casualidade, vía NER estándar do nome), non
coma fuga esixible.

Uso:
    .venv/bin/python medicion/medir_v1.py [--gardar]

`--gardar` escribe tamén un informe JSON en `medicion/resultados/`.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from anonimizador.pipeline import anonimizar_texto
from anonimizador.registry import RexistroCorrespondencias


def cargar_corpus(ficheiros: list[str] | None = None) -> list[dict]:
    """Combina o corpus curado a man (`corpus_sintetico.json`, poucos casos
    pero cada un documentado e ligado a un bug real) co corpus xerado por
    `generador_corpus.py` (moitas variantes por categoría, verdade calculada).
    Ámbolos dous seguen o mesmo formato -- ver `medicion/README.md`."""
    casos = []
    for nome_ficheiro in ficheiros or ("corpus_sintetico.json", "corpus_generado.json"):
        ruta = Path(__file__).parent / nome_ficheiro
        if ruta.exists():
            with open(ruta, encoding="utf-8") as f:
                casos.extend(json.load(f))
    return casos


_CONECTORES = {"de", "del", "do", "dos", "da", "das", "la", "las", "los", "el", "y", "e"}


def palabras_a_vista(debe_desaparecer: list[str], anon: str) -> list[str]:
    """FUGA PARCIAL: palabras dun dato que debía desaparecer que seguen no
    texto anonimizado aínda que o dato COMPLETO xa non estea. Atopado o
    28/09/2026 lendo as saídas a man: "Firma el presente documento Breixo
    PERSOA_000001" contaba coma OK (o nome completo xa non está), pero o
    nome de pía quedaba á vista. Métrica á parte: NON cambia o criterio
    de "ok", para que as medicións anteriores sigan sendo comparables."""
    a_vista = []
    for dato in debe_desaparecer:
        if dato in anon:
            continue  # xa conta coma fuga enteira
        for palabra in re.findall(r"[\wÁÉÍÓÚÑÜáéíóúñü'-]+", dato):
            if len(palabra) >= 3 and palabra.lower() not in _CONECTORES and not palabra.isdigit() \
                    and re.search(r"(?<![\w])" + re.escape(palabra) + r"(?![\w])", anon):
                a_vista.append(palabra)
    return a_vista


def medir(corpus: list[dict]) -> dict:
    """Cada caso é un documento SINTÉTICO independente (non partes dun mesmo
    expediente) -- por iso usa un rexistro NOVO por caso. Compartir un só
    rexistro entre os 300+ casos do corpus faría que un nome mencionado nun
    caso puidese "recoñecerse" coma a mesma persoa doutro caso non
    relacionado por pura coincidencia de apelido, contaminando os
    resultados (atopado o 27/09/2026 medindo por primeira vez: "Turno"
    marcábase para revisión nuns casos e noutros non, sen motivo aparente,
    ata illar cada caso co seu propio rexistro)."""
    resultados = []
    for caso in corpus:
        with tempfile.TemporaryDirectory() as d:
            rexistro = RexistroCorrespondencias(d)
            anon, informe = anonimizar_texto(caso["texto"], rexistro)
            fugas = [s for s in caso.get("debe_desaparecer", []) if s in anon]
            fugas_parciais = palabras_a_vista(caso.get("debe_desaparecer", []), anon)
            sobre_anon = [s for s in caso.get("debe_permanecer", []) if s not in anon]
            marcado_para_revision = any(
                p.get("marcado_para_revision") for p in informe.get("persoas", [])
            )
            resultados.append({
                "id": caso["id"],
                "categoria": caso["categoria"],
                "texto_orixinal": caso["texto"],
                "texto_anonimizado": anon,
                "fugas": fugas,
                "fugas_parciais": fugas_parciais,
                "sobre_anonimizacion": sobre_anon,
                # Sobre-anonimización XA marcada para revisión humana non é un
                # fallo silencioso -- é o comportamento deliberado do proxecto
                # ("mellor un falso positivo de máis", ver risco_residual.py).
                # So preocupa quedar SEN marcar, porque en modo automático
                # (sen revisión humana) iso pasaría desapercibido.
                "sobre_anonimizacion_sen_marcar": bool(sobre_anon) and not marcado_para_revision,
                "ok": not fugas and (not sobre_anon or marcado_para_revision),
            })
    return {"resultados": resultados}


def resumir(resultados: list[dict]) -> None:
    total = len(resultados)
    con_fugas = [r for r in resultados if r["fugas"]]
    con_sobre = [r for r in resultados if r["sobre_anonimizacion"]]
    con_sobre_sen_marcar = [r for r in resultados if r["sobre_anonimizacion_sen_marcar"]]
    ok = [r for r in resultados if r["ok"]]

    print(f"Casos totais: {total}")
    print(f"OK: {len(ok)} ({100*len(ok)/total:.1f}%)")
    print(f"Con FUGA (dato que debía desaparecer e non desapareceu): {len(con_fugas)}")
    con_parciais = [r for r in resultados if r.get("fugas_parciais")]
    print(f"Con FUGA PARCIAL (parte do dato segue á vista; non cambia o OK): {len(con_parciais)}")
    print(f"Con sobre-anonimización, PERO marcada para revisión humana: "
          f"{len(con_sobre) - len(con_sobre_sen_marcar)} (comportamento deliberado, non é un fallo)")
    print(f"Con sobre-anonimización SEN marcar (fallo silencioso, preocupa en modo automático): "
          f"{len(con_sobre_sen_marcar)}")
    print()

    if con_fugas:
        print("--- Detalle de FUGAS ---")
        for r in con_fugas:
            print(f"  [{r['categoria']}] {r['id']}: quedou sen tapar {r['fugas']}")
        print()

    if con_parciais:
        print("--- Detalle de FUGAS PARCIAIS ---")
        for r in con_parciais:
            print(f"  [{r['categoria']}] {r['id']}: segue á vista {r['fugas_parciais']}")
        print()

    if con_sobre:
        print("--- Detalle de SOBRE-ANONIMIZACIÓN ---")
        for r in con_sobre:
            marca = "SEN marcar" if r["sobre_anonimizacion_sen_marcar"] else "marcada para revisión"
            print(f"  [{r['categoria']}] {r['id']}: borrouse de máis {r['sobre_anonimizacion']} ({marca})")
        print()

    print("--- Por categoría ---")
    categorias = sorted({r["categoria"] for r in resultados})
    for cat in categorias:
        do_cat = [r for r in resultados if r["categoria"] == cat]
        ok_cat = [r for r in do_cat if r["ok"]]
        print(f"  {cat}: {len(ok_cat)}/{len(do_cat)} OK")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gardar", action="store_true", help="Garda o informe en medicion/resultados/")
    # Os conxuntos de reserva e de controis mídense Á PARTE (nunca
    # mesturados co corpus principal): se non, un bo resultado nun
    # escondería un mal resultado noutro.
    ap.add_argument("--corpus", nargs="+", metavar="FICHEIRO",
                    help="Ficheiros JSON de medicion/ a medir (por defecto, o corpus principal)")
    args = ap.parse_args()

    corpus = cargar_corpus(args.corpus)
    saida = medir(corpus)
    resumir(saida["resultados"])

    if args.gardar:
        agora = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        sufixo = "" if not args.corpus else "-" + "+".join(Path(c).stem for c in args.corpus)
        destino = Path(__file__).parent / "resultados" / f"v1-baseline{sufixo}-{agora}.json"
        with open(destino, "w", encoding="utf-8") as f:
            json.dump(saida, f, ensure_ascii=False, indent=2)
        print(f"\nInforme gardado en {destino}")


if __name__ == "__main__":
    main()
