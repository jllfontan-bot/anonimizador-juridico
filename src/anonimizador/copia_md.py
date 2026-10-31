"""Copia en Markdown (.md) do documento anonimizado.

Para que Claude (ou calquera outra ferramenta) lea o resultado SEN ter que
convertelo: un PDF chégalle coma texto e ademais coma imaxe de cada páxina,
e un .docx/.odt nin sequera o le directamente. A copia vai canda o
documento anonimizado de sempre (`<saída>.md`, ex.
`demanda.anonimizado.pdf.md`), que non cambia en nada.

SEGURIDADE: todo o TEXTO da copia sae do texto xa anonimizado (o mesmo
que se garda no documento: `texto_final`, revisado se houbo revisión). Do
documento orixinal só se le a ESTRUTURA -- estilo de cada parágrafo, listas,
táboas e caixas das celas --, nunca texto. Un parágrafo ou unha cela que non
estea no texto anonimizado (unha estrutura que o anonimizador non le) non
sae na copia.

Estrutura que se conserva:
  - .docx/.odt: títulos, listas (coa súa numeración), táboas (na súa
    posición) e, ao final, cabeceiras e pés de páxina.
  - PDF: marca de cada páxina (`<!-- páxina N -->`) e as táboas con liñas
    (as mesmas que ve `page.find_tables()`, ver `taboas_pdf.py`). Títulos e
    listas non: un PDF non garda que é un título.
  - Imaxes: o texto do OCR.
Se o texto revisado xa non casa coa estrutura (edición libre que engade ou
quita liñas), a copia é o texto tal cal, sen estrutura.
"""

from __future__ import annotations

import bisect
import re
from pathlib import Path

import fitz  # PyMuPDF
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from odf.element import Element as ElementoOdt
from odf.namespaces import STYLENS, TABLENS, TEXTNS

from . import idioma, taboas_pdf
from .pdf_estrutura import SEPARADOR_PAXINAS, _limites_paxinas
from .lectura import (
    _agrupar_liñas_por_paragrafo,
    _aplicar_substitucions_a_texto,
    _cabeceiras_e_pes_docx,
    _paragrafos_dun_contedor_docx,
)
from .registry import substituir_con_reintentos

def ruta_copia(ruta_saida: str) -> str | None:
    """`demanda.anonimizado.pdf` -> `demanda.anonimizado.pdf.md`. Coa
    extensión do documento dentro do nome, un `demanda.pdf` e un
    `demanda.docx` do mesmo cartafol non escriben na mesma copia. `None`
    se a saída xa é un .md (entrada .md): non fai falta copia."""
    if Path(ruta_saida).suffix.lower() == ".md":
        return None
    return str(ruta_saida) + ".md"


def escribir(texto_md: str, ruta_saida: str) -> str | None:
    ruta = ruta_copia(ruta_saida)
    if ruta is None:
        return None
    Path(ruta).write_text(texto_md, encoding="utf-8")
    return ruta


def mover(ruta_saida_provisional: str, ruta_saida_final: str) -> None:
    """Renomea a copia canda o documento (o nome final, anonimizado,
    calcúlase despois de procesar o contido)."""
    orixe, destino = ruta_copia(ruta_saida_provisional), ruta_copia(ruta_saida_final)
    if orixe and destino and orixe != destino and Path(orixe).exists():
        substituir_con_reintentos(Path(orixe), Path(destino))


def xerar(contexto: dict | None, texto_final: str, substitucions: list | None = None) -> str:
    """Markdown de `texto_final` (texto anonimizado). Chamar ANTES de gardar
    o documento: gardar un PDF redacta `contexto["documento"]` no sitio, e
    as táboas buscánse nas páxinas sen redactar."""
    if contexto is None:
        return _texto_plano(texto_final)
    if contexto.get("imaxe"):
        return _pdf(contexto, texto_final, substitucions, marcar_paxinas=False)
    if contexto["tipo"] == "pdf":
        return _pdf(contexto, texto_final, substitucions, marcar_paxinas=True)
    textos = _textos_por_paragrafo(contexto, texto_final)
    if textos is None:
        return _liñas_coma_paragrafos(texto_final)
    if contexto["tipo"] == "docx":
        return _docx(contexto, textos)
    return _odt(contexto, textos)


# -- texto ------------------------------------------------------------------

