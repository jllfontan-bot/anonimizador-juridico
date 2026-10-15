"""Listas oficiais de lugares (municipios do INE e Nomenclátor de Galicia:
concellos, parroquias e lugares) para non tapar coma persoa un topónimo.

Datos: `datos/lugares_oficiais.tsv`, táboa derivada con licenza CC BY-SA 4.0
que cita as súas dúas fontes (ver `datos/lugares/LEEME.md` na raíz do
repositorio). A licenza da táboa non afecta ao resto do código.

Por que existe: o modelo de castelán toma coma PER topónimos que non coñece
("Braña", "San Clodio", "Cartelle", municipios cataláns...) e un lugar tapado
coma persoa é a sobreanonimización dominante. Unha lista oficial non depende
de que o modelo "coñeza" o lugar.

Criterio (`e_lugar_oficial`):
  - un lugar da lista que non é nome nin apelido frecuente do INE non se tapa
    coma persoa (salvo con "don/doña" diante: esa decisión é do chamador);
  - un lugar que TAMÉN é apelido frecuente ("Castro", "Vilar", "Lugo") ou que
    ten forma de nome de persoa só se le coma lugar con CONTEXTO de lugar
    ("en", "parroquia de", "concello de", "vecino de", unha provincia ao lado
    ou unha enumeración de lugares)."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from . import nomes_ine

_DATOS = Path(__file__).parent / "datos"

# Un apelido (ou nome) con tantas persoas ou máis é "frecuente": o mesmo
# umbral que `ner._FRECUENCIA_MINIMA_SIGLA_APELIDO`.
FRECUENCIA_APELIDO_FRECUENTE = 1000
FRECUENCIA_NOME_FRECUENTE = 100

PARTICULAS = frozenset("""
DE DEL DO DOS DA DAS LA LAS LOS EL O A OS AS Y E I D L EN
""".split())
ARTIGOS = frozenset("EL LA LOS LAS O A OS AS ELS LES L'".split())
_SANTOS = frozenset("SAN SANTA SANT SANTO SANTS SANTES SAO".split())


@lru_cache(maxsize=1)
def lugares() -> dict[str, str]:
    """Nome normalizado -> orixes (I municipio INE, C concello, F parroquia,
    L lugar, P provincia)."""
    taboa = {}
    with open(_DATOS / "lugares_oficiais.tsv", encoding="utf-8") as f:
        for lina in f:
            if lina.startswith("#") or not lina.strip():
                continue
            nome, orixes = lina.rstrip("\n").split("\t")
            taboa[nome] = orixes
    return taboa


def normalizar_lugar(texto: str) -> str:
    """Mesma normalización ca a táboa; espazos (tamén saltos de liña) colapsados."""
    texto = re.sub(r"-\n\s*", "", texto)
    return nomes_ine.normalizar(re.sub(r"\s+", " ", texto.replace("’", "'"))).strip(" .,;:")


def e_lugar(texto: str) -> bool:
    return normalizar_lugar(texto) in lugares()


def e_provincia(texto: str) -> bool:
    return "P" in lugares().get(normalizar_lugar(texto), "")


def parece_nome_de_persoa(nome_normalizado: str) -> bool:
    """Un lugar que podería ser tamén unha persoa: unha soa palabra que é
    apelido ou nome frecuente do INE; ou varias que empezan por nome de pía
    frecuente ("Manuel Castro") ou son todas apelidos/nomes frecuentes."""
    nomes, apelidos = nomes_ine.nomes(), nomes_ine.apelidos()
    palabras = [p for p in nome_normalizado.split() if p not in PARTICULAS]
    if not palabras:
        return False

    def frecuente(p: str) -> bool:
        return (apelidos.get(p, 0) >= FRECUENCIA_APELIDO_FRECUENTE
                or nomes.get(p, 0) >= FRECUENCIA_NOME_FRECUENTE)

    if len(palabras) == 1:
        return frecuente(palabras[0])
    significativas = [p for p in palabras if p not in _SANTOS]
    if not significativas:
        return False
    # "Santiago de Compostela": con conector e un remate pouco frecuente é un
    # topónimo composto, non "Nome de Apelido".
    if len(nome_normalizado.split()) >= 3 and any(c in PARTICULAS for c in nome_normalizado.split()[1:-1]) \
            and not frecuente(significativas[-1]):
        return False
    if palabras[0] not in _SANTOS and nomes.get(palabras[0], 0) >= FRECUENCIA_NOME_FRECUENTE:
        return True
    return all(frecuente(p) for p in significativas)
