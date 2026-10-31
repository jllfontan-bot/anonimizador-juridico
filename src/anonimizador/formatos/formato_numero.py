"""Número tal e como o amosa unha cela de Excel (`number_format` do .xlsx).

O .xlsx garda o valor (`0.25`) e o formato á parte (`0%`); quen abre o
arquivo ve «25%». O Markdown leva o que se ve: porcentaxes, millares e
decimais, moeda e ceros á esquerda (`00123`). Un formato que non se sabe
interpretar (científico, fraccións, condicións, datas) devolve `None` e quen
chama usa o valor tal cal.

Separadores: punto de millares e coma decimal, coma en castelán e galego
(os dous idiomas do programa); o .xlsx non garda a configuración rexional.
"""

from __future__ import annotations

import functools
import re
from decimal import ROUND_HALF_UP, Decimal
from typing import NamedTuple, Optional


class _Seccion(NamedTuple):
    antes: str
    despois: str
    min_enteiros: int
    min_decimais: int
    max_decimais: int
    millares: bool
    porcentaxe: bool


_MOEDA = re.compile(r"\[\$([^\]\-]*)(?:-[^\]]*)?\]")


def _separar_seccions(formato: str) -> list:
    pezas, actual, i, n = [], [], 0, len(formato)
    while i < n:
        c = formato[i]
        if c == '"':
            fin = formato.find('"', i + 1)
            fin = n - 1 if fin < 0 else fin
            actual.append(formato[i:fin + 1])
            i = fin + 1
            continue
        if c == "[":
            fin = formato.find("]", i)
            fin = n - 1 if fin < 0 else fin
            actual.append(formato[i:fin + 1])
            i = fin + 1
            continue
        if c == "\\" and i + 1 < n:
            actual.append(formato[i:i + 2])
            i += 2
            continue
        if c == ";":
            pezas.append("".join(actual))
            actual = []
        else:
            actual.append(c)
        i += 1
    pezas.append("".join(actual))
    return pezas


def _analizar_seccion(texto: str) -> Optional[_Seccion]:
    antes, despois, numero = [], [], []
    porcentaxe = False
    i, n = 0, len(texto)
    while i < n:
        c = texto[i]
        destino = despois if numero else antes
        if c == '"':
            fin = texto.find('"', i + 1)
            fin = n - 1 if fin < 0 else fin
            destino.append(texto[i + 1:fin])
            i = fin + 1
            continue
        if c == "[":
            fin = texto.find("]", i)
            fin = n - 1 if fin < 0 else fin
            corchetes = texto[i:fin + 1]
            moeda = _MOEDA.fullmatch(corchetes)
            if moeda:
                destino.append(moeda.group(1))
            elif re.match(r"\[[<>=]", corchetes):
                return None  # condición
            i = fin + 1
            continue
        if c == "\\" and i + 1 < n:
            destino.append(texto[i + 1])
            i += 2
            continue
        if c in "_*":  # espazo de aliñamento / recheo: non se le
            i += 2
            continue
        if c in "0#?,.":
            if despois:  # número partido en dous (`0 "x" 0`)
                return None
            numero.append(c)
        elif c == "%":
            porcentaxe = True
            destino.append("%")
        elif c in "Ee" and i + 1 < n and texto[i + 1] in "+-":
            return None  # científico
        elif c == "/":
            return None  # fraccións
        elif c == "@":
            return None
        elif c.isalpha():
            return None  # datas, horas, «General»
        else:
            destino.append(c)
        i += 1
    numero = "".join(numero)
    if not numero and (antes or despois):  # sección só de texto (`"cero"`)
        return _Seccion("".join(antes + despois), "", -1, 0, 0, False, False)
    if not numero or "?" in numero or numero.endswith(","):  # sen díxitos, ou escala (`0,`)
        return None
    enteiro, _, decimais = numero.partition(".")
    return _Seccion("".join(antes), "".join(despois),
                    enteiro.replace(",", "").count("0"),
                    decimais.count("0"), len(decimais), "," in enteiro, porcentaxe)


@functools.lru_cache(maxsize=512)
def _analizar(formato: str):
    if not formato or formato.lower() == "general":
        return None
    seccions = [_analizar_seccion(s) for s in _separar_seccions(formato)[:3]]
    return None if not seccions or any(s is None for s in seccions) else tuple(seccions)


def _escribir(valor: Decimal, s: _Seccion) -> str:
    if s.min_enteiros < 0:
        return s.antes
    if s.porcentaxe:
        valor *= 100
    cifra = valor.quantize(Decimal(1).scaleb(-s.max_decimais), rounding=ROUND_HALF_UP)
    enteiro, _, decimais = f"{cifra:f}".partition(".")
    decimais = decimais.rstrip("0").ljust(s.min_decimais, "0")
    enteiro = enteiro.zfill(s.min_enteiros) if s.min_enteiros else enteiro.lstrip("0")
    if s.millares:
        enteiro = f"{int(enteiro or 0):,}".replace(",", ".").zfill(len(enteiro)) if enteiro else enteiro
    if not enteiro and not decimais:
        enteiro = "0"
    return (s.antes + enteiro + ("," + decimais if decimais else "") + s.despois).strip()


def formatar(valor, formato: str) -> Optional[str]:
    """`valor` (int/float) como o amosa `formato`, ou `None` se non se sabe."""
    seccions = _analizar(formato)
    if seccions is None:
        return None
    try:
        v = Decimal(repr(valor))
    except Exception:
        return None
    if v == 0 and len(seccions) >= 3:
        return _escribir(v, seccions[2])
    if v < 0:
        if len(seccions) >= 2:
            return _escribir(-v, seccions[1])
        return "-" + _escribir(-v, seccions[0])
    return _escribir(v, seccions[0])
