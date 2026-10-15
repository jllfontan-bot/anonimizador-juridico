"""Orquestra o fluxo completo descrito no informe (seccion 05):
inxesta -> deteccion -> resolucion de identidade -> rexistro -> substitucion
-> analise de efecto mosaico -> informe para revision humana.
"""

from __future__ import annotations

import re
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

import docx
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml.ns import qn
from lxml import etree
from odf import teletype
from odf.dc import Creator as AutorAnotacionOdt
from odf.dc import Description as DescricionMetaOdt
from odf.dc import Subject as AsuntoMetaOdt
from odf.dc import Title as TituloMetaOdt
from odf.element import Element as ElementoOdt
from odf.element import Text as TextoOdt
from odf.meta import InitialCreator as CreadorInicialMetaOdt
from odf.meta import Keyword as PalabraClaveMetaOdt
from odf.meta import PrintedBy as ImprimidoPorMetaOdt
from odf.meta import UserDefined as PersonalizadoMetaOdt
from odf.office import Annotation as AnotacionOdt
from odf.opendocument import load as cargar_odt
from odf.text import H as TituloOdt
from odf.text import P as ParagrafoOdt

from . import codigos, idioma, imaxes, mosaic, ner, resolution
from .categoria_especial import escanear_categoria_especial
from .risco_residual import escanear_risco_residual
from .pdf_estrutura import _limites_paxinas, cargar_pdf_estruturado, gardar_pdf_estruturado
from .recognizers import Entidade
from .registry import RexistroCorrespondencias

_CONFIG_POR_DEFECTO = str(Path(__file__).resolve().parents[2] / "config" / "entidades.yaml")

_ETIQUETA_REDACCION = {
    "TELEFONO": "TELEFONO",
    "EMAIL": "EMAIL",
    "MATRICULA": "MATRICULA",
    "EXPEDIENTE": "EXPEDIENTE",
    "ENDEREZO": "ENDEREZO",
    "COLEXIADO": "COLEXIADO",
    "PASAPORTE": "PASAPORTE",
    "DOCUMENTO_IDENTIDADE": "DOCUMENTO_IDENTIDADE",  # columna "DNI/NIE/PAS", "NRP"... dunha táboa PDF
    "CSV": "CSV",
    "REFERENCIA": "REFERENCIA",
    "IBAN": "IBAN",
    "TARXETA": "TARXETA",
    "REF_CATASTRAL": "REF_CATASTRAL",
    "SEGURIDADE_SOCIAL": "SEGURIDADE_SOCIAL",
}

FORMATOS_CON_ESTRUTURA = (".docx", ".odt", ".pdf", *imaxes.FORMATOS)


def conserva_formato(contexto: dict | None, ruta_saida: str) -> bool:
    """Se `ruta_saida` pide o mesmo formato có documento cargado (entón
    gárdase con `gardar_documento_estruturado`, non coma texto plano)."""
    if not contexto:
        return False
    if contexto.get("imaxe"):
        return imaxes.conserva_formato(contexto, ruta_saida)
    return Path(ruta_saida).suffix.lower() == "." + contexto["tipo"]

# Qnames ODF reutilizados en varios sitios (percorrido de parágrafos e
# títulos, exclusión de anotacións do texto dun parágrafo...).
_QNAME_PARAGRAFO_ODT = ParagrafoOdt().qname
_QNAME_TITULO_ODT = TituloOdt(outlinelevel=1).qname
_QNAME_ANOTACION_ODT = AnotacionOdt().qname


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


def _anacos_docx(paragrafo) -> list:
    """Devolve TODOS os "anacos" (elementos `w:r`) que aportan texto a
    `paragrafo.text`, en orde de documento -- incluídos os que van dentro
    dun `w:hyperlink`. `paragraph.text` (python-docx) xa inclúe o texto
    dos hyperlinks, pero `paragraph.runs` NON inclúe eses `w:r` (só os que
    penden DIRECTAMENTE do parágrafo) -- iso descolocaba as substitucións
    cando había un hyperlink no medio dun parágrafo. Os elementos `w:r`
    teñen `.text` (get/set) igual cós obxectos `Run`, así que serven
    directamente coma "anaco" para `_distribuir_por_anacos`."""
    anacos = []
    for elemento in paragrafo._p.xpath("w:r | w:hyperlink"):
        if elemento.tag == qn("w:r"):
            anacos.append(elemento)
        else:  # w:hyperlink
            anacos.extend(elemento.xpath("w:r"))
    return anacos


def _anacos_coinciden_co_texto_docx(paragrafo, texto_orixinal: str) -> bool:
    """Ver A7: antes de confiar nas coordenadas por tramos, comproba que
    os "anacos" (`_anacos_docx`) reconstrúen EXACTAMENTE o texto orixinal
    do parágrafo tal como se leu (`paragraph.text`). Se non coincide --
    unha estrutura non anticipada coma un campo (`w:fldSimple`) ou
    similar -- é máis seguro caer á reserva ca arriscar unha
    substitución descolocada."""
    return "".join(anaco.text for anaco in _anacos_docx(paragrafo)) == texto_orixinal


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


def _limpar_hyperlinks_mailto_docx(documento) -> None:
    """O TEXTO visible dun `w:hyperlink` xa se detecta e substitúe coma
    calquera outro (ver `_anacos_docx`, A7), pero o seu DESTINO real vive
    á parte, en `word/_rels/document.xml.rels` (ou no `.rels` da
    cabeceira/pé correspondente) coma atributo `Target` da relación --
    "Contacto" pode quedar ben anonimizado no texto mentres o propio
    hyperlink segue apuntando a
    `mailto:xmcastro@example.com?subject=DNI%2012345678Z`. python-docx non
    ten API pública para editar unha relación xa creada (`_Relationship`
    só garda `_target` coma atributo interno) -- baléirase directamente,
    mesmo principio ca `part._blob` en `_limpar_metadatos_docx`. Só se
    tocan as relacións `mailto:`: as demais (ligazóns a outros
    documentos, anchors internos...) non levan un dato persoal directo no
    propio destino."""
    for parte in _partes_docx_con_texto(documento):
        for relacion in parte.rels.values():
            if (
                relacion.is_external
                and relacion.reltype == RT.HYPERLINK
                and relacion.target_ref.lower().startswith("mailto:")
            ):
                relacion._target = "mailto:"