_INICIO_CON_SIGNIFICADO = re.compile(r"(#{1,6}(\s|$)|>|```|~~~|<[A-Za-z!/?])")
_SO_RAIAS = re.compile(r"[-*_=](\s*[-*_=])*")


def _escapar_liña(liña: str) -> str:
    """Unha liña dun escrito que empeza por "#" ou que é só "-----" non debe
    converterse en título ou en raia. A sangría quítase: catro espazos
    diante serían un bloque de código."""
    liña = liña.strip()
    if _INICIO_CON_SIGNIFICADO.match(liña) or _SO_RAIAS.fullmatch(liña):
        return "\\" + liña
    return liña


def _escapar_cela(texto: str) -> str:
    return " ".join(texto.split()).replace("|", "\\|")


def _texto_plano(texto: str) -> str:
    """Liñas tal cal (escapadas); as liñas baleiras separan parágrafos."""
    liñas = [_escapar_liña(l) for l in texto.replace(SEPARADOR_PAXINAS, "\n\n").split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(liñas)).strip() + "\n"


def _liñas_coma_paragrafos(texto: str) -> str:
    liñas = [_escapar_liña(l) for l in texto.split("\n")]
    return "\n\n".join(l for l in liñas if l) + "\n"


def _limpar_bloque(texto: str) -> str:
    liñas = [_escapar_liña(l) for l in texto.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(liñas)).strip()


def _taboa_md(filas: list) -> str | None:
    """Táboa Markdown (a primeira fila fai de cabeceira). `None` se non é
    unha táboa de verdade: menos de dúas filas ou columnas con texto."""
    filas = [f for f in filas if any(f)]
    if not filas:
        return None
    n_columnas = max((i + 1 for f in filas for i, c in enumerate(f) if c), default=0)
    if len(filas) < 2 or n_columnas < 2:
        return None
    filas = [(f + [""] * n_columnas)[:n_columnas] for f in filas]
    liñas = ["| " + " | ".join(filas[0]) + " |", "|" + " --- |" * n_columnas]
    liñas += ["| " + " | ".join(f) + " |" for f in filas[1:]]
    return "\n".join(liñas)


def _unir_bloques(bloques: list) -> str:
    """`bloques`: (é_elemento_de_lista, texto). Os elementos de lista seguidos
    van en liñas seguidas; o resto, separado por unha liña baleira."""
    saida = []
    anterior_lista = False
    for e_lista, texto in bloques:
        if not texto:
            continue
        if saida:
            saida.append("\n" if e_lista and anterior_lista else "\n\n")
        saida.append(texto)
        anterior_lista = e_lista
    return "".join(saida)


def _engadir_cabeceiras(corpo: str, textos: list) -> str:
    vistos, liñas = set(), []
    for texto in textos:
        for liña in texto.split("\n"):
            liña = _escapar_liña(liña)
            if liña and liña not in vistos:
                vistos.add(liña)
                liñas.append(liña)
    if liñas:
        marca = f"<!-- {idioma.t('copia_md.cabeceiras')} -->"
        corpo = (corpo + "\n\n" if corpo else "") + marca + "\n\n" + "\n\n".join(liñas)
    return corpo + "\n"


def _textos_por_paragrafo(contexto: dict, texto_final: str) -> list | None:
    """Texto anonimizado de cada parágrafo (mesma correspondencia ca ao
    gardar o .docx/.odt), ou `None` se o número de liñas xa non casa."""
    orixinais = contexto["textos_orixinais"]
    partes = texto_final.split("\n")
    if len(partes) != sum(t.count("\n") + 1 for t in orixinais):
        return None
    return _agrupar_liñas_por_paragrafo(partes, orixinais)


