"""Lectura de documentos (.docx, .odt, .pdf, imaxes e texto) e utilidades
de texto que comparten a escritura (`pipeline`) e a copia Markdown
(`copia_md`). Sen dependencias do NER (spaCy): ler un documento ou xerar o
seu Markdown non necesita cargar o modelo nin ter spaCy instalado.
Movido sen cambios dende `pipeline.py`, que reexporta os nomes antigos.
"""

from __future__ import annotations

from pathlib import Path

import docx
from docx.oxml.ns import qn
from odf import teletype
from odf.element import Element as ElementoOdt
from odf.element import Text as TextoOdt
from odf.office import Annotation as AnotacionOdt
from odf.opendocument import load as cargar_odt
from odf.text import H as TituloOdt
from odf.text import LineBreak as SaltoLiñaOdt
from odf.text import P as ParagrafoOdt
from odf.text import S as EspazosOdt
from odf.text import Tab as TabuladorOdt

from . import imaxes
from .pdf_estrutura import cargar_pdf_estruturado

# Qnames ODF reutilizados en varios sitios (percorrido de parágrafos e
# títulos, exclusión de anotacións do texto dun parágrafo...).
_QNAME_PARAGRAFO_ODT = ParagrafoOdt().qname
_QNAME_TITULO_ODT = TituloOdt(outlinelevel=1).qname
_QNAME_ANOTACION_ODT = AnotacionOdt().qname
_QNAME_SALTO_ODT = SaltoLiñaOdt().qname
_QNAME_TABULADOR_ODT = TabuladorOdt().qname
_QNAME_ESPAZOS_ODT = EspazosOdt().qname
_QNAMES_ESPAZADO_ODT = (_QNAME_SALTO_ODT, _QNAME_TABULADOR_ODT, _QNAME_ESPAZOS_ODT)


def _paragrafos_dun_contedor_docx(contedor) -> list:
    """`contedor` pode ser o documento completo, unha cabeceira/pé de
    páxina ou unha celda de táboa -- en python-docx todos comparten a
    mesma interface (`.paragraphs`/`.tables`), así que a mesma función
    serve para calquera deles, incluídas táboas ANIÑADAS dentro doutras
    táboas (unha celda tamén ten `.tables` propias)."""
    paragrafos = list(contedor.paragraphs)
    for tabla in contedor.tables:
        paragrafos.extend(_paragrafos_de_taboa_docx(tabla))
    return paragrafos


def _paragrafos_de_taboa_docx(tabla) -> list:
    """As celdas combinadas (horizontal ou verticalmente) aparecen
    REPETIDAS en `fila.cells` -- é o MESMO obxecto/elemento XML varias
    veces -- así que se deduplica por identidade do elemento `w:tc` para
    non duplicar parágrafos nin desaliñar o texto conxunto."""
    paragrafos = []
    celdas_vistas = set()
    for fila in tabla.rows:
        for celda in fila.cells:
            id_celda = id(celda._tc)
            if id_celda in celdas_vistas:
                continue
            celdas_vistas.add(id_celda)
            paragrafos.extend(_paragrafos_dun_contedor_docx(celda))
    return paragrafos


def _cabeceiras_e_pes_docx(documento) -> list:
    """Cabeceiras e pés de páxina de TODAS as seccións: por defecto,
    primeira páxina e páxinas pares/impares. Acceder a `.paragraphs` ou
    `.tables` dunha cabeceira/pé que NON ten definición propia (está
    "ligada á anterior", `is_linked_to_previous`) créaa baleira coma
    efecto colateral de python-docx -- por iso se comproba antes e só se
    devolven as que xa teñen contido propio."""
    contedores = []
    for seccion in documento.sections:
        for hf in (
            seccion.header, seccion.footer,
            seccion.first_page_header, seccion.first_page_footer,
            seccion.even_page_header, seccion.even_page_footer,
        ):
            if not hf.is_linked_to_previous:
                contedores.append(hf)
    return contedores


