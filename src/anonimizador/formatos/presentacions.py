"""Presentacións (.pptx, .odp) a Markdown, SEN anonimizar.

Unha sección por diapositiva: `## Diapositiva N: Título` (sen os dous puntos
se non ten título), co texto, as listas, as táboas e, ao final, as notas do
orador. As imaxes e os gráficos saen coma marca (`[imaxe]`), nunca o seu
contido.

Que entra e que non (ver `ESCONDITES.md`):
  - Entra: título, texto (tamén de formas agrupadas), táboas, notas do orador
    e o texto alternativo das imaxes.
  - Non entra: diapositivas agochadas (avísase), pés, data e número de
    diapositiva (repítense en todas), metadatos do arquivo (autor,
    comentarios do documento...), comentarios de revisión e o texto dos
    obxectos que non son texto nin táboa (SmartArt, obxectos incrustados).
"""

from __future__ import annotations

from pathlib import Path

from odf import teletype
from odf.namespaces import DRAWNS, PRESENTATIONNS, STYLENS, TABLENS, TEXTNS
from odf.opendocument import load as cargar_odf
from pptx import Presentation
from pptx.enum.shapes import PP_PLACEHOLDER
from pptx.oxml.ns import qn
from pptx.shapes.graphfrm import GraphicFrame
from pptx.shapes.group import GroupShape
from pptx.shapes.picture import Picture

from pptx.text.text import _Run

from . import _odf
from ._comun import (
    Conversion, _escapar_cela, _escapar_liña, ligazon_md, marca_imaxe, t, taboa_ou_liñas,
    url_ligazon,
)

FORMATOS = (".pptx", ".odp")


class _Dia:
    def __init__(self, numero: int):
        self.numero = numero
        self.titulo = ""
        self.bloques: list = []
        self.notas: list = []
        self.imaxes_omitidas = 0


def _imaxe(dia: "_Dia", alt: str) -> None:
    marca = marca_imaxe(alt)
    if marca:
        dia.bloques.append(marca)
    else:
        dia.imaxes_omitidas += 1


def a_markdown(ruta: str) -> str:
    return convertir(ruta).markdown


def convertir(ruta: str) -> Conversion:
    sufixo = Path(ruta).suffix.lower()
    avisos: list = []
    if sufixo == ".pptx":
        dias = _ler_pptx(ruta, avisos)
    elif sufixo == ".odp":
        dias = _ler_odp(ruta, avisos)
    else:
        raise ValueError(f"Formato de presentación non soportado: {sufixo}")
    omitidas = sum(dia.imaxes_omitidas for dia in dias)
    if omitidas:
        avisos.append(t("imaxes_omitidas", n=omitidas))
    seccions = []
    for dia in dias:
        cabeceira = "## " + t("diapositiva", n=dia.numero)
        if dia.titulo:
            cabeceira += ": " + _escapar_liña(dia.titulo)
        partes = [cabeceira] + [b for b in dia.bloques if b]
        if dia.notas:
            partes.append("**" + t("notas_orador") + "**")
            partes.extend(dia.notas)
        seccions.append("\n\n".join(partes))
    return Conversion("\n\n".join(seccions) + "\n" if seccions else "", avisos)


def _liñas(texto: str, sangria: str = "") -> str:
    """Un parágrafo con saltos manuais (\\v, \\n): cada liña escapada e
    unidas por un salto duro de Markdown."""
    liñas = [x.strip() for x in texto.replace("\x0b", "\n").split("\n")]
    return ("  \n" + sangria).join(_escapar_liña(l) if l else "" for l in liñas).strip()


def _paragrafo(texto: str) -> str:
    return _liñas(texto)


def _elemento_lista(texto: str, nivel: int) -> str:
    sangria = "  " * nivel
    return f"{sangria}- " + _liñas(texto, sangria + "  ").lstrip()


def _unha_liña(texto: str) -> str:
    return " ".join(texto.split())


# -- .pptx ------------------------------------------------------------------

_SO_REPETIDOS = (PP_PLACEHOLDER.FOOTER, PP_PLACEHOLDER.DATE, PP_PLACEHOLDER.SLIDE_NUMBER)
_CORPO = (PP_PLACEHOLDER.BODY, PP_PLACEHOLDER.OBJECT)


def _e_lista_pptx(forma, paragrafo) -> bool:
    ppr = paragrafo._p.pPr
    if ppr is not None:
        if ppr.find(qn("a:buNone")) is not None:
            return False
        if any(ppr.find(qn(f"a:{b}")) is not None for b in ("buChar", "buAutoNum", "buBlip")):
            return True
    return forma.is_placeholder and forma.placeholder_format.type in _CORPO


