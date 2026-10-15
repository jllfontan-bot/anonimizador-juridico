#!/usr/bin/env python3
"""Distorsións do PDF de saída: texto NON persoal que desaparece.

`corpus_web_auditar.py` busca FUGAS (datos que quedan); isto busca o
contrario, o que o pipeline quería CONSERVAR pero falta no PDF anonimizado
(liñas veciñas borradas polo tachado, marcadores de lista, pés de páxina...).
Atopou así o fallo das liñas veciñas (29/09/2026: 4446 palabras en 118 de
150 documentos).

    perdidas    = palabras(PDF orixinal) - palabras(PDF anonimizado)
    esperadas   = palabras(texto orixinal) - palabras(texto anonimizado)
    inesperadas = perdidas - esperadas

Só amosa contas por documento e as palabras perdidas por páxina: SAÍDA LOCAL
(os documentos teñen datos reais), nunca a gardar no repo.

Uso:
    .venv/bin/python medicion/corpus_web_distorsions.py [--dir DIR] [--detalle]
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

import fitz  # PyMuPDF

sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus_web_descargar import DIR_POR_DEFECTO  # noqa: E402

_PUNTUACION = ".,;:()[]«»\"'“”‘’¿?¡!"


def _normalizar(palabra: str) -> str:
    # O guion brando do orixinal sae coma guion non separable no PDF de saída.
    return palabra.replace("­", "-").replace("‑", "-").strip(_PUNTUACION)


# Coma o pipeline (`pdf_estrutura._PUNTO_ANTES_DE_RAIA_RE`): "Martínez.–El" son
# dúas palabras; senón, tapar só o apelido contaba "Martínez.–El" coma perdida.
_PUNTO_ANTES_DE_RAIA_RE = re.compile("(?<=\\.)(?=[\u2013\u2014])")


def _anacos(palabra_pdf: str) -> list:
    # MuPDF non parte polos espazos tipográficos nin tras ".–"
    return [a for x in palabra_pdf.split() for a in _PUNTO_ANTES_DE_RAIA_RE.split(x)]


def _palabras_pdf(ruta: Path) -> Counter:
    contas = Counter()
    with fitz.open(str(ruta)) as documento:
        for pagina in documento:
            for w in pagina.get_text("words"):
                for anaco in _anacos(w[4]):
                    if t := _normalizar(anaco):
                        contas[t] += 1
    return contas


def _palabras_texto(ruta: Path) -> Counter:
    return Counter(t for t in (_normalizar(x) for x in ruta.read_text(encoding="utf-8").split()) if t)


def perdidas_inesperadas(dir_corpus: Path, doc_id: str) -> Counter:
    fonte = "boe" if doc_id.startswith("BOE") else "dog"
    auditoria = dir_corpus / "auditoria"
    perdidas = _palabras_pdf(dir_corpus / "docs" / fonte / f"{doc_id}.pdf") - _palabras_pdf(
        auditoria / "pdf" / f"{doc_id}.pdf")
    esperadas = _palabras_texto(auditoria / "textos" / f"{doc_id}.orixinal.txt") - _palabras_texto(
        auditoria / "textos" / f"{doc_id}.anonimizado.txt")
    return Counter({k: v for k, v in (perdidas - esperadas).items() if not re.fullmatch(r"[-–—·•]+", k)})


def perdidas_por_paxina(dir_corpus: Path, doc_id: str, palabras: set) -> list:
    fonte = "boe" if doc_id.startswith("BOE") else "dog"
    resultado = []
    with fitz.open(str(dir_corpus / "docs" / fonte / f"{doc_id}.pdf")) as orixinal, \
            fitz.open(str(dir_corpus / "auditoria" / "pdf" / f"{doc_id}.pdf")) as anonimizado:
        for n, (po, pa) in enumerate(zip(orixinal, anonimizado), 1):
            quedan = Counter(_normalizar(x) for w in pa.get_text("words") for x in _anacos(w[4]))
            faltan = []
            for w in po.get_text("words"):
                t = _normalizar(_anacos(w[4])[0]) if w[4].split() else ""
                if t in palabras and quedan[t] <= 0:
                    faltan.append(t)
                elif t in quedan:
                    quedan[t] -= 1
            if faltan:
                resultado.append((n, faltan))
    return resultado


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=DIR_POR_DEFECTO)
    ap.add_argument("--detalle", action="store_true", help="Palabras perdidas por páxina (datos reais)")
    args = ap.parse_args()

    resultados = []
    for pdf in sorted((args.dir / "auditoria" / "pdf").glob("*.pdf")):
        inesperadas = perdidas_inesperadas(args.dir, pdf.stem)
        resultados.append((sum(inesperadas.values()), pdf.stem, inesperadas))
    resultados.sort(reverse=True)

    print(f"Documentos analizados: {len(resultados)}")
    print(f"Con palabras perdidas inesperadas: {sum(1 for r in resultados if r[0])}")
    print(f"Total palabras perdidas inesperadas: {sum(r[0] for r in resultados)}")
    for total, doc_id, inesperadas in resultados:
        if not total:
            break
        print(f"{total:5d}  {doc_id}")
        if args.detalle:
            for n, faltan in perdidas_por_paxina(args.dir, doc_id, set(inesperadas)):
                print(f"        páx {n}: {len(faltan)} -> {' '.join(faltan[:25])}")


if __name__ == "__main__":
    main()
