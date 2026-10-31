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

from ._comun import Conversion, _escapar_cela, marca_imaxe, taboa_ou_liñas

FORMATOS = (".html", ".htm")

_LIXO = ("script", "style", "noscript", "template", "iframe", "svg", "canvas", "object", "embed",
         "nav", "aside", "dialog", "select", "textarea", "button", "input", "option", "datalist",
         "head")
_ROLES_LIXO = {"navigation", "banner", "contentinfo", "complementary", "search"}
# Clases/ids de lixo corrente, só en contedores xenéricos (nunca en celas).
_CLASES_LIXO = {"menu", "navbar", "breadcrumb", "breadcrumbs", "cookies", "cookie-banner",
                "sidebar", "skip-link"}
_CONTEDORES_XENERICOS = ("div", "ul", "section")
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
        filas = []
        for tr in el.find_all("tr"):
            if tr.find_parent("table") is not el:
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
        taboa = None
        if _taboa_de_verdade(filas):
            taboa = taboa_ou_liñas(filas)
        if taboa is None:
            # Taboa de maquetación: o seu contido, coma parágrafos normais.
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


def _taboa_de_verdade(filas: list) -> bool:
    con_texto = [f for f in filas if any(f)]
    n_columnas = max((i + 1 for f in con_texto for i, c in enumerate(f) if c), default=0)
    return len(con_texto) >= 2 and n_columnas >= 2


def convertir(ruta: str) -> Conversion:
    datos = Path(ruta).read_bytes()
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

    for imaxe in raiz.find_all("img"):
        imaxe.replace_with(marca_imaxe(imaxe.get("alt") or ""))
    for ligazon in raiz.find_all("a"):
        href = (ligazon.get("href") or "").strip()
        if not href or href.startswith(("#", "javascript:", "data:")):
            ligazon.unwrap()
    for texto in raiz.find_all(string=True):
        if texto.find_parent(["pre", "code"]) is None:
            texto.replace_with(re.sub(r"\s+", " ", str(texto)))
    for tag in raiz.find_all(True):
        tag.attrs = {k: v for k, v in tag.attrs.items() if k in _ATRIBUTOS_QUE_QUEDAN}

    markdown = _Conversor(heading_style="ATX", bullets="-", newline_style="spaces",
                           escape_asterisks=False, escape_underscores=False).convert_soup(raiz)
    markdown = markdown.replace("\xa0", " ")
    markdown = re.sub(r"[ \t]+\n", "\n", markdown)
    markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()
    if titulo and not raiz.find("h1"):
        markdown = f"# {titulo}\n\n{markdown}".rstrip()
    return Conversion(markdown + "\n" if markdown else "")
