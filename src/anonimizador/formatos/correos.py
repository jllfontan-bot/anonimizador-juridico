"""Correos gardados (.eml) a Markdown, SEN anonimizar.

Que entra e que non (ver `ESCONDITES.md`):
  - Entra: o asunto (coma título), as cabeceiras que ve a persoa no seu
    programa de correo (De, Para, Cc, Cco, Responder a, Data), o corpo (o
    texto plano se o hai; se non, o HTML polo lector de páxinas web) e a
    lista dos anexos, co seu nome e tamaño.
  - Non entra: as cabeceiras técnicas (`Received`, `Message-ID`,
    `Return-Path`, `X-*`, DKIM...: IP, servidores e enderezos de rebote), a
    versión HTML cando hai texto plano, o contido dos anexos e as imaxes
    incrustadas (sinaturas, logotipos). Os anexos non se converten: lístanse
    e avísase, para gardalos e convertelos á parte.
"""

from __future__ import annotations

import re
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from pathlib import Path

from . import paxinas_html
from ._comun import Conversion, _escapar_liña, t

FORMATOS = (".eml",)

# (cabeceira, clave do texto): as que ve a persoa, nesta orde.
_CABECEIRAS = (("From", "correo_de"), ("To", "correo_para"), ("Cc", "correo_cc"), ("Bcc", "correo_cco"),
               ("Reply-To", "correo_responder_a"), ("Date", "correo_data"))
_CITA = re.compile(r"(?:>[ \t]?)+")


def a_markdown(ruta: str) -> str:
    return convertir(ruta).markdown


def _un_espazo(texto) -> str:
    return " ".join(str(texto or "").split())


def _data(valor: str) -> str:
    """`Sat, 31 Oct 2026 10:15:00 +0100` -> `2026-10-31 10:15` (a hora tal
    como a escribiu quen enviou); se non se entende, tal cal."""
    try:
        return parsedate_to_datetime(valor).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, IndexError):
        return valor


def _liña_de_texto(liña: str) -> str:
    """Escapada coma calquera liña dun escrito, pero as citas dunha resposta
    (`> `, `>> `) quedan coma citas de Markdown, un `> ` por nivel."""
    cita = _CITA.match(liña)
    if not cita:
        return _escapar_liña(liña)
    niveis = cita.group().count(">")
    return ("> " * niveis + _escapar_liña(liña[cita.end():])).rstrip()


def _texto_plano(texto: str) -> str:
    liñas = [_liña_de_texto(l) for l in texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(liñas)).strip()


def _follas(parte):
    """As partes finais da mensaxe; unha mensaxe reenviada coma anexo
    (`message/rfc822`) é unha soa folla, sen entrar nela."""
    if parte.get_content_type() == "message/rfc822" or not parte.is_multipart():
        yield parte
        return
    for subparte in parte.iter_parts():
        yield from _follas(subparte)


def _tamaño(octetos: int) -> str:
    if octetos >= 1024 * 1024:
        return f"{octetos / (1024 * 1024):.1f} MB"
    return f"{max(1, round(octetos / 1024))} KB"


def _anexo(parte) -> str:
    if parte.get_content_type() == "message/rfc822":
        reenviada = parte.get_content()
        nome = parte.get_filename() or _un_espazo(reenviada["subject"]) or "message/rfc822"
        return f"{_un_espazo(nome)} ({_tamaño(len(reenviada.as_bytes()))})"
    nome = parte.get_filename() or parte.get_content_type()
    return f"{_un_espazo(nome)} ({_tamaño(len(parte.get_payload(decode=True) or b''))})"


def convertir(ruta: str) -> Conversion:
    mensaxe = BytesParser(policy=policy.default).parsebytes(Path(ruta).read_bytes())

    bloques = []
    asunto = _un_espazo(mensaxe["subject"])
    if asunto:
        bloques.append(f"# {asunto}")
    cabeceiras = []
    for cabeceira, clave in _CABECEIRAS:
        valor = _un_espazo(mensaxe[cabeceira])
        if valor:
            cabeceiras.append(f"- {t(clave)}: {_data(valor) if cabeceira == 'Date' else valor}")
    if cabeceiras:
        bloques.append("\n".join(cabeceiras))

    corpo = mensaxe.get_body(preferencelist=("plain", "html"))
    if corpo is not None:
        if corpo.get_content_subtype() == "plain":
            texto = _texto_plano(corpo.get_content())
        else:
            # Os avisos do lector HTML son de imaxes sen texto alternativo:
            # aquí cóntanse as incrustadas, abaixo.
            texto = paxinas_html.convertir_html(corpo.get_content(), con_titulo=False).markdown.strip()
        if texto:
            bloques.append(texto)

    anexos, incrustadas = [], 0
    for parte in _follas(mensaxe):
        if parte is corpo:
            continue
        disposicion = parte.get_content_disposition()
        if parte.get_content_type() == "message/rfc822":
            anexos.append(_anexo(parte))
        elif parte.get_content_maintype() == "image" and disposicion != "attachment" and (
                parte["Content-ID"] or disposicion == "inline"):
            incrustadas += 1
        elif parte.get_filename() or disposicion == "attachment":
            anexos.append(_anexo(parte))
        # O resto son as outras versións do corpo (o HTML canda o texto plano).
    if anexos:
        bloques.append(t("correo_anexos") + "\n" + "\n".join(f"- {a}" for a in anexos))

    avisos = []
    if anexos:
        avisos.append(t("correo_anexos_sen_converter", n=len(anexos)))
    if incrustadas:
        avisos.append(t("correo_imaxes_incrustadas", n=incrustadas))
    markdown = "\n\n".join(bloques)
    return Conversion(markdown + "\n" if markdown else "", avisos)
