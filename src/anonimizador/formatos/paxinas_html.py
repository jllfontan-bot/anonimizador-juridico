"""Páxinas web gardadas (.html, .htm) a Markdown, SEN anonimizar.

Pensado para as páxinas do BOE e do DOG gardadas: títulos, listas, táboas e
ligazóns; fóra menús, cabeceiras e pés de páxina, scripts e estilos.

Que entra e que non (ver `ESCONDITES.md`):
  - Entra: o texto visible do contido principal (`<main>`, o `#textoxslt` do
    BOE ou, se non hai, todo o corpo sen o lixo da páxina), as ligazóns
    (`[texto](url)`) e o texto alternativo das imaxes.
  - Non entra: comentarios HTML, `<head>` (metadatos, autor, descrición),
    scripts, estilos, `noscript`, elementos agochados (`hidden`,
    `display:none`, `visibility:hidden`, `input type=hidden`), formularios,
    atributos `title`, `data-*` e calquera outro atributo; as imaxes, nin o
    seu URL nin o seu contido en base64.
"""

from __future__ import annotations

import re
import warnings
from pathlib import Path

from bs4 import BeautifulSoup, Comment
from markdownify import MarkdownConverter

from ._comun import Conversion, _escapar_cela, marca_imaxe, t, taboa_ou_liñas

FORMATOS = (".html", ".htm")

_LIXO = ("script", "style", "noscript", "template", "iframe", "svg", "canvas", "object", "embed",
         "nav", "aside", "dialog", "select", "textarea", "button", "input", "option", "datalist",
         "head")
_ROLES_LIXO = {"navigation", "banner", "contentinfo", "complementary", "search"}
# Clases/ids de lixo corrente, só en contedores xenéricos (nunca en celas).
_CLASES_LIXO = {"menu", "navbar", "breadcrumb", "breadcrumbs", "cookies", "cookie-banner",
                "sidebar", "skip-link"}
_CONTEDORES_XENERICOS = ("div", "ul", "section")
# Menús e pés concretos do BOE (boe.es) e do DOG (xunta.gal): só nomes exactos,
# nunca fragmentos, para non levar por diante contido doutras webs.
_CLASES_LIXO |= {"banda-menu", "franjaMigas", "logosInicio", "selector-idioma", "filtros", "pie",
                 "menuPie", "migas", "zonaNavegacion", "selectorIdioma", "selectorIdiomaMenu",
                 "menuPrincipal", "opciones-menu", "loggin-container", "anuncios-laterales",
                 "lista-boletines", "box-color-gris", "menu-footer"}
# Elementos de lixo en calquera etiqueta: botón de audio (ReadSpeaker, no DOG),
# ligazón «Subir» e selector de apartados da lei consolidada (BOE).
_CLASES_LIXO_CALQUERA = {"rs_skip", "rsbtn", "linkSubir", "marcadores"}
_AGOCHADO = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.I)
_ATRIBUTOS_QUE_QUEDAN = {"href", "colspan", "rowspan", "start"}


def a_markdown(ruta: str) -> str:
    return convertir(ruta).markdown


def _e_lixo(tag) -> bool:
    if tag.name in _LIXO or tag.has_attr("hidden"):
        return True
    if _AGOCHADO.search(tag.get("style") or ""):
        return True
    if (tag.get("role") or "") in _ROLES_LIXO:
        return True
    if tag.name in ("header", "footer") and tag.find_parent(["article", "main", "section"]) is None:
        return True
    if _CLASES_LIXO_CALQUERA & set(tag.get("class") or []):
        return True
    if tag.name in _CONTEDORES_XENERICOS:
        clases = set(tag.get("class") or []) | {tag.get("id") or ""}
        if clases & _CLASES_LIXO:
            return True
    return False


def _contido_principal(sopa):
    mains = sopa.find_all("main") or sopa.find_all(attrs={"role": "main"})
    if len(mains) == 1:
        return mains[0]
    boe = sopa.find(id="textoxslt")
    if boe is not None:
        return boe
    return sopa.body or sopa


class _Conversor(MarkdownConverter):
    """As táboas pásanse polo escapado común (`_taboa_md`) en vez do de
    markdownify, que non escapa `|` e tropeza coas aniñadas e as de
    maquetación."""

    def convert_table(self, el, text, *args, **kwargs):
        # As de maquetación xa non chegan aquí (`_desfacer_taboas_de_maquetacion`).
        taboa = taboa_ou_liñas(_filas(el)) if not _e_de_maquetacion(el) else None
        if taboa is None:
            return "\n\n" + text.strip() + "\n\n"
        titulo = el.find("caption")
        previo = f"{_escapar_cela(titulo.get_text(' '))}\n\n" if titulo is not None else ""
        return "\n\n" + previo + taboa + "\n\n"

    def _contido(self, el, text, *args, **kwargs):
        return "\n\n" + text.strip() + "\n\n"

    convert_td = convert_th = _contido

    def convert_tr(self, el, text, *args, **kwargs):
        return text

    convert_thead = convert_tbody = convert_tfoot = convert_caption = convert_tr


