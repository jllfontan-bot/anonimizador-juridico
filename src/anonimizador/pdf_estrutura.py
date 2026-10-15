"""Conservación do formato E EXTENSIÓN orixinais en PDF (informe: "que
sempre manteña o formato e extensión do arquivo orixinal"), tanto con
texto nativo coma escaneado -- o mesmo nivel de esixencia que xa existía
para `.docx`/`.odt` (`pipeline.cargar_documento_estruturado` /
`gardar_documento_estruturado`), aplicado agora tamén a PDF.

Deseño (paralelo ao de .docx/.odt, pero a nivel de PALABRA en vez de
"run"/"span", pola natureza visual do PDF):

1. Cárgase cada páxina PALABRA A PALABRA -- texto nativo con
   `pagina.get_text("words")`, ou OCR con `pytesseract.image_to_data`
   (bounding boxes) nas páxinas sen capa de texto extraíble -- gardando
   para cada palabra o seu rectángulo exacto na páxina.
2. A detección de entidades (NER/patróns) funciona igual ca sempre sobre
   o texto conxunto reconstruído a partir desas palabras.
3. Ao gardar, cada substitución mapéase de volta ás palabras que cobre
   (gránulo de PALABRA enteira, non de carácter -- a diferenza de
   .docx/.odt onde se traballa por carácter dentro dunha "run"), e:
   - Redáctase o rectángulo (`add_redact_annot` + `apply_redactions`,
     que elimina de VERDADE o contido orixinal -- texto vectorial ou
     píxeles de imaxe nunha páxina escaneada, non so o tapa visualmente).
   - Insírese o código de substitución nese rectángulo, con axuste
     automático do tamaño de letra para que caiba.
   Se un letrado editou a man o texto dunha páxina de xeito que xa non
   coincide co que producirían as substitucións orixinais, esa páxina
   completa cae na reserva -- redáctase enteira e reescríbese co texto
   editado en fonte xenérica -- para non arriscar debuxar código encima
   de contido que xa non lle corresponde.
"""

from __future__ import annotations

import difflib
import re
import shutil
import unicodedata
from dataclasses import dataclass, field

import cv2
import fitz  # PyMuPDF
import numpy as np
import pytesseract

from . import sen_consola, taboas_pdf

# Sen consolas que parpadeen en Windows (ver `sen_consola.py`).
sen_consola.aplicar()
from PIL import Image
from pytesseract import Output

from .pdf import (
    _CONFIG_TESSERACT,
    _DPI_OCR,
    _LONGO_ABONDO,
    TesseractNonInstalado,
    _idioma_dispoñible,
    _preprocesar,
)

# Bug real atopado nunha carta escaneada: unha liña en branco SOLTA
# ("\n\n") é un salto de parágrafo completamente normal dentro do texto
# dunha páxina (moi habitual en cartas -- saúdo, corpo, enderezo, sinatura
# -- cada bloque separado por unha liña en branco propia). Usala tamén
# coma separador ENTRE páxinas facía que `gardar_pdf_estruturado` contase
# MÁIS "páxinas" das que hai de verdade en canto o documento tiña un só
# parágrafo con salto interno, e caía sempre no respaldo de texto plano
# (perdendo o PDF orixinal) aínda sen editar nada a man. O carácter de
# "form feed" (`\f`, 0x0C) é o separador clásico de páxina en texto plano
# e NON aparece en texto real extraído dun PDF (nin nativo nin OCR) --
# flanqueado por saltos de liña, segue a parecer unha liña en branco na
# caixa de revisión, pero xa non se confunde cun salto de parágrafo.
SEPARADOR_PAXINAS = "\n\f\n"

_FONTE_SAIDA = "helv"
_MARXE_INSERCION = 1.5  # puntos PDF, para que o texto novo non toque o bordo do rectángulo

# Corrección atopada probando contra un documento real: nunha marxe con
# texto vertical (moi habitual en rexistros mercantís/notariais -- o
# número de inscrición impreso ao longo do lateral da folla), o código de
# substitución inseríase sempre en HORIZONTAL, solapando e facendo
# ilexible tanto o código coma o propio texto vertical orixinal. PyMuPDF
# expón a dirección de cada LIÑA de texto nativo (`get_text("dict")`,
# campo "dir": un vector -- (1,0) horizontal, (0,-1) vertical cara arriba,
# (-1,0) horizontal invertido, (0,1) vertical cara abaixo) -- isto mapea
# ese vector ao ángulo de rotación máis próximo (0/90/180/270) para poder
# inserir o código coa MESMA orientación ca o texto que substitúe.
_DIRECCION_A_GRAOS = (((1, 0), 0), ((0, -1), 90), ((-1, 0), 180), ((0, 1), 270))


def _rotacion_mais_preto(direccion: tuple) -> int:
    dx, dy = direccion
    return min(
        _DIRECCION_A_GRAOS,
        key=lambda par: (par[0][0] - dx) ** 2 + (par[0][1] - dy) ** 2,
    )[1]


@dataclass
class _PalabraPaxina:
    inicio: int  # offset local (dentro do texto DESTA páxina)
    fin: int
    rect: tuple  # (x0, y0, x1, y1) en puntos PDF
    rotacion: int = 0  # 0/90/180/270 -- ver _DIRECCION_A_GRAOS
    # O dato ten tinta en PÍXELES: palabra lida por OCR, ou nativa (capa de
    # texto de escaneo) que un OCR duplica. Alí hai que tapar o rectángulo
    # enteiro; nas demais (texto vectorial) chega con recortar.
    ocr: bool = False


@dataclass
class _PaxinaPdf:
    texto: str
    palabras: list = field(default_factory=list)  # list[_PalabraPaxina]
    # Celas de columnas de dato persoal das táboas (`taboas_pdf.py`), en
    # offsets locais coma `palabras`.
    celas: list = field(default_factory=list)  # list[taboas_pdf.CelaDatoPersoal]


_VECIÑANZA_VECES = 4.0  # canto máis lonxe (en alturas propias) se busca veciñas
_MOSTRA_MINIMA_VECIÑANZA = 3  # menos ca isto preto -> non hai referencia fiable


def _mediana(valores: list) -> float:
    ordenados = sorted(valores)
    meio = len(ordenados) // 2
    if len(ordenados) % 2:
        return ordenados[meio]
    return (ordenados[meio - 1] + ordenados[meio]) / 2


def _altura_veciña(palabras: list, rect_alvo: tuple, excluir: frozenset = frozenset()) -> float | None:
    """Mediana da altura das palabras VECIÑAS (preto verticalmente) de
    `rect_alvo`, para usar coma referencia de tamaño de letra plausible.
    `excluir` son as propias palabras que se están a substituír (por
    identidade, non por posición -- varias palabras poderían compartir
    coordenadas nun documento patolóxico).

    A propósito NON se usa a páxina enteira: unha cabeceira grande
    LEXÍTIMA (ex. un código de expediente en letra moi grande, illado,
    nunha portada) tería un tamaño moi distinto ao corpo de texto do
    resto da páxina, e limitalo á mediana global estragaría ese caso real
    (atopado probando este mesmo arranxo). Mirando só as palabras preto
    dela, unha cabeceira illada non ten "veciñas" abondas para comparar
    (e non se limita), mentres que un bounding box anómalo nunha táboa
    densa SI ten veciñas moi próximas de tamaño normal (e sinala o
    anómalo). Devolve `None` se non hai mostra abonda para confiar nela."""
    altura_alvo = rect_alvo[3] - rect_alvo[1]
    if altura_alvo <= 0:
        return None
    centro_y = (rect_alvo[1] + rect_alvo[3]) / 2
    limiar = altura_alvo * _VECIÑANZA_VECES

    alturas = []
    for p in palabras:
        if id(p) in excluir:
            continue
        altura_p = p.rect[3] - p.rect[1]
        if altura_p <= 0:
            continue
        centro_p = (p.rect[1] + p.rect[3]) / 2
        if abs(centro_p - centro_y) <= limiar:
            alturas.append(altura_p)

    if len(alturas) < _MOSTRA_MINIMA_VECIÑANZA:
        return None
    return _mediana(alturas)


# Fuga atopada nunha auditoría (A22): un encabezado con LETREADO
# EXPANDIDO -- o operador `Tc` do PDF (espazado entre caracteres) posto a
# un valor alto, recurso tipográfico moi habitual en portadas e
# encabezados ("D E M A N D A N T E : J U A N   P E R E Z") -- chega a
# `get_text("words")` coma unha palabra POR CADA LETRA. O texto
# reconstruído era "J U A N  P E R E Z", que nin o NER nin os patróns
# recoñecen (nin sequera saltaba a rede de seguridade de
# `risco_residual.py`: "J U A N" non parece un nome), así que o nome e o
# DNI saían intactos.
#
# A pista para distinguilo dunha liña con palabras de verdade separadas
# está na GEOMETRÍA, non no texto: nunha liña letreada a separación entre
# letras dunha mesma palabra é moi pequena comparada coa altura da letra,
# e a separación entre palabras é claramente maior. Por iso só se colapsa
# cando a liña é maioritariamente de letras soltas E a separación típica
# entre elas é menor ca a altura da letra -- unha fila de táboa con
# columnas dun só carácter ("1  2  3  4") ten separacións moito máis
# grandes ca a altura e NON se colapsa.
_LETREADO_SOLTAS_MINIMAS = 4
_LETREADO_PROPORCION_SOLTAS = 0.7
_LETREADO_SEPARACION_MAXIMA = 1.0  # veces a altura da letra
_LETREADO_FOLGURA_PALABRA = 1.6  # veces a separación mediana -> límite de palabra


def _separacion(anterior: tuple, seguinte: tuple, vertical: bool) -> float:
    """Oco entre dous rectángulos consecutivos NA DIRECCIÓN DE LECTURA."""
    if vertical:
        return seguinte[1] - anterior[3]
    return seguinte[0] - anterior[2]


def _colapsar_letreado(items: list) -> list:
    """Se `items` (as palabras dunha MESMA liña, en orde de lectura) son
    en realidade letras soltas dun texto con letreado expandido, xúntaas
    nas palabras que forman de verdade (texto concatenado, rectángulo
    unión -- así o tachado cobre todas as letras). Se non ten pinta de
    letreado, devólvense tal cal."""
    if len(items) < _LETREADO_SOLTAS_MINIMAS:
        return items
    soltas = sum(1 for item in items if len(item[0]) == 1)
    if soltas < _LETREADO_SOLTAS_MINIMAS or soltas < _LETREADO_PROPORCION_SOLTAS * len(items):
        return items

    vertical = items[0][4] in (90, 270)
    alturas = [
        (item[3][2] - item[3][0]) if vertical else (item[3][3] - item[3][1])
        for item in items
    ]
    altura = _mediana(alturas)
    if altura <= 0:
        return items
    separacions = [
        _separacion(items[i][3], items[i + 1][3], vertical) for i in range(len(items) - 1)
    ]
    separacion_tipica = _mediana(separacions)
    if separacion_tipica > altura * _LETREADO_SEPARACION_MAXIMA:
        return items  # separacións de columna, non de letreado

    limiar = max(separacion_tipica, 0.1) * _LETREADO_FOLGURA_PALABRA
    colapsados = []
    grupo = [items[0]]
    for i in range(1, len(items)):
        if separacions[i - 1] > limiar:
            colapsados.append(_xuntar_items(grupo))
            grupo = []
        grupo.append(items[i])
    colapsados.append(_xuntar_items(grupo))
    return colapsados


def _xuntar_items(grupo: list) -> tuple:
    if len(grupo) == 1:
        return grupo[0]
    rect = fitz.Rect(grupo[0][3])
    for item in grupo[1:]:
        rect |= fitz.Rect(item[3])
    primeiro = grupo[0]
    xuntado = ("".join(item[0] for item in grupo), primeiro[1], primeiro[2], tuple(rect), primeiro[4])
    return xuntado + (True,) if any(_tinta_en_pixeles(item) for item in grupo) else xuntado


