"""Lectores de formatos novos para o conversor a .md (fase 4), SEN
anonimizar.

Punto de enganche do motor do conversor: `LECTORES` (extensión -> módulo) e
`a_markdown(ruta)` / `convertir(ruta)`. Cada módulo ten `FORMATOS`,
`a_markdown(ruta)` e `convertir(ruta, ...)`, que devolve un `Conversion` co
Markdown, os avisos e os ficheiros escritos á parte.

MODO ANONIMIZADO: estes formatos NON se poden anonimizar aínda -- cada un
necesita os seus tests de fuga (punto 6 do estudo; lista de escondites en
`ESCONDITES.md`). O motor debe rexeitalos nese modo con
`EXTENSIONS_SO_SEN_ANONIMIZAR`.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from . import correos, follas, paxinas_html, presentacions
from ._comun import Conversion

LECTORES = {ext: modulo for modulo in (follas, presentacions, paxinas_html, correos) for ext in modulo.FORMATOS}
EXTENSIONS = tuple(sorted(LECTORES))
# Todas, de momento: ningunha ten aínda os tests de fuga do modo anonimizado.
EXTENSIONS_SO_SEN_ANONIMIZAR = EXTENSIONS


def convertir(ruta: str, **opcions) -> Conversion:
    """Convirte `ruta` co lector da súa extensión. As `opcions` (por exemplo
    `max_filas`, `dir_csv` das follas) pásanse só aos lectores que as
    entenden."""
    sufixo = Path(ruta).suffix.lower()
    modulo = LECTORES.get(sufixo)
    if modulo is None:
        raise ValueError(f"Formato non soportado: {sufixo or ruta}")
    aceptadas = inspect.signature(modulo.convertir).parameters
    return modulo.convertir(ruta, **{k: v for k, v in opcions.items() if k in aceptadas})


def a_markdown(ruta: str, **opcions) -> str:
    return convertir(ruta, **opcions).markdown
