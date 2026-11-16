"""Etapas con nome da conversión dun documento, para indicar o progreso.

Caso real (portátil con Windows, 15/11/2026): nun PDF de 351 páxinas o
contador de páxinas chegaba ao final e o Reductor seguía varios minutos sen
ningún indicador (detección e anonimización do texto enteiro). Quen converte
(`conversor.converter`, argumento `progreso_etapa`) pon un aviso con
`avisar`; o motor só chama a `etapa` nos seus puntos de paso. Sen aviso,
`etapa` non fai nada: o motor compórtase e devolve exactamente o mesmo.

`clave`: unha de `ETAPAS` (o texto visible é `conversor.etapa.<clave>`, en
`textos/*.json`). `feito`/`total`: avance dentro da etapa, se hai un bucle
que se poida contar (anacos do NER, persoas ao asociar os DNI).
O aviso NON debe lanzar excepcións: chámase no medio do motor.
"""
from __future__ import annotations

import contextvars
from contextlib import contextmanager

ETAPAS = ("detectar", "axustar", "agrupar", "codigos", "riscos", "markdown", "gardar")

_AVISO = contextvars.ContextVar("aviso_etapa", default=None)


@contextmanager
def avisar(callback):
    token = _AVISO.set(callback)
    try:
        yield
    finally:
        _AVISO.reset(token)


def etapa(clave: str, feito: int | None = None, total: int | None = None) -> None:
    aviso = _AVISO.get()
    if aviso is not None:
        aviso(clave, feito, total)