def _numero(valor: int, formato: str) -> str:
    if formato in ("lowerLetter", "upperLetter", "a", "A"):
        letras = ""
        while valor > 0:
            valor, resto = divmod(valor - 1, 26)
            letras = chr(ord("a") + resto) + letras
        return letras.upper() if formato in ("upperLetter", "A") else letras
    if formato in ("lowerRoman", "upperRoman", "i", "I"):
        romano = ""
        for arabe, simbolo in ((1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"),
                               (50, "l"), (40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")):
            while valor >= arabe:
                romano += simbolo
                valor -= arabe
        return romano.upper() if formato in ("upperRoman", "I") else romano
    if formato == "decimalZero":
        return f"{valor:02d}"
    return str(valor)


# -- .docx ------------------------------------------------------------------

_ESTILO_TITULO_DOCX = re.compile(r"(?i)(heading|t[ií]tulo|encabezado)\s*([1-9])")


def _nivel_esquema_docx(pPr) -> int | None:
    if pPr is None:
        return None
    esquema = pPr.find(qn("w:outlineLvl"))
    if esquema is None:
        return None
    valor = int(esquema.get(qn("w:val"), "9"))
    return valor + 1 if valor < 9 else None


def _cadea_de_estilos(paragrafo) -> list:
    try:
        estilo = paragrafo.style
    except Exception:  # noqa: BLE001 -- un estilo roto non pode tumbar a copia
        return []
    cadea = []
    while estilo is not None and len(cadea) < 20:
        cadea.append(estilo)
        estilo = estilo.base_style
    return cadea


def _nivel_titulo_docx(paragrafo) -> int | None:
    nivel = _nivel_esquema_docx(paragrafo._p.pPr)
    if nivel:
        return nivel
    for estilo in _cadea_de_estilos(paragrafo):
        nome = (estilo.name or "").strip()
        if nome.lower() in ("title", "título", "titulo"):
            return 1
        coincidencia = _ESTILO_TITULO_DOCX.fullmatch(nome)
        if coincidencia:
            return int(coincidencia.group(2))
        nivel = _nivel_esquema_docx(estilo.element.pPr)
        if nivel:
            return nivel
    return None


class _NumeracionDocx:
    """Numeración das listas de Word (`numbering.xml`): o prefixo de cada
    elemento ("1.", "a)", "1.2.", "-") contando coma Word, por lista e nivel."""

    def __init__(self, documento):
        self.niveis = {}  # numId -> {ilvl: (numFmt, lvlText, start)}
        self.contadores = {}  # numId -> [contador por nivel]
        numeracion = None
        # Sen `documento.part.numbering_part`: se o documento non ten
        # numeración, python-docx CREARÍA unha parte baleira no documento.
        for rel in documento.part.rels.values():
            if rel.reltype == RT.NUMBERING:
                numeracion = rel.target_part.element
        if numeracion is None:
            return
        abstractos = {}
        for abstracto in numeracion.findall(qn("w:abstractNum")):
            niveis = {}
            for nivel in abstracto.findall(qn("w:lvl")):
                formato = nivel.find(qn("w:numFmt"))
                texto = nivel.find(qn("w:lvlText"))
                inicio = nivel.find(qn("w:start"))
                niveis[int(nivel.get(qn("w:ilvl"), "0"))] = (
                    formato.get(qn("w:val")) if formato is not None else "decimal",
                    texto.get(qn("w:val")) if texto is not None else "",
                    int(inicio.get(qn("w:val"))) if inicio is not None else 1,
                )
            abstractos[abstracto.get(qn("w:abstractNumId"))] = niveis
        for num in numeracion.findall(qn("w:num")):
            ligazon = num.find(qn("w:abstractNumId"))
            if ligazon is not None:
                self.niveis[num.get(qn("w:numId"))] = abstractos.get(ligazon.get(qn("w:val")), {})

    @staticmethod
    def _numpr(paragrafo):
        pPr = paragrafo._p.pPr
        if pPr is not None and pPr.numPr is not None:
            return pPr.numPr
        for estilo in _cadea_de_estilos(paragrafo):
            pPr = estilo.element.pPr
            if pPr is not None and pPr.numPr is not None:
                return pPr.numPr
        return None

    def prefixo(self, paragrafo) -> tuple | None:
        """(nivel, prefixo) ou `None` se o parágrafo non é dunha lista."""
        numpr = self._numpr(paragrafo)
        if numpr is None or numpr.numId is None:
            return None
        num_id = str(numpr.numId.val)
        nivel = numpr.ilvl.val if numpr.ilvl is not None else 0
        if num_id == "0" or num_id not in self.niveis:
            return None
        niveis = self.niveis[num_id]
        formato, texto, inicio = niveis.get(nivel, ("decimal", f"%{nivel + 1}.", 1))
        if formato == "bullet":
            return nivel, "-"
        if formato == "none":
            return nivel, ""
        contadores = self.contadores.setdefault(num_id, [None] * 9)
        contadores[nivel] = inicio if contadores[nivel] is None else contadores[nivel] + 1
        for i in range(nivel + 1, 9):
            contadores[i] = None

        def substituir(coincidencia):
            k = int(coincidencia.group(1)) - 1
            formato_k, _, inicio_k = niveis.get(k, ("decimal", "", 1))
            return _numero(contadores[k] if contadores[k] is not None else inicio_k, formato_k)

        return nivel, re.sub(r"%([1-9])", substituir, texto)


def _bloque_paragrafo(texto: str, nivel_titulo: int | None, lista: tuple | None) -> tuple:
    liñas = [l.strip() for l in texto.split("\n") if l.strip()]
    if not liñas:
        return lista is not None, ""
    if nivel_titulo:
        return False, "#" * min(nivel_titulo, 6) + " " + " ".join(liñas)
    if lista and lista[1]:
        sangria = "  " * lista[0]
        return True, "\n".join(
            [sangria + lista[1] + " " + liñas[0]] + [sangria + "  " + l for l in liñas[1:]]
        )
    return False, "\n".join(_escapar_liña(l) for l in liñas)


def _celas_docx(contedor, texto_de: dict) -> str:
    textos = [texto_de.get(p._p) for p in _paragrafos_dun_contedor_docx(contedor)]
    return "<br>".join(_escapar_cela(t) for t in textos if t and t.strip())


def _taboa_docx(taboa, texto_de: dict) -> tuple:
    filas, vistas = [], set()
    for fila in taboa.rows:
        celas = []
        for cela in fila.cells:
            # Unha cela combinada aparece repetida en `fila.cells`: texto só na primeira.
            if cela._tc in vistas:
                celas.append("")
                continue
            vistas.add(cela._tc)
            celas.append(_celas_docx(cela, texto_de))
        filas.append(celas)
    md = _taboa_md(filas)
    if md is not None:
        return False, md
    # Unha soa columna (un recadro arredor dun texto): parágrafos normais.
    return False, "\n\n".join(c.replace("<br>", "\n\n") for f in filas for c in f if c)


def _docx(contexto: dict, textos: list) -> str:
    documento = contexto["documento"]
    texto_de = {p._p: t for p, t in zip(contexto["paragrafos"], textos)}
    numeracion = _NumeracionDocx(documento)
    bloques = []
    for fillo in documento.element.body.iterchildren():
        if fillo.tag == qn("w:p") and fillo in texto_de:
            paragrafo = Paragraph(fillo, documento)
            bloques.append(_bloque_paragrafo(
                texto_de[fillo], _nivel_titulo_docx(paragrafo), numeracion.prefixo(paragrafo)
            ))
        elif fillo.tag == qn("w:tbl"):
            bloques.append(_taboa_docx(Table(fillo, documento), texto_de))
    cabeceiras = [
        texto_de[p._p]
        for contedor in _cabeceiras_e_pes_docx(documento)
        for p in _paragrafos_dun_contedor_docx(contedor)
        if p._p in texto_de
    ]
    return _engadir_cabeceiras(_unir_bloques(bloques), cabeceiras)


# -- .odt -------------------------------------------------------------------

def _e(no, ns: str, nome: str) -> bool:
    return isinstance(no, ElementoOdt) and no.qname == (ns, nome)


def _antepasados(no) -> list:
    resultado = []
    no = no.parentNode
    while no is not None:
        resultado.append(no)
        no = no.parentNode
    return resultado


def _estilos_de_lista_odt(documento) -> dict:
    """nome do estilo de lista -> {nivel: (formato, prefixo, sufixo, inicio)}
    (`formato` None = viñeta)."""
    estilos = {}
    for raiz in (documento.styles, documento.automaticstyles):
        for estilo in raiz.childNodes:
            if not _e(estilo, TEXTNS, "list-style"):
                continue
            niveis = {}
            for nivel in estilo.childNodes:
                if _e(nivel, TEXTNS, "list-level-style-number"):
                    niveis[int(nivel.getAttrNS(TEXTNS, "level") or 1)] = (
                        nivel.getAttrNS(STYLENS, "num-format") or "1",
                        nivel.getAttrNS(STYLENS, "num-prefix") or "",
                        nivel.getAttrNS(STYLENS, "num-suffix") or "",
                        int(nivel.getAttrNS(TEXTNS, "start-value") or 1),
                    )
                elif _e(nivel, TEXTNS, "list-level-style-bullet"):
                    niveis[int(nivel.getAttrNS(TEXTNS, "level") or 1)] = (None, "", "", 1)
            estilos[estilo.getAttrNS(STYLENS, "name")] = niveis
    return estilos


def _celas_odt(cela, texto_de: dict, usados: set) -> str:
    textos = []

    def percorrer(no):
        for fillo in no.childNodes:
            if id(fillo) in texto_de:
                usados.add(id(fillo))
                textos.append(texto_de[id(fillo)])
            elif isinstance(fillo, ElementoOdt):
                percorrer(fillo)

    percorrer(cela)
    return "<br>".join(_escapar_cela(t) for t in textos if t and t.strip())


def _taboa_odt(taboa, texto_de: dict, usados: set) -> str:
    filas_xml = []

    def recoller_filas(no):
        for fillo in no.childNodes:
            if _e(fillo, TABLENS, "table-row"):
                filas_xml.append(fillo)
            elif isinstance(fillo, ElementoOdt) and fillo.qname[0] == TABLENS and fillo.qname[1] in (
                "table-header-rows", "table-rows", "table-row-group",
            ):
                recoller_filas(fillo)

    recoller_filas(taboa)
    filas = []
    for fila_xml in filas_xml:
        celas = []
        for cela in fila_xml.childNodes:
            if not (_e(cela, TABLENS, "table-cell") or _e(cela, TABLENS, "covered-table-cell")):
                continue
            texto = _celas_odt(cela, texto_de, usados) if _e(cela, TABLENS, "table-cell") else ""
            repeticions = int(cela.getAttrNS(TABLENS, "number-columns-repeated") or 1)
            celas.extend([texto] * (min(repeticions, 50) if texto else min(repeticions, 1)))
        filas.append(celas)
    md = _taboa_md(filas)
    if md is not None:
        return md
    return "\n\n".join(c.replace("<br>", "\n\n") for f in filas for c in f if c)


def _odt(contexto: dict, textos: list) -> str:
    documento = contexto["documento"]
    texto_de = {id(p): t for p, t in zip(contexto["paragrafos"], textos)}
    estilos_lista = _estilos_de_lista_odt(documento)
    contadores = {}  # id(text:list) -> número do último elemento
    elementos_vistos = set()  # id(text:list-item) xa co seu prefixo
    usados = set()
    bloques, cabeceiras = [], []
    for paragrafo, texto in zip(contexto["paragrafos"], textos):
        if id(paragrafo) in usados:
            continue
        antepasados = _antepasados(paragrafo)
        if any(_e(a, STYLENS, "master-page") for a in antepasados):
            cabeceiras.append(texto)
            continue
        taboas = [a for a in antepasados if _e(a, TABLENS, "table")]
        if taboas:
            bloques.append((False, _taboa_odt(taboas[-1], texto_de, usados)))
            continue
        nivel_titulo = None
        if _e(paragrafo, TEXTNS, "h"):
            nivel_titulo = int(paragrafo.getAttrNS(TEXTNS, "outline-level") or 1)
        listas = [a for a in antepasados if _e(a, TEXTNS, "list")]
        lista = None
        if listas and nivel_titulo is None:
            elemento = next(a for a in antepasados if _e(a, TEXTNS, "list-item") or _e(a, TEXTNS, "list-header"))
            profundidade = len(listas)
            if id(elemento) in elementos_vistos or _e(elemento, TEXTNS, "list-header"):
                lista = (profundidade - 1, " ")  # segundo parágrafo do mesmo elemento
            else:
                elementos_vistos.add(id(elemento))
                nome_estilo = next((l.getAttrNS(TEXTNS, "style-name") for l in listas
                                    if l.getAttrNS(TEXTNS, "style-name")), None)
                formato, prefixo, sufixo, inicio = estilos_lista.get(nome_estilo, {}).get(
                    profundidade, (None, "", "", 1))
                if formato is None:
                    lista = (profundidade - 1, "-")
                else:
                    n = contadores.get(id(listas[0]), inicio - 1) + 1
                    contadores[id(listas[0])] = n
                    lista = (profundidade - 1, f"{prefixo}{_numero(n, formato)}{sufixo}".strip() or "-")
        bloques.append(_bloque_paragrafo(texto, nivel_titulo, lista))
    return _engadir_cabeceiras(_unir_bloques(bloques), cabeceiras)


# -- PDF e imaxes -------------------------------------------------------------

class _Desprazamentos:
    """Posición no texto ANONIMIZADO dunha posición do texto orixinal da
    páxina. Unha posición que cae DENTRO dunha substitución leva ao
    principio ou ao final do texto que a substitúe, nunca ao orixinal."""

    def __init__(self, substitucions: list):
        self.subs = sorted(substitucions)
        self.fins = [f for _, f, _ in self.subs]
        self.inicios_anon = []
        desprazamento = 0
        for inicio, fin, novo in self.subs:
            self.inicios_anon.append(inicio + desprazamento)
            desprazamento += len(novo) - (fin - inicio)
        self.acumulado = []
        total = 0
        for inicio, fin, novo in self.subs:
            total += len(novo) - (fin - inicio)
            self.acumulado.append(total)

    def anon(self, pos: int, final: bool) -> int:
        k = bisect.bisect_right(self.fins, pos)  # substitucións rematadas antes de pos
        if k < len(self.subs) and self.subs[k][0] < pos:  # pos cae dentro da k-ésima
            inicio_anon = self.inicios_anon[k]
            return inicio_anon + len(self.subs[k][2]) if final else inicio_anon
        return pos + (self.acumulado[k - 1] if k else 0)


def _paxina_pdf(pagina, info, anon: str, locais: list | None) -> str:
    if pagina is None or locais is None or pagina.rotation:
        return _limpar_bloque(anon)
    try:
        taboas = pagina.find_tables().tables
    except Exception:  # noqa: BLE001 -- unha táboa rara non pode tumbar a copia
        return _limpar_bloque(anon)
    if not taboas:
        return _limpar_bloque(anon)

    desprazamentos = _Desprazamentos(locais)
    consumido = bytearray(len(anon))
    insercions = []
    for taboa in sorted(taboas, key=lambda t: (t.bbox[1], t.bbox[0])):
        filas, intervalos = [], []
        for fila in taboa.rows:
            celas = []
            for caixa in fila.cells:
                if caixa is None:
                    celas.append("")
                    continue
                anacos = []
                for a, b in taboas_pdf._pezas_da_cela(info.palabras, fitz.Rect(caixa)):
                    ia, ib = desprazamentos.anon(a, final=False), desprazamentos.anon(b, final=True)
                    anacos.append(anon[ia:ib])
                    intervalos.append((ia, ib))
                celas.append(_escapar_cela(" ".join(anacos)))
            filas.append(celas)
        md = _taboa_md(filas)
        if md is None or not intervalos:
            continue
        for ia, ib in intervalos:
            consumido[ia:ib] = b"\x01" * (ib - ia)
        insercions.append((min(ia for ia, _ in intervalos), md))

    insercions.sort()
    partes, anaco, k = [], [], 0
    for pos in range(len(anon) + 1):
        while k < len(insercions) and insercions[k][0] <= pos:
            partes.append(_limpar_bloque("".join(anaco)))
            anaco = []
            partes.append(insercions[k][1])
            k += 1
        if pos < len(anon) and not consumido[pos]:
            anaco.append(anon[pos])
    partes.append(_limpar_bloque("".join(anaco)))
    return "\n\n".join(p for p in partes if p)


def _pdf(contexto: dict, texto_final: str, substitucions: list | None, marcar_paxinas: bool) -> str:
    paxinas = contexto["paxinas"]
    partes = texto_final.split(SEPARADOR_PAXINAS)
    if len(partes) != len(paxinas):
        return _texto_plano(texto_final)
    documento = contexto.get("documento")
    limites = _limites_paxinas(paxinas)
    saida = []
    for i, (info, anon) in enumerate(zip(paxinas, partes)):
        locais = None
        if substitucions is not None:
            inicio, fin = limites[i]
            # Mesmo criterio ca `gardar_pdf_estruturado`: as substitucións
            # desta páxina só valen se reproducen exactamente o seu texto.
            locais = [(s - inicio, f - inicio, n) for s, f, n in substitucions if inicio <= s and f <= fin]
            if _aplicar_substitucions_a_texto(info.texto, locais) != anon:
                locais = None
        corpo = _paxina_pdf(documento[i] if documento is not None else None, info, anon, locais)
        if marcar_paxinas:
            saida.append(f"<!-- {idioma.t('copia_md.paxina', n=i + 1)} -->" + ("\n\n" + corpo if corpo else ""))
        elif corpo:
            saida.append(corpo)
    return "\n\n".join(saida) + "\n"
