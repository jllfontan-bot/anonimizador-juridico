"""Pezas comúns dos lectores de formatos novos (`formatos/`)."""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field

from .. import idioma
# O escapado é o MESMO ca na copia en Markdown do documento anonimizado.
from ..copia_md import _escapar_cela, _escapar_liña, _taboa_md  # noqa: F401


@dataclass
class Conversion:
    """Resultado dun lector: o Markdown, os avisos para a persoa (cousas que
    se deixaron fóra ou que convén saber) e os ficheiros que se escribiron
    á parte (follas moi grandes en .csv)."""
    markdown: str
    avisos: list = field(default_factory=list)
    ficheiros: list = field(default_factory=list)


_TEXTOS = {
    "es": {
        "folla_oculta": "Hoja oculta omitida: «{nome}».",
        "filas_ocultas": "Hoja «{nome}»: {n} filas ocultas omitidas.",
        "columnas_ocultas": "Hoja «{nome}»: {n} columnas ocultas omitidas.",
        "folla_grande": ("La hoja «{nome}» tiene {n} filas (más de {max}): una tabla Markdown tan "
                         "grande gasta muchos tokens; conviene dejarla en un .csv aparte."),
        "folla_a_csv": ("Hoja de {n} filas y {m} columnas, guardada aparte en «{ficheiro}» "
                        "(una tabla tan grande gasta muchos tokens). Columnas: {columnas}."),
        "aviso_a_csv": "La hoja «{nome}» ({n} filas) se ha guardado aparte en «{ficheiro}».",
        "comentarios": "Comentarios de celda:",
        "diapositiva": "Diapositiva {n}",
        "diapositiva_oculta": "Diapositiva {n} oculta omitida.",
        "notas_orador": "Notas del orador:",
        "imaxes_omitidas": "{n} imágenes sin texto alternativo omitidas.",
        "imaxe_alt": "[imagen: {alt}]",
        "grafico": "[gráfico]",
        "obxecto": "[objeto no convertido]",
        "correo_de": "De",
        "correo_para": "Para",
        "correo_cc": "CC",
        "correo_cco": "CCO",
        "correo_responder_a": "Responder a",
        "correo_data": "Fecha",
        "correo_anexos": "Adjuntos:",
        "correo_anexos_sen_converter": ("{n} adjuntos sin convertir (se listan al final del .md): "
                                        "guárdalos y conviértelos aparte."),
        "correo_imaxes_incrustadas": "{n} imágenes incrustadas en el correo omitidas (firmas, logotipos...).",
    },
    "gl": {
        "folla_oculta": "Folla agochada omitida: «{nome}».",
        "filas_ocultas": "Folla «{nome}»: {n} filas agochadas omitidas.",
        "columnas_ocultas": "Folla «{nome}»: {n} columnas agochadas omitidas.",
        "folla_grande": ("A folla «{nome}» ten {n} filas (máis de {max}): unha táboa Markdown tan "
                         "grande gasta moitos tokens; convén deixala nun .csv á parte."),
        "folla_a_csv": ("Folla de {n} filas e {m} columnas, gardada á parte en «{ficheiro}» "
                        "(unha táboa tan grande gasta moitos tokens). Columnas: {columnas}."),
        "aviso_a_csv": "A folla «{nome}» ({n} filas) gardouse á parte en «{ficheiro}».",
        "comentarios": "Comentarios de cela:",
        "diapositiva": "Diapositiva {n}",
        "diapositiva_oculta": "Diapositiva {n} agochada omitida.",
        "notas_orador": "Notas do orador:",
        "imaxes_omitidas": "{n} imaxes sen texto alternativo omitidas.",
        "imaxe_alt": "[imaxe: {alt}]",
        "grafico": "[gráfico]",
        "obxecto": "[obxecto non convertido]",
        "correo_de": "De",
        "correo_para": "Para",
        "correo_cc": "Cc",
        "correo_cco": "Cco",
        "correo_responder_a": "Responder a",
        "correo_data": "Data",
        "correo_anexos": "Anexos:",
        "correo_anexos_sen_converter": ("{n} anexos sen converter (lístanse ao final do .md): "
                                        "gárdaos e convérteos á parte."),
        "correo_imaxes_incrustadas": "{n} imaxes incrustadas no correo omitidas (sinaturas, logotipos...).",
    },
}