def _texto_pptx_con_ligazons(paragrafo) -> str:
    """O texto do parágrafo (`\\v` nos saltos manuais) con `[texto](url)` nas
    ligazóns web e de correo; as partidas en varios fragmentos únense."""
    partes: list = []  # (URL ou "", texto)
    for fillo in paragrafo._p.content_children:
        url = ""
        if fillo.tag == qn("a:r"):
            url = url_ligazon(_Run(fillo, paragrafo).hyperlink.address)
        if partes and partes[-1][0] == url:
            partes[-1] = (url, partes[-1][1] + fillo.text)
        else:
            partes.append((url, fillo.text))
    return "".join(ligazon_md(texto, url) if url else texto for url, texto in partes)


def _texto_cela_pptx(cela) -> str:
    return "\n".join(_texto_pptx_con_ligazons(p) for p in cela.text_frame.paragraphs)


def _texto_alternativo(forma) -> str:
    valores = forma._element.xpath("./*[1]/p:cNvPr/@descr")
    return _unha_liña(valores[0]) if valores else ""


def _formas_pptx(formas, dia: _Dia, id_titulo) -> None:
    for forma in formas:
        if forma.is_placeholder and forma.placeholder_format.type in _SO_REPETIDOS:
            continue
        if id_titulo is not None and forma.shape_id == id_titulo:
            continue
        if isinstance(forma, GroupShape):
            _formas_pptx(forma.shapes, dia, id_titulo)
        elif isinstance(forma, GraphicFrame):
            if forma.has_table:
                dia.bloques.append(taboa_ou_liñas(
                    [[_escapar_cela(_texto_cela_pptx(c)) for c in fila.cells]
                     for fila in forma.table.rows]))
            elif forma.has_chart:
                dia.bloques.append(t("grafico"))
            else:
                dia.bloques.append(t("obxecto"))
        elif isinstance(forma, Picture) or forma._element.tag == qn("p:pic"):
            _imaxe(dia, _texto_alternativo(forma))
        elif getattr(forma, "has_text_frame", False) and forma.has_text_frame:
            _texto_pptx(forma, dia)


def _texto_pptx(forma, dia: _Dia) -> None:
    lista: list = []
    for paragrafo in forma.text_frame.paragraphs:
        texto = _texto_pptx_con_ligazons(paragrafo)
        if not texto.strip():
            continue
        if _e_lista_pptx(forma, paragrafo):
            lista.append(_elemento_lista(texto, paragrafo.level))
        else:
            if lista:
                dia.bloques.append("\n".join(lista))
                lista = []
            dia.bloques.append(_paragrafo(texto))
    if lista:
        dia.bloques.append("\n".join(lista))


def _ler_pptx(ruta: str, avisos: list) -> list:
    dias = []
    for numero, diapositiva in enumerate(Presentation(ruta).slides, start=1):
        if diapositiva._element.get("show") == "0":
            avisos.append(t("diapositiva_oculta", n=numero))
            continue
        dia = _Dia(numero)
        titulo = diapositiva.shapes.title
        if titulo is not None:
            dia.titulo = _unha_liña(titulo.text_frame.text)
        _formas_pptx(diapositiva.shapes, dia, titulo.shape_id if titulo is not None else None)
        if diapositiva.has_notes_slide:
            cadro = diapositiva.notes_slide.notes_text_frame
            if cadro is not None:
                dia.notas = [_paragrafo(_texto_pptx_con_ligazons(p)) for p in cadro.paragraphs
                             if p.text.strip()]
        dias.append(dia)
    return dias


# -- .odp -------------------------------------------------------------------

_CLASES_REPETIDAS = {"footer", "date-time", "page-number", "header"}


def _clase_odp(no) -> str:
    return no.getAttrNS(PRESENTATIONNS, "class") or ""


def _lista_odp(lista, nivel: int, saida: list) -> None:
    for item in lista.childNodes:
        if not _odf.e_elemento(item, TEXTNS):
            continue
        if item.qname[1] == "list-item" or item.qname[1] == "list-header":
            for fillo in item.childNodes:
                if _odf.e_elemento(fillo, TEXTNS, "list"):
                    _lista_odp(fillo, nivel + 1, saida)
                elif _odf.e_elemento(fillo, TEXTNS, "p") or _odf.e_elemento(fillo, TEXTNS, "h"):
                    texto = _odf.texto_con_ligazons(fillo)
                    if texto.strip():
                        saida.append(_elemento_lista(texto, nivel))