def _limpar_comentarios_docx(documento) -> None:
    """Os comentarios de revisión (`word/comments.xml`) NON pasan pola
    detección de datos persoais igual có corpo do documento -- adoitan ser
    notas internas que poden mencionar directamente ás partes ("o DNI que
    di Xoana que..."). Decisión (documentada tamén no informe final):
    baléiranse por completo -- autor, iniciais e texto -- en vez de
    tentar analizalos, conservando só a marca de referencia no corpo (así
    non hai que tocar máis a estrutura do documento). Non se crea unha
    parte de comentarios nova se o documento non tiña ningunha."""
    try:
        documento.part.part_related_by(RT.COMMENTS)
    except KeyError:
        return
    for comentario in documento.comments:
        comentario.author = ""
        comentario.initials = None
        for paragrafo in comentario.paragraphs:
            _substituir_texto_paragrafo_docx(paragrafo, "")


def _limpar_metadatos_docx(documento) -> None:
    """`docProps/core.xml` (autor, quen editou por última vez, título...)
    ten API propia en python-docx (`core_properties`). `docProps/app.xml`
    (Compañía, Xestor/Manager) NON a ten -- edítase o XML cru do part
    directamente, mesmo principio ca coas imaxes en
    `_redactar_imaxes_docx` (`part._blob` non ten setter público pero é o
    atributo real que le `.blob`)."""
    propiedades = documento.core_properties
    propiedades.author = ""
    propiedades.last_modified_by = ""
    propiedades.title = ""
    propiedades.subject = ""
    propiedades.keywords = ""
    propiedades.comments = ""
    propiedades.category = ""

    for part in documento.part.package.iter_parts():
        if part.partname != "/docProps/app.xml":
            continue
        arbore = etree.fromstring(part.blob)
        for elemento in arbore.iter():
            if etree.QName(elemento).localname in ("Company", "Manager"):
                elemento.text = ""
        part._blob = etree.tostring(
            arbore, xml_declaration=True, encoding="UTF-8", standalone=True
        )


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


def _texto_paragrafo_odt(paragrafo) -> str:
    """Texto dun parágrafo/título coma `teletype.extractText`, pero sen
    contar o contido das anotacións (ver `_fillos_de_texto_odt`)."""
    return "".join(
        fillo.data if isinstance(fillo, TextoOdt) else teletype.extractText(fillo)
        for fillo in _fillos_de_texto_odt(paragrafo)
    )


def _limpar_anotacions_odt(documento) -> None:
    """As anotacións (comentarios de revisión, `office:annotation`) NON
    pasan pola detección de datos persoais igual có resto do documento --
    mesma decisión ca cos comentarios .docx (`_limpar_comentarios_docx`):
    baléiranse por completo -- autor (`dc:creator`) e contido de texto --
    en vez de tentar analizalas, conservando só a marca de referencia no
    texto."""
    for anotacion in documento.getElementsByType(AnotacionOdt):
        for autor in anotacion.getElementsByType(AutorAnotacionOdt):
            while autor.childNodes:
                autor.childNodes[0].parentNode = None
                del autor.childNodes[0]
        for paragrafo in anotacion.getElementsByType(ParagrafoOdt):
            while paragrafo.childNodes:
                paragrafo.childNodes[0].parentNode = None
                del paragrafo.childNodes[0]


def _limpar_metadatos_odt(documento) -> None:
    """`meta.xml` garda datos persoais coma quen creou o documento
    orixinalmente (`meta:initial-creator`), quen fixo o último cambio
    (`dc:creator` -- en ODF é ese o seu significado, "último autor", NON
    "autor orixinal"), quen o imprimiu por última vez, título, descrición,
    asunto, palabras clave e campos personalizados -- báleiranse todos,
    mesmo principio cós campos equivalentes de `docProps/core.xml` en
    .docx (`_limpar_metadatos_docx`)."""
    clases_a_baleirar = (
        CreadorInicialMetaOdt, AutorAnotacionOdt, ImprimidoPorMetaOdt,
        TituloMetaOdt, DescricionMetaOdt, AsuntoMetaOdt,
        PalabraClaveMetaOdt, PersonalizadoMetaOdt,
    )
    for clase in clases_a_baleirar:
        for elemento in documento.meta.getElementsByType(clase):
            while elemento.childNodes:
                elemento.childNodes[0].parentNode = None
                del elemento.childNodes[0]


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


# -- escritura conservando formato ------------------------------------------

def _distribuir_por_anacos(textos_anacos: list, substitucions_locais: list) -> list:
    """Reparte `substitucions_locais` (inicio, fin, texto_novo; coordenadas
    locais ao conxunto de anacos, sen solaparse) entre os "anacos" de texto
    dun parágrafo (runs de .docx ou spans/nodos de texto de .odt), cada un
    co seu propio formato. Devolve unha lista paralela co texto novo de
    cada anaco: o texto de substitución insírese enteiro no anaco onde
    EMPEZA a mención orixinal (herda ese formato); os anacos que só cobren
    a continuación dunha mesma substitución quedan baleiros nesa parte."""
    limites = []
    cursor = 0
    for t in textos_anacos:
        limites.append((cursor, cursor + len(t)))
        cursor += len(t)

    resultado = []
    for texto_orix, (inicio_anaco, fin_anaco) in zip(textos_anacos, limites):
        partes = []
        pos = inicio_anaco
        while pos < fin_anaco:
            activa = next((s for s in substitucions_locais if s[0] <= pos < s[1]), None)
            if activa:
                s_inicio, s_fin, s_texto = activa
                if s_inicio == pos:
                    partes.append(s_texto)
                pos = min(s_fin, fin_anaco)
            else:
                candidatos = [s[0] for s in substitucions_locais if pos < s[0] < fin_anaco]
                seguinte = min(candidatos) if candidatos else fin_anaco
                partes.append(texto_orix[pos - inicio_anaco:seguinte - inicio_anaco])
                pos = seguinte
        resultado.append("".join(partes))
    return resultado