def t(clave: str, **valores) -> str:
    return _TEXTOS[idioma.actual()][clave].format(**valores)


def formatar_numero(valor: float) -> str:
    """3.0 -> "3"; 0.25 -> "0.25"."""
    if valor == int(valor) and abs(valor) < 1e15:
        return str(int(valor))
    return repr(valor)


def formatar_data(valor) -> str:
    if isinstance(valor, datetime.datetime):
        if valor.time() == datetime.time(0):
            return valor.date().isoformat()
        return valor.isoformat(sep=" ", timespec="seconds" if valor.second else "minutes")
    if isinstance(valor, datetime.time):
        return valor.isoformat(timespec="seconds" if valor.second else "minutes")
    return valor.isoformat()


_ESQUEMAS_LIGAZON = ("http://", "https://", "mailto:")


def url_ligazon(url: str | None) -> str:
    """O URL listo para `[texto](url)`, ou `""` se non é unha ligazón web ou
    de correo (as internas, `#folla`, e as de ficheiros locais non valen)."""
    url = (url or "").strip()
    if not url.lower().startswith(_ESQUEMAS_LIGAZON):
        return ""
    return url.replace(" ", "%20").replace("(", "%28").replace(")", "%29").replace("|", "%7C")


def ligazon_md(texto: str, url: str) -> str:
    """`[texto](url)`; sen texto, o propio URL. Os brancos das beiras quedan fóra."""
    cuberto = texto.strip()
    if not cuberto:
        return url
    return texto[:len(texto) - len(texto.lstrip())] + f"[{cuberto}]({url})" + \
        texto[len(texto.rstrip()):]


def con_ligazons(texto: str, ligazons: list) -> str:
    """Pon `[texto](url)` onde o texto dunha ligazón aparece no `texto` do
    parágrafo, en orde; as que non se atopan van ao final entre paréntese.
    `ligazons`: (texto da ligazón, URL xa limpo con `url_ligazon`)."""
    cursor, saida, sobran = 0, [], []
    for texto_ligazon, url in ligazons:
        texto_ligazon = " ".join(texto_ligazon.split())
        posicion = texto.find(texto_ligazon, cursor) if texto_ligazon else -1
        if posicion < 0:
            sobran.append(url)
            continue
        saida.append(texto[cursor:posicion])
        saida.append(f"[{texto_ligazon}]({url})")
        cursor = posicion + len(texto_ligazon)
    saida.append(texto[cursor:])
    return "".join(saida) + "".join(f" ({u})" for u in sobran)


def taboa_ou_liñas(filas: list) -> str:
    """`filas`: listas de celas YA escapadas (`_escapar_cela`). Táboa
    Markdown; se non o é de verdade (unha columna, unha fila), a lista ou a
    táboa só con cabeceira que non perda ningún dato."""
    taboa = _taboa_md(filas)
    if taboa is not None:
        return taboa
    filas = [f for f in filas if any(f)]
    if not filas:
        return ""
    n_columnas = max(len(f) for f in filas)
    if n_columnas <= 1:
        return "\n".join("- " + f[0] for f in filas)
    # Unha soa fila con varias columnas: táboa só con cabeceira.
    return "\n".join(["| " + " | ".join(filas[0]) + " |", "|" + " --- |" * len(filas[0])]
                     + ["| " + " | ".join(f) + " |" for f in filas[1:]])


_NOME_DE_IMAXE = re.compile(r"\.(png|jpe?g|gif|bmp|tiff?|webp|emf|wmf|svg)$", re.I)


def marca_imaxe(alt: str = "") -> str:
    """`[imaxe: texto alternativo]`, ou `""` se non hai: unha imaxe sen texto
    alternativo é case sempre decorativa e unha marca baleira só gasta
    tokens (quen chama conta as omitidas e avisa). Os programas poñen o NOME
    DO ARQUIVO da imaxe coma texto alternativo (`foto.png`): non é texto
    alternativo, e pode levar nomes de persoas."""
    alt = " ".join((alt or "").split())
    if not alt or _NOME_DE_IMAXE.search(alt):
        return ""
    return t("imaxe_alt", alt=alt)
