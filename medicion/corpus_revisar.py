#!/usr/bin/env python3
"""Revisión do corpus público por decisións (plan interno de revisión do corpus).

Escolle unha mostra ao chou dun lote (BOE/DOG xa descargado) e abre a interface
web en MODO CORPUS: cola de documentos, rexistro propio e desbotable, e cada
revisión gárdase coma etiqueta en `LOTE/revision/etiquetas/<id>.json` (fóra de git).

A orde da mostra fíxase coa semente a primeira vez e gárdase en
`LOTE/revision/cola.json`; volver executar retoma a mesma cola. Ampliar (piloto
de 10 -> 60) colle os SEGUINTES da mesma orde: o xa revisado segue valendo.

Uso:
    .venv/bin/python medicion/corpus_revisar.py --dir LOTE --n 10        # piloto
    .venv/bin/python medicion/corpus_revisar.py --dir LOTE --n 60        # ampliar
    .venv/bin/python medicion/corpus_revisar.py --dir LOTE --preparar    # só fixar a mostra
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import threading
import time
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from anonimizador import corpus_revision, web  # noqa: E402

SEMENTE_POR_DEFECTO = 20261010
MOSTRA_COMPLETA = 60
N_CONTROL = 8


def cola_da_mostra(dir_lote: Path, n: int, semente: int) -> tuple:
    """Os `n` primeiros dunha orde ao chou FIXADA na primeira execución, e os
    documentos de CONTROL CEGO (sen propostas de Claude): 8 dos 60 primeiros,
    escollidos tamén coa semente ao crear a cola."""
    ruta = dir_lote / "revision" / "cola.json"
    if ruta.exists():
        gardada = json.loads(ruta.read_text(encoding="utf-8"))
        if gardada["semente"] != semente:
            raise SystemExit(f"A cola xa existe coa semente {gardada['semente']}: non se cambia a mostra.")
        orde, control = gardada["orde"], gardada["control"]
    else:
        manifesto = json.loads((dir_lote / "manifesto.json").read_text(encoding="utf-8"))
        ids = sorted(d["id"] for d in manifesto["documentos"])
        orde = random.Random(semente).sample(ids, len(ids))
        control = random.Random(semente + 1).sample(orde[:MOSTRA_COMPLETA], min(N_CONTROL, len(orde)))
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps({
            "semente": semente,
            "creada": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "orde": orde,
            "control": control,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
    return orde[:n], control


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, required=True, help="Lote do corpus (con manifesto.json e docs/)")
    ap.add_argument("--n", type=int, default=10, help="Tamaño da mostra (10 = piloto)")
    ap.add_argument("--semente", type=int, default=SEMENTE_POR_DEFECTO)
    ap.add_argument("--porto", type=int, default=5090)
    ap.add_argument("--sen-navegador", action="store_true")
    ap.add_argument("--preparar", action="store_true",
                    help="Só fixa a mostra (cola.json) e sae, sen abrir a interface")
    args = ap.parse_args()

    cola, control = cola_da_mostra(args.dir, args.n, args.semente)
    if args.preparar:
        print(f"Cola fixada: {len(cola)} documentos ({sum(i in control for i in cola)} de control)")
        return
    corpus_revision.activar(args.dir, cola, control=control)
    url = f"http://127.0.0.1:{args.porto}/corpus"
    print(f"MODO CORPUS: {len(cola)} documentos de {args.dir}")
    print(f"Etiquetas en {args.dir / 'revision' / 'etiquetas'}")
    print(f"Interface en {url} (Ctrl+C para pechar)")
    if not args.sen_navegador:
        threading.Thread(target=lambda: (time.sleep(1.5), webbrowser.open(url)), daemon=True).start()
    web.executar(porto=args.porto)


if __name__ == "__main__":
    main()
