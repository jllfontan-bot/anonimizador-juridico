#!/usr/bin/env python3
"""Xera as táboas de nomes e apelidos que usa o anonimizador a partir das
descargas ORIXINAIS do INE (ver `LEEME.md` deste mesmo cartafol).

Por que un script e non copiar a man: a táboa ten que poder rexenerarse
tal cal cando o INE publique datos novos, e calquera persoa ten que poder
comprobar que non se engadiu nin quitou ningún nome "a ollo" (se se
fixese, a medición con `medicion/corpus_nomes_galegos_reserva.json`
deixaría de demostrar nada).

As táboas gárdanse SEN filtrar (todo nome/apelido dunha soa palabra con
20 ou máis persoas): os filtros contra falsos positivos ("Sala", "Mayo"...)
viven no código (`nomes_ine.py`, `ner.py`), á vista e con tests.

Uso (o .xls de apelidos é formato Excel antigo: precisa `xlrd`, que NON é
dependencia do programa, só deste script):
    python3 -m venv /tmp/venv_xls && /tmp/venv_xls/bin/pip install xlrd==2.0.1
    /tmp/venv_xls/bin/python datos/ine/xerar_taboas.py
"""
from __future__ import annotations

import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
DESTINO = AQUI.parent.parent / "src" / "anonimizador" / "datos"
_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def normalizar(palabra: str) -> str:
    """MESMA normalización ca `nomes_ine.normalizar` (o INE publica sen
    acentos pero conserva a Ñ): maiúsculas, sen diacríticos, Ñ intacta."""
    palabra = palabra.strip().upper().replace("Ñ", "\0")
    palabra = "".join(c for c in unicodedata.normalize("NFD", palabra) if unicodedata.category(c) != "Mn")
    return palabra.replace("\0", "Ñ")


def _follas_xlsx(ruta: Path) -> dict[str, list[dict[str, str]]]:
    """Lector mínimo de .xlsx coa biblioteca estándar (evita engadir
    openpyxl ao programa só para isto)."""
    z = zipfile.ZipFile(ruta)
    compartidas = [
        "".join(t.text or "" for t in si.iter(_NS + "t"))
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(_NS + "si")
    ]
    libro = ET.fromstring(z.read("xl/workbook.xml"))
    relacions = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    follas = {}
    for folla in libro.find(_NS + "sheets"):
        rid = folla.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        raiz = ET.fromstring(z.read("xl/" + relacions[rid].replace("/xl/", "").lstrip("/")))
        filas = []
        for fila in raiz.iter(_NS + "row"):
            celas = {}
            for c in fila.findall(_NS + "c"):
                columna = re.match(r"[A-Z]+", c.get("r")).group()
                v = c.find(_NS + "v")
                if v is None:
                    continue
                celas[columna] = compartidas[int(v.text)] if c.get("t") == "s" else v.text
            filas.append(celas)
        follas[folla.get("name")] = filas
    return follas


def nomes() -> dict[str, int]:
    """Follas "Hombres" e "Mujeres": columnas B (nome) e C (frecuencia).
    Un nome usado polos dous sexos súmase (a táboa non distingue sexo)."""
    frecuencias: dict[str, int] = {}
    for filas in _follas_xlsx(AQUI / "nombres_por_edad_media.xlsx").values():
        for fila in filas:
            nome, frecuencia = fila.get("B", ""), fila.get("C", "")
            if not frecuencia.isdigit() or " " in nome.strip():
                continue
            chave = normalizar(nome)
            frecuencias[chave] = frecuencias.get(chave, 0) + int(frecuencia)
    return frecuencias


def apelidos() -> dict[str, int]:
    """Dúas follas (>=100 e 20-99). Columna C = persoas con ese PRIMEIRO
    apelido, D = co segundo; gárdase o máximo das dúas (un apelido raro
    pode aparecer máis veces en segunda posición)."""
    import xlrd

    libro = xlrd.open_workbook(AQUI / "apellidos_frecuencia.xls")
    frecuencias: dict[str, int] = {}
    for folla in libro.sheets():
        for n in range(folla.nrows):
            fila = folla.row_values(n)
            apelido = fila[1] if isinstance(fila[1], str) else ""
            if not apelido.strip() or " " in apelido.strip() or not isinstance(fila[2], float):
                continue
            segundo = fila[3] if isinstance(fila[3], float) else 0
            chave = normalizar(apelido)
            frecuencias[chave] = max(frecuencias.get(chave, 0), int(fila[2]), int(segundo))
    return frecuencias


def gardar(nome_ficheiro: str, frecuencias: dict[str, int], cabeceira: str) -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    with open(DESTINO / nome_ficheiro, "w", encoding="utf-8", newline="\n") as f:
        f.write(cabeceira)
        for chave in sorted(frecuencias):
            f.write(f"{chave}\t{frecuencias[chave]}\n")
    print(f"{nome_ficheiro}: {len(frecuencias)} entradas")


CITA = (
    "# Elaboración propia con datos extraídos do sitio web do INE: www.ine.es\n"
    "# Licenza CC BY 4.0. Datos a 01/01/2025, actualizados polo INE o 23/04/2026.\n"
    "# Rexenerar con datos/ine/xerar_taboas.py (ver datos/ine/LEEME.md).\n"
)

if __name__ == "__main__":
    gardar("nomes_ine.tsv", nomes(), CITA + "# Nomes dunha soa palabra con frecuencia >= 20 (homes + mulleres).\n")
    gardar("apelidos_ine.tsv", apelidos(), CITA + "# Apelidos dunha soa palabra con frecuencia >= 20 (máx. 1º/2º apelido).\n")
    sys.exit(0)
