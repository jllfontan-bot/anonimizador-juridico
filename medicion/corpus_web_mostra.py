#!/usr/bin/env python3
"""Prepara a LECTURA HUMANA dunha mostra do corpus web: orixinal e
anonimizado lado a lado nunha páxina HTML local.

A metodoloxía do proxecto di que o automático só NON abonda: a auditoría
(`corpus_web_auditar.py`) só atopa o que sabe buscar. Esta mostra é
pequena e variada a propósito (unha ou dúas por fonte e sección, e
algunhas sen ningún achado automático, que son as que máis din de fugas
que ninguén buscou).

A páxina contén datos reais: gárdase en `DIR/mostra/` (local, fóra do
repo) e non se publica en ningures.

Uso:
    .venv/bin/python medicion/corpus_web_mostra.py [--dir DIR] [--n 12]
"""
from __future__ import annotations

import argparse
import html
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus_web_descargar import DIR_POR_DEFECTO  # noqa: E402

_CODIGO_RE = re.compile(r"(\[[A-Z_]+\]|\b[A-Z]+_\d{6}\b)")
MAX_CARACTERES = 12000


def escoller_mostra(resultados: list[dict], n: int, azar: random.Random) -> list[dict]:
    """Primeiro un documento por fonte+sección (variedade), alternando con
    e sen achados; despois enche ata `n` con documentos SEN achados."""
    grupos = defaultdict(list)
    for r in resultados:
        if "caracteres" in r:
            grupos[(r["fonte"], r["seccion"])].append(r)
    mostra = []
    for i, (_, docs) in enumerate(sorted(grupos.items())):
        azar.shuffle(docs)
        con = [d for d in docs if d["achados"]]
        sen = [d for d in docs if not d["achados"]]
        preferidos = (sen + con) if i % 2 else (con + sen)
        mostra.append(preferidos[0])
    resto = [r for docs in grupos.values() for r in docs if r not in mostra and not r["achados"]]
    azar.shuffle(resto)
    return (mostra + resto)[:n]


def _marcar(texto: str) -> str:
    return _CODIGO_RE.sub(lambda m: f"<mark>{m.group()}</mark>", html.escape(texto))


def xerar_html(mostra: list[dict], dir_textos: Path) -> str:
    bloques = []
    for k, r in enumerate(mostra, 1):
        orixinal = (dir_textos / f"{r['id']}.orixinal.txt").read_text(encoding="utf-8")[:MAX_CARACTERES]
        anon = (dir_textos / f"{r['id']}.anonimizado.txt").read_text(encoding="utf-8")[:MAX_CARACTERES]
        achados = "".join(
            f"<li><b>{html.escape(a['tipo'])}</b>: {html.escape(a['texto'])}</li>" for a in r["achados"][:15]
        ) or "<li>ningún achado automático</li>"
        bloques.append(f"""
<section id="d{k}">
  <h2>{k}. {html.escape(r['id'])} <small>{html.escape(r['fonte'])} · {html.escape(r['seccion'])} · {html.escape(r['data'])}</small></h2>
  <p class="titulo">{html.escape(r['titulo'])}</p>
  <details><summary>Achados automáticos ({len(r['achados'])})</summary><ul>{achados}</ul></details>
  <div class="par">
    <div><h3>Orixinal</h3><pre>{html.escape(orixinal)}</pre></div>
    <div><h3>Anonimizado</h3><pre>{_marcar(anon)}</pre></div>
  </div>
  <fieldset>
    <legend>A túa lectura</legend>
    <label><input type="checkbox"> Fuga (dato persoal que quedou)</label>
    <label><input type="checkbox"> Sobre-anonimización (tapou algo que non era persoal)</label>
    <label><input type="checkbox"> Texto roto / ilexible</label>
    <textarea placeholder="Notas: que falla e onde (sen copiar o documento enteiro)"></textarea>
  </fieldset>
</section>""")
    indice = "".join(f'<li><a href="#d{k}">{html.escape(r["id"])}</a> ({html.escape(r["fonte"])} {html.escape(r["seccion"])})</li>'
                     for k, r in enumerate(mostra, 1))
    return f"""<!doctype html>
<html lang="gl"><head><meta charset="utf-8">
<title>Mostra corpus web</title>
<style>
:root {{ --bg:#fff; --fg:#1c1c1c; --panel:#f4f4f2; --mark:#ffe08a; --borde:#ddd; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#161616; --fg:#e8e8e8; --panel:#222; --mark:#6b5500; --borde:#444; }} }}
body {{ background:var(--bg); color:var(--fg); font:15px/1.45 system-ui, sans-serif; margin:0 16px 60px; }}
h1 {{ font-size:1.4em; }} h2 small {{ font-weight:normal; opacity:.7; font-size:.7em; }}
.titulo {{ opacity:.8; }}
.par {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }}
@media (max-width: 800px) {{ .par {{ grid-template-columns:1fr; }} }}
pre {{ background:var(--panel); border:1px solid var(--borde); padding:10px; white-space:pre-wrap;
       word-break:break-word; max-height:70vh; overflow:auto; font-size:13px; }}
mark {{ background:var(--mark); color:inherit; }}
section {{ border-top:2px solid var(--borde); margin-top:28px; }}
fieldset {{ border:1px solid var(--borde); margin-top:8px; }} label {{ display:block; }}
textarea {{ width:100%; min-height:60px; background:var(--panel); color:var(--fg); }}
</style></head><body>
<h1>Mostra para lectura humana — corpus web (LOCAL, datos reais)</h1>
<p>Compara cada orixinal co anonimizado. Procura sobre todo: nomes ou DNI que quedaron
(fuga) e cousas tapadas que non eran persoais (institucións, lugares, leis). Os
códigos de substitución van resaltados. Textos cortados a {MAX_CARACTERES} caracteres.</p>
<ol>{indice}</ol>
{''.join(bloques)}
</body></html>"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=DIR_POR_DEFECTO)
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--semente", type=int, default=20260928)
    args = ap.parse_args()

    resultados = json.loads((args.dir / "auditoria" / "informe.json").read_text(encoding="utf-8"))
    mostra = escoller_mostra(resultados, args.n, random.Random(args.semente))
    destino = args.dir / "mostra" / "index.html"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(xerar_html(mostra, args.dir / "auditoria" / "textos"), encoding="utf-8")
    print(f"Mostra de {len(mostra)} documentos: {destino}")


if __name__ == "__main__":
    main()
