"""Lectura de táboas OpenDocument (.ods e as táboas dun .odp)."""

from __future__ import annotations

from dataclasses import dataclass, field

from odf.element import Element
from odf.text import A
from odf.namespaces import OFFICENS, TABLENS, TEXTNS, XLINKNS
from odf import teletype

from ..lectura import _texto_paragrafo_odt
from ._comun import con_ligazons, formatar_numero, url_ligazon

# Un .ods pode traer 1.048.576 filas baleiras repetidas e 16.384 columnas:
# as baleiras non se expanden e as repeticións limítanse.
_MAX_REPETICIONS = 1024
_CONTEDORES = {"table-columns", "table-header-columns", "table-column-group",
               "table-rows", "table-header-rows", "table-row-group"}
_OCULTO = ("collapse", "filter")



@dataclass
class TaboaOdf:
    filas: list
    notas: list = field(default_factory=list)  # (referencia "B2", texto)
    filas_ocultas: int = 0
    columnas_ocultas: int = 0


def e_elemento(no, espazo: str | None = None, nome: str | None = None) -> bool:
    return (isinstance(no, Element) and (espazo is None or no.qname[0] == espazo)
            and (nome is None or no.qname[1] == nome))


def letra_columna(n: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    letras = ""
    n += 1
    while n:
        n, resto = divmod(n - 1, 26)
        letras = chr(65 + resto) + letras
    return letras


def _ligazons(paragrafo) -> list:
    """(texto, URL limpo) das ligazóns `text:a` dun parágrafo."""
    saida = []
    for a in paragrafo.getElementsByType(A):
        url = url_ligazon(a.getAttrNS(XLINKNS, "href"))
        if url:
            saida.append((teletype.extractText(a), url))
    return saida


def texto_con_ligazons(paragrafo) -> str:
    """O texto do parágrafo con `[texto](url)` nas ligazóns web e de correo."""
    return con_ligazons(_texto_paragrafo_odt(paragrafo), _ligazons(paragrafo))


def paragrafos(nodo) -> list:
    """Texto de cada parágrafo/título (e das listas) dentro de `nodo`, sen
    entrar nas anotacións (os comentarios das celas)."""
    saida = []
    for fillo in nodo.childNodes:
        if e_elemento(fillo, TEXTNS, "p") or e_elemento(fillo, TEXTNS, "h"):
            saida.append(texto_con_ligazons(fillo))
        elif e_elemento(fillo, TEXTNS, "list"):
            saida.append(" ".join(teletype.extractText(fillo).split()))
    return saida


def _elementos(taboa, nome: str):
    """Filas ou columnas dunha táboa, tamén as que van dentro de grupos e
    cabeceiras, sen baixar ás celas (táboas aniñadas)."""
    for fillo in taboa.childNodes:
        if e_elemento(fillo, TABLENS, nome):
            yield fillo
        elif e_elemento(fillo, TABLENS) and fillo.qname[1] in _CONTEDORES:
            yield from _elementos(fillo, nome)


def _repeticions(no, atributo: str) -> int:
    try:
        return max(1, int(no.getAttrNS(TABLENS, atributo) or 1))
    except ValueError:
        return 1


def _valor_cela(cela) -> str:
    """O texto que se ve na cela (`1.234,50 €`); se non hai, o valor."""
    texto = " ".join(" ".join(paragrafos(cela)).split())
    if texto:
        return texto
    tipo = cela.getAttrNS(OFFICENS, "value-type")
    if tipo in ("float", "percentage", "currency"):
        try:
            return formatar_numero(float(cela.getAttrNS(OFFICENS, "value")))
        except (TypeError, ValueError):
            return ""
    if tipo == "date":
        return (cela.getAttrNS(OFFICENS, "date-value") or "").replace("T00:00:00", "")
    if tipo == "boolean":
        return "TRUE" if cela.getAttrNS(OFFICENS, "boolean-value") == "true" else "FALSE"
    if tipo == "time":
        return cela.getAttrNS(OFFICENS, "time-value") or ""
    if tipo == "string":
        return cela.getAttrNS(OFFICENS, "string-value") or ""
    return ""


def _comentario_cela(cela) -> str:
    """Texto do comentario da cela (sen autor nin data)."""
    for fillo in cela.childNodes:
        if e_elemento(fillo, OFFICENS, "annotation"):
            return " ".join(" ".join(paragrafos(fillo)).split())
    return ""


def ler_taboa(taboa) -> TaboaOdf:
    ocultas, posicion = set(), 0
    for columna in _elementos(taboa, "table-column"):
        repeticions = min(_repeticions(columna, "number-columns-repeated"), 16384)
        if columna.getAttrNS(TABLENS, "visibility") in _OCULTO:
            ocultas.update(range(posicion, posicion + repeticions))
        posicion += repeticions

    resultado = TaboaOdf(filas=[], columnas_ocultas=len(ocultas))
    numero_fila = 0
    for fila in _elementos(taboa, "table-row"):
        repeticions = _repeticions(fila, "number-rows-repeated")
        textos, comentarios = [], []
        for cela in fila.childNodes:
            if not e_elemento(cela, TABLENS):
                continue
            if cela.qname[1] not in ("table-cell", "covered-table-cell"):
                continue
            veces = min(_repeticions(cela, "number-columns-repeated"), _MAX_REPETICIONS)
            if cela.qname[1] == "covered-table-cell":
                texto, comentario = "", ""
            else:
                texto, comentario = _valor_cela(cela), _comentario_cela(cela)
            if comentario:
                comentarios.append((len(textos), comentario))
            textos.extend([texto] * veces)
        if not any(textos) and not comentarios:
            numero_fila += repeticions
            continue
        if fila.getAttrNS(TABLENS, "visibility") in _OCULTO:
            resultado.filas_ocultas += repeticions
            numero_fila += repeticions
            continue
        for k in range(min(repeticions, _MAX_REPETICIONS)):
            resultado.filas.append([c for i, c in enumerate(textos) if i not in ocultas])
            if k == 0:
                for i, comentario in comentarios:
                    if i not in ocultas:
                        resultado.notas.append((f"{letra_columna(i)}{numero_fila + 1}", comentario))
        numero_fila += repeticions
    return resultado
