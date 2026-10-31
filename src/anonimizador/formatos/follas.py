"""Follas de cálculo (.xlsx, .ods) e .csv a Markdown, SEN anonimizar.

Cada folla é unha táboa Markdown co nome da folla de título (`## Nome`); un
.csv non leva título (o título é o nome do arquivo). A primeira fila fai de
cabeceira.

Que entra e que non (ver `ESCONDITES.md`):
  - Entra: o texto de todas as celas que se ven, os comentarios das celas
    (sen autor nin data) e, nas fórmulas, o valor que gardou o programa (se
    non o gardou, a fórmula).
  - Non entra: follas agochadas, filas e columnas agochadas (tamén as
    agochadas polo filtro), metadatos do arquivo (autor, empresa,
    propiedades...), imaxes, gráficos, ligazóns e formato das celas.
  Cada cousa deixada fóra avísase en `Conversion.avisos`.

Follas grandes (punto 5.6 do estudo): por riba de `max_filas`, avisa e, se
se dá `dir_csv`, a folla vai a un .csv á parte e no Markdown queda só a
cabeceira (para saber as columnas). Sen `dir_csv` a táboa sae enteira: nunca
se perden filas calladas.
"""

from __future__ import annotations

import csv
import datetime
import re
from pathlib import Path

import openpyxl
from odf.namespaces import STYLENS, TABLENS
from odf.opendocument import load as cargar_odf

from . import _odf
from ._comun import (
    Conversion, _escapar_cela, _escapar_liña, formatar_data, formatar_numero, ligazon_md,
    t, taboa_ou_liñas, url_ligazon,
)
from .formato_numero import formatar as formatar_con_formato

FORMATOS = (".xlsx", ".ods", ".csv")
MAX_FILAS = 500
# Un .csv con máis columnas ca isto non é lexible coma táboa Markdown: queda tal cal.
MAX_COLUMNAS_TABOA = 20


class _Folla:
    def __init__(self, nome, filas, notas=()):
        self.nome = nome  # None: sen título (.csv)
        self.filas = filas  # listas de str, sen escapar
        self.notas = list(notas)  # (referencia, texto)
        self.literal = None  # .csv: o texto orixinal, para deixalo tal cal se é moi ancho


def a_markdown(ruta: str, **opcions) -> str:
    return convertir(ruta, **opcions).markdown


def convertir(ruta: str, *, max_filas: int = MAX_FILAS, dir_csv: str | None = None) -> Conversion:
    sufixo = Path(ruta).suffix.lower()
    avisos: list = []
    if sufixo == ".xlsx":
        follas = _ler_xlsx(ruta, avisos)
    elif sufixo == ".ods":
        follas = _ler_ods(ruta, avisos)
    elif sufixo == ".csv":
        follas = _ler_csv(ruta)
    else:
        raise ValueError(f"Formato de folla non soportado: {sufixo}")

    ficheiros: list = []
    bloques = []
    for folla in follas:
        folla.filas = _sen_columnas_finais(folla.filas)
        if not folla.filas and not folla.notas:
            continue
        if folla.nome is not None:
            bloques.append("## " + _escapar_liña(folla.nome))
        if len(folla.filas) > max_filas:
            if dir_csv is None:
                avisos.append(t("folla_grande", nome=folla.nome or Path(ruta).name,
                                n=len(folla.filas), max=max_filas))
                bloques.append(_taboa_ou_literal(folla))
            else:
                csv_aparte = _gardar_csv(folla, ruta, dir_csv, ficheiros)
                avisos.append(t("aviso_a_csv", nome=folla.nome or Path(ruta).name,
                                n=len(folla.filas), ficheiro=csv_aparte.name))
                columnas = ", ".join(c for c in map(_escapar_cela, folla.filas[0]) if c)
                bloques.append(t("folla_a_csv", n=len(folla.filas), m=len(folla.filas[0]),
                                 ficheiro=csv_aparte.name, columnas=columnas))
        else:
            bloques.append(_taboa_ou_literal(folla))
        if folla.notas:
            bloques.append(t("comentarios") + "\n"
                           + "\n".join(f"- {ref}: {_escapar_cela(texto)}" for ref, texto in folla.notas))
    markdown = "\n\n".join(b for b in bloques if b)
    return Conversion(markdown + "\n" if markdown else "", avisos, ficheiros)


