"""Correccion de DNI/NIE mal lidos polo OCR, apoiandose no diixito de
control: a letra final dun DNI calculase matematicamente a partir dos 8
numeros (resto da division entre 23), asi que non fai falta que o OCR a
lea ben -- abonda con reconstruir correctamente os 8 numeros e
RECALCULAR a letra, en vez de confiar na letra que o OCR devolveu.

E o caso real que motivou isto: un DNI "30014811Z" foi lido polo OCR como
"300148112" (o "Z" final confundiuse cun "2"). Sen esta correccion, nin
sequera casaba co patron de DNI e quedaba SEN redactar no documento
anonimizado -- unha fuga de dato real, non so un problema de precision.
"""

from __future__ import annotations

import re

_LETRAS_DNI = "TRWAGMYFPDXBNJZSQVHLCKE"

# Confusions habituais do OCR sobre digitos (nun contexto onde deberia
# haber un numero, pero o motor recoñeceu unha letra parecida).
_LETRA_A_DIXITO = {
    "O": "0", "Q": "0", "D": "0",
    "I": "1", "L": "1",
    "Z": "2",
    "S": "5",
    "G": "6", "B": "8",
    "T": "7",
}

# Abreviatura de "número" ("nº", "n.º", "n°"...) entre a etiqueta e o
# propio documento, ex. "DNI nº 30O14811Z" -- mesmo fragmento ca
# `recognizers._N_ORDINAL`, pero copiado aquí (non se importa de alí)
# para evitar un import circular: `recognizers.py` xa importa este
# módulo enteiro.
_N_ORDINAL_OCR = r"n[.º°o\x22\x27’”′]{0,2}"

# A etiqueta tamén pode ir CON PUNTOS entre cada letra ("D.N.I.", "N.I.E.")
# -- moi habitual en escritos xudiciais -- que "DNI" a secas NON recoñece
# (son literalmente caracteres distintos, mesmo motivo có "C.S.V." en
# `recognizers._CSV_ETIQUETA`). Caso real de revisión: "DNI nº 30O14811Z"
# (coa abreviatura de "número" no medio) e "D.N.I. 30O14811Z" (coa
# etiqueta con puntos) quedaban os DOUS sen detectar -- o patrón antigo
# esixía a etiqueta pegada DIRECTAMENTE ao número (sen "nº" polo medio) e
# só recoñecía "DNI"/"NIE"/"NIF" sen puntos.
_ETIQUETA_DOC_OCR = r"D\.?N\.?I\.?|N\.?I\.?[EF]\.?"
_CONTEXTO_DNI_RE = re.compile(
    r"\b(?:" + _ETIQUETA_DOC_OCR + r")\s*(?:" + _N_ORDINAL_OCR + r")?\s*[:.]?\s*([A-Za-z0-9]{8,9})\b",
    re.IGNORECASE,
)


def letra_control(digitos8: str) -> str:
    return _LETRAS_DNI[int(digitos8) % 23]


def _normalizar_digitos(cadea: str, lonxitude_esperada: int) -> str | None:
    """Intenta ler `cadea` coma un numero de `lonxitude_esperada` diixitos,
    corrixindo confusions tipicas de OCR letra->diixito. Devolve None se
    non e posible reconstruir diixitos coherentes."""
    convertida = "".join(_LETRA_A_DIXITO.get(c.upper(), c) for c in cadea)
    if convertida.isdigit() and len(convertida) == lonxitude_esperada:
        return convertida
    return None


_LETRA_INICIAL_NIE = {"X": "0", "Y": "1", "Z": "2"}


def recoñecer_dni_ocr(candidato: str) -> str | None:
    """Recibe un anaco de texto de ata 9 caracteres atopado a carón da
    palabra DNI/NIE/NIF (posiblemente mal lido polo OCR) e devolve o
    documento normalizado, cos diixitos de control RECALCULADOS a partir
    dos numeros (nunca confiando na letra final que o OCR leu), ou None
    se non se pode recoñecer coma tal. Cobre tanto DNI (8 diixitos +
    letra) coma NIE (X/Y/Z + 7 diixitos + letra)."""
    candidato = candidato.strip().upper().replace(" ", "").replace("-", "")
    if len(candidato) not in (8, 9):
        return None

    primeira = candidato[0]
    if primeira in _LETRA_INICIAL_NIE:
        if len(candidato) != 9:
            return None
        resto = _normalizar_digitos(candidato[1:8], 7)
        if resto is None:
            return None
        digitos8 = _LETRA_INICIAL_NIE[primeira] + resto
        return f"{primeira}{resto}{letra_control(digitos8)}"

    digitos8 = _normalizar_digitos(candidato[:8], 8)
    if digitos8 is None:
        return None
    return f"{digitos8}{letra_control(digitos8)}"


def e_cif_valido(codigo: str) -> bool:
    """NIF dunha persoa xurídica co díxito/letra de control correcto ("NIF
    Q2876002C" do ICO, BOE-A-2026-16914): non é un DNI mal lido polo OCR
    ("Q" coma "0"), senón unha entidade (lectura de Claude, 30/09/2026)."""
    c = re.sub(r"[\s.-]", "", codigo.upper())
    m = re.fullmatch(r"([ABCDEFGHJNPQRSUVW])(\d{7})([0-9A-J])", c)
    if not m:
        return False
    d = m.group(2)
    pares = sum(int(d[i]) for i in (1, 3, 5))
    impares = sum(sum(divmod(2 * int(d[i]), 10)) for i in (0, 2, 4, 6))
    control = (10 - (pares + impares) % 10) % 10
    return m.group(3) in (str(control), "JABCDEFGHI"[control])


def detectar_dnis_por_contexto(texto: str, xa_ocupado) -> list:
    """Busca candidatos a DNI/NIE a carón da palabra clave, mesmo se non
    casan co patron estrito (para texto que vén de OCR con erros). So
    considera posicions aínda non cubertas por outro recoñecedor."""
    from .recognizers import Entidade

    atopados = []
    for match in _CONTEXTO_DNI_RE.finditer(texto):
        inicio, fin = match.span(1)
        if any(xa_ocupado[inicio:fin]):
            continue
        if e_cif_valido(match.group(1)):
            continue
        recoñecido = recoñecer_dni_ocr(match.group(1))
        if recoñecido:
            atopados.append(Entidade(inicio, fin, recoñecido, "DNI_NIE"))
    return atopados
