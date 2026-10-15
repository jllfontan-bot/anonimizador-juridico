#!/usr/bin/env python3
"""Medición das TÁBOAS do corpus web: que queda á vista nas columnas de
dato persoal e que se tapou de máis nas outras.

Complementa `corpus_web_auditar.py`, que só mira o que o propio pipeline
detectou (non ve o que nunca detectou). Aquí a referencia é a CABECEIRA:
para cada táboa do PDF ORIXINAL con columnas "Apellidos y nombre",
"DNI/NIE/PAS", "NRP"... (`taboas_pdf.papel_da_cabeceira`), o texto de
cada cela sácase con `find_tables().extract()` -- independente do mapeo
cela -> palabras que usa o anonimizador -- e búscase no PDF de SAÍDA que
xa deixou `corpus_web_auditar.py` en `DIR/auditoria/pdf/`:

  - fuga_persoa / fuga_documento: palabra dunha cela de nome (3+ letras,
    non conector) ou código dunha cela de documento que segue no texto da
    mesma páxina de saída.
  - tapado_outra_columna: palabra (4+ letras) dunha cela doutra columna
    da mesma táboa que XA NON está na páxina de saída (sobre-anonimización
    aproximada: pode ser tamén un dato persoal lexítimo doutra columna).

Límites coñecidos: usa o mesmo vocabulario de cabeceiras ca o anonimizador,
así que non mide as columnas que ese vocabulario non recoñece ("Titular",
"Nome/Razón social"...). Só ve táboas con bordos (igual ca `find_tables`).
E "fuga_persoa" ten falsos positivos en FORMULARIOS EN BRANCO (varios
campos "Nome:", "DNI:", "Enderezo:"... na mesma columna, sen ningún dato
real que encher): a palabra dun rótulo veciño ("DNI", "Ministerio") aparece
tamén noutro sitio lexítimo do documento e conta coma "fuga" aínda que o
anonimizador (que si comproba os dous puntos, `ner._texto_de_cela_e_nome`)
non tapase nada porque non había ningunha persoa que tapar -- confirmar
sempre contra `corpus_web_auditar.py` (o que le o PDF de saída de verdade)
antes de tratar un "fuga_persoa" coma fallo real.

Uso:
    .venv/bin/python medicion/corpus_web_taboas.py --dir DIR [--detalle]
Sen `--detalle` só imprime contas (sen texto dos documentos).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import fitz  # noqa: E402

from anonimizador import taboas_pdf  # noqa: E402

_CONECTORES = {"de", "del", "do", "dos", "da", "das", "la", "las", "los", "el", "y", "e"}
_PALABRA_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
_CODIGO_RE = re.compile(r"[A-Za-z0-9*]+")


def _norm(texto: str) -> str:
    return unicodedata.normalize("NFC", " ".join(texto.split()))


def _ten_palabra(palabra: str, texto: str) -> bool:
    return re.search(r"(?<![\w*])" + re.escape(palabra) + r"(?![\w*])", texto) is not None


def _codigo_de_documento(codigo: str) -> bool:
    digitos = sum(c.isdigit() for c in codigo)
    return digitos >= 5 or (digitos >= 4 and any(c.isalpha() for c in codigo)) or (digitos >= 3 and "*" in codigo)


def _papeis(textos: list) -> tuple:
    for i, fila in enumerate(textos[:3]):
        papeis = {c: p for c, p in ((c, taboas_pdf.papel_da_cabeceira(t)) for c, t in enumerate(fila)) if p}
        if papeis:
            return papeis, i + 1
    return {}, 0


def medir_documento(orixinal: Path, saida: Path, detalle: list) -> Counter:
    contas = Counter()
    with fitz.open(str(orixinal)) as doc_o, fitz.open(str(saida)) as doc_s:
        if len(doc_o) != len(doc_s):
            contas["paxinas_distintas"] += 1
            return contas
        for n, (pax_o, pax_s) in enumerate(zip(doc_o, doc_s)):
            texto_orixinal = _norm(pax_o.get_text())
            texto_saida = _norm(pax_s.get_text())
            for taboa in pax_o.find_tables().tables:
                textos = taboa.extract()
                papeis, primeira = _papeis(textos)
                if not papeis:
                    continue
                contas["taboas"] += 1
                for fila in textos[primeira:]:
                    for c, cela in enumerate(fila):
                        cela = _norm(cela or "")
                        if not cela:
                            continue
                        papel = papeis.get(c)
                        if papel == taboas_pdf.PERSOA:
                            contas["celas_persoa"] += 1
                            restos = [p for p in _PALABRA_RE.findall(cela)
                                      if len(p) >= 3 and p.lower() not in _CONECTORES and _ten_palabra(p, texto_saida)]
                            if restos:
                                contas["celas_persoa_con_fuga"] += 1
                                contas["fuga_persoa"] += len(restos)
                                detalle.append((orixinal.name, n + 1, "persoa", cela, restos))
                        elif papel == taboas_pdf.DOCUMENTO:
                            codigos = [t for t in _CODIGO_RE.findall(cela) if _codigo_de_documento(t)]
                            if not codigos:
                                continue
                            contas["celas_documento"] += 1
                            restos = [t for t in codigos if _ten_palabra(t, texto_saida)]
                            if restos:
                                contas["celas_documento_con_fuga"] += 1
                                contas["fuga_documento"] += len(restos)
                                detalle.append((orixinal.name, n + 1, "documento", cela, restos))
                        else:
                            palabras = [p for p in _PALABRA_RE.findall(cela) if len(p) >= 4]
                            contas["palabras_outras_columnas"] += len(palabras)
                            tapadas = [p for p in palabras
                                       if _ten_palabra(p, texto_orixinal) and not _ten_palabra(p, texto_saida)]
                            if tapadas:
                                contas["tapado_outra_columna"] += len(tapadas)
                                detalle.append((orixinal.name, n + 1, "tapado", cela, tapadas))
    return contas


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, required=True)
    ap.add_argument("--detalle", action="store_true", help="Imprime o texto das celas (datos reais, só en local)")
    args = ap.parse_args()

    manifesto = json.loads((args.dir / "manifesto.json").read_text(encoding="utf-8"))
    total = Counter()
    detalle = []
    for doc in manifesto["documentos"]:
        orixinal = args.dir / "docs" / doc["ficheiro"]
        saida = args.dir / "auditoria" / "pdf" / orixinal.name
        if not saida.exists():
            total["sen_saida"] += 1
            continue
        contas = medir_documento(orixinal, saida, detalle)
        if contas["taboas"]:
            total["documentos_con_taboas"] += 1
        total.update(contas)

    for chave in ("documentos_con_taboas", "taboas", "celas_persoa", "celas_persoa_con_fuga", "fuga_persoa",
                  "celas_documento", "celas_documento_con_fuga", "fuga_documento",
                  "palabras_outras_columnas", "tapado_outra_columna", "sen_saida", "paxinas_distintas"):
        print(f"  {chave:28s} {total[chave]}")
    if args.detalle:
        for nome, paxina, tipo, cela, restos in detalle:
            print(f"- {nome} p.{paxina} [{tipo}] {cela!r} -> {restos}")


if __name__ == "__main__":
    main()