def _paragrafos_docx(documento) -> list:
    """`documento.paragraphs`/`documento.tables` só devolven o CORPO do
    documento -- as cabeceiras e pés de páxina (de calquera sección,
    incluídas primeira páxina e páxinas pares) viven en partes .docx
    separadas e quedarían fóra, conservando os datos persoais orixinais
    aínda que o corpo quedase ben anonimizado."""
    paragrafos = _paragrafos_dun_contedor_docx(documento)
    for contedor in _cabeceiras_e_pes_docx(documento):
        paragrafos.extend(_paragrafos_dun_contedor_docx(contedor))
    return paragrafos


def _aceptar_control_de_cambios_docx(elemento_raiz) -> None:
    """Normaliza o control de cambios (revisión de Word) dun XML .docx
    ANTES de extraer texto del -- política: ACEPTAR as insercións (`w:ins`,
    o seu contido aínda NON pasara por `paragraph.text`/`paragraph.runs`,
    así que quedaba fóra da detección enteiramente) e ELIMINAR as
    delecións (`w:del`/`w:delText`, cuxo texto queda no XML aínda que xa
    non se vexa en Word ao aceptar cambios). Tras esta normalización xa
    non quedan `w:ins`/`w:del` -- `_paragrafos_docx`/`_anacos_docx` len en
    o resto coma texto normal.

    `w:moveTo`/`w:moveFrom` (un "mover texto" rastrexado) son o MESMO caso
    ca `w:ins`/`w:del` -- `w:moveTo` (destino, cos `w:r`/`w:t` normais do
    texto movido) queda tan invisible para `paragraph.text` coma un
    `w:ins`, e `w:moveFrom` (orixe, con `w:delText`) coma un `w:del` --
    así que se tratan igual: desenvolver `w:moveTo`, eliminar
    `w:moveFrom`. Antes non se tocaban: un nome movido con "Aceptar todos
    os cambios" en Word escapaba enteiro, sen detectar nin no destino
    (invisible) nin na orixe (xa aceptada, non debería quedar). Non se
    tocan os marcadores `w:moveFromRangeStart/End` (sen texto propio) nin
    marcas de cambio de formato coma `w:rPrChange`."""
    for elemento in list(elemento_raiz.iter(qn("w:ins"))) + list(elemento_raiz.iter(qn("w:moveTo"))):
        pai = elemento.getparent()
        if pai is None:
            continue
        for fillo in list(elemento):
            elemento.addprevious(fillo)
        pai.remove(elemento)

    for elemento in list(elemento_raiz.iter(qn("w:del"))) + list(elemento_raiz.iter(qn("w:moveFrom"))):
        pai = elemento.getparent()
        if pai is not None:
            pai.remove(elemento)


def _limpar_autores_de_cambios_docx(elemento_raiz) -> None:
    """O nome de quen fixo un cambio rastrexado vai no atributo `w:author`
    -- ademais de `w:ins`/`w:del` (xa tratados en
    `_aceptar_control_de_cambios_docx`), tamén pode aparecer en marcas de
    cambio de formato (`w:rPrChange`, `w:pPrChange`...) que NON se
    eliminan (só cambian formato, non texto). Báleirase ese atributo en
    calquera elemento que o teña."""
    atributo_author = qn("w:author")
    for elemento in elemento_raiz.iter():
        if atributo_author in elemento.attrib:
            elemento.set(atributo_author, "")


def _partes_docx_con_texto(documento) -> list:
    """As partes .docx que poden conter texto de persoas: o documento
    principal e as cabeceiras/pés de páxina con definición propia (as
    mesmas que percorre `_cabeceiras_e_pes_docx`)."""
    partes = [documento.part]
    partes.extend(hf.part for hf in _cabeceiras_e_pes_docx(documento))
    return partes