def _taboa_ou_literal(folla: _Folla) -> str:
    """Táboa Markdown; un .csv moi ancho vai tal cal nun bloque de código."""
    if folla.literal is not None and folla.filas and len(folla.filas[0]) > MAX_COLUMNAS_TABOA:
        valla = "```"
        while valla in folla.literal:
            valla += "`"
        return f"{valla}csv\n{folla.literal.strip()}\n{valla}"
    return taboa_ou_liñas(_escapar_filas(folla.filas))


def _escapar_filas(filas: list) -> list:
    return [[_escapar_cela(c) for c in fila] for fila in filas]


def _sen_columnas_finais(filas: list) -> list:
    filas = [f for f in filas if any(f)]
    n = max((i + 1 for f in filas for i, c in enumerate(f) if c), default=0)
    return [(f + [""] * n)[:n] for f in filas]


def _gardar_csv(folla: _Folla, ruta: str, dir_csv: str, ficheiros: list) -> Path:
    base = f"{Path(ruta).stem}.{re.sub(r'[^\w.-]+', '_', folla.nome or 'datos')}"
    destino = Path(dir_csv) / f"{base}.csv"
    n = 2
    while str(destino) in ficheiros:
        destino = Path(dir_csv) / f"{base}-{n}.csv"
        n += 1
    with open(destino, "w", newline="", encoding="utf-8") as saida:
        csv.writer(saida).writerows(folla.filas)
    ficheiros.append(str(destino))
    return destino


# -- .xlsx ------------------------------------------------------------------

def _valor_xlsx(valor, formato: str = "General") -> str:
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "TRUE" if valor else "FALSE"
    if isinstance(valor, (datetime.datetime, datetime.date, datetime.time)):
        return formatar_data(valor)
    if isinstance(valor, (int, float)):
        return formatar_con_formato(valor, formato) or formatar_numero(valor)
    if hasattr(valor, "text"):  # fórmula matricial
        return str(valor.text or "")
    return str(valor)


_HYPERLINK = re.compile(r'=\s*HYPERLINK\(\s*"([^"]*)"\s*(?:[,;]\s*"([^"]*)"\s*)?\)', re.I)


def _con_ligazon_xlsx(cela, texto: str) -> str:
    """Ligazón da cela (`hyperlink`) ou da fórmula `=HYPERLINK("url";"texto")`."""
    url = url_ligazon(cela.hyperlink.target if cela.hyperlink is not None else None)
    if not url and isinstance(cela.value, str):
        formula = _HYPERLINK.match(cela.value)
        url = url_ligazon(formula.group(1)) if formula else ""
        if url and texto.startswith("="):  # sen valor gardado: o rótulo da fórmula
            texto = formula.group(2) or ""
    return ligazon_md(texto, url) if url else texto


def _columnas_ocultas_xlsx(folla) -> set:
    ocultas = set()
    for dimension in folla.column_dimensions.values():
        if dimension.hidden and dimension.min:
            ocultas.update(range(dimension.min, (dimension.max or dimension.min) + 1))
    return ocultas


