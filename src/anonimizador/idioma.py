"""Idioma do programa: castelán (por defecto) ou galego.

Decide tres cousas: os textos da interface (`t`), o prefixo dos códigos de
persoa que se escriben nos documentos (`PERSONA_000001` / `PERSOA_000001`) e
as etiquetas dos datos redactados (`[DIRECCIÓN]` / `[ENDEREZO]`).

Por dentro o código dunha persoa é SEMPRE `PERSOA_nnnnnn` (o rexistro
cifrado garda ese, e os documentos xa entregados lévano): `codigo_visible`
tradúceo ao saír cara a un documento ou á pantalla, e `codigo_canonico` volve
a el ao entrar (reversión, decisións de revisión). Así un documento
anonimizado en calquera dos dous idiomas -- ou cos antigos `ID_nnnnnn` --
pódese reverter igual.

Orde para saber o idioma: variable de contorno `ANONIMIZADOR_IDIOMA` (para
probas e scripts), despois a preferencia gardada pola pantalla de inicio
(`preferencias.json` no cartafol de traballo, xunto a `datos_rexistro`) e,
se non hai ningunha, castelán.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path

IDIOMAS = {"es": "Castellano", "gl": "Galego"}
POR_DEFECTO = "es"
VARIABLE = "ANONIMIZADOR_IDIOMA"
FICHEIRO_PREFERENCIAS = "preferencias.json"

_DIR_TEXTOS = Path(__file__).resolve().parent / "textos"

_PREFIXO_PERSOA = {"es": "PERSONA", "gl": "PERSOA"}
_CODIGO_RE = re.compile(r"(?<![A-Za-z0-9_])(?:PERSOA|PERSONA|ID)_(\d{6})(?![0-9])")

# Etiqueta interna (a de `pipeline._ETIQUETA_REDACCION`) -> texto entre
# corchetes no documento. As que non cambian non fai falta poñelas.
_ETIQUETAS_ES = {
    "TELEFONO": "TELÉFONO",
    "MATRICULA": "MATRÍCULA",
    "ENDEREZO": "DIRECCIÓN",
    "COLEXIADO": "COLEGIADO",
    "DOCUMENTO_IDENTIDADE": "DOCUMENTO_IDENTIDAD",
    "TARXETA": "TARJETA",
    "SEGURIDADE_SOCIAL": "SEGURIDAD_SOCIAL",
}


def ficheiro_preferencias() -> Path:
    return Path.cwd() / FICHEIRO_PREFERENCIAS


def _ler_preferencias() -> dict:
    try:
        datos = json.loads(ficheiro_preferencias().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return datos if isinstance(datos, dict) else {}


def actual() -> str:
    """Idioma en uso agora mesmo ("es" ou "gl")."""
    valor = os.environ.get(VARIABLE, "").strip().lower()
    if valor in IDIOMAS:
        return valor
    valor = _ler_preferencias().get("idioma")
    return valor if valor in IDIOMAS else POR_DEFECTO


def gardar(idioma: str) -> None:
    """Garda a escolla da pantalla de inicio (sobrevive a pechar o programa)."""
    if idioma not in IDIOMAS:
        raise ValueError(f"idioma descoñecido: {idioma}")
    datos = _ler_preferencias()
    datos["idioma"] = idioma
    ruta = ficheiro_preferencias()
    temporal = ruta.with_suffix(".tmp")
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporal, ruta)


# -- textos -------------------------------------------------------------------

@lru_cache(maxsize=None)
def textos(idioma: str) -> dict:
    return json.loads((_DIR_TEXTOS / f"{idioma}.json").read_text(encoding="utf-8"))


def t(clave: str, idioma: str | None = None, **valores) -> str:
    """Texto `clave` no idioma pedido (ou no actual). Se faltase nese idioma
    úsase o outro antes ca amosar a clave: nunca un oco en branco."""
    idioma = idioma or actual()
    texto = textos(idioma).get(clave)
    if texto is None:
        outro = "gl" if idioma == "es" else "es"
        texto = textos(outro).get(clave, clave)
    return texto.format(**valores) if valores else texto


def textos_con_prefixo(prefixo: str, idioma: str | None = None) -> dict:
    """Todos os textos que comezan por `prefixo`, sen el (para o JavaScript
    dunha páxina: `const T = {...}`)."""
    idioma = idioma or actual()
    outro = "gl" if idioma == "es" else "es"
    xuntos = {**textos(outro), **textos(idioma)}
    return {c[len(prefixo):]: v for c, v in xuntos.items() if c.startswith(prefixo)}


@lru_cache(maxsize=None)
def _patrons_mensaxes() -> list:
    """Mensaxes en galego que chegan á pantalla desde módulos que non saben de
    idiomas (rexistro, explorador...): claves "msx.*", co texto galego exacto
    e {marcadores} para as partes variables."""
    patrons = []
    for clave, texto in textos("gl").items():
        if not clave.startswith("msx."):
            continue
        partes = re.split(r"\{(\w+)\}", texto)
        regex = "".join(re.escape(x) if i % 2 == 0 else f"(?P<{x}>.+?)" for i, x in enumerate(partes))
        patrons.append((re.compile(regex, re.S), clave))
    return patrons


def traducir_mensaxe(mensaxe: str, idioma: str | None = None) -> str:
    """Traduce unha mensaxe galega coñecida (ex. o texto dunha excepción do
    rexistro) ao idioma actual; a que non coñece devólvea tal cal."""
    idioma = idioma or actual()
    if idioma == "gl" or not mensaxe:
        return mensaxe
    limpa = mensaxe[1:-1] if len(mensaxe) > 1 and mensaxe[0] == mensaxe[-1] == "'" else mensaxe  # str(KeyError)
    for regex, clave in _patrons_mensaxes():
        m = regex.fullmatch(limpa)
        if m:
            return t(clave, idioma, **m.groupdict())
    return mensaxe


# -- códigos e etiquetas dos documentos ---------------------------------------

def e_codigo_persoa(texto: str) -> bool:
    return bool(_CODIGO_RE.fullmatch(texto or ""))


def codigo_canonico(codigo: str) -> str:
    """`PERSONA_000007` / `ID_000007` -> `PERSOA_000007` (o do rexistro)."""
    m = _CODIGO_RE.fullmatch(codigo or "")
    return f"PERSOA_{m.group(1)}" if m else codigo


def codigo_visible(codigo: str, idioma: str | None = None) -> str:
    """`PERSOA_000007` -> `PERSONA_000007` en castelán; o resto, igual."""
    m = _CODIGO_RE.fullmatch(codigo or "")
    if not m:
        return codigo
    return f"{_PREFIXO_PERSOA[idioma or actual()]}_{m.group(1)}"


def codigos_visibles_no_texto(texto: str, idioma: str | None = None) -> str:
    """Todos os códigos de persoa dun texto no prefixo do idioma."""
    prefixo = _PREFIXO_PERSOA[idioma or actual()]
    return _CODIGO_RE.sub(lambda m: f"{prefixo}_{m.group(1)}", texto)


def etiqueta(interna: str, idioma: str | None = None) -> str:
    """Texto entre corchetes dun dato redactado (`ENDEREZO` -> `DIRECCIÓN`)."""
    if (idioma or actual()) == "es":
        return _ETIQUETAS_ES.get(interna, interna)
    return interna
