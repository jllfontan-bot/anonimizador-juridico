"""Escaneo de risco residual: despois de anonimizar, busca no texto FINAL
calquera patrón que aínda PAREZA un dato persoal sen redactar.

Isto NON é un recoñecedor máis (non redacta nada automaticamente) -- é
unha rede de seguridade para cando a detección normal (spaCy +
expresións regulares) falla por completo ante un formato non previsto,
coma pasou cunha listaxe real do BOE (nomes en orde "Apelidos, Nome",
DNI sen letra de control...). Ningún sistema de detección pode garantir
cubrir tódolos formatos posibles nun documento real -- así que en vez de
fiar cegamente no informe de homónimos/mosaico, isto dá ao letrado unha
listaxe CONCRETA de onde mirar antes de dar por bo o resultado.

Deseño deliberadamente RUIDOSO en confianza "baixa" (mellor un falso
positivo de máis que un nome real sen avisar), pero separado en dous
niveis para que a confianza "alta" (patróns que xa sabemos que son
persoas ou identificadores reais, coma "Apelidos, Nome" ou un DNI sen
redactar) non se perda entre ruído xenérico.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import ner

# IMPORTANTE: nunca `re.IGNORECASE` nestes patróns -- a esixencia de
# MAIÚSCULA INICIAL (`[A-ZÁÉÍÓÚÑÜ]`) é o que distingue un nome propio de
# prosa normal en minúscula ("de septiembre, por la..."). Con
# IGNORECASE, `[A-Z]` tamén casaría letras minúsculas e o patrón
# "Apelidos, Nome" incendiaríase con calquera coma da prosa (bug real
# atopado probando isto -- "de septiembre, por la" marcábase coma
# "posible nome"). Para documentos TODO EN MAIÚSCULAS (coma a propia
# táboa do BOE que motivou este módulo), suavízase antes coa MESMA
# transformación ca `ner.py` (Title Case agás palabras funcionais).
_PALABRA_MAIUS_OU_CAPITALIZADA = r"[A-ZÁÉÍÓÚÑÜ][a-zA-ZÁÉÍÓÚÑÜáéíóúñü'-]+"
_CONECTOR = r"(?:de|del|do|dos|da|das|la|las|los|el|van|von)"
_RACHA = (
    r"(?:" + _CONECTOR + r"[ \t]+){0,2}" + _PALABRA_MAIUS_OU_CAPITALIZADA
    + r"(?:[ \t]+(?:" + _CONECTOR + r"[ \t]+)?" + _PALABRA_MAIUS_OU_CAPITALIZADA + r"){0,3}"
)

# Alta confianza: "Apelidos, Nome" (orde invertida) SEN redactar --
# exactamente o patrón que motivou este escaneo. Se isto casa no texto
# XA ANONIMIZADO, é case seguro un nome real que escapou á detección.
#
# Mesmo bug ca en `ner._APELIDOS_NOME_INVERSO` (copia case idéntica desta
# lóxica, alí xa arranxada): unha soa palabra capitalizada de inicio de
# frase seguida de coma confúndese co "apelido" -- caso real atopado
# probando isto contra un documento real: un título de sección
# ("COMPARECENCIAS, ALEGACIONES Y ACUERDOS:") disparaba coma se
# "Comparecencias" fose un apelido. Nome do grupo "apelidos" engadido
# só para poder aplicarlle a mesma comprobación de
# `ner._apelido_unico_a_inicio_de_frase` (reutilizada, non duplicada).
_APELIDOS_NOME_SOLTO = re.compile(
    r"(?<![\w,])(?P<apelidos>" + _RACHA + r"),[ \t]+" + _RACHA + r"(?![\w,])"
)

# Alta confianza: un número solto de 7-9 díxitos (DNI/NIE/NRP/teléfono
# sen formato recoñecido) que quedou tal cal.
#
# "Solto" (illado) é a condición clave -- non abondaba con "non pegado a
# outro díxito" (`(?<!\d)...(?!\d)`, a versión orixinal). Probando isto
# contra documentos reais de urbanismo/rexistro da propiedade, a inmensa
# maioría dos disparos NON eran DNI: eran a PARTE INICIAL doutro
# identificador máis longo, cortada a modo por só mirar o díxito
# seguinte:
#   - Unha referencia catastral ("Referencia Catastral 6872011NH3467B...")
#     -- os primeiros 7 díxitos van SEMPRE pegados a letras despois, nunca
#     soltos.
#   - Unha coordenada UTM en notación decimal ("4746999,76" ou
#     "4147004.21") -- os díxitos antes da coma/punto son a parte enteira
#     dun decimal, non un número solto.
# En ningún dos dous casos o díxito seguinte É outro díxito (por iso o
# patrón orixinal non os descartaba), pero en ambos os dous o número
# tampouco está realmente SOLTO -- está pegado a unha letra ou a unha
# coma/punto seguido de máis díxitos. Esíxese agora tamén iso: nin letra
# nin díxito pegado (`\w` cobre as dúas cousas de vez), nin fai parte
# inmediata dunha notación decimal a calquera dos dous lados.
#
# Isto NON pretende cubrir todo o ruído posible (un "Documento: 05390661"
# solto entre espazos, ou un teléfono/fax institucional, seguen a
# disparar -- correctamente ambiguos de máis para descartalos por
# patrón, quedan para o ollo humano, coma sempre neste módulo).
_NUMERO_SOLTO = re.compile(r"(?<!\w)(?<!\d[.,])\d{7,9}(?!\w)(?![.,]\d)")

# Mesma alta confianza ca `_NUMERO_SOLTO`, pero para un teléfono escrito
# en GRUPOS separados por espazo/punto/guión ("666 12 34 56", tan
# habitual coma se dita ou transcribe de dous en dous díxitos) -- caso
# real de revisión (A19): `_NUMERO_SOLTO` esixe os 7-9 díxitos TODOS
# seguidos, así que un teléfono agrupado nunca chega a acadar ese anaco
# contiguo (cada anaco solto ten só 2 ou 3 díxitos) e quedaba
# completamente invisible para a rede de seguridade, aínda que a
# detección principal (`recognizers._TELEFONO_3_2_2_2`) fallase por
# algún outro motivo (ex. un separador mesturado non prevido, coma
# "666.12 34-56"). O primeiro grupo esíxese empezar por 6/7/8/9 (móbil ou
# fixo español) para non disparar con calquera racha de números soltos.
_TELEFONO_EN_GRUPOS_SOLTO = re.compile(
    r"(?<!\w)[6789]\d{2}(?:[ \t.-]\d{2}){3}(?!\w)"
)

# Baixa confianza: calquera racha de 2+ palabras que empecen por
# maiúscula, illada (non parte doutro identificador xa redactado coma
# "[ENDEREZO]"). MOI ruidoso a propósito -- moitas institucións e
# lugares tamén casan aquí -- así que se marca coma revisión opcional,
# nunca coma "atopado un fallo".
_RACHA_ILLADA = re.compile(
    r"(?<![\w\[])" + _PALABRA_MAIUS_OU_CAPITALIZADA
    + r"(?:[ \t]+(?:" + _CONECTOR + r"[ \t]+)?" + _PALABRA_MAIUS_OU_CAPITALIZADA + r"){1,4}"
    r"(?![\w\]])"
)

# Palabras/frases que casarían coa racha illada pero son ruído coñecido
# (cabeceiras, códigos institucionais, meses...) -- reduce o ruído sen
# arriscar deixar pasar un nome real.
_RUIDO_COÑECIDO = {
    "boe núm", "cuerpo", "especialidad", "anexo", "turno", "puntuación",
    "apellidos y nombre", "profesores de", "enseñanza secundaria",
    "ministerio de educación", "política social", "deporte",
}


@dataclass
class RiscoResidual:
    tipo: str
    texto: str
    confianza: str  # "alta" ou "baixa"
    contexto: str
    inicio: int
    fin: int


def _contexto(texto: str, inicio: int, fin: int, marxe: int = 40) -> str:
    anaco = texto[max(0, inicio - marxe):min(len(texto), fin + marxe)]
    return " ".join(anaco.split())


def escanear_risco_residual(texto_anonimizado: str) -> list[RiscoResidual]:
    """Escanea o texto XA ANONIMIZADO en busca de patróns que aínda
    parezan datos persoais. Devolve unha lista de `RiscoResidual`,
    ordenada por confianza (alta primeiro).

    Escanea sobre unha copia suavizada (Title Case en anacos TODO EN
    MAIÚSCULAS, mesma transformación ca `ner.py`) para que un documento
    coma unha táboa do BOE -- onde os nomes van en maiúsculas -- non
    dependa de "casualmente" ter tamén maiúsculas a esixencia dos
    patróns; a suavización preserva SEMPRE a lonxitude (1 carácter por
    1), así que as posicións seguen a corresponder ao texto orixinal
    para o contexto amosado."""
    texto_suavizado = ner._suavizar_maiusculas_para_deteccion(texto_anonimizado)
    atopados: list[RiscoResidual] = []
    ocupado = [False] * len(texto_suavizado)

    for match in _APELIDOS_NOME_SOLTO.finditer(texto_suavizado):
        inicio, fin = match.span()
        if ner._apelido_unico_a_inicio_de_frase(texto_suavizado, match.start("apelidos"), match.group("apelidos")):
            continue
        atopados.append(RiscoResidual(
            "nome_en_orde_invertida", texto_anonimizado[inicio:fin], "alta",
            _contexto(texto_anonimizado, inicio, fin), inicio, fin,
        ))
        for i in range(inicio, fin):
            ocupado[i] = True

    for match in _NUMERO_SOLTO.finditer(texto_suavizado):
        inicio, fin = match.span()
        if any(ocupado[inicio:fin]):
            continue
        atopados.append(RiscoResidual(
            "numero_solto", texto_anonimizado[inicio:fin], "alta",
            _contexto(texto_anonimizado, inicio, fin), inicio, fin,
        ))
        for i in range(inicio, fin):
            ocupado[i] = True

    for match in _TELEFONO_EN_GRUPOS_SOLTO.finditer(texto_suavizado):
        inicio, fin = match.span()
        if any(ocupado[inicio:fin]):
            continue
        atopados.append(RiscoResidual(
            "numero_solto", texto_anonimizado[inicio:fin], "alta",
            _contexto(texto_anonimizado, inicio, fin), inicio, fin,
        ))
        for i in range(inicio, fin):
            ocupado[i] = True

    for match in _RACHA_ILLADA.finditer(texto_suavizado):
        inicio, fin = match.span()
        if any(ocupado[inicio:fin]):
            continue
        if match.group().strip().lower() in _RUIDO_COÑECIDO:
            continue
        atopados.append(RiscoResidual(
            "racha_capitalizada", texto_anonimizado[inicio:fin], "baixa",
            _contexto(texto_anonimizado, inicio, fin), inicio, fin,
        ))

    orde_confianza = {"alta": 0, "baixa": 1}
    atopados.sort(key=lambda r: (orde_confianza[r.confianza], r.inicio))
    return atopados