def _aplicar_substitucions_a_texto(texto: str, substitucions: list) -> str:
    resultado = texto
    for inicio, fin, novo in sorted(substitucions, key=lambda s: s[0], reverse=True):
        resultado = resultado[:inicio] + novo + resultado[fin:]
    return resultado


def _limites_paragrafos(textos: list) -> list:
    limites = []
    cursor = 0
    for t in textos:
        limites.append((cursor, cursor + len(t)))
        cursor += len(t) + 1  # +1 polo "\n" que separa parágrafos
    return limites


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


def _substituir_texto_paragrafo_docx(paragrafo, texto_novo: str) -> None:
    """Reserva: todo o parágrafo queda co formato do primeiro "anaco".
    Úsase só cando non se poden aplicar substitucións por tramos (ex. o
    letrado editou ese parágrafo na interface de revisión). Usa
    `_anacos_docx` (non `paragrafo.runs`) para baleirar TAMÉN os `w:r`
    que van dentro dun hyperlink -- se non, o texto orixinal do
    hyperlink quedaría sen tocar mentres o resto do parágrafo xa leva o
    texto novo (ver A7)."""
    anacos = _anacos_docx(paragrafo)
    if not anacos:
        if texto_novo:
            paragrafo.add_run(texto_novo)
        return
    anacos[0].text = texto_novo
    for anaco in anacos[1:]:
        anaco.text = ""


def _aplicar_substitucions_paragrafo_docx(paragrafo, substitucions_locais: list) -> None:
    """Conserva o formato de cada "anaco" por separado: só se reescribe o
    texto que cambia, dentro do anaco onde xa estaba. Usa `_anacos_docx`
    para incluír tamén os `w:r` dentro de hyperlinks (ver A7)."""
    anacos = _anacos_docx(paragrafo)
    if not anacos:
        return
    textos = [a.text for a in anacos]
    novos = _distribuir_por_anacos(textos, substitucions_locais)
    for anaco, novo in zip(anacos, novos):
        anaco.text = novo


def _substituir_texto_paragrafo_odt(paragrafo, texto_novo: str) -> None:
    """Reserva: mesmo criterio ca a versión .docx. NON toca unha eventual
    anotación (`office:annotation`) que sexa fillo directo -- o seu
    contido trátase á parte, sempre, en `_limpar_anotacions_odt`
    (ver `_fillos_de_texto_odt`/A9).

    Nota técnica: non se usa `paragrafo.removeChild()` para baleirar o
    paragrafo porque odfpy falla ao tentar actualizar as súas caches
    internas cando o fillo é un nodo de texto plano nun documento cargado
    de disco; manipular `childNodes` directamente evita ese fallo."""
    for fillo in _fillos_de_texto_odt(paragrafo):
        fillo.parentNode = None
        paragrafo.childNodes.remove(fillo)
    if texto_novo:
        paragrafo.addText(texto_novo)


def _aplicar_substitucions_paragrafo_odt(paragrafo, substitucions_locais: list) -> None:
    """Conserva o formato de cada fillo directo do parágrafo por separado
    -- un nodo de texto plano ou un "span" con estilo propio (que pode
    conter varios apelidos con formatos distintos dentro dunha mesma
    frase). Un nodo de texto plano reescríbese cambiando `.data`
    directamente; un "span" baléirase e reescríbese coma na reserva, pero
    SO o seu contido -- o seu propio estilo non se toca. Unha eventual
    anotación fillo directo QUEDA FÓRA (ver `_fillos_de_texto_odt`)."""
    fillos = _fillos_de_texto_odt(paragrafo)
    if not fillos:
        return
    textos = [
        fillo.data if isinstance(fillo, TextoOdt) else teletype.extractText(fillo)
        for fillo in fillos
    ]
    novos = _distribuir_por_anacos(textos, substitucions_locais)
    for fillo, novo in zip(fillos, novos):
        if isinstance(fillo, TextoOdt):
            fillo.data = novo
        else:
            while fillo.childNodes:
                fillo.childNodes[0].parentNode = None
                del fillo.childNodes[0]
            if novo:
                fillo.addText(novo)


def _redactar_imaxes_docx(documento) -> None:
    """Percorre TÓDALAS imaxes de TODO o paquete .docx -- `document.part.
    related_parts` só devolve as relacións DIRECTAS do documento
    principal, o que deixaría fóra imaxes en cabeceiras/pés de páxina
    (viven na súa propia HeaderPart/FooterPart, cunhas relacións á parte;
    comprobado que iter_parts() si as atopa, related_parts non) -- e
    substitúe polo branco+etiqueta calquera que conteña un QR ou código
    de barras. `part._blob` non ten setter público en python-docx, pero é
    o atributo real que le `.blob` -- reescribilo directamente xa queda
    recollido ao gardar o documento."""
    for part in list(documento.part.package.iter_parts()):
        if not getattr(part, "content_type", "").startswith("image/"):
            continue
        nova_imaxe = codigos.redactar_imaxe_se_ten_codigo(part.blob)
        if nova_imaxe is not None:
            part._blob = nova_imaxe


def _redactar_imaxes_odt(documento) -> None:
    """`documento.Pictures` (odfpy) garda cada imaxe incrustada coma
    {ruta: (tipo, bytes, mimetype)} -- tanto as que xa había ao cargar
    coma as engadidas de novo. Reescribir esa entrada xa abonda, non fai
    falta tocar os propios elementos `draw:image` do XML."""
    for ruta, (tipo, datos, mime) in list(documento.Pictures.items()):
        nova_imaxe = codigos.redactar_imaxe_se_ten_codigo(datos)
        if nova_imaxe is not None:
            documento.Pictures[ruta] = (tipo, nova_imaxe, mime)


