"""Recoñecedores por expresión regular para identificadores directos propios
do contexto xurídico español, que un modelo de NER xenérico non cobre ben."""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import ocr_dni


@dataclass
class Entidade:
    inicio: int
    fin: int
    texto: str
    etiqueta: str
    # Só usado para "PERSOA_EXENTA_CARGO_PUBLICO" (ver ner.py): garda o
    # cargo público concreto que motivou a exención, para amosalo na
    # revisión humana.
    cargo: str | None = None
    # Persoa que SI pode cruzar un salto de liña: a cela "Apelidos,\nNome."
    # partida en dúas liñas dunha táboa (ver ner.py,
    # `_APELIDOS_NOME_INVERSO_DUAS_LINAS`). O resto de persoas pártense por
    # liñas na rede de seguridade de `ner.detectar`.
    multilinea: bool = False
    # Vén dunha cela dunha columna de dato persoal dunha táboa PDF (ver
    # `taboas_pdf.py`): a cabeceira xa di o que é, así que non se estende,
    # non se parte por liñas nin se exime por cargo público.
    cela: bool = False
    # Fila da táboa PDF (`taboas_pdf.CelaDatoPersoal.fila`) da persoa ou do
    # documento de identidade: liga o documento co seu titular pola fila,
    # non pola distancia no texto.
    fila: int | None = None

    @property
    def span(self):
        return (self.inicio, self.fin)


# Documentos que identifican a UNHA persoa: substitúense polo mesmo código
# ca o seu titular cando se sabe quen é (ver `resolution.documentos_por_grupo`).
DOCUMENTOS_DE_IDENTIDADE = ("DNI_NIE", "PASAPORTE", "DOCUMENTO_IDENTIDADE")


# NON se usa `\b` (fronteira de palabra): o guión baixo "_" CONTA coma
# carácter "de palabra" en `\w`/`\b`, así que un DNI pegado a un "_" (moi
# habitual en nomes de ficheiro xerados por sedes electrónicas, ex.
# "Solicitud_ApudActa_90817269K.pdf") non tiña fronteira ningunha aí e
# quedaba invisible ao patrón -- caso real atopado nun certificado de
# apoderamento xudicial, o propio nome do documento anexo deixaba o DNI
# completo sen redactar. As comprobacións explícitas de abaixo son
# equivalentes a `\b` pero só contan letra/díxito coma "pegado", nunca
# "_" -- así o DNI segue detectándose tanto solto coma pegado a un "_".
# A letra non pode ser o comezo dunha palabra, tampouco con til: nunha
# táboa, "20200703 Técnicas" (data + cela seguinte) daba un DNI e borraba
# a data e o "T" (BOE-A-2026-15923, lectura de Claude 30/09/2026).
# Nin o CIF dunha entidade ("CIF G-80743503") nin a conxunción despois do
# número ("G-80743503 y en su nombre" daba o DNI "80743503W", corpus web
# lote 2, 30/09/2026): unha vogal minúscula solta tras un espazo só é a
# letra se coincide coa de control (ver `_letra_solta_non_e_do_dni`).
_DNI = re.compile(r"(?<![A-Za-z0-9])(?<![ABCDEFGHJNPQRSUVW][-\u2013])\d{8}(?:\s*[-\u2013]\s*|\s?)[A-Za-z](?![^\W_])")
_NIE = re.compile(r"(?<![A-Za-z0-9])[XYZxyz][\s-]?\d{7}(?:\s*[-\u2013]\s*|\s?)[A-Za-z](?![^\W_])")
# Formato español: 9 cifras que empezan por 6, 7, 8 ou 9 (+34 opcional).
# Probouse (28/09/2026) restrinxilo aos prefixos asignados de verdade (71-74,
# 80-88, 90-98...) e só engadía fugas sen gañar nada: un documento de 9
# cifras pode ter prefixo válido igual ("987..."). O que decide é o
# contexto (etiqueta de documento ou columna "DNI/NIE/PAS", ver abaixo).
_PREFIXO_TELEFONO = r"[6789]\d{2}"
# Nunca dentro dunha cifra con puntos de miles: "y = 4.694.887\n178" (UTM
# e a cela seguinte dunha táboa, lote 3) casaba desde o "694".
_NON_DENTRO_DE_CIFRA = r"(?<!\d[.,])"
_TELEFONO = re.compile(_NON_DENTRO_DE_CIFRA + r"\b(?:\+34[\s-]?)?" + _PREFIXO_TELEFONO
                       + r"[\s.-]?\d{3}[\s.-]?\d{3}\b(?![.,]\d)")