def _ler_xlsx(ruta: str, avisos: list) -> list:
    # Dúas lecturas: os valores que gardou o programa e as fórmulas (para
    # as que nunca se calcularon, coma as escritas por un script).
    con_valores = openpyxl.load_workbook(ruta, data_only=True)
    con_formulas = openpyxl.load_workbook(ruta)
    follas = []
    for folla in con_formulas.worksheets:
        if folla.sheet_state != "visible":
            avisos.append(t("folla_oculta", nome=folla.title))
            continue
        valores = con_valores[folla.title]
        columnas_ocultas = _columnas_ocultas_xlsx(folla)
        filas, notas = [], []
        n_filas_ocultas = 0
        for celas in folla.iter_rows():
            if not celas:
                continue
            if folla.row_dimensions[celas[0].row].hidden:
                if any(c.value is not None for c in celas):
                    n_filas_ocultas += 1
                continue
            fila = []
            for cela in celas:
                if cela.column in columnas_ocultas:
                    continue
                valor = valores[cela.coordinate].value
                fila.append(_con_ligazon_xlsx(
                    cela, _valor_xlsx(cela.value if valor is None else valor, cela.number_format)))
                if cela.comment is not None and cela.comment.text:
                    notas.append((cela.coordinate, cela.comment.text))
            filas.append(fila)
        if n_filas_ocultas:
            avisos.append(t("filas_ocultas", nome=folla.title, n=n_filas_ocultas))
        if columnas_ocultas and any(c.value is not None for fila in folla.iter_rows()
                                    for c in fila if c.column in columnas_ocultas):
            avisos.append(t("columnas_ocultas", nome=folla.title, n=len(
                [c for c in columnas_ocultas if c <= folla.max_column])))
        follas.append(_Folla(folla.title, filas, notas))
    return follas


# -- .ods -------------------------------------------------------------------

def _follas_ocultas_ods(documento) -> set:
    """Nomes dos estilos de folla con `table:display="false"`."""
    ocultos = set()
    for contedor in (documento.automaticstyles, documento.styles):
        for estilo in contedor.childNodes:
            if not _odf.e_elemento(estilo) or estilo.qname[1] != "style":
                continue
            if estilo.getAttrNS(STYLENS, "family") != "table":
                continue
            for fillo in estilo.childNodes:
                if _odf.e_elemento(fillo) and fillo.qname[1] == "table-properties":
                    if fillo.getAttrNS(TABLENS, "display") == "false":
                        ocultos.add(estilo.getAttrNS(STYLENS, "name"))
    return ocultos


def _ler_ods(ruta: str, avisos: list) -> list:
    documento = cargar_odf(ruta)
    estilos_ocultos = _follas_ocultas_ods(documento)
    follas = []
    for taboa in documento.spreadsheet.childNodes:
        if not _odf.e_elemento(taboa, TABLENS, "table"):
            continue
        nome = taboa.getAttrNS(TABLENS, "name") or ""
        if taboa.getAttrNS(TABLENS, "style-name") in estilos_ocultos:
            avisos.append(t("folla_oculta", nome=nome))
            continue
        lida = _odf.ler_taboa(taboa)
        if lida.filas_ocultas:
            avisos.append(t("filas_ocultas", nome=nome, n=lida.filas_ocultas))
        if lida.columnas_ocultas:
            avisos.append(t("columnas_ocultas", nome=nome, n=lida.columnas_ocultas))
        follas.append(_Folla(nome, lida.filas, lida.notas))
    return follas


# -- .csv -------------------------------------------------------------------

_DELIMITADORES = ";,\t|"


def _decodificar(datos: bytes) -> str:
    for codificacion in ("utf-8-sig", "cp1252"):
        try:
            return datos.decode(codificacion)
        except UnicodeDecodeError:
            pass
    return datos.decode("latin-1")


def _delimitador(texto: str) -> str:
    """O delimitador co que as primeiras liñas dan máis veces o mesmo
    número (>1) de campos."""
    mostra = texto.splitlines()[:30]
    mellor, puntuacion = ",", (0, 0)
    for candidato in _DELIMITADORES:
        n_campos = [len(f) for f in csv.reader(mostra, delimiter=candidato)]
        frecuente = max(set(n_campos), key=n_campos.count, default=1)
        if frecuente < 2:
            continue
        actual = (n_campos.count(frecuente), frecuente)
        if actual > puntuacion:
            mellor, puntuacion = candidato, actual
    return mellor


def _ler_csv(ruta: str) -> list:
    texto = _decodificar(Path(ruta).read_bytes())
    if not texto.strip():
        return []
    csv.field_size_limit(2 ** 30)
    filas = list(csv.reader(texto.splitlines(), delimiter=_delimitador(texto)))
    folla = _Folla(None, filas)
    folla.literal = texto
    return [folla]