def _filas(taboa) -> list:
    """As celas (escapadas) de cada fila da `taboa`, sen as das aniñadas."""
    filas = []
    for tr in taboa.find_all("tr"):
        if tr.find_parent("table") is not taboa:
            continue
        fila = []
        for cela in tr.find_all(["td", "th"], recursive=False):
            fila.append(_escapar_cela(cela.get_text(" ")))
            try:
                extra = min(int(cela.get("colspan", 1)), 50) - 1
            except ValueError:
                extra = 0
            fila.extend([""] * max(extra, 0))
        filas.append(fila)
    return filas


def _e_de_maquetacion(taboa) -> bool:
    """Con táboas dentro e sen cabeceira propia (un calendario de meses, un
    boletín por correo), ou sen dúas filas e dúas columnas con texto."""
    cabeceira_propia = any(c.find_parent("table") is taboa for c in taboa.find_all("th"))
    if taboa.find("table") is not None and not cabeceira_propia:
        return True
    return not _taboa_de_verdade(_filas(taboa))


def _desfacer_taboas_de_maquetacion(raiz) -> None:
    """As táboas de maquetación pasan a bloques normais ANTES de converter:
    dentro dunha cela, markdownify aplana títulos e parágrafos nunha liña.
    Decídese sobre a estrutura orixinal de todas e despois desfanse."""
    de_maquetacion = [t for t in raiz.find_all("table") if _e_de_maquetacion(t)]
    for taboa in de_maquetacion:
        for parte in taboa.find_all(["thead", "tbody", "tfoot", "tr", "td", "th", "caption"]):
            if parte.find_parent("table") is taboa:
                parte.name = "div"
        taboa.name = "div"


def _taboa_de_verdade(filas: list) -> bool:
    con_texto = [f for f in filas if any(f)]
    n_columnas = max((i + 1 for f in con_texto for i, c in enumerate(f) if c), default=0)
    return len(con_texto) >= 2 and n_columnas >= 2


def convertir(ruta: str) -> Conversion:
    return convertir_html(Path(ruta).read_bytes())


def convertir_html(datos: bytes | str, con_titulo: bool = True) -> Conversion:
    """O mesmo ca `convertir`, dende o HTML xa lido (o corpo dun correo).
    Sen `con_titulo`, o `<title>` non se usa coma título."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        sopa = BeautifulSoup(datos, "lxml")
    titulo = " ".join(sopa.title.get_text().split()) if sopa.title else ""

    for comentario in sopa.find_all(string=lambda s: isinstance(s, Comment)):
        comentario.extract()
    for tag in sopa.find_all(True):
        if not tag.decomposed and _e_lixo(tag):
            tag.decompose()
    raiz = _contido_principal(sopa)
    # `form` pode envolver a páxina enteira (ASP.NET): quítase só a etiqueta.
    for tag in raiz.find_all("form"):
        tag.unwrap()

    omitidas = 0
    for imaxe in raiz.find_all("img"):
        marca = marca_imaxe(imaxe.get("alt") or "")
        if marca:
            imaxe.replace_with(marca)
        else:
            imaxe.decompose()
            omitidas += 1
    for ligazon in raiz.find_all("a"):
        href = (ligazon.get("href") or "").strip()
        if not href or href.startswith(("#", "javascript:", "data:")):
            ligazon.unwrap()
    for texto in raiz.find_all(string=True):
        if texto.find_parent(["pre", "code"]) is None:
            texto.replace_with(re.sub(r"\s+", " ", str(texto)))
    for tag in raiz.find_all(True):
        tag.attrs = {k: v for k, v in tag.attrs.items() if k in _ATRIBUTOS_QUE_QUEDAN}

    _desfacer_taboas_de_maquetacion(raiz)
    markdown = _Conversor(heading_style="ATX", bullets="-", newline_style="spaces",
                           escape_asterisks=False, escape_underscores=False).convert_soup(raiz)
    markdown = markdown.replace("\xa0", " ")
    markdown = re.sub(r"[ \t]+\n", "\n", markdown)
    markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()
    if con_titulo and titulo and not any(h.get_text(strip=True) for h in raiz.find_all("h1")):
        # O DOG pon no `<title>` «DOG n - TITULO» e o corpo repite o TITULO: queda só o prefixo.
        cabeza, separador, resto = titulo.partition(" - ")
        if (resto if separador else titulo)[:60] in markdown:
            titulo = cabeza if separador else ""
        if titulo:
            markdown = f"# {titulo}\n\n{markdown}".rstrip()
    avisos = [t("imaxes_omitidas", n=omitidas)] if omitidas else []
    return Conversion(markdown + "\n" if markdown else "", avisos)
