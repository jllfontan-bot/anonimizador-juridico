"""Resolucion de identidade: agrupa as mencions dun mesmo documento que
corresponden a unha soa persoa, e extrae sinais (DNI, contexto distintivo)
para que o rexistro decida se e a mesma persoa doutro documento ou non.

Regra de deseno (informe, seccion 06): ante a duvida NUNCA se fusiona --
crear grupos separados e deixar que sexa o rexistro (con axuda humana)
quen confirme se son a mesma persoa.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .recognizers import DOCUMENTOS_DE_IDENTIDADE, Entidade

_CONTEXTO_RE = re.compile(
    r"\(([^)]{3,60})\)|(?:veci[ñn][oa]\s+de\s+\w[\w\s]{0,25})",
    re.IGNORECASE,
)
_ANEXO_ENTRE_RE = re.compile(r"(?im)^[ \t]*anexo(?:[ \t]+(?:[ivxlc]+|\d+))?[ \t]*\.?[ \t]*$")
_DISTANCIA_DNI = 120  # caracteres de xanela para asociar un DNI a unha mencion
_RESPECTIVAMENTE_RE = re.compile(r"\brespectivamente\b", re.IGNORECASE)
_XANELA_RESPECTIVAMENTE = 200  # caracteres cara atrás dende "respectivamente"


def normalizar(nome: str) -> str:
    # U+2010/U+2011 (guións do DOG) descompóñense a un carácter non ASCII e
    # perderíanse: "Fernández\u2011Albor" sería "fernandezalbor".
    nome = nome.replace("\u2010", "-").replace("\u2011", "-")
    # "Es-\nteiro" (palabra partida polo axuste de liña, segue en minúscula) é
    # "Esteiro" (lote 6): sen isto a mesma persoa levaba dous códigos.
    nome = re.sub(r"-[ \t]*\n[ \t]*(?=[^\W\d_A-ZÁÉÍÓÚÑÜ])", "", nome)
    sen_acentos = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    # "B. L. S." e "B.L.S." son a mesma persoa (iniciais con ou sen espazos).
    # "Galán-\nSiles" (guion de fin de liña) é "Galán-Siles", e "Pedro-José"
    # é "Pedro José" (BOE-A-2026-14843): o guion conta coma un espazo.
    return re.sub(r"(?<=\b[a-z]\.) (?=[a-z]\.)", "", " ".join(sen_acentos.lower().replace("-", " ").split()))


@dataclass
class Grupo:
    representante: str
    mencions: list = field(default_factory=list)
    dni: str | None = None
    contexto: str | None = None
    ambiguo: bool = False
    motivo_ambiguidade: str | None = None


def _buscar_contexto(texto: str, fin_mencion: int) -> str | None:
    fragmento = texto[fin_mencion:fin_mencion + 70]
    m = _CONTEXTO_RE.search(fragmento)
    if not m:
        return None
    return (m.group(1) or m.group(0)).strip()


# Fin de frase ou de liña entre un DNI e a mención que vén DESPOIS del.
_FRONTEIRA_FRASE_RE = re.compile(r"\n|\.\s+[A-ZÁÉÍÓÚÑ]")
_PENALIZACION_FRONTEIRA = 10_000
_FRONTEIRA_ANEXO_RE = re.compile(
    r"\n[ \t]*(?:ANEXO|Anexo|ANEXOS)\b|\n[ \t]*(?:N\.?I\.?F|D\.?N\.?I|N\.?I\.?E)[^\n]{0,30}\n")
_DNI_DA_PERSOA_ANTERIOR_RE = re.compile(
    r"[ \t]*,?[ \t\n]*(?:con|provist[oa][ \t]+de(?:l)?|titular[ \t]+del?|portador[a]?[ \t]+del?)"
    r"[ \t\n]+(?:el[ \t]+|o[ \t]+)?(?:DNI|NIE|NIF|D\.[ \t]?N\.[ \t]?I\.|N\.[ \t]?I\.[ \t]?E\.|pasaporte)"
    r"[ \t\n]*(?:n[.º°o]{0,2}[ \t]*)?:?[ \t\n]*",
    re.IGNORECASE,
)


def _asociar_dnis(persoas: list, dnis: list, texto: str) -> dict:
    return {id(m): d.texto for m, d in _emparellar(persoas, dnis, texto)}


def _emparellar(persoas: list, dnis: list, texto: str) -> list:
    """Empareyamento guloso do veciño mais preto entre mencions e DNI: cada
    DNI so se asocia a UNHA mencion (a mais preto) e viceversa. Isto evita
    que, cando hai dous homonimos seguidos pero so un ten DNI a carón,
    o DNI "salte" e se asocie tamen a segunda mencion por estar dentro
    da mesma xanela ampla de caracteres.

    Nun escrito o DNI vai DESPOIS do nome ao que pertence ("Nome, con DNI
    X"), así que unha mención que vén despois do DNI tras un fin de frase ou
    de liña só se escolle se non hai outra candidata. Sen isto, en "...o seu
    fillo Manuel F. S., con DNI X.\\nManuel F. S. declarou" o DNI do fillo
    ía parar á mención da liña seguinte (2 caracteres) en vez de ao fillo.
    É unha penalización e non unha prohibición: nun formulario ("DNI: X",
    e na liña seguinte "Nome: Y") esa é a única mención, e debe emparellarse."""
    pares = []
    for m in persoas:
        for d in dnis:
            distancia = min(abs(d.inicio - m.fin), abs(m.inicio - d.fin))
            # Un encabezado "ANEXO" entre os dous: o DNI é doutra sección (lote 6,
            # AnuncioG0426-080324-0005_gl: o 1º "DNI denunciado" do anexo levaba o
            # código da xefa territorial que asina xusto enriba).
            if _ANEXO_ENTRE_RE.search(texto, min(m.fin, d.fin), max(m.inicio, d.inicio)):
                continue
            if distancia <= _DISTANCIA_DNI:
                orde = distancia
                if m.inicio >= d.fin and _FRONTEIRA_FRASE_RE.search(texto, d.fin, m.inicio):
                    orde += _PENALIZACION_FRONTEIRA
                # "Nome, con DNI X": o DNI é desta persoa aínda que a seguinte
                # mención ("..., e dona Outra") quede 1 carácter máis preto
                # (auditoría do rexistro de correspondencias, 03/10/2026).
                if m.fin <= d.inicio and _DNI_DA_PERSOA_ANTERIOR_RE.fullmatch(texto, m.fin, d.inicio):
                    orde = -1
                pares.append((orde, m, d))
    pares.sort(key=lambda p: p[0])

    mencions_asignadas, dnis_asignados = set(), set()
    resultado = []
    for _, m, d in pares:
        if id(m) in mencions_asignadas or id(d) in dnis_asignados:
            continue
        resultado.append((m, d))
        mencions_asignadas.add(id(m))
        dnis_asignados.add(id(d))
    return resultado


def _mesmo_dni(a: str, b: str) -> bool:
    limpar = lambda s: s.upper().replace(" ", "").replace("-", "")
    return limpar(a) == limpar(b)


def _parellas_por_respectivamente(persoas: list, dnis: list, texto: str) -> tuple[dict, set]:
    """Cando o texto di "...persoa1 e persoa2, con DNI d1 e d2
    respectivamente", o emparellamento é POR ORDE (a primeira persoa co
    primeiro DNI, a segunda coa segunda...), NON polo veciño máis preto
    (`_asociar_dnis`) -- bug real (A15): "Xoán Páez Veiga e María
    Lozano Duarte, con DNI 11111111H e 22222222J respectivamente" asociaba
    o primeiro DNI á mención máis PRÓXIMA en caracteres (María, por
    estar despois do "e"), intercambiando os dous DNI entre as persoas.
    Como o rexistro indexa por DNI, o erro arrástrase a outros documentos.

    Devolve (dict id(persoa) -> texto do DNI, set de id(dni) xa usados)
    para que o chamador exclúa estas mencións do emparellamento guloso
    xeral -- só actúa cando hai tantas persoas coma DNI na xanela
    inmediatamente anterior a "respectivamente" (se non, é ambiguo e
    non se arrisca a inventar un emparellamento)."""
    parellas: dict = {}
    dnis_usados: set = set()
    for m in _RESPECTIVAMENTE_RE.finditer(texto):
        inicio_xanela = max(0, m.start() - _XANELA_RESPECTIVAMENTE)
        dnis_na_xanela = sorted(
            (d for d in dnis if inicio_xanela <= d.inicio < m.start() and id(d) not in dnis_usados),
            key=lambda d: d.inicio,
        )
        persoas_na_xanela = sorted(
            (p for p in persoas if inicio_xanela <= p.inicio < m.start() and id(p) not in parellas),
            key=lambda p: p.inicio,
        )
        if len(dnis_na_xanela) < 2 or len(dnis_na_xanela) != len(persoas_na_xanela):
            continue  # "respectivamente" sen listas de igual lonxitude: ambiguo, non arriscar
        if persoas_na_xanela[-1].fin > dnis_na_xanela[0].inicio:
            continue  # as persoas teñen que vir TODAS antes có primeiro DNI
        for persoa, dni in zip(persoas_na_xanela, dnis_na_xanela):
            parellas[id(persoa)] = dni.texto
            dnis_usados.add(id(dni))
    return parellas, dnis_usados


def documentos_por_grupo(grupos: list, entidades: list, texto: str) -> dict:
    """id(documento de identidade) -> grupo do seu titular, para que o
    documento reciba O MESMO código ca o nome (decisión do usuario,
    29/09/2026: "son datos da mesma persoa"). Antes só se ligaba o DNI
    completo que `agrupar` asociara (e con outro código, ID_n); no corpus
    web a maioría quedaban soltos coma "[DNI_NIE]"/"[PASAPORTE]".

    Por orde de fiabilidade: (1) a mesma fila dunha táboa PDF, se nela hai
    unha soa persoa; (2) o DNI que `agrupar` xa asociou ao grupo (todas as
    súas aparicións); (3) a mención máis preta, coas regras de `_emparellar`.
    Non cambia `grupo.dni`: o rexistro entre documentos segue indexando só
    DNI/NIE completos (un DNI enmascarado "***4567**" ou un pasaporte
    parcial non abonda para dicir que dúas persoas son a mesma)."""
    grupo_da_mencion = {id(m): g for g in grupos for m in g.mencions}
    mencions = [m for g in grupos for m in g.mencions]
    documentos = [e for e in entidades if e.etiqueta in DOCUMENTOS_DE_IDENTIDADE]
    resultado = {}

    mencions_por_fila: dict = {}
    for m in mencions:
        if m.fila is not None:
            mencions_por_fila.setdefault(m.fila, []).append(m)
    for d in documentos:
        na_fila = mencions_por_fila.get(d.fila, []) if d.fila is not None else []
        if len({id(grupo_da_mencion[id(m)]) for m in na_fila}) == 1:
            resultado[id(d)] = grupo_da_mencion[id(na_fila[0])]

    for g in grupos:
        if g.dni:
            for d in documentos:
                if id(d) not in resultado and d.etiqueta == "DNI_NIE" and _mesmo_dni(d.texto, g.dni):
                    resultado[id(d)] = g

    grupos_con_documento = {id(g) for g in resultado.values()}
    libres = [m for m in mencions if id(grupo_da_mencion[id(m)]) not in grupos_con_documento]
    # Nunca por proximidade a través dun "ANEXO" ou da cabeceira dunha táboa
    # de documentos: o pasaporte do anexo levaba o código de quen asina enriba
    # (AnuncioG0759-281025-0002, auditoría do rexistro, lote 4).
    restantes = [d for d in documentos if id(d) not in resultado]
    for m, d in _emparellar(libres, restantes, texto):
        a, b = sorted((m.fin, d.inicio)) if m.fin <= d.inicio else sorted((d.fin, m.inicio))
        if _FRONTEIRA_ANEXO_RE.search(texto, a, b):
            continue
        resultado[id(d)] = grupo_da_mencion[id(m)]
    return resultado


def _abreviatura_compatible(completo: str, abreviado: str) -> bool:
    """"Elena E. Ramírez Duarte" é unha forma de "Elena Esperanza Ramírez Duarte":
    mesmas palabras, ou a inicial dunha delas."""
    a, b = normalizar(completo).split(), normalizar(abreviado).split()
    if len(a) != len(b) or a == b:
        return False
    return all(x == y or (re.fullmatch(r"[a-z]\.", y) and x[0] == y[0]) for x, y in zip(a, b))


def _unir_abreviatura_entre_parenteses(grupos: list, persoas: list, texto: str) -> None:
    """"doña Elena Esperanza Ramírez Duarte (Elena E. Ramírez Duarte)" (BOE-A-2025-9720):
    a forma abreviada entre parénteses XUSTO DETRÁS do nome completo é a mesma
    persoa (decisión do usuario, 11/10/2026). Só nese caso: noutro sitio do texto
    non hai sinal abondo e, ante a dúbida, non se fusiona."""
    grupo_de = {id(m): g for g in grupos for m in g.mencions}
    ordenadas = sorted(persoas, key=lambda e: e.inicio)
    for completo, abreviado in zip(ordenadas, ordenadas[1:]):
        if not re.fullmatch(r"\s*\(\s*", texto[completo.fin:abreviado.inicio]):
            continue
        if not re.match(r"\s*\)", texto[abreviado.fin:]) or not _abreviatura_compatible(completo.texto, abreviado.texto):
            continue
        destino, orixe = grupo_de.get(id(completo)), grupo_de.get(id(abreviado))
        if destino is None or orixe is None or destino is orixe or orixe not in grupos:
            continue
        if orixe.dni and destino.dni and not _mesmo_dni(orixe.dni, destino.dni):
            continue
        destino.mencions.extend(orixe.mencions)
        destino.dni = destino.dni or orixe.dni
        grupos.remove(orixe)
        for m in orixe.mencions:
            grupo_de[id(m)] = destino


def agrupar(entidades: list, texto: str) -> list:
    """Agrupa as mencions de persoa dun documento en grupos (posibles persoas).

    Importante: dous mencions co MESMO nome completo pero con DNI distinto
    preto de cada unha son homonimos e NON se fusionan -- e xustamente o
    caso que o informe (seccion 03) marca como o mais delicado."""
    persoas = [e for e in entidades if e.etiqueta == "PERSOA"]
    dnis = [e for e in entidades if e.etiqueta == "DNI_NIE"]

    # "...persoa1 e persoa2, con DNI d1 e d2 respectivamente" resólvese POR
    # ORDE antes do emparellamento guloso xeral (ver A15 en `_parellas_
    # por_respectivamente`): sen isto, o veciño máis próximo intercambiaría
    # os DNI entre as dúas persoas.
    dni_por_mencion_id, dnis_usados_respectivamente = _parellas_por_respectivamente(persoas, dnis, texto)
    persoas_restantes = [p for p in persoas if id(p) not in dni_por_mencion_id]
    dnis_restantes = [d for d in dnis if id(d) not in dnis_usados_respectivamente]
    dni_por_mencion_id.update(_asociar_dnis(persoas_restantes, dnis_restantes, texto))
    dni_por_mencion = {id(m): dni_por_mencion_id.get(id(m)) for m in persoas}
    contexto_por_mencion = {id(m): _buscar_contexto(texto, m.fin) for m in persoas}

    grupos: list = []
    pendentes_apelido = []

    for mencion in persoas:
        if len(mencion.texto.split()) < 2:
            pendentes_apelido.append(mencion)
            continue

        chave = normalizar(mencion.texto)
        dni_m = dni_por_mencion[id(mencion)]
        candidato = None

        for g in grupos:
            if normalizar(g.representante) != chave:
                continue
            if dni_m and g.dni:
                if _mesmo_dni(dni_m, g.dni):
                    candidato = g
                    break
                continue  # mesmo nome, DNI distinto -> son persoas distintas
            if not dni_m and not g.dni:
                candidato = g
                break
            # un ten DNI e o outro non: sinal insuficiente para fusionar
            # automaticamente, sae do bucle e crease un grupo novo.

        if candidato is not None:
            candidato.mencions.append(mencion)
        else:
            novo = Grupo(
                representante=mencion.texto,
                dni=dni_m,
                contexto=contexto_por_mencion[id(mencion)],
            )
            novo.mencions.append(mencion)
            grupos.append(novo)

    # Nun escrito xurídico a persoa identifícase co DNI na PRIMEIRA mención e
    # nas seguintes só co nome (indicación do usuario, 28/09/2026). Antes, esas
    # mencións sen DNI quedaban coma outra persoa (outro código, marcada coma
    # posible homónimo), e en modo automático ninguén o resolvía. Se no
    # documento hai UN SÓ DNI para ese nome, son esa persoa, sexa cal sexa a
    # orde. Con dous ou máis DNI distintos co mesmo nome (pai e fillo) segue
    # sen haber sinal para escoller: quedan á parte, coma antes.
    for sen_dni in [g for g in grupos if not g.dni]:
        chave = normalizar(sen_dni.representante)
        con_dni = [g for g in grupos if g.dni and normalizar(g.representante) == chave]
        if len(con_dni) == 1:
            con_dni[0].mencions.extend(sen_dni.mencions)
            grupos.remove(sen_dni)

    # "El Sr. Iscar Molina" tras "Don Manuel Iscar Molina" (corpus web lote
    # 2, 30/09/2026): os apelidos sen o nome son a mesma persoa se hai UN SÓ
    # nome completo no documento que remate neles. Antes levaban outro código.
    for parcial in [g for g in grupos if not g.dni]:
        chave = normalizar(parcial.representante)
        completos = [
            g for g in grupos
            if g is not parcial and (normalizar(g.representante).endswith(" " + chave)
                                     # "Manuel Sobral" tras "Manuel Sobral Lourido"
                                     # (BOE-A-2026-1546, lectura do usuario 03/10/2026).
                                     or (" " in chave and normalizar(g.representante).startswith(chave + " ")))
        ]
        if len(completos) == 1:
            completos[0].mencions.extend(parcial.mencions)
            grupos.remove(parcial)

    _unir_abreviatura_entre_parenteses(grupos, persoas, texto)

    # Mencions dun so apelido intentan pegarse a un unico grupo compatible
    # (por apelido); se hai ambiguidade, quedan como grupo propio marcado.
    for mencion in pendentes_apelido:
        apelido = normalizar(mencion.texto)
        candidatos = [
            g for g in grupos
            if apelido and normalizar(g.representante).split()[-1] == apelido
        ]
        if len(candidatos) == 1:
            candidatos[0].mencions.append(mencion)
        else:
            novo = Grupo(
                representante=mencion.texto,
                dni=dni_por_mencion[id(mencion)],
                contexto=contexto_por_mencion[id(mencion)],
                ambiguo=True,
                motivo_ambiguidade=(
                    "mencion por apelido solto sen un unico nome completo "
                    "compatible no documento"
                ),
            )
            novo.mencions.append(mencion)
            grupos.append(novo)

    return grupos