def gardar_documento_estruturado(
    contexto: dict, texto_final: str, ruta_saida: str, substitucions: list | None = None
) -> None:
    """Escribe `texto_final` de volta no documento orixinal.

    Cando se pasan `substitucions` (inicio, fin, texto_novo; coordenadas do
    texto plano completo, tal como as produce `anonimizar_texto_detallado`)
    e o parágrafo non foi tocado á man na revisión, aplícanse por tramos
    -- conservando a mestura de formatos DENTRO dese parágrafo. Se un
    parágrafo si foi editado (o texto xa non coincide co que se obtería
    aplicando as substitucións orixinais), ou non se pasan `substitucions`,
    ese parágrafo cae na reserva: todo el queda co formato do seu primeiro
    anaco de texto.

    Lanza ValueError se o número de liñas do texto (posiblemente editado)
    xa non coincide co número de parágrafos orixinais -- engadir ou quitar
    saltos de liña desaliñaría a escritura, así que non se intenta.

    Para PDF (`contexto["tipo"] == "pdf"`) delega en
    `pdf_estrutura.gardar_pdf_estruturado`, que traballa por páxina en vez
    de por parágrafo -- ver ese módulo para o porqué."""
    if contexto.get("imaxe"):
        imaxes.gardar(contexto, texto_final, ruta_saida, substitucions)
        return
    if contexto["tipo"] == "pdf":
        gardar_pdf_estruturado(contexto, texto_final, ruta_saida, substitucions)
        return

    partes = texto_final.split("\n")
    paragrafos = contexto["paragrafos"]
    textos_orixinais = contexto["textos_orixinais"]
    n_liñas_esperadas = sum(t.count("\n") + 1 for t in textos_orixinais)
    if len(partes) != n_liñas_esperadas:
        raise ValueError(
            f"o texto ten {len(partes)} liña(s) pero o documento orixinal agarda "
            f"{n_liñas_esperadas} (contando saltos de liña manuais dentro de cada "
            f"parágrafo, en {len(paragrafos)} paragrafo(s)) -- non se pode conservar "
            "o formato (evita engadir ou quitar liñas ao revisar o texto)"
        )
    partes = _agrupar_liñas_por_paragrafo(partes, textos_orixinais)

    limites = _limites_paragrafos(textos_orixinais) if substitucions is not None else None

    substituir_por_tramos = (
        _aplicar_substitucions_paragrafo_docx if contexto["tipo"] == "docx"
        else _aplicar_substitucions_paragrafo_odt
    )
    substituir_todo = (
        _substituir_texto_paragrafo_docx if contexto["tipo"] == "docx"
        else _substituir_texto_paragrafo_odt
    )
    # En .docx, ademais de coincidir o texto, os "anacos" (w:r, incluídos
    # os de hyperlinks) teñen que RECONSTRUÍR exactamente o texto
    # orixinal -- se non (estrutura non anticipada), non é seguro
    # aplicar por tramos e cae á reserva (ver A7).
    anacos_coinciden = (
        _anacos_coinciden_co_texto_docx if contexto["tipo"] == "docx"
        else lambda paragrafo, texto_orixinal: True
    )

    for i, (paragrafo, texto_novo) in enumerate(zip(paragrafos, partes)):
        substitucions_locais = None
        if substitucions is not None:
            p_inicio, p_fin = limites[i]
            locais = [
                (s[0] - p_inicio, s[1] - p_inicio, s[2])
                for s in substitucions
                if p_inicio <= s[0] and s[1] <= p_fin
            ]
            if (
                _aplicar_substitucions_a_texto(textos_orixinais[i], locais) == texto_novo
                and anacos_coinciden(paragrafo, textos_orixinais[i])
            ):
                substitucions_locais = locais

        if substitucions_locais is not None:
            substituir_por_tramos(paragrafo, substitucions_locais)
        else:
            substituir_todo(paragrafo, texto_novo)

    # Pasadas independentes do texto por parágrafo: QR/códigos de barras
    # incrustados coma IMAXE, metadatos do paquete (autor, título...) e
    # comentarios/anotacións de revisión -- nada disto forma parte de
    # ningún parágrafo nin substitución, así que se limpa á parte, SEMPRE
    # (mesmo principio ca en `pdf_estrutura._redactar_codigos_da_paxina`).
    if contexto["tipo"] == "docx":
        _redactar_imaxes_docx(contexto["documento"])
        _limpar_hyperlinks_mailto_docx(contexto["documento"])
        _limpar_comentarios_docx(contexto["documento"])
        _limpar_metadatos_docx(contexto["documento"])
    else:
        _redactar_imaxes_odt(contexto["documento"])
        _limpar_anotacions_odt(contexto["documento"])
        _limpar_metadatos_odt(contexto["documento"])

    contexto["documento"].save(str(ruta_saida))


# -- anonimizacion ------------------------------------------------------

def _limites_por_contexto(contexto: dict | None) -> list | None:
    if not contexto:
        return None
    if contexto["tipo"] == "pdf":
        return _limites_paxinas(contexto["paxinas"])
    return _limites_paragrafos(contexto["textos_orixinais"])


def _clamp_substitucions_a_limites(substitucions: list, limites: list) -> list:
    """Se unha substitución cruza a fronteira entre dous "contedores"
    (parágrafos en .docx/.odt, páxinas en .pdf) -- practicamente sempre un
    erro de detección do NER/patróns esparexendo unha mención máis alá do
    que debería, nunca unha mención real que abarque dous contedores --
    pártese en anacos, un por cada contedor que toca. Isto evita desaliñar
    o número de parágrafos/páxinas do documento orixinal (o que faría
    fallar `gardar_documento_estruturado`/`gardar_pdf_estruturado` xa na
    primeira comprobación, mesmo SEN que un letrado editase nada a man).
    Cada anaco redáctase co MESMO código, así que nunca queda un anaco sen
    redactar."""
    resultado = []
    for inicio, fin, novo in substitucions:
        tocados = [(a, b) for (a, b) in limites if fin > a and inicio < b]
        if len(tocados) <= 1:
            resultado.append((inicio, fin, novo))
            continue
        for a, b in tocados:
            i2, f2 = max(inicio, a), min(fin, b)
            if i2 < f2:
                resultado.append((i2, f2, novo))
    return resultado


