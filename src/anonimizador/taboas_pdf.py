"""Detección POR COLUMNA nas táboas dos PDF con texto nativo.

Fugas reais do corpus web (BOE + DOG, 28/09/2026): nas listaxes oficiais
en táboa, a cela "APELIDOS, NOME." pártese en varias liñas ("VARELA\\nDOVAL,
\\nANTÍA.", "SALCEDO ROEL, BRAIS\\nMANUEL") e os patróns de texto só collían
parte do nome; e baixo a columna "DNI/NIE/PAS" hai pasaportes e documentos
estranxeiros sen forma recoñecible. Os patróns de texto (`ner.py`,
`recognizers.py`) seguen aí, pero NON abondan: cada forma nova de partir a
cela era unha fuga nova.

Aquí o que manda é a CABECEIRA da columna: se unha táboa ten unha columna
"Apellidos y nombre", "Nome e apelidos", "DNI/NIE/PAS", "NRP"..., cada cela
desa columna é o nome ou o documento dunha persoa, teña a forma que teña.
`page.find_tables()` (PyMuPDF) reconstrúe a táboa a partir das liñas
vectoriais e dá a caixa de cada cela; as palabras xa extraídas
(`pdf_estrutura`) cuxo centro cae nesa caixa son o contido da cela, e as
súas posicións no texto da páxina son o que despois se redacta.

Límites (medidos e sabidos, non esquecidos):
  - Só táboas CON LIÑAS (bordos vectoriais): `find_tables` coa estratexia
    por defecto non ve as táboas sen bordos (columnas aliñadas só con
    espazos). A estratexia "text" si as ve, pero atopa "táboas" en
    calquera texto a dúas columnas -- demasiado ruído para decidir por
    ela que algo é un nome. Esas táboas seguen dependendo dos patróns.
  - Nada en páxinas escaneadas (OCR): non hai liñas vectoriais nin texto
    nativo; a táboa é píxeles.
  - Páxinas xiradas (/Rotate distinto de 0): sáltanse (coordenadas de
    `find_tables` sen comprobar alí).
  - Táboa que continúa noutra páxina SEN repetir a cabeceira: hérdanse os
    papeis das columnas da última táboa con cabeceira da páxina anterior
    só se é a primeira táboa da páxina e ten o MESMO número de columnas
    nas MESMAS posicións (tolerancia `_TOLERANCIA_COLUMNA`). Se a
    maquetación cambia entre páxinas, non se herda nada.
  - Columnas mixtas ("Titular", "Nome/Razón social", "DNI/Razón
    social/Nombre") NON se forzan: poden ser empresas, e taparlas sería
    sobre-anonimizar. Quedan para os patróns e o NER.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

import fitz  # PyMuPDF

PERSOA = "PERSOA"
DOCUMENTO = "DOCUMENTO"
# Columna mixta ("Propietario", "Titular"): pode ser unha persoa, unha empresa
# ou un organismo. Non se forza: cada anaco da cela (separados por ";") só se
# toma por persoa se ten forma de nome do INE (ver `ner._entidades_de_celas`).
# BOE-B-2025-27849 (lote 4, FUGA): os titulares partidos en liñas quedaban á vista.
MIXTA = "MIXTA"
# A propia cela de cabeceira dunha desas columnas: é un rótulo coñecido, e
# o NER tomaba "Persoa" de "Persoa interesada/DNI" por un nome.
CABECEIRA = "CABECEIRA"


@dataclass
class CelaDatoPersoal:
    """Cela dunha columna de dato persoal. `pezas` son intervalos
    [inicio, fin) no texto da páxina (locais en `pdf_estrutura._PaxinaPdf`,
    globais en `contexto["celas_datos_persoais"]`): normalmente un só, pero
    se a orde de lectura mestura a cela con outra columna, un por cada
    tramo seguido de palabras. `fila` identifica a fila no documento
    (para unir "1º apelido | 2º apelido | Nome" da mesma persoa)."""
    tipo: str
    pezas: list = field(default_factory=list)
    fila: int = 0


def _normalizar_cabeceira(texto: str) -> str:
    sen_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    texto = sen_acentos.lower().replace("(*)", "").replace("*", "")
    texto = re.sub(r"\s+", " ", texto).strip(" :.")
    return re.sub(r"(?<=[a-z])\d$", "", texto)  # chamada de nota ao pé ("NOME/RAZÓN SOCIAL5")


# Cabeceiras EXACTAS (tras normalizar): unha cabeceira que só CONTÉN a
# palabra ("Nome da parcela", "DNI/NIE da persoa representante" -- un
# formulario baleiro) non vale.
_CABECEIRAS_PERSOA = frozenset("""
apellidos y nombre|apellidos y nombres|apellidos, nombre|apellidos nombre|nombre y apellidos|nombre completo
apelidos e nome|apelidos, nome|nome e apelidos|nome completo
nombre|nome|apellidos|apelidos
primer apellido|segundo apellido|1er apellido|1o apellido|2o apellido|1 apellido|2 apellido
primeiro apelido|segundo apelido|1o apelido|2o apelido|1 apelido|2 apelido
persoa interesada|persona interesada|persoa interesada/dni|persona interesada/dni
""".replace("\n", "|").strip("|").split("|"))

_CABECEIRAS_DOCUMENTO = frozenset("""
dni|nie|nif|nrp|pasaporte
dni/nie|dni/nif|nif/nie|dni/nie/pas|dni/nie/pasaporte|dni/nif/nie|nie/pasaporte|dni/pasaporte|dni/nif/cif
documento de identidad|documento de identidade|documento identidad|documento identidade
""".replace("\n", "|").strip("|").split("|"))


def _clave_documento(normalizada: str) -> str:
    return re.sub(r"[.\s]", "", normalizada)  # "D.N.I." / "DNI / NIE" -> "dni", "dni/nie"


_CABECEIRAS_MIXTAS = frozenset("""
propietario|propietarios|propietario/a|propietaria|propietarios/as|titular|titulares|titular catastral
proprietario|proprietarios|titular/es|titulares catastrales|propietario/titular|interesado|interesados
""".replace("\n", "|").strip("|").split("|"))


def papel_da_cabeceira(texto: str | None, mixtas: bool = False) -> str | None:
    if not texto:
        return None
    normalizada = _normalizar_cabeceira(texto)
    if mixtas and normalizada in _CABECEIRAS_MIXTAS:
        return MIXTA
    if normalizada in _CABECEIRAS_PERSOA:
        return PERSOA
    if _clave_documento(normalizada) in {_clave_documento(c) for c in _CABECEIRAS_DOCUMENTO}:
        return DOCUMENTO
    return None


# Chamada barata antes de `find_tables` (medio segundo por documento de
# media no corpus): sen ningunha destas palabras na páxina non pode haber
# unha cabeceira das de arriba.
_PISTA_CABECEIRA = re.compile(
    r"\b(?:d\.?n\.?i|n\.?i\.?e|n\.?i\.?f|n\.?r\.?p|pasaporte|apell?idos?|apelidos?|nombre|nome|interesad[ao]"
    r"|documento|propietari[oa]s?|titular(?:es)?)\b",
    re.IGNORECASE,
)

_FILAS_CABECEIRA_MAXIMAS = 3  # cabeceira de grupo ("Datos personales") + a real
_TOLERANCIA_COLUMNA = 3.0  # puntos PDF


@dataclass
class _Papeis:
    """Papeis das columnas dunha táboa con cabeceira, para herdalos se a
    táboa continúa na páxina seguinte sen repetila."""
    por_columna: dict  # índice de columna -> PERSOA/DOCUMENTO
    bordos: list  # x0 de cada columna


def _bordos_columnas(taboa) -> list:
    """x0 de cada columna, da primeira fila que teña tódalas celas."""
    for fila in taboa.rows:
        if all(cela is not None for cela in fila.cells):
            return [cela[0] for cela in fila.cells]
    return []


def _mesmas_columnas(a: list, b: list) -> bool:
    return len(a) == len(b) and bool(a) and all(abs(x - y) <= _TOLERANCIA_COLUMNA for x, y in zip(a, b))


def _papeis_da_taboa(taboa, textos: list) -> tuple:
    """(papeis por columna, primeira fila de datos, fila da cabeceira ou
    None se non está dentro da táboa). Busca a cabeceira nas
    primeiras filas; se a táboa trae a cabeceira fóra (`header.external`,
    texto enriba da táboa), tamén a mira alí."""
    for i, fila in enumerate(textos[:_FILAS_CABECEIRA_MAXIMAS]):
        papeis = {c: p for c, p in ((c, papel_da_cabeceira(t, mixtas=True)) for c, t in enumerate(fila)) if p}
        if papeis:
            return papeis, i + 1, i
    if taboa.header.external:
        papeis = {c: p for c, p in ((c, papel_da_cabeceira(t, mixtas=True)) for c, t in enumerate(taboa.header.names)) if p}
        if papeis:
            return papeis, 0, None
    return {}, 0, None


def _centro_dentro(rect: tuple, caixa: "fitz.Rect") -> bool:
    x = (rect[0] + rect[2]) / 2
    y = (rect[1] + rect[3]) / 2
    return caixa.x0 <= x <= caixa.x1 and caixa.y0 <= y <= caixa.y1


def _pezas_da_cela(palabras: list, caixa: "fitz.Rect") -> list:
    """Intervalos do texto da páxina que ocupan as palabras da cela: un por
    cada tramo de palabras SEGUIDAS na orde de lectura."""
    indices = [i for i, p in enumerate(palabras) if _centro_dentro(p.rect, caixa)]
    pezas = []
    for i in indices:
        if pezas and pezas[-1][2] == i - 1:
            pezas[-1] = (pezas[-1][0], palabras[i].fin, i)
        else:
            pezas.append((palabras[i].inicio, palabras[i].fin, i))
    return [(inicio, fin) for inicio, fin, _ in pezas]


def celas_da_paxina(pagina: "fitz.Page", texto: str, palabras: list, herdados: _Papeis | None,
                    primeira_fila: int) -> tuple:
    """Devolve (celas, papeis_para_a_seguinte_paxina, filas_usadas).
    `palabras` son as `_PalabraPaxina` da páxina (offsets locais)."""
    if pagina.rotation or (herdados is None and not _PISTA_CABECEIRA.search(texto)):
        return [], None, 0
    try:
        taboas = pagina.find_tables().tables
    except Exception:  # noqa: BLE001 -- unha táboa rara nunca pode tumbar a carga do PDF
        return [], None, 0
    taboas = sorted(taboas, key=lambda t: (t.bbox[1], t.bbox[0]))

    celas = []
    ultimos_papeis = None
    fila_id = primeira_fila
    for n, taboa in enumerate(taboas):
        textos = taboa.extract()
        papeis, primeira_de_datos, fila_cabeceira = _papeis_da_taboa(taboa, textos)
        bordos = _bordos_columnas(taboa)
        if not papeis and n == 0 and herdados is not None and _mesmas_columnas(bordos, herdados.bordos):
            papeis, primeira_de_datos = herdados.por_columna, 0
        if not papeis:
            ultimos_papeis = None  # a táboa que pode continuar na seguinte páxina é a ÚLTIMA
            continue
        ultimos_papeis = _Papeis(papeis, bordos)
        if fila_cabeceira is not None:
            cabeceira = taboa.rows[fila_cabeceira]
            for columna in papeis:
                if columna < len(cabeceira.cells) and cabeceira.cells[columna] is not None:
                    pezas = _pezas_da_cela(palabras, fitz.Rect(cabeceira.cells[columna]))
                    if pezas:
                        celas.append(CelaDatoPersoal(CABECEIRA, pezas, 0))
        for fila in taboa.rows[primeira_de_datos:]:
            fila_id += 1
            for columna, papel in papeis.items():
                if columna >= len(fila.cells) or fila.cells[columna] is None:
                    continue
                pezas = _pezas_da_cela(palabras, fitz.Rect(fila.cells[columna]))
                if pezas:
                    celas.append(CelaDatoPersoal(papel, pezas, fila_id))
    return celas, ultimos_papeis, fila_id - primeira_fila