def _paragrafos_odt(documento) -> list:
    """`documento.getElementsByType(P)` só atopa parágrafos (`text:p`) --
    deixa fóra os TÍTULOS (`text:h`, A9), que en ODF son un elemento
    DISTINTO aínda que conteñan texto normal coma calquera parágrafo.
    Percorre a árbore enteira en orde de documento (`documento.topnode`
    xa inclúe tanto o corpo coma as páxinas mestras -- así se atopan
    tamén as cabeceiras/pés de páxina, definidos en `styles.xml`) e
    recolle parágrafos E títulos xuntos, na orde en que aparecen.

    As anotacións (`office:annotation`, comentarios de revisión) NON se
    percorren aquí -- o seu contido trátase á parte en
    `_limpar_anotacions_odt` (ver esa función para o porqué): se se
    incluísen tamén coma parágrafos normais, o seu texto contaríase
    DÚAS veces (dentro do parágrafo que as contén E coma entrada propia),
    desaliñando as coordenadas -- ver tamén `_fillos_de_texto_odt`, que
    exclúe as anotacións do texto do parágrafo que as contén polo mesmo
    motivo."""
    tags = (_QNAME_PARAGRAFO_ODT, _QNAME_TITULO_ODT)
    resultado = []

    def percorrer(no):
        for fillo in no.childNodes:
            if not isinstance(fillo, ElementoOdt):
                continue
            if fillo.qname == _QNAME_ANOTACION_ODT:
                continue
            if fillo.qname in tags:
                resultado.append(fillo)
            percorrer(fillo)

    percorrer(documento.topnode)
    return resultado


def _fillos_de_texto_odt(paragrafo) -> list:
    """Fillos DIRECTOS dun parágrafo/título que aportan texto propio --
    exclúe as anotacións (`office:annotation`), que son unha marca
    estrutural (autor + parágrafo propio de comentario) e non texto do
    parágrafo que as contén (ver A9). Reutilízase tanto para LER o texto
    orixinal (`_texto_paragrafo_odt`) coma para escribir por tramos
    (`_aplicar_substitucions_paragrafo_odt`) -- así as anotacións quedan
    SEMPRE fóra da detección e da reescritura, e só se tocan á parte en
    `_limpar_anotacions_odt`."""
    return [
        fillo for fillo in paragrafo.childNodes
        if not (isinstance(fillo, ElementoOdt) and fillo.qname == _QNAME_ANOTACION_ODT)
    ]


def _texto_fillo_odt(fillo) -> str:
    """Texto que aporta un fillo directo dun parágrafo/título.
    `teletype.extractText` só converte os saltos de liña manuais
    (`text:line-break`), os tabuladores (`text:tab`) e os espazos
    repetidos (`text:s`) cando van DENTRO do elemento que se lle pasa (un
    span): pasándolle o propio salto devolve "". Por iso un salto fillo
    directo do parágrafo desaparecía e as palabras de cada lado chegaban
    pegadas á detección -- "representación de" + salto + "Antía Varela
    Doval" líase "deAntía Varela Doval" e "Antía" quedaba á vista."""
    if isinstance(fillo, TextoOdt):
        return fillo.data
    if fillo.qname == _QNAME_SALTO_ODT:
        return "\n"
    if fillo.qname == _QNAME_TABULADOR_ODT:
        return "\t"
    if fillo.qname == _QNAME_ESPAZOS_ODT:
        return " " * int(fillo.getAttribute("c") or 1)
    return teletype.extractText(fillo)


def _texto_paragrafo_odt(paragrafo) -> str:
    """Texto dun parágrafo/título coma `teletype.extractText`, pero sen
    contar o contido das anotacións (ver `_fillos_de_texto_odt`)."""
    return "".join(_texto_fillo_odt(fillo) for fillo in _fillos_de_texto_odt(paragrafo))


