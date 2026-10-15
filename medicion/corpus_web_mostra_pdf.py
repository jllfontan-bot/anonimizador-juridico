#!/usr/bin/env python3
"""LECTURA HUMANA visual dos PDF do corpus web: páxinas orixinal/anonimizado
lado a lado, nunha páxina HTML LOCAL (datos reais: `DIR/mostra_pdf/`, fóra do
repo, nunca se publica).

A diferenza de `corpus_web_mostra.py` (texto), aquí vese o PDF de saída tal
como o verá quen o reciba: liñas borradas, táboas estragadas, códigos
superpostos... As marcas gárdanse no navegador e o botón "Copiar marcas"
xera un resumo para pegalo no chat (as casillas soas non chegan a ningures).

Uso:
    .venv/bin/python medicion/corpus_web_mostra_pdf.py [--dir DIR] [--doc ID[:PÁX,PÁX][=MOTIVO] ...]
"""
from __future__ import annotations

import argparse
import html
import random
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF

sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus_web_descargar import DIR_POR_DEFECTO  # noqa: E402

_CODIGO = re.compile(r"PERSOA_\d{6}|\[[A-Z_]+\]")
_PPP = 110

# Os que tiveron problemas na revisión do 29-30/09/2026 (documento, páxinas, motivo).
ESCOLLIDOS = [
    ("BOE-A-2026-18411", [3], "Liñas veciñas borradas por cada substitución"),
    ("BOE-A-2026-19709", [1], "'Dr.' e marcadores 1./2./3."),
    ("BOE-A-2026-19567", [3], "Palabras das liñas veciñas"),
    ("AnuncioG0198-070926-0001_gl", [13, 78], "CVE-DOG na marxe; formulario"),
    ("AnuncioG0761-060726-0002_gl", [2, 20], "Logotipo Xunta + pé ISSN"),
    ("AnuncioG0426-310826-0001_gl", [3], "Caixetín dun plano"),
    ("BOE-B-2026-30660", [4], "Listaxe de parcelas con DNI e titulares"),
    ("AnuncioL257-140826-0001_gl", [2], "Bloque de texto e iniciais"),
    ("BOE-A-2026-19692", [4, 8], "BIC: estradas, lindes, dioses Lares"),
    ("BOE-B-2026-29850", [1], "Anuncio dun xulgado"),
]


def _paxinas_con_codigos(pdf: Path, maximo: int = 2) -> list:
    with fitz.open(str(pdf)) as d:
        contas = [(len(_CODIGO.findall(p.get_text())), i + 1) for i, p in enumerate(d)]
    return [n for c, n in sorted(contas, reverse=True)[:maximo] if c > 0]


_SCRIPT = """
// Por identificador do documento: a numeración cambia dunha mostra a outra.
const CLAVE = "mostra_pdf_marcas_por_documento";
function ler() { try { return JSON.parse(localStorage.getItem(CLAVE) || "{}"); } catch (e) { return {}; } }
function gardar(d) { try { localStorage.setItem(CLAVE, JSON.stringify(d)); } catch (e) {} }
const estado = ler();
document.querySelectorAll("fieldset[data-doc]").forEach(fs => {
  const k = fs.dataset.id, e = estado[k] || {};
  fs.querySelectorAll("input[type=checkbox]").forEach(c => { c.checked = (e.t || []).includes(c.dataset.t); });
  const nota = fs.querySelector("input[type=text]"); nota.value = e.nota || "";
  fs.addEventListener("input", () => {
    estado[k] = { t: [...fs.querySelectorAll("input[type=checkbox]:checked")].map(c => c.dataset.t), nota: nota.value };
    gardar(estado);
  });
});
document.getElementById("copiar").addEventListener("click", async () => {
  const liñas = [...document.querySelectorAll("fieldset[data-doc]")].map(fs => {
    const t = [...fs.querySelectorAll("input[type=checkbox]:checked")].map(c => c.dataset.t);
    const nota = fs.querySelector("input[type=text]").value;
    return t.length || nota ? `doc ${fs.dataset.doc} (${fs.dataset.id}): ${t.join(", ")}${nota ? " -- " + nota : ""}` : null;
  }).filter(Boolean);
  const txt = liñas.join("\\n") || "(sen marcas)";
  try { await navigator.clipboard.writeText(txt); document.getElementById("aviso").textContent = "Copiado: pégao no chat."; }
  catch (e) { prompt("Copia isto:", txt); }
});
"""


def xerar(dir_corpus: Path, escollidos: list, extras_ao_chou: bool = True) -> Path:
    auditoria, destino = dir_corpus / "auditoria", dir_corpus / "mostra_pdf"
    destino.mkdir(exist_ok=True)
    if not extras_ao_chou:
        return _xerar_html(dir_corpus, auditoria, destino, escollidos)
    azar = random.Random(20260930)
    con_codigos = [p.stem for p in sorted((auditoria / "pdf").glob("BOE-A-*.pdf"))
                   if sum(len(_CODIGO.findall(pg.get_text())) for pg in fitz.open(str(p))) >= 15]
    xa = {e[0] for e in escollidos}
    extra = [(i, None, "BOE con moitos códigos") for i in azar.sample([c for c in con_codigos if c not in xa], 2)]
    resto = [p.stem for p in sorted((auditoria / "pdf").glob("*.pdf")) if p.stem not in xa | {e[0] for e in extra}]
    extra += [(i, None, "Escollido ao chou") for i in azar.sample(resto, 3)]
    return _xerar_html(dir_corpus, auditoria, destino, escollidos + extra)


