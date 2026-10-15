#!/usr/bin/env python3
"""Xera `src/anonimizador/datos/lugares_oficiais.tsv` a partir das descargas
ORIXINAIS (ver `LEEME.md` deste cartafol):

  - `diccionario26.xlsx` (INE, municipios de España a 1/1/2026, CC BY 4.0)
  - `nomenclator-galicia.csv` (Xunta de Galicia, Nomenclátor de Galicia,
    Decreto 27/2026, CC BY-SA 4.0)

A táboa gárdase SEN filtrar contra nomes e apelidos: os criterios de uso
(un lugar que tamén é apelido frecuente só se le coma lugar con contexto)
viven no código (`lugares_oficiais.py`, `ner.py`), á vista e con tests.

Cada liña: NOME_NORMALIZADO <TAB> orixes, onde orixes é un subconxunto de
  I municipio do INE · C concello galego · F parroquia galega ·
  L lugar galego · P provincia galega.
Normalización: a MESMA ca `nomes_ine.normalizar` (maiúsculas, sen acentos, coa
Ñ). Do orde "Adro, O" / "Ballestero, El" / "Nucia, la" xéranse as dúas formas
("O ADRO" e "ADRO"); do "A/B" dos municipios bilingües, cada alternativa.

Uso (só biblioteca estándar):
    python3 datos/lugares/xerar_lugares.py
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent.parent
sys.path.insert(0, str(RAIZ / "datos" / "ine"))
sys.path.insert(0, str(RAIZ / "src"))

from anonimizador.nomes_ine import normalizar  # noqa: E402
from xerar_taboas import _follas_xlsx  # noqa: E402

DESTINO = RAIZ / "src" / "anonimizador" / "datos" / "lugares_oficiais.tsv"

# Artigos que o nomenclátor e o INE pospoñen ("Adro, O" = "O Adro").
_ARTIGOS = {"O", "A", "OS", "AS", "EL", "LA", "LOS", "LAS", "L'", "EL'", "LES", "ELS", "ES", "SA", "SES", "SON", "NA"}
_ARTIGO_FINAL_RE = re.compile(r"^(?P<nome>.+?),\s*(?P<artigo>[A-Za-zÀ-ÿ]+'?)\s*(?:\((?P<parent>[^)]*)\))?\s*$")


def variantes(bruto: str) -> set[str]:
    """Formas co que pode aparecer un nome oficial nun texto."""
    saida = set()
    for alternativa in re.split(r"\s*/\s*", bruto):
        alternativa = re.sub(r"\s+", " ", alternativa).strip()
        if not alternativa:
            continue
        # "Toxa (Illa Da)", "Ponte Liñares, A (ou Feira Nova, A)": sen parénteses.
        alternativa = re.sub(r"\s*\([^)]*\)", "", alternativa).strip()
        m = _ARTIGO_FINAL_RE.match(alternativa)
        if m and normalizar(m.group("artigo")) in _ARTIGOS:
            nome, artigo = m.group("nome").strip(), m.group("artigo")
            saida.add(nome)
            saida.add(f"{artigo}{'' if artigo.endswith(chr(39)) else ' '}{nome}")
        else:
            saida.add(alternativa)
    return {normalizar(v).replace("’", "'") for v in saida if v}


def ine() -> dict[str, set[str]]:
    taboa: dict[str, set[str]] = {}
    for filas in _follas_xlsx(AQUI / "diccionario26.xlsx").values():
        for fila in filas:
            if not fila.get("C", "").isdigit():  # cabeceira e título
                continue
            for v in variantes(fila.get("E", "")):
                taboa.setdefault(v, set()).add("I")
    return taboa


def galicia() -> dict[str, set[str]]:
    taboa: dict[str, set[str]] = {}
    with open(AQUI / "nomenclator-galicia.csv", encoding="utf-8-sig", newline="") as f:
        filas = list(csv.reader(f, delimiter=";"))[1:]
    for fila in filas:
        # Columnas: Provincia; concello NG2003/NG2025; parroquia NG2003/NG2025;
        # advocación 2003/2025 (o santo: non se usa); lugar NG2003/NG2025.
        for indice, orixe in ((0, "P"), (1, "C"), (2, "C"), (3, "F"), (4, "F"), (7, "L"), (8, "L")):
            if fila[indice]:
                for v in variantes(fila[indice]):
                    taboa.setdefault(v, set()).add(orixe)
    return taboa


def main() -> None:
    total: dict[str, set[str]] = {}
    for parcial in (ine(), galicia()):
        for nome, orixes in parcial.items():
            total.setdefault(nome, set()).update(orixes)
    cabeceira = (
        "# Lugares oficiais de España (municipios) e de Galicia (concellos, parroquias, lugares).\n"
        "# Fonte 1: INE, Relación de municipios y códigos (diccionario26.xlsx, a 1/1/2026), CC BY 4.0.\n"
        "#   Elaboración propia con datos extraídos do sitio web do INE: www.ine.es\n"
        "# Fonte 2: Xunta de Galicia, Nomenclátor de Galicia (Decreto 27/2026), abertos.xunta.gal,\n"
        "#   licenza CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/deed.gl).\n"
        "# ESTA TÁBOA DERIVADA COMPÁRTESE COA MESMA LICENZA, CC BY-SA 4.0, citando as dúas fontes.\n"
        "# Rexenerar con datos/lugares/xerar_lugares.py (ver datos/lugares/LEEME.md).\n"
        "# Columnas: nome normalizado; orixes (I municipio INE, C concello, F parroquia, L lugar, P provincia).\n"
    )
    liñas = [f"{nome}\t{''.join(sorted(orixes))}" for nome, orixes in sorted(total.items())]
    DESTINO.write_text(cabeceira + "\n".join(liñas) + "\n", encoding="utf-8")
    print(f"{len(liñas)} nomes -> {DESTINO} ({DESTINO.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