# Agrupamento "3-2-2-2" ("666 12 34 56"): moi habitual cando se dita ou
# transcribe un teléfono en voz alta (de dous en dous díxitos), fronte ao
# "3-3-3" xa cuberto arriba -- caso real de revisión: o patrón estrito de
# `_TELEFONO` esixe un segundo E un terceiro grupo de EXACTAMENTE 3
# díxitos, así que "666 12 34 56" non casaba en ningures (nunca hai 3
# díxitos seguidos despois do primeiro grupo). O separador esíxese
# SEMPRE (nunca opcional) para non solaparse con `_TELEFONO`, que xa
# cobre a forma sen separador ningún.
_TELEFONO_3_2_2_2 = re.compile(
    _NON_DENTRO_DE_CIFRA + r"\b(?:\+34[\s-]?)?" + _PREFIXO_TELEFONO
    + r"[\s.-]\d{2}[\s.-]\d{2}[\s.-]\d{2}\b(?![.,]\d)"
)
# Con etiqueta ("teléfono", "tfno.", "móvil"...) o número é un teléfono
# sexa cal sexa o prefixo (tamén estranxeiro ou mal escrito): o contexto
# manda, igual ca co pasaporte.
_TELEFONO_CON_ETIQUETA = re.compile(
    r"\b(?:tel[eé]fonos?|tfnos?\.?|tlfs?\.?|tel\.|m[oó]vil|m[oó]bil|fax)"
    r"(?:\s+(?:de\s+contacto|fixo|fijo|m[oó]vil|m[oó]bil))?\s*(?:" + r"n[.º°o]{0,2}" + r"\s*)?:?\s*"
    r"(?P<numero>(?:\+\d{2,3}[\s-]?)?\d{3}(?:[\s.-]?\d{3}[\s.-]?\d{3}|[\s.-]\d{2}[\s.-]\d{2}[\s.-]\d{2}))"
    r"(?!\d)",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")

# Matrícula actual (dende 2000): 4 díxitos + 3 consoantes, sen vogais nin Q/Ñ.
_MATRICULA = re.compile(r"\b\d{4}[\s-]?[BCDFGHJKLMNPRSTVWXYZ]{3}\b")
# Matrícula antiga (ata 2000): código de provincia + 4 díxitos + 2 letras,
# sempre impresa con separador na placa física.
_MATRICULA_ANTIGA = re.compile(r"\b[A-Z]{1,2}[\s-]\d{4}[\s-][A-Z]{2}\b")

# Abreviatura de "número": "n" + ata dous caracteres de puntuación en
# calquera orde (º, °, aspas rectas/curvas, punto -- "nº", "n.º", "n°",
# `n"` ...). O símbolo ordinal adoita saír mal do OCR, confundido con
# aspas ou o signo de grao, e pode ir antes ou despois do punto.
_N_ORDINAL = r"n[.º°o\x22\x27’”′]{0,2}"

_EXPEDIENTE = re.compile(
    r"\b(?:expediente|proc(?:edemento)?|autos)\s+" + _N_ORDINAL + r"\s*\d+/\d{2,4}\b",
    re.IGNORECASE,
)

# Número de colexiado/a: identifica un profesional case tan directamente
# coma un DNI. So se redacta a cifra (grupo "numero"); a palabra "colegiado
# número"/"colexiado nº" queda visible coma contexto.
_COLEXIADO = re.compile(
    r"\bcole[gx]iad[oa]\s+(?:" + _N_ORDINAL + r"|n[uú]mero)\s*(?P<numero>\d{1,3}(?:\.\d{3})+|\d+)\b",
    re.IGNORECASE,
)
# "número de colexiado 1.905 da Coruña" (orde inversa e miles con punto;
# lectura de Claude, DOG AnuncioG0763-290726-0013, 30/09/2026).
_COLEXIADO_INVERSO = re.compile(
    r"\b(?:n[uú]mero|" + _N_ORDINAL + r")\s+de\s+cole[gx]iad[oa]\s*(?P<numero>\d{1,3}(?:\.\d{3})+|\d+)\b",
    re.IGNORECASE,
)

# Pasaporte español: identificador directo tan forte coma un DNI, pero o
# formato (letras + díxitos) é demasiado xenérico para recoñecelo sen
# contexto -- esíxese a etiqueta "pasaporte" preto, igual ca colexiado/
# referencia/CSV (a REGRA DE OURO desas ambigüidades, ver máis abaixo).
# Formato oficial español dende 2007: 3 letras + 6 díxitos ("AAA123456");
# admítense tamén 2 letras (formato anterior) e 7 díxitos, para non ser
# demasiado estrito ante variantes ou erros de OCR.
#
# Pasaportes e documentos ESTRANXEIROS (caso real, corpus web 28/09/2026:
# anexo do DOG con persoas non aseguradas, columna "DNI/NIE/PAS"): os
# formatos varían moito ("P29214852", "BF718330", "120692171",
# "3M6D5GOZU00060488597T"), así que o número admite calquera código
# alfanumérico con polo menos 5 díxitos, ou só díxitos se son 8-12 (un
# número de 6-7 díxitos adoita ser un expediente). Segue esixíndose
# contexto: a etiqueta, o "representante" ou a columna da táboa.
_ID_DOCUMENTO = (
    r"(?:\d{8,12}|(?=[A-Za-z0-9]*[A-Za-z])(?=(?:[A-Za-z]*\d){5})[A-Za-z0-9]{6,24})"
    r"(?![A-Za-z0-9])"
)
_PASAPORTE = re.compile(
    r"\bpasaporte\s*(?:" + _N_ORDINAL + r"|n[uú]mero)?\s*:?\s*"
    r"(?P<numero>[A-Za-z]{2,3}\d{6,7}(?![A-Za-z0-9])|" + _ID_DOCUMENTO + r")",
    re.IGNORECASE,
)
# "(representante 219051727)": o documento de quen representa á persoa
# interesada, nas mesmas táboas. Un DNI/NIE con formato xa o colle o
# patrón de DNI antes (vai primeiro en `_PATRONS`).
_DOCUMENTO_REPRESENTANTE = re.compile(
    r"\brepresentante\s*(?:\(?\s*(?:DNI|NIE|NIF|pasaporte|PAS)\s*\)?\s*)?:?\s*"
    r"(?P<numero>" + _ID_DOCUMENTO + r")",
    re.IGNORECASE,
)
# Cabeceira dunha columna de documento de identidade que inclúe pasaportes.
_CABECEIRA_DOCUMENTO = re.compile(
    r"\b(?:DNI|NIF)\s*/\s*NIE\s*/\s*(?:PAS(?:APORTE)?|pasaporte)\b|\bNIE\s*/\s*pasaporte\b",
    re.IGNORECASE,
)
# Valor dunha cela desa columna: o código ao principio da liña, só ou
# seguido dun paréntese ("P29214852 (NIE X...)").
_CELA_DOCUMENTO = re.compile(r"(?m)^[ \t]*(?P<numero>" + _ID_DOCUMENTO + r")(?=[ \t]*(?:\(|$))")

# Código Seguro de Verificación (CSV): permite recuperar o documento
# ORIXINAL completo, sen anonimizar, no portal do organismo emisor -- deixalo
# visible anularía toda a anonimización aínda que se borren nomes e DNI.
# O formato varía moito segundo o organismo (Ministerio de Xustiza, sedes
# electrónicas autonómicas, Colexio de Rexistradores...), así que se busca
# por contexto: a etiqueta pode ir antes ou despois do propio código.
#
# Corrección atopada probando contra un certificado real de Registradores
# de España: a etiqueta vai coma "C.S.V." (con puntos entre cada letra),
# que "CSV" a secas NON recoñece -- son literalmente caracteres distintos
# (puntos de por medio), non unha variante de maiúsculas/minúsculas. Sen
# este caso, o CSV quedaba sen redactar en dúas páxinas dun documento real.
_CSV_ETIQUETA = (
    r"c[oó]digo\s+seguro\s+de\s+verificaci[oó]n\b"
    r"|C\.S\.V\.?"
    r"|CSV\b"
)
_CSV_ETIQUETA_LOGO_CODIGO = re.compile(
    r"\b(?:" + _CSV_ETIQUETA + r")\s*:?\s*"
    r"(?P<numero>[A-Za-z0-9][A-Za-z0-9\-:]{7,})",
    re.IGNORECASE,
)
_CSV_CODIGO_LOGO_ETIQUETA = re.compile(
    r"(?P<numero>[A-Za-z0-9]{4,}(?:[-:][A-Za-z0-9]+){2,})"
    r"(?=\s*(?:" + _CSV_ETIQUETA + r"))",
    re.IGNORECASE,
)

# N.R.P. (Número de Rexistro de Persoal): identificador oficial do
# persoal funcionario, moi habitual en listaxes do BOE/DOG (nomeamentos,
# oposicións...). Formato: OS 8 DÍXITOS DO DNI + 2 díxitos propios do NRP
# + espazo + letra do corpo + 4 díxitos (ex. "1194568868 A0590" -- os
# primeiros 8 díxitos, "11945688", SON literalmente o DNI da persoa).
#
# Caso real atopado nunha listaxe BOE de funcionarios: a propia columna
# "D.N.I." amosaba eses 8 díxitos SOLTOS, SEN letra de control ningunha
# -- e como o patrón de DNI esixe sempre esa letra final, quedaban
# completamente sen detectar en TODA a táboa (decenas de persoas). O NRP,
# en cambio, SI ten un formato propio recoñecible sen ambigüidade, así
# que se usa para deducir o DNI (letra recalculada, nunca inventada) e
# despois buscar tamén ese mesmo DNI solto noutro punto do documento.
# DNI/NIE con PUNTOS de millares ("12.345.678-Z", "1.234.567-L", "X-1.234.567-L").
# Non vai nos patróns estritos de arriba porque un número con puntos tamén é
# un IMPORTE ("1.234.567 y otros") ou un número de expediente: aquí só se
# acepta se hai OUTRO sinal de que é un documento de identidade -- (a) hifen
# ou letra pegada ao número, (b) a letra coincide co díxito de control
# calculado, ou (c) a palabra DNI/NIF/NIE xusto antes (nese caso vale mesmo
# sen letra). Bug real atopado nun escrito xudicial: "DNI 12.345.678- V"
# (puntos + hifen + espazo + letra, incluso con salto de liña antes da
# letra) quedaba sen anonimizar.
_DNI_PUNTOS = re.compile(
    r"(?<![A-Za-z0-9.,])(?P<num>\d{1,2}\.\d{3}\.\d{3})(?!\d|[.,]\d)"
    r"(?:(?P<sep>\s*[-\u2013]\s*|\s?)(?P<letra>[A-Za-z])(?![^\W_]))?"
)
_NIE_PUNTOS = re.compile(
    r"(?<![A-Za-z0-9.,])(?P<pref>[XYZxyz])[\s-]?(?P<num>\d\.\d{3}\.\d{3})(?!\d|[.,]\d)"
    r"(?P<sep>\s*[-\u2013]\s*|\s?)(?P<letra>[A-Za-z])(?![^\W_])"
)
_CLAVE_DOCUMENTO_ANTES = re.compile(r"(?:DNI|NIE|NIF|N\.I\.F\.?|D\.N\.I\.?)\W{0,14}$", re.IGNORECASE)


def _detectar_dnis_con_puntos(texto: str, ocupado: list) -> list:
    atopados = []
    for match in _NIE_PUNTOS.finditer(texto):
        inicio, fin = match.span()
        if any(ocupado[inicio:fin]):
            continue
        resto = match.group("num").replace(".", "")
        digitos8 = {"X": "0", "Y": "1", "Z": "2"}[match.group("pref").upper()] + resto
        for i in range(inicio, fin):
            ocupado[i] = True
        normalizado = f"{match.group('pref').upper()}{resto}{ocr_dni.letra_control(digitos8)}"
        atopados.append(Entidade(inicio, fin, normalizado, "DNI_NIE"))

    for match in _DNI_PUNTOS.finditer(texto):
        inicio, fin = match.span()
        if any(ocupado[inicio:fin]):
            continue
        digitos8 = match.group("num").replace(".", "").zfill(8)
        letra, sep = match.group("letra"), match.group("sep") or ""
        con_clave = bool(_CLAVE_DOCUMENTO_ANTES.search(texto[max(0, inicio - 30):inicio]))
        if letra:
            aceptado = (
                con_clave
                or "-" in sep or "\u2013" in sep      # hifen: "12.345.678-Z" / "12.345.678- Z"
                or sep == ""                            # letra pegada: "12.345.678Z"
                or letra.upper() == ocr_dni.letra_control(digitos8)
            )
        else:
            aceptado = con_clave                       # "DNI 12.345.678" (sen letra)
            fin = match.end("num")
        if not aceptado:
            continue
        for i in range(inicio, fin):
            ocupado[i] = True
        atopados.append(Entidade(inicio, fin, f"{digitos8}{ocr_dni.letra_control(digitos8)}", "DNI_NIE"))
    return atopados


def _detectar_columna_documento(texto: str, ocupado: list, xa_atopados: list) -> list:
    """Táboas con columna "DNI/NIE/PAS": despois da cabeceira, o código ao
    principio de cada liña é o documento da persoa, teña ou non forma de
    DNI/NIE (os que a teñen xa os colleu o patrón de DNI). Sen esa
    cabeceira non se fai nada: fóra de contexto, un código así pode ser
    calquera cousa."""
    cabeceira = _CABECEIRA_DOCUMENTO.search(texto)
    if not cabeceira:
        return []
    atopados = []
    telefonos = {(e.inicio, e.fin): e for e in xa_atopados if e.etiqueta == "TELEFONO"}
    for match in _CELA_DOCUMENTO.finditer(texto, cabeceira.end()):
        inicio, fin = match.span("numero")
        if (inicio, fin) in telefonos:
            # Na columna de documentos, o contexto gaña á forma: xa estaba
            # tapado coma teléfono, só se corrixe a etiqueta.
            telefonos[(inicio, fin)].etiqueta = "PASAPORTE"
            continue
        if any(ocupado[inicio:fin]):
            continue
        for i in range(inicio, fin):
            ocupado[i] = True
        atopados.append(Entidade(inicio, fin, match.group("numero"), "PASAPORTE"))
    return atopados


_NRP = re.compile(r"\b(?P<dni8>\d{8})\d{2}[\s-][A-Z]\d{4}\b")


def _detectar_dnis_por_nrp(texto: str, ocupado: list) -> list:
    atopados = []
    dnis8_vistos = set()
    for match in _NRP.finditer(texto):
        inicio, fin = match.span("dni8")
        if any(ocupado[inicio:fin]):
            continue
        digitos8 = match.group("dni8")
        for i in range(inicio, fin):
            ocupado[i] = True
        atopados.append(Entidade(inicio, fin, f"{digitos8}{ocr_dni.letra_control(digitos8)}", "DNI_NIE"))
        dnis8_vistos.add(digitos8)

    if not dnis8_vistos:
        return atopados

    # a mesma persoa: busca eses MESMOS díxitos soltos noutro punto do
    # documento (ex. a columna "D.N.I." da táboa) -- nunca "calquera
    # número solto", só os xa confirmados por un NRP real. Acepta de 1 a
    # 9 díxitos (non esixe exactamente 8): casos reais atopados na MESMA
    # táboa, en filas distintas -- a columna "D.N.I." ás veces perde o
    # cero inicial ("9752357", 7 díxitos) e ás veces o conserva coma
    # díxito de máis ("034867809", 9 díxitos).
    for match in re.finditer(r"(?<!\d)\d{1,9}(?!\d)", texto):
        cru = match.group()
        if len(cru) == 9:
            if cru[0] != "0":
                continue
            digitos8 = cru[1:]
        else:
            digitos8 = cru.zfill(8)
        if digitos8 not in dnis8_vistos:
            continue
        inicio, fin = match.span()
        if any(ocupado[inicio:fin]):
            continue
        for i in range(inicio, fin):
            ocupado[i] = True
        atopados.append(Entidade(inicio, fin, f"{digitos8}{ocr_dni.letra_control(digitos8)}", "DNI_NIE"))
    return atopados


# "Número de referencia" dun trámite (apoderamentos, expedientes de sede
# electrónica...): mesmo risco cá CSV -- é a clave para consultar o trámite
# no portal do organismo. Só se redacta a cifra, coma no resto de casos.
_REFERENCIA = re.compile(
    r"\bn[uú]mero\s+de\s+referencia\s*:?\s*(?P<numero>[A-Za-z0-9][A-Za-z0-9\-/]{2,})\b",
    re.IGNORECASE,
)

# IBAN español: código de conta bancaria internacional -- identifica
# directamente a titularidade dunha conta, mesmo risco ca un número de
# tarxeta. Formato oficial: "ES" + 2 díxitos de control + 20 díxitos máis,
# case sempre agrupados de 4 en 4 con espazo ("ES91 2100 0418 4502 0005
# 1332"), aínda que tamén aparece sen espazos. Non se esixía patrón
# ningún para isto -- quedaba completamente sen detectar.
_IBAN = re.compile(r"\b[Ee][Ss]\d{2}(?:[ \t]?\d{4}){5}\b")

# Número de tarxeta bancaria: 4 grupos de 4 díxitos (16 en total), case
# sempre separados por espazo ou guión nos formatos impresos/dixitados a
# man. Esíxese SEMPRE separador entre grupos (nunca 16 díxitos soltos)
# para non disparar con calquera número de conta/referencia longo que
# tamén teña 16 díxitos seguidos sen forma recoñecible de tarxeta.
_TARXETA = re.compile(r"\b\d{4}[ \t-]\d{4}[ \t-]\d{4}[ \t-]\d{4}\b")

# Referencia catastral: 20 caracteres alfanuméricos que identifican de
# forma unívoca unha parcela/inmoble e, indirectamente, a quen consta
# coma titular no rexistro -- so se redacta cando vai etiquetada
# explicitamente (o formato en si, 20 alfanuméricos seguidos, é
# demasiado xenérico para recoñecelo sen contexto, coma xa pasa con CSV
# e "número de referencia").
_REF_CATASTRAL = re.compile(
    r"\breferencia\s+catastral\s*:?\s*(?P<numero>[A-Za-z0-9]{20})\b",
    re.IGNORECASE,
)

# Número de afiliación á Seguridade Social: código persoal (2 díxitos de
# provincia + "/" + 10 díxitos) que identifica directamente ao
# traballador/a ante a Seguridade Social. Igual ca a referencia
# catastral, esíxese a etiqueta previa -- o formato "díxitos/díxitos" a
# secas tamén podería ser unha fracción ou un expediente doutro tipo.
# A ETIQUETA admite as formas reais (galego e castelán, enteiras ou en
# siglas) e o NÚMERO os tres xeitos de escribilo: "28/12345678/40",
# "28/1234567840" e "281234567840" (tamén con espazo ou guión). Todo isto
# saíu de probar o que se escapaba o 27/09/2026: só se recoñecía "número de
# afiliación [a la Seguridad Social]" cun único formato.
#
# A REGRA DE OURO non cambia: sen etiqueta preto NON se toca nada. Un
# "28/1234567840" solto pode ser un expediente ou unha fracción, e redactalo
# por si só faría perder texto que non é un dato persoal. Os díxitos de
# control do número si se poderían comprobar, pero un de cada 97 números ao
# chou cadra por casualidade: serviría para AVISAR, nunca para redactar só.
# "número", "núm.", "nº", "n.º", "n°"
_N_ABREV = r"n(?:[uú]mero|[uú]m\.?|\.?[ºo°])"
# "á Seguridade Social" (galego, coa contracción) ou "a la Seguridad Social"
_SS_NOME = r"[aá]\s+(?:l[ao]\s+)?Seguridad[e]?\s+Social"
_SS_ETIQUETA = (
    r"" + _N_ABREV + r"\s+de\s+afiliaci[oó]n(?:\s+" + _SS_NOME + r")?"
    r"|afiliaci[oó]n\s+" + _SS_NOME + r"(?:\s+" + _N_ABREV + r")?"
    r"|" + _N_ABREV + r"\s+(?:de\s+)?l[ao]\s+Seguridad[e]?\s+Social"
    r"|" + _N_ABREV + r"\s+de\s+Seguridad[e]?\s+Social"
    r"|N\.?A\.?F\.?|N\.?A\.?S\.?S\.?"
)
_SS_NUMERO = r"\d{2}[/\s-]?\d{8}[/\s-]?\d{2}"
_SEGURIDADE_SOCIAL = re.compile(
    r"\b(?:" + _SS_ETIQUETA + r")\s*(?:n[ºo°]\.?|n[uú]m\.?)?\s*:?\s*"
    r"(?P<numero>" + _SS_NUMERO + r")\b",
    re.IGNORECASE,
)

# Enderezos: verbo tipo de vía (galego e castelán, incluíndo "lugar" tan
# habitual no rural galego) + nome + número ou "s/n" (sen número).
# Nunca "\s+" (que tamén casa un salto de liña) -- un enderezo real vai
# sempre NUNHA soa liña; caso real atopado nunha táboa BOE: "María del
# CAMINO" (nome de pía real, "camiño" coma verbo de vía) casaba de
# seguido co DNI da SEGUINTE liña coma se fose un "número" de portal,
# fusionando dous datos completamente distintos (nome + DNI doutra
# persoa) nun só falso "enderezo" e ocupando ese espazo antes de que o
# propio nome puidese detectarse coma persoa.
# O número de portal pode levar unha letra de piso/bloque PEGADA
# directamente ("Rúa Nova 12B", sen espazo nin guión) -- caso real de
# revisión: `\d+` remataba en `\b`, pero entre un díxito e unha letra
# pegada NON hai fronteira de palabra ningunha (os dous son `\w`), así
# que ese `\b` final fallaba e o enderezo enteiro quedaba sen casar en
# ningures (non só sen a letra: SEN NADA). Só se acepta UNHA letra
# pegada (o patrón enteiro xa vai con IGNORECASE, así que vale
# maiúscula ou minúscula) para non tragar por accidente a primeira
# letra da palabra seguinte.
_NUMERO_PORTAL = r"\d+[A-ZÁÉÍÓÚÑ]?"  # IGNORECASE aplícase a todo o patrón -> tamén casa minúscula
_ENDEREZO = re.compile(
    r"\b(?:r[uú]a|calle|c/|avenida|avda\.?|estrada|carretera|cami[ñn]o|traves[íi]a|paseo|rolda|ronda|"
    r"urbanizaci[oó]n|praz[ae]|plaza|lugar)[ \t]+"
    r"(?:d[eoa]s?[ \t]+)?[\wáéíóúñÁÉÍÓÚÑ.'-]+(?:[ \t]+[\wáéíóúñÁÉÍÓÚÑ.'-]+){0,4}"
    r"(?:,?[ \t]*" + _N_ORDINAL + r"[ \t]*" + _NUMERO_PORTAL
    + r"|,?[ \t]*n[uú]mero[ \t]*" + _NUMERO_PORTAL
    + r"|,?[ \t]*s[ \t]*/[ \t]*n|,?[ \t]*" + _NUMERO_PORTAL + r")\b",
    re.IGNORECASE,
)

# Unha estrada identificada polo seu código ("carretera AS-374", "estrada
# LU-P-4103") ou un camiño/linde dunha parcela ("camino de la parcela 10115")
# é unha referencia xeográfica, non un domicilio (corpus web, BOE de
# declaración dun BIC, 30/09/2026). Só se descarta se NON hai contexto de
# domicilio preto: "con domicilio en Estrada N-550, km 12" segue sendo enderezo.
_VIA_CON_CODIGO_OU_PARCELA_RE = re.compile(
    # Cun adxectivo diante do código: "estrada autonómica PO-532" (lote 3).
    r"^(?:carretera|estrada|autov[ií]a|cami[ñn]o)[ \t]+"
    r"(?:(?:auton[oó]mica|nacional|provincial|local|comarcal|municipal|estatal)[ \t]+)?"
    r"(?:[A-Za-z]{1,4}-[A-Za-z0-9-]*\d"
    r"|(?:d[eoa]s?[ \t]+)?(?:la[ \t]+|a[ \t]+)?(?:parcela|pol[ií]gono|finca)\b)",
    re.IGNORECASE,
)
_CONTEXTO_DOMICILIO_RE = re.compile(
    r"domicil|vecin|veciñ|resid|enderezo|direcci[oó]n|notificaci|con sede|sito|sita", re.IGNORECASE
)


# "ha tenido lugar con posterioridad al 3 de abril" (BOE-A-2026-14956, lectura
# humana 01/10/2026): "lugar" en prosa, non o tipo de vía do rural galego.
_LUGAR_EN_PROSA_RE = re.compile(r"lugar[ \t]+(?!d[eoa]s?[ \t])[a-záéíóúñ]")


# "(plaza 026CUN25)", "titular de la plaza número 2 de la Sección" (lote 3,
# 03/10/2026), "en la plaza código 021132" (lote 5, BOE-A-2025-2801): unha praza
# de persoal; unha praza da cidade sempre ten nome.
_PRAZA_DE_PERSOAL_RE = re.compile(
    r"(?:plaza|praza)[ \t]+(?:(?:n[uú]mero|c[oó]digo|con[ \t]+c[oó]digo|co[ \t]+c[oó]digo|n\.?[ºo°]\.?)[ \t]*)?\d",
    re.IGNORECASE)


def _e_referencia_xeografica(texto: str, match) -> bool:
    if _LUGAR_EN_PROSA_RE.match(match.group()) or _PRAZA_DE_PERSOAL_RE.match(match.group()):
        return True
    if not _VIA_CON_CODIGO_OU_PARCELA_RE.match(match.group()):
        return False
    return _CONTEXTO_DOMICILIO_RE.search(texto[max(0, match.start() - 80):match.start()]) is None


_PATRONS = (
    ("DNI_NIE", _DNI),
    ("DNI_NIE", _NIE),
    # Os documentos con etiqueta ("pasaporte", "representante") ANTES ca o
    # teléfono: un pasaporte de 9 cifras que empeza por 6-9 ten tamén forma
    # de teléfono, e o contexto é o que decide.
    ("PASAPORTE", _PASAPORTE),
    ("PASAPORTE", _DOCUMENTO_REPRESENTANTE),
    ("TELEFONO", _TELEFONO_CON_ETIQUETA),
    ("TELEFONO", _TELEFONO),
    ("TELEFONO", _TELEFONO_3_2_2_2),
    ("EMAIL", _EMAIL),
    ("MATRICULA", _MATRICULA),
    ("MATRICULA", _MATRICULA_ANTIGA),
    ("EXPEDIENTE", _EXPEDIENTE),
    ("ENDEREZO", _ENDEREZO),
    ("COLEXIADO", _COLEXIADO),
    ("COLEXIADO", _COLEXIADO_INVERSO),
    ("CSV", _CSV_ETIQUETA_LOGO_CODIGO),
    ("CSV", _CSV_CODIGO_LOGO_ETIQUETA),
    # IBAN ANTES de TARXETA: un IBAN xa reclama tódolos seus díxitos (6
    # grupos de 4), así que a busca de "4 grupos de 4" da tarxeta nunca
    # chega a atopar un anaco libre dentro del.
    ("IBAN", _IBAN),
    ("TARXETA", _TARXETA),
    ("REF_CATASTRAL", _REF_CATASTRAL),
    ("SEGURIDADE_SOCIAL", _SEGURIDADE_SOCIAL),
    ("REFERENCIA", _REFERENCIA),
)


def _letra_solta_non_e_do_dni(capturado: str) -> bool:
    m = re.fullmatch(r"(\d{8})\s([yeoua])", capturado)
    return m is not None and ocr_dni.letra_control(m.group(1)) != m.group(2).upper()


def detectar(texto: str) -> list[Entidade]:
    """Devolve identificadores directos detectados por patrón, sen solapamentos
    (o primeiro patrón que casa nunha posición gaña).

    O DNI/NIE normalízase sempre a partir dos díxitos e o díxito de
    control RECALCULADO (`ocr_dni.py`) -- nunca se confía na letra final
    tal como aparece no texto, xa que e a que máis erra o OCR e ademais e
    redundante (calcúlase a partir dos números)."""
    atopados: list[Entidade] = []
    ocupado = [False] * len(texto)

    for etiqueta, patron in _PATRONS:
        for match in patron.finditer(texto):
            # Se o patrón ten un grupo "numero", so se redacta ESE anaco
            # (o resto do texto de contexto, coma "colegiado número", queda
            # visible); senón redáctase o match enteiro.
            if etiqueta == "ENDEREZO" and _e_referencia_xeografica(texto, match):
                continue
            if "numero" in patron.groupindex:
                inicio, fin = match.span("numero")
                texto_capturado = match.group("numero")
            else:
                inicio, fin = match.span()
                texto_capturado = match.group()

            if any(ocupado[inicio:fin]):
                continue
            if etiqueta == "DNI_NIE" and _letra_solta_non_e_do_dni(texto_capturado):
                continue
            for i in range(inicio, fin):
                ocupado[i] = True
            texto_entidade = texto_capturado
            if etiqueta == "DNI_NIE":
                texto_entidade = ocr_dni.recoñecer_dni_ocr(texto_entidade) or texto_entidade
            atopados.append(Entidade(inicio, fin, texto_entidade, etiqueta))

    # Recoñecedor de reserva: candidatos a DNI/NIE a carón da palabra clave
    # que non casaron co patrón estrito (texto vindo de OCR con erros).
    atopados.extend(_detectar_dnis_con_puntos(texto, ocupado))
    atopados.extend(ocr_dni.detectar_dnis_por_contexto(texto, ocupado))

    # Recoñecedor de reserva: DNI incrustado nun N.R.P. (ver `_NRP`), e a
    # súa aparición solta (sen letra) noutro punto do mesmo documento.
    atopados.extend(_detectar_dnis_por_nrp(texto, ocupado))

    atopados.extend(_detectar_columna_documento(texto, ocupado, atopados))

    return sorted(atopados, key=lambda e: e.inicio)