def _tinta_en_pixeles(item: tuple) -> bool:
    """Os items son (texto, bloque, liña, rect, rotacion) e, opcionalmente,
    un sexto elemento `True` se o dato ten tinta en píxeles."""
    return len(item) > 5 and bool(item[5])


def _por_liñas(items: list) -> list:
    """Agrupa os items CONSECUTIVOS coa mesma clave (bloque, liña) -- xa
    veñen en orde de lectura, así que non fai falta reordenar nada."""
    grupos = []
    for item in items:
        chave = (item[1], item[2])
        if grupos and grupos[-1][0] == chave:
            grupos[-1][1].append(item)
        else:
            grupos.append((chave, [item]))
    return [grupo for _chave, grupo in grupos]


def _mesma_liña_visual(anterior: tuple, item: tuple) -> bool:
    """Liña xustificada que PyMuPDF parte nunha "liña" por palabra ("Suplente:
    Itziar Romanillos Camarasaltas.", BOE-A-2026-13616): co salto entre
    elas, a persoa partíase e o último apelido quedaba á vista. Só no mesmo
    bloque, mesma altura exacta, de esquerda a dereita e preto (as celas
    dunha táboa adoitan ir en bloques distintos)."""
    if anterior is None or anterior[1] != item[1] or anterior[4] != 0 or item[4] != 0:
        return False
    (ax0, ay0, ax1, ay1), (bx0, by0, bx1, by1) = anterior[3], item[3]
    altura = ay1 - ay0
    return (abs(ay0 - by0) < 0.5 and abs(ay1 - by1) < 0.5 and bx0 >= ax1 - 0.5
            and bx0 - ax1 < 3 * altura)


def _ensamblar_texto(items: list) -> tuple:
    """`items` é unha lista de (texto, bloque, liña, rect, rotacion) xa en
    orde de lectura. Devolve (texto_conxunto, palabras) inserindo un
    espazo entre palabras da mesma liña e un salto de liña ao cambiar de
    bloque/liña -- para que o texto reconstruído se pareza a unha lectura
    normal, sen afectar as posicións (`palabras`) que se usan despois para
    redactar. Cada liña pasa antes por `_colapsar_letreado` (A22)."""
    items = [item for liña in _por_liñas(items) for item in _colapsar_letreado(liña)]
    anacos = []
    palabras = []
    cursor = 0
    liña_actual = None
    anterior = None
    for item in items:
        texto, bloque, liña, rect, rotacion = item[:5]
        chave_liña = (bloque, liña)
        if liña_actual is not None:
            mesma = chave_liña == liña_actual or _mesma_liña_visual(anterior, item)
            anacos.append(" " if mesma else "\n")
            cursor += 1
        liña_actual = chave_liña
        anterior = item
        inicio = cursor
        anacos.append(texto)
        cursor += len(texto)
        palabras.append(_PalabraPaxina(inicio, cursor, rect, rotacion, _tinta_en_pixeles(item)))
    return "".join(anacos), palabras


# -- coordenadas: render (píxeles) -> páxina ---------------------------------
#
# Fuga atopada nunha auditoría (A5): nunha páxina con /Rotate 90/270, o
# render (`get_pixmap`) sae xa ROTADO -- tal e como o ve o lector -- pero
# tanto as palabras nativas (`get_text("words")`) coma as anotacións de
# redacción traballan en coordenadas SEN rotar. Dividir os píxeles pola
# escala sen máis (como se facía no OCR, nos QR e na reserva de páxina
# completa) deixaba o tachado noutro sitio e o dato á vista. Toda
# conversión render -> páxina pasa agora por aquí.

def _rect_pixmap_a_paxina(pagina: "fitz.Page", pix: "fitz.Pixmap", matriz: "fitz.Matrix", x0, y0, x1, y1) -> "fitz.Rect":
    """Rectángulo en píxeles dun render de `pagina` (feito con `matriz`,
    con ou sen `clip`) -> rectángulo en coordenadas SEN rotar da páxina
    (as de `get_text`/`add_redact_annot`). `pix.x`/`pix.y` son a orixe do
    render -- non é cero nin cun `clip` nin cunha matriz que inclúe
    rotación (A21), así que a volta ten que pasar SEMPRE por eles antes
    de desfacer a matriz."""
    visual = fitz.Rect(x0 + pix.x, y0 + pix.y, x1 + pix.x, y1 + pix.y) * ~matriz
    return fitz.Rect(visual * pagina.derotation_matrix).normalize()


def _rect_visible_sen_rotar(pagina: "fitz.Page") -> "fitz.Rect":
    """A área visible da páxina (CropBox) en coordenadas SEN rotar --
    `pagina.rect` vén xa rotada (ex. 842x595 nunha A4 con /Rotate 90), e
    usala tal cal para redactar deixaba sen tapar parte da páxina."""
    return fitz.Rect(pagina.rect * pagina.derotation_matrix).normalize()


def _rotacion_visual(pagina: "fitz.Page") -> int:
    """Rotación (0/90/180/270, convención de `_DIRECCION_A_GRAOS`) con que
    hai que inserir texto novo en coordenadas SEN rotar para que o lector
    o vexa en horizontal nunha páxina con /Rotate. Coincide coa de
    `get_text("dict")` para texto que se ve dereito."""
    m = pagina.derotation_matrix
    return _rotacion_mais_preto((m.a, m.b))


# -- carga --------------------------------------------------------------------

# Corpus web (BOE, 29/09/2026): entre o marcador dunha lista e o seu texto
# ("b)<EM SPACE>Actividades relacionadas...") hai un espazo tipográfico
# (U+2003) que `get_text("words")` NON parte: chega "b)\u2003Actividades" coma
# UNHA palabra, e redactar "Actividades" borraba tamén o "b)" / "1.".
_SEN_ESPAZO_TIPOGRAFICO_RE = re.compile("[^\u00a0\u2000-\u200a\u202f\u205f\u3000]+")


def _partes_por_espazos_tipograficos(texto: str, rect: tuple, rotacion: int, caracteres: list) -> list:
    """[(subtexto, subrect)] partindo `texto` polos espazos tipográficos.
    `caracteres` (rawdict) dá a caixa exacta de cada letra; se non se atopa
    a palabra entre eles, repártese o rectángulo en proporción ás letras."""
    partes = [
        (a, b) for m in _SEN_ESPAZO_TIPOGRAFICO_RE.finditer(texto)
        for a, b in _tramos_tras_punto_e_raia(texto, *m.span())
    ]
    if not partes:
        return []
    if len(partes) == 1 and partes[0] == (0, len(texto)):
        return [(texto, rect)]

    letras = [c["c"] for c in caracteres]
    inicio = next(
        (i for i in range(len(letras) - len(texto) + 1) if "".join(letras[i:i + len(texto)]) == texto), None
    )
    resultado = []
    x0, y0, x1, y1 = rect
    n = len(texto)
    for ini, fin in partes:
        if inicio is not None:
            caixas = [fitz.Rect(c["bbox"]) for c in caracteres[inicio + ini:inicio + fin]]
            sub = fitz.Rect(caixas[0])
            for caixa in caixas[1:]:
                sub |= caixa
            resultado.append((texto[ini:fin], tuple(sub)))
            continue
        a, b = ini / n, fin / n
        if rotacion == 0:
            sub = (x0 + (x1 - x0) * a, y0, x0 + (x1 - x0) * b, y1)
        elif rotacion == 180:
            sub = (x1 - (x1 - x0) * b, y0, x1 - (x1 - x0) * a, y1)
        elif rotacion == 90:
            sub = (x0, y1 - (y1 - y0) * b, x1, y1 - (y1 - y0) * a)
        else:
            sub = (x0, y0 + (y1 - y0) * a, x1, y0 + (y1 - y0) * b)
        resultado.append((texto[ini:fin], sub))
    return resultado


# Sinatura do BOE (corpus web lote 2, 30/09/2026): "...Serrano Martínez.–El
# Secretario Primero..." chega coma UNHA palabra "Martínez.–El", e tapar o
# apelido levaba consigo ".–El". Pártese tras o punto que precede á raia.
_PUNTO_ANTES_DE_RAIA_RE = re.compile("\\.(?=[\u2013\u2014])")


def _tramos_tras_punto_e_raia(texto: str, inicio: int, fin: int) -> list:
    cortes = [m.end() for m in _PUNTO_ANTES_DE_RAIA_RE.finditer(texto, inicio, fin) if m.end() < fin]
    limites = [inicio, *cortes, fin]
    return list(zip(limites, limites[1:]))


def _caracteres_da_caixa(pagina: "fitz.Page", rect: tuple) -> list:
    try:
        bloques = pagina.get_text("rawdict", clip=fitz.Rect(rect) + (-1, -1, 1, 1)).get("blocks", [])
    except Exception:  # noqa: BLE001 -- sen caixas por letra, repártese en proporción
        return []
    return [
        c for b in bloques if b.get("type") == 0
        for l in b["lines"] for sp in l["spans"] for c in sp["chars"]
    ]


def _items_nativos(pagina: "fitz.Page") -> list:
    rotacion_por_liña = {}
    for bi, bloque in enumerate(pagina.get_text("dict").get("blocks", [])):
        for li, liña in enumerate(bloque.get("lines", [])):
            rotacion_por_liña[(bi, li)] = _rotacion_mais_preto(liña["dir"])

    items = []
    for (x0, y0, x1, y1, texto, bloque, liña, _n) in pagina.get_text("words"):
        rotacion = rotacion_por_liña.get((bloque, liña), 0)
        if _SEN_ESPAZO_TIPOGRAFICO_RE.fullmatch(texto) and not _PUNTO_ANTES_DE_RAIA_RE.search(texto[:-1]):
            items.append((texto, bloque, liña, (x0, y0, x1, y1), rotacion))
            continue
        caracteres = _caracteres_da_caixa(pagina, (x0, y0, x1, y1))
        for subtexto, subrect in _partes_por_espazos_tipograficos(texto, (x0, y0, x1, y1), rotacion, caracteres):
            items.append((subtexto, bloque, liña, tuple(subrect), rotacion))
    return items


# Fuga atopada nunha auditoría (A21): un ESCANEO DE LADO -- a folla
# dixitalizada en horizontal, coa imaxe xirada 90º e SEN o /Rotate do PDF
# que llo diría ao visor (moi habitual nun escáner de alimentación
# automática cando a folla entra tombada). Tesseract con `--psm 6`
# ("bloque de texto uniforme") asume que o texto vai dereito: do escaneo
# de lado sacaba lixo de dúas letras ("9 ED / Z 5 D / e >"), non casaba
# ningún patrón e a saída quedaba idéntica á entrada -- pero xirando a
# páxina a man líase "Juan Perez Garcia / DNI ..." en claro.
#
# Próbanse agora as catro orientacións (0/90/180/270) cando a primeira
# non dá texto con sentido. A propósito NON se usa a detección de
# orientación de Tesseract (OSD, `--psm 0`): neste mesmo caso devolvía
# unha orientación cunha confianza de 1,33 (practicamente nula) e ademais
# esixe o ficheiro `osd.traineddata`, que non sempre se instala. Puntuar
# o resultado REAL do OCR en cada xiro non depende de datos extra e mide
# exactamente o que nos importa: canto texto fiable se le.
_CONFIANZA_OCR_MINIMA = 60  # a que reporta Tesseract por palabra (0-100)
_LONGO_PALABRA_FIABLE = 3  # de menos letras, o lixo tamén "acerta"
_PUNTUACION_OCR_ABONDA = 12  # caracteres fiables: por riba, non se tentean xiros
_XIROS_ALTERNATIVOS = (90, 180, 270)
_MARXE_MINIMA_MELLORA_XIRO = 6  # un xiro só gaña se mellora CLARAMENTE, non por 1-2 puntos de ruído
_NATIVAS_MAXIMAS_ZONA_VECTORIAL = 4
_MARXE_ZONA_OCR = 6  # puntos PDF de aire arredor dunha zona antes de facerlle OCR (A25)