def _xerar_html(dir_corpus: Path, auditoria: Path, destino: Path, escollidos: list) -> Path:
    bloques, indice = [], []
    for k, (doc_id, paxinas, motivo) in enumerate(escollidos, 1):
        fonte = "boe" if doc_id.startswith("BOE") else "dog"
        orixinal, anon = dir_corpus / "docs" / fonte / f"{doc_id}.pdf", auditoria / "pdf" / f"{doc_id}.pdf"
        if not orixinal.exists() or not anon.exists():
            continue
        if paxinas == "todas":
            with fitz.open(str(orixinal)) as do:
                paxinas = list(range(1, len(do) + 1))
        paxinas = paxinas or _paxinas_con_codigos(anon) or [1]
        figuras = []
        with fitz.open(str(orixinal)) as do, fitz.open(str(anon)) as da:
            for n in paxinas:
                if n > len(do):
                    continue
                for sufixo, d in (("o", do), ("a", da)):
                    d[n - 1].get_pixmap(dpi=_PPP).save(destino / f"{doc_id}_p{n}_{sufixo}.png")
                nome = html.escape(doc_id)
                figuras.append(f"""
  <h3>Páxina {n}</h3>
  <div class="par">
    <figure><figcaption>Orixinal</figcaption><img loading="lazy" src="{nome}_p{n}_o.png"></figure>
    <figure><figcaption>Anonimizado</figcaption><img loading="lazy" src="{nome}_p{n}_a.png"></figure>
  </div>""")
        indice.append(f'<li><a href="#d{k}">{html.escape(doc_id)}</a> — {html.escape(motivo)}</li>')
        bloques.append(f"""
<section id="d{k}">
  <h2>{k}. {html.escape(doc_id)} <small>{html.escape(motivo)}</small></h2>
  {''.join(figuras)}
  <fieldset data-doc="{k}" data-id="{html.escape(doc_id)}"><legend>A túa lectura</legend>
    <label><input type="checkbox" data-t="fuga"> Fuga (dato persoal que quedou)</label>
    <label><input type="checkbox" data-t="tapou algo non persoal"> Tapou algo que non era persoal</label>
    <label><input type="checkbox" data-t="texto ou táboa estragados"> Texto ou táboa estragados</label>
    <label><input type="checkbox" data-t="correcto"> Correcto</label>
    <input type="text" placeholder="Páxina e que (opcional)">
  </fieldset>
</section>""")

    saida = destino / "index.html"
    saida.write_text(f"""<!doctype html>
<html lang="gl"><head><meta charset="utf-8"><title>Mostra PDF anonimizados</title>
<style>
:root {{ --bg:#fff; --fg:#1c1c1c; --borde:#ccc; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#161616; --fg:#e8e8e8; --borde:#444; }} }}
body {{ background:var(--bg); color:var(--fg); font:15px/1.45 system-ui,sans-serif; margin:0 16px 60px; }}
h2 small {{ font-weight:normal; opacity:.7; font-size:.7em; }}
.par {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }}
@media (max-width:900px) {{ .par {{ grid-template-columns:1fr; }} }}
figure {{ margin:0; }} img {{ width:100%; border:1px solid var(--borde); background:#fff; }}
section {{ border-top:2px solid var(--borde); margin-top:28px; }}
label {{ display:block; }} input[type=text] {{ width:100%; }}
</style></head><body>
<h1>Mostra visual dos PDF anonimizados (LOCAL, datos reais)</h1>
<p>Orixinal á esquerda, anonimizado á dereita. Mira sobre todo: que non queden nomes/DNI,
que non desaparezan liñas veciñas, marcadores de lista nin bordos de táboas, e que o
"CVE-DOG" e o "cve: BOE" da marxe sigan intactos. As marcas gárdanse neste navegador.</p>
<p><button id="copiar">Copiar marcas</button> <span id="aviso"></span></p>
<ol>{''.join(indice)}</ol>
{''.join(bloques)}
<script>{_SCRIPT}</script>
</body></html>""", encoding="utf-8")
    return saida


def _ler_doc(especificacion: str) -> tuple:
    """"BOE-A-2026-623:1,3=Maxistrada" -> ("BOE-A-2026-623", [1, 3], "Maxistrada")."""
    doc, _, motivo = especificacion.partition("=")
    doc_id, _, paxinas = doc.partition(":")
    return doc_id, [int(n) for n in paxinas.split(",")] if paxinas else "todas", motivo or "Escollido"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=DIR_POR_DEFECTO)
    ap.add_argument("--doc", action="append", default=[], metavar="ID[:PÁX,PÁX][=MOTIVO]",
                    help="Documento da mostra (repetible); sen páxinas, TODAS. Substitúe a "
                         "ESCOLLIDOS e non engade documentos ao chou.")
    args = ap.parse_args()
    if args.doc:
        saida = xerar(args.dir, [_ler_doc(d) for d in args.doc], extras_ao_chou=False)
    else:
        saida = xerar(args.dir, ESCOLLIDOS)
    print(f"Mostra visual: {saida}")


if __name__ == "__main__":
    main()
