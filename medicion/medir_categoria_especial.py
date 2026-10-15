#!/usr/bin/env python3
"""Mide o aviso de categoría especial (`categoria_especial.py`) a través do
pipeline completo (o escaneo faise sobre o texto XA anonimizado, igual ca en
produción). Tres conxuntos, sempre por separado:

  1. Os 44 casos de categoría especial do corpus principal (xerador + curados).
     OLLO: a lista de termos coñecía o vocabulario do xerador (VIH, CIG,
     "profesa la religión"...), así que este número está inflado.
  2. `corpus_categoria_especial_reserva.json`: frases redactadas e comitadas
     ANTES da lista, con vocabulario distinto (29 positivas + 19 negativas).
     É o número que conta. Non é un conxunto cego (escribiuno o mesmo autor
     ca lista), pero non se engadiu ningún termo só para acertar un caso del.
  3. Falsos positivos no resto do corpus principal (268 casos sen dato
     sensible): calquera aviso aí é un aviso de máis.

Uso:
    .venv/bin/python medicion/medir_categoria_especial.py [--gardar]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from anonimizador.pipeline import anonimizar_texto
from anonimizador.registry import RexistroCorrespondencias

AQUI = Path(__file__).parent


def _avisos(texto: str) -> tuple[str, list[dict]]:
    with tempfile.TemporaryDirectory() as d:
        anon, informe = anonimizar_texto(texto, RexistroCorrespondencias(d))
    return anon, informe["categoria_especial"]


def _subcategoria_do_xerador(id_caso: str) -> str | None:
    for prefixo, sub in (("saude", "saude"), ("relixion", "relixion"),
                         ("orientacion", "orientacion_sexual"), ("sindical", "sindical")):
        if prefixo in id_caso:
            return sub
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gardar", action="store_true")
    args = ap.parse_args()

    principal = []
    for nome in ("corpus_sintetico.json", "corpus_generado.json"):
        principal.extend(json.loads((AQUI / nome).read_text(encoding="utf-8")))
    reserva = json.loads((AQUI / "corpus_categoria_especial_reserva.json").read_text(encoding="utf-8"))

    detalle = {"xerador": [], "reserva": [], "falsos_positivos_corpus_principal": []}

    print("== 1. Casos do xerador (inflado: a lista coñecía o seu vocabulario) ==")
    xerador = [c for c in principal if c["categoria"] == "categoria_especial"]
    acertos = 0
    for c in xerador:
        esperado = _subcategoria_do_xerador(c["id"])
        anon, avisos = _avisos(c["texto"])
        ok = any(a["categoria"] == esperado for a in avisos)
        acertos += ok
        detalle["xerador"].append({"id": c["id"], "esperado": esperado, "ok": ok,
                                   "anonimizado": anon, "avisos": avisos})
    print(f"   {acertos}/{len(xerador)} ({100*acertos/len(xerador):.1f}%)")

    print("\n== 2. Corpus de reserva (o número que conta) ==")
    positivos = [c for c in reserva if c["esperado"]]
    negativos = [c for c in reserva if not c["esperado"]]
    por_sub: dict[str, list[bool]] = {}
    fallos = []
    for c in positivos:
        anon, avisos = _avisos(c["texto"])
        ok = any(a["categoria"] == c["esperado"] for a in avisos)
        por_sub.setdefault(c["esperado"], []).append(ok)
        detalle["reserva"].append({"id": c["id"], "esperado": c["esperado"], "ok": ok,
                                   "anonimizado": anon, "avisos": avisos})
        if not ok:
            fallos.append((c["id"], anon, avisos))
    total_ok = sum(sum(v) for v in por_sub.values())
    print(f"   Detectados: {total_ok}/{len(positivos)} ({100*total_ok/len(positivos):.1f}%)")
    for sub, v in sorted(por_sub.items()):
        print(f"     {sub}: {sum(v)}/{len(v)}")
    falsos_reserva = []
    for c in negativos:
        anon, avisos = _avisos(c["texto"])
        detalle["reserva"].append({"id": c["id"], "esperado": None, "ok": not avisos,
                                   "anonimizado": anon, "avisos": avisos})
        if avisos:
            falsos_reserva.append((c["id"], avisos))
    print(f"   Negativos sen aviso: {len(negativos) - len(falsos_reserva)}/{len(negativos)}")
    if fallos:
        print("   Non detectados:")
        for id_, anon, avisos in fallos:
            print(f"     {id_}: {anon!r} -> {[a['termo'] for a in avisos]}")
    if falsos_reserva:
        print("   Avisos de máis nos negativos:")
        for id_, avisos in falsos_reserva:
            print(f"     {id_}: {[(a['categoria'], a['termo']) for a in avisos]}")

    print("\n== 3. Falsos positivos no resto do corpus principal ==")
    resto = [c for c in principal if c["categoria"] != "categoria_especial"]
    falsos = []
    for c in resto:
        _, avisos = _avisos(c["texto"])
        if avisos:
            falsos.append((c["id"], avisos))
            detalle["falsos_positivos_corpus_principal"].append({"id": c["id"], "avisos": avisos})
    print(f"   Casos con aviso de máis: {len(falsos)}/{len(resto)}")
    for id_, avisos in falsos:
        print(f"     {id_}: {[(a['categoria'], a['termo']) for a in avisos]}")

    if args.gardar:
        agora = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        destino = AQUI / "resultados" / f"categoria-especial-{agora}.json"
        destino.write_text(json.dumps(detalle, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nInforme gardado en {destino}")


if __name__ == "__main__":
    main()
