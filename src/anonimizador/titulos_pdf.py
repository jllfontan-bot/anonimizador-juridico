"""Títulos nun PDF con texto, polo tamaño da letra (ESTUDIO-CONVERSOR-MD,
fase 5). SÓ para o conversor a .md: nin a copia .md do anonimizador nin o PDF
anonimizado usan este módulo.

Un PDF non garda que unha liña é un título; o único rastro fiable é que vai
en letra máis grande ca o corpo do texto. O criterio é o de `pymupdf4llm`
(tamaño máis frecuente = corpo; os maiores, niveis de título) coas gardas
que necesita un documento real, medidas sobre o corpus do BOE e do DOG:

- Negra, cursiva ou MAIÚSCULAS NON fan un título: o corpo dun escrito
  xurídico vai a miúdo en negra ou en maiúsculas (nomes de partes,
  «ANEXO», «HECHOS»). Só conta o tamaño.
- O corpo é o tamaño con máis caracteres do documento; un título leva
  polo menos `_SALTO_MINIMO` puntos máis e un `_RATIO_MINIMO` de máis.
- Fóra: liñas sen letras (números de páxina, o «18399» do BOE) ou con
  letras matemáticas (fórmulas), as que comparten fila con outra liña
  (cabeceiras de columnas, celas), as das marxes de arriba e de abaixo da páxina (cabeceira e pé), as que se
  repiten en varias páxinas, as moi longas (un parágrafo en letra grande
  non é un título; tampouco un tamaño con moitas liñas longas, que é a
  prosa dun documento de corpo pequeno) e todo o documento se máis dunha cuarta parte do seu
  texto sairía en título (non hai un corpo claro: cartaz, diapositivas).
- Niveis: un por cada tamaño distinto (a máis dun punto de diferenza), de
  maior a menor, ata `NIVEIS_MAXIMOS`. As liñas seguidas do mesmo tamaño son un só título
  (títulos partidos en varias liñas).

- Estruturais («Artigo 1.», «ANEXO I», «CAPÍTULO II», «Disposición final»...):
  só se a liña COMEZA por esa palabra e vai en negra, en maiúsculas ou en
  cursiva (como o BOE e o DOG os escriben), curta e soa; ver `_rango_estrutural`.

`detectar_titulos` devolve onde está cada título no texto da páxina, que é
o que le `pdf_estrutura`; o texto do título non se le de aquí.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

import fitz  # PyMuPDF

NIVEIS_MAXIMOS = 4

_SALTO_MINIMO = 1.0  # puntos por riba do corpo
_RATIO_MINIMO = 1.08
_DIFERENCIA_DE_NIVEL = 1.0  # puntos entre dous niveis de título
_MARXE_PAXINA = 0.06  # fracción da altura: cabeceira e pé
_LONGO_MAXIMO_LIÑA = 150
_LONGO_MAXIMO_TITULO = 150
_LIÑAS_MAXIMAS_TITULO = 3
_PALABRAS_MAXIMAS = 14
_PALABRAS_FRASE = 8  # con punto final
_MINIMO_TEXTO_CORRIDO = 8  # liñas dun tamaño con media longa: texto, non títulos
_LONGO_TEXTO_CORRIDO = 55
_FRACCION_MAXIMA = 0.25  # de caracteres do documento en letra de título
_PALABRAS_ESTRUTURAL = 12  # o que vai despois de «Artigo 1.» nun título estrutural
_LONGO_ESTRUTURAL = 100
_NIVEIS_TOTAIS = 6
# O BOE e o DOG escriben «Artículo 1. Objeto.» en letra normal co nome en cursiva, nin en
# negra nin en maiúsculas. Con isto, unha liña en cursiva (a partir do 25 % das letras) que
# comeza en maiúscula cumpre a forma que se pide da negra (medido o 31/10/2026 sobre 1770 PDF:
# 1072 artigos, seccións e disposicións máis, 45 de 45 revisados a man correctos).
_ADMITE_CURSIVA = True
_HUECO_MAXIMO = 2.0  # entre anacos dunha mesma fila, en tamaños de letra
_SEPARACION_MAXIMA = 1.7  # entre a parte de arriba de dúas liñas dun mesmo título, en tamaños de letra

_LETRAS = re.compile(r"[^\W\d_]")
_DIXITOS = re.compile(r"\d+")
# Espazos para encher (....., …), campos de formulario («Centro de destino: X»)
# e a data dunha sinatura («Santiago de Compostela, 25 de setembro de 2024»).
_NON_TITULO = re.compile(r"\.{4,}|…|:\s*\S{3}|\d{1,2} de \w+ de \d{4}\s*$", re.IGNORECASE)
_FONTE_NEGRA = re.compile(r"bold|black|heavy|[-,]bd\b", re.IGNORECASE)
_FONTE_CURSIVA = re.compile(r"italic|oblique", re.IGNORECASE)
_MATEMATICAS = re.compile("[\U0001d400-\U0001d7ff]")  # letras matemáticas: unha fórmula


@dataclass
class Titulo:
    paxina: int  # 0-based
    inicio: int  # offset no texto DESTA páxina (`_PaxinaPdf.texto`)
    fin: int
    nivel: int  # 1 = o maior
    grupo: int = 0  # as liñas dun mesmo título (partido en varias) comparten grupo


@dataclass
class _Liña:
    paxina: int
    rect: tuple
    texto: str
    tamano: float
    caracteres: int
    horizontal: bool = True
    negra: bool = False  # polo menos o 90 % das letras en negra
    cursiva: bool = False  # polo menos o 25 % das letras en cursiva


def _tamano(valor: float) -> float:
    return round(valor * 2) / 2


def _liñas_da_paxina(pagina: "fitz.Page", numero: int) -> list:
    liñas = []
    for bloque in pagina.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)["blocks"]:
        for liña in bloque.get("lines", ()):
            por_tamano, en_negra, en_cursiva = Counter(), 0, 0
            for span in liña["spans"]:
                por_tamano[_tamano(span["size"])] += len(span["text"].strip())
                if _FONTE_NEGRA.search(span["font"]) or span["flags"] & 16:
                    en_negra += len(span["text"].strip())
                if _FONTE_CURSIVA.search(span["font"]) or span["flags"] & 2:
                    en_cursiva += len(span["text"].strip())
            texto = " ".join("".join(s["text"] for s in liña["spans"]).split())
            if texto and por_tamano:
                tamano, caracteres = max(por_tamano.items(), key=lambda t: (t[1], t[0]))
                horizontal = tuple(round(c) for c in liña["dir"]) == (1, 0)
                negra = en_negra >= 0.9 * sum(por_tamano.values())
                cursiva = en_cursiva >= 0.25 * sum(por_tamano.values())
                liñas.append(_Liña(numero, tuple(liña["bbox"]), texto, tamano, caracteres, horizontal, negra, cursiva))
    return _fusionar_fragmentos(liñas)


def _fusionar_fragmentos(liñas: list) -> list:
    """Un texto xustificado ou con espazos grandes sae en anacos soltos da
    mesma fila («CONSELLERÍA», «DE», «EDUCACIÓN,»...): xúntanse os do mesmo
    tamaño que están xunto, cunha separación de ata `_HUECO_MAXIMO`
    tamaños de letra. A orde das liñas non cambia (o anaco que xunta
    ocupa o lugar do primeiro)."""
    saida = []
    for l in liñas:
        if l.horizontal:
            for k in range(len(saida) - 1, max(len(saida) - 40, -1), -1):
                o = saida[k]
                if (o.horizontal and o.tamano == l.tamano and abs(o.rect[1] - l.rect[1]) <= 0.35 * l.tamano
                        and min(abs(l.rect[0] - o.rect[2]), abs(o.rect[0] - l.rect[2])) <= _HUECO_MAXIMO * l.tamano
                        and (l.rect[0] >= o.rect[2] - 1 or o.rect[0] >= l.rect[2] - 1)):
                    primeiro, segundo = (o, l) if o.rect[0] <= l.rect[0] else (l, o)
                    saida[k] = _Liña(o.paxina, (min(o.rect[0], l.rect[0]), min(o.rect[1], l.rect[1]),
                                                max(o.rect[2], l.rect[2]), max(o.rect[3], l.rect[3])),
                                     primeiro.texto + " " + segundo.texto, o.tamano, o.caracteres + l.caracteres,
                                     True, o.negra and l.negra, o.cursiva and l.cursiva)
                    break
            else:
                saida.append(l)
        else:
            saida.append(l)
    return saida


def _clave_repetida(texto: str) -> str:
    return _DIXITOS.sub("#", texto.casefold())


def _niveis(candidatas: list, corpo: float) -> dict:
    """Tamaño -> nivel. Dous tamaños a menos de `_DIFERENCIA_DE_NIVEL` puntos
    son o mesmo nivel (no BOE a sección vai en 15 pt e o organismo en 15,7)."""
    niveis, nivel, anterior = {}, 0, None
    for tamano in sorted({l.tamano for l in candidatas if l.tamano >= corpo + _SALTO_MINIMO}, reverse=True):
        if anterior is None or anterior - tamano > _DIFERENCIA_DE_NIVEL:
            nivel = min(nivel + 1, NIVEIS_MAXIMOS)
        niveis[tamano] = nivel
        anterior = tamano
    return niveis


def _na_mesma_fila(l: _Liña, outras: list) -> bool:
    """Outra liña da páxina, doutro sitio, que se solapa en vertical: unha
    cabeceira de varias columnas («DOG Núm.  |  data  |  Páx.»), unha cela
    ou unha fórmula, non un título."""
    alto = l.rect[3] - l.rect[1]
    for o in outras:
        if o is l or not o.horizontal:  # o texto vertical do margo (cve, «Verificable en…») non é unha fila
            continue
        solape = min(l.rect[3], o.rect[3]) - max(l.rect[1], o.rect[1])
        if solape > 0.5 * min(alto, o.rect[3] - o.rect[1]):
            return True
    return False


def _tamanos_de_texto_corrido(liñas: list, corpo: float) -> set:
    """Tamaños maiores ca o corpo que levan texto corrido (o dominante é a
    letra pequena dunha táboa e a prosa vai nun tamaño maior): moitas liñas
    e longas. Un título é curto."""
    longos = {}
    for l in liñas:
        if l.horizontal and l.tamano > corpo:
            longos.setdefault(l.tamano, []).append(len(l.texto))
    return {t for t, v in longos.items()
            if len(v) >= _MINIMO_TEXTO_CORRIDO and sorted(v)[len(v) // 2] >= _LONGO_TEXTO_CORRIDO}


def _liñas_de_titulo(liñas: list, altos: list, corpo: float) -> list:
    """As liñas candidatas a título (sen agrupar), nun documento."""
    corridos = _tamanos_de_texto_corrido(liñas, corpo)
    repetidas = Counter()
    if len(altos) > 1:
        for _, clave in {(l.paxina, _clave_repetida(l.texto)) for l in liñas}:
            repetidas[clave] += 1
    por_paxina = {}
    for l in liñas:
        por_paxina.setdefault(l.paxina, []).append(l)
    candidatas = []
    for l in liñas:
        if not l.horizontal or l.tamano < corpo + _SALTO_MINIMO or l.tamano < corpo * _RATIO_MINIMO:
            continue
        if l.tamano in corridos:
            continue
        if not _LETRAS.search(l.texto) or len(l.texto) > _LONGO_MAXIMO_LIÑA or _MATEMATICAS.search(l.texto):
            continue
        alto = altos[l.paxina]
        centro = (l.rect[1] + l.rect[3]) / 2
        if centro < alto * _MARXE_PAXINA or centro > alto * (1 - _MARXE_PAXINA):
            continue
        if repetidas[_clave_repetida(l.texto)] > 1 or _na_mesma_fila(l, por_paxina[l.paxina]):
            continue
        candidatas.append(l)
    return candidatas


def _agrupar(candidatas: list) -> list:
    """Liñas seguidas do mesmo tamaño (mesma páxina, case sen espazo de por
    medio) -> unha lista de liñas por título."""
    grupos = []
    for l in candidatas:
        if grupos:
            ultima = grupos[-1][-1]
            if (ultima.paxina == l.paxina and ultima.tamano == l.tamano
                    and 0 < l.rect[1] - ultima.rect[1] <= l.tamano * _SEPARACION_MAXIMA):
                grupos[-1].append(l)
                continue
        grupos.append([l])
    return grupos


def _intervalo(palabras: list, rect: tuple) -> tuple | None:
    """Offsets (inicio, fin) das palabras da páxina cuxo centro cae na caixa
    da liña, ou `None`."""
    x0, y0, x1, y1 = rect
    dentro = [p for p in palabras
              if x0 - 1 <= (p.rect[0] + p.rect[2]) / 2 <= x1 + 1 and y0 - 1 <= (p.rect[1] + p.rect[3]) / 2 <= y1 + 1]
    return (min(p.inicio for p in dentro), max(p.fin for p in dentro)) if dentro else None


def _semella_frase(texto: str) -> bool:
    """Un título non é unha frase: non continúa unha anterior (empeza en
    minúscula ou remata en coma), non é o rótulo dun campo (remata en dous
    puntos), non é longa (máis de `_PALABRAS_MAXIMAS`) nin remata en punto
    cunha boa tirada de palabras (sinaturas, parágrafos en letra grande), e
    non é un campo de formulario ou unha data (`_NON_TITULO`)."""
    primeira = next((c for c in texto if c.isalpha()), "")
    palabras = len(texto.split())
    return (primeira.islower() or palabras > _PALABRAS_MAXIMAS
            or (texto.rstrip().endswith(".") and palabras >= _PALABRAS_FRASE)
            or texto.rstrip().endswith((",", ":")) or bool(_NON_TITULO.search(texto)))


# -- títulos estruturais: «Artigo 1.», «ANEXO I», «CAPÍTULO II»... en negra ao
# tamaño do corpo (e, polo tanto, invisibles para o criterio do tamaño) ------

_ORDINAL = (r"(?:[úu]nic[oa]|primer[oa]?|segund[oa]|tercer[oa]?|cuart[oa]|quint[oa]|sext[oa]|s[ée]ptim[oa]|octav[oa]|"
            r"noven[oa]|d[ée]cim[oa]|undécim[oa]|duod[ée]cim[oa]|preliminar|[ivxlc]+|\d+(?:\.\d+)*[.ºª°]*)")
# Lista pechada: (rango, expresión). O rango só ordena os niveis (1 = o máis alto).
_ESTRUTURAIS = (
    (1, re.compile(r"(?:anexo|anexos)(?:\s+" + _ORDINAL + r")?(?![\w])", re.IGNORECASE)),
    (1, re.compile(r"t[ií]tulo\s+" + _ORDINAL + r"(?![\w])", re.IGNORECASE)),
    (2, re.compile(r"cap[ií]tulo\s+" + _ORDINAL + r"(?![\w])", re.IGNORECASE)),
    (3, re.compile(r"secci[óo]n\s+" + _ORDINAL + r"(?![\w])", re.IGNORECASE)),
    (4, re.compile(r"(?:art[ií]culo|artigo)\s+(?:\d+(?:\.\d+)*[.ºª°]*(?:\s*(?:bis|ter|qu[aá]ter|quinquies))?|[úu]nic[oa])(?![\w])",
                   re.IGNORECASE)),
    (4, re.compile(r"disposici[óo]ns?\s+(?:adicional|transitoria|derogatoria|final|adicionais|transitorias|derogatorias|finais)"
                   r"(?:\s+" + _ORDINAL + r")?(?![\w])", re.IGNORECASE)),
)
_RELLENO = re.compile(r"\.{4,}|…|\d{1,2} de \w+ de \d{4}\s*$", re.IGNORECASE)


def _rango_estrutural(l: _Liña) -> int | None:
    """Rango do título estrutural que abre `l`, ou `None`. Só vale unha liña
    que COMEZA por unha palabra da lista, en negra (todo o que leva) ou toda
    en maiúsculas, curta, soa (o que siga a «Artigo 1.» é, como moito, o seu
    nome: se hai un texto, non é un título) e que non é a mención dunha
    norma («artigo 5 da Lei...» non comeza a liña en negra nin en maiúsculas)."""
    texto = l.texto
    forma = l.negra or texto.isupper() or (_ADMITE_CURSIVA and l.cursiva and texto[:1].isupper())
    if len(texto) > _LONGO_ESTRUTURAL or not forma:
        return None
    for rango, expresion in _ESTRUTURAIS:
        m = expresion.match(texto)
        if not m:
            continue
        resto = texto[m.end():].strip()
        if resto:
            primeira = resto[0]
            curto_anexo = rango == 1 and expresion.pattern.startswith("(?:anexo") and len(resto.split()) <= 6
            if not (primeira in ".:–—-«\"“(" or primeira.isupper() or curto_anexo):
                return None  # «Artigo 5 da Lei...»: unha frase
            if (len(resto.split()) > _PALABRAS_ESTRUTURAL or resto.endswith(",") or _RELLENO.search(resto)
                    or (resto.endswith(".") and len(resto.split()) >= _PALABRAS_FRASE)):
                return None
        return rango
    return None


def _con_continuacion(l: _Liña, liñas: list) -> list:
    """`l` e, se o título quedou partido (non remata en punto), as liñas
    seguintes co mesmo tamaño e estilo, pegadas a ela: «Artigo 16. Coordinación
    con equipos de medios adecuados de solución de» / «controversias."""
    grupo = [l]
    k = liñas.index(l)
    while (not grupo[-1].texto.rstrip().endswith((".", ":")) and len(grupo) < _LIÑAS_MAXIMAS_TITULO
           and k + len(grupo) < len(liñas)):
        o = liñas[k + len(grupo)]
        if (o.paxina != l.paxina or not o.horizontal or o.tamano != l.tamano or o.negra != l.negra
                or o.cursiva != l.cursiva or not 0 < o.rect[1] - grupo[-1].rect[1] <= l.tamano * _SEPARACION_MAXIMA
                or _rango_estrutural(o) is not None or sum(len(x.texto) for x in grupo + [o]) > _LONGO_MAXIMO_TITULO):
            break
        grupo.append(o)
    return grupo


def _grupos_estruturais(liñas: list, altos: list, corpo: float, ocupadas: set) -> list:
    """[(rango, [_Liña])] dos títulos estruturais (cada un, as súas liñas). `ocupadas`: ids das liñas
    que xa son título polo tamaño (ou que o tamaño xa rexeitou)."""
    por_paxina = {}
    for l in liñas:
        por_paxina.setdefault(l.paxina, []).append(l)
    repetidas = Counter()
    if len(altos) > 1:  # idéntica en varias páxinas: cabeceira (non «Artigo 1.» e «Artigo 2.»)
        for pax, texto in {(l.paxina, l.texto.casefold()) for l in liñas}:
            repetidas[texto] += 1
    achados = []
    for l in liñas:
        if (not l.horizontal or id(l) in ocupadas or l.tamano < corpo - _SALTO_MINIMO
                or l.tamano >= corpo + _SALTO_MINIMO and l.tamano >= corpo * _RATIO_MINIMO):
            continue
        rango = _rango_estrutural(l)
        if rango is None or _MATEMATICAS.search(l.texto) or repetidas[l.texto.casefold()] > 1:
            continue
        centro = (l.rect[1] + l.rect[3]) / 2
        if centro < altos[l.paxina] * _MARXE_PAXINA or centro > altos[l.paxina] * (1 - _MARXE_PAXINA):
            continue
        if _na_mesma_fila(l, por_paxina[l.paxina]):
            continue
        achados.append((rango, _con_continuacion(l, liñas)))
    return achados


def grupos_de_titulos(documento: "fitz.Document") -> list:
    """Os títulos do documento, na súa orde: cada un, unha lista de
    (`_Liña`, nivel) -- as liñas do PDF que o forman. Primeiro os do tamaño
    da letra; despois, un nivel por debaixo, os estruturais (Artigo, Anexo,
    Capítulo...) en negra ou maiúsculas ao tamaño do corpo."""
    liñas, altos = [], []
    for i, pagina in enumerate(documento):
        altos.append(pagina.rect.height)
        if not pagina.rotation:  # as palabras de `pdf_estrutura` van en coordenadas sen rotar
            liñas.extend(_liñas_da_paxina(pagina, i))
    total = Counter()
    for l in liñas:
        total[l.tamano] += l.caracteres
    if not total:
        return []
    corpo = max(total.items(), key=lambda t: (t[1], t[0]))[0]
    texto_total = sum(total.values())

    candidatas = _liñas_de_titulo(liñas, altos, corpo)
    por_tamano, base = [], 0
    if sum(l.caracteres for l in candidatas) <= _FRACCION_MAXIMA * texto_total:
        niveis = _niveis(candidatas, corpo)
        por_tamano = [[(l, niveis[l.tamano]) for l in grupo]
                      for grupo in _agrupar(candidatas)
                      if len(grupo) <= _LIÑAS_MAXIMAS_TITULO and sum(len(l.texto) for l in grupo) <= _LONGO_MAXIMO_TITULO
                      and not _semella_frase(" ".join(l.texto for l in grupo))]
        base = max((nivel for grupo in por_tamano for _, nivel in grupo), default=0)

    # Lectura grande (letra por riba do corpo): xa a tratou o tamaño, ben ou rexeitada.
    ocupadas = {id(l) for l in liñas if l.tamano >= corpo + _SALTO_MINIMO and l.tamano >= corpo * _RATIO_MINIMO}
    estruturais = _grupos_estruturais(liñas, altos, corpo, ocupadas)
    if sum(x.caracteres for _, grupo in estruturais for x in grupo) > _FRACCION_MAXIMA * texto_total:
        estruturais = []
    posicion = {id(l): k for k, l in enumerate(liñas)}
    rangos = sorted({rango for rango, _ in estruturais})
    grupos = [(posicion[id(grupo[0][0])], grupo) for grupo in por_tamano]
    for rango, ls in estruturais:
        nivel = min(base + rangos.index(rango) + 1, _NIVEIS_TOTAIS)
        grupos.append((posicion[id(ls[0])], [(x, nivel) for x in ls]))
    return [grupo for _, grupo in sorted(grupos, key=lambda g: g[0])]


def detectar_titulos(documento: "fitz.Document", paxinas: list) -> list:
    """`documento` e `paxinas` (`contexto["paxinas"]`, as `_PaxinaPdf` coas súas
    palabras): lista de `Titulo`, na orde do documento, un por liña do PDF;
    as liñas dun mesmo título comparten `grupo`."""
    if len(paxinas) != len(documento):
        return []
    titulos = []
    for grupo, liñas in enumerate(grupos_de_titulos(documento)):
        for l, nivel in liñas:
            intervalo = _intervalo(paxinas[l.paxina].palabras, l.rect)
            if intervalo:
                titulos.append(Titulo(l.paxina, intervalo[0], intervalo[1], nivel, grupo))
    return titulos


def _liñas_do_titulo(anon: str, mapa, titulos_do_grupo: list) -> list:
    """Liñas (xa anonimizadas) do texto que ocupa un título na súa páxina."""
    inicio = min(t.inicio for t in titulos_do_grupo)
    fin = max(t.fin for t in titulos_do_grupo)
    return [l.strip() for l in anon[mapa.anon(inicio, final=False):mapa.anon(fin, final=True)].split("\n") if l.strip()]


def marcar_titulos_md(md: str, contexto: dict | None, texto_final: str, substitucions: list | None = None) -> str:
    """`md`: o Markdown que dá `copia_md.xerar(contexto, texto_final,
    substitucions)` dun PDF con texto. Devolve o mesmo cos títulos como
    `#`. O texto de cada título sae do `texto_final` (xa anonimizado, coas
    mesmas substitucións que o resto): do PDF só se le onde está e canto
    mide a letra. Un título que non se atopa en `md` liña a liña (unha táboa,
    un texto reordenado) queda sen marcar. Sen títulos, ou noutro tipo de
    contexto, `md` tal cal."""
    from .copia_md import _Desprazamentos, _aplicar_substitucions_a_texto, _escapar_liña
    from .pdf_estrutura import SEPARADOR_PAXINAS, _limites_paxinas

    if not contexto or contexto.get("tipo") != "pdf" or contexto.get("imaxe") or contexto.get("documento") is None:
        return md
    paxinas = contexto["paxinas"]
    partes = texto_final.split(SEPARADOR_PAXINAS)
    if len(partes) != len(paxinas):
        return md
    try:
        titulos = detectar_titulos(contexto["documento"], paxinas)
    except Exception:  # noqa: BLE001 -- un PDF raro non pode tumbar a conversión: sen títulos
        return md
    if not titulos:
        return md

    limites = _limites_paxinas(paxinas)
    mapas = {}  # páxina -> mapa de posicións (ou None: a páxina non casa)
    for i in {t.paxina for t in titulos}:
        locais = None if substitucions is None else [
            (s - limites[i][0], f - limites[i][0], n) for s, f, n in substitucions if limites[i][0] <= s and f <= limites[i][1]]
        if locais is not None and _aplicar_substitucions_a_texto(paxinas[i].texto, locais) != partes[i]:
            mapas[i] = None
        else:
            mapas[i] = _Desprazamentos(locais or [])

    grupos = {}
    for t in titulos:
        grupos.setdefault(t.grupo, []).append(t)
    liñas = md.split("\n")
    substitucions_md = {}  # índice da primeira liña -> (nº de liñas, liña nova)
    cursor = 0
    for grupo in sorted(grupos):
        do_grupo = grupos[grupo]
        mapa = mapas[do_grupo[0].paxina]
        if mapa is None:
            continue
        propias = _liñas_do_titulo(partes[do_grupo[0].paxina], mapa, do_grupo)
        if not propias:
            continue
        buscadas = [_escapar_liña(l) for l in propias]
        for k in range(cursor, len(liñas) - len(buscadas) + 1):
            if liñas[k:k + len(buscadas)] == buscadas:
                substitucions_md[k] = (len(buscadas), "#" * do_grupo[0].nivel + " " + " ".join(propias))
                cursor = k + len(buscadas)
                break
    if not substitucions_md:
        return md
    saida, k = [], 0
    while k < len(liñas):
        if k in substitucions_md:
            n, nova = substitucions_md[k]
            if saida and saida[-1]:
                saida.append("")
            saida.append(nova)
            k += n
            if k < len(liñas) and liñas[k]:
                saida.append("")
        else:
            saida.append(liñas[k])
            k += 1
    return "\n".join(saida)