def cargar_documento_estruturado(ruta: str):
    """Para `.docx`/`.odt` devolve (texto_plano, contexto), onde `contexto`
    garda o necesario para escribir de volta conservando o formato
    orixinal (`gardar_documento_estruturado`), incluíndo o texto orixinal
    de cada parágrafo (para poder distribuír as substitucións por "anaco"
    -- run ou span -- respectando a mestura de formatos dentro del). Para
    calquera outro formato, devolve (texto_plano, None)."""
    ruta_p = Path(ruta)
    sufixo = ruta_p.suffix.lower()

    if sufixo == ".docx":
        documento = docx.Document(str(ruta_p))
        # Normalizar o control de cambios ANTES de ler o texto -- se non,
        # o texto insertado quedaría fóra da detección (A8) e as marcas
        # de autor/delección quedarían no XML de saída sen tocar.
        for parte in _partes_docx_con_texto(documento):
            _aceptar_control_de_cambios_docx(parte.element)
            _limpar_autores_de_cambios_docx(parte.element)
        paragrafos = _paragrafos_docx(documento)
        textos_orixinais = [p.text for p in paragrafos]
        texto = "\n".join(textos_orixinais)
        return texto, {
            "tipo": "docx", "documento": documento,
            "paragrafos": paragrafos, "textos_orixinais": textos_orixinais,
        }

    if sufixo == ".odt":
        documento = cargar_odt(str(ruta_p))
        paragrafos = _paragrafos_odt(documento)
        textos_orixinais = [_texto_paragrafo_odt(p) for p in paragrafos]
        texto = "\n".join(textos_orixinais)
        return texto, {
            "tipo": "odt", "documento": documento,
            "paragrafos": paragrafos, "textos_orixinais": textos_orixinais,
        }

    if sufixo == ".pdf":
        return cargar_pdf_estruturado(str(ruta_p))

    if sufixo in imaxes.FORMATOS:
        return imaxes.cargar(str(ruta_p))

    return ruta_p.read_text(encoding="utf-8"), None


def cargar_texto(ruta: str) -> str:
    return cargar_documento_estruturado(ruta)[0]


# -- utilidades de texto compartidas coa escritura e coa copia .md ---------

def _aplicar_substitucions_a_texto(texto: str, substitucions: list) -> str:
    resultado = texto
    for inicio, fin, novo in sorted(substitucions, key=lambda s: s[0], reverse=True):
        resultado = resultado[:inicio] + novo + resultado[fin:]
    return resultado


def _agrupar_liñas_por_paragrafo(partes: list, textos_orixinais: list) -> list:
    """Un parágrafo pode ocupar MÁIS DUNHA "liña" (separada por "\n") do
    texto plano se o seu propio texto orixinal xa contiña un salto de
    liña MANUAL (Shift+Enter en Word/LibreOffice, moi habitual nun só
    parágrafo dun enderezo ou bloque de sinatura -- "Rúa Maior 5\\nVigo,
    36001" É UN SÓ parágrafo con dúas liñas). Bug real atopado nunha carta:
    tratar "1 liña = 1 parágrafo" facía que ese documento sempre fallase
    coa conta de parágrafos desaliñada e caese no respaldo de texto plano,
    perdendo o .docx/.odt orixinal, aínda SEN editar nada a man. Agrupa
    `partes` (xa separadas por "\\n") en tantos anacos coma parágrafos,
    respectando cantas liñas ocupaba cada un orixinalmente, e reconstrúe
    cada un unindo as súas liñas de novo -- así un salto interno tamén se
    conserva se non se edita, e detéctase igual coma antes se se edita
    (borrando ou engadindo unha liña dentro dese mesmo parágrafo)."""
    n_liñas = [t.count("\n") + 1 for t in textos_orixinais]
    resultado = []
    cursor = 0
    for n in n_liñas:
        resultado.append("\n".join(partes[cursor:cursor + n]))
        cursor += n
    return resultado
