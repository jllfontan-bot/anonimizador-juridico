"""Táboas oficiais de nomes e apelidos (INE, CC BY 4.0 -- ver
`datos/ine/LEEME.md` na raíz do repositorio) para o recoñecedor de persoas
por táboa de `ner.py`.

Por que existe: spaCy (`es_core_news_md`, adestrado en castelán) non
recoñece ben nomes de pía galegos pouco frecuentes (Roi, Xacobe, Breixo,
Ledicia, Covadonga...): en frases concretas etiquétaos coma LOC/ORG ou non
os ve, e o nome queda SEN redactar (9 fugas reais na medición do
28/09/2026). Unha lista oficial non depende de que o modelo "coñeza" o
nome.

As táboas gárdanse sen filtrar; os filtros contra palabras que tamén son
nomes están aquí (`nomes_para_detector`) e en `ner.py`, á vista e con
tests."""

from __future__ import annotations

import unicodedata
from functools import lru_cache
from pathlib import Path

_DATOS = Path(__file__).parent / "datos"

# Nomes da lista INE que en documentos xurídicos case sempre son OUTRA
# cousa (mes, cargo, topónimo, palabra común) e que o filtro automático de
# `nomes_para_detector` non colle por ter 100 ou máis persoas. Só se
# quitan do DETECTOR POR TÁBOA: se spaCy recoñece "Camino Pérez" coma
# persoa, segue a redactarse igual.
_NOMES_EXCLUIDOS = frozenset("""
SAN SANTA SANTO CRISTO VIRGEN RIO CAMINO VALLE MONTE MAR SOL
SEGUNDO SEGUNDA PRIMERO TERCERO REINA REY
""".split())

# Por debaixo disto, un "nome" que tamén é palabra coñecida do modelo de
# castelán ("SALA": 22 persoas, "MAYO": 51, "VIGO": 37, "DON": 22) é moito
# máis probable que sexa a palabra ca o nome. Os nomes galegos raros que
# motivaron isto non teñen vector no modelo (LEDICIA, XACOBE, BREIXO,
# TAREIXA) ou pasan o limiar (ROI: 3.532 persoas), así que non se perden.
_FRECUENCIA_MINIMA_SE_E_PALABRA = 100


def normalizar(palabra: str) -> str:
    """Coma o INE: maiúsculas, sen acentos nin diérese, pero coa Ñ (o INE
    distingue "MARTIÑO"). Tamén o usa `datos/ine/xerar_taboas.py`."""
    palabra = palabra.strip().upper().replace("Ñ", "\0")
    palabra = "".join(c for c in unicodedata.normalize("NFD", palabra) if unicodedata.category(c) != "Mn")
    return palabra.replace("\0", "Ñ")


def _ler_taboa(nome_ficheiro: str) -> dict[str, int]:
    taboa = {}
    with open(_DATOS / nome_ficheiro, encoding="utf-8") as f:
        for lina in f:
            if lina.startswith("#") or not lina.strip():
                continue
            chave, frecuencia = lina.rstrip("\n").split("\t")
            taboa[chave] = int(frecuencia)
    return taboa


@lru_cache(maxsize=1)
def nomes() -> dict[str, int]:
    """Nome normalizado -> persoas en España con ese nome (>= 20)."""
    return _ler_taboa("nomes_ine.tsv")


@lru_cache(maxsize=1)
def apelidos() -> dict[str, int]:
    """Apelido normalizado -> persoas con ese apelido (>= 20)."""
    return _ler_taboa("apelidos_ine.tsv")


_NOMES_DETECTOR: dict[int, frozenset] = {}


def nomes_para_detector(nlp) -> frozenset:
    """Os nomes da táboa que o recoñecedor por táboa pode usar: sen os de
    `_NOMES_EXCLUIDOS` e sen os moi pouco frecuentes que tamén son palabra
    coñecida do modelo (ver `_FRECUENCIA_MINIMA_SE_E_PALABRA`). Depende do
    vocabulario do modelo cargado, por iso recibe `nlp` (e gárdase por
    modelo: calcúlase unha soa vez, non en cada documento)."""
    clave = id(nlp.vocab)
    if clave not in _NOMES_DETECTOR:
        _NOMES_DETECTOR[clave] = frozenset(
            nome for nome, frecuencia in nomes().items()
            if len(nome) >= 2
            and nome not in _NOMES_EXCLUIDOS
            and not (frecuencia < _FRECUENCIA_MINIMA_SE_E_PALABRA and nlp.vocab.has_vector(nome.lower()))
        )
    return _NOMES_DETECTOR[clave]
