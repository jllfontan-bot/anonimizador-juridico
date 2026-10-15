#!/usr/bin/env python3
"""Prepara os documentos da cola do corpus para a LECTURA DE CLAUDE (fase 3 de
plan interno de revisión do corpus): para cada documento que NON é de control escribe
`LOTE/revision/para_claude/<id>.md` co texto orixinal e o tapado polo programa
marcado ⟦así|PERSOA_000001⟧, e a lista de persoas e exencións detectadas.
Claude leo e garda a súa proposta con `corpus_revision.gardar_proposta`.
Os documentos de CONTROL non se exportan: así a proposta non pode existir.
Todo queda no lote (LOCAL, leva nomes reais).

Uso:
    .venv/bin/python medicion/corpus_propostas.py --dir LOTE [--n 10]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from anonimizador.pipeline import anonimizar_texto_detallado, cargar_documento_estruturado  # noqa: E402
from anonimizador.registry import RexistroCorrespondencias  # noqa: E402


def marcar(texto: str, substitucions: list) -> str:
    resultado = texto
    for inicio, fin, novo in sorted(substitucions, key=lambda s: s[0], reverse=True):
        resultado = resultado[:inicio] + f"⟦{texto[inicio:fin]}|{novo}⟧" + resultado[fin:]
    return resultado


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, required=True)
    ap.add_argument("--n", type=int, default=10)
    args = ap.parse_args()
    cola = json.loads((args.dir / "revision" / "cola.json").read_text(encoding="utf-8"))
    manifesto = {d["id"]: d for d in json.loads((args.dir / "manifesto.json").read_text(encoding="utf-8"))["documentos"]}
    destino = args.dir / "revision" / "para_claude"
    destino.mkdir(parents=True, exist_ok=True)
    for doc_id in cola["orde"][:args.n]:
        if doc_id in cola["control"]:
            print(f"{doc_id}: CONTROL, non se exporta")
            continue
        texto, contexto = cargar_documento_estruturado(str(args.dir / "docs" / manifesto[doc_id]["ficheiro"]))
        with tempfile.TemporaryDirectory() as d:
            _, informe, substitucions = anonimizar_texto_detallado(texto, RexistroCorrespondencias(d), contexto=contexto)
        liñas = [f"# {doc_id} — {manifesto[doc_id].get('titulo', '')[:200]}", "",
                 "## Persoas detectadas (mencións)", ""]
        liñas += [f"- {p['codigo']}: {' | '.join(p['mencions'])}" for p in informe["persoas"]]
        liñas += ["", "## Exentas por cargo", ""]
        liñas += [f"- {e['texto']} ({e.get('cargo')})" for e in informe.get("exentos_cargo_publico", [])]
        liñas += ["", "## Texto orixinal co tapado marcado", "", marcar(texto, substitucions)]
        (destino / f"{doc_id}.md").write_text("\n".join(liñas) + "\n", encoding="utf-8")
        print(f"{doc_id}: {len(informe['persoas'])} persoas, {len(texto)} caracteres")


if __name__ == "__main__":
    main()