def _puntuacion_ocr(datos: dict) -> int:
    """Caracteres lidos con confianza alta en palabras de lonxitude
    plausible -- serve para comparar o mesmo render en varios xiros."""
    total = 0
    for texto, confianza in zip(datos["text"], datos["conf"]):
        limpo = texto.strip()
        if len(limpo) < _LONGO_PALABRA_FIABLE:
            continue
        try:
            valor = float(confianza)
        except (TypeError, ValueError):
            continue
        if valor >= _CONFIANZA_OCR_MINIMA:
            total += len(limpo)
    return total


def _ocr_do_render(pagina: "fitz.Page", matriz: "fitz.Matrix", clip) -> tuple:
    pix = pagina.get_pixmap(matrix=matriz, clip=clip)
    if pix.width < 2 or pix.height < 2:
        return None, None
    imaxe_proc = _preprocesar(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
    return pix, pytesseract.image_to_data(
        imaxe_proc, lang=_idioma_dispoñible(), config=_CONFIG_TESSERACT,
        output_type=Output.DICT,
    )


def _items_ocr(pagina: "fitz.Page", zona: "fitz.Rect | None" = None, id_zona: int = 0,
               confianza_minima: float = 0) -> list:
    """OCR (Tesseract, `image_to_data`, con coordenadas de cada palabra)
    do render da páxina enteira ou só de `zona` (coordenadas SEN rotar).
    Devolve items coma os de `_items_nativos`, xa en coordenadas SEN rotar
    da páxina (ver `_rect_pixmap_a_paxina`) -- as claves de bloque levan
    o prefixo "ocr" para non mesturarse nunca coas liñas nativas."""
    if shutil.which("tesseract") is None:
        raise TesseractNonInstalado()

    escala = _DPI_OCR / 72  # píxeles por punto PDF
    # Marxe arredor da zona (A25): un recorte XUSTO ao bounding box dos
    # trazos pode cortar polo medio a primeira/última letra se toca o
    # bordo (caso real: "Juan" quedaba sen ler nun nome vectorizado
    # porque a "J" tocaba o bordo esquerdo exacto da zona) -- Tesseract
    # le mellor cun pouco de aire arredor do texto. Recórtase sempre
    # dentro do visible da páxina, nunca máis aló.
    zona_con_marxe = None if zona is None else (
        (fitz.Rect(zona) + (-_MARXE_ZONA_OCR, -_MARXE_ZONA_OCR, _MARXE_ZONA_OCR, _MARXE_ZONA_OCR))
        & _rect_visible_sen_rotar(pagina)
    )
    clip = None if zona_con_marxe is None else fitz.Rect(zona_con_marxe * pagina.rotation_matrix).normalize()
    matriz = fitz.Matrix(escala, escala)
    pix, datos = _ocr_do_render(pagina, matriz, clip)
    if pix is None:
        return []

    xiro = 0
    mellor = _puntuacion_ocr(datos)
    if mellor < _PUNTUACION_OCR_ABONDA:
        for angulo in _XIROS_ALTERNATIVOS:
            matriz_xirada = fitz.Matrix(escala, escala).prerotate(angulo)
            pix_xirado, datos_xirados = _ocr_do_render(pagina, matriz_xirada, clip)
            if pix_xirado is None:
                continue
            puntuacion = _puntuacion_ocr(datos_xirados)
            # Nunha zona PEQUENA (unha soa palabra ou dúas, coma un nome
            # vectorizado, A25) un pequeno erro de lectura do OCR pode
            # deixar a orientación correcta xusto por debaixo do limiar
            # "abondo" -- e calquera lectura, aínda que sexa lixo, pode
            # sacar por puro azar 1-2 caracteres "fiables" de máis nunha
            # orientación xirada. Sen esta marxe, ese lixo "gañaba" por 1
            # punto á lectura correcta pero imperfecta (caso real: "Parez
            # Garcia", puntuación 11, perdía contra "819185) 23194" a
            # 180º, puntuación 12). Esixir unha mellora CLARA antes de
            # trocar evita iso sen afectar o caso real que isto arranxa
            # (unha páxina xirada de verdade escora a 0 na orientación
            # errada e a decenas de caracteres na correcta).
            if puntuacion > mellor + _MARXE_MINIMA_MELLORA_XIRO:
                mellor, xiro = puntuacion, angulo
                matriz, pix, datos = matriz_xirada, pix_xirado, datos_xirados

    # Tesseract le o render tal e como se ve, así que o texto que atopa
    # vai "dereito" NESE render: en coordenadas SEN rotar da páxina, iso é
    # a rotación visual da páxina (0 se non ten /Rotate) máis o xiro que
    # tivemos que darlle ao render para poder lelo.
    rotacion = (_rotacion_visual(pagina) + xiro) % 360
    items = []
    for i in range(len(datos["text"])):
        texto = datos["text"][i].strip()
        if not texto:
            continue
        try:
            if float(datos["conf"][i]) < confianza_minima:
                continue
        except (TypeError, ValueError):
            pass
        x0px, y0px = datos["left"][i], datos["top"][i]
        x1px, y1px = x0px + datos["width"][i], y0px + datos["height"][i]
        rect = _rect_pixmap_a_paxina(pagina, pix, matriz, x0px, y0px, x1px, y1px)
        items.append((
            texto, ("ocr", id_zona, datos["block_num"][i]),
            f"{datos['par_num'][i]}-{datos['line_num'][i]}", tuple(rect), rotacion,
        ))
    return items


# Fuga atopada nunha auditoría (A4): unha páxina con texto nativo abondo
# (>= `_LONGO_ABONDO`, ex. un selo de rexistro de entrada) que ademais leva
# unha IMAXE con datos -- unha dilixencia escaneada pegada, unha captura,
# un DNI fotografado -- nunca pasaba por OCR, e a imaxe saía intacta.
# Variante peor: un escaneo cunha capa de OCR previa (texto invisible) mal
# aliñada coa imaxe -- redactábase o texto invisible, pero os píxeles cos
# datos quedaban noutro sitio, á vista.
#
# Agora, en calquera páxina, faise OCR tamén de cada zona con imaxe de
# tamaño apreciable. Para non duplicar no texto de revisión o que xa é
# texto nativo (ex. un selo dixital debuxado ENCIMA da imaxe, ou unha capa
# OCR ben aliñada), descártase a palabra OCR que solapa cunha nativa co
# mesmo texto -- pero ampliando o rectángulo da nativa ata cubrir tamén o
# da OCR, para que o tachado tape seguro os píxeles. A palabra OCR sen
# parella nativa engádese ao final do texto da páxina (con coordenadas
# propias), e redáctase coma calquera outra.
_IMAXE_LADO_CURTO_MINIMO = 8.0  # puntos: por debaixo non cabe unha liña lexible
_IMAXE_LADO_LONGO_MINIMO = 20.0
_SOLAPE_DUPLICADO = 0.3  # fracción da área menor
_SIMILITUDE_DUPLICADO = 0.75


def _zonas_con_imaxe(pagina: "fitz.Page") -> list:
    """Rectángulos (SEN rotar, recortados á área visible) das imaxes de
    tamaño apreciable da páxina -- incluídas as que van dentro de Form
    XObjects -- fusionando as que se solapan para non facer OCR dúas veces
    da mesma zona."""
    visible = _rect_visible_sen_rotar(pagina)
    zonas = []
    for info in pagina.get_image_info():
        r = fitz.Rect(info["bbox"]).normalize() & visible
        if r.is_empty:
            continue
        curto, longo = sorted((r.width, r.height))
        if curto >= _IMAXE_LADO_CURTO_MINIMO and longo >= _IMAXE_LADO_LONGO_MINIMO:
            zonas.append(fitz.Rect(r))

    return _fusionar_rects(zonas)


# Mesmo problema ca A4, pero cun texto DEBUXADO en vez de fotografado
# (A25): nunha páxina con texto nativo normal (un selo, un pé de páxina),
# un nome convertido a trazos vectoriais non é nin texto nin imaxe, así
# que non entraba por ningunha das dúas portas e non se analizaba.
#
# A pista para distinguir un texto vectorizado do debuxo normal dunha
# páxina é a DENSIDADE: o contorno de cada letra é un camiño pequeno, e
# un nome son ducias deles moi xuntos. O marco dunha táboa, unha liña de
# separación ou unha caixa son poucos camiños e grandes -- por iso só se
# fai OCR dos grupos de MOITOS camiños pequenos pegados, e non de calquera
# páxina con debuxos (que serían practicamente todas).
#
# O agrupamento faise sobre unha REXILLA de celas, non comparando cada
# trazo con cada outro: un plano de urbanismo (documentos habituais neste
# despacho) ten miles de camiños pequenos nunha soa páxina, e a fusión
# por pares -- a que usa `_fusionar_rects` para catro ou cinco imaxes --
# aí dispárase a minutos. Dúas celas veciñas (tamén en diagonal) son o
# mesmo grupo, así que trazos a menos dunha cela de distancia únense:
# chega para que as letras dunha liña, ocos entre palabras incluídos,
# caian nun só grupo (unha palabra curta coma "Juan" son só 5 contornos,
# por debaixo do mínimo se quedase soa -- atopado co test de regresión).
_TRAZO_PEQUENO_LADO = 40.0  # puntos: por riba xa non é o contorno dunha letra
_CELA_AGRUPAMENTO = 6.0  # puntos
_TRAZOS_DENSOS_MINIMOS = 8
_ZONAS_DENSAS_MAXIMAS = 8  # máis ca isto: unha soa zona que as abrangue todas


def _celas_ocupadas(rects: list) -> dict:
    ocupadas = {}
    for k, rect in enumerate(rects):
        for i in range(int(rect.x0 // _CELA_AGRUPAMENTO), int(rect.x1 // _CELA_AGRUPAMENTO) + 1):
            for j in range(int(rect.y0 // _CELA_AGRUPAMENTO), int(rect.y1 // _CELA_AGRUPAMENTO) + 1):
                ocupadas.setdefault((i, j), []).append(k)
    return ocupadas


def _grupos_de_trazos(pequenos: list) -> list:
    """Índices de `pequenos` agrupados por proximidade (compoñentes
    conexas da rexilla de celas)."""
    ocupadas = _celas_ocupadas(pequenos)
    visitadas = set()
    grupos = []
    for cela in ocupadas:
        if cela in visitadas:
            continue
        visitadas.add(cela)
        pendentes = [cela]
        membros = set()
        while pendentes:
            i, j = pendentes.pop()
            membros.update(ocupadas[(i, j)])
            # ±2 celas (non ±1): un espazo normal entre DUAS PALABRAS
            # (non entre letras da mesma palabra) pode superar unha soa
            # cela de marxe -- caso real: "Juan" quedaba fóra do grupo de
            # "Perez Garcia" por un burato de ~11pt entre as dúas
            # palabras, algo máis ca unha cela (`_CELA_AGRUPAMENTO`), e
            # "Juan" só non chegaba ao mínimo de trazos densos por si só
            # -- quedaba fóra da zona de OCR enteiramente, sen ler.
            for di in (-2, -1, 0, 1, 2):
                for dj in (-2, -1, 0, 1, 2):
                    veciña = (i + di, j + dj)
                    if veciña in ocupadas and veciña not in visitadas:
                        visitadas.add(veciña)
                        pendentes.append(veciña)
        grupos.append(membros)
    return grupos


def _zonas_con_trazos_densos(pagina: "fitz.Page") -> list:
    visible = _rect_visible_sen_rotar(pagina)
    pequenos = []
    for rect in _trazos_da_paxina(pagina):
        recortado = rect & visible
        if not recortado.is_empty and max(recortado.width, recortado.height) <= _TRAZO_PEQUENO_LADO:
            pequenos.append(fitz.Rect(recortado))
    if len(pequenos) < _TRAZOS_DENSOS_MINIMOS:
        return []

    zonas = []
    for membros in _grupos_de_trazos(pequenos):
        if len(membros) < _TRAZOS_DENSOS_MINIMOS:
            continue
        grupo = fitz.Rect(pequenos[next(iter(membros))])
        for k in membros:
            grupo |= pequenos[k]
        curto, longo = sorted((grupo.width, grupo.height))
        if curto >= _IMAXE_LADO_CURTO_MINIMO and longo >= _IMAXE_LADO_LONGO_MINIMO:
            zonas.append(grupo)

    # Moitos grupos pequenos espallados (un formulario cheo de iconas,
    # por exemplo) sairían máis caros en chamadas a Tesseract ca unha soa
    # pasada que os cubra a todos.
    if len(zonas) > _ZONAS_DENSAS_MAXIMAS:
        todo = fitz.Rect(zonas[0])
        for zona in zonas[1:]:
            todo |= zona
        zonas = [todo]
    return zonas


def _fusionar_rects(rects: list) -> list:
    """Funde os rectángulos que se solapan (repetindo ata que non quede
    ningún par solapado) -- para non facer dúas veces o mesmo traballo
    sobre a mesma zona."""
    rects = [fitz.Rect(r) for r in rects]
    fusionadas = True
    while fusionadas:
        fusionadas = False
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                if rects[i].intersects(rects[j]):
                    rects[i] |= rects.pop(j)
                    fusionadas = True
                    break
            if fusionadas:
                break
    return rects


def _area(rect: "fitz.Rect") -> float:
    return 0.0 if rect.is_empty else rect.width * rect.height


def _clave_comparacion(texto: str) -> str:
    sen_tiles = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in sen_tiles if c.isalnum()).casefold()


def _rects_texto_invisible(pagina: "fitz.Page") -> list:
    """Caixas do texto nativo INVISIBLE (modo de renderizado 3): a capa de
    OCR dun escaneo. O seu dato está nos píxeles da imaxe, non no texto."""
    try:
        return [fitz.Rect(s["bbox"]) for s in pagina.get_texttrace() if s.get("type") == 3]
    except Exception:  # noqa: BLE001 -- sen esta info, todo se trata coma texto visible
        return []


def _fusionar_ocr_con_nativos(nativos: list, ocr: list, invisibles: list = ()) -> list:
    """Devolve `nativos` (co rectángulo ampliado onde unha palabra OCR os
    duplica) + as palabras OCR que NON son duplicado de ningunha nativa.
    Márcanse con tinta en píxeles as palabras OCR e as nativas INVISIBLES
    que un OCR duplica; unha nativa visible que o OCR tamén le (plano con
    imaxe de fondo, ou páxina enteira pasada por OCR) ten a tinta en
    vectores e admite recorte."""
    nativos = [list(item) for item in nativos]
    rects_nativos = [fitz.Rect(item[3]) for item in nativos]
    novos = []
    for item in ocr:
        r = fitz.Rect(item[3])
        clave = _clave_comparacion(item[0])
        area = _area(r)
        solapadas = []
        if clave and area > 0:
            for k, rn in enumerate(rects_nativos):
                area_n = _area(rn)
                if area_n <= 0:
                    continue
                if _area(rn & r) >= _SOLAPE_DUPLICADO * min(area, area_n):
                    solapadas.append(k)
        duplicado = False
        if solapadas:
            xunto = _clave_comparacion("".join(nativos[k][0] for k in solapadas))
            duplicado = bool(xunto) and (
                clave in xunto
                or difflib.SequenceMatcher(None, clave, xunto).ratio() >= _SIMILITUDE_DUPLICADO
            )
        if duplicado:
            for k in solapadas:
                rects_nativos[k] |= r
                nativos[k][3] = tuple(rects_nativos[k])
                centro = fitz.Point((nativos[k][3][0] + nativos[k][3][2]) / 2, (nativos[k][3][1] + nativos[k][3][3]) / 2)
                if any(centro in i for i in invisibles):
                    nativos[k] = nativos[k][:5] + [True]
        else:
            novos.append(tuple(item[:5]) + (True,))
    return [tuple(item) for item in nativos] + novos


# Fuga atopada nunha auditoría (A20): un PDF cuxas fontes non teñen
# tabla /ToUnicode -- é dicir, o ficheiro leva os códigos dos GLIFOS pero
# non o mapa que os traduce a Unicode. Pasa con subconxuntos de fonte mal
# xerados e con fontes Type3 (moi habitual en PDF saídos de certos
# programas de xestión procesal e de escáneres con "texto vectorizado").
# O visor amosa "El demandante Juan Perez Garcia" perfectamente -- debuxa
# glifos, non precisa saber que letra é cada un -- pero `get_text`
# devolve lixo do estilo "Ho#ghpdqgdqwh#Mxdq#Shuh}" (o código en cru). Coma
# a páxina TEN texto nativo abondo, nunca pasaba por OCR: non casaba ningún
# patrón, a saída era idéntica á entrada e, aínda así, calquera OCR da
# propia saída seguía a ler o nome e o DNI reais.
#
# O sinal máis fiable non é a ausencia de /ToUnicode en si (as 14 fontes
# estándar do PDF, as que usa este mesmo programa ao inserir os códigos,
# tampouco a levan e extráense perfectamente), senón que o texto
# resultante non se pareza a texto real. A proporción de VOGAIS é o que
# mellor separa os dous casos probados: calquera texto en galego ou
# castelán anda polo 40-45%, e o lixo de códigos desprazados baixa ao
# 10%. A falta de /ToUnicode usase só coma agravante, para ser máis
# esixente nas páxinas onde o mapeo pode estar roto de verdade.
_VOGAIS = frozenset("aeiouáéíóúàèìòùâêîôûäëïöüãõ")
_LETRAS_MINIMAS_PARA_XULGAR = 20  # con menos non hai mostra para decidir nada
_VOGAIS_MINIMAS = 0.22
_VOGAIS_MINIMAS_SEN_TOUNICODE = 0.30
_RACHA_SEN_ESPAZOS_MAXIMA = 40  # caracteres seguidos sen espazo nin salto


def _fontes_sen_tounicode(pagina: "fitz.Page") -> bool:
    documento = pagina.parent
    for fonte in pagina.get_fonts(full=False):
        try:
            if documento.xref_get_key(fonte[0], "ToUnicode")[0] == "null":
                return True
        except Exception:  # obxecto roto: trátase coma sospeitoso
            return True
    return False


# URL, correos, rutas e liñas de puntos son rachas longas LEXÍTIMAS sen
# espazos: o pé de TODAS as páxinas do DOG leva
# "https://www.xunta.gal/diario-oficial-galicia" (44 caracteres) e a regra
# de arriba tomaba as 322 páxinas do corpus web (e 29 do BOE) por texto
# roto -> OCR da páxina enteira, cuxo ruído ("Sy", a reixa dun formulario
# lida coma "AAA IEA III") acababa en persoas falsas.
def _e_url_ou_similar(anaco: str) -> bool:
    if "/" in anaco or "@" in anaco or anaco.lower().startswith("www.") or anaco.count("-") >= 3:
        return True
    return sum(c.isalpha() for c in anaco) < len(anaco) / 2


def _texto_semella_real(texto: str, sen_tounicode: bool) -> bool:
    """Se o texto extraído dunha páxina se parece a lingua escrita ou a
    lixo dun mapeo de glifos roto (ver o comentario de arriba)."""
    letras = [c for c in texto.casefold() if c.isalpha()]
    if len(letras) < _LETRAS_MINIMAS_PARA_XULGAR:
        return True  # mostra insuficiente: non se toca nada
    if max((len(anaco) for anaco in texto.split() if not _e_url_ou_similar(anaco)), default=0) > _RACHA_SEN_ESPAZOS_MAXIMA:
        return False  # nin un só espazo en toda unha liña: non é texto
    limiar = _VOGAIS_MINIMAS_SEN_TOUNICODE if sen_tounicode else _VOGAIS_MINIMAS
    return sum(1 for c in letras if c in _VOGAIS) / len(letras) >= limiar


def _extraer_paxina(pagina: "fitz.Page") -> _PaxinaPdf:
    """Texto + posición de cada palabra dunha páxina: SEMPRE o texto nativo
    (visible ou non -- A6: un "DNI 12345678Z" invisible ou en branco nunha
    páxina con menos de `_LONGO_ABONDO` caracteres quedaba sen analizar
    porque a páxina se trataba só por OCR) + OCR da páxina enteira se case
    non ten texto nativo OU se o que ten non semella texto real (A20), ou
    só das súas zonas con imaxe (A4) ou con trazos vectoriais densos
    (A25) se o ten e é bo."""
    nativos = _items_nativos(pagina)
    texto_nativo = pagina.get_text().strip()
    if len(texto_nativo) < _LONGO_ABONDO or not _texto_semella_real(
        texto_nativo, _fontes_sen_tounicode(pagina)
    ):
        # Consérvase tamén o texto nativo (aínda que sexa lixo): pode
        # levar contido invisible que o OCR non ve (A6), e o lixo á vista
        # na pantalla de revisión é a pista de que esta páxina viña rota.
        ocr = _items_ocr(pagina)
    else:
        ocr = []
        zonas_imaxe = _zonas_con_imaxe(pagina)
        zonas = _fusionar_rects(zonas_imaxe + _zonas_con_trazos_densos(pagina))
        for i, zona in enumerate(zonas):
            so_debuxos = not any(zona.intersects(z) for z in zonas_imaxe)
            # Unha zona SÓ de debuxos que xa leva texto nativo dentro é unha
            # táboa ou un esquema con letras de verdade, non un nome
            # vectorizado (A25, que non ten texto nativo ningún): o OCR só le
            # a reixa coma lixo ("AAA IEA III", "SINO") e o NER tomábao por
            # persoas (corpus web, formulario do DOG).
            if so_debuxos and sum(fitz.Rect(n[3]).intersects(zona) for n in nativos) >= _NATIVAS_MAXIMAS_ZONA_VECTORIAL:
                continue
            ocr.extend(_items_ocr(pagina, zona, i, _CONFIANZA_OCR_MINIMA if so_debuxos else 0))
    invisibles = _rects_texto_invisible(pagina) if ocr else []
    texto, palabras = _ensamblar_texto(_fusionar_ocr_con_nativos(nativos, ocr, invisibles))
    return _PaxinaPdf(texto=texto, palabras=palabras)


def cargar_pdf_estruturado(ruta: str | None, documento: "fitz.Document | None" = None) -> tuple:
    """Devolve (texto_conxunto, contexto). `contexto["paxinas"]` garda,
    para cada páxina, o seu texto e as posicións exactas de cada palabra
    -- nativa ou por OCR -- necesarias para redactar con precisión ao
    gardar (`gardar_pdf_estruturado`). Antes de extraer nada, o documento
    pásase por `_preparar_documento` (contido oculto, anotacións,
    formularios, sinaturas -- ver alí). `documento` (en vez de `ruta`): un
    PDF xa aberto en memoria, ex. o que `imaxes.py` constrúe dunha imaxe."""
    documento, sinaturas = _preparar_documento(documento if documento is not None else fitz.open(ruta))
    paxinas = []
    papeis_herdados = None  # papeis das columnas dunha táboa que pode continuar
    filas = 0
    for pagina in documento:
        paxina = _extraer_paxina(pagina)
        paxina.celas, papeis_herdados, filas_usadas = taboas_pdf.celas_da_paxina(
            pagina, paxina.texto, paxina.palabras, papeis_herdados, filas
        )
        filas += filas_usadas
        paxinas.append(paxina)

    texto_conxunto = SEPARADOR_PAXINAS.join(p.texto for p in paxinas)
    contexto = {
        "tipo": "pdf", "documento": documento, "paxinas": paxinas, "sinaturas": sinaturas,
        "celas_datos_persoais": _celas_en_offsets_globais(paxinas),
    }
    return texto_conxunto, contexto


def _celas_en_offsets_globais(paxinas: list) -> list:
    celas = []
    for paxina, (inicio_paxina, _fin) in zip(paxinas, _limites_paxinas(paxinas)):
        for cela in paxina.celas:
            celas.append(taboas_pdf.CelaDatoPersoal(
                cela.tipo, [(inicio_paxina + a, inicio_paxina + b) for a, b in cela.pezas], cela.fila,
            ))
    return celas


def _limites_paxinas(paxinas: list) -> list:
    limites = []
    cursor = 0
    for p in paxinas:
        limites.append((cursor, cursor + len(p.texto)))
        cursor += len(p.texto) + len(SEPARADOR_PAXINAS)
    return limites


def _aplicar_substitucions_a_texto(texto: str, substitucions: list) -> str:
    resultado = texto
    for inicio, fin, novo in sorted(substitucions, key=lambda s: s[0], reverse=True):
        resultado = resultado[:inicio] + novo + resultado[fin:]
    return resultado


def _rects_das_palabras_no_intervalo(palabras: list, inicio: int, fin: int) -> list:
    """Devolve os rectángulos de tódalas palabras que solapan
    [inicio, fin) -- polo menos parcialmente. Redáctase SEMPRE a palabra
    enteira (gránulo de palabra, non de carácter): se unha substitución
    non casa exactamente cos límites dunha palabra, redáctase igualmente
    a palabra completa que a contén, nunca menos do necesario."""
    return [p for p in palabras if p.inicio < fin and p.fin > inicio]


_TOLERANCIA_ALTURA_VECIÑA = 2.2  # veces a altura das veciñas, como máximo


def _inserir_texto_axustado(
    pagina: "fitz.Page", rect: "fitz.Rect", texto: str, rotacion: int = 0, altura_veciña: float | None = None,
) -> None:
    """Insire `texto` dentro de `rect` (o rectángulo redactado), partindo
    dun tamaño de letra estimado a partir do LADO PERPENDICULAR á lectura
    do rectángulo orixinal (para parecerse ao tamaño do texto que había
    antes) e encollendo máis só se aínda así non cabe en LONXITUDE -- un
    código adoita ser máis longo có texto orixinal que substitúe (ex.
    "PERSOA_000042" fronte a "Ana"). `rotacion` (0/90/180/270) reproduce a
    orientación orixinal -- imprescindible en marxes con texto vertical
    (moi habitual en rexistros mercantís/notariais), onde inserir sempre
    en horizontal solapaba e facía ilexible tanto o código coma o texto
    orixinal ao seu redor.

    Corrección atopada nunha táboa densa dun documento real escaneado: o
    bounding box dunha soa palabra (viña dunha capa de texto inserida polo
    propio proceso de dixitalización, non de fontes vectoriais fiables)
    era moito máis alto cás palabras ao seu redor, e o código resultante
    saía nun tamaño de letra disparatado, solapando o texto veciño. Se
    `altura_veciña` (ver `_altura_veciña`) di que este rectángulo é
    anormalmente grande fronte ás palabras preto del, limítase o tamaño
    ao delas en vez de confiar nesta única palabra."""
    vertical = rotacion in (90, 270)
    lonxitude_dispoñible = max((rect.height if vertical else rect.width) - _MARXE_INSERCION, 4)
    lado_perpendicular = rect.width if vertical else rect.height

    # 4 pt é o mínimo lexible, pero nunca máis grande có propio texto
    # substituído: nunha lenda de plano a 1,5 pt un código a 4 pt tapaba as
    # celas veciñas (corpus web, caixetín dun plano do DOG).
    minimo = min(4.0, max(lado_perpendicular, 1.0))
    fontsize = max(lado_perpendicular * 0.75, minimo)
    if altura_veciña:
        fontsize_veciño = altura_veciña * 0.75
        if fontsize > fontsize_veciño * _TOLERANCIA_ALTURA_VECIÑA:
            fontsize = max(fontsize_veciño, minimo)

    lonxitude_necesaria = fitz.get_text_length(texto, fontname=_FONTE_SAIDA, fontsize=fontsize)
    if lonxitude_necesaria > lonxitude_dispoñible:
        fontsize = max(fontsize * (lonxitude_dispoñible / lonxitude_necesaria), minimo)

    # a liña base dunha palabra sen descendentes (g, p, q...) case coincide
    # co bordo do seu rectángulo na dirección de lectura -- un pequeno
    # axuste cara dentro evita que se recorte visualmente contra ese bordo
    desprazamento = min(2.0, fontsize * 0.15)
    if rotacion == 0:
        punto = (rect.x0, rect.y1 - desprazamento)
    # En 90/270 os glifos medran cara a -x (90) ou +x (270) dende a liña
    # base (comprobado con `get_text("words")` sobre o texto inserido): a
    # liña base vai no bordo OPOSTO -- antes ía no mesmo e o código saía
    # fóra do rectángulo redactado, encima do texto veciño.
    elif rotacion == 90:
        punto = (rect.x1 - desprazamento, rect.y1)
    elif rotacion == 180:
        punto = (rect.x1, rect.y0 + desprazamento)
    else:  # 270
        punto = (rect.x0 + desprazamento, rect.y0)

    pagina.insert_text(
        punto, texto, fontsize=fontsize, fontname=_FONTE_SAIDA, color=(0, 0, 0), rotate=rotacion,
    )


# Fuga atopada nunha auditoría (A25): TEXTO CONVERTIDO A TRAZOS
# VECTORIAIS -- cada letra debuxada coma un contorno pechado, non coma
# texto (sae así de programas de deseño, de sinaturas dixitalizadas e de
# certos "vectorizadores" de escaneos). O nome LESE por OCR e o seu sitio
# redáctase, pero os TRAZOS quedaban no ficheiro baixo o recadro branco
# -- recuperables con `get_drawings()` sen ningún visor de por medio, o
# mesmo tipo de fuga xa arranxada cos obxectos de imaxe orfos -- e o que
# sobresaía do recadro que mide o OCR (as iniciais grandes dun
# encabezado), ademais, á vista.
#
# Probado contra este mesmo caso: `apply_redactions` co seu
# `graphics=1` por defecto ("elimina o debuxo que queda dentro do
# rectángulo") NON é fiable con contornos de letras -- cun rectángulo que
# os contiña de sobra seguían quedando 21 dos 23 trazos, e ampliar o
# rectángulo chegaba a deixar MÁIS trazos, non menos. O único modo que os
# elimina de verdade é `graphics=2` ("todo o que TOQUE o rectángulo"),
# que por si só sería perigoso: unha raia de táboa ou o marco da páxina
# que cruzase o tachado desaparecería ENTEIRO (comprobado), estragando o
# formato que este módulo existe para conservar.
#
# Así que se fan dúas pasadas. Primeiro amplíase cada rectángulo ata
# cubrir os trazos que o tocan e son de tamaño comparable a el (unha
# letra si; unha raia de ancho de páxina non). Se NINGÚN trazo grande
# toca ese rectángulo, xa sabemos que `graphics=2` alí só pode levar por
# diante os trazos que o propio rectángulo xa cobre -> pasada agresiva.
# Os poucos rectángulos que si teñen un trazo grande enriba van na
# pasada prudente (`graphics=1`): nese caso o contido queda tapado polo
# recadro branco, pero pode quedar algún fragmento vectorial dentro do
# ficheiro -- limitación coñecida, preferida a borrar as liñas da táboa.
_TRAZO_VECES_MAXIMAS = 3.0
_TRAZO_LADO_MINIMO = 12.0  # puntos: unha letra normal cabe sempre aquí


def _trazos_da_paxina(pagina: "fitz.Page") -> list:
    """Rectángulos dos debuxos vectoriais da páxina, xa inflados co groso
    do trazo (o `rect` de `get_drawings` é o do camiño, e o trazo píntase
    medio groso para fóra del)."""
    trazos = []
    for debuxo in pagina.get_drawings():
        # A inflación vai ANTES de mirar se está baleiro: unha raia
        # horizontal ou vertical ten un lado de longo cero (`is_empty`), e
        # descartala aquí era peor có problema que arranxa esta función --
        # a raia deixaba de contar coma "trazo grande" e a pasada agresiva
        # borraba as liñas das táboas (atopado cun test de regresión).
        marxe = (debuxo.get("width") or 0) / 2 + 0.5
        rect = fitz.Rect(debuxo["rect"]).normalize() + (-marxe, -marxe, marxe, marxe)
        if not rect.is_empty:
            trazos.append(rect)
    return trazos


def _e_bordo_de_taboa(trazo: "fitz.Rect", rect: "fitz.Rect") -> bool:
    """Un trazo que ENCERRA o texto (o recadro da cela) ou unha raia fina
    que sobresae del é un bordo de táboa, non unha letra vectorizada: non
    se amplía o tachado con el nin se borra por rozalo (corpus web: as
    liñas das táboas dun formulario desaparecían arredor das celas
    redactadas). Unha letra vectorizada queda dentro do rectángulo."""
    if trazo.contains(rect):
        return True
    fina = min(trazo.width, trazo.height) < 1.5
    return fina and not rect.contains(trazo)


def _ampliar_con_trazos(rect: "fitz.Rect", trazos: list) -> tuple:
    """Devolve (rectángulo ampliado cos trazos pequenos que o tocan,
    se hai algún trazo GRANDE tocándoo)."""
    limite_ancho = max(rect.width, _TRAZO_LADO_MINIMO) * _TRAZO_VECES_MAXIMAS
    limite_alto = max(rect.height, _TRAZO_LADO_MINIMO) * _TRAZO_VECES_MAXIMAS
    ampliado = fitz.Rect(rect)
    hai_grandes = False
    for trazo in trazos:
        if not trazo.intersects(rect):
            continue
        if trazo.width > limite_ancho or trazo.height > limite_alto or _e_bordo_de_taboa(trazo, rect):
            hai_grandes = True
            continue
        ampliado |= trazo
    return ampliado, hai_grandes


def _redactar_rects(pagina: "fitz.Page", agresivos: list, prudentes: list) -> None:
    """Aplica as dúas pasadas de redacción descritas arriba. Nunha páxina
    sen debuxos vectoriais (o caso normal) todo vai na agresiva, onde
    `graphics=2` é indistinguible de `graphics=1` porque non hai trazo
    ningún que tocar."""
    for rect in agresivos:
        pagina.add_redact_annot(rect, fill=(1, 1, 1))
    if agresivos:
        pagina.apply_redactions(graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED)
    for rect in prudentes:
        pagina.add_redact_annot(rect, fill=(1, 1, 1))
    if prudentes:
        pagina.apply_redactions(graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED)


def _eixo_perpendicular(rect, rotacion: int) -> tuple:
    """(inicio, fin) do rectángulo no eixo perpendicular á lectura: o
    vertical para texto horizontal, o horizontal para texto a 90/270."""
    r = fitz.Rect(rect)
    return (r.x0, r.x1) if rotacion in (90, 270) else (r.y0, r.y1)


def _por_liña_visual(tocadas: list) -> list:
    """As palabras dunha substitución agrupadas pola liña visual en que
    están (unha entidade partida por un salto de liña dá dous grupos)."""
    grupos = []
    for p in tocadas:
        a0, a1 = _eixo_perpendicular(p.rect, p.rotacion)
        for grupo in grupos:
            b0, b1 = _eixo_perpendicular(grupo[0].rect, grupo[0].rotacion)
            if grupo[0].rotacion == p.rotacion and abs((a0 + a1) - (b0 + b1)) / 2 < min(a1 - a0, b1 - b0) / 2:
                grupo.append(p)
                break
        else:
            grupos.append([p])
    return grupos


# Distorsión real atopada relendo os PDF de saída do corpus web (BOE,
# 29/09/2026): a caixa de cada palabra de `get_text("words")` mide o alto
# da fonte (ascendente+descendente, 14,3 pt nun BOE) pero as liñas van a
# 12 pt, así que se solapa uns 2 pt coa liña de enriba e coa de debaixo.
# `apply_redactions` borra CALQUERA carácter cuxa caixa toque o
# rectángulo: cada substitución levaba tamén os anacos das liñas veciñas
# que caían no seu ancho ("Presupuestos Generales del Estado" deixaba en
# branco tres liñas). O rectángulo recórtase ata onde empezan as palabras
# das liñas veciñas: os caracteres do propio dato seguen tocándoo e
# bórranse enteiros igual.
_AIRE_LIÑA_VECIÑA = 0.25  # puntos PDF


def _sen_invadir_liñas_veciñas(rect: "fitz.Rect", rotacion: int, palabras: list, propias: frozenset) -> "fitz.Rect":
    vertical = rotacion in (90, 270)
    lo0, lo1 = _eixo_perpendicular(rect, rotacion)
    centro = (lo0 + lo1) / 2
    mesma_liña = (lo1 - lo0) / 4
    r0, r1 = (rect.y0, rect.y1) if vertical else (rect.x0, rect.x1)
    for p in palabras:
        if id(p) in propias:
            continue
        q = fitz.Rect(p.rect)
        l0, l1 = (q.y0, q.y1) if vertical else (q.x0, q.x1)
        if l1 <= r0 or l0 >= r1:
            continue
        b0, b1 = _eixo_perpendicular(q, rotacion)
        if b1 <= lo0 or b0 >= lo1 or abs((b0 + b1) / 2 - centro) < mesma_liña:
            continue
        if (b0 + b1) / 2 < centro:
            lo0 = max(lo0, b1 + _AIRE_LIÑA_VECIÑA)
        else:
            lo1 = min(lo1, b0 - _AIRE_LIÑA_VECIÑA)
    if lo1 - lo0 < 1.0:  # liñas case superpostas: só a franxa central
        lo0, lo1 = centro - 0.5, centro + 0.5
    recortado = fitz.Rect(rect)
    if vertical:
        recortado.x0, recortado.x1 = lo0, lo1
    else:
        recortado.y0, recortado.y1 = lo0, lo1
    return recortado


_SOLAPE_MAXIMO_RECORTABLE = 0.35  # fracción do rectángulo: por riba, é o mesmo texto lido dúas veces


def _eixo_lectura(rect, rotacion: int) -> tuple:
    r = fitz.Rect(rect)
    return (r.y0, r.y1) if rotacion in (90, 270) else (r.x0, r.x1)


def _sen_invadir_nativas(rect: "fitz.Rect", rotacion: int, palabras: list, propias: frozenset) -> "fitz.Rect":
    """Rectángulo dun dato con tinta en píxeles (OCR): non se recorta polas
    liñas veciñas (a tinta pode chegar a elas), pero si se lle quita o que
    só ROZA palabras NATIVAS alleas -- o rectángulo do OCR dun logotipo
    levaba o pé "ISSN... Depósito legal..." que ía xunto a el. Se a nativa
    solapa máis dun `_SOLAPE_MAXIMO_RECORTABLE` do rectángulo, é o mesmo
    texto lido dúas veces e non se toca (mellor tapar de máis)."""
    r0, r1 = _eixo_lectura(rect, rotacion)
    p0, p1 = _eixo_perpendicular(rect, rotacion)
    for p in palabras:
        if id(p) in propias or p.ocr:
            continue
        q = fitz.Rect(p.rect)
        if not q.intersects(rect):
            continue
        q0, q1 = _eixo_lectura(q, rotacion)
        b0, b1 = _eixo_perpendicular(q, rotacion)
        mesma_liña = min(p1, b1) - max(p0, b0) > 0.5 * min(p1 - p0, b1 - b0)
        if mesma_liña:
            solape = min(r1, q1) - max(r0, q0)
            if solape <= 0 or solape > _SOLAPE_MAXIMO_RECORTABLE * (r1 - r0):
                continue
            if (q0 + q1) / 2 < (r0 + r1) / 2:
                r0 = max(r0, q1 + _AIRE_LIÑA_VECIÑA)
            else:
                r1 = min(r1, q0 - _AIRE_LIÑA_VECIÑA)
        else:
            solape = min(p1, b1) - max(p0, b0)
            if solape <= 0 or solape > _SOLAPE_MAXIMO_RECORTABLE * (p1 - p0):
                continue
            if (b0 + b1) / 2 < (p0 + p1) / 2:
                p0 = max(p0, b1 + _AIRE_LIÑA_VECIÑA)
            else:
                p1 = min(p1, b0 - _AIRE_LIÑA_VECIÑA)
    if r1 - r0 < 1.0 or p1 - p0 < 1.0:
        return fitz.Rect(rect)
    if rotacion in (90, 270):
        return fitz.Rect(p0, r0, p1, r1)
    return fitz.Rect(r0, p0, r1, p1)


def _redactar_e_reescribir_paxina(pagina: "fitz.Page", substitucions_locais: list, palabras: list) -> None:
    """Redacta e insire o código de substitución para cada substitución
    desta páxina -- as redaccións agrúpanse e aplícanse de vez (máis
    eficiente e evita reordenacións intermedias)."""
    trazos = _trazos_da_paxina(pagina) if substitucions_locais else []
    agresivos, prudentes = [], []
    rects_por_substitucion = []
    for inicio, fin, novo in substitucions_locais:
        tocadas = _rects_das_palabras_no_intervalo(palabras, inicio, fin)
        if not tocadas:
            continue
        propias = frozenset(id(p) for p in tocadas)
        # Un rectángulo POR LIÑA: a unión dunha entidade partida en dúas
        # liñas ("Lidia Sáez\nMateu") collía as dúas liñas enteiras de
        # lado a lado, co texto alleo que houbese nelas.
        pezas = []
        for liña in _por_liña_visual(tocadas):
            rect = fitz.Rect(liña[0].rect)
            for p in liña[1:]:
                rect |= fitz.Rect(p.rect)
            pezas.append((rect, liña[0].rotacion, any(p.ocr for p in liña)))
        # O código vai na peza máis longa (a única, no caso normal).
        rect_insercion, rotacion, _ = max(
            pezas, key=lambda par: par[0].height if par[1] in (90, 270) else par[0].width
        )
        altura_veciña = _altura_veciña(palabras, tuple(rect_insercion), excluir=propias)
        for rect, rotacion_peza, en_pixeles in pezas:
            # Con tinta en píxeles (escaneo, OCR) recortar polas liñas
            # veciñas deixaría tinta do dato á vista -- mellor tapar de máis.
            # Un texto vectorial sobre unha imaxe de fondo (plano) si recorta.
            if en_pixeles:
                rect = _sen_invadir_nativas(rect, rotacion_peza, palabras, propias)
            else:
                rect = _sen_invadir_liñas_veciñas(rect, rotacion_peza, palabras, propias)
            # O rectángulo AMPLIADO (A25) só se usa para tachar: o código
            # insírese no orixinal, que é o que ten o tamaño do texto que
            # substitúe (co ampliado sairía nunha letra desproporcionada).
            ampliado, hai_trazos_grandes = _ampliar_con_trazos(rect, trazos)
            (prudentes if hai_trazos_grandes else agresivos).append(ampliado)
        rects_por_substitucion.append((rect_insercion, novo, rotacion, altura_veciña))

    if not rects_por_substitucion:
        return

    # images=2 (por defecto en `apply_redactions`): tapa tamén píxeles de
    # imaxe superpostos -- imprescindible nunha páxina escaneada, onde o
    # "texto" é só imaxe.
    _redactar_rects(pagina, agresivos, prudentes)

    for rect_total, novo, rotacion, altura_veciña in rects_por_substitucion:
        _inserir_texto_axustado(pagina, rect_total, novo, rotacion, altura_veciña)


# Erro real atopado nunha auditoría (A23): nunha páxina densa (76 liñas a
# 8 pt) cun só cambio feito a man na pantalla de revisión, o texto
# reescrito non collía na caixa a 11 pt. `insert_textbox` NON escribe
# nada cando non cabe (devolve un número negativo, o que falta), pero
# ninguén miraba ese valor: a páxina, xa redactada enteira, quedaba EN
# BRANCO -- 0 caracteres -- sen ningún aviso. Non é unha fuga de datos,
# pero si a perda completa do contido dunha páxina.
#
# Agora búscase primeiro o tamaño de letra co que cabe, e a proba faise
# nunha páxina desbotable: cando `insert_textbox` responde que non
# cabía, o orixinal xa está destruído e non hai volta atrás.
_TAMANO_RESERVA = 11  # o de sempre: só se baixa del se non hai outra
_TAMANO_RESERVA_MINIMO = 5  # por debaixo disto xa non é lexible en papel
_FACTOR_ENCOLLIDO = 0.9


def _tamano_que_cabe(rect: "fitz.Rect", texto: str, rotacion: int) -> float | None:
    """Maior tamaño de letra (empezando en `_TAMANO_RESERVA`) co que
    `texto` cabe enteiro en `rect`, ou `None` se nin o mínimo chega."""
    documento_proba = fitz.open()
    try:
        pagina_proba = documento_proba.new_page(width=rect.x1 + 1, height=rect.y1 + 1)
        tamano = float(_TAMANO_RESERVA)
        while tamano >= _TAMANO_RESERVA_MINIMO:
            sobra = pagina_proba.insert_textbox(
                rect, texto, fontsize=tamano, fontname=_FONTE_SAIDA, rotate=rotacion,
            )
            if sobra >= 0:
                return tamano
            tamano *= _FACTOR_ENCOLLIDO
        return None
    finally:
        documento_proba.close()


def _redactar_paxina_completa(pagina: "fitz.Page", texto_novo: str) -> None:
    """Reserva cando un letrado editou a man o texto desta páxina: xa non
    hai forma fiable de saber que palabra orixinal corresponde a cada
    cambio, así que se redacta a páxina ENTEIRA e reescríbese co texto
    final en fonte xenérica -- perde o formato orixinal desa páxina
    concreta, pero segue sendo un PDF válido có texto correcto."""
    # A5: en coordenadas SEN rotar (ver `_rect_visible_sen_rotar`) -- con
    # `pagina.rect` tal cal, nunha páxina con /Rotate 90/270 quedaba unha
    # franxa do contido orixinal sen tapar.
    visible = _rect_visible_sen_rotar(pagina)
    caixa = visible + (18, 18, -18, -18)
    rotacion = _rotacion_visual(pagina)
    tamano = _tamano_que_cabe(caixa, texto_novo, rotacion)
    if tamano is None:
        # Compróbase ANTES de redactar: así o PDF de saída nin se escribe
        # e o letrado recibe unha explicación, en vez dunha páxina baleira.
        raise ValueError(
            f"o texto revisado non colle na páxina nin reducindo a letra a "
            f"{_TAMANO_RESERVA_MINIMO} puntos ({len(texto_novo)} caracteres). "
            "Esta páxina hai que reescribila enteira porque se editou o seu "
            "texto a man: acurta o engadido ou reparte o texto entre varias "
            "páxinas antes de gardar."
        )
    # A páxina enteira vaise reescribir, así que aquí `graphics=2` (A25)
    # non ten a pega de sempre: non hai formato que conservar nela e así
    # non queda dentro do ficheiro ningún trazo vectorial do orixinal.
    pagina.add_redact_annot(visible, fill=(1, 1, 1))
    pagina.apply_redactions(graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED)
    pagina.insert_textbox(
        caixa, texto_novo, fontsize=tamano, fontname=_FONTE_SAIDA, rotate=rotacion,
    )


# Códigos QR e de barras: un elemento VISUAL, independente de se a páxina
# ten texto nativo ou é escaneada -- por iso se detecta sempre sobre unha
# imaxe renderizada da páxina enteira (mesmo DPI que xa se usa para OCR),
# nunca sobre o texto extraído. Un QR de verificación (moi habitual en
# documentos oficiais españois, ex. xunto ao CSV) pode codificar datos
# persoais directamente, ou seren a clave para consultalos no portal do
# organismo emisor -- o mesmo risco xa asumido para o propio CSV en texto
# (`recognizers._CSV_ETIQUETA`).
#
# A PROPÓSITO só se DETECTA a posición (`detectMulti`, nunca
# `detectAndDecodeMulti`): esixir que se poida DECODIFICAR deixaría sen
# redactar un código danado, rotado ou de resolución insuficiente para
# ler -- que pode seguir a conter datos persoais igual, aínda sen poder
# comprobalo. Mellor redactar un código de máis (falso positivo raro,
# ex. un debuxo cadriculado casual) que deixar escapar un de menos.
#
# LÍMITE COÑECIDO: os detectores de OpenCV non cobren os códigos 2D que
# non son QR (DataMatrix sobre todo) -- ver `codigos.py`, onde está o
# diagnóstico completo e o que faría falta para cubrilos.
_DPI_CODIGOS = _DPI_OCR
_MARXE_CODIGO = 3  # puntos PDF, para cubrir tamén a "zona muda" ao redor


def _detectar_rects_codigos(pagina: "fitz.Page") -> list:
    """Devolve os rectángulos (coordenadas PDF, en puntos) de tódolos QR e
    códigos de barras atopados na páxina."""
    escala = _DPI_CODIGOS / 72
    matriz = fitz.Matrix(escala, escala)
    pix = pagina.get_pixmap(matrix=matriz, colorspace=fitz.csGRAY)
    imaxe = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    visible = _rect_visible_sen_rotar(pagina)

    rects = []
    for detector in (cv2.QRCodeDetector(), cv2.barcode_BarcodeDetector()):
        try:
            atopado, cuadrilateros = detector.detectMulti(imaxe)
        except cv2.error:
            continue
        if not atopado:
            continue
        for cuad in cuadrilateros:
            xs, ys = cuad[:, 0], cuad[:, 1]
            # A5: coordenadas do render -> SEN rotar (ver `_rect_pixmap_a_paxina`)
            rect = _rect_pixmap_a_paxina(pagina, pix, matriz, xs.min(), ys.min(), xs.max(), ys.max())
            rects.append((rect + (-_MARXE_CODIGO, -_MARXE_CODIGO, _MARXE_CODIGO, _MARXE_CODIGO)) & visible)
    # Un mesmo código adoita dar varias deteccións parciais solapadas
    # (dous anacos do mesmo código de barras, p.ex.): fundilas antes de
    # tachar é o que permite que o debuxo vectorial completo do código
    # quede DENTRO dun só rectángulo e se poida eliminar de verdade (A25).
    return _fusionar_rects(rects)


def _redactar_codigos_da_paxina(pagina: "fitz.Page") -> None:
    rects = _detectar_rects_codigos(pagina)
    if not rects:
        return
    # Mesmo problema ca co texto vectorizado (A25): un QR ou un código de
    # barras DEBUXADO (non incrustado coma imaxe) só desaparece do
    # ficheiro se o rectángulo o cobre enteiro -- se non, queda tapado
    # polo recadro branco pero segue en `get_drawings()`.
    trazos = _trazos_da_paxina(pagina)
    agresivos, prudentes = [], []
    for rect in rects:
        ampliado, hai_trazos_grandes = _ampliar_con_trazos(rect, trazos)
        (prudentes if hai_trazos_grandes else agresivos).append(ampliado)
    _redactar_rects(pagina, agresivos, prudentes)
    for rect in rects:
        pagina.insert_textbox(
            rect, "[CODIGO]", fontsize=8, fontname=_FONTE_SAIDA, align=1, rotate=_rotacion_visual(pagina),
        )


# Sinatura dixital (campo de formulario "Signature"): outro elemento
# VISUAL independente do texto da páxina, coma os códigos QR de arriba --
# pero por un motivo distinto. Caso real atopado nun informe técnico
# asinado: o selo visual que debuxa Adobe/AutoFirma ("Firmado digitalmente
# por..., Nombre de reconocimiento (DN): ..., serialNumber=IDCES-<DNI>,
# givenName=<nome>, sn=<apelidos>...") NON forma parte do texto da páxina
# (`pagina.get_text("words")`) -- vive na "appearance stream" propia do
# WIDGET de sinatura, invisible tanto para `recognizers.py` coma para
# `ner.py` por moito que se probase o patrón illado (funciona perfecto
# fóra de contexto). Redactar SÓ o DNI/nome dentro dese selo esixiría
# entrar na propia appearance stream do widget (formato distinto segundo
# a ferramenta de sinatura -- Adobe, AutoFirma, FNMT...), moi fráxil.
#
# Elimínase o widget ENTEIRO no seu lugar: calquera edición a un PDF
# asinado xa invalida a sinatura criptográfica orixinal, así que manter o
# selo visual despois de anonimizar sería enganoso (parece un documento
# asinado e sen tocar, cando xa non o é). É ademais a única forma que
# cobre calquera ferramenta de sinatura de vez, sen depender do seu
# formato de texto concreto.
def _retirar_sinaturas_dixitais_da_paxina(pagina: "fitz.Page") -> list:
    """Elimina os widgets de sinatura da páxina e devolve os rectángulos
    dos que tiñan selo visual, para redactalos e etiquetalos ao gardar
    (`_etiquetar_sinaturas_dixitais`). Faise xa na CARGA -- antes de
    `_preparar_documento` aplanar o resto de widgets, para que o selo non
    acabe convertido en contido da páxina."""
    widgets_sinatura = [
        w for w in (pagina.widgets() or []) if w.field_type_string == "Signature"
    ]
    # Caso real: un certificado de apoderamento xudicial ten dous campos de
    # sinatura SEN selo visual ningún (validación puramente electrónica,
    # non pensados para amosarse) -- o seu `rect` vén baleiro (área cero,
    # ex. `Rect(0, 842, 0, 842)`). `insert_textbox` esixe un rectángulo
    # finito e NON baleiro, así que só se insire a etiqueta nos que si
    # ocupan espazo real na páxina; o widget elimínase igual en calquera
    # caso (nunca hai nada que redactar visualmente se non hai selo).
    rects = [fitz.Rect(w.rect) for w in widgets_sinatura if not w.rect.is_empty]
    for widget in widgets_sinatura:
        pagina.delete_widget(widget)
    return rects


def _etiquetar_sinaturas_dixitais(pagina: "fitz.Page", rects: list) -> None:
    if not rects:
        return
    for rect in rects:
        pagina.add_redact_annot(rect, fill=(1, 1, 1))
    pagina.apply_redactions()
    for rect in rects:
        pagina.insert_textbox(
            rect, "[SINATURA_DIXITAL]", fontsize=8, fontname=_FONTE_SAIDA, align=1,
            rotate=_rotacion_visual(pagina),
        )


def _eliminar_sinaturas_dixitais_da_paxina(pagina: "fitz.Page") -> None:
    """Retirada + etiqueta nun só paso (compatibilidade con chamadores que
    non pasan por `cargar_pdf_estruturado`)."""
    _etiquetar_sinaturas_dixitais(pagina, _retirar_sinaturas_dixitais_da_paxina(pagina))


# -- contido oculto e anotacións: preparación ANTES de extraer ----------------
#
# Fugas atopadas nunha auditoría (A6, A3): contido que non se ve nun visor
# normal, e que por iso nin se analizaba nin se redactaba, pero que
# seguía no ficheiro de saída:
#
# - Capas opcionais (OCG) apagadas: `get_text` non as extrae, pero o seu
#   texto segue no fluxo de contido. Quítase /OCProperties do catálogo --
#   sen el, tódalas capas (e as OCMD que dependían delas) pasan a
#   visibles -- e o documento recárgase: así o seu texto entra no texto
#   de revisión e redáctase coma o resto. POLÍTICA: mellor ver na saída
#   (xa anonimizado) o que estaba oculto ca deixalo sen revisar dentro.
# - Texto/imaxes fóra do CropBox (pero dentro do MediaBox): redáctase todo
#   o que quede fóra da área visible (o CropBox consérvase).
# - Anotacións: as de comentario/adxunto/multimedia (nota adhesiva,
#   "popup", ficheiro adxunto, son, vídeo...) elimínanse enteiras -- o seu
#   contido (autor, texto do comentario, ficheiro) non se ve na páxina e
#   non ten sentido conservalo nun documento anonimizado. As redaccións
#   pendentes (/Redact sen aplicar) aplícanse. O resto de anotacións
#   visibles (texto libre, selos, tinta, formas, subliñados) e os campos
#   de formulario ("widgets") APLÁNANSE (`bake`): o que se vía pasa a ser
#   contido normal da páxina, e así o texto que levaban (ex. o valor dun
#   campo "Demandante") analízase e redáctase coma calquera outro; a
#   anotación/campo en si (co seu autor, valor, etc.) desaparece. As
#   ligazóns consérvanse aquí (ver `_limpar_documento` para as URI).
# - Sinaturas dixitais: ver `_retirar_sinaturas_dixitais_da_paxina`.
_ANOTACIONS_A_ELIMINAR = frozenset({
    fitz.PDF_ANNOT_TEXT, fitz.PDF_ANNOT_POPUP, fitz.PDF_ANNOT_FILE_ATTACHMENT,
    fitz.PDF_ANNOT_SOUND, fitz.PDF_ANNOT_MOVIE, fitz.PDF_ANNOT_SCREEN,
    fitz.PDF_ANNOT_RICH_MEDIA, fitz.PDF_ANNOT_3D, fitz.PDF_ANNOT_PROJECTION,
})


def _caixa_bruta(documento: "fitz.Document", xref: int, chave: str) -> "fitz.Rect | None":
    """/MediaBox ou /CropBox tal e como está no PDF (coordenadas PDF, orixe
    abaixo á esquerda), seguindo a herdanza dende os nodos /Pages pais.
    Non se usan `pagina.mediabox`/`pagina.cropbox`: probado que con un
    MediaBox desprazado (ex. [-50 -50 595 842]) devolven valores
    incoherentes entre si."""
    for _ in range(64):  # protección contra ciclos /Parent
        tipo, valor = documento.xref_get_key(xref, chave)
        if tipo == "xref":
            tipo, valor = "array", documento.xref_object(int(valor.split()[0]))
        if tipo == "array":
            try:
                return fitz.Rect([float(v) for v in valor.strip().strip("[]").split()]).normalize()
            except (ValueError, TypeError):
                return None
        tipo, pai = documento.xref_get_key(xref, "Parent")
        if tipo != "xref":
            return None
        xref = int(pai.split()[0])
    return None


def _redactar_fora_do_cropbox(pagina: "fitz.Page") -> None:
    documento = pagina.parent
    mediabox = _caixa_bruta(documento, pagina.xref, "MediaBox")
    if mediabox is None:
        return
    cropbox = _caixa_bruta(documento, pagina.xref, "CropBox")
    cropbox = mediabox if cropbox is None else (cropbox & mediabox)
    if cropbox.is_empty or cropbox == mediabox:
        return
    # Coordenadas SEN rotar da páxina: orixe na esquina superior esquerda
    # do CropBox, y cara abaixo -- (X, Y) do PDF -> (X - c.x0, c.y1 - Y).
    # Redáctanse as catro franxas do MediaBox que quedan fóra do CropBox
    # (as anotacións de redacción poden ir fóra de `pagina.rect`).
    mb = fitz.Rect(
        mediabox.x0 - cropbox.x0, cropbox.y1 - mediabox.y1,
        mediabox.x1 - cropbox.x0, cropbox.y1 - mediabox.y0,
    )
    cb = fitz.Rect(0, 0, cropbox.width, cropbox.height)
    franxas = (
        fitz.Rect(mb.x0, mb.y0, mb.x1, cb.y0),
        fitz.Rect(mb.x0, cb.y1, mb.x1, mb.y1),
        fitz.Rect(mb.x0, cb.y0, cb.x0, cb.y1),
        fitz.Rect(cb.x1, cb.y0, mb.x1, cb.y1),
    )
    redactar = [r for r in franxas if not r.is_empty]
    for rect in redactar:
        pagina.add_redact_annot(rect, fill=(1, 1, 1))
    if redactar:
        pagina.apply_redactions()


def _preparar_documento(documento: "fitz.Document") -> tuple:
    """Devolve (documento_listo_para_extraer, rects_sinaturas_por_páxina).
    Pode devolver un documento NOVO (recargado en memoria) -- ver o
    comentario de arriba para o que fai e por que."""
    modificado = False

    if documento.is_pdf:
        catalogo = documento.pdf_catalog()
        if documento.xref_get_key(catalogo, "OCProperties")[0] != "null":
            documento.xref_set_key(catalogo, "OCProperties", "null")
            modificado = True

    if documento.is_pdf and _quitar_texto_alternativo(documento):
        modificado = True

    sinaturas = []
    aplanar = False
    for pagina in documento:
        sinaturas.append(_retirar_sinaturas_dixitais_da_paxina(pagina))

        redaccions_pendentes = False
        for anotacion in list(pagina.annots() or []):
            tipo = anotacion.type[0]
            if tipo in _ANOTACIONS_A_ELIMINAR:
                pagina.delete_annot(anotacion)
                modificado = True
            elif tipo == fitz.PDF_ANNOT_REDACT:
                redaccions_pendentes = True
            else:
                aplanar = True
        if redaccions_pendentes:
            pagina.apply_redactions()
            modificado = True
        if any(True for _ in (pagina.widgets() or [])):
            aplanar = True

        _redactar_fora_do_cropbox(pagina)

    if aplanar:
        documento.bake(annots=True, widgets=True)
        modificado = True

    if modificado:
        # Recárgase dende os bytes: tras `bake` (e tras cambiar as capas
        # opcionais) PyMuPDF segue a ver en memoria o estado anterior --
        # probado: o texto aplanado saía DUPLICADO en `get_text` ata recargar.
        documento = fitz.open("pdf", documento.tobytes())
    return documento, sinaturas


# -- limpeza a nivel de documento, ANTES de gardar ---------------------------
#
# Fuga atopada nunha auditoría (A3): a nivel de documento non se limpaba
# nada. POLÍTICA (sempre, sen opción de desactivala):
# - Metadatos: baléirase o dicionario /Info (título, autor, asunto,
#   palabras clave, creador, produtor, datas) e elimínase o XMP -- do
#   documento e de CALQUERA obxecto que o leve (páxinas, imaxes...).
# - Marcadores/índice (/Outlines): elimínanse (os títulos adoitan levar
#   nomes das partes).
# - Ficheiros adxuntos (/EmbeddedFiles) e JavaScript do documento:
#   elimínanse; tamén /OpenAction e /AA (accións automáticas).
# - Sinaturas: /Perms e /DSS (levan o certificado do asinante, co seu
#   nome e DNI) elimínanse; /AcroForm tamén (os campos xa se aplanaron).
# - Anotacións: elimínanse TODAS as que queden (as de redacción xa están
#   aplicadas); das ligazóns só se conservan as INTERNAS (ir a unha páxina
#   ou destino do propio documento) -- as URI (ex. un mailto: co correo e
#   o DNI no asunto), de lanzar programa ou a outro ficheiro elimínanse.
# - Miniaturas (/Thumb) e /PieceInfo das páxinas: elimínanse.
# - Texto alternativo: /ActualText e /Alt elimínanse tanto dos
#   dicionarios (árbore de estrutura, listas de propiedades) coma dos
#   dicionarios en liña dos fluxos de contido (`/Span <</ActualText
#   (...)>> BDC`); dos elementos de estrutura quítanse tamén /T e /E. A
#   árbore de estrutura consérvase (accesibilidade), sen eses textos.
_CHAVES_CATALOGO_A_ELIMINAR = (
    "OpenAction", "AA", "Perms", "DSS", "AcroForm", "PieceInfo",
    "SpiderInfo", "Threads", "Collection", "Metadata",
)
_CHAVES_PAXINA_A_ELIMINAR = ("Thumb", "PieceInfo", "AA")
_LIGAZONS_A_CONSERVAR = frozenset({fitz.LINK_GOTO, fitz.LINK_NAMED})
_TEXTO_ALTERNATIVO_EN_FLUXO = re.compile(rb"/(?:ActualText|Alt)\s*(?=[(<])")


def _saltar_cadea_pdf(datos: bytes, i: int) -> int:
    """`datos[i]` é "(" ou "<": devolve a posición xusto despois da cadea
    (literal con parénteses aniñadas e escapes, ou hexadecimal)."""
    if datos[i:i + 1] == b"<":
        fin = datos.find(b">", i)
        return len(datos) if fin < 0 else fin + 1
    nivel = 0
    j = i
    while j < len(datos):
        c = datos[j:j + 1]
        if c == b"\\":
            j += 2
            continue
        if c == b"(":
            nivel += 1
        elif c == b")":
            nivel -= 1
            if nivel == 0:
                return j + 1
        j += 1
    return len(datos)


def _quitar_texto_alternativo_do_fluxo(datos: bytes) -> bytes:
    anacos = []
    cursor = 0
    for m in _TEXTO_ALTERNATIVO_EN_FLUXO.finditer(datos):
        if m.start() < cursor or datos[m.end():m.end() + 2] == b"<<":
            continue
        anacos.append(datos[cursor:m.start()])
        cursor = _saltar_cadea_pdf(datos, m.end())
    if not anacos:
        return datos
    anacos.append(datos[cursor:])
    return b"".join(anacos)


def _limpar_documento(documento: "fitz.Document") -> None:
    documento.set_metadata({})
    documento.del_xml_metadata()
    documento.set_toc([])
    for nome in list(documento.embfile_names()):
        documento.embfile_del(nome)

    catalogo = documento.pdf_catalog()
    for chave in _CHAVES_CATALOGO_A_ELIMINAR:
        documento.xref_set_key(catalogo, chave, "null")
    if documento.xref_get_key(catalogo, "Names")[0] == "dict":
        for chave in ("JavaScript", "EmbeddedFiles"):
            documento.xref_set_key(catalogo, f"Names/{chave}", "null")

    for pagina in documento:
        for anotacion in list(pagina.annots() or []):
            pagina.delete_annot(anotacion)
        for widget in list(pagina.widgets() or []):
            pagina.delete_widget(widget)
        for ligazon in pagina.get_links():
            if ligazon["kind"] not in _LIGAZONS_A_CONSERVAR:
                pagina.delete_link(ligazon)
        for chave in _CHAVES_PAXINA_A_ELIMINAR:
            documento.xref_set_key(pagina.xref, chave, "null")

    _quitar_texto_alternativo(documento)


def _quitar_texto_alternativo(documento: "fitz.Document") -> bool:
    """Quita /ActualText e /Alt (e /T, /E dos elementos de estrutura) e o
    XMP de calquera obxecto, e /ActualText//Alt dos fluxos de contido.
    Chámase xa na CARGA (`_preparar_documento`): MuPDF usa o /ActualText
    EN VEZ dos glifos reais ao extraer o texto, así que un /ActualText cun
    nome desviaba o texto analizado e as coordenadas das palabras (probado:
    tachaba palabras que non eran). Devolve se cambiou algo."""
    modificado = False
    xrefs_contido = set()
    for pagina in documento:
        xrefs_contido.update(pagina.get_contents())

    for xref in range(1, documento.xref_length()):
        try:
            tipo = documento.xref_get_key(xref, "Type")[1]
            chaves = ("ActualText", "Alt", "Metadata")
            if tipo == "/StructElem":
                chaves += ("T", "E")
            for chave in chaves:
                if documento.xref_get_key(xref, chave)[0] != "null":
                    documento.xref_set_key(xref, chave, "null")
                    modificado = True
            if documento.xref_get_key(xref, "Subtype")[1] == "/Form":
                xrefs_contido.add(xref)
        except Exception:  # obxecto roto/libre: non hai nada que limpar
            continue

    for xref in xrefs_contido:
        try:
            datos = documento.xref_stream(xref)
        except Exception:
            continue
        if datos and (b"/ActualText" in datos or b"/Alt" in datos):
            limpo = _quitar_texto_alternativo_do_fluxo(datos)
            if limpo != datos:
                documento.update_stream(xref, limpo)
                modificado = True
    return modificado


def gardar_pdf_estruturado(contexto: dict, texto_final: str, ruta_saida: str, substitucions: list) -> None:
    """Escribe `texto_final` de volta no PDF orixinal, conservando
    formato e extensión. Lanza ValueError se o número de "páxinas" do
    texto (posiblemente editado) xa non coincide co orixinal -- engadir
    ou quitar un separador de páxina desaliñaría a escritura."""
    partes = texto_final.split(SEPARADOR_PAXINAS)
    paxinas = contexto["paxinas"]
    if len(partes) != len(paxinas):
        raise ValueError(
            f"o texto ten {len(partes)} páxina(s) pero o PDF orixinal ten "
            f"{len(paxinas)} páxina(s) -- non se pode conservar o formato "
            "(evita engadir ou quitar liñas baleiras completas ao revisar o texto)"
        )

    documento = contexto["documento"]
    limites = _limites_paxinas(paxinas) if substitucions is not None else None

    for i, (paxina_info, texto_novo) in enumerate(zip(paxinas, partes)):
        pagina = documento[i]
        substitucions_locais = None
        if substitucions is not None:
            p_inicio, p_fin = limites[i]
            locais = [
                (s[0] - p_inicio, s[1] - p_inicio, s[2])
                for s in substitucions
                if p_inicio <= s[0] and s[1] <= p_fin
            ]
            if _aplicar_substitucions_a_texto(paxina_info.texto, locais) == texto_novo:
                substitucions_locais = locais

        if substitucions_locais is not None:
            _redactar_e_reescribir_paxina(pagina, substitucions_locais, paxina_info.palabras)
        else:
            _redactar_paxina_completa(pagina, texto_novo)

        # Pasada independente do texto: QR e códigos de barras son un
        # elemento VISUAL (ver `_redactar_codigos_da_paxina`), así que se
        # detectan e redactan sempre, tanto se esta páxina caeu na reserva
        # (edición a man) coma se non.
        _redactar_codigos_da_paxina(pagina)

        # Mesmo principio para o selo de sinatura dixital (ver
        # `_eliminar_sinaturas_dixitais_da_paxina`) -- vive nun WIDGET, non
        # no texto da páxina, así que non depende de se a páxina caeu ou
        # non na reserva. O widget xa se retirou na carga
        # (`_preparar_documento`); aquí redáctase o seu sitio e etiquétase.
        if "sinaturas" in contexto:
            _etiquetar_sinaturas_dixitais(pagina, contexto["sinaturas"][i])
        else:
            _eliminar_sinaturas_dixitais_da_paxina(pagina)

    # Metadatos, adxuntos, anotacións, ligazóns URI, miniaturas, texto
    # alternativo... (ver `_limpar_documento`).
    _limpar_documento(documento)

    # CRÍTICO: sen isto, o obxecto de imaxe ORIXINAL (sen redactar) queda
    # no ficheiro coma "orfo" -- xa non o amosa a páxina, pero segue sendo
    # extraíble directamente do PDF (ex. fitz.Pixmap(doc, xref)) por
    # calquera ferramenta que percorra o propio ficheiro, aínda que ningún
    # visor normal o mostre. `garbage=4` elimina tódolos obxectos xa non
    # referenciados (a máxima limpeza que ofrece PyMuPDF); `deflate=True`
    # comprime ademais os fluxos, evitando que o ficheiro medre moito
    # trala redacción. Atopado probando contra documentos reais escaneados
    # do despacho -- un ficheiro chegou a pasar de 6,8 MB a 346 MB.
    documento.save(ruta_saida, garbage=4, deflate=True)