def ler_fragmentos(bruto: str) -> list:
    """Cadro "engadir ou xeneralizar" da revisión: un fragmento por liña;
    "texto => substituto" xeneraliza (o substituto vai tal cal), "texto" só
    anonimízao coma persoa (código PERSOA_ novo, o mesmo en todas as súas
    aparicións). Liñas baleiras ignóranse."""
    fragmentos = []
    for liña in (bruto or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if not liña.strip():
            continue
        texto, separador, substituto = liña.partition("=>")
        texto = texto.strip()
        if texto:
            fragmentos.append((texto, substituto.strip() if separador else None))
    return fragmentos


def aplicar_decisions(
    texto: str,
    substitucions: list,
    rexistro: RexistroCorrespondencias,
    codigos_descartados: set,
    fragmentos: list,
    contexto: dict | None = None,
) -> tuple:
    """Revisión humana por DECISIÓNS: parte sempre do texto ORIXINAL e das
    substitucións automáticas, nunca dun texto libre editado -- así o
    documento de saída conserva SEMPRE o formato (o PDF non cae a .txt).

    - `codigos_descartados`: persoas que quen revisa marcou coma "non é
      persoa" -> as súas substitucións quítanse (o texto queda á vista).
    - `fragmentos`: [(texto, substituto | None)] (ver `ler_fragmentos`).
      Cada aparición enteira (non dentro doutra palabra) que non estea xa
      tapada substitúese; sen substituto, cun código de persoa novo.

    Devolve (texto_final, substitucions, codigos_novos)."""
    novas = [s for s in substitucions if s[2] not in codigos_descartados]
    codigos_novos = []
    for fragmento, substituto in fragmentos:
        ocupado = sorted((a, b) for a, b, _ in novas)
        aparicions = [
            (m.start(), m.end()) for m in re.finditer(r"(?<!\w)" + re.escape(fragmento) + r"(?!\w)", texto)
            if not any(m.start() < b and a < m.end() for a, b in ocupado)
        ]
        if not aparicions:
            continue
        if substituto is None:
            mencions = [Entidade(a, b, texto[a:b], "PERSOA") for a, b in aparicions]
            codigo, _, _, _ = rexistro.resolver_ou_crear(resolution.Grupo(representante=fragmento, mencions=mencions))
            codigo = idioma.codigo_visible(codigo)
            codigos_novos.append(codigo)
            substituto = codigo
        novas.extend((a, b, substituto) for a, b in aparicions)
    limites = _limites_por_contexto(contexto)
    if limites is not None:
        novas = _clamp_substitucions_a_limites(novas, limites)
    return _aplicar_substitucions_a_texto(texto, novas), novas, codigos_novos


def anonimizar_texto_detallado(
    texto: str,
    rexistro: RexistroCorrespondencias,
    ficheiro_config: str = _CONFIG_POR_DEFECTO,
    contexto: dict | None = None,
) -> tuple:
    """Coma `anonimizar_texto`, pero devolve tamén a lista de substitucións
    (inicio, fin, texto_novo) en coordenadas do texto orixinal completo --
    necesaria para escribir de volta un .docx/.odt/.pdf conservando o
    formato orixinal (`gardar_documento_estruturado`). Cando se pasa
    `contexto`, calquera substitución que cruce unha fronteira de
    parágrafo/páxina pártese en anacos (`_clamp_substitucions_a_limites`)
    para non desaliñar a estrutura do documento xa desde aquí."""
    entidades, doc = ner.detectar(texto, celas=(contexto or {}).get("celas_datos_persoais"))
    grupos = resolution.agrupar(entidades, texto)
    # Cada aparición física dun documento ten UN só titular aquí (A16: se
    # recibise dúas substitucións coas mesmas coordenadas, a segunda
    # aplicaríase sobre o texto xa modificado e corrompería os veciños).
    titular_do_documento = resolution.documentos_por_grupo(grupos, entidades, texto)
    documentos = [e for e in entidades if id(e) in titular_do_documento]
    lingua = idioma.actual()  # unha soa vez: todo o documento co mesmo prefixo e etiquetas

    substitucions = []  # (inicio, fin, texto_substituto)
    informe_persoas = []

    for grupo in grupos:
        codigo, marcado, motivo, posibles_coincidencias = rexistro.resolver_ou_crear(grupo)
        # O rexistro garda PERSOA_n; o documento e a pantalla levan o prefixo do idioma.
        codigo = idioma.codigo_visible(codigo, lingua)
        posibles_coincidencias = [idioma.codigo_visible(c, lingua) for c in posibles_coincidencias or []]
        for mencion in grupo.mencions:
            substitucions.append((mencion.inicio, mencion.fin, codigo))
        for d in documentos:
            if titular_do_documento[id(d)] is grupo:
                substitucions.append((d.inicio, d.fin, codigo))
        informe_persoas.append({
            "codigo": codigo,
            "mencions": [m.texto for m in grupo.mencions],
            "marcado_para_revision": marcado,
            "motivo": idioma.codigos_visibles_no_texto(motivo, lingua) if motivo else motivo,
            "posibles_coincidencias": posibles_coincidencias,
        })

    documentos_cubertos = {id(d) for d in documentos}
    outras_directas = []
    exentos_cargo_publico = []
    for e in entidades:
        etiqueta_saida = _ETIQUETA_REDACCION.get(e.etiqueta)
        if id(e) in documentos_cubertos:
            if e.etiqueta != "DNI_NIE":  # o informe segue amosando pasaportes e documentos de táboa
                outras_directas.append({"tipo": e.etiqueta, "texto": e.texto})
            continue
        if etiqueta_saida:
            substitucions.append((e.inicio, e.fin, f"[{idioma.etiqueta(etiqueta_saida, lingua)}]"))
            outras_directas.append({"tipo": e.etiqueta, "texto": e.texto})
        elif e.etiqueta == "DNI_NIE":
            substitucions.append((e.inicio, e.fin, "[DNI_NIE]"))
            outras_directas.append({"tipo": e.etiqueta, "texto": e.texto})
        elif e.etiqueta == "PERSOA_EXENTA_CARGO_PUBLICO":
            # Non se anonimiza (criterio AEPD, ver ner.py `_CARGOS_EXENTOS_RE`)
            # -- queda no informe para que un letrado poida revisar e corrixir
            # a man se a exención automática se aplicou mal.
            exentos_cargo_publico.append({"texto": e.texto, "cargo": e.cargo})

    limites = _limites_por_contexto(contexto)
    if limites is not None:
        substitucions = _clamp_substitucions_a_limites(substitucions, limites)

    texto_anonimizado = _aplicar_substitucions_a_texto(texto, substitucions)

    riscos_mosaico = mosaic.analizar(texto_anonimizado, ner.cargar_modelo(), ficheiro_config)

    # Rede de seguridade final: NON é un recoñecedor máis, é un escaneo
    # do texto XA anonimizado en busca de patróns que aínda parezan datos
    # persoais -- ningunha combinación de spaCy + patróns pode garantir
    # cubrir tódolos formatos posibles nun documento real (ver
    # `risco_residual.py`). Sepárase por confianza para que o letrado
    # saiba distinguir "case seguro un fallo" de "revisión opcional".
    risco_residual = escanear_risco_residual(texto_anonimizado)
    categoria_especial = escanear_categoria_especial(texto_anonimizado)

    informe = {
        "persoas": informe_persoas,
        "identificadores_directos": outras_directas,
        "exentos_cargo_publico": exentos_cargo_publico,
        "riscos_mosaico": [
            {"tipo": r.tipo, "frase": r.frase, "detalle": r.detalle} for r in riscos_mosaico
        ],
        "risco_residual": [
            {"tipo": r.tipo, "texto": r.texto, "confianza": r.confianza, "contexto": r.contexto}
            for r in risco_residual
        ],
        "categoria_especial": [
            {"categoria": a.categoria, "termo": a.termo, "contexto": a.contexto}
            for a in categoria_especial
        ],
    }
    return texto_anonimizado, informe, substitucions


def anonimizar_texto(
    texto: str,
    rexistro: RexistroCorrespondencias,
    ficheiro_config: str = _CONFIG_POR_DEFECTO,
) -> tuple:
    texto_anonimizado, informe, _ = anonimizar_texto_detallado(texto, rexistro, ficheiro_config)
    return texto_anonimizado, informe


def anonimizar_ficheiro(ruta_entrada: str, rexistro: RexistroCorrespondencias, ficheiro_config: str = _CONFIG_POR_DEFECTO) -> tuple:
    texto = cargar_texto(ruta_entrada)
    return anonimizar_texto(texto, rexistro, ficheiro_config)


def nome_ficheiro_anonimizado(
    nome_orixinal: str,
    rexistro: RexistroCorrespondencias,
    persoas_do_documento: list | None = None,
) -> str:
    """Anonimiza nomes de persoas, DNI/NIE e outros identificadores directos
    que aparezan no propio NOME DO FICHEIRO -- caso real atopado cos
    documentos dun expediente real: un ficheiro chamado coma a persoa á
    que se refire ("Certificado poder Jose Luis Lopez Rabadan.pdf") deixaría
    o nome real á vista aínda que o CONTIDO quedase ben anonimizado.

    `persoas_do_documento` (opcional) é `informe["persoas"]` xa calculado
    para o CONTIDO deste mesmo ficheiro (`anonimizar_texto_detallado`) --
    se un nome do ficheiro coincide cunha mención xa resolta aí, reutilízase
    ESE código directamente, sen volver pasar por `resolver_ou_crear`.

    A17 (revisión 21/09/2026): antes desta función SEMPRE resolvía os
    nomes do propio ficheiro coma un texto illado, sen ningunha relación
    co contido -- e coma `resolver_ou_crear` NUNCA fusiona automaticamente
    só por coincidir o nome (protección xeral contra homónimos entre
    documentos DISTINTOS, ver `registry.resolver_ou_crear`), cada chamada
    creaba un código NOVO. Resultado: o contido dicía "PERSOA_000005" pero
    o nome de ficheiro dicía "PERSOA_000006", e chamar isto outra vez
    (coma faille o zip, que tamén anonimiza cartafoles) daba "PERSOA_000007".
    Coma este é o MESMO documento, non hai risco de confundir dúas persoas
    distintas: se o nome xa se viu no contido, é seguro reutilizar o
    código sen crear un rexistro novo.

    Sen `persoas_do_documento` (chamada solta, sen contido de referencia)
    compórtase coma antes: créase código novo coa lóxica conservadora de
    sempre.

    "_"/"-" trócanse por espazos SÓ para a detección (1 carácter por 1,
    non desprazan posicións -- mesmo truco ca coa suavización de
    maiúsculas en `ner.py`), xa que son os separadores máis habituais en
    nomes de ficheiro ("Jose_Luis_Lopez_Rabadan.pdf"); o resto do nome
    (partes non detectadas) mantense tal cal, separadores incluídos."""
    ruta = Path(nome_orixinal)
    stem_orixinal = ruta.stem
    stem_normalizado = stem_orixinal.replace("_", " ").replace("-", " ")

    entidades, _ = ner.detectar(stem_normalizado)
    if not entidades:
        return nome_orixinal

    codigo_por_nome = {}
    for persoa in persoas_do_documento or []:
        for mencion in persoa.get("mencions", []):
            codigo_por_nome[resolution.normalizar(mencion)] = persoa["codigo"]

    dnis = [e for e in entidades if e.etiqueta == "DNI_NIE"]
    grupos = resolution.agrupar(entidades, stem_normalizado)
    substitucions = []
    dnis_xa_substituidos_ids = set()  # mesma protección ca A16, ver anonimizar_texto_detallado

    for grupo in grupos:
        codigo = codigo_por_nome.get(resolution.normalizar(grupo.representante))
        if not codigo:
            codigo, _, _, _ = rexistro.resolver_ou_crear(grupo)
            codigo = idioma.codigo_visible(codigo)
        for mencion in grupo.mencions:
            substitucions.append((mencion.inicio, mencion.fin, codigo))
        if grupo.dni:
            for d in dnis:
                if id(d) in dnis_xa_substituidos_ids:
                    continue
                if d.texto == grupo.dni or d.texto.upper().replace("-", "") == grupo.dni:
                    substitucions.append((d.inicio, d.fin, codigo))
                    dnis_xa_substituidos_ids.add(id(d))

    # Un DNI SOLTO (sen nome de persoa preto para agrupalo dentro do propio
    # nome de ficheiro, coma "DNI 30014811Z escaneado.pdf") queda por
    # defecto coma "[DNI_NIE]" xenérico -- `resolution.agrupar` esixe un
    # nome preto para poder ligalo a unha persoa. Se ese DNI xa está
    # rexistrado (a persoa xa apareceu no contido do documento, por
    # exemplo), mellor usar o código da persoa, coherente co resto dos
    # seus documentos.
    dnis_cubertos = {s[0] for s in substitucions}
    for d in dnis:
        if d.inicio in dnis_cubertos:
            continue
        codigo = rexistro.codigo_por_dni(d.texto)
        if codigo:
            codigo = idioma.codigo_visible(codigo)
        substitucions.append((d.inicio, d.fin, codigo or "[DNI_NIE]"))

    if not substitucions:
        return nome_orixinal

    novo_stem = _aplicar_substitucions_a_texto(stem_orixinal, substitucions)
    return novo_stem + ruta.suffix


def _anonimizar_cartafoles_ruta(
    cartafol: PurePosixPath,
    rexistro: RexistroCorrespondencias,
    persoas_do_documento: list | None = None,
) -> PurePosixPath:
    """Anonimiza CADA compoñente dun camiño de cartafol por separado,
    mantendo a estrutura de subcartafoles (A10) -- reutiliza
    `nome_ficheiro_anonimizado` para cada compoñente, mesma lóxica ca no
    nome do propio ficheiro: un cartafol chamado coma unha persoa
    ("Cliente Xosé Manuel Carballo Portela/nota.txt") deixaría o nome real
    á vista aínda que o ficheiro final xa quedase ben anonimizado."""
    return PurePosixPath(
        *(
            nome_ficheiro_anonimizado(compoñente, rexistro, persoas_do_documento)
            for compoñente in cartafol.parts
        )
    )


def ruta_saida_por_defecto(
    ruta_entrada: str,
    cartafol_saida: str | None = None,
    rexistro: RexistroCorrespondencias | None = None,
    persoas_do_documento: list | None = None,
    ruta_provisional_propia: str | None = None,
) -> str:
    """Para .docx/.odt e .zip mantén a mesma extensión (conserva formato,
    ou estrutura de cartafoles no caso do zip); para calquera outro
    formato de entrada, garda coma .txt plano. Sen `cartafol_saida`, o
    ficheiro final vai canda o orixinal (comportamento de sempre); con el,
    vai nese cartafol en vez de alí. Se se pasa `rexistro`, o NOME do
    ficheiro tamén se anonimiza (`nome_ficheiro_anonimizado`) -- útil
    cando o propio nome do ficheiro orixinal xa menciona a persoa ou o
    seu DNI. `persoas_do_documento` (opcional, `informe["persoas"]` do
    CONTIDO xa procesado deste mesmo ficheiro) evita que o nome de
    ficheiro reciba un código distinto ao do contido (A17).

    `ruta_provisional_propia` (opcional): a ruta que XA se usou para
    escribir provisionalmente ESTE MESMO ficheiro (patrón "escribir a un
    nome provisional, logo calcular o nome final e renomear" que usan
    `web._procesar_automatico` e `cli.main`) -- non conta coma colisión
    contra si mesma na comprobación de A18, xa que ese ficheiro
    provisional vai desaparecer (renomearse) nesta mesma chamada."""
    ruta_p = Path(ruta_entrada)
    sufixo = ruta_p.suffix.lower()
    nome_ficheiro = ruta_p.name
    if rexistro is not None:
        nome_ficheiro = nome_ficheiro_anonimizado(nome_ficheiro, rexistro, persoas_do_documento)
    stem = Path(nome_ficheiro).stem
    if sufixo in FORMATOS_CON_ESTRUTURA or sufixo == ".zip":
        extension_saida = ".anonimizado" + sufixo
    else:
        extension_saida = ".anonimizado.txt"
    cartafol = Path(cartafol_saida) if cartafol_saida else ruta_p.parent

    # A18 (revisión 21/09/2026): ao procesar TODO un cartafol cara a un
    # `cartafol_saida` PLANO (sen manter a estrutura de subcartafoles),
    # dous ficheiros de entrada con distinto camiño pero o MESMO nome
    # (p.ex. "A/demanda.pdf" e "B/demanda.pdf") calculaban exactamente a
    # mesma ruta de saída -- o segundo sobrescribía o primeiro EN SILENCIO,
    # sen aviso ningún, perda real de contido xa anonimizado. Se a ruta xa
    # existe (doutro ficheiro deste mesmo lote, xa escrito), engádese un
    # contador ata atopar unha ruta libre -- nunca se sobrescribe nada xa
    # escrito por esta mesma execución.
    ruta_propia = Path(ruta_provisional_propia).resolve() if ruta_provisional_propia else None
    ruta_saida = cartafol / (stem + extension_saida)
    contador = 2
    while ruta_saida.exists() and ruta_saida.resolve() != ruta_propia:
        ruta_saida = cartafol / (f"{stem}-{contador}" + extension_saida)
        contador += 1
    return str(ruta_saida)


EXTENSIONS_SOPORTADAS = (".pdf", ".docx", ".odt", ".txt", *imaxes.FORMATOS)


def listar_ficheiros_soportados(cartafol: str) -> tuple[list, list]:
    """Percorre `cartafol` recursivamente (informe: "que anonimice todos
    os arquivos do cartafol"). Devolve (soportados, omitidos) coma listas
    de rutas absolutas ordenadas -- cada soportado procésase coma un
    documento á parte, cunha sesión de revisión propia, igual ca se se
    tivese indicado un por un.

    Os resultados dunha pasada anterior (`<nome>.anonimizado.<ext>`, ver
    `ruta_saida_por_defecto`) NON se volven procesar como entrada -- se se
    repite un cartafol co mesmo cartafol de saída (ou sen ningún: saen
    canda o orixinal), senón se anonimizarían as propias copias xa
    anonimizadas e o cartafol encheríase de `.anonimizado.anonimizado`.
    Van a `omitidos`."""
    raiz = Path(cartafol)
    soportados, omitidos = [], []
    for ruta in sorted(raiz.rglob("*")):
        if ruta.is_dir():
            continue
        if ruta.suffix.lower() in EXTENSIONS_SOPORTADAS and not ruta.stem.lower().endswith(".anonimizado"):
            soportados.append(str(ruta))
        else:
            omitidos.append(str(ruta))
    return soportados, omitidos


def anonimizar_zip(
    ruta_entrada: str,
    ruta_saida: str,
    rexistro: RexistroCorrespondencias,
    ficheiro_config: str = _CONFIG_POR_DEFECTO,
) -> dict:
    """Anonimiza cada ficheiro soportado (.pdf, .docx, .odt, .txt e
    imaxes) dentro dun .zip, mantendo a estrutura de cartafoles.

    Conserva o formato e a extensión orixinais para .docx/.odt/.pdf e as
    imaxes coma en `anonimizar_e_gardar` (`pdf_estrutura.py` para o caso de
    PDF, con ou sen texto nativo; `imaxes.py`). O orixinal NUNCA se inclúe
    no zip de saída baixo ningún concepto -- só a versión xa anonimizada.

    Calquera outro tipo de ficheiro (planos CAD, HEIC...) NON se pode
    analizar en busca de datos persoais e por seguridade NON se inclúe no
    zip de saída -- queda listado en `omitidos` do informe devolto, para
    que quede constancia explícita do que non se puido revisar.

    Os nomes de CARTAFOL tamén se anonimizan compoñente a compoñente
    (`_anonimizar_cartafoles_ruta`) -- un cartafol chamado coma unha
    persoa ("Cliente Xosé Manuel Carballo Portela/nota.txt") deixaría o
    nome real á vista aínda que o ficheiro final quedase ben anonimizado
    (A10). As entradas de metadatos do propio ZIP xerados por macOS
    (`__MACOSX/` e ficheiros `._*`) NON se tentan procesar -- son copias
    de metadatos de Finder, non documentos reais -- e quedan en
    `omitidos`."""
    informes_por_ficheiro = {}
    omitidos = []

    with zipfile.ZipFile(ruta_entrada) as zip_entrada, \
         zipfile.ZipFile(ruta_saida, "w", zipfile.ZIP_DEFLATED) as zip_saida, \
         tempfile.TemporaryDirectory() as tmp:
        for info in zip_entrada.infolist():
            if info.is_dir():
                continue

            nome = info.filename
            nome_p = PurePosixPath(nome)
            if "__MACOSX" in nome_p.parts or nome_p.name.startswith("._"):
                omitidos.append(nome)
                continue

            sufixo = Path(nome).suffix.lower()
            if sufixo not in EXTENSIONS_SOPORTADAS:
                omitidos.append(nome)
                continue

            tmp_entrada = Path(tmp) / Path(nome).name
            tmp_entrada.write_bytes(zip_entrada.read(nome))

            texto, contexto = cargar_documento_estruturado(str(tmp_entrada))
            texto_anon, informe, substitucions = anonimizar_texto_detallado(
                texto, rexistro, ficheiro_config, contexto=contexto
            )
            informes_por_ficheiro[nome] = informe

            nome_ficheiro_saida = nome_ficheiro_anonimizado(nome_p.name, rexistro, informe["persoas"])
            stem_saida = PurePosixPath(nome_ficheiro_saida).stem
            cartafol_saida = _anonimizar_cartafoles_ruta(nome_p.parent, rexistro, informe["persoas"])
            if contexto and sufixo in FORMATOS_CON_ESTRUTURA:
                nome_saida = str(cartafol_saida / (stem_saida + ".anonimizado" + sufixo))
                tmp_saida = Path(tmp) / ("saida_" + Path(nome).name)
                gardar_documento_estruturado(contexto, texto_anon, str(tmp_saida), substitucions)
                zip_saida.write(str(tmp_saida), arcname=nome_saida)
            else:
                nome_saida = str(cartafol_saida / (stem_saida + ".anonimizado.txt"))
                zip_saida.writestr(nome_saida, texto_anon)

            tmp_entrada.unlink()

    return {"ficheiros": informes_por_ficheiro, "omitidos": omitidos}


def anonimizar_e_gardar(
    ruta_entrada: str,
    ruta_saida: str,
    rexistro: RexistroCorrespondencias,
    ficheiro_config: str = _CONFIG_POR_DEFECTO,
) -> tuple:
    """Anonimiza `ruta_entrada` e garda en `ruta_saida`. Conserva o formato
    orixinal (incluída a mestura de formatos dentro de cada parágrafo)
    cando a entrada é .docx/.odt E a saída pide a mesma extensión; en
    calquera outro caso garda coma texto plano."""
    texto_anonimizado, informe, _ = anonimizar_e_gardar_detallado(ruta_entrada, ruta_saida, rexistro, ficheiro_config)
    return texto_anonimizado, informe


def anonimizar_e_gardar_detallado(
    ruta_entrada: str,
    ruta_saida: str,
    rexistro: RexistroCorrespondencias,
    ficheiro_config: str = _CONFIG_POR_DEFECTO,
) -> tuple:
    """Coma `anonimizar_e_gardar`, pero devolve tamén as substitucións (as
    necesita a revisión posterior dun documento procesado en automático)."""
    texto, contexto = cargar_documento_estruturado(ruta_entrada)
    texto_anonimizado, informe, substitucions = anonimizar_texto_detallado(
        texto, rexistro, ficheiro_config, contexto=contexto
    )

    if conserva_formato(contexto, ruta_saida):
        gardar_documento_estruturado(contexto, texto_anonimizado, ruta_saida, substitucions)
    else:
        Path(ruta_saida).write_text(texto_anonimizado, encoding="utf-8")

    return texto_anonimizado, informe, substitucions