def _texto_odp(contedor, dia_bloques: list, como_lista: bool) -> None:
    lista: list = []

    def baleirar():
        nonlocal lista
        if lista:
            dia_bloques.append("\n".join(lista))
            lista = []

    for fillo in contedor.childNodes:
        if _odf.e_elemento(fillo, TEXTNS, "list"):
            _lista_odp(fillo, 0, lista)
        elif _odf.e_elemento(fillo, TEXTNS, "p") or _odf.e_elemento(fillo, TEXTNS, "h"):
            texto = _odf.texto_con_ligazons(fillo)
            if not texto.strip():
                continue
            if como_lista:
                lista.append(_elemento_lista(texto, 0))
            else:
                baleirar()
                dia_bloques.append(_paragrafo(texto))
    baleirar()


def _formas_odp(pai, dia: _Dia) -> None:
    for fillo in pai.childNodes:
        if not _odf.e_elemento(fillo):
            continue
        espazo, nome = fillo.qname
        if espazo == PRESENTATIONNS:
            continue  # notas, animacións...
        if espazo == TABLENS and nome == "table":
            dia.bloques.append(taboa_ou_liñas(
                [[_escapar_cela(c) for c in f] for f in _odf.ler_taboa(fillo).filas]))
        elif espazo == DRAWNS and nome == "frame":
            _marco_odp(fillo, dia)
        elif espazo == DRAWNS and nome == "g":
            _formas_odp(fillo, dia)
        elif espazo == DRAWNS and nome in ("page-thumbnail", "layer-set", "glue-point"):
            continue
        elif espazo == DRAWNS:
            _texto_odp(fillo, dia.bloques, False)  # formas con texto propio


def _marco_odp(marco, dia: _Dia) -> None:
    clase = _clase_odp(marco)
    if clase in _CLASES_REPETIDAS:
        return
    # Un marco con táboa leva ademais unha imaxe de vista previa: non é unha imaxe.
    con_taboa = any(_odf.e_elemento(f, TABLENS, "table") for f in marco.childNodes)
    for fillo in marco.childNodes:
        if not _odf.e_elemento(fillo):
            continue
        espazo, nome = fillo.qname
        if con_taboa and espazo == DRAWNS and nome == "image":
            continue
        if espazo == DRAWNS and nome == "text-box":
            if clase == "title":
                dia.titulo = _unha_liña(" ".join(_odf.paragrafos(fillo)))
            else:
                _texto_odp(fillo, dia.bloques, clase == "outline")
        elif espazo == TABLENS and nome == "table":
            dia.bloques.append(taboa_ou_liñas(
                [[_escapar_cela(c) for c in f] for f in _odf.ler_taboa(fillo).filas]))
        elif espazo == DRAWNS and nome == "image":
            _imaxe(dia, _alt_odp(marco))
        elif espazo == DRAWNS and nome in ("object", "object-ole", "plugin", "applet", "floating-frame"):
            dia.bloques.append(t("obxecto"))


def _alt_odp(marco) -> str:
    """Texto alternativo dunha imaxe (`svg:desc` do marco)."""
    for fillo in marco.childNodes:
        if _odf.e_elemento(fillo) and fillo.qname[1] == "desc":
            return _unha_liña(teletype.extractText(fillo))
    return ""


def _estilos_de_paxina_oculta(documento) -> set:
    """LibreOffice garda a diapositiva agochada no ESTILO da páxina
    (`presentation:visibility="hidden"` en `style:drawing-page-properties`)."""
    ocultos = set()
    for estilo in documento.automaticstyles.childNodes:
        if not _odf.e_elemento(estilo, STYLENS, "style"):
            continue
        for fillo in estilo.childNodes:
            if (_odf.e_elemento(fillo, STYLENS, "drawing-page-properties")
                    and fillo.getAttrNS(PRESENTATIONNS, "visibility") == "hidden"):
                ocultos.add(estilo.getAttrNS(STYLENS, "name"))
    return ocultos


def _ler_odp(ruta: str, avisos: list) -> list:
    documento = cargar_odf(ruta)
    estilos_ocultos = _estilos_de_paxina_oculta(documento)
    dias = []
    numero = 0
    for pagina in documento.presentation.childNodes:
        if not _odf.e_elemento(pagina, DRAWNS, "page"):
            continue
        numero += 1
        if pagina.getAttrNS(DRAWNS, "style-name") in estilos_ocultos:
            avisos.append(t("diapositiva_oculta", n=numero))
            continue
        dia = _Dia(numero)
        _formas_odp(pagina, dia)
        for fillo in pagina.childNodes:
            if _odf.e_elemento(fillo, PRESENTATIONNS, "notes"):
                for marco in fillo.childNodes:
                    if _odf.e_elemento(marco, DRAWNS, "frame") and _clase_odp(marco) == "notes":
                        notas: list = []
                        for caixa in marco.childNodes:
                            if _odf.e_elemento(caixa, DRAWNS, "text-box"):
                                _texto_odp(caixa, notas, False)
                        dia.notas.extend(notas)
        dias.append(dia)
    return dias
