"""Motor de deteccion de entidades: combina o NER de spaCy (persoas, lugares)
cos recoñecedores por patron de identificadores directos españois."""

from __future__ import annotations

import bisect
import itertools
import re
import sys
import unicodedata
from functools import lru_cache

import spacy

from . import lugares_oficiais, nomes_ine, recognizers
from .recognizers import DOCUMENTOS_DE_IDENTIDADE, Entidade

_MODELO = "es_core_news_md"

# Mapeo das etiquetas do modelo (esquema CoNLL) as nosas categorias.
_MAPA_SPACY = {"PER": "PERSOA", "LOC": "LOCALIZACION", "ORG": "ORGANIZACION"}

# Conectores de apelidos/nomes compostos que son lexitimamente minúsculos
# (Xoán "de" Cominges, "van" der Berg...) e non deben cortarse.
_CONECTORES_NOME = {"de", "del", "do", "dos", "da", "das", "la", "las", "los", "el", "y", "e", "van", "von"}

# O modelo apenas recoñece persoas en texto TODO EN MAIÚSCULAS -- caso real
# atopado nun certificado de poder ("D/Dª JOSE LUIS LOPEZ RABADAN..." non se
# detectaba coma persoa en absoluto). É extremadamente habitual en notas de
# poder, notas simples rexistrais e sinaturas de documentos oficiais
# españois. Pasamos unha copia con eses anacos en "Title Case" SÓ PARA A
# DETECCIÓN: `capitalize()` non cambia a lonxitude de ningunha palabra
# (incluídas as acentuadas), así que as posicións de caracteres seguen a
# corresponder exactamente ao texto orixinal.
#
# Importante: NON abonda con poñer en Title Case calquera palabra en
# maiúsculas -- se toda a frase está en maiúsculas, palabras funcionais
# coma "CON" ou "NIF" tamén parecerían nomes propios e o recorte de
# fronteiras (`_recortar_entidade_persoa`) xa non as distinguiría. Por
# iso estas palabras pásanse a minúsculas (non a Title Case) para que
# seguan a "parecer" o que son: conectores, non continuacións de nome.
_PALABRA_MAIUSCULA = re.compile(r"\b[A-ZÁÉÍÓÚÑÜ]{2,}\b")

_PALABRAS_FUNCIONAIS = {
    # preposicions, conxuncions, artigos, pronomes (castelán e galego)
    "con", "sin", "por", "para", "en", "de", "del", "al", "a", "ante", "bajo",
    "cabe", "contra", "desde", "durante", "entre", "hacia", "hasta", "mediante",
    "según", "segun", "sobre", "tras", "versus", "vía", "via",
    "e", "y", "o", "u", "ni", "que", "como", "cuando", "cuanto", "donde",
    "quien", "cuyo", "cuya", "el", "la", "los", "las", "un", "una", "unos", "unas",
    "do", "da", "dos", "das", "no", "na", "nos", "nas", "ao", "aos", "coa", "cos",
    "este", "esta", "estos", "estas", "ese", "esa", "esos", "esas",
    "mi", "mí", "tu", "tú", "su", "sus", "él", "ella", "ellos", "ellas",
    "usted", "ustedes", "nosotros", "vosotros", "eu", "ti", "min",
    # termos administrativos habituais que non forman parte dun nome
    "nif", "dni", "nie", "cif", "csv", "cp",
    # "CVE" (Código de Verificación Electrónica): pé de páxina habitual do DOG
    # ("CVE-DOG: <hash>", repetido en cada páxina). Sen esta entrada, a
    # suavización deixaba "CVE" en Title Case ("Cve") e, unido ao guion,
    # "Cve-Dog" tiña a forma exacta dun apelido composto ("Pérez-Vázquez") --
    # spaCy clasificábao coma PERSOA en case o 70% das aparicións (caso real:
    # documento de 147 páxinas, 20 delas coa etiqueta trocada por un código de
    # persoa e o hash real intacto ao lado, INCONSISTENTE dentro do MESMO
    # documento porque a clasificación de spaCy depende do contexto veciño de
    # cada páxina). "CVE-DOG" nunca é un dato persoal.
    "cve",
    # Mesmo mecanismo nas siglas dos boletíns oficiais: a marxe de cada
    # páxina do BOE ("cve: BOE-A-2026-19351") e "publicado no BOE" saían
    # coma "PERSOA_..." (corpus web, 29/09/2026: 13 documentos).
    "boe", "dog", "bop", "doue", "ou",
    "domicilio", "mayor", "menor", "edad", "vecino", "vecina", "vecinos", "vecinas",
    "residente", "titular", "titulares", "referencia", "número", "numero",
    "comparece", "comparecen", "manifiesta", "manifiestan", "declara", "declaran",
    "expone", "exponen", "solicita", "solicitan", "certifica", "certifican",
    "consta", "constan", "según", "propio", "propia", "nombre",
    # profesións/cargos habituais despois dun nome en sinaturas e certificados
    "arquitecto", "arquitecta", "abogado", "abogada", "avogado", "avogada",
    "notario", "notaria", "procurador", "procuradora", "médico", "medico",
    "médica", "medica", "ingeniero", "ingeniera", "enxeñeiro", "enxeñeira",
    "aparejador", "aparejadora", "colegiado", "colegiada", "colexiado", "colexiada",
    "registrador", "registradora", "secretario", "secretaria", "presidente", "presidenta",
}


def _suavizar_maiusculas_para_deteccion(texto: str) -> str:
    def _transformar(match: re.Match) -> str:
        palabra = match.group(0)
        if palabra.lower() in _PALABRAS_FUNCIONAIS:
            return palabra.lower()
        return palabra.capitalize()

    return _PALABRA_MAIUSCULA.sub(_transformar, texto)


# Caso real atopado revisando unha certificación de burofax: "Mª Pilar
# Camacho Briones" (honorífico abreviado con "ª") non se detectaba coma
# persoa EN ABSOLUTO -- o modelo fusionábaa cunha ORGANIZACIÓN da liña
# anterior ("... S.L.\nMª Pilar...") en vez de recoñecela coma PER. O
# causante é o propio caracter "ª"/"º" (indicador ordinal), non habitual
# no corpus de adestramento do modelo. Substituílo por unha letra normal
# ("a"/"o") -- SEMPRE 1 caracter por 1 caracter, así que non despraza
# ningunha posición -- abonda para que o tokenizador faga a análise
# correcta, e resolve tamén "Dª", "nº" etc. de paso.
_ORDINAIS_A_LETRA = str.maketrans({"ª": "a", "º": "o"})


def _suavizar_ordinais_para_deteccion(texto: str) -> str:
    return texto.translate(_ORDINAIS_A_LETRA)


# Recoñecedor de reserva (mesmo principio ca `ocr_dni.detectar_dnis_por_contexto`):
# cando o modelo de NER falla en recoñecer unha persoa introducida por un
# tratamento honorífico -- moi habitual en textos xurídicos españois ("D.",
# "Dna.", "Don", "Doña", "D/Dª") -- e a funde noutra entidade (caso real:
# na mesma páxina, "Documentacion\nPor D. José Luis López Rabadán" quedou
# etiquetado enteiro coma MISC, non PER, polo texto veciño -- e "Leandro
# M. del Valle Resua" nunha sinatura quedou partido en "Leandro" (PER) e
# "Valle Resua" (LOC) --, este patrón cobre igual o nome sen depender do
# que decida o modelo. `[ \t]+` (nunca `\s+`) impide que se estenda a
# unha liña seguinte (ex. un enderezo despois dun salto de liña); un
# conector ("del", "de"... ou dous seguidos: "de la", "de los") só se
# acepta cando vai seguido dunha nova palabra en maiúscula, así o nome nunca remata nun conector solto.
#
# A propósito NON inclúe "y"/"e": son os conectores lexítimos dun apelido
# composto ("Ortega y Gasset"), pero en textos xurídicos é moitísimo máis
# habitual coma conxunción ENTRE DÚAS PERSOAS distintas ("D. Xoán... e
# Dna. María... comparecen") -- incluílos aquí fundiría eses dous
# comparecentes nunha soa "persoa" (bug real atopado probando este mesmo
# arranxo cun texto de comparecencia con dous nomes).
_CONECTOR_NOME_RE = r"(?:de|del|do|dos|da|das|la|las|los|el|van|von)"
# Esixe POLO MENOS 2 caracteres (`+`, non `*`): unha soa maiúscula solta
# (coma a conxunción "Y"/"E" entre dúas persoas, que non se suaviza a
# minúscula por ter só 1 caracter -- ver `_suavizar_maiusculas_para_deteccion`)
# NON debe colar coma "palabra de nome", ou volvería fundir comparecentes
# distintos (mesmo bug ca arriba). Unha inicial real sempre leva punto
# ("M.") e xa ten a súa propia alternativa á parte.
#
# Admite tamén apelidos con guion ("Pérez-Vázquez") e con apóstrofo tras
# unha inicial ("O'Donnell", "D'Angelo") coma UNHA soa palabra: antes o
# guion/apóstrofo cortaba o nome e o resto quedaba en claro (bug real:
# "D. Xoán Pérez-Vázquez Souto" -> "D. PERSOA_000001-Vázquez Souto").
# Tras o guion tamén en minúscula: apelidos compostos cataláns
# ("Vall-llossera", "Puig-serra", "Ribas-i-Soler"); corpus web (30/09/2026):
# "doña Marta Vall-llossera Ferran" deixaba "-llossera Ferran" á vista.
_PALABRA_CAPITALIZADA_RE = (
    r"(?:[A-ZÁÉÍÓÚÑÜ]['’])?[A-ZÁÉÍÓÚÑÜ][\wáéíóúñÁÉÍÓÚÑÜ]+"
    r"(?:-[\wáéíóúñÁÉÍÓÚÑÜ]+)*"
)

# Continuación dun nome xa detectado: cada "unidade" é (a) unha inicial
# solta ("M.", habitual coma segundo nome/materno) ou (b) un conector
# coñecido ("del", "de"... ou dous seguidos, "de la") seguido de 1 ou 2 palabras con maiúscula
# inicial (un apelido composto coma "del Valle Resua"). A propósito NON
# existe unha unidade "palabra con maiúscula solta, sen conector" -- se a
# houbese, calquera lista de persoas enumeradas ("Don Xoán... e Dna.
# María...") fundiríase nunha soa, xa que cada nome da lista tamén
# empeza por maiúsculas (bug real atopado probando este mesmo arranxo).
_UNIDADE_CONTINUACION_RE = (
    r"(?:[A-ZÁÉÍÓÚÑÜ]\."
    r"|(?:" + _CONECTOR_NOME_RE + r"[ \t]+){1,2}" + _PALABRA_CAPITALIZADA_RE
    + r"(?:[ \t]+" + _PALABRA_CAPITALIZADA_RE + r")?)"
)

# "Dña" (contraendo o "o") é a abreviatura MÁIS habitual de "Doña" en
# textos administrativos, tan ou máis ca a forma sen contraer.
#
# Aquí SI se usa `\s+` (con salto de liña incluído) coma separador dentro
# do propio nome -- a diferenza de `_CONTINUACION_NOME_PERSOA` -- porque
# xa estamos ANCORADOS por un tratamento persoal explícito xusto diante;
# o risco de estenderse a un enderezo ou epígrafe doutro contido (o
# motivo de restrinxilo alí) non se aplica aquí. Caso real que o motivou:
# un apelido dividido por un salto de liña de axuste de marxe, "D. José
# Luis López\nRabadán", quedaba con "Rabadán" sen redactar.
#
# Tamén en MINÚSCULA ("don", "doña", "dona", "dña."): no texto corrido do
# BOE/DOG é a forma habitual ("resuelvo: Nombrar a doña X...", "De una
# parte, don X... Alcalde-Presidente") -- caso real do corpus web
# (28/09/2026): sen coma entre o nome e o cargo, spaCy non detectaba a
# persoa e o nome quedaba enteiro á vista. A abreviatura "D." segue só en
# maiúscula ("d." en minúscula é moi ambiguo).
_HONORIFICO_RE = r"(?:[Dd]o[ñn]a?\.?|[Dd]ña\.?|D/D[ªa]\.?|D\.)"
#
# O nome pode ser só iniciais ("don B. L. S.", "doña T.G.C."): o BOE
# pseudonimiza así nas resolucións da DGSJFP. spaCy detectábaas ao chou
# (unha aparición si, outra non; ás veces coma ORG) -- corpus web lote 2
# (30/09/2026). O usuario decidiu seguir substituíndoas.
_INICIAIS_NOME_RE = r"(?:[A-ZÁÉÍÓÚÑÜ]\.[ \t]?){1,4}[A-ZÁÉÍÓÚÑÜ]\.(?!\w)"
_HONORIFICO_PERSOA = re.compile(
    # "Sr."/"Sra." tamén (fuga real: "La Sra. García López pregunta" quedaba
    # á vista); aí o nome ten que comezar por palabra do INE ("Sr.
    # Presidente" non é ninguén), ver `_detectar_persoas_por_honorifico`.
    r"\b(?P<trat>" + _HONORIFICO_RE + r"|Sr\.|Sra\.|Srta\.)\s+"
    r"(?P<nome>" + _INICIAIS_NOME_RE + r"|" + _PALABRA_CAPITALIZADA_RE
    + r"(?:\s+(?:" + _CONECTOR_NOME_RE + r"\s+){0,2}(?:" + _PALABRA_CAPITALIZADA_RE
    # Inicial no medio ("don Pedro J. Benito Fuertes": o "J." cortaba o
    # nome en dous códigos e quedaba á vista). Nunca "D.", que é o tratamento
    # da seguinte persoa nunha lista sen comas.
    + r"|(?!D\.)[A-ZÁÉÍÓÚÑÜ]\.(?=[ \t]+[A-ZÁÉÍÓÚÑÜ]))){0,4})"
)

# Cargo pegado ao nome SEN coma ("doña X Y Z Secretaria General del
# Consorcio", "don X Y Z Alcalde-Presidente del Ayuntamiento de..."): o
# patrón de arriba arrastraba o cargo dentro do nome e despois
# `_quitar_organismos` tiraba o anaco ENTEIRO -- o nome quedaba á vista
# (caso real do corpus web, 28/09/2026). O nome córtase na primeira
# palabra de cargo; o cargo non é dato persoal e queda visible.
_CARGO_TRAS_NOME_RE = re.compile(
    r"\s+(?:(?:Sub|Vice)(?:secretari[oa]|president[ea]|director[a]?|consejer[oa]|conselleir[oa]|delegad[oa]|"
    r"rector[a]?|decan[oa])|"  # "La Vicepresidenta Segunda" (BOE-A-2026-12358)
    r"(?:Sub|Vice)?(?:secretari[oa]|Secretari[oa]|Alcalde(?:sa)?|President[ea]|Director[a]?|"
    r"Conseller[oa]?|Conselleir[oa]|Consejer[oa]|Delegad[oa]|Concejal[a]?|Concelleir[oa]|"
    r"Teniente|Tenente|Jef[ea]|Xef[ea]|Gerente|Xerente|Rector[a]?|Decan[oa]|Diputad[oa]|"
    r"Deputad[oa]|Ministr[oa]|Interventor[a]?|Tesorer[oa]|Tesoureir[oa]|Coordinador[a]?|"
    r"Catedr[aá]tic[oa]|Profesor[a]?|Titular|Responsable|Portavoz|General|Xeral))"
    r"(?![a-záéíóúñü])"
)


_MUNICIPIOS_CON_TRATAMENTO = {"don benito", "doña mencía", "doña mencia", "dona mencía"}

# Nome dunha vivenda rural: "Casería Don Gabriel", "Molino\nde Don Francisco
# Alcalá" (BOE-A-2025-3685, vivendas na contorna dunha planta solar; o usuario,
# revisión do lote 5: non son persoas). Só co tipo de inmoble en MAIÚSCULA (nome
# propio) e "Don/Doña" tamén: "la casería de don X" segue sendo unha persoa.
_INMOBLE_ANTES_DE_TRATAMENTO_RE = re.compile(
    r"(?<![\w])(?:Caser[ií]as?|Caser[ií]os?|Cortijos?|Cortijadas?|Molinos?|Fincas?|Haciendas?|Fazendas?|"
    r"Pazos?|Quintas?|Granjas?|Mas[ií]as?|Masos?|Ventas?|Huertas?|Hortas?|Dehesas?)"
    r"\s+(?:(?:de|del|da|do)\s+)?\Z"
)


@lru_cache(maxsize=1)
def _cargo_exento_tras_nome_re():
    # `_CARGOS_EXENTOS_RE` defínese máis abaixo no módulo.
    return re.compile(r"\s+(?=" + _CARGOS_EXENTOS_RE.replace(r"\b(?:", "(?:", 1) + r")", re.IGNORECASE)


def _detectar_persoas_por_honorifico(texto: str, texto_suavizado: str, ocupado: list) -> list:
    """`texto_suavizado` (Title Case + ordinais normalizados, coma o que
    recibe spaCy) é o que se busca -- NON o texto orixinal directamente --
    porque en documentos TODO EN MAIÚSCULAS o patrón non tería forma de
    distinguir "CON"/"NIF" (palabras funcionais) dun apelido real; a
    suavización xa fai exactamente esa distinción (`_PALABRAS_FUNCIONAIS`).
    O texto devolto en cada entidade tómase sempre do ORIXINAL."""
    atopadas = []
    for match in _HONORIFICO_PERSOA.finditer(texto_suavizado):
        inicio, fin = match.span("nome")
        # Municipios que empezan por un tratamiento ("DON BENITO" na columna
        # Localidade, BOE-A-2026-12310): "Don Benito" só, sen apelidos.
        if " ".join(match.group().lower().split()) in _MUNICIPIOS_CON_TRATAMENTO:
            continue
        if match.group("trat")[0] == "D" and _INMOBLE_ANTES_DE_TRATAMENTO_RE.search(
                texto_suavizado, max(0, match.start() - 40), match.start()):
            for i in range(match.start(), fin):
                ocupado[i] = True  # que spaCy non o colla despois coma persoa
            continue
        # "D." solto é ambiguo ("D. Foral" na cabeceira dunha táboa,
        # BOE-A-2026-12309): coma "Sr.", o nome ten que empezar por palabra do INE.
        if (match.group("trat").startswith("Sr") or match.group("trat") == "D.") \
                and _tramo_sen_ine(match.group("nome").split()[0]):
            continue
        cargo = _CARGO_TRAS_NOME_RE.search(texto_suavizado, inicio, fin)
        if cargo:
            fin = cargo.start()
        # Cargo exento pegado SEN coma ("doña X Letrada de la Administración de
        # Justicia"): córtase igual ca coa coma, e a exención (criterio CENDOJ:
        # xuíces, maxistrados e LAJ vense) aplícase despois. Decisión do usuario 01/10/2026.
        exento = _cargo_exento_tras_nome_re().search(texto_suavizado, inicio, min(len(texto_suavizado), fin + 60))
        if exento and exento.start() < fin:
            fin = exento.start()
        if any(ocupado[inicio:fin]):
            continue
        # `\s+` pode cruzar liña (apelido partido por axuste de marxe), pero
        # a entidade NUNCA: pártese e descártase o anaco que sexa unha
        # etiqueta da liña seguinte ("D. Xoán Páez Veiga\nJuez: D. ...").
        atopadas.extend(_partir_persoa_por_linas(
            Entidade(inicio, fin, texto[inicio:fin], "PERSOA"), texto, texto_suavizado
        ))
    return atopadas


# Tres ou catro iniciais soltas, sen tratamento ("con la firma de «A. C.
# G.»", BOE-A-2026-14304): só así, con espazos, e nunca unha forma xurídica.
_TRES_INICIAIS_RE = re.compile(r"(?<![\w.])(?:[A-ZÁÉÍÓÚÑ]\.[ \t]){2,3}[A-ZÁÉÍÓÚÑ]\.(?![\w])")
_SIGLAS_NON_PERSOA = {"SAU", "SLU", "SLP", "EPE", "SCP", "SAL", "SLL"}


_MARIA_ABREVIADA_RE = re.compile(
    r"(?<![\w.])(M[ \t]?\.?[ \t]?ª\.?|Ma\.)[ \t]+((?:(?:del|de la|de los|de las|de)[ \t]+)?"
    r"[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:[ \t]+(?:(?:de|del|de la)[ \t]+)?[A-ZÁÉÍÓÚÑ][a-záéíóúñ'-]+){1,4})")


def _maria_abreviada(texto: str, ocupado: list) -> list:
    """"M.ª del Carmen Berrocal Gil (No se dispone de DNI válido)" nunha listaxe
    (BOE-B-2025-42645, FUGA vista comparando versións, 04/10/2026): spaCy fundíao
    coa liña anterior coma organización. "M.ª"/"Mª" + nome + polo menos un
    apelido do INE na mesma liña é unha persoa."""
    apelidos = nomes_ine.apelidos()
    atopadas = []
    for m in _MARIA_ABREVIADA_RE.finditer(texto):
        palabras = [p for p in m.group(2).split() if p.lower() not in _PARTICULAS_APELIDO]
        if len(palabras) < 2 or any(ocupado[m.start():m.end()]) or _e_organismo(m.group(2)):
            continue
        if not any(apelidos.get(nomes_ine.normalizar(p), 0) >= 100 for p in palabras[1:]):
            continue
        atopadas.append(Entidade(m.start(), m.end(), m.group(), "PERSOA"))
    return atopadas


def _iniciais_soltas(texto: str, ocupado: list) -> list:
    atopadas = []
    for m in _TRES_INICIAIS_RE.finditer(texto):
        if any(ocupado[m.start():m.end()]) or re.sub(r"[.\s]", "", m.group()) in _SIGLAS_NON_PERSOA:
            continue
        atopadas.append(Entidade(m.start(), m.end(), m.group(), "PERSOA"))
    return atopadas


def _outras_aparicions_de_iniciais(entidades: list, texto: str, ocupado: list) -> list:
    """Iniciais xa detectadas tras un tratamento ("don B. L. S.") en CADA
    outra aparición, con ou sen tratamento e con ou sen espazos ("B.L.S."):
    senón quedaban á vista as aparicións que spaCy non vía."""
    atopadas = []
    letras = {
        tuple(re.findall(r"[^\W\d_]", e.texto))
        for e in entidades
        if e.etiqueta == "PERSOA" and re.fullmatch(_INICIAIS_NOME_RE, e.texto)
    }
    for secuencia in letras:
        patron = re.compile(
            r"(?<![\w.])" + r"[ \t]?".join(re.escape(l) + r"\." for l in secuencia) + r"(?!\w)"
        )
        for m in patron.finditer(texto):
            if not any(ocupado[m.start():m.end()]):
                atopadas.append(Entidade(m.start(), m.end(), m.group(), "PERSOA"))
    return atopadas


# Segundo recoñecedor de reserva: unha persoa introducida polo seu NOME
# (sen honorífico) directamente seguido de ", profesión" -- moi habitual
# no bloque de sinatura dun informe técnico ("Leandro M. del Valle Resua,
# arquitecto colegiado nº..."). Caso real que o motivou: unha epígrafe en
# maiúsculas repetindo o mesmo nome XUSTO ENRIBA ("LEANDRO DEL VALLE RESUA
# ARQUITECTO") facía que o modelo etiquetase a liña de sinatura enteira
# coma LOC, non PER -- nin sequera quedaba un anaco parcial coma "Leandro"
# para que `_estender_entidade_persoa` puidese arranxar. Reutiliza
# `_UNIDADE_CONTINUACION_RE` (inclúe iniciais soltas coma "M.") para poder
# cubrir exactamente ese caso.
#
# A MAIORES, a diferenza de `_UNIDADE_CONTINUACION_RE` (que NON permite
# unha palabra con maiúscula solta sen conector diante, para non fundir
# varias persoas nunha lista honorífica -- ver comentario de arriba desa
# constante), aquí SI se permite: este patrón vai sempre ANCORADO por
# ", profesión" xusto despois, así que non hai risco de estenderse a
# outra persoa da mesma frase (pararía no primeiro "," que non vaia
# seguido dunha profesión coñecida). Sen isto, un apelido composto SEN
# conector (ex. "Veiga Lucas") quedaba fóra do nome -- caso real:
# "Xoana Veiga Lucas, secretaria da comunidade..." só detectaba
# "Lorenzo" (a última palabra antes da coma), e ese anaco parcial quedaba
# "ocupado", bloqueando a spaCy de detectar despois o nome completo.
_UNIDADE_CONTINUACION_PROFESION_RE = (
    r"(?:" + _UNIDADE_CONTINUACION_RE + r"|" + _PALABRA_CAPITALIZADA_RE + r")"
)
_PROFESIONS_RE = (
    r"(?:arquitect[oa]|aparejador[a]?|abogad[oa]|avogad[oa]|notari[oa]|"
    r"procurador[a]?|m[eé]dic[oa]|ingenier[oa]|enxe[ñn]eir[oa]|"
    r"colegiad[oa]|colexiad[oa]|registrador[a]?|secretari[oa]|president[ea])"
)
_PERSOA_ANTES_DE_PROFESION = re.compile(
    r"(?P<nome>" + _PALABRA_CAPITALIZADA_RE
    + r"(?:[ \t]+" + _UNIDADE_CONTINUACION_PROFESION_RE + r"){0,4}),[ \t]+" + _PROFESIONS_RE + r"\b"
)

# Variante SEN coma: a cabeceira/sinatura dun informe técnico moitas veces
# non usa coma ningunha entre o nome e a profesión, senón só espazo --
# visualmente adoita ser un aliñamento (nome á esquerda, profesión á
# dereita, moito espazo en branco de por medio na PÁXINA orixinal), pero
# ese espazo NON sobrevive á extracción: `_ensamblar_texto` (ver
# `pdf_estrutura.py`) recompón as palabras dunha liña cun ÚNICO espazo
# entre cada unha, así que "LEANDRO DEL VALLE RESUA
# ARQUITECTO" no PDF chega aquí coma "Leandro del Valle Resua arquitecto"
# (un espazo só) -- confirmado probando isto contra o documento REAL
# completo (un informe técnico de 43 páxinas), onde esta epígrafe se
# repite en TODAS as páxinas coma cabeceira e NINGUNHA se detectaba:
# spaCy nin sequera propuña "Leandro" coma PER nese contexto (rodeado do
# resto do informe, non illado), así que `_estender_entidade_persoa`
# nunca chegaba a activarse (proba illada equivalente en
# `test_estende_entidade_demasiado_curta_por_conector`, que SI funciona
# porque alí "Leandro" queda detectado por estar completamente só).
#
# Un só espazo coma separador é moito menos distintivo cá coma, así que
# esíxese POLO MENOS UNHA continuación (nunca un nome dunha soa palabra)
# para non confundir un título xenérico coma "Informe arquitecto" cun
# nome real -- un nome de pía solto antes da profesión é ambiguo de
# máis, pero un nome completo (2+ palabras) xa non.
_PERSOA_ANTES_DE_PROFESION_SEN_COMA = re.compile(
    r"(?P<nome>" + _PALABRA_CAPITALIZADA_RE
    + r"(?:[ \t]+" + _UNIDADE_CONTINUACION_PROFESION_RE + r"){1,4})[ \t]+" + _PROFESIONS_RE + r"\b"
)


def _detectar_persoas_por_profesion(texto: str, texto_suavizado: str, ocupado: list) -> list:
    """Mesmo principio ca `_detectar_persoas_por_honorifico`, pero ancorado
    por unha profesión/cargo despois do nome en vez dun tratamento
    honorífico diante."""
    atopadas = []
    matches = itertools.chain(
        _PERSOA_ANTES_DE_PROFESION.finditer(texto_suavizado),
        _PERSOA_ANTES_DE_PROFESION_SEN_COMA.finditer(texto_suavizado),
    )
    for match in matches:
        inicio, fin = match.span("nome")
        if any(ocupado[inicio:fin]):
            continue
        atopadas.append(Entidade(inicio, fin, texto[inicio:fin], "PERSOA"))
    return atopadas


# Terceiro recoñecedor de reserva: "APELIDOS, NOME" (orde invertida, coa
# coma no medio) -- o formato ESTÁNDAR en listaxes oficiais de persoal
# (BOE/DOG: nomeamentos, oposicións, rexistros...), onde cada fila amosa
# "Apellidos y nombre" xusto así. Caso real, moi grave: nunha listaxe do
# BOE con centos de persoas, spaCy detectaba SÓ UNHA das dúas metades de
# cada nome -- ora os apelidos ("Crespo Gonzalez"), ora o nome de pía
# ("Maria Amalia"), practicamente ao chou -- deixando SEMPRE a outra
# metade sen redactar, en texto plano, en TODAS as filas da táboa. Ao
# non ser un patrón que un modelo de linguaxe xeral recoñeza de forma
# fiable (a orde invertida e a coma confúndeno), cóbrese por patrón:
# calquera "racha de maiúsculas, racha de maiúsculas" convértese NUNHA
# SOA entidade PERSOA (apelidos + nome completo), nunca fusionando con
# texto arredor (as lookaround esixen que non haxa máis letras nin comas
# pegadas nin antes nin despois, así non se estende a un enderezo ou
# título/cargo veciño coma "Presidente, Xunta de Galicia").
#
# Palabra SÓ DE LETRAS (nunca díxitos): un apelido real nunca leva
# números, a diferenza dun código administrativo coma "A0590" (o corpo
# do NRP, ver `recognizers._NRP`) -- sen esta restrición, "A0590 Crespo
# Gonzalez" fundíase enteiro coma se "A0590" fose un apelido máis.
_PALABRA_NOME_PURO_RE = r"[A-ZÁÉÍÓÚÑÜ][a-zA-ZÁÉÍÓÚÑÜáéíóúñü'-]+"
# ata 2 conectores SEGUIDOS antes da primeira palabra real (non só 1):
# apelidos compostos coma "de la Fuente" ou "de los Santos" empezan por
# DOUS conectores en fileira, non un só (bug real atopado probando isto
# -- "DE LA FUENTE COBELA" perdía o "DE" inicial).
# Cada "unidade" acepta tamén unha inicial solta ("M.", segundo nome
# habitual -- caso real: "M. de la Medalla Milagrosa" coma nome de pía
# perdíase enteiro por empezar por inicial, non por unha palabra normal).
# "M.ª" (María) chega suavizado coma "M.a": "ABRISKETA CARBALLO, M.ª CARMEN"
# partíase en dous códigos (corpus web lote 2, 30/09/2026).
_NUCLEO_OU_INICIAL_RE = r"(?:[A-ZÁÉÍÓÚÑÜ]\.a(?![\w])|[A-ZÁÉÍÓÚÑÜ]\.|" + _PALABRA_NOME_PURO_RE + r")"
_UNIDADE_NOME_INVERSO_RE = (
    r"(?:" + _CONECTOR_NOME_RE + r"[ \t]+){0,2}" + _NUCLEO_OU_INICIAL_RE
)
_RACHA_NOME_INVERSO_RE = (
    _UNIDADE_NOME_INVERSO_RE + r"(?:[ \t]+" + _UNIDADE_NOME_INVERSO_RE + r"){0,3}"
)

# Cargos públicos exentos de anonimización (ver comentario completo máis
# abaixo, sección "Exención por cargo público"). Definido AQUÍ (antes do
# seu primeiro uso real) porque este mesmo recoñecedor de "Apelidos, Nome"
# precisa dun lookahead negativo con el: sen el, un bloque de sinatura
# coma "María Lozano Veiga, Letrada de la Administración de Justicia"
# confundíase coa listaxe BOE e fundíase todo nunha soa entidade que xa
# non casaba coa exención (caso real atopado probando este mesmo arranxo).
_CARGOS_EXENTOS_RE = (
    r"\b(?:"
    r"maxistrad[oa]-xu[íi]z[a]?|magistrad[oa]-juez[a]?"
    r"|xu[íi]z-maxistrad[oa]|juez-magistrad[oa]"
    r"|maxistrad[oa]|magistrad[oa]"
    r"|xu[íi]z[a]?|juez[a]?"
    r"|letrad[oa]\s+da\s+Administraci[oó]n\s+de\s+Xustiza"
    r"|letrad[oa]\s+de\s+la\s+Administraci[oó]n\s+de\s+Justicia"
    r"|LAJ"
    r"|secretari[oa]\s+xudicial|secretari[oa]\s+judicial"
    r"|m[eé]dic[oa]\s+forense"
    r")\b"
)

_APELIDOS_NOME_INVERSO = re.compile(
    r"(?<![\w,])"
    r"(?P<apelidos>" + _RACHA_NOME_INVERSO_RE + r"),[ \t]+"
    # (?i:...) -- flag `i` SÓ dentro deste anaco: o resto do patrón segue
    # a depender de esixir MAIÚSCULA inicial (case-sensitive) para
    # distinguir un nome propio de prosa normal; só o cargo (que xa ven
    # cunha palabra completa, non unha letra solta) pode ser insensible.
    r"(?!(?i:" + _CARGOS_EXENTOS_RE + r"))"
    r"(?P<nome>" + _RACHA_NOME_INVERSO_RE + r")"
    r"(?![\w,])"
)

# Mesma listaxe "Apelidos, Nome", pero coa cela partida en DÚAS liñas
# (táboas do BOE en PDF, caso real do corpus web 28/09/2026): o salto vai
# despois da coma ("RODRIGUEZ LORENZO,\nGUILLERMO.") ou dentro dos apelidos
# tras un conector ("SALAS ROMERO DE LA\nRIVA, FEDERICO."). O patrón
# dunha soa liña só collía o anaco da segunda liña (ou nada, se a primeira
# era un só apelido: "OTERO,\nANTÍA.") e os apelidos quedaban á vista.
# Para non confundilo con prosa partida ao chou, esíxese forma de cela:
# empeza a principio de liña e o nome remata a liña (cun punto opcional).
_APELIDOS_NOME_INVERSO_DUAS_LINAS = re.compile(
    r"(?m)^[ \t]*"
    r"(?P<apelidos>" + _RACHA_NOME_INVERSO_RE
    # salto dentro dos apelidos, tras un conector ou non ("CABAÑAS\nGALAN,\n
    # CELIA.": a cela ocupa tres liñas, caso real do mesmo corpus)
    + r"(?:(?:[ \t]+" + _CONECTOR_NOME_RE + r"(?:[ \t]+" + _CONECTOR_NOME_RE + r")?)?"
    + r"[ \t]*\n[ \t]*" + _RACHA_NOME_INVERSO_RE + r")?"
    r"),(?:[ \t]*\n)?[ \t]*"
    r"(?!(?i:" + _CARGOS_EXENTOS_RE + r"))"
    r"(?P<nome>" + _RACHA_NOME_INVERSO_RE + r")"
    r"\.?[ \t]*$"
)


# Sinal de que o que casa coma "Apelidos, Nome" en realidade continúa
# unha ENUMERACIÓN de varias persoas distintas ("..., e Ana Salcedo Roel")
# -- bug real (A14): "Comparecen Xoán Páez Veiga, María Lozano Duarte e
# Ana Salcedo Roel" lía "Xoán Páez Veiga" coma apelidos e "María Lozano
# Duarte" coma nome DUNHA SOA persoa, fundindo dúas persoas distintas
# nunha soa entidade (e roubándolle a spaCy a súa detección correcta, xa
# que este recoñecedor corre ANTES e marca o tramo coma "ocupado"). Nunha
# listaxe real "Apelidos, Nome" a fila remata en DNI/números, nunca en
# "e/y + outro nome" -- sinal fiable para distinguir os dous casos.
#
# A propósito NON vai coma lookahead dentro do propio `_APELIDOS_NOME_
# INVERSO`: un lookahead negativo despois dun grupo repetitivo GREEDY
# (`nome`, ata 4 unidades) só fai que o motor de regex probe versións
# MÁIS CURTAS de "nome" ata atopar unha que evada o lookahead (aquí:
# "María López" en vez de "María Lozano Duarte"), sen chegar a rexeitar o
# match -- bug real atopado implementando este mesmo arranxo. Compróbase
# á parte, DESPOIS de ter xa o match completo (greedy, sen recortar).
_ENUMERACION_PERSOAS_RE = re.compile(
    r",?[ \t]+(?:e|y)[ \t]+" + _RACHA_NOME_INVERSO_RE
)


# Nunha listaxe real do BOE os "apelidos" adoitan ser 1 ou 2 palabras
# (ver `test_risco_residual.py`), así que non abonda con esixir sempre 2+
# palabras. Pero unha SOA palabra é ambigua: tamén é exactamente a forma
# dun advervio/conector discursivo NORMAL a inicio de frase ("Despois,",
# "Logo,", "Finalmente,"...) seguido dunha coma calquera -- caso real
# atopado probando isto: "Despois, Xoana Veiga Lucas, veciña de
# Vigo..." confundíase coma se "Despois" fose o apelido dunha listaxe,
# fundíndoo co nome real que viña despois ("Despois, Xoana Vázquez").
# Nunha listaxe oficial real cada fila non é unha frase gramatical
# completa (non hai suxeito nin verbo antes da coma), así que se a "soa
# palabra" está xusto a inicio de frase (inicio do texto, ou despois de
# ".", "!" ou "?" e espazo) case seguro NON é un apelido, senón unha
# palabra de prosa normal -- descártase para deixar que spaCy detecte o
# nome real coma persoa normal (sen a orde invertida).
_INICIO_DE_FRASE_RE = re.compile(r"[.!?]\s+\Z")


def _apelido_unico_a_inicio_de_frase(texto_suavizado: str, inicio: int, apelidos: str) -> bool:
    if " " in apelidos or "\t" in apelidos:
        return False
    # Listaxe con documento na liña seguinte ("Biedermann, Anna Maria.\nNIE:
    # ****3376*.", BOE-A-2026-7914): é unha persoa, non "Despois, ...".
    if re.match(r"[^\n]*\n[ \t]*(?:DNI|NIE|NIF|Pasaporte)\b", texto_suavizado[inicio:], re.IGNORECASE):
        return False
    prefixo = texto_suavizado[:inicio]
    return prefixo == "" or bool(_INICIO_DE_FRASE_RE.search(prefixo))


# Ministerios e consellerías enumeran as súas áreas coma "Ministerio de
# Educación, Formación Profesional y Deportes" ou "Consellería de Emprego,
# Comercio e Emigración" -- cada área separada por comas, exactamente coma
# unha enumeración de persoas ("Apelidos, Nome"). Caso real do corpus web
# (28/09/2026): "Educación, Formación Profesional" e "Ciencia, Innovación"
# detectábanse coma persoa porque ningunha das dúas palabras é en si mesma
# un organismo (ver `_ORGANISMOS_RE`) -- unha lista pechada de "palabras
# de área ministerial" sería fráxil (medicina, cultura, industria... cada
# unha podería ser tamén un apelido real noutro contexto). O que SI é
# fiable é o INTRODUTOR xusto antes: se hai "Ministerio/Consellería/
# Consejería/Departamento de" a non máis de varias palabras enumeradas de
# distancia (só palabras con maiúscula, comas e "e"/"y" entre medias,
# nunca prosa nin verbo), todo o tramo é o NOME do departamento, non unha
# persoa.
# Tamén o CARGO que leva o nome do departamento ("La Ministra de Vivienda y
# Agenda Urbana, Isabel Ramírez Galán", BOE-A-2025-6472, revisión do lote 5):
# "Agenda Urbana" líase coma os apelidos e tapábase co nome nun só anaco. En
# minúscula tamén ("A conselleira de Política Social, ..."): `(?i:...)` só aquí.
_ORGANISMO_INTRODUTOR_RE = (
    r"(?:Ministerio|Minist[eé]rio|Consell(?:er[ií]a|eiro|eira)|Consejer[ií]a|Departamento|"
    r"Direcci[oó]n(?:\s+(?:Xeral|General))?|Subdirecci[oó]n(?:\s+(?:Xeral|General))?|"
    r"Secretar[ií]a(?:\s+(?:Xeral|General|de\s+Estado))?|Subsecretar[ií]a|"
    r"(?i:(?:vice)?ministr[oa]|(?:vice)?consejer[oa]|(?:vice)?conselleir[oa]|(?:sub)?secretari[oa]"
    r"(?:\s+(?:xeral|general|de\s+estado))?|(?:sub)?director[a]?(?:\s+(?:xeral|general))?))\s+(?:de|do|da|del|dos|das)\s*"
)
_ENUMERACION_TRAS_ORGANISMO_RE = re.compile(
    r"(?:" + _ORGANISMO_INTRODUTOR_RE + r")"
    r"(?:[ \t\n]*(?:" + _PALABRA_CAPITALIZADA_RE + r"|,|e|y))*[ \t\n]*\Z"
)


def _enumeracion_de_organismo(texto_suavizado: str, inicio: int) -> bool:
    ventá = texto_suavizado[max(0, inicio - 160):inicio]
    return bool(_ENUMERACION_TRAS_ORGANISMO_RE.search(ventá))


_RESTO_DO_NOME_NA_LIÑA_SEGUINTE_RE = re.compile(r"[ \t]*\n[ \t]*(" + _RACHA_NOME_INVERSO_RE + r")")


def _persoa_tras_cargo_con_coma(texto: str, texto_suavizado: str, match) -> "Entidade | None":
    """"La Ministra de Vivienda y Agenda Urbana, Begoña\nMarín Sabucedo": descartado
    o "Apelidos, Nome", o que vai tras a coma é o nome de quen asina. Só se empeza
    por un nome de pía do INE; se a liña remata nel e os apelidos van na seguinte,
    xúntanse (spaCy non sempre o detecta: "Isabel\nRamírez" si, "Begoña\n..." non)."""
    inicio, fin = match.span("nome")
    if nomes_ine.normalizar(match.group("nome").split()[0]) not in nomes_ine.nomes():
        return None
    resto = _RESTO_DO_NOME_NA_LIÑA_SEGUINTE_RE.match(texto_suavizado, fin)
    if resto and _continua_na_liña_seguinte(Entidade(inicio, fin, texto[inicio:fin], "PERSOA"),
                                            texto_suavizado, resto.start(1), resto.end(1)):
        return Entidade(inicio, resto.end(1), texto[inicio:resto.end(1)], "PERSOA", multilinea=True)
    return Entidade(inicio, fin, texto[inicio:fin], "PERSOA")


# Cargo dunha comisión diante de "Apelidos, Nome" ("Presidente Lamela Pedrón, Manuel", "1ª Vogal
# Taboada Iglesias, María Jesús"): non é un apelido. Entraba no anaco e o recorte do cargo
# levábao enteiro: FUGA (o nome á vista enteiro ou só cos apelidos), lote 5 sen ver.
_CARGO_DE_COMISION_DIANTE_RE = re.compile(
    r"(?:\d+[ºª]?\.?[ \t]+)?(?i:presidente|presidenta|secretari[oa]|vogal|vocal)"
    # despois, un apelido con maiúscula: nunca "Presidente de la CNMV, Nome" (cargo dun organismo)
    # nin un calificativo do cargo ("Secretario Provincial, Manuel ...", BOE-B-2025-14097)
    r"(?:[ \t]+(?i:suplente|titular))?[ \t]+(?=[A-ZÁÉÍÓÚÑÜ])"
    r"(?!(?i:provincial|general|xeral|territorial|t[eé]cnic[oa]|municipal|auton[oó]mic[oa]|judicial|xudicial|"
    r"ejecutiv[oa]|executiv[oa]|primer[oa]?|segund[oa]|adjunt[oa]|adxunt[oa])\b)")


# Profesión pegada ao nome na mesma liña da comisión ("Salcedo Roel, Ana Profesor titular de ..."):
# o patrón metíaa no nome e tapábase.
_PROFESION_TRAS_NOME_RE = re.compile(
    r"[ \t]+(?:Catedr[aá]tic[oa](?:/a)?|Profesor(?:a|/a)?|Contratad[oa](?:/a)?|Asociad[oa](?:/a)?|Axudante|Ayudante|"
    r"Investigador(?:a|/a)?|Doutor(?:a|/a)?|Doctor(?:a|/a)?)(?![\w])")


def _sen_profesion(match, fin: int) -> int:
    """Fin da persoa sen a profesión que o patrón metera no nome."""
    profesion = _PROFESION_TRAS_NOME_RE.search(match.string, match.start("nome"), fin)
    return profesion.start() if profesion else fin


def _sen_cargo_de_comision(match, inicio: int) -> int:
    """Inicio da persoa sen o cargo de comisión que o patrón metera nos apelidos: ao
    principio, ou ao principio dunha liña (a variante de dúas liñas colle tamén a liña
    anterior: "Universidade de Santiago\nSecretario Páez Veiga, Xoán Carlos")."""
    apelidos = match.group("apelidos")
    fin_cargo = None
    for comezo in [0] + [m.end() for m in re.finditer(r"\n[ \t]*", apelidos)]:
        cargo = _CARGO_DE_COMISION_DIANTE_RE.match(apelidos, comezo)
        if cargo:
            fin_cargo = cargo.end()
    return inicio + fin_cargo if fin_cargo is not None else inicio


_ARTIGOS_DETRAS = frozenset("A O AS OS LA EL LOS LAS".split())


def _municipio_co_artigo_detras(match) -> bool:
    """"Coruña, A.", "Porriño, O." (BOE-A-2024-1230, lote 6): municipio oficial co artigo
    detrás, coma nas listaxes de xulgados; non "Apelidos, Nome"."""
    from . import lugares_oficiais
    # Só a primeira palabra: detrás pode vir a provincia ("Porriño, O. Pontevedra").
    artigo = match.group("nome").split()[0].rstrip(".").upper()
    if artigo not in _ARTIGOS_DETRAS:
        return False
    # "Tramitación P.A. Coruña, A.": a "A." de "P.A." entra no anaco coma se fose unha inicial.
    lugar = re.sub(r"^(?:[A-ZÁÉÍÓÚÑ]\.[ \t]*)+", "", match.group("apelidos"))
    return lugares_oficiais.normalizar_lugar(f"{artigo} {lugar}") in lugares_oficiais.lugares()


def _detectar_persoas_apelidos_nome_inverso(texto: str, texto_suavizado: str, ocupado: list) -> list:
    atopadas = []
    # Primeiro a cela partida en dúas liñas (ver
    # `_APELIDOS_NOME_INVERSO_DUAS_LINAS`): se correse despois, o patrón
    # dunha soa liña xa tería ocupado o anaco da segunda ("Rubia, Federico")
    # e os apelidos da primeira quedarían fóra.
    for match in _APELIDOS_NOME_INVERSO_DUAS_LINAS.finditer(texto_suavizado):
        inicio, fin = match.start("apelidos"), match.end("nome")
        inicio = _sen_cargo_de_comision(match, inicio)
        fin = _sen_profesion(match, fin)
        # Tamén a cela nunha liña pero sen espazo tras a coma ("Sobrado
        # Deza,Tamara", DOG, corpus web lote 2): o patrón dunha liña esixe
        # espazo e partíaa en dous códigos.
        multilinea = "\n" in texto_suavizado[inicio:fin]
        if not (multilinea or re.search(r",[^\W\d_]", texto_suavizado[inicio:fin])) or any(ocupado[inicio:fin]):
            continue
        if _enumeracion_de_organismo(texto_suavizado, inicio):
            continue
        atopadas.append(Entidade(inicio, fin, texto[inicio:fin], "PERSOA", multilinea=multilinea))
        for i in range(inicio, fin):
            ocupado[i] = True
    for match in _APELIDOS_NOME_INVERSO.finditer(texto_suavizado):
        inicio, fin = match.start("apelidos"), match.end("nome")
        inicio = _sen_cargo_de_comision(match, inicio)
        fin = _sen_profesion(match, fin)
        if _municipio_co_artigo_detras(match):
            for i in range(inicio, fin):
                ocupado[i] = True  # que spaCy non o colla despois coma persoa
            continue
        if _enumeracion_de_organismo(texto_suavizado, inicio):
            persoa = _persoa_tras_cargo_con_coma(texto, texto_suavizado, match)
            if persoa is not None and not any(ocupado[persoa.inicio:persoa.fin]):
                atopadas.append(persoa)
                for i in range(persoa.inicio, persoa.fin):
                    ocupado[i] = True
            continue
        if _ENUMERACION_PERSOAS_RE.match(texto_suavizado, fin):
            # Non é UNHA persoa "Apelidos, Nome" -- é a primeira metade
            # dunha enumeración de varias persoas distintas (ver
            # `_ENUMERACION_PERSOAS_RE`). Non se marca nada coma ocupado:
            # déixase o tramo enteiro LIBRE para que spaCy detecte cada
            # persoa por separado.
            continue
        if _apelido_unico_a_inicio_de_frase(texto_suavizado, inicio, match.group("apelidos")):
            # A propia palabra solta ("Despois"...) confunde tamén a spaCy
            # (detéctaa coma persoa por si soa, pola mesma forma ambigua
            # "Palabra,") -- márcase coma ocupada para que non se cole
            # despois coma entidade á parte, pero sen tocar o resto do
            # match (o nome real, que ten que quedar LIBRE para que spaCy
            # o detecte coma persoa normal).
            for i in range(inicio, match.end("apelidos")):
                ocupado[i] = True
            continue
        if any(ocupado[inicio:fin]):
            continue
        atopadas.append(Entidade(inicio, fin, texto[inicio:fin], "PERSOA"))
    return atopadas


# Cando o cargo vai ANTES do nome, entre el e o nome só pode haber
# artigos/títulos honoríficos coñecidos ("Ilmo. Sr. Magistrado D. Xoán...")
# -- nunca outra prosa, ou calquera frase anterior que casualmente
# mencione un cargo público arrastraría un nome non relacionado.
#
# A propósito NON inclúe "o"/"a": o artigo galego vai DIANTE do cargo ("o
# xuíz D. X", "a maxistrada Dª X"), nunca entre o cargo e o nome; nesa
# posición "a" é a PREPOSICIÓN (castelán e galego) e o nome é o doutra
# persoa -- bug real: "el Magistrado a D. Xoán Páez Veiga le impuso
# una multa" ou "notificada por la jueza a la Sra. María Lozano Duarte"
# deixaban ao multado/notificado SEN anonimizar, coma se fose o xuíz.
_ARTIGO_TITULO_RE = (
    r"(?:el|la|lo|los|las"
    r"|Ilmo\.?|Ilma\.?|Iltmo\.?|Iltma\.?|Excmo\.?|Excma\.?|Sr\.?|Sra\.?)"
)
_CARGO_ANTES_RE = re.compile(
    _CARGOS_EXENTOS_RE
    # "D[ªa]": "Dª" solto (na copia suavizada xa é "Da"), que non forma
    # parte do nome (ver `_recortar_tratamentos`).
    # Un salto de liña pode ir entre o cargo e o tratamento ("la Magistrada\n
    # doña X", BOE-A-2026-623): o título tapábaa e o corpo non.
    + r"(?:" + r"(?:[ \t]*\n[ \t]*|[ \t]+)" + _ARTIGO_TITULO_RE + r")*"
    + r"(?:(?:[ \t]*\n[ \t]*|[ \t]+)(?:" + _HONORIFICO_RE + r"|D[ªa]\.?))?[ \t]*\n?[ \t]*$",
    re.IGNORECASE,
)
# Cando o cargo vai DESPOIS do nome (bloque de sinatura: "Xoán Páez
# Veiga, Magistrado-Juez del Juzgado..."), abonda unha coma opcional.
#
# O cargo NON pode ir seguido de ":" -- entón é a ETIQUETA doutra persoa
# na liña seguinte ("Demandante: D. Xoán Páez Veiga\nJuez: D. Luis
# Salcedo Roel"), non o cargo de quen vai antes (bug real: ao non poder xa a
# entidade cruzar liñas, o demandante quedaba exento coma se fose o xuíz).
_CARGO_DESPOIS_RE = re.compile(
    r"^[ \t\n]*,?[ \t\n]*" + _CARGOS_EXENTOS_RE + r"(?![ \t]*:)",
    re.IGNORECASE,
)
_XANELA_CARGO = 90


def _cargo_publico_exento(texto_suavizado: str, inicio: int, fin: int):
    """Devolve o `Match` do cargo público exento atopado xusto antes ou
    despois da mención (nunca máis lonxe ca `_XANELA_CARGO` caracteres),
    ou `None` se non hai ningún -- ver comentario de `_CARGOS_EXENTOS_RE`."""
    antes = texto_suavizado[max(0, inicio - _XANELA_CARGO):inicio]
    match = _CARGO_ANTES_RE.search(antes)
    if match is not None:
        return match
    despois = texto_suavizado[fin:fin + _XANELA_CARGO]
    return _CARGO_DESPOIS_RE.match(despois)


# spaCy rexeita textos de máis de 1.000.000 de caracteres (nlp.max_length) --
# un documento técnico real (unha "memoria" de proxecto de 351 páxinas) xa
# superaba ese límite. En vez de tocar ese límite (o propio spaCy avisa de
# ata 1 GB de memoria temporal por cada 100.000 caracteres, inasumible nun
# "ordenador normal"), o texto trocéase en anacos moi por debaixo do
# límite, cortando SEMPRE por saltos de liña (nunca a media palabra nin a
# media frase) para non partir unha mención polo medio.
_TAMANO_MAXIMO_ANACO = 400_000


def _anacos_para_ner(texto: str) -> list:
    """Devolve unha lista de (inicio_global, anaco) que cobren `texto`
    enteiro sen solapamentos. Se `texto` xa é abondo curto, devolve un
    único anaco."""
    if len(texto) <= _TAMANO_MAXIMO_ANACO:
        return [(0, texto)]

    anacos = []
    inicio_anaco = 0
    ultimo_salto = None
    for cursor, caracter in enumerate(texto):
        if caracter == "\n":
            ultimo_salto = cursor
        if cursor - inicio_anaco >= _TAMANO_MAXIMO_ANACO:
            # corta no último salto de liña dispoñible; se non houbo
            # ningún dentro deste anaco (unha liña patoloxicamente longa),
            # corta igualmente aquí coma última reserva de seguridade.
            corte = ultimo_salto + 1 if ultimo_salto is not None and ultimo_salto >= inicio_anaco else cursor
            anacos.append((inicio_anaco, texto[inicio_anaco:corte]))
            inicio_anaco = corte
            ultimo_salto = None
    anacos.append((inicio_anaco, texto[inicio_anaco:]))
    return anacos


@lru_cache(maxsize=1)
def cargar_modelo():
    nlp = spacy.load(_MODELO)
    aviso = _comprobar_compatibilidade(nlp)
    if aviso:
        print(f"[AVISO] {aviso}", file=sys.stderr)
    return nlp


def _comprobar_compatibilidade(nlp) -> str | None:
    """Comproba que o modelo de idioma e a versión de spaCy instaladas se
    correspondan. NON é unha comprobación teórica: os paquetes de
    instalación levaron ata o 27/09/2026 o modelo 3.8.0 xunto con spaCy
    3.7.5, e con esa mestura o modelo detecta PEOR sen dar ningún erro --
    o programa instalado marcaba coma persoa o membrete "XUNTA DE GALICIA"
    que a copia de desenvolvemento (co modelo que lle corresponde) deixa
    intacto. spaCy só saca un `UserWarning` que nun programa de escritorio
    (sen consola) non ve ninguén, así que se expón tamén na interface."""
    esixido = nlp.meta.get("spacy_version")
    if not esixido:
        return None
    try:
        if spacy.util.is_compatible_version(spacy.about.__version__, esixido):
            return None
    except Exception:  # pragma: no cover -- formato inesperado na versión
        return None
    return (
        f"o modelo de idioma {_MODELO} {nlp.meta.get('version', '?')} precisa spaCy "
        f"{esixido}, pero está instalada a {spacy.about.__version__}: a detección de "
        "nomes empeora sen avisar (membretes marcados coma persoas, apelidos que se "
        "escapan). Reinstala o programa cun paquete no que as dúas versións se "
        "correspondan."
    )


def aviso_compatibilidade_modelo() -> str | None:
    """Mensaxe para a interface web, ou `None` se todo está en orde."""
    try:
        return _comprobar_compatibilidade(cargar_modelo())
    except Exception:  # pragma: no cover -- sen modelo instalado
        return None


# Traballa sobre o TEXTO (non tokens de spaCy) para non depender de como
# tokenice os espazos -- crítico porque spaCy tokeniza un espazo DOBRE
# (moi habitual no texto que sae de `page.get_text()` en columnas/táboas
# xustificadas dun PDF escaneado) coma un token propio, o que rompía por
# completo a versión anterior baseada en "mirar o seguinte token" (caso
# real: "Leandro  M.  del  Valle  Resua" nunha sinatura nunca se estendía
# máis alá de "Leandro"). `[ \t]+` (nunca `\s+`) impide que a EXTENSIÓN
# dunha entidade xa detectada por spaCy cruce a unha liña seguinte (ex.
# un enderezo despois dun salto de liña, caso real distinto atopado
# probando este mesmo arranxo).
_CONTINUACION_NOME_PERSOA = re.compile(
    r"(?:[ \t]+" + _UNIDADE_CONTINUACION_RE + r"){1,3}"
)


_PARTICULAS_APELIDO = _CONECTORES_NOME | {"der", "den", "di", "du", "le", "ten", "ter", "des", "d", "l"}
_MINUSCULAS_INICIAIS_RE = re.compile(r"(?:[a-záéíóúñü][\wáéíóúñü'’-]*[ \t]+)+")


def _estender_entidade_persoa(ent):
    """Caso oposto ao de `_recortar_entidade_persoa`: o modelo ás veces
    corta unha entidade PER DEMASIADO curta, deixando fóra apelidos que
    veñen despois (ex. detecta só "Leandro" en "Leandro del Valle Resua",
    nun bloque de sinatura real). Estende cara adiante mentres o texto
    siga o padrón de `_CONTINUACION_NOME_PERSOA` -- así nunca se estende
    cara a unha palabra allea coma un cargo ou profesión, que non
    encaixa nese padrón (non ten maiúscula inicial nin é unha inicial
    solta precedida de conector)."""
    doc = ent.doc
    match = _CONTINUACION_NOME_PERSOA.match(doc.text, ent.end_char)
    if not match:
        return ent
    span = doc.char_span(ent.start_char, match.end(), alignment_mode="expand")
    return span if span is not None else ent


def _recortar_entidade_persoa(ent, texto_orixinal: str):
    """O modelo ás veces esparexe unha entidade PER máis alá do nome (ex.
    "Xoana Veiga Lucas presentou" en vez de so "Xoana Veiga Lucas").
    Corrixe recortando polo final: mentres o último token non sexa un
    conector coñecido e non comece por maiúscula (as verbas e outras
    palabras que se coaron non levan maiúscula inicial en galego/castelán,
    a diferenza dos nomes propios -- comparación que se fai sobre a forma
    xa suavizada, non sobre o texto todo en maiúsculas), retírase. Devolve
    (inicio, fin, texto) tomando o texto SEMPRE do orixinal (para non
    devolver a forma en Title Case usada só para a detección), ou None se
    non queda nada recoñecible coma nome."""
    tokens = list(ent)
    fin_idx = len(tokens)
    while fin_idx > 0:
        tok = tokens[fin_idx - 1]
        if tok.text[:1].isupper() or tok.text.lower() in _CONECTORES_NOME:
            break
        fin_idx -= 1

    if fin_idx == 0:
        return None
    if fin_idx == len(tokens):
        return ent.start_char, ent.end_char, texto_orixinal[ent.start_char:ent.end_char]

    ultimo = tokens[fin_idx - 1]
    fin_char = ultimo.idx + len(ultimo.text)
    return ent.start_char, fin_char, texto_orixinal[ent.start_char:fin_char]


# --- Tratamentos soltos, extensión cara atrás e unión de tramos ------------
#
# spaCy adoita incluír o propio tratamento no span ("D. Xoán de la Fuente
# Pérez", "Sra. María Lozano Duarte") e ás veces devolve SÓ un tratamento ou
# un cargo coma se fose unha persoa (caso real: "Firma la LAJ a D. X" ->
# "LAJ" etiquetado PER e substituído por un pseudónimo). Recórtanse os
# tratamentos do principio/final do span e descártase a entidade se non
# queda ningunha palabra que poida ser un nome.
_TRATAMENTO_RE = (
    r"(?:" + _HONORIFICO_RE
    + r"|Sr\.?|Sra\.?|Srta\.?|Ilm[oa]\.?|Iltm[oa]\.?|Excm[oa]\.?|Dra?\.)"
)
_TRATAMENTOS_INICIAIS_RE = re.compile(r"(?:" + _TRATAMENTO_RE + r"\s+)+")
_TRATAMENTOS_FINAIS_RE = re.compile(r"(?:\s+" + _TRATAMENTO_RE + r")+\Z")
_SEN_NOME_RE = re.compile(
    r"(?:" + _TRATAMENTO_RE + r"(?!\w)|" + _CARGOS_EXENTOS_RE
    + r"|\b(?:el|la|lo|los|las|o|a)\b|[\s,.;:()\-'’/])*",
    re.IGNORECASE,
)


# "Dª"/"Dº" soltos (sen "D/"): mírase no texto ORIXINAL, porque na copia
# suavizada xa son "Da"/"Do" e confundiríanse cun apelido ("Da Silva").
_DA_ORDINAL_INICIAL_RE = re.compile(r"D[ªº]\.?\s+")


def _recortar_tratamentos(orixinal: str, suavizado: str, inicio: int, fin: int):
    """Devolve (inicio, fin) sen tratamentos nos extremos, ou None se o
    span non contén ningunha palabra de nome (só tratamentos/cargos)."""
    while True:
        m = _TRATAMENTOS_INICIAIS_RE.match(suavizado, inicio, fin) or _DA_ORDINAL_INICIAL_RE.match(orixinal, inicio, fin)
        if not m:
            break
        inicio = m.end()
    m = _TRATAMENTOS_FINAIS_RE.search(suavizado[inicio:fin])
    if m:
        fin = inicio + m.start()
    if fin <= inicio or _SEN_NOME_RE.fullmatch(suavizado[inicio:fin]):
        return None
    return inicio, fin


# Nomes de pía frecuentes (galego e castelán). Só se usan para decidir se
# unha palabra capitalizada A INICIO DE FRASE (ou que spaCy etiquetou coma
# lugar/organización) é o primeiro nome dunha persoa que spaCy deixou fóra
# da entidade -- caso real: "Informe Xosé Manuel Carballo Portela" ->
# "Informe Xosé PERSOA_000001". A inicio de frase non hai forma de
# distinguir só pola forma "Xosé" de "Informe" ou "Comparece", así que
# alí esíxese estar nesta lista; no medio da frase abonda con ser unha
# palabra capitalizada que non sexa unha palabra coñecida de prosa.
_NOMES_PIA = frozenset("""
xosé jose josé xoán xoan juan manuel antonio antón anton francisco xan xurxo
jorge luis lois carlos xavier javier jesús xesús jesus pedro pablo paulo
miguel ángel angel andrés andres ramón ramon alberto fernando david daniel
alejandro alexandre rafael sergio roberto ricardo enrique henrique vicente
santiago diego iago tomás tomas mario marcos martín martin rubén ruben adrián
adrian óscar oscar víctor victor raúl raul iván ivan hugo álvaro alvaro
gonzalo eduardo emilio alfonso afonso julio xulio agustín benito bieito
domingo gabriel ignacio joaquín xoaquín nicolás salvador félix rosendo
maría maria carmen ana isabel dolores pilar teresa rosa laura lucía lucia
marta cristina elena sara paula raquel beatriz patricia sonia silvia mónica
monica nuria rocío eva irene alba noelia sandra susana natalia montserrat
mercedes josefa xosefa concepción manuela rosario antonia francisca xoana
juana luisa margarita begoña inés ines sofía sofia carla uxía iria antía
sabela noa lara nerea ángela esther verónica lorena julia xulia olga emma
clara fátima encarnación remedios consuelo rosalía seán sean
""".split())

# Palabras capitalizadas de prosa xurídica que NUNCA se deben tomar por
# un nome ao estender cara atrás (encabezan resolucións, epígrafes...).
_PALABRAS_NON_NOME = frozenset("""
informe informes resolución resolucion sentencia sentenza auto autos
providencia decreto dilixencia diligencia escrito expediente recurso demanda
acta asinado asinada firmado firmada firma asina firman fdo don doña dona
señor señora señora sr sra comparece comparecen visto vistos vista
certificado certificación certificacion notificación notificacion oficio
despacho testemuña testigo demandante demandado demandada
lei ley leis leyes orgánica organica regulamento reglamento
presupuestos orzamentos generales xerais estado persoa persona persoas personas
só solo sólo prazo prazos concesión concesion nombrar nomear cesar aprobar autorizar
convocar resolver declarar ordenar publicar desestimar estimar dispoñer disponer acordar
solicitante solicitantes representante representantes nif nome nomes apelidos
custo custos solicitado solicitados dedicación dedicacion meses imputables imputable
categoría categoria compra leasing acrónimo acronimo actividade actividades importe
adquisición adquisicion data amortización amortizacion descrición descripcion detallada
total persoal personal propio propia contratación contratacion titulación titulacion
cotización cotizacion proxecto proyecto gastos indirectos equipamento equipo material
instrumental participación participacion información informacion conectividade
solucións solucions innovadoras grupo
publicouse publícase publicase publícanse aprobouse apróbase convócase resolveuse axenda agenda
labradío labradio secano regadío regadio pastos pastizal pinar olivar almendro maderable hidrografía
hidrografia vía via comunicación comunicacion paraje parajes canal granja espartizal
catedrático catedrática catedraticos catedráticos catedráticas catedratico catedratica
orden orde ordes órdenes ordenes
lares penates linde lindes lindeiro lindeiros lindero linderos
tasa cuadro gasto medir planes plan umbral eje choque objetivo específico especifico
lingua cando pola área area formación formacion cualificacións cualificacions programas
plans estilos vida saudables justicia xustiza pág pag fides país pais
pesca ganadería ganaderia gandaría gandaria alimentación alimentacion agricultura industria comercio
fundamentos derecho dereito arrendamientos urbanos rústicos rusticos
turismo deporte deportes escalada vivienda sanidad sanidade educación educacion economía economia hacienda facenda empleo emprego
""".split())
# ^ Corpus web (29/09/2026): spaCy (modelo castelán) toma o galego "Lei"
# por un nome ("da Lei 39/2015" -> "da PERSOA_... 39/2015"), e tamén
# "Presupuestos Generales del Estado" ou o rótulo "Persoa interesada".
# Só se descarta a entidade se TODAS as súas palabras están aquí: "Lei
# Wang" segue sendo unha persoa.

# Cuarto recoñecedor de reserva: nomes escritos INTEGRAMENTE en
# minúscula (sen maiúscula inicial ningunha) -- caso real de revisión:
# unha acta transcrita a man ("comparece xosé manuel castro pereira, con
# domicilio en...") non ten forma ningunha que a distinga de prosa
# normal, nin para spaCy nin para ningún dos patróns de arriba (todos
# esixen maiúscula inicial en polo menos un punto, coma o resto do
# módulo xustifica -- ver `_PALABRA_MAIUSCULA_OU_CAPITALIZADA` en
# `risco_residual.py`, mesmo motivo). Sen NINGÚN sinal de maiúscula,
# recoñecer un nome a partir só da súa FORMA sería indistinguible de
# calquera racha de palabras en minúscula -- así que se esixen DOUS
# anclaxes á vez, non un só: (a) un verbo introdutorio típico dunha
# comparecencia/sinatura xurídica xusto antes, e (b) que a PRIMEIRA
# palabra do suposto nome sexa un nome de pía coñecido (`_NOMES_PIA`).
_VERBO_INTRODUTOR_PERSOA_RE = (
    r"comparece[n]?|manifiesta[n]?|declara[n]?|expone[n]?|solicita[n]?|"
    r"suscribe[n]?|firma[n]?|asina[n]?|certifica[n]?"
)
_NOME_PIA_MINUSCULA_RE = "|".join(re.escape(nome) for nome in sorted(_NOMES_PIA, key=len, reverse=True))
_PALABRA_MINUSCULA_RE = r"[a-záéíóúñ][a-záéíóúñ'-]*"
_PERSOA_MINUSCULA_TRAS_VERBO = re.compile(
    r"\b(?i:" + _VERBO_INTRODUTOR_PERSOA_RE + r")[ \t]+"
    r"(?P<nome>(?:" + _NOME_PIA_MINUSCULA_RE + r")(?:[ \t]+" + _PALABRA_MINUSCULA_RE + r"){1,3})"
    r"(?![a-záéíóúñ])"
)


def _detectar_persoas_minusculas(texto: str, ocupado: list) -> list:
    """Ver comentario de `_PERSOA_MINUSCULA_TRAS_VERBO`. Recorta polo
    final calquera palabra que non pareza parte do nome (funcional ou de
    prosa xurídica coñecida, ex. "con domicilio..." despois do apelido)
    -- mesma idea ca `_recortar_entidade_persoa`, pero sobre texto en
    minúscula onde spaCy nunca chegou a propor unha entidade que recortar."""
    atopadas = []
    for match in _PERSOA_MINUSCULA_TRAS_VERBO.finditer(texto):
        inicio, fin = match.span("nome")
        if any(ocupado[inicio:fin]):
            continue
        palabras = match.group("nome").split()
        while len(palabras) > 1:
            baixa = palabras[-1].lower()
            if baixa in _PALABRAS_FUNCIONAIS or baixa in _PALABRAS_NON_NOME:
                palabras.pop()
                continue
            break
        if len(palabras) < 2:
            continue
        fin = inicio + len(" ".join(palabras))
        if any(ocupado[inicio:fin]):
            continue
        atopadas.append(Entidade(inicio, fin, texto[inicio:fin], "PERSOA"))
    return atopadas


# Quinto recoñecedor de reserva: nome de pía da TÁBOA OFICIAL do INE
# (`nomes_ine.py`) seguido de polo menos un apelido que tamén estea na
# táboa oficial de apelidos. Caso real que o motivou (medición do
# 28/09/2026, 9 fugas): spaCy etiqueta "Roi Barroso Cordeiro", "Xacobe
# Ferrándiz Salcedo" ou "Ledicia Falcón Bande" coma LOC, ORG ou MISC -- non
# coma persoa -- e o nome queda SEN redactar. Corre ANTES ca spaCy polo
# mesmo motivo ca o recoñecedor de honorífico: se correse despois, a zona
# xa estaría "ocupada" pola LOC incorrecta.
#
# Esixir un apelido DA TÁBOA (non abonda "palabra con maiúscula") é o que
# evita confundir "Amparo Constitucional", "Sala Primera" ou "Mariña
# Lucense" cun nome. Pero a táboa de apelidos tamén trae palabras
# correntes (hai persoas apelidadas "Real", "Mayor" ou "Primera"): esas
# non contan coma apelido e cortan o nome (`_NON_APELIDOS`).
_NON_APELIDOS = frozenset("""
PRIMERA PRIMERO SEGUNDA SEGUNDO TERCERA TERCERO CUARTA CUARTO PROVINCIAL
REAL MAYOR MENOR CIVIL PENAL JUSTICIA NUEVA NUEVO VIEJA VIEJO NEGRA NEGRO
VERDE GRIS ROJA ROJO APOSTOL MARTIR JUZGADO SALA REINO GOBIERNO CIUDAD
PLAYA PUERTO HOSPITAL ESCUELA CALLE PLAZA PRAZA CAMINO ESTRADA BARRIO
SANTO SANTA SAN VIRGEN CRISTO GRANDE PEQUEÑO BAJO BAJA LARGO NORTE SUR
ESTE ORIENTE LEVANTE ENERO FEBRERO MARZO ABRIL MAYO JUNIO JULIO AGOSTO
SEPTIEMBRE OCTUBRE NOVIEMBRE DICIEMBRE LUNES MARTES MIERCOLES JUEVES
VIERNES SABADO DOMINGO CONSEJO SALUD GUARDIA FISCAL
""".split())

# A palabra xusto antes do nome indica que é o nome dunha VÍA, CENTRO ou
# PREMIO, non dunha persoa ("calle Rosalía de Castro", "Hospital Álvaro
# Cunqueiro", "IES Rosalía de Castro"). Tamén con "de" polo medio ("Praza
# de María Pita"). Compárase sen acentos e en minúscula.
_PREFIXOS_LUGAR = frozenset("""
calle c rua r avenida avda av plaza pza praza paseo pasaxe pasaje travesia
travesa ronda camino camiño estrada carretera lugar barrio bairro parroquia
urbanizacion poligono edificio hospital clinica centro colegio ceip cpi ies
instituto escola escuela universidad universidade facultad fundacion
asociacion club premio estadio teatro auditorio aeropuerto aeroporto
pabellon biblioteca museo residencia hotel virgen san santa santo senora
""".split())

# Artigo ou preposición contraída xusto antes: en castelán non vai diante
# dun nome de persoa, pero si dun topónimo ou advocación ("María del
# Pilar" xa o colle spaCy enteiro; "la Virgen del Pilar" non é persoa).
_PREVIOS_NON_PERSOA = frozenset({"del", "el"})

# Topónimos, marcas e lugares que coinciden exactamente con "nome da
# táboa + apelido da táboa" (normalizados coma o INE).
_EXCEPCIONS_NOME_TABOA = (
    "SANTIAGO DE COMPOSTELA", "SANTIAGO BERNABEU", "MERCEDES BENZ",
    "MERCEDES-BENZ", "SOL MELIA", "CRUZ ROJA", "MARIÑA LUCENSE",
)

_PALABRA_CANDIDATA_NOME = re.compile(r"(?<![\w'’-])" + _PALABRA_CAPITALIZADA_RE)
_UNIDADE_APELIDO_TABOA = re.compile(
    r"[ \t]+(?:" + _CONECTOR_NOME_RE + r"[ \t]+){0,2}(?P<palabra>" + _PALABRA_CAPITALIZADA_RE + r")"
)
_MAX_APELIDOS_TABOA = 4
_SOCIEDADE_DESPOIS_RE = re.compile(r",?[ \t]*S\.?[ \t]?(?:L|A|C)\.?(?:U\.?)?(?!\w)")
# Admite un punto ou barra pegados á palabra anterior: abreviaturas de
# vía ("Avda. Rosalía de Castro", "c/ Rosalía de Castro").
_PALABRA_ANTES_RE = re.compile(r"([\wÁÉÍÓÚÑÜáéíóúñü]+)[./]?[ \t]*\Z")


def _palabras_anteriores(texto_suavizado: str, inicio: int, cantas: int = 2) -> list:
    """As `cantas` palabras xusto antes de `inicio` na MESMA liña, da máis
    próxima á máis lonxana."""
    # Só unha xanela curta cara atrás: buscar dende o principio do texto
    # en cada candidato sería cadrático nun documento de centos de páxinas.
    xanela = texto_suavizado[max(0, inicio - 80):inicio]
    palabras = []
    for _ in range(cantas):
        match = _PALABRA_ANTES_RE.search(xanela)
        if match is None:
            break
        palabras.append(match.group(1))
        xanela = xanela[:match.start(1)]
    return palabras


def _e_apelido_da_taboa(palabra: str) -> bool:
    return any(
        nomes_ine.normalizar(parte) in nomes_ine.apelidos()
        and nomes_ine.normalizar(parte) not in _NON_APELIDOS
        for parte in palabra.split("-")
    )


def _detectar_persoas_por_taboa(texto: str, texto_suavizado: str, ocupado: list, nlp) -> list:
    """Ver comentario de `_NON_APELIDOS`. Busca no texto SUAVIZADO (así un
    nome TODO EN MAIÚSCULAS tamén se atopa, igual ca nos outros
    recoñecedores); o texto devolto tómase do ORIXINAL. Os cargos públicos
    exentos non se miran aquí: a última pasada de `detectar` aplícalles a
    exención igual ca ás persoas atopadas por calquera outro camiño."""
    nomes_validos = nomes_ine.nomes_para_detector(nlp)
    atopadas = []
    for match in _PALABRA_CANDIDATA_NOME.finditer(texto_suavizado):
        inicio = match.start()
        if ocupado[inicio] or nomes_ine.normalizar(match.group()) not in nomes_validos:
            continue

        anteriores = _palabras_anteriores(texto_suavizado, inicio)
        anteriores_baixa = [p.lower().translate(_ACENTOS) for p in anteriores]
        if anteriores_baixa and (
            anteriores_baixa[0] in _PREFIXOS_LUGAR
            or anteriores_baixa[0] in _PREVIOS_NON_PERSOA
            or (anteriores_baixa[0] in {"de", "do", "da"} and anteriores_baixa[1:2]
                and anteriores_baixa[1] in _PREFIXOS_LUGAR)
        ):
            continue
        # "vivía en A Mariña": artigo galego en maiúscula no medio da frase
        # = topónimo. A inicio de frase, "A" pode ser a preposición ("A Roi
        # Barroso se le notificó..."), e aí decide o apelido.
        if anteriores and anteriores[0] in {"A", "O", "As", "Os"}:
            antes_do_artigo = texto_suavizado[:inicio - len(anteriores[0]) - 1].rstrip(" \t")
            if antes_do_artigo and not _INICIO_DE_FRASE_RE.search(antes_do_artigo + " ") \
                    and not antes_do_artigo.endswith("\n"):
                continue

        unidades = []  # (fin, é apelido da táboa, palabra)
        fin = match.end()
        for _ in range(_MAX_APELIDOS_TABOA):
            unidade = _UNIDADE_APELIDO_TABOA.match(texto_suavizado, fin)
            if unidade is None:
                break
            palabra = unidade.group("palabra")
            baixa = palabra.lower()
            if (
                nomes_ine.normalizar(palabra) in _NON_APELIDOS
                or baixa in _PALABRAS_FUNCIONAIS
                or baixa in _PALABRAS_NON_NOME
                or re.fullmatch(_CARGOS_EXENTOS_RE, palabra, re.IGNORECASE)
            ):
                break
            fin = unidade.end()
            unidades.append((fin, _e_apelido_da_taboa(palabra), palabra))
        # Unha palabra DESPOIS do último apelido da táboa que non está nela
        # pero si é palabra corrente do modelo ("Leticia Viana Letrada") non
        # é apelido: fóra. Un apelido galego raro que non está na táboa
        # ("Fiolleda") non ten vector no modelo, así que se conserva -- se
        # se quitase, quedaría á vista xunto ao nome xa redactado.
        while unidades and not unidades[-1][1] and nlp.vocab.has_vector(unidades[-1][2].lower()):
            unidades.pop()
        if not any(e_apelido for _, e_apelido, _ in unidades):
            continue
        fin = unidades[-1][0]

        normalizado = nomes_ine.normalizar(texto_suavizado[inicio:fin])
        if normalizado.startswith(_EXCEPCIONS_NOME_TABOA):
            continue
        if _SOCIEDADE_DESPOIS_RE.match(texto_suavizado, fin):
            continue
        if any(ocupado[inicio:fin]):
            continue
        atopadas.append(Entidade(inicio, fin, texto[inicio:fin], "PERSOA"))
        for i in range(inicio, fin):
            ocupado[i] = True
    return atopadas


_PALABRA_ANTERIOR_RE = re.compile(
    r"(?<![\w'’.\-])(" + _PALABRA_CAPITALIZADA_RE + r")[ \t]+\Z"
)
_POS_NON_NOME = {"VERB", "AUX", "ADP", "DET", "PRON", "CCONJ", "SCONJ", "NUM", "PUNCT"}
_MAX_PALABRAS_CARA_ATRAS = 2


def _estender_cara_atras(doc, inicio: int) -> int:
    """Caso oposto a `_estender_entidade_persoa`: spaCy deixa ás veces o
    PRIMEIRO nome de pía fóra da entidade ("Xosé" en "Xosé Manuel Carballo
    Portela", ou etiquetado á parte coma LOC). Estende cara atrás sobre
    ata `_MAX_PALABRAS_CARA_ATRAS` palabras capitalizadas contiguas (só
    espazo/tabulador polo medio, nunca salto de liña nin puntuación) que
    non sexan palabras funcionais, de prosa coñecida, cargos nin verbos."""
    texto = doc.text
    for _ in range(_MAX_PALABRAS_CARA_ATRAS):
        m = _PALABRA_ANTERIOR_RE.search(texto, max(0, inicio - 80), inicio)
        if m is None:
            break
        palabra = m.group(1)
        baixa = palabra.lower()
        if baixa in _PALABRAS_FUNCIONAIS or baixa in _PALABRAS_NON_NOME:
            break
        if re.fullmatch(_CARGOS_EXENTOS_RE, palabra, re.IGNORECASE):
            break
        w_inicio = m.start(1)
        span = doc.char_span(w_inicio, m.end(1), alignment_mode="expand")
        if span is None or any(t.pos_ in _POS_NON_NOME for t in span):
            break
        anterior = texto[:w_inicio].rstrip(" \t")
        inicio_frase = anterior == "" or anterior[-1] in ".!?:;\n"
        noutra_entidade = any(
            e.start_char <= w_inicio < e.end_char and e.label_ != "PER" for e in doc.ents
        )
        if (inicio_frase or noutra_entidade) and baixa not in _NOMES_PIA:
            break
        inicio = w_inicio
        if inicio_frase:
            break
    return inicio


# Tramo que se pode engadir a unha persoa xa detectada por patrón ao
# unila coa entidade (máis longa) de spaCy: só palabras capitalizadas,
# iniciais e conectores de apelido ("de la", "y" de "Ortega y Gasset"),
# con guion/apóstrofo -- nunca salto de liña, tratamentos (sinal dunha
# SEGUNDA persoa: "... y Dña. María") nin cargos.
_UNIDADE_TRAMO_RE = (
    r"(?:[A-ZÁÉÍÓÚÑÜ][\wáéíóúñÁÉÍÓÚÑÜ]*\.?|"
    + _CONECTOR_NOME_RE + r"|y|e)"
)
_TRAMO_NOME_RE = re.compile(
    r"[ \t\-'’]*(?:" + _UNIDADE_TRAMO_RE + r"(?:[ \t\-'’]+|\Z))*"
)
_TRATAMENTO_NO_TRAMO_RE = re.compile(r"(?<!\w)" + _TRATAMENTO_RE + r"(?!\w)")

# Un guión CON espazos a ambos lados ("Aldara - Turno") é puntuación --
# separador de columna/cláusula nunha listaxe ou epígrafe -- nunca parte
# dun apelido composto: eses van SEMPRE pegados, sen espazos ("Pérez-
# Vázquez", ver tests de honorífico). Sen esta excepción, un tramo coma
# " - Turno" pasaba `_TRAMO_NOME_RE` (o guión solto xa vai admitido coma
# separador de unidade) e `_unir_con_persoa_existente` fundía "Turno" no
# nome da persoa veciña sen deixar rastro -- bug real: "Veiga Lucas,
# Aldara - Turno de mañá" redactaba "Turno" coma parte do nome, en vez de
# deixalo coma mención solta marcada para revisión (o que si pasaba en
# "Barroso Cordeiro, Sabela - Turno", onde spaCy devolvía "Turno" coma
# entidade á parte dende un principio, sen pasar por aquí).
_GUION_SOLTO_RE = re.compile(r"\s-\s")


def _tramo_de_nome(tramo: str) -> bool:
    if "\n" in tramo or _TRATAMENTO_NO_TRAMO_RE.search(tramo):
        return False
    if re.search(_CARGOS_EXENTOS_RE, tramo, re.IGNORECASE):
        return False
    if _GUION_SOLTO_RE.search(tramo):
        return False
    return _TRAMO_NOME_RE.fullmatch(tramo) is not None


# Cargo ANTES do nome, sen honorífico, en bloques de sinatura reais do BOE/
# DOG ("El Secretario General Técnico, Xoán Páez Veiga", "La
# Subdirectora General de Planificación, Ana Marín Ferrer"): spaCy
# adoita devolver cargo+nome coma UNHA SOA entidade, redactando tamén o
# cargo (sobre-anonimización SEN marcar, caso real do corpus web
# 28/09/2026). Ningún nome real en castelán/galego empeza por "El/La/Los/
# Las" (nunca é nome de pía), así que ese artigo NO PROPIO INICIO da
# entidade, seguido dunha coma, é sinal fiable de que todo o anterior á
# coma é o cargo -- non fai falta unha lista pechada de palabras de cargo
# (fráxil, coma se viu coas áreas ministeriais).
_ARTIGO_CARGO_INICIO_RE = re.compile(
    # SEN "\A": ese ancoraxe é ao inicio ABSOLUTO da cadea completa, non á
    # posición `pos` que se lle pasa a `.match()` -- usar `\A` aquí faría
    # que isto só casase cando a entidade estivese literalmente no
    # carácter 0 do documento (bug atopado probando este mesmo arranxo).
    # `.match(string, pos, endpos)` xa ancora en `pos` por definición.
    #
    # O primeiro artigo acepta minúscula tamén (bloque de sinatura no medio
    # dunha frase: "...y el Secretario de Estado de Cultura, Nome..."); o
    # resto do patrón segue a esixir maiúscula inicial (Title Case) para
    # non casar con prosa normal.
    r"[.\u2013\u2014-]*[ \t]*(?:[Ee]l|[Ll]a|[Ll]os|[Ll]as)[ \t]+"
    r"(?:" + _PALABRA_CAPITALIZADA_RE + r"|d[eo]s?|del|las?|los)"
    r"(?:[ \t]+(?:" + _PALABRA_CAPITALIZADA_RE + r"|d[eo]s?|del|las?|los)){0,6}"
    r"[ \t]*,[ \t]*"
)


def _recortar_cargo_inicial(entidade, texto: str, suavizado: str) -> None:
    """Se a propia entidade empeza por "El/La/Los/Las <cargo>," recorta o
    cargo e dei xa só o resto coma entidade -- pero só se o resto AÍNDA
    ten forma de nome (`_tramo_de_nome`); se non, deixa a entidade coma
    estaba (mellor sobre-anonimización de máis ca un anaco sen sentido
    ou, peor, unha fuga)."""
    match = _ARTIGO_CARGO_INICIO_RE.match(suavizado, entidade.inicio, entidade.fin)
    if not match:
        return
    resto = texto[match.end():entidade.fin]
    # Co apelido xa unido desde a liña seguinte ("José Francisco Salido\nEscudero",
    # BOE-A-2026-16711) o salto non impide recortar o cargo.
    if not resto or not _tramo_de_nome(resto.replace("\n", " ")):
        return
    entidade.inicio = match.end()
    entidade.texto = resto


# "el Notario de Valencia", "Registradora de la Propiedad de Ourense n.º 2":
# un cargo co seu lugar, sen nome. spaCy dáo coma persoa (corpus web lote 2,
# 30/09/2026). Co nome detrás ("Notario de Boadilla del Monte Don Rafael...")
# recórtase ata o tratamento; o nome queda para o seu recoñecedor.
_CARGO_DE_LUGAR_RE = re.compile(
    r"(?:[Ee]l|[Ll]a)?[ \t]*(?:Notari[oa]|Registrador[a]?(?:[ \t]+de[ \t]+la[ \t]+Propiedad|[ \t]+Mercantil)?)"
    r"[ \t]+(?:de|del|d['’])[ \t]*(?P<resto>.*)\Z",
    re.DOTALL,
)


def _e_cargo_de_lugar(entidade, texto: str) -> bool:
    m = _CARGO_DE_LUGAR_RE.match(entidade.texto)
    if not m:
        return False
    honorifico = re.search(r"(?<!\w)" + _TRATAMENTO_RE + r"[ \t]+", m.group("resto"))
    if honorifico is None:
        return True
    nome_ini = entidade.inicio + m.start("resto") + honorifico.end()
    if nome_ini >= entidade.fin:
        return True
    entidade.inicio = nome_ini
    entidade.texto = texto[nome_ini:entidade.fin]
    return False


# Verbo (ou palabra de prosa) a INICIO de frase que o modelo mete dentro do
# nome: "Asina Uxía Barroso Cordeiro" -> "Asina PERSOA_...", con "Asina"
# absorbido (corpus web, 29/09/2026). Só se recorta a PRIMEIRA palabra e só
# se o resto aínda ten forma de nome.
_VERBOS_INICIAIS = frozenset("""
asina asinan firma firman informa informan declara declaran manifesta manifiesta
manifestan expón expone exponen solicita solicitan certifica certifican suscribe
suscriben resolve resuelve notifica notifican presenta presentan propón propone
nomea nombra recibe remite autoriza ordena comparece comparecen fai fago fixo
asiste asisten
""".split())
_PRIMEIRA_PALABRA_RE = re.compile(r"(\w+)[ \t]+")


# Titular dunha parcela nunha táboa sen bordos (BOE, expropiacións): a cela
# estreita parte o nome en "APELIDO1 APELIDO2\nNOME" (corpus web,
# BOE-B-2026-30660: quedaba enteiro á vista, spaCy tomábao por lugar). Só
# cando a primeira liña son DOUS apelidos do INE e a segunda un nome de pía do
# INE, e nada máis nas dúas liñas: unha lista de concellos ou de organismos
# non cumpre as dúas condicións á vez.
_APELIDOS_LIÑA_NOME_LIÑA_RE = re.compile(
    r"(?m)^[ \t]*(?P<ap>[A-ZÁÉÍÓÚÑÜ]{2,}[ \t]+[A-ZÁÉÍÓÚÑÜ]{2,})[ \t]*\n"
    r"[ \t]*(?P<nome>[A-ZÁÉÍÓÚÑÜ]{2,}(?:[ \t]+[A-ZÁÉÍÓÚÑÜ]{2,})?)[ \t]*$"
)
_FRECUENCIA_MINIMA_APELIDO_LIÑA = 100
_FRECUENCIA_MINIMA_NOME_LIÑA = 1000


def _detectar_persoas_apelidos_liña_nome_liña(texto: str, ocupado: list) -> list:
    nomes, apelidos = nomes_ine.nomes(), nomes_ine.apelidos()
    atopadas = []
    for m in _APELIDOS_LIÑA_NOME_LIÑA_RE.finditer(texto):
        inicio, fin = m.start("ap"), m.end("nome")
        if any(ocupado[inicio:fin]) or _e_organismo(m.group(0)):
            continue
        aps, nps = m.group("ap").split(), m.group("nome").split()
        if any(p.lower() in _PALABRAS_FUNCIONAIS or p.lower() in _PALABRAS_NON_NOME for p in aps + nps):
            continue
        if all(apelidos.get(nomes_ine.normalizar(a), 0) >= _FRECUENCIA_MINIMA_APELIDO_LIÑA for a in aps) and \
                all(nomes.get(nomes_ine.normalizar(n), 0) >= _FRECUENCIA_MINIMA_NOME_LIÑA for n in nps):
            atopadas.append(Entidade(inicio, fin, texto[inicio:fin], "PERSOA", multilinea=True))
    return atopadas


def _recortar_verbo_inicial(entidade, texto: str, suavizado: str) -> None:
    m = _PRIMEIRA_PALABRA_RE.match(suavizado, entidade.inicio, entidade.fin)
    if not m:
        return
    palabra = m.group(1).lower()
    if palabra not in _VERBOS_INICIAIS and (
        palabra not in _PALABRAS_NON_NOME or nomes_ine.normalizar(palabra) in nomes_ine.nomes()
    ):
        return
    resto = texto[m.end():entidade.fin]
    if not resto or not _tramo_de_nome(resto):
        return
    entidade.inicio = m.end()
    entidade.texto = resto


# Marcas e programas con maiúsculas no medio ("VInnovate", "PYMEs"): un
# nome de persoa nunca leva 2+ maiúsculas seguidas e despois minúsculas.
# Trade-off aceptado: un nome mal lido por OCR con esa forma non se redacta.
_MARCA_MAIUSCULAS_RE = re.compile(r"\b[A-ZÁÉÍÓÚÑ]{2,}[a-záéíóúñ]{3,}\b")


# Sen NINGUNHA palabra nas táboas oficiais do INE (nomes nin apelidos): siglas
# ("ENISA", "DOGC", "EOI") e substantivos con maiúscula ("Riesgos",
# "Financiación", "Pobreza Energética", "Normalización Lingüística") que spaCy
# toma por persoas (corpus web, lectura humana 30/09/2026). Todos os nomes
# reais dos 150 documentos teñen polo menos unha palabra no INE. Non se aplica
# tras un tratamento (don/Sr./Dr.): aí manda o tratamento.
# Trade-off: un nome estranxeiro RARÍSIMO sen ningunha palabra no INE (menos
# de 20 persoas en España por palabra) e sen tratamento non se redactaría.
_PALABRAS_CONTIDO_MAXIMAS_SEN_INE = 5
_TRATAMENTO_ANTES_RE = None


def _tras_cargo_de_comision(entidade, texto: str) -> bool:
    """"3º Vogal Maalem Nasrullah, Nadeen": a persoa vai xusto despois dun cargo de
    comisión ao principio da liña e ten forma "Apelidos, Nome". A estrutura abonda: os
    nomes estranxeiros (fóra das táboas do INE) quedaban á vista (xa na versión do 4/10)."""
    inicio_liña = texto.rfind("\n", 0, entidade.inicio) + 1
    cargo = _CARGO_DE_COMISION_DIANTE_RE.match(texto, inicio_liña, entidade.fin)
    return bool(cargo and cargo.end() == entidade.inicio and "," in entidade.texto
                and "\n" not in entidade.texto.strip())


def _sen_palabras_de_nome_ine(entidade, texto: str) -> bool:
    if _tras_cargo_de_comision(entidade, texto):
        return False
    global _TRATAMENTO_ANTES_RE
    if _TRATAMENTO_ANTES_RE is None:
        _TRATAMENTO_ANTES_RE = re.compile(r"(?:" + _TRATAMENTO_RE + r")[ \t]*\Z", re.IGNORECASE)
    antes = texto[max(0, entidade.inicio - 12):entidade.inicio]
    por_delegacion = re.search(r"P\.[ \t]*D\.[ \t]*\Z", antes) is not None  # "P. D. Orden EFD/..."
    return _tramo_sen_ine(entidade.texto) and (por_delegacion or not _TRATAMENTO_ANTES_RE.search(antes))


# Unha soa sigla en maiúsculas ("BIC", "IVA") só pode ser un apelido se é
# FRECUENTE: "BIC" está no INE (27 persoas) pero no BOE é "Ben de Interese
# Cultural".
_FRECUENCIA_MINIMA_SIGLA_APELIDO = 1000


def _e_sigla_rara(tramo: str) -> bool:
    t = tramo.strip()
    if not re.fullmatch(r"[A-ZÁÉÍÓÚÑÜ]{2,5}", t):
        return False
    k = nomes_ine.normalizar(t)
    # Un nome de pía en maiúsculas ("XOÁN" nunha listaxe "APELIDOS, XOÁN.")
    # nunca é unha sigla, sexa cal sexa a súa frecuencia (regresión atopada
    # nos tests ao introducir esta regra).
    if nomes_ine.nomes().get(k, 0) > 0:
        return False
    return nomes_ine.apelidos().get(k, 0) < _FRECUENCIA_MINIMA_SIGLA_APELIDO


def _tramo_sen_ine(tramo: str) -> bool:
    if _e_sigla_rara(tramo):
        return True
    palabras = [p for p in re.findall(r"[^\W\d_]+", tramo) if p.lower() not in _PARTICULAS_APELIDO]
    if not palabras or len(palabras) > _PALABRAS_CONTIDO_MAXIMAS_SEN_INE:
        return False
    # Iniciais dun nome ("Barroso Cordeiro, M. I."): son do nome, aínda que
    # unha letra solta non estea no INE (regresión atopada na auditoría).
    if re.search(r"(?<![^\W\d_])[^\W\d_]\.", tramo):
        return False
    contido = [p for p in palabras if p.lower() not in _PALABRAS_FUNCIONAIS and p.lower() not in _PALABRAS_NON_NOME]
    nomes, apelidos = nomes_ine.nomes(), nomes_ine.apelidos()
    return not any(nomes_ine.normalizar(p) in nomes or nomes_ine.normalizar(p) in apelidos for p in contido)


def _quitar_anacos_sen_ine(entidade, texto: str) -> list:
    """"General de la Entidad Pública Empresarial, Miguel Ramiro Guillem":
    pártese polas comas SÓ se algún anaco non ten ningunha palabra do INE, e
    tírase ese anaco. Se todos teñen ("Páez Veiga, Xoán"), non se toca."""
    if _tras_cargo_de_comision(entidade, texto):
        return [entidade]
    if entidade.etiqueta != "PERSOA" or entidade.cela or not re.search(r"[,;]", entidade.texto):
        return [entidade]
    pezas, cursor = [], entidade.inicio
    for m in list(re.finditer(r"[,;]", texto[entidade.inicio:entidade.fin])) + [None]:
        fin = entidade.inicio + m.start() if m else entidade.fin
        ini = cursor
        while ini < fin and texto[ini] in " \t\n":
            ini += 1
        f = fin
        while f > ini and texto[f - 1] in " \t\n":
            f -= 1
        if f > ini:
            pezas.append((ini, f))
        cursor = fin + 1
    boas = [(a, b) for a, b in pezas if not _tramo_sen_ine(texto[a:b])]
    if len(boas) == len(pezas):
        return [entidade]
    return [Entidade(a, b, texto[a:b], entidade.etiqueta, fila=entidade.fila, multilinea=entidade.multilinea)
            for a, b in boas]


# Iniciais dunha forma xurídica pegadas diante do nome ("...Energía, M.P.,
# Miguel Ramiro Guillem", "Fundación EOI F.S.P., Diego..."): non son do nome.
_INICIAIS_CON_COMA_RE = re.compile(r"(?:[A-ZÁÉÍÓÚÑ]\.[ \t]*)+,[ \t]*")


def _recortar_iniciais_con_coma(entidade, texto: str) -> None:
    m = _INICIAIS_CON_COMA_RE.match(texto, entidade.inicio, entidade.fin)
    if m and m.end() < entidade.fin and _tramo_de_nome(texto[m.end():entidade.fin].split("\n")[0]):
        entidade.inicio = m.end()
        entidade.texto = texto[m.end():entidade.fin]


# Corpus web lote 2 (30/09/2026), nada disto é unha persoa:
#  - ordinal dun apartado nunha liña ("Segundo.", "Sexto.-"): "Segundo"
#    é tamén nome de pía, por iso só cando vai só e seguido de puntuación;
#  - "de Arbizu" solto (lista "el Ayuntamiento\nde Arbizu"), sen outra
#    persoa pegada da que poida ser o apelido;
#  - abreviaturas do BOE: "P. D." (por delegación), "P. S." (por
#    substitución), "Sec. II.A. Pág." da cabeceira.
_ORDINAIS = frozenset("""
primero segundo tercero cuarto quinto sexto séptimo septimo octavo noveno décimo decimo
undécimo undecimo duodécimo duodecimo primeiro terceiro sétimo setimo oitavo
""".split())
_ABREVIATURAS_BOLETIN_RE = re.compile(r"(?:P\.[ \t]?[DS]\.|[A-Z]\.[ \t]+P[áa]g)\Z")


# Razón social: "GRAM LAW, SOCIEDAD LIMITADA", "MIA PIA IBERIA S.L."
# (BOE-A-2026-11924): detrás só outras palabras en MAIÚSCULAS (0-6, na mesma
# liña: "PUEYO Y PUMAR CONCURSAL Y PERICIAL SLP") e a forma.
_FORMA_SOCIEDADE_DESPOIS_RE = re.compile(
    r"(?:[ \t]+[A-ZÁÉÍÓÚÑ0-9&'.-]+){0,6}[ \t]*,?[ \t]*(?:"
    r"S\.?[ \t]?L\.?(?:[ \t]?U\.?)?|S\.?[ \t]?A\.?(?:[ \t]?U\.?)?|SAT|SLU|SAU|SLP|"
    r"SOCIEDAD[ \t]+(?:LIMITADA|AN[OÓ]NIMA|DE[ \t]+RESPONSABILIDAD|COOPERATIVA)|"
    r"Sociedad[ \t]+(?:Limitada|An[oó]nima|de[ \t]+Responsabilidad|Cooperativa))(?![\w])"
)


# Só para o cargo SEN nome ("El Letrado de la Administración de Justicia",
# BOE-B-2026-17992). A propósito non en `_CARGO_TRAS_NOME_RE`: aí cortaría o
# nome antes do cargo e activaría a exención de cargo público onde hoxe se
# anonimiza (decisión que lle corresponde ao usuario).
_CARGO_XUSTIZA_RE = re.compile(
    r"(?:Letrad[oa]|Magistrad[oa]|Juez|Jueza|Xu[ií]za?|Fiscal|Notari[oa]|Registrador[a]?|Procurador[a]?)(?![\wáéíóúñ])")


@lru_cache(maxsize=8)
def _termos_definidos(texto: str) -> dict:
    """Termos que o propio documento define entre comiñas latinas: "(en lo
    sucesivo, «TATE»)", "una «Parte»", "«Per Diem» significa..." (convenio
    BOE-A-2026-1546). Só os que non poden ser o alias dunha persoa: siglas, nomes
    comúns (aparecen tamén en minúscula) ou definicións con "significa"."""
    termos = {}
    for m in re.finditer(r"«([^»\n]{2,40})»", texto):
        termo = m.group(1).strip()
        definido = re.search(r"(?i)(?:en\s+lo\s+sucesivo|en\s+adelante|denominad[oa]s?)[^.;]{0,60}\Z",
                             texto[max(0, m.start() - 80):m.start()])
        significa = re.match(r"\s+(?:significa|se\s+entender)", texto[m.end():m.end() + 20])
        if not (definido or significa):
            continue
        if significa or re.fullmatch(r"[A-ZÁÉÍÓÚÑ]{2,}", termo) \
                or re.search(r"(?<!\w)" + re.escape(termo.lower()) + r"(?!\w)", texto):
            termos[termo.lower()] = termo
    return termos


_MOEDAS_ROMANAS = {"as", "semis", "denario", "áureo", "aureo", "sestercio", "dupondio", "cuadrante", "quinario"}
_CODIGO_ESTRADA_RE = re.compile(r"(?<![\w-])[A-Z]{1,4}-\d{1,4}(?![\w-])")
def _e_palabra_solta_non_nome(entidade, t: str, texto: str) -> bool:
    """Unha soa palabra no medio dunha frase en minúscula, sen tratamento
    diante (lote 3, 03/10/2026):
    - sigla en maiúsculas pouco frecuente coma apelido/nome no INE ("a través
      de SIMENDEF, MENSADEF, GEISER o correo", "excluyendo IVA o impuestos");
    - palabra común con maiúscula que aparece tamén en minúscula no documento
      e non é nome de pía ("o Seguro, será responsable" / "de seguro")."""
    if not re.fullmatch(r"[^\W\d_]+", t):
        return False
    inicio_liña = texto.rfind("\n", 0, entidade.inicio) + 1
    antes = texto[inicio_liña:entidade.inicio]
    if not re.search(r"[a-záéíóúñ]{3,}", antes) or _TRATAMENTO_ANTES_RE_SOLTA.search(antes):
        return False
    k = nomes_ine.normalizar(t)
    if t.isupper():
        # "PÉREZ, Manuel": orde inversa dun nome, non sigla.
        if re.match(r"[ \t]*,[ \t]*[A-ZÁÉÍÓÚÑ]", texto[entidade.fin:entidade.fin + 4]):
            return False
        return (len(t) >= 2 and nomes_ine.nomes().get(k, 0) < _FRECUENCIA_MINIMA_SIGLA_APELIDO
                and nomes_ine.apelidos().get(k, 0) < _FRECUENCIA_MINIMA_SIGLA_APELIDO)
    return (t[:1].isupper() and t[1:].islower() and re.search(r"[a-záéíóúñ,][ \t]*\Z", antes) is not None
            and nomes_ine.nomes().get(k, 0) == 0
            and re.search(r"(?<!\w)" + re.escape(t.lower()) + r"(?!\w)", texto) is not None)


def _dentro_de_listaxe_de_lugares(entidade, t: str, texto: str) -> bool:
    """"los juzgados de Barcelona, Arenys de Mar, Badalona, Berga, ..."
    (BOE-A-2025-22094, lote 4): nunha enumeración longa onde case ningún
    elemento empeza por un nome de pía, os elementos son lugares ou
    organismos. Unha listaxe de persoas (cada elemento empeza por un nome de
    pía) non entra aquí."""
    nomes = nomes_ine.nomes()
    primeira = t.split()[0].strip(",")
    # "Santa\nColoma de Farners": San/Santa/Sant abren un topónimo.
    if primeira not in ("San", "Santa", "Sant", "Santo") and nomes.get(nomes_ine.normalizar(primeira), 0) >= 100:
        return False
    if _TRATAMENTO_ANTES_RE_SOLTA.search(texto, max(0, entidade.inicio - 12), entidade.inicio):
        return False
    ini = max(texto.rfind(";", 0, entidade.inicio), texto.rfind(":", 0, entidade.inicio),
              texto.rfind(". ", 0, entidade.inicio), entidade.inicio - 1500)
    fins = [p for p in (texto.find(";", entidade.fin), texto.find(".\n", entidade.fin)) if p >= 0]
    fin = min(fins + [entidade.fin + 1500])
    elementos = [e.strip() for e in re.split(r",|\s+(?:y|e|i)\s+", texto[ini + 1:fin])]
    elementos = [e for e in elementos if re.match(r"[A-ZÁÉÍÓÚÑ]", e)]
    if len(elementos) < 8:
        return False
    con_nome = sum(e.split()[0] not in ("San", "Santa", "Sant", "Santo")
                   and nomes.get(nomes_ine.normalizar(e.split()[0]), 0) >= 100 for e in elementos)
    return con_nome <= len(elementos) * 0.2


_TRATAMENTO_ANTES_RE_SOLTA = re.compile(r"(?:" + _TRATAMENTO_RE + r")[ \t]*\Z", re.IGNORECASE)
_CONECTORES_GALEGOS_INICIO = {"segundo", "segunda", "polo", "pola", "polos", "polas"}


def _e_ruido_de_boletin(entidade, texto: str) -> bool:
    t = entidade.texto.strip()
    # Nome dun premio entre comiñas: "Premio de Investigación ... «Ángela Ruiz
    # Robles»" (BOE-A-2026-15844; decisión do usuario 01/10/2026: queda á vista).
    if (texto[max(0, entidade.inicio - 1):entidade.inicio] in ("«", "“", '"')
            # Tamén o nome dunha institución: "Instituto Asturiano de
            # Administración Pública «Adolfo Posada»" (BOE-A-2026-7477, lote 3).
            and re.search(r"\b(?i:Premios?|Becas?|Medallas?|Galard[oó]n|C[aá]tedra|Instituto|Escuela|Escola"
                          r"|Colegio|Colexio|Fundaci[oó]n|Museo|Biblioteca|Centro|Pol[ií]gono|Parque|Pavill?[oó]n"
                          r"|Estadio|Auditorio)\b[^.;«“\"]{0,140}\Z",
                          texto[max(0, entidade.inicio - 160):entidade.inicio - 1])
            # "concedido a «Nome»": esa é a persoa premiada, non o premio.
            and not re.search(r"\b(?:a|al|para|á|ao)\s*\Z", texto[max(0, entidade.inicio - 8):entidade.inicio - 1])):
        return True
    if t.isupper() and _FORMA_SOCIEDADE_DESPOIS_RE.match(texto, entidade.fin):
        return True
    if t.startswith("SE "):  # subestación eléctrica: "SE Itxaso"
        return True
    # Calquera caixa se a forma vai xusto detrás: "I-DE Redes Eléctricas
    # Inteligentes, SAU" (BOE-A-2026-16636).
    if re.match(r"[ \t]*(?:[A-ZÁÉÍÓÚÑ][\wáéíóúñ-]+[ \t]*)?,[ \t]*(?:SAU|SLU|SAT|SLP|S\.A\.U?\.?|S\.L\.U?\.?|SA|SL)(?![\w])",
                texto[entidade.fin:entidade.fin + 40]):
        return True
    # "D.X. DE GANDARÍA": o "D." tomouse coma tratamento e quedou "X. DE ...".
    if re.match(r"[XG]\.", t) and texto[max(0, entidade.inicio - 2):entidade.inicio] in ("D.", "S."):
        return True
    # Só o cargo, sen nome: "–El Secretario Primero de la Comisión" (sinatura
    # do BOE; "Primero" tamén é apelido e salvábao do filtro do INE).
    artigo = re.match(r"[.\u2013\u2014-]*[ \t]*(?:[Ee]l|[Ll]a)[ \t]+", t)
    if artigo and "," not in t and (_CARGO_TRAS_NOME_RE.match(" " + t[artigo.end():])
                                    or _CARGO_XUSTIZA_RE.match(t, artigo.end())):
        return True
    abreviatura = _ABREVIATURAS_BOLETIN_RE.search(t)
    if abreviatura and (abreviatura.start() == 0 or _tramo_sen_ine(t[:abreviatura.start()].strip(" ,"))
                        or _ARTIGO_CARGO_INICIO_RE.fullmatch(t[:abreviatura.start()].rstrip(" ,") + ",")):
        return True
    # Tamén seguido de minúscula: "Sexto curso." (BOE-A-2026-6004, lote 3).
    if t.lower() in _ORDINAIS and re.match(r"[ \t]*(?:[.:\u2013\u2014-]|[a-záéíóúñ])", texto[entidade.fin:entidade.fin + 3]):
        return True
    # "Segundo o previsto", "Polo exposto," (lote 3, DOG): "Segundo" é nome de
    # pía e "Polo" apelido, pero sós e seguidos de minúscula ou coma son
    # preposición galega.
    if t.lower() in _CONECTORES_GALEGOS_INICIO and re.match(r"[ \t]*(?:,|[a-záéíóúñ])", texto[entidade.fin:entidade.fin + 3]):
        return True
    # "MD da PO-532" (marxe dereita dunha estrada, lote 3): código de estrada
    # e nada con forma de nome.
    estrada = _CODIGO_ESTRADA_RE.search(t)
    if estrada:
        resto = (t[:estrada.start()] + " " + t[estrada.end():]).strip()
        if all(p.lower() in _PARTICULAS_APELIDO or (p.isupper() and len(p) <= 3) for p in resto.split()) \
                or _tramo_sen_ine(resto):
            return True
    if _e_palabra_solta_non_nome(entidade, t, texto):
        return True
    # "Londres, Reino Unido": "Reino" quedaba só ao separar "Londres".
    seguinte = re.match(r"[ \t\n]+([^\W\d_]+)", texto[entidade.fin:entidade.fin + 30])
    if seguinte and f"{t} {seguinte.group(1)}".lower() in _TERRITORIOS:
        return True
    # "Rico, El" de "Porto Rico, El Salvador": o anaco é o final dun territorio.
    anterior = re.search(r"([^\W\d_]+)[ \t\n]+\Z", texto[max(0, entidade.inicio - 30):entidade.inicio])
    primeira = re.match(r"[^\W\d_]+", t)
    if anterior and primeira and f"{anterior.group(1)} {primeira.group()}".lower() in _TERRITORIOS \
            and all(p.lower() in _TERRITORIOS or p.lower() in _PARTICULAS_APELIDO
                    for p in re.findall(r"[^\W\d_]+", t[primeira.end():])):
        return True
    # "Sábado (...).\nDomingo (...)" (BOE-A-2026-4943): día da semana, non o nome.
    if t in ("Domingo", "DOMINGO") and re.search(r"(?i)s[aá]bado", texto[max(0, entidade.inicio - 80):entidade.fin + 80]):
        return True
    # "C. Clasificación...\nD. Permisos y beneficios" (BOE-A-2026-4943): o "D."
    # dunha lista A., B., C., D. non é "don".
    if re.search(r"(?:^|\n)C\.[ \t][^\n]*\n[ \t]*D\.[ \t]+\Z", texto[max(0, entidade.inicio - 200):entidade.inicio]):
        return True
    # "c.sede Vigo.- Anuncio de subasta" (BOE-B-2026-8928): ".-" no medio dun
    # nome nunca; aquí separa a cidade do título do anuncio.
    if re.fullmatch(r"[^\W\d_]+\.[ \t]*[-–—][ \t]*(?:Anuncio|Edicto|Edito|C[eé]dula|Notificaci[oó]n)", t):
        return True
    # "Pontevedra-Vigo-Ourense" (AnuncioC3K1-180825, lote 4): área xeográfica.
    if "-" in t and all(p.lower() in _PROVINCIAS or p.lower() in _TERRITORIOS for p in t.split("-")):
        return True
    if _dentro_de_listaxe_de_lugares(entidade, t, texto):
        return True
    # "Chave365", "SOROLLA2": letras e cifras pegadas nunha soa palabra (lote 3).
    if re.fullmatch(r"[^\W\d_]{2,}\d+", t):
        return True
    # "D. Cabezas explosivas.\n153,133" (BOE-A-2026-9676): letra dunha táboa de
    # índices, non "don"; esíxese a cifra da cela seguinte.
    if re.search(r"(?:^|\n)[ \t]*D\.[ \t]+\Z", texto[max(0, entidade.inicio - 6):entidade.inicio]) \
            and re.match(r"[ \t]+[a-záéíóúñ]+\.?[ \t]*\n[ \t]*[\d.,]+[ \t]*(?:\n|$)", texto[entidade.fin:entidade.fin + 60]):
        return True
    # Provincia dentro dunha enumeración de provincias ("Albacete, Cuenca y\n
    # Guadalajara", "ÁVILA, BURGOS, SEGOVIA Y SORIA").
    pezas = [p for p in re.split(r"[ \t\n]*,[ \t\n]*|[ \t\n]+[yYeE][ \t\n]+", t) if p]
    if pezas and all(p.lower() in _PROVINCIAS for p in pezas):
        antes_p = re.search(r"([^\W\d_]+)[ \t\n]*(?:,|[ \t\n][yYeE])[ \t\n]*\Z",
                            texto[max(0, entidade.inicio - 30):entidade.inicio])
        despois_p = re.match(r"[ \t\n]*(?:,|[yYeE][ \t\n])[ \t\n]*([^\W\d_]+)", texto[entidade.fin:entidade.fin + 30])
        if (antes_p and antes_p.group(1).lower() in _PROVINCIAS) or (despois_p and despois_p.group(1).lower() in _PROVINCIAS):
            return True
    # "Ministerio de la Presidencia, Justicia y Relaciones con las Cortes".
    if re.fullmatch(r"(?i)las[ \t\n]+Cortes", t) and re.search(r"Relaciones[ \t\n]+con[ \t\n]*\Z",
                                                                 texto[max(0, entidade.inicio - 20):entidade.inicio]):
        return True
    antes = texto[max(0, entidade.inicio - 40):entidade.inicio]
    despois = texto[entidade.fin:entidade.fin + 40]
    # "acuerdo de Sala\nde Gobierno", "la presidencia de la Sala" (BOE-A-2026-5479).
    if t in ("Sala", "SALA") and (re.search(r"\b(?:la|esta|dicha|cada|misma|de)[ \t\n]+\Z", antes)
                                  or re.match(r"[ \t\n]+de[ \t\n]+(?:Gobierno|lo|la|Apelaci|Casaci)", despois)):
        return True
    # "Tesorero/a" (BOE-A-2026-2939): cargo co xénero, nunca unha persoa.
    if re.match(r"/(?:as?|os?)\b", despois):
        return True
    # Catálogo de moedas (BOE-A-2026-7022): "Época de Augusto", "Anv.: Cabeza
    # laureada de Tiberio a izquierda", "Semis", "la sala Tauler y Fau".
    if re.search(r"\b(?:[ÉEé]poca|reinado|tiempos?)[ \t]+de[ \t]+\Z", antes) \
            or re.search(r"\b(?:Anv|Rev)\.:[ \t]*\Z", antes) \
            or re.match(r"[ \t]+a[ \t]+(?:derecha|izquierda)\b", despois) \
            or t.lower() in _MOEDAS_ROMANAS \
            or re.search(r"\bsala[ \t\n]+(?:[A-ZÁÉÍÓÚÑ][\wáéíóúñ]+[ \t\n]+[yYe][ \t\n]+)?\Z", antes):
        return True
    # Termos que o propio convenio define: "la TATE", "Tate Liverpool", "la Parte".
    termos = _termos_definidos(texto)
    if termos:
        sen_artigo = re.sub(r"^(?:[Ee]l|[Ll]as?|[Ll]os)[ \t\n]+", "", t)
        primeira = sen_artigo.split()[0].lower() if sen_artigo.split() else ""
        # "Tate Liverpool": a primeira palabra é a sigla definida («TATE»).
        if sen_artigo.lower() in termos or (primeira in termos and termos[primeira].isupper()):
            return True
    # "S. DE E. DE MEDIO AMBIENTE" (Secretaría de Estado, BOE-A-2026-6433).
    if t.startswith("E. ") and re.search(r"\bS\.[ \t]+DE[ \t]+\Z", texto[max(0, entidade.inicio - 8):entidade.inicio]):
        return True
    # "(MNCARS-Madrid)": sigla dun organismo e a súa sede.
    if re.fullmatch(r"[A-Z]{3,}-[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+", t):
        return True
    # "S. DE E. TELECOMUNIC. E INFRAEST." (BOE-A-2026-2636, lote 3): palabra
    # abreviada en maiúsculas, co punto pegado, que non está no INE.
    ultima = t.split()[-1]
    if t.isupper() and texto[entidade.fin:entidade.fin + 1] == "." and len(ultima) >= 4 \
            and _tramo_sen_ine(ultima):
        return True
    # "Consejería de Presidencia, Reto\nDemográfico, Igualdad" (BOE-A-2026-7477).
    if t == "Reto" and re.match(r"\s+Demogr[aá]fico", texto[entidade.fin:entidade.fin + 15]):
        return True
    # "A. Engadese o parágrafo" (lote 3): letra de enumeración e un verbo.
    enumeracion = re.fullmatch(r"[A-ZÁÉÍÓÚÑ]\.[ \t]+([^\W\d_]+)", t)
    if enumeracion and texto[max(0, entidade.inicio - 1):entidade.inicio] in ("", "\n") \
            and _tramo_sen_ine(enumeracion.group(1)):
        return True
    if re.fullmatch(r"(?:de|del|d[oa]s?)[ \t\n]+\w+", t):
        # Apelido dunha persoa partida ("Xoán\nde Andrade") só se a palabra
        # de diante ten forma de nome e non é un organismo ("Ayuntamiento").
        anterior = re.search(r"(\w+)[\W]{0,3}\Z", texto[max(0, entidade.inicio - 40):entidade.inicio])
        return anterior is None or not anterior.group(1)[:1].isupper() or _e_organismo(anterior.group(1))
    return False


def _e_fragmento_de_palabra(entidade, texto: str) -> bool:
    """"Re-" de "Re-\nsolución": o principio dunha palabra partida a final
    de liña non é un nome se o que segue empeza en minúscula (en "Ana-\n
    María" segue unha maiúscula e mantense)."""
    if not entidade.texto.rstrip().endswith(("-", "\u00ad", "\u2010", "\u2011")):
        return False
    resto = texto[entidade.fin:entidade.fin + 12].lstrip()
    return resto[:1].islower()


def _e_marca(entidade) -> bool:
    return len(entidade.texto.split()) <= 3 and _MARCA_MAIUSCULAS_RE.search(entidade.texto) is not None


# Topónimos: o que vai xusto despois de "MVMC" (monte vecinal en man común),
# "monte", "parroquia"... é un lugar ("MVMC Acevedo", "Parroquia da
# Pereira"), non unha persoa, aínda que sexa un apelido real. "lugar de"
# queda fóra a propósito: "en lugar de D. Xoán" é "en vez de".
_LUGAR_INTRODUTOR = r"(?:mvmc|monte|parroquia|freguesía|aldea|aldeas|comunidade[ \t]+de[ \t]+montes)"
_ENTIDADE_COMEZA_POR_LUGAR_RE = re.compile(
    r"(?:" + _LUGAR_INTRODUTOR + r"|paraxes?|parajes?|cortijos?|canal|finca|barranco|arroio|arroyo|regato"
    r"|[aá]reas?[ \t]+sanitarias?|distritos?[ \t]+sanitarios?)\b",
    re.IGNORECASE)
_PRECEDIDA_DE_LUGAR_RE = re.compile(
    r"\b" + _LUGAR_INTRODUTOR + r"[ \t]+(?:d[eo]s?[ \t]+|das?[ \t]+)?\Z", re.IGNORECASE
)


# "vecino de Ames", "Ayuntamiento de Ames", "con domicilio en San José"
# (corpus web lote 2, 30/09/2026): o que vén detrás é un lugar.
_TRAS_INTRODUTOR_DE_LUGAR_RE = re.compile(
    r"\b(?:(?:vecin[oa]s?|veciñ[oa]s?|natural|concello|ayuntamiento|municipio|provincia|"
    r"localidade?|t[ée]rmino[ \t]+municipal|termo[ \t]+municipal)[ \t\n]+d[eo]|"
    r"(?:con[ \t]+domicilio|domiciliad[oa]|residente|radicad[oa])[ \t\n]+en)[ \t\n]+\Z",
    re.IGNORECASE,
)


# Lugar e data dunha sinatura: "Ames, 16 de julio de 2026.–El Presidente"
# (BOE-A-2026-15975, lectura de Claude 30/09/2026).
_DATA_DESPOIS_RE = re.compile(
    r",[ \t]*\d{1,2}[ \t]+de[ \t]+(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|"
    r"octubre|noviembre|diciembre|xaneiro|febreiro|marzo|abril|maio|xuño|xullo|agosto|setembro|outubro|"
    r"novembro|decembro)\b",
    re.IGNORECASE,
)


def _e_toponimo(entidade, suavizado: str) -> bool:
    if _ENTIDADE_COMEZA_POR_LUGAR_RE.match(suavizado, entidade.inicio, entidade.fin):
        return True
    if _DATA_DESPOIS_RE.match(suavizado, entidade.fin):
        return True
    tratamento = re.search(r"(\w+)[ \t]+\Z", suavizado[max(0, entidade.inicio - 8):entidade.inicio])
    if tratamento and f"{tratamento.group(1)} {entidade.texto}".lower() in _MUNICIPIOS_CON_TRATAMENTO:
        return True
    antes = suavizado[max(0, entidade.inicio - 40):entidade.inicio]
    # "en San Juan de Alicante" (a entidade é "Juan de Alicante"); "Pedro San
    # Juan" non: diante do "San" vai un nome, non unha palabra en minúscula.
    if re.search(r"(?:^|[^\w])[a-záéíóúñ]+\s+Sant?[oa]?\s+\Z", antes):
        return True
    # Nome dunha institución: "Universidad\nCarlos III de Madrid",
    # "Universidad Rovira i Virgili" (BOE-A-2026-13616, lectura de Claude).
    # Nunca "Apelidos, Nome": "...Titulares de Universidad\nAlcaraz Iborra,
    # Manuel." é a listaxe de profesorado (BOE-A-2026-7914, FUGA).
    if "," not in entidade.texto and re.search(
            r"\b(?:Universidad|Universidade|Fundaci[oó]n|Hospital|Colegio|Colexio|Instituto|"
            r"Escuela|Escola|Conservatorio)\s+\Z", antes):
        return True
    # Rúa co nome dunha persoa: "na rúa Manuel Ángel Terrón" (DOG
    # AnuncioG0763-290726-0013, lectura de Claude): é un topónimo.
    # Tamén partida por guión de fin de liña ("na ave-\nnida Enrique Peinador",
    # AnuncioG0256) e mosteiros, igrexas... ("ao mosteiro de San Clodio").
    if re.search(r"\b(?:r[uú]a|calle|avenida|avda\.|praza|plaza|pza\.|paseo|camiño|camino|travesía|travesia|"
                 r"rolda|ronda|glorieta|mosteiro|monasterio|igrexa|iglesia|capela|capilla|ermida|ermita|"
                 r"santuario|convento|colexiata|colegiata)\s+(?:d[eoa]s?\s+(?:la\s+)?)?\Z",
                 re.sub(r"-\n", "", antes), re.IGNORECASE):
        return True
    # "Ecologistas en Acción"; "SE Itxaso" (subestación eléctrica).
    if re.search(r"(?:Ecologistas\s+en|\bSE)\s+\Z", antes):
        return True
    # Título dunha lei: "Ley 29/1994, de 24 de noviembre, de Arrendamientos
    # Urbanos" (BOE-A-2026-14956, lectura humana 01/10/2026).
    if re.search(r"\b(?:Ley|Lei|Decreto|Orden|Reglamento|Regulamento)\b[^.;]{0,50},?\s+(?:de|del|sobre)\s+\Z", antes):
        return True
    # "Cauce: Arroyo Prado Medio", "Paraje de la toma: Fuente..." (BOE-B-2025-35020).
    if re.search(r"\b(?:Cauce|Paraje(?:[ \t]+de[ \t]+la[ \t]+toma)?|Paraxe|Lugar[ \t]+de[ \t]+la[ \t]+toma)[ \t]*:[ \t]*"
                 r"(?:(?:Arroyo|R[ií]o|Regato|Barranco|Rambla|Fuente|Manantial)[ \t]+(?:de[ \t]+(?:la[ \t]+|los[ \t]+|las[ \t]+)?)?)?\Z",
                 antes):
        return True
    # Nome dunha liña eléctrica: "a 220 kV Itxaso-Elgea" (BOE-A-2026-16636).
    if re.search(r"\d\s*(?:kV|kW|MW|MVA)\s+\Z", antes):
        return True
    return _PRECEDIDA_DE_LUGAR_RE.search(antes) is not None or _TRAS_INTRODUTOR_DE_LUGAR_RE.search(antes) is not None


# Lugares das listas oficiais (INE + Nomenclátor de Galicia): ver
# `lugares_oficiais.py`. Palabras que introducen un lugar ("vecino de",
# "parroquia de"...) e preposicións que o sitúan ("en", "na", "no").
_CONTEXTO_LUGAR_ANTES_RE = re.compile(
    r"(?:\b(?:en|na|no|nas|nos|ata|hasta|desde|dende)[ \t]+(?:(?:el|la|los|las|o|a|os|as)[ \t]+)?"
    r"|\b(?:parroquias?|freguesías?|concellos?|municipios?|ayuntamientos?|aldeas?|lugar(?:es)?|"
    r"localidad(?:es)?|localidades?|barrios?|bairros?|termos?|t[ée]rminos?|provincias?|comarcas?|"
    r"vecin[oa]s?|veciñ[oa]s?|naturales?|residentes?|domiciliad[oa]s?|polígonos?|poligonos?|"
    r"parajes?|paraxes?|núcleos?|nucleos?|capital|cidade|ciudad|"
    # Organismos e edificios cuxo "de X" é un lugar (corpus web lotes 3-4, 04/10/2026).
    r"audiencias?[ \t]+(?:provincial|nacional)|diputaci[oó]n(?:es)?[ \t]+(?:provincial|foral)|"
    r"notari[oa]s?|registr(?:o|ador[a]?)[ \t]+(?:de[ \t]+la[ \t]+propiedad|mercantil)|"
    r"edificios?(?:[ \t]+[A-ZÁÉÍÓÚÑ][\wáéíóúñ]+)?|hospital|campus|estaci[oó]n|"
    r"subdelegaci[oó]n[ \t]+del[ \t]+gobierno)"
    r"[ \t]*:?[ \t]+(?:(?:d[eo]s?|da|das|del)[ \t]+(?:(?:el|la|los|las|o|a|os|as)[ \t]+)?)?)\Z",
    re.IGNORECASE)
# "Cenes de la Vega, Granada, España": código postal diante na mesma liña, ou "España" detrás.
_CODIGO_POSTAL_ANTES_RE = re.compile(r"\b\d{5}\b[^\n]{0,60},[ \t]*\Z")
_ESPAÑA_DESPOIS_RE = re.compile(r"[ \t]*,?[ \t]*(?:España|Espanya|Spain)\b")
_ENTIDADE_COMEZA_POR_INTRODUTOR_RE = re.compile(
    r"(?:(?:vecin[oa]s?|veciñ[oa]s?|natural(?:es)?|residentes?|parroquia|concello|municipio|ayuntamiento|"
    r"lugar|localidad|aldea|barrio|provincia|t[ée]rmino|termo)[ \t]+d[eo]s?[ \t]+(?:(?:el|la|o|a)[ \t]+)?|"
    r"mvmc[ \t]+)",
    re.IGNORECASE)
_SEPARADOR_DE_LUGARES_RE = re.compile(r"[ \t]*[,;][ \t]*|[ \t]+(?:y|e|i|ou)[ \t]+|[ \t]*[-\u2013\u2014/][ \t]*")
_ELEMENTO_ANTES_RE = re.compile(r"([^,;\n]{1,60})(?:[ \t]*[,;][ \t]*|[ \t]+(?:y|e|i)[ \t]+|[ \t]+[-\u2013][ \t]+)\Z")
_ELEMENTO_DESPOIS_RE = re.compile(r"(?:[ \t]*[,;][ \t]*|[ \t]+(?:y|e|i)[ \t]+|[ \t]+[-\u2013][ \t]+)([^,;.\n]{1,60})")
_PROVINCIA_ENTRE_PARENTESES_RE = re.compile(r"[ \t]*\(([^()\n]{2,40})\)")


def _lugar_con_contexto(entidade, texto: str) -> bool:
    """Contexto que fai ler coma lugar un nome que tamén podería ser persoa."""
    antes = texto[max(0, entidade.inicio - 60):entidade.inicio]
    antes = antes[antes.rfind("\n") + 1:]
    if _CONTEXTO_LUGAR_ANTES_RE.search(antes) or _CODIGO_POSTAL_ANTES_RE.search(antes):
        return True
    if _ESPAÑA_DESPOIS_RE.match(texto, entidade.fin):
        return True
    # "Vilar (Lugo)", "Castro, Lugo": unha provincia xusto ao lado.
    despois = texto[entidade.fin:entidade.fin + 60]
    entre = _PROVINCIA_ENTRE_PARENTESES_RE.match(despois)
    if entre and lugares_oficiais.e_provincia(entre.group(1)):
        return True
    veciño = _ELEMENTO_DESPOIS_RE.match(despois)
    if veciño and lugares_oficiais.e_provincia(veciño.group(1)):
        return True
    # Enumeración de lugares: un veciño de lista que tamén é lugar e non ten
    # forma de nome ("Castro, Vilar e San Clodio").
    anterior = _ELEMENTO_ANTES_RE.search(re.sub(r"(?i)(?<=[ \t])(?:el|la|los|las|els|les|o|a|os|as)[ \t]+\Z", "", antes))
    for elemento, cara_atras in ((anterior.group(1) if anterior else None, True), (veciño.group(1) if veciño else None, False)):
        if not elemento:
            continue
        elemento = _ENTIDADE_COMEZA_POR_INTRODUTOR_RE.sub("", elemento.strip())
        palabras = elemento.split()
        # O veciño pode levar palabras de máis ("do esbozo do MVMC Estelo"): proba
        # o final (diante) ou o comezo (detrás) do anaco, de 1 a 4 palabras.
        candidatos = [" ".join(palabras[-n:] if cara_atras else palabras[:n]) for n in range(1, min(4, len(palabras)) + 1)]
        for candidato in candidatos:
            if lugares_oficiais.e_lugar(candidato) and (
                    not lugares_oficiais.parece_nome_de_persoa(lugares_oficiais.normalizar_lugar(candidato))
                    or lugares_oficiais.e_provincia(candidato)):
                return True
    return False


def _e_lugar_oficial(entidade, texto: str) -> bool:
    """A "persoa" é un lugar das listas oficiais (ver `lugares_oficiais.py`)?
    Con "don/doña" diante segue a ser persoa. Cunha enumeración de lugares
    ("Sant Feliu de Llobregat, Arenys de Mar") valen todos os elementos."""
    t = _ENTIDADE_COMEZA_POR_INTRODUTOR_RE.sub("", re.sub(r"^(?:de|del|do|da|en)[ \t\n]+", "", entidade.texto.strip()))
    if not t or not t[:1].isalpha():
        return False
    if _TRATAMENTO_ANTES_RE_SOLTA.search(texto, max(0, entidade.inicio - 14), entidade.inicio) \
            or re.search(r"\b(?:don|doña|dona|d\.|dª|dña)[ \t]*\Z", texto[max(0, entidade.inicio - 8):entidade.inicio], re.IGNORECASE):
        return False
    if lugares_oficiais.normalizar_lugar(t) in lugares_oficiais.ARTIGOS:
        # "El" de "El Masroig" cortado pola entidade.
        seguinte = re.match(r"[ \t]+[^\W\d_][\w'’-]*(?:[ \t]+(?:d[eo]s?|da|del|d')?[ \t]*[^\W\d_][\w'’-]*){0,3}",
                            texto[entidade.fin:entidade.fin + 50])
        palabras = seguinte.group().split() if seguinte else []
        return any(lugares_oficiais.e_lugar(f"{t} {' '.join(palabras[:n])}") for n in range(1, len(palabras) + 1))
    pezas = [p for p in _SEPARADOR_DE_LUGARES_RE.split(t) if p]
    if len(pezas) > 1 and not lugares_oficiais.e_lugar(t):
        # "Milà, Els": o artigo é o da localidade seguinte ("Els Guiamets").
        pezas = [p for p in pezas if lugares_oficiais.normalizar_lugar(p) not in lugares_oficiais.ARTIGOS]
        if len(pezas) == 1:
            t = pezas[0]
    if len(pezas) > 1 and not lugares_oficiais.e_lugar(t):
        # "Pontevedra-Vigo", "Sant Feliu de Llobregat, Arenys": todas lugares.
        # A última pode quedar cortada pola entidade ("Arenys" de "Arenys de Mar").
        ultima = pezas[-1]
        seguinte = re.match(r"(?:[ \t]+[^\W\d_]+){1,3}", texto[entidade.fin:entidade.fin + 40])
        palabras = seguinte.group().split() if seguinte else []
        prolongada = any(lugares_oficiais.e_lugar(f"{ultima} {' '.join(palabras[:n])}")
                         for n in range(1, len(palabras) + 1))
        if not (all(lugares_oficiais.e_lugar(p) for p in pezas[:-1]) and (lugares_oficiais.e_lugar(ultima) or prolongada)):
            return False
        # "Vilar, Lugo": lugar e provincia.
        if "," in t and lugares_oficiais.e_provincia(ultima):
            return True
        # "Pérez-Castro" son dous apelidos aínda que ambos sexan lugares: só
        # se len coma lugares con contexto de lugar.
        if any(lugares_oficiais.parece_nome_de_persoa(lugares_oficiais.normalizar_lugar(p)) for p in pezas):
            return _lugar_con_contexto(entidade, texto)
        return True
    if not lugares_oficiais.e_lugar(t):
        # "Cimadevila Darbo": dous topónimos seguidos; só con contexto de lugar
        # (dous apelidos raros que sexan lugares tamén poden ser unha persoa).
        palabras = [w for w in t.split() if lugares_oficiais.normalizar_lugar(w) not in lugares_oficiais.PARTICULAS]
        return (len(palabras) > 1 and all(lugares_oficiais.e_lugar(w) for w in palabras)
                and not any(lugares_oficiais.parece_nome_de_persoa(lugares_oficiais.normalizar_lugar(w)) for w in palabras)
                and _lugar_con_contexto(entidade, texto))
    if not lugares_oficiais.parece_nome_de_persoa(lugares_oficiais.normalizar_lugar(t)):
        return True
    return _lugar_con_contexto(entidade, texto)


# Encabezados de formulario e termos institucionais que o modelo toma por
# persoa ("SÚA REPRESENTACIÓN", "PALABRAS CHAVE", "Traductor Jurado",
# "Autoridad Independiente de Responsabilidad Fiscal"; lotes 3-4, 04/10/2026):
# a "persoa" está feita SÓ de palabras destas listas ou de substantivos
# abstractos (-ción, -idade...), sen ningunha palabra que sexa nome de pía ou
# apelido frecuente, e sen tratamento (don/Sr.) diante.
_TERMOS_ENCABEZADO = frozenset("""
palabras chave orden puesto novo razon social apelidos persoa fisica xuridica privada entidade local
obxecto interprete traductor jurado autoridad independiente fiscal provedor factura data ambito
prioridade datos nome nif sinatura nacionalidade enderezo telefono representacion sua jefe jefa xefe xefa
trabajo trabajos consejeria consejera consejero consej migraciones seguridad social sala mellor
""".split())
_SUFIXO_ABSTRACTO_RE = re.compile(r"(?:cion|sion|idade|idad|mento|miento)\Z")
_CIFP_RE = re.compile(r"(?:CIFP|CEIP|CPI|CPR|EOI|CEE|IES)\b")


def _e_encabezado_ou_termo(entidade, texto: str) -> bool:
    t = entidade.texto.strip()
    if _CIFP_RE.match(t):  # "CIFP Reina Victoria Eugenia": centro docente
        return True
    antes = texto[max(0, entidade.inicio - 12):entidade.inicio]
    nomes, apelidos = nomes_ine.nomes(), nomes_ine.apelidos()
    palabras = [p for p in re.findall(r"[^\W\d_]+", t) if p.lower() not in _PARTICULAS_APELIDO
                and p.lower() not in _PALABRAS_FUNCIONAIS and not re.fullmatch(r"N[º°]", p)]
    if not palabras:
        return False
    # "Sra. Fiscal Jefa": o tratamento diante dun CARGO non fai persoa ao cargo.
    so_cargo = all(p.lower() in ("fiscal", "sala", "jefe", "jefa", "xefe", "xefa", "consejero", "consejera") for p in palabras)
    if not so_cargo and (_TRATAMENTO_ANTES_RE_SOLTA.search(antes)
                         or re.search(r"\b(?:don|doña|dona)[ \t]*\Z", antes, re.IGNORECASE)):
        return False
    encabezado = False
    for p in palabras:
        sen_acento = unicodedata.normalize("NFD", p.lower())
        sen_acento = "".join(c for c in sen_acento if unicodedata.category(c) != "Mn")
        if sen_acento in _TERMOS_ENCABEZADO:
            encabezado = True
            continue
        k = nomes_ine.normalizar(p)
        if nomes.get(k, 0) >= 100 or apelidos.get(k, 0) >= 1000:
            return False
        if _SUFIXO_ABSTRACTO_RE.search(sen_acento):
            encabezado = True
        elif len(p) > 1 and not _e_sigla_rara(p):
            return False
    return encabezado


# Termos que NON son persoas e que o NER tapa (lote 5, revisión humana do 10/10/2026):
# logo do pé do DOG ("[CIRA"), siglas con puntos ("I.R.P.F."), títulos de temario
# ("Título I. De"), nomes de planta solar ("Flix-Ascó II", "Oleo Solar"), binomios
# latinos de especies ("(Falco naumanni)"), accidentes xeográficos ("Sierra de La
# Cabra"), a "Sala" dun tribunal e verbos a comezo de frase ("Simultanearán").
_SIGLAS_NON_PERSOA = frozenset("IRPF IVA IBI IAE ITP AJD BOE DOG DNI NIF CIF NRP TRLA".split())
_TITULO_DE_NORMA_RE = re.compile(r"(?i)(?:t[ií]tulo|cap[ií]tulo|art[ií]culo|secci[oó]n|anexo|disposici[oó]n)\b")
_ACCIDENTE_XEOGRAFICO_RE = re.compile(
    # Exixe o conector ("Sierra del Toro"): Llanos, Sierra, Valle ou Monte tamén son nomes de pía
    # ("Llanos Carretero Ganuza", firmante dun BOE do lote 5).
    r"(?i)(?:sierra|r[ií]o|llanos?|cerro|monte|valle|arroyo|pico|laguna|embalse|serra|ribeira)\b[ \t]+"
    r"(?:de|del|de[ \t]+la|de[ \t]+los|de[ \t]+las|da|do|das|dos)\b[ \t]+\S")
_PROXECTO_ANTES_RE = re.compile(
    r"(?i)\b(?:planta|parque|central|proyecto|instalaci[oó]n)\b[^.\n]{0,40}\b(?:solar|fotovolt\w+|e[oó]lic\w+)\b[ \t\n«\"]*\Z")
_VERBO_FUTURO_RE = re.compile(r"(?i)\w{4,}(?:ar[aá]n|er[aá]n|ir[aá]n)\Z")
# Casos soltos do lote 6 (petición do usuario, 12/10/2026).
_FORMAS_XURIDICAS_SIGLAS = frozenset("FSP SA SL SAU SLU SLL SLP SC SCP CB SCOOP".split())
_FRANXA_HORARIA_ANTES_RE = re.compile(r"\d{1,2}[:.]\d{2}[ \t]*[-–][ \t]*\d{1,2}[:.]\d{2}[ \t]*\Z")
_TITULACIONS = frozenset("grao grado máster master mestrado licenciatura diplomatura doutoramento doctorado".split())
_PLANTA_OU_FONDO_RE = re.compile(r"(?:FV|PSFV|PFV|PSF)\b|Fondos?[ \t]+(?:de|Europeo|Social|Galego|para)\b")
# Cargo + calificativo ("Fiscal Delegada para la Protección", "Rector Magnífico"; lote 6).
_CARGO_CON_CALIFICATIVO_RE = re.compile(
    r"(?:Fiscal|Rector[a]?|Vicerrector[a]?|Decan[oa]|Director[a]?|Subdirector[a]?|Secretari[oa]|Presidente|Presidenta)"
    r"[ \t\n]+(?:Delegad[oa]|Magn[ií]fic[oa]|Jef[ea]|Xef[ea]|Superior|Provincial|Adxunt[oa]|Adjunt[oa]|Territorial)\b")


_TRATAMENTO_PROPIO_RE = re.compile(
    r"(?<![^\W\d_])(?:don|do[ñn]a|dña|d\.|dª|d/dª|sr\.?|sra\.?|srta\.?|ilm[oa]\.?|iltm[oa]\.?|excm[oa]\.?|dra?\.)[ \t]*\Z",
    re.IGNORECASE)


def _tratamento_antes(antes: str) -> bool:
    """Tratamento (don, Sra., Ilmo...) pegado diante, sen confundir "antigüedad. " co "d." de D."."""
    return _TRATAMENTO_PROPIO_RE.search(antes[-14:]) is not None


def _e_termo_non_persoa(entidade, texto: str) -> bool:
    t = entidade.texto.strip()
    antes = texto[max(0, entidade.inicio - 100):entidade.inicio]
    despois = texto[entidade.fin:entidade.fin + 40]
    # Logo ("[CIRA") do pé de páxina do DOG: unha soa palabra en maiúsculas xunto ao
    # CVE-DOG ou ao selo "XUNTA DE GALICIA".
    if (re.fullmatch(r"[A-ZÁÉÍÓÚÑ]{2,8}", t)
            and (re.match(r"[ \t\n]*(?:\d+%[ \t]*)?XUNTA\b", despois) or "CVE-DOG:" in antes)):
        return True
    # Lixo do OCR do logotipo do pé do DOG antes do selo "5% XUNTA DE GALICIA" ("Dr RUA 3 [OSOS
    # 5% XUNTA", "Ela [a] dE En ao 5% XUNTA"; lote 6: 47 veces nun documento).
    # O lixo pode ocupar varias liñas ("Dr RUA 3\n[OSOS\n5% XUNTA"); 30 caracteres non chegan a
    # saltar a liña do CVE-DOG (máis de 40), así que un asinante xusto antes do pé non entra.
    if (len(t.split()) <= 3 and re.match(r"[\s\S]{0,30}?(?:\d+[ \t]*%|EDOG)[ \t]*XUNTA\b", despois)
            and not _tratamento_antes(antes)):
        return True
    letras = re.sub(r"[^A-Za-z]", "", t).upper()
    if re.fullmatch(r"(?:[A-Z]\.){3,}", t) and letras in _SIGLAS_NON_PERSOA:
        return True
    if _TITULO_DE_NORMA_RE.match(t) and re.search(r"\b[IVXLC]+\b|\d", t):
        return True
    if _ACCIDENTE_XEOGRAFICO_RE.match(t) and len(t.split()) >= 2 and not _tratamento_antes(antes):
        return True
    # "(Falco naumanni)", "(Olea oleaster)": binomio latino entre parénteses.
    if len(t.split()) == 1 and antes.endswith("(") and re.match(r"[ \t][a-z]{4,}[ \t]*[,)]", despois):
        return True
    # Nome dunha planta/parque solar: "planta solar fotovoltaica Flix-Ascó II".
    if _PROXECTO_ANTES_RE.search(antes) and not _tratamento_antes(antes):
        return True
    # "Sala" dun tribunal: "Sala de lo Contencioso", "ante la referida Sala".
    if (re.search(r"(?i)\bSala\Z", t)
            and (re.match(r"[ \t]+de[ \t]+lo[ \t]+", despois) or re.search(r"(?i)(?:referida|dicha|ante la)[ \t]+\Z", antes)
                 or re.search(r"(?i)\b(?:tribunal|justicia|audiencia)\b", t))):
        return True
    # "N.º Póliza": rótulo, nunca unha persoa.
    if re.match(r"N[.º°o]+[ \t]", t) or t.startswith(("Nº ", "N° ")):
        return True
    # Rótulo de formulario só na súa liña ("Patrón:" entre "Call sign:" e "Skipper:", BOE-A-2024-4467).
    inicio_liña = texto.rfind("\n", 0, entidade.inicio) + 1
    fin_liña = texto.find("\n", entidade.fin)
    liña = texto[inicio_liña:fin_liña if fin_liña >= 0 else len(texto)].strip()
    if len(t.split()) == 1 and liña == t + ":":
        return True
    # Concello só na súa liña (columna "Concello" dunha táboa: "Teo", AnuncioG0692-250324-0015_gl).
    if (len(t.split()) == 1 and liña == t and not _tratamento_antes(antes)
            and "C" in lugares_oficiais.lugares().get(lugares_oficiais.normalizar_lugar(t), "")):
        return True
    # Forma xurídica en siglas ("Fundación Pluralismo y Convivencia, F. S.P.", BOE-B-2024-3210).
    if (re.fullmatch(r"(?:[A-ZÁÉÍÓÚÑ]\.[ \t]?){2,4}", t)
            and re.sub(r"[^A-Z]", "", t) in _FORMAS_XURIDICAS_SIGLAS):
        return True
    # Programa dun congreso: "11:30 - 12:00 Pausa café" (sen nome de pía do INE).
    if (_FRANXA_HORARIA_ANTES_RE.search(antes)
            and not any(nomes_ine.normalizar(p) in nomes_ine.nomes() for p in t.split())):
        return True
    # Titulación: "Grao en Medicina".
    if t.lower() in _TITULACIONS and re.match(r"[ \t]+en[ \t]+[A-ZÁÉÍÓÚÑ]", despois):
        return True
    # Rol: "el Técnico o Patrón de la tripulación".
    if t in ("Patrón", "Patroa", "Patrona") and re.match(r"[ \t\n]+de[ \t]", despois):
        return True
    # Planta fotovoltaica ("FV Quilla Solar") e fondos ("Fondo de Asilo, Migración e Integración").
    if _PLANTA_OU_FONDO_RE.match(t) and not _tratamento_antes(antes):
        return True
    # Departamento tras o cargo ou organismo ("Dirección General de Presupuestos y Fondos Europeos",
    # "directora xeral do Tesouro e Política Financeira"; lote 6): sen ningún nome de pía do INE.
    if (_ENUMERACION_TRAS_ORGANISMO_RE.search(antes)
            and not any(nomes_ine.normalizar(p) in nomes_ine.nomes() for p in re.findall(r"[^\W\d_]+", t))):
        return True
    # Cargo con calificativo e ningún nome de pía do INE no resto: o cargo, non a persoa.
    cargo = _CARGO_CON_CALIFICATIVO_RE.match(t)
    if cargo and not any(nomes_ine.normalizar(p) in nomes_ine.nomes()
                         for p in re.findall(r"[^\W\d_]+", t[cargo.end():])) and not _tratamento_antes(antes):
        return True
    # Verbo en futuro a comezo de frase, que non é apelido do INE.
    if (len(t.split()) == 1 and _VERBO_FUTURO_RE.match(t)
            and nomes_ine.apelidos().get(nomes_ine.normalizar(t), 0) == 0
            and nomes_ine.nomes().get(nomes_ine.normalizar(t), 0) == 0
            and not _tratamento_antes(antes)):
        return True
    return False


# Nome dun centro educativo público detrás das súas siglas ou da súa
# denominación: "CIFP Reina Victoria Eugenia", "IES Antonio Machado", "Centro
# Integrado de Formación Profesional Reina Victoria Eugenia" (BOE-A-2025-24517,
# petición do usuario 04/10/2026). Aplícase DESPOIS de propagar as mencións
# dunha persoa, para que ningunha aparición do nome do centro quede tapada.
# Unha persoa separada por coma ("IES Xelmírez I, Ana Pérez") non entra.
_CENTRO_EDUCATIVO_ANTES_RE = re.compile(
    r"(?:\b(?:CIFP|IES|CEIP|CPI|CPR|EOI|CEE|CEPA|CRA|EEI|CPEI|CIFP|I\.E\.S\.)"
    r"|\b(?i:centro[ \t\n]+integrado[ \t\n]+de[ \t\n]+formaci[oó]n[ \t\n]+profesional"
    r"|instituto[ \t\n]+de[ \t\n]+educaci[oó]n[ \t\n]+secundaria"
    r"|colexio[ \t\n]+de[ \t\n]+educaci[oó]n[ \t\n]+infantil[ \t\n]+e[ \t\n]+primaria"
    r"|colegio[ \t\n]+de[ \t\n]+educaci[oó]n[ \t\n]+infantil[ \t\n]+y[ \t\n]+primaria))"
    r"(?:[ \t\n]+(?:Reina|Rey|Rei|Raíña|Infanta|Infante|Príncipe|Princesa|San|Santa|Santo|Doctor|Doutor|Dr\.|"
    r"Poeta|Pintor|Maestro|Mestre|Profesor|Profesora|Padre|Sor))?[ \t\n]+\Z"
)


def _e_nome_de_centro_educativo(entidade, texto: str) -> bool:
    return _CENTRO_EDUCATIVO_ANTES_RE.search(texto[max(0, entidade.inicio - 90):entidade.inicio]) is not None


# Cando `_unir_con_persoa_existente` rexeita fusionar un anaco (por non
# parecer continuación de nome -- ver `_tramo_de_nome`), ese anaco aínda
# pode ser UNHA SOA palabra solta con forma de nome propio ("Turno" en
# " - Turno"). Sen isto desaparecía sen deixar rastro: nin redactada nin
# marcada para revisión, a diferenza do mesmo caso cando spaCy SI a
# devolve á parte dende un principio (aí queda coma mención "apelido
# solto" en `resolution.agrupar`). Permítense separadores soltos a ambos
# lados (espazo, guión, coma, apóstrofo) para poder illar a palabra do
# resto do anaco rexeitado.
_TRAMO_SOLTO_RE = re.compile(
    r"[ \t\-'’,]*(?P<nome>" + _PALABRA_CAPITALIZADA_RE + r")[ \t\-'’,]*"
)


def _engadir_resto_nome_solto(entidades, ocupado, ocupado_directas, texto, suavizado, inicio, fin) -> None:
    """Se o anaco [inicio, fin) (rexeitado por `_unir_con_persoa_existente`
    como continuación de nome) é en realidade UNHA SOA palabra con forma de
    nome propio, engádea coma unha entidade PERSOA nova e independente --
    exactamente coma se spaCy a tivese detectado á parte dende un
    principio (ver comentario de `_TRAMO_SOLTO_RE`)."""
    if inicio >= fin:
        return
    match = _TRAMO_SOLTO_RE.fullmatch(suavizado[inicio:fin])
    if match is None:
        return
    nome_inicio, nome_fin = inicio + match.start("nome"), inicio + match.end("nome")
    if any(ocupado[nome_inicio:nome_fin]) or any(ocupado_directas[nome_inicio:nome_fin]):
        return
    entidades.append(Entidade(nome_inicio, nome_fin, texto[nome_inicio:nome_fin], "PERSOA"))
    for i in range(nome_inicio, nome_fin):
        ocupado[i] = True


def _unir_con_persoa_existente(entidades, ocupado, ocupado_directas, texto, suavizado, inicio, fin) -> bool:
    """Se o span PER de spaCy [inicio, fin) solapa cunha ÚNICA persoa xa
    detectada (por patrón ou por outra entidade PER veciña) e nada máis,
    estende esa persoa á UNIÓN dos dous tramos en vez de descartar o de
    spaCy -- bug real: o patrón de tratamento só collía "Xoán" en "D. Xoán
    de la Fuente Pérez" e o resto do nome quedaba en claro. Só se engade
    a parte que sexa un tramo de nome válido (`_tramo_de_nome`); a parte
    rexeitada, se aínda así parece unha palabra solta con forma de nome,
    engádese coma mención independente (`_engadir_resto_nome_solto`).
    Devolve True se a entidade de spaCy xa queda cuberta (unida)."""
    solapadas = [
        e for e in entidades
        if e.etiqueta == "PERSOA" and e.inicio < fin and e.fin > inicio
    ]
    if len(solapadas) != 1 or solapadas[0].cela:
        return False  # unha cela de táboa acaba no bordo da cela
    persoa = solapadas[0]
    # Unhas iniciais xa son o nome enteiro: estendelas colle o "y" que
    # separa dous comparecentes ("Don B. L. S. y Doña T. G. C.").
    if re.fullmatch(_INICIAIS_NOME_RE, persoa.texto):
        return True
    # calquera outra posición xa ocupada (identificador directo, palabra
    # marcada polo recoñecedor inverso...) -> non se une nada
    if any(ocupado[i] for i in range(inicio, fin) if not persoa.inicio <= i < persoa.fin):
        return False
    novo_inicio, novo_fin = persoa.inicio, persoa.fin
    # A extensión cara adiante non pode entrar nun cargo pegado sen coma
    # (ver `_CARGO_TRAS_NOME_RE`): arrastraríao ata o organismo ("...
    # Secretaria General del Consorcio") e `_quitar_organismos` tiraría
    # despois a persoa ENTEIRA, nome incluído.
    cargo = _CARGO_TRAS_NOME_RE.search(suavizado, persoa.fin, fin)
    exento = _cargo_exento_tras_nome_re().search(suavizado, persoa.fin, min(len(suavizado), fin + 60))
    if exento and exento.start() < fin and (cargo is None or exento.start() < cargo.start()):
        cargo = exento
    if cargo:
        fin = max(persoa.fin, cargo.start())
    if inicio < persoa.inicio and _tramo_de_nome(suavizado[inicio:persoa.inicio]):
        novo_inicio = inicio
    if fin > persoa.fin and _tramo_de_nome(suavizado[persoa.fin:fin]):
        novo_fin = fin
    if any(ocupado_directas[novo_inicio:novo_fin]):
        return True
    orixe_inicio, orixe_fin = persoa.inicio, persoa.fin
    persoa.inicio, persoa.fin = novo_inicio, novo_fin
    persoa.texto = texto[novo_inicio:novo_fin]
    for i in range(novo_inicio, novo_fin):
        ocupado[i] = True
    if fin > orixe_fin and novo_fin < fin:
        _engadir_resto_nome_solto(entidades, ocupado, ocupado_directas, texto, suavizado, novo_fin, fin)
    if inicio < orixe_inicio and novo_inicio > inicio:
        _engadir_resto_nome_solto(entidades, ocupado, ocupado_directas, texto, suavizado, inicio, novo_inicio)
    return True


# --- Persoas que cruzan saltos de liña -------------------------------------
#
# Bug crítico (mestura de identidades): nun .docx os parágrafos/táboas/
# cabeceiras únense con "\n", e spaCy devolvía UNHA soa entidade PER que
# cruzaba varias liñas ("Brais Lorenzo Ogando Fandiño\nTestemuña: Rosa María
# Varela Doval\nDespacho"); unida despois con "Xosé Manuel Carballo Portela",
# as TRES persoas acababan co mesmo código e co DNI de Xosé. Un nome nunca
# se toma coma entidade multiliña: (1) unha entidade PER de spaCy que
# cruza liñas substitúese polas persoas que spaCy atopa en CADA LIÑA por
# separado (`_ents_sen_persoas_multilinea`), e (2) calquera persoa final,
# de calquera recoñecedor, pártese por liñas (`_partir_persoa_por_linas`).
_SALTO_LINA_RE = re.compile(r"[\n\r\f\v\x1c-\x1e\x85  ]")


def _ents_sen_persoas_multilinea(nlp, doc, anaco: str):
    """Devolve [(ent, desprazamento)]: as entidades de `doc` tal cal
    (desprazamento 0), agás as PER que cruzan un salto de liña, que se
    substitúen polas PER dun doc novo de CADA liña que tocan (con
    desprazamento = inicio da liña no anaco) que solapen co span orixinal."""
    texto = doc.text
    resultado = []
    for ent in doc.ents:
        if ent.label_ != "PER" or not _SALTO_LINA_RE.search(ent.text):
            resultado.append((ent, 0))
            continue
        inicio_lina = ent.start_char
        while inicio_lina > 0 and not _SALTO_LINA_RE.match(texto, inicio_lina - 1):
            inicio_lina -= 1
        while inicio_lina < ent.end_char:
            m = _SALTO_LINA_RE.search(texto, inicio_lina)
            fin_lina = m.start() if m else len(texto)
            if texto[inicio_lina:fin_lina].strip():
                for sub in nlp(texto[inicio_lina:fin_lina]).ents:
                    if (sub.label_ == "PER"
                            and inicio_lina + sub.start_char < ent.end_char
                            and inicio_lina + sub.end_char > ent.start_char):
                        resultado.append((sub, inicio_lina))
            inicio_lina = fin_lina + 1
    return resultado


def _e_soamente_prosa_ou_cargo(suavizado: str, ini: int, fin: int, esixir_maiuscula: bool = True) -> bool:
    """True se `suavizado[ini:fin]` non ten forma de nome propio: (se
    `esixir_maiuscula`) non empeza en maiúscula, ou TODAS as súas
    palabras son funcionais, prosa xurídica coñecida
    (`_PALABRAS_NON_NOME`) ou un cargo/profesión exento
    (`_CARGOS_EXENTOS_RE`). `esixir_maiuscula=False` para entidades que
    poden ser LEXITIMAMENTE en minúscula (`_detectar_persoas_minusculas`,
    A19) -- aí só conta se TODAS as palabras son prosa/cargo, nunca a
    maiúscula. Usado para descartar tramos sen ningún nome real -- tanto
    anacos partidos por liña coma a entidade enteira cando non hai salto
    ningún (caso real: "ante Notario" etiquetaba "Notario" a secas coma
    PERSOA, sen ningún nome detrás)."""
    palabras = [re.sub(r"^[(\[]+|[\d³²¹⁴⁵)\].,;:]+$", "", p) for p in suavizado[ini:fin].split()]
    sen_maiuscula = esixir_maiuscula and not suavizado[ini:ini + 1].isupper()
    return sen_maiuscula or all(
        p.lower() in _PALABRAS_FUNCIONAIS or p.lower() in _PALABRAS_NON_NOME
        or re.fullmatch(_CARGOS_EXENTOS_RE, p, re.IGNORECASE)
        for p in palabras
    )


# Membretes e pés de sinatura dos escritos administrativos ("XUNTA DE
# GALICIA / Consellería de ... / Dirección Xeral de ..."), que o modelo
# etiqueta ás veces coma PER -- caso real: o programa instalado anonimizaba
# o membrete enteiro dun escrito da Xunta, e tamén "Tribunal Superior de
# Xustiza de Galicia, Sala do Contencioso-Administrativo".
#
# Só palabras INEQUÍVOCAS de organismo: nada que poida ser apelido por si
# só ("Sala", "Iglesias", "Castro"...). A entidade NON se descarta enteira:
# pártese polas comas/puntos e coma e SÓ se tiran os anacos que teñen unha
# desas palabras, para que un nome de persoa pegado ao organismo ("Xulgado
# do Social nº 2, Xoán Páez Veiga") siga a redactarse.
_ORGANISMOS_RE = re.compile(
    r"\b("
    r"xunta|generalitat|goberno|gobierno|"
    r"conselleri[ao]|consejeri[ao]|ministerio|"
    r"concello|ayuntamiento|deputacion|diputacion|"
    r"direccion\s+(?:xeral|general)|subdireccion|secretaria\s+(?:xeral|general|de\s+estado)|"
    r"delegacion|subdelegacion|xefatura|jefatura|"
    # "Autoridad Portuaria de Sevilla" (lote 6, metade de desenvolvemento)
    r"autoridad\s+portuaria|autoridade\s+portuaria|"
    r"tribunal|audiencia|xulgado|juzgado|fiscalia|"
    # "es" opcional: "universidade"/"universidad" NON casaban co plural
    # "universidades" -- o "s" final rompía o límite de palabra despois de
    # "universidade", así que `_quitar_organismos` nunca o recoñecía. Caso
    # real (corpus web, 28/09/2026): a cabeceira "Educación, Ciencia,
    # Universidades e Formación Profesional" dun DOG partida en varias
    # liñas casaba co patrón "Apelidos,\nNome" ("Ciencia,\nUniversidades")
    # e quedaba SEN filtrar, coma se "Universidades" fose o nome dunha
    # persoa.
    r"universidades?|universidad(?:es)?|"
    r"sergas|servizo\s+galego|servicio\s+gallego|"
    r"axencia\s+(?:estatal|tributaria|galega)|agencia\s+(?:estatal|tributaria)|"
    r"seguridade\s+social|seguridad\s+social|instituto\s+nacional|"
    r"tesouraria\s+(?:xeral|general)|tesoreria\s+general|"
    r"colexio\s+(?:oficial|de)|colegio\s+(?:oficial|de)|camara\s+oficial|"
    r"inspeccion\s+de\s+(?:traballo|trabajo)|"
    # "Sala" ou "Sección" SÓ cando van seguidas do que as identifica coma
    # órgano ("Sala do Contencioso-Administrativo", "Sección 2ª"): "Sala"
    # a secas é un apelido real e non se pode tirar por si só.
    r"sala\s+(?:d[oae]s?|del|primeira|segunda|terceira|cuarta)\b|"
    r"seccion|negociado|"
    r"rexistro\s+civil|registro\s+civil|"
    r"comisaria|garda\s+civil|guardia\s+civil|policia\s+(?:nacional|local|autonomica)|"
    r"centro\s+de\s+(?:saude|salud)|hospital|fundaci[oó]n|"
    # Xulgados: "Sección Civil e Instrucción TI Haro" (Tribunal de Instancia).
    r"instruci[oó]n|instrucci[oó]n|primeira\s+instancia|primera\s+instancia|"
    # Remate institucional ("Xunta de Galicia", "Tribunal Superior de
    # Xustiza de Galicia", "Diario Oficial de Galicia"...); caso real: o
    # OCR do logotipo da Xunta en cada páxina do DOG lía "PEE Pé DE
    # GALICIA" e tapábase coma persoa, levando consigo o pé da páxina.
    r"de\s+galicia|"
    # Corpus web lote 2 (30/09/2026): entes, sociedades e bancos tapados
    # coma persoa ("el Instituto de Crédito Oficial", "Red Eléctrica de
    # España", "Mesa Sectorial", "Cruz Vermella").
    r"instituto\s+de|entidad(?:e)?\s+p[uú]blica|confederaci[oó]n|mancomunidad(?:e)?|"
    r"federaci[oó]n|consorcio|uni[oó]n\s+europea|red\s+el[eé]ctrica|mesa\s+sectorial|"
    r"cruz\s+(?:vermella|roja)|banco|caixa|pa[ií]s\s+vasco|comunidad\s+foral|augas|aguas|greenpeace|ecologistas|"
    # Lote 3 (control de Claude, AnuncioG2022-090226; lectura do usuario, 1546).
    r"valedor[a]?\s+do\s+pobo|reina\s+sofia"
    r")\b",
    re.IGNORECASE,
)

# Forma xurídica dunha sociedade ("Casa Raña SAT", "Isabella Sunset Club,
# S. L.", "Red Eléctrica de España, SAU", "ICO, E.P.E."): nunca é persoa.
# En maiúsculas e sobre o texto ORIXINAL ("Sal", "Sat" en Title Case non).
_FORMA_SOCIEDADE_RE = re.compile(
    r"(?<![\w.])(?:S\.?[ \t]?L\.?(?:[ \t]?U\.?)?|S\.?[ \t]?A\.?(?:[ \t]?U\.?)?|SAT|S\.?[ \t]?COOP\.?|"
    r"E\.?[ \t]?P\.?[ \t]?E\.?|SLU|SAU|SLP)(?![\w])"
)

# Comunidades autónomas e países soltos nunha enumeración ("Aragón,
# Baleares, Cataluña, Navarra, País Vasco"): un anaco que só é iso non é persoa.
_TERRITORIOS = frozenset("""
españa portugal francia italia alemania andalucía andalucia aragón aragon asturias baleares
bélgica belgica dinamarca holanda suecia noruega finlandia irlanda austria suiza grecia polonia
rumanía rumania marruecos argentina méxico mexico chile perú peru colombia venezuela brasil
londres parís paris roma lisboa bruselas berlín berlin copenhague madrid barcelona
hungría hungria cuba israel india china xapón japón japon corea bélxica belxica alemaña
suíza suiza marrocos exipto egipto arxentina canadá canada
canarias cantabria cataluña cataluna catalunya extremadura galicia navarra murcia ceuta melilla
euskadi rioja
""".split()) | {"castilla y león", "castilla-la mancha", "costa rica", "país vasco", "pais vasco", "la rioja",
                "reino unido", "estados unidos", "países bajos", "paises bajos", "países baixos",
                "porto rico", "puerto rico", "arabia saudí", "arabia saudita", "asia oriental",
                "el salvador", "costa de marfil", "palma de mallorca", "las palmas de gran canaria",
                "santa cruz de tenerife", "a coruña", "la coruña", "ciudad real", "san sebastián",
                "emerita augusta"}

# Provincias e capitais: moitas son tamén apelidos ("Cuenca", "Burgos",
# "Soria"), así que só se len coma lugar DENTRO dunha enumeración de
# provincias ("Albacete, Cuenca y Guadalajara", BOE-A-2026-5550).
_PROVINCIAS = frozenset("""
álava alava albacete alicante almería almeria asturias ávila avila badajoz barcelona burgos cáceres caceres
cádiz cadiz cantabria castellón castellon ciudad córdoba cordoba coruña cuenca girona gerona granada
guadalajara guipúzcoa guipuzcoa huelva huesca jaén jaen león leon lleida lérida lerida lugo madrid málaga
malaga murcia navarra ourense orense palencia palmas pontevedra rioja salamanca segovia sevilla soria
tarragona teruel toledo valencia valladolid vizcaya bizkaia zamora zaragoza ceuta melilla baleares mérida
merida santander logroño logrono oviedo pamplona vitoria bilbao vigo ferrol santiago cartagena
""".split())

_ACENTOS = str.maketrans("áàäâãéèëêíìïîóòöôõúùüûñçÁÀÄÂÃÉÈËÊÍÌÏÎÓÒÖÔÕÚÙÜÛÑÇ",
                         "aaaaaeeeeiiiiooooouuuuncAAAAAEEEEIIIIOOOOOUUUUNC")


def _e_sociedade(fragmento: str) -> bool:
    m = _FORMA_SOCIEDADE_RE.search(fragmento)
    if m is None:
        return False
    if not re.fullmatch(r"[A-Z]\.[ \t]+[A-Z]\.", m.group()):
        return True
    # "S. L."/"S. A." con espazo tamén son as iniciais dunha persoa
    # ("Barroso Cordeiro, S. L."): só é sociedade se o resto ten algunha
    # palabra que non sexa nome nin apelido do INE ("Isabella Sunset Club").
    resto = fragmento[:m.start()] + " " + fragmento[m.end():]
    palabras = [p for p in re.findall(r"[^\W\d_]{2,}", resto) if p.lower() not in _PARTICULAS_APELIDO]
    nomes, apelidos = nomes_ine.nomes(), nomes_ine.apelidos()
    return any(nomes_ine.normalizar(p) not in nomes and nomes_ine.normalizar(p) not in apelidos for p in palabras)


def _e_organismo(fragmento: str) -> bool:
    return (
        _ORGANISMOS_RE.search(fragmento.translate(_ACENTOS)) is not None
        or _e_sociedade(fragmento)
        or any(" ".join(p.lower().split()) in _TERRITORIOS for p in re.split(r"[,;]", fragmento))
        # "las Cortes de Castilla y León" (BOE-A-2026-12615); sen til, para non
        # tomar o apelido "Cortés de ...".
        or re.search(r"\bCortes\s+(?:de\s+(?:Castilla|Arag[oó]n)|Generales|Valencianas)\b", fragmento) is not None
        # "S.X. DE ORZAMENTOS", "D.X. DE GANDARÍA" (Subdirección/Dirección
        # Xeral no DOG); sen espazo: "D. X." é "don" + unha inicial.
        or re.search(r"(?<![\w.])[SD]\.(?:[XG]\.|[ \t][XG]\.(?=[ \t\n]+(?:DE|DO|DA|de|do|da)\b))", fragmento) is not None
    )


def _peza_non_persoa(peza: str, despois: str = "") -> bool:
    """Anaco entre comas dunha "persoa" que non é nome, no bloque de
    sinatura dun convenio ("–Por la Embajada, el Embajador de España, Nome
    Apelidos, P. S., ...", "–Por Grupo Puentes, Gerente País-Costa Rica,
    Nome"): o cargo, "de <territorio>" e o "P." de "P. S."/"P. D." (corpus
    web lote 2, 30/09/2026)."""
    t = peza.strip()
    if _CARGO_TRAS_NOME_RE.match(" " + t):
        return True
    if re.match(r"P\.[ \t]?[DS]\.", t):  # "P. D. Orden EFD/335/2025"
        return True
    sen_de = re.sub(r"^(?:de|del)[ \t\n]+", "", t)
    if sen_de != t and " ".join(sen_de.lower().split()) in _TERRITORIOS:
        return True
    return t == "P." and re.match(r"[ \t]*[SD]\.", despois) is not None


_PALABRA_ORGANISMO_ALT = r"(?:JUZGADO|XULGADO|TRIBUNAL|AUDIENCIA)"
# "JUZGADO PRIETO, CARLOS" (apelidos, nome; só en maiúsculas).
_APELIDOS_NOME_MAIUSCULAS_RE = re.compile(
    _PALABRA_ORGANISMO_ALT + r"[ \t]+([A-ZÁÉÍÓÚÑ]+),[ \t]*([A-ZÁÉÍÓÚÑ]+)(?:[ \t]+[A-ZÁÉÍÓÚÑ]+)*")
# "CARLOS JUZGADO PRIETO" (nome, apelidos): nome do INE diante e outro apelido detrás.
_NOME_APELIDOS_ORGANISMO_RE = re.compile(
    r"([^\W\d_]+)(?:[ \t]+[^\W\d_]+)?[ \t]+(?i:" + _PALABRA_ORGANISMO_ALT + r")[ \t]+([^\W\d_]+)(?:[ \t]+[^\W\d_]+)?")


def _apelido_de_xulgado_con_nome(entidade) -> bool:
    """"JUZGADO PRIETO, CARLOS" ou "CARLOS JUZGADO PRIETO" (anexos de nomeamentos,
    BOE-A-2025-9417): "Juzgado" é un apelido real, non o organismo. Esixe un nome de pía
    do INE e un apelido do INE (>= 1000) á beira; "JUZGADO PRIMERA INSTANCIA, ..." non casa."""
    if entidade.etiqueta != "PERSOA":
        return False
    t = entidade.texto.strip()
    nomes, apelidos = nomes_ine.nomes(), nomes_ine.apelidos()
    m = _APELIDOS_NOME_MAIUSCULAS_RE.fullmatch(t)
    if m:
        return (apelidos.get(nomes_ine.normalizar(m.group(1)), 0) >= 1000
                and nomes.get(nomes_ine.normalizar(m.group(2)), 0) >= 100)
    m = _NOME_APELIDOS_ORGANISMO_RE.fullmatch(t)
    if m:
        return (nomes.get(nomes_ine.normalizar(m.group(1)), 0) >= 100
                and apelidos.get(nomes_ine.normalizar(m.group(2)), 0) >= 1000)
    return False


def _quitar_organismos(entidade, texto: str) -> list:
    """Tira da entidade os anacos que son o nome dun organismo público (ver
    `_ORGANISMOS_RE`) e devolve os que quedan. Se a entidade non menciona
    ningún organismo, devólvese tal cal."""
    if _apelido_de_xulgado_con_nome(entidade):
        return [entidade]
    # "Presidente Salcedo Roel, Ana" (comisión dun concurso): sen o cargo é unha soa persoa
    # "Apelidos, Nome", nun só anaco e cun só código.
    cargo = _CARGO_DE_COMISION_DIANTE_RE.match(texto, entidade.inicio, entidade.fin)
    if entidade.etiqueta == "PERSOA" and cargo and "," in entidade.texto:
        # ... e sen a profesión pegada detrás ("..., Brais Asociado").
        profesion = _PROFESION_TRAS_NOME_RE.search(texto, cargo.end(), entidade.fin)
        fin = profesion.start() if profesion else entidade.fin
        resto = texto[cargo.end():fin]
        if not _e_organismo(resto) and not any(_peza_non_persoa(m.group().strip(), "") for m in re.finditer(r"[^,;]+", resto)):
            return [Entidade(cargo.end(), fin, resto, entidade.etiqueta, cela=entidade.cela, fila=entidade.fila)]
    if entidade.etiqueta != "PERSOA" or not (
            _e_organismo(entidade.texto)
            or ("," in entidade.texto and any(
                _peza_non_persoa(m.group(), texto[entidade.inicio + m.end():entidade.inicio + m.end() + 4])
                for m in re.finditer(r"[^,;]+", entidade.texto)))):
        return [entidade]
    # Cunha forma xurídica, o resto tamén é o nome da sociedade ("Isabella
    # Sunset Club, S. L."): partir pola coma deixaba "Isabella Sunset Club".
    # Non as comunidades de bens (C.B.), que son persoas físicas.
    if _e_sociedade(entidade.texto):
        return []
    pezas = []
    cursor = entidade.inicio
    while cursor < entidade.fin:
        m = re.compile(r"[,;]").search(texto, cursor, entidade.fin)
        ini, fin = cursor, (m.start() if m else entidade.fin)
        cursor = fin + 1
        while ini < fin and texto[ini] in " \t\n":
            ini += 1
        while fin > ini and texto[fin - 1] in " \t\n":
            fin -= 1
        # "Presidente Salcedo Roel, Ana": a peza do cargo leva os apelidos; quítase só o cargo
        # (antes tirábase a peza enteira e os apelidos quedaban á vista).
        cargo = _CARGO_DE_COMISION_DIANTE_RE.match(texto, ini, fin)
        if cargo and m is not None:
            ini = cargo.end()
        if fin <= ini or _e_organismo(texto[ini:fin]) or _peza_non_persoa(texto[ini:fin], texto[fin:fin + 4]):
            continue
        pezas.append(Entidade(ini, fin, texto[ini:fin], entidade.etiqueta, cela=entidade.cela, fila=entidade.fila))
    return pezas


# Último apelido que o axuste de liña do PDF manda á liña seguinte, soa
# (sinatura do BOE: "...2026.–La Subsecretaria de Hacienda, Nome Apelido1\n
# Apelido2.", caso real do corpus web 28/09/2026: "Apelido2" quedaba á
# vista). Só cando a persoa remata xusto no fin da liña e a liña seguinte
# non ten NADA máis ca 1-2 palabras con forma de apelido (e un punto ou
# coma): calquera outra cousa nesa liña indica que xa é outro contido.
_APELIDO_SOLTO_LIÑA_SEGUINTE = re.compile(
    # "Pérez\nde Andrade": o conector do apelido tamén salta de liña.
    r"[ \t]*\n[ \t]*(?P<resto>(?:" + _CONECTOR_NOME_RE + r"[ \t]+){0,2}" + _PALABRA_CAPITALIZADA_RE
    + r"(?:[ \t]+(?:" + _CONECTOR_NOME_RE + r"[ \t]+){0,2}" + _PALABRA_CAPITALIZADA_RE + r")?)"
    r"[ \t]*[.,]?[ \t]*(?=\n|\Z)"
)


_APELIDO_LIÑA_SEGUINTE_E_FRASE = re.compile(
    r"[ \t]*\n[ \t]*(?P<resto>" + _PALABRA_CAPITALIZADA_RE + r"(?:[ \t]+" + _PALABRA_CAPITALIZADA_RE + r")?)"
    r"(?=[ \t]*,[ \t]*(?:quien|que|con|mayor|vecin|veciñ|natural|actuando|titular|provist|domiciliad|nacid|en[ \t]+su)"
    r"|[ \t]+con[ \t]+(?:DNI|NIE|D\.N\.I\.|pasaporte))",
    re.IGNORECASE,
)
_TRATAMENTO_ANTES_DA_PERSOA_RE = re.compile(r"(?:\b(?:[Dd]o[ñn]a?|D\.|Dña\.|Sr\.|Sra\.|D[ªa]\.?))[ \t]*\Z")

# Epígrafes que adoitan ir soas nunha liña xusto despois dunha sinatura.
_EPIGRAFES_TRAS_SINATURA = {"anexo", "anexos", "apéndice", "apendice", "índice", "indice", "sumario"}


def _estender_apelido_na_liña_seguinte(entidades, ocupado, texto: str, suavizado: str) -> None:
    for entidade in list(entidades):
        if entidade.etiqueta != "PERSOA" or entidade not in entidades or entidade.multilinea:
            continue
        m = _APELIDO_SOLTO_LIÑA_SEGUINTE.match(suavizado, entidade.fin)
        if not m and _TRATAMENTO_ANTES_DA_PERSOA_RE.search(texto, max(0, entidade.inicio - 12), entidade.inicio):
            # "doña Suzana Marija Curic\nŠpehar, quien actúa" (BOE-A-2025-21164,
            # FUGA): o apelido salta de liña e a frase segue nela.
            m = _APELIDO_LIÑA_SEGUINTE_E_FRASE.match(suavizado, entidade.fin)
        if not m:
            continue
        ini, fin = m.span("resto")
        palabras = suavizado[ini:fin].split()
        # unha liña TODA en maiúsculas despois dun nome que non o está é
        # unha epígrafe ("ANEXO"), non o apelido que saltou de liña
        if texto[ini:fin].isupper() and not texto[entidade.inicio:entidade.fin].isupper():
            continue
        if (_e_organismo(texto[ini:fin])
                or _e_soamente_prosa_ou_cargo(suavizado, ini, fin)
                or any(p.lower() in _PALABRAS_NON_NOME or p.lower() in _EPIGRAFES_TRAS_SINATURA
                       for p in palabras)
                or _CARGO_TRAS_NOME_RE.search(" " + suavizado[ini:fin])):
            continue
        # spaCy pode ter tomado ese apelido solto coma outra persoa ou coma
        # lugar ("Milán"): se é UNHA soa entidade dentro da liña, intégrase.
        dentro = [e for e in entidades if e is not entidade and e.inicio < fin and e.fin > ini]
        if len(dentro) > 1 or (dentro and (
                dentro[0].etiqueta not in ("PERSOA", "LOCALIZACION")
                or dentro[0].inicio < ini or dentro[0].fin > fin)):
            continue
        if any(ocupado[i] for i in range(ini, fin)
               if not (dentro and dentro[0].inicio <= i < dentro[0].fin)):
            continue
        if dentro:
            entidades.remove(dentro[0])
        entidade.fin = fin
        entidade.texto = texto[entidade.inicio:fin]
        entidade.multilinea = True
        for i in range(ini, fin):
            ocupado[i] = True


def _partir_persoa_por_linas(entidade, texto: str, suavizado: str) -> list:
    """Parte `entidade` por saltos de liña/páxina e devolve só os anacos con
    forma de nome: sen a etiqueta previa a ":" ("Testemuña: Rosa..." ->
    "Rosa..."), descartando o anaco que é el mesmo unha etiqueta (vai
    seguido de ":"), só tratamentos/cargos, ou palabras de prosa coñecidas
    (`_e_soamente_prosa_ou_cargo`) -- mesma comprobación tanto se hai
    salto de liña coma se non. Sen esixir maiúscula na entidade ENTEIRA
    (`esixir_maiuscula=False`): pode vir do recoñecedor de nomes en
    minúscula (A19), que xa esixe os SEUS propios anclaxes (verbo +
    nome de pía) para non confundirse con prosa."""
    if not _SALTO_LINA_RE.search(texto, entidade.inicio, entidade.fin):
        if _e_soamente_prosa_ou_cargo(
            suavizado, entidade.inicio, entidade.fin, esixir_maiuscula=False
        ):
            return []
        return [entidade]
    pezas = []
    cursor = entidade.inicio
    while cursor < entidade.fin:
        m = _SALTO_LINA_RE.search(texto, cursor, entidade.fin)
        ini, fin = cursor, (m.start() if m else entidade.fin)
        cursor = fin + 1
        dous_puntos = max(suavizado.rfind(":", ini, fin), suavizado.rfind(";", ini, fin))
        if dous_puntos >= 0:
            ini = dous_puntos + 1
        while ini < fin and suavizado[ini] in " \t":
            ini += 1
        while fin > ini and suavizado[fin - 1] in " \t,":
            fin -= 1
        if fin <= ini or suavizado[fin:fin + 3].lstrip(" \t").startswith(":"):
            continue
        recortado = _recortar_tratamentos(texto, suavizado, ini, fin)
        if recortado is None:
            continue
        ini, fin = recortado
        # "Xoán Pérez\nde Andrade": un apelido con conector que o axuste de
        # liña mandou só á liña seguinte segue sendo da mesma persoa (antes
        # tirábase e "Andrade" quedaba á vista coma lugar).
        if (pezas and pezas[-1].fin <= ini and not texto[pezas[-1].fin:ini].strip()
                and _continua_na_liña_seguinte(pezas[-1], suavizado, ini, fin)):
            anterior = pezas.pop()
            pezas.append(Entidade(anterior.inicio, fin, texto[anterior.inicio:fin], entidade.etiqueta, multilinea=True))
            continue
        if _e_soamente_prosa_ou_cargo(suavizado, ini, fin):
            continue
        pezas.append(Entidade(ini, fin, texto[ini:fin], entidade.etiqueta))
    return pezas


def _nome_de_pia_partido(a, b, medio: str) -> bool:
    """"nomeouse a María\nJesús Ferro Godos" (AnuncioL135, lote 3): ao final
    da liña só un nome de pía e na seguinte outro nome de pía e apelidos."""
    # Tamén tras un cargo e coma ("Función Pública, María\nHilda Jurado Noguera",
    # BOE-A-2026-2939): o cargo recórtase despois.
    pia = re.search(r"(?:^|,[ \t]+)([^\W\d_]+)\Z", a.texto)
    if medio.startswith("-") or pia is None:
        return False
    nomes = nomes_ine.nomes()
    palabras_b = b.texto.split()
    return (len(palabras_b) >= 3 and nomes_ine.normalizar(pia.group(1)) in nomes
            and nomes_ine.normalizar(palabras_b[0]) in nomes and "," not in b.texto)


# Palabra con maiúscula que o axuste de liña pode partir cun guión ("Es-\nteiro").
_PALABRA_PARTIBLE_RE = r"[A-ZÁÉÍÓÚÑÜ][a-záéíóúñüàèìòùç·'’]+(?:-\n[ \t]*[a-záéíóúñüàèìòùç·'’]+)?"
_NOME_PARTIDO_CON_GUION_RE = re.compile(
    r"(?<![\w-])" + _PALABRA_PARTIBLE_RE
    + r"(?:[ \t]+(?:(?:de|del|da|do|de la|de los)[ \t]+)?" + _PALABRA_PARTIBLE_RE + r"){1,3}(?![\w-])"
)


def _detectar_persoas_partidas_con_guion(texto: str, ocupado: list) -> list:
    """"Ana Salcedo Roel, Xoán Páez Es-\nteiro e Brais Páez Estei-\nro" (AnuncioG0427-200924-0004_gl,
    lote 6): o guión de fin de liña partía un apelido e a persoa quedaba á vista
    enteira ou só co anaco final. Nome de pía do INE + apelidos do INE (xa unidos),
    con polo menos un partido por "-\n" e a seguinte liña en minúscula."""
    nomes, apelidos = nomes_ine.nomes(), nomes_ine.apelidos()
    atopadas = []
    for m in _NOME_PARTIDO_CON_GUION_RE.finditer(texto):
        if "-\n" not in m.group() or any(ocupado[m.start():m.end()]):
            continue
        palabras = re.sub(r"-\n[ \t]*", "", m.group()).split()
        contido = [p for p in palabras if p.lower() not in _PARTICULAS_APELIDO]
        if len(contido) < 2 or nomes_ine.normalizar(contido[0]) not in nomes:
            continue
        if not all(nomes_ine.normalizar(p) in apelidos for p in contido[1:]):
            continue
        atopadas.append(Entidade(m.start(), m.end(), m.group(), "PERSOA", multilinea=True))
    return atopadas


_MAIUSCULA = "A-ZÁÉÍÓÚÑÜÀÈÌÒÙÇ"
_PALABRA_NOME = r"[" + _MAIUSCULA + r"][a-záéíóúñüàèìòùçï]+"
# Anacos de nome de pía que quedaban á vista diante dos apelidos tapados (lote 6,
# BOE-A-2024-14397 e BOE-A-2024-13946). Cada un ancorado nun nome de pía do INE
# (grupo "nome") ou nunha forma que só pode ser un nome partido.
_PREFIXOS_NOME_DE_PIA = [
    # "Maria dels Àngels Fuster": conector catalán tras o nome de pía. Só "dels"/"de les":
    # con "de la" casaba "Puerto de la Bahía de Cádiz" ("Puerto" tamén é nome de pía).
    re.compile(r"(?<![\w·])(?P<nome>" + _PALABRA_NOME + r")[ \t]+(?:dels|de les)[ \t]+\Z"),
    # "Marcel·Lí Del Olmo": o punto volado do "l·l" catalán cortaba o nome
    re.compile(r"(?<![\w·])[" + _MAIUSCULA + r"][a-záéíóúñüàèìòùç]*·\Z"),
    # "M.ªElena Benítez" (sen espazo), "M Luisa De La Fuente", "Mª Luisa ..."
    re.compile(r"(?<![\w.])M(?:\.ª|\.a|ª|\.)?[ \t]*(?P<nome>" + _PALABRA_NOME + r")[ \t]+\Z"),
    # "Clara M Pereira", "Ana M. Pereira": nome de pía + inicial solta
    re.compile(r"(?<![\w.])(?P<nome>" + _PALABRA_NOME + r")[ \t]+[" + _MAIUSCULA + r"]\.?[ \t]+\Z"),
]
# "M Carmen Pereira": a persoa xa empeza no nome de pía e queda diante só a "M"
# (María) solta (BOE-A-2024-13946, 6 veces).
_M_SOLTA_DIANTE_RE = re.compile(r"(?<![\w.])M(?:\.ª|\.a|ª|\.)?[ \t]+\Z")
_SO_INICIAIS_ENTRE_RE = re.compile(r"[ \t]+(?:[" + _MAIUSCULA + r"]\.[ \t]?){1,4}[ \t]*")


def _completar_nome_de_pia(entidades: list, texto: str) -> list:
    """Estende cara á esquerda unha persoa cando o que vai xusto diante é o seu
    nome de pía nunha forma que os detectores non collían (`_PREFIXOS_NOME_DE_PIA`),
    e xunta dous anacos da mesma persoa separados só por iniciais ("Kamal M.R.F.
    Amin Kamal", BOE-A-2024-20240: "M.R.F." quedaba á vista)."""
    nomes = nomes_ine.nomes()
    persoas = sorted((e for e in entidades if e.etiqueta == "PERSOA"), key=lambda e: e.inicio)
    for a, b in zip(persoas, persoas[1:]):
        # "D." solto entre dous nomes é o tratamento da seguinte persoa nunha lista
        # sen comas ("D. Xoán Páez Veiga D. Manuel Castro"), non unha inicial.
        if (a in entidades and b in entidades and _SO_INICIAIS_ENTRE_RE.fullmatch(texto, a.fin, b.inicio)
                and texto[a.fin:b.inicio].strip() not in ("D.", "Dª.", "Dª")):
            entidades.remove(b)
            a.fin, a.texto = b.fin, texto[a.inicio:b.fin]
            a.multilinea = a.multilinea or b.multilinea
    fins = sorted(e.fin for e in entidades)
    for e in (e for e in entidades if e.etiqueta == "PERSOA"):
        cambiou = True
        while cambiou:
            cambiou = False
            antes = texto[max(0, e.inicio - 40):e.inicio]
            for patron in _PREFIXOS_NOME_DE_PIA:
                m = patron.search(antes)
                if m is None or ("nome" in patron.groupindex and nomes_ine.normalizar(m.group("nome")) not in nomes):
                    continue
                novo_inicio = e.inicio - (len(antes) - m.start())
                if any(novo_inicio < f <= e.inicio for f in fins if f != e.fin):
                    continue  # non comer outra entidade
                e.inicio, e.texto = novo_inicio, texto[novo_inicio:e.fin]
                cambiou = True
                break
            if not cambiou:
                m = _M_SOLTA_DIANTE_RE.search(antes)
                primeira = e.texto.split()[0] if e.texto.split() else ""
                if m and nomes_ine.normalizar(primeira) in nomes:
                    e.inicio = e.inicio - (len(antes) - m.start())
                    e.texto = texto[e.inicio:e.fin]
    return entidades


_PALABRAS_LIÑA_SEGUINTE_RE = re.compile(
    r"[ \t]*\n[ \t]*(" + _PALABRA_CAPITALIZADA_RE + r"(?:[ \t]+" + _PALABRA_CAPITALIZADA_RE + r"){0,2})(?![\w-])")


_CONECTOR_E_APELIDO_LIÑA_SEGUINTE_RE = re.compile(
    r"[ \t]+(?:de|del|da|do|dos|das|de[ \t]+la|de[ \t]+los|de[ \t]+las)[ \t]*\n[ \t]*(" + _PALABRA_CAPITALIZADA_RE
    # ata dous apelidos: "del\nCampo Serrano" ("Serrano" quedaba á vista, BOE-A-2025-6823)
    + r"(?:[ \t]+" + _PALABRA_CAPITALIZADA_RE + r")?)(?![\w-])")


def _xuntar_anacos_da_mesma_persoa(entidades: list, texto: str, suavizado: str) -> list:
    """Dous anacos que son a mesma persoa (lote 6, metade de desenvolvemento):
    "Maria" + " dels " + "Àngels Galán Viana" ("dels" quedaba á vista), "Antonio" e
    "Fraga Millán" en dúas liñas (dous códigos), e "Antonio Fraga" cun
    apelido solto na liña seguinte que ningún detector collía ("Millán" á vista).
    Na liña seguinte úsase o mesmo criterio ca `_continua_na_liña_seguinte`."""
    nomes = nomes_ine.nomes()
    persoas = sorted((e for e in entidades if e.etiqueta == "PERSOA"), key=lambda e: e.inicio)
    for a, b in zip(persoas, persoas[1:]):
        if a not in entidades or b not in entidades:
            continue
        medio = texto[a.fin:b.inicio]
        dels = (re.fullmatch(r"[ \t]+(?:dels|de les)[ \t]+", medio) and len(a.texto.split()) == 1
                and nomes_ine.normalizar(a.texto) in nomes)
        liña = (re.fullmatch(r"[ \t]*\n[ \t]*", medio)
                and _continua_na_liña_seguinte(a, suavizado, b.inicio, b.fin))
        if dels or liña:
            entidades.remove(b)
            a.fin, a.texto, a.multilinea = b.fin, texto[a.inicio:b.fin], True
    ocupados = sorted((e.inicio, e.fin) for e in entidades)
    apelidos = nomes_ine.apelidos()
    for a in [e for e in entidades if e.etiqueta == "PERSOA"]:
        # Conector ao final da liña e apelido na seguinte ("Manuel Gallego del\nAldana",
        # BOE-B-2025-14097): "del Aldana" quedaba á vista.
        c = _CONECTOR_E_APELIDO_LIÑA_SEGUINTE_RE.match(suavizado, a.fin)
        fin_apelidos = None
        if c and c.group(1).split()[0] not in ("San", "Santa", "Santo", "Sant"):  # "de\nSan Lázaro": un lugar
            # só os apelidos do INE seguidos: "Campo Serrano" enteiro, "Campo Presidenta" só "Campo"
            fin_apelidos = c.start(1)
            for p in re.finditer(r"\S+", c.group(1)):
                if nomes_ine.normalizar(p.group()) not in apelidos:
                    break
                fin_apelidos = c.start(1) + p.end()
            if fin_apelidos == c.start(1) or re.match(r"[ \t]*\d", suavizado[fin_apelidos:fin_apelidos + 20]):
                fin_apelidos = None
        if fin_apelidos is not None:
            solapan = [e for e in entidades if e is not a and e.inicio < fin_apelidos and a.fin < e.fin]
            # O apelido tomado por un lugar ("Aldana") cede; outra persoa, nunca.
            if all(e.etiqueta != "PERSOA" and a.fin <= e.inicio and e.fin <= fin_apelidos for e in solapan):
                for e in solapan:
                    entidades.remove(e)
                a.fin, a.texto, a.multilinea = fin_apelidos, texto[a.inicio:fin_apelidos], True
                continue
        m = _PALABRAS_LIÑA_SEGUINTE_RE.match(suavizado, a.fin)
        if not m or any(i < m.end(1) and m.start(1) < f for i, f in ocupados):
            continue
        if _continua_na_liña_seguinte(a, suavizado, m.start(1), m.end(1)):
            a.fin, a.texto, a.multilinea = m.end(1), texto[a.inicio:m.end(1)], True
    return entidades


def _unir_persoas_partidas_por_guion(entidades: list, texto: str) -> list:
    """"don Manuel Galán-\nSiles Calabuig": o guion de fin de liña deixaba
    dúas persoas (dous códigos) -- corpus web lote 2, 30/09/2026."""
    persoas = sorted((e for e in entidades if e.etiqueta == "PERSOA"), key=lambda e: e.inicio)
    for a, b in zip(persoas, persoas[1:]):
        if a not in entidades or b not in entidades:
            continue
        medio = texto[a.fin:b.inicio]
        if re.fullmatch(r"-?[ \t]*\n[ \t]*", medio) and (
                a.texto.endswith("-") or medio.startswith("-") or _nome_de_pia_partido(a, b, medio)):
            entidades.remove(b)
            a.fin = b.fin
            a.texto = texto[a.inicio:b.fin]
            a.multilinea = True
    return entidades


def _continua_na_liña_seguinte(anterior, suavizado: str, ini: int, fin: int) -> bool:
    """O anaco [ini, fin) da liña seguinte é o resto do nome `anterior`:
    apelido con conector ("Pérez\nde Andrade"), apelido partido por guion
    ("Galán-\nSiles Calabuig") ou só o nome de pía antes do salto e só
    apelidos do INE despois ("don Eduardo\nBaltasar Blanco"). Corpus web
    lote 2 (30/09/2026): cada anaco levaba o seu código."""
    if _APELIDO_CON_CONECTOR_RE.fullmatch(suavizado, ini, fin):
        return True
    palabras = suavizado[ini:fin].split()
    contido = [p for p in palabras if p.lower() not in _PARTICULAS_APELIDO]
    if not contido or len(contido) > 3 or not _tramo_de_nome(suavizado[ini:fin]):
        return False
    if anterior.texto.endswith("-"):
        return True
    # Só nome(s) de pía antes do salto ("Marta", "Vicente Luis") e só apelidos
    # despois ("Gorostiza Ferrándiz de Pinedo", BOE-A-2026-14304).
    previas = anterior.texto.split()
    nomes, apelidos = nomes_ine.nomes(), nomes_ine.apelidos()
    if (len(previas) <= 2 and all(nomes_ine.normalizar(p) in nomes for p in previas)
            and all(nomes_ine.normalizar(p) in apelidos for p in contido)):
        return True
    # Nome(s) e PRIMEIRO apelido antes do salto e só o segundo despois ("doña Elena
    # Esperanza Ramírez\nDuarte (Elena E. Ramírez Duarte)", BOE-A-2025-9720, revisión
    # do lote 5): levaba outro código, ou quedaba á vista. Nunca unha liña de lugar
    # e data ("...\nMadrid, 3 de marzo"): moitos topónimos son tamén apelidos.
    return (len(contido) == 1 and 2 <= len(previas) <= 3
            and all(nomes_ine.normalizar(p) in nomes for p in previas[:-1])
            and nomes_ine.normalizar(previas[-1]) in apelidos
            and nomes_ine.normalizar(contido[0]) in apelidos
            # nin unha cela de táboa: provincia seguida do importe ("Pontevedra 3.000,00 €", lote 5)
            and not re.match(r"[ \t]*(?:,[ \t]*(?:a[ \t]+)?)?\d", suavizado[fin:]))


_APELIDO_CON_CONECTOR_RE = re.compile(
    r"(?:" + _CONECTOR_NOME_RE + r"[ \t]+){1,2}" + _PALABRA_CAPITALIZADA_RE
    + r"(?:[ \t]+" + _PALABRA_CAPITALIZADA_RE + r")?"
)


# --- Celas de columnas de dato persoal (táboas PDF, `taboas_pdf.py`) -------
#
# A cabeceira da columna di que a cela é un nome ou un documento; aquí só
# se comproba que o contido NON sexa claramente outra cousa (cela baleira,
# "Desierto", un rótulo de formulario, un organismo). Se non pasa, non se
# forza nada e quedan os patróns e o NER de sempre.

_PALABRA_CELA_NOME_RE = re.compile(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*\.?,?")
_CELAS_NON_NOME = frozenset("""
desierto desierta desiertos desiertas deserto deserta vacante vacantes anulado anulada anulada
sin adjudicar non adxudicado non adxudicada no adjudicado no adjudicada ninguno ninguna
""".split())
_SIGNOS_BORDO_CELA = " \t\n,;.:()"


# Rótulos dun formulario en branco ("NOMBRE Y APELLIDOS", "DOMICILIO A
# EFECTOS DE NOTIFICACIÓN", "LOCALIDAD", "TELÉFONO"): tapábanse coma persoas
# (BOE-A-2026-15844, lectura de Claude 30/09/2026).
_ROTULOS_FORMULARIO = frozenset("""
nombre nome apellidos apelidos domicilio enderezo dirección direccion localidad localidade
provincia municipio concello teléfono telefono correo electrónico electronico nif nie dni
pasaporte cód cod código codigo postal fecha data firma sinatura solicitante representante
empleo emprego cp fax móvil movil situación situacion destino nacimiento nacemento
""".split())  # "Empleo", "CP": formulario baleiro de BOE-A-2026-685 (lote 3)


def _texto_de_cela_e_nome(fragmento: str) -> bool:
    palabras = fragmento.split()
    if not palabras or ":" in fragmento or _e_organismo(fragmento):
        return False
    if any(p.strip(".,()").lower() in _ROTULOS_FORMULARIO for p in palabras):
        return False
    if " ".join(p.strip(".,").lower() for p in palabras) in _CELAS_NON_NOME:
        return False
    if any(p.strip(".,").lower() in _CELAS_NON_NOME for p in palabras):
        return False
    letras = 0
    for palabra in palabras:
        if not _PALABRA_CELA_NOME_RE.fullmatch(palabra):
            return False
        nucleo = palabra.strip(".,")
        if nucleo.lower() in _CONECTORES_NOME:
            continue
        if not nucleo[0].isupper():
            return False
        letras += len(nucleo)
    return letras >= 2


def _tramos_libres(inicio: int, fin: int, ocupado: list) -> list:
    """[inicio, fin) sen as posicións xa ocupadas (un DNI dentro da cela
    "Persoa interesada/DNI"), en tramos seguidos."""
    tramos = []
    for i in range(inicio, fin):
        if ocupado[i]:
            continue
        if tramos and tramos[-1][1] == i:
            tramos[-1][1] = i + 1
        else:
            tramos.append([i, i + 1])
    return [tuple(t) for t in tramos]


def _recortar_bordos_cela(texto: str, inicio: int, fin: int) -> tuple:
    while inicio < fin and texto[inicio] in _SIGNOS_BORDO_CELA:
        inicio += 1
    while fin > inicio and texto[fin - 1] in _SIGNOS_BORDO_CELA:
        fin -= 1
    return inicio, fin


# Código dunha columna de documento: polo menos 5 díxitos, ou 4 con letra
# ("A1135", o final do NRP), ou 3 con asteriscos (o DNI enmascarado do BOE,
# "***4567**"). Un número de 4 cifras solto (un ano) non vale.
_CODIGO_CELA_RE = re.compile(r"[A-Za-z0-9*]+")
_CIF_RE = re.compile(r"[ABCDEFGHJNPQRSUVW]\d{7}[0-9A-J]")  # empresa, non persoa


def _e_codigo_de_documento(codigo: str) -> bool:
    digitos = sum(c.isdigit() for c in codigo)
    if _CIF_RE.fullmatch(codigo.upper()):
        return False
    return (digitos >= 5
            or (digitos >= 4 and any(c.isalpha() for c in codigo))
            or (digitos >= 3 and "*" in codigo))


def _titulares_da_cela_mixta(texto: str, inicio: int, fin: int, ocupado: list, fila: int) -> list:
    """Cela dunha columna "Propietario"/"Titular": cada anaco separado por ";"
    é unha persoa se TODAS as súas palabras son nomes ou apelidos do INE e
    hai polo menos un nome de pía ("Panduro Galan Maria Luisa", "Vera Sastre
    Jose Manuel (Herederos)"); "Principado de Asturias" ou unha empresa non."""
    nomes, apelidos = nomes_ine.nomes(), nomes_ine.apelidos()
    atopadas = []
    for m in re.finditer(r"[^;]+", texto[inicio:fin]):
        a, b = inicio + m.start(), inicio + m.end()
        anaco = texto[a:b]
        herdeiros = re.search(r"\s*\((?:Herederos|Herdeiros|y otros|e outros)\)\s*$", anaco, re.IGNORECASE)
        if herdeiros:
            b = a + herdeiros.start()
        while a < b and texto[a] in " \t\n,.":
            a += 1
        while b > a and texto[b - 1] in " \t\n,.":
            b -= 1
        palabras = [p for p in re.findall(r"[^\W\d_]+", texto[a:b]) if p.lower() not in _PARTICULAS_APELIDO]
        if len(palabras) < 2 or _e_organismo(texto[a:b]) or any(ocupado[a:b]):
            continue
        k = [nomes_ine.normalizar(p) for p in palabras]
        if all(x in nomes or x in apelidos for x in k) and any(x in nomes for x in k):
            atopadas.append(Entidade(a, b, texto[a:b], "PERSOA", multilinea=True, cela=True, fila=fila))
    return atopadas


def _entidades_de_celas(texto: str, celas: list, ocupado: list, directas: list) -> list:
    """Entidades PERSOA/DOCUMENTO das celas de columnas de dato persoal.
    Os identificadores directos xa detectados (DNI con letra...) gañan:
    só se engade o que queda libre, pero reciben a fila da cela para
    ligalos co seu titular. As partes dunha mesma persoa en columnas
    veciñas da mesma fila ("1º apelido | 2º apelido | Nome") únense nunha
    soa entidade se no texto só as separan espazos."""
    atopadas = []
    persoas_por_fila = {}
    for cela in celas:
        for peza_inicio, peza_fin in cela.pezas:
            if cela.tipo == "CABECEIRA":
                continue
            if cela.tipo == "DOCUMENTO":
                for e in directas:
                    if e.etiqueta in DOCUMENTOS_DE_IDENTIDADE and peza_inicio <= e.inicio < peza_fin:
                        e.fila = cela.fila
                for m in _CODIGO_CELA_RE.finditer(texto, peza_inicio, peza_fin):
                    if _e_codigo_de_documento(m.group()) and not any(ocupado[m.start():m.end()]):
                        atopadas.append(Entidade(m.start(), m.end(), m.group(), "DOCUMENTO_IDENTIDADE",
                                                 cela=True, fila=cela.fila))
                continue
            if cela.tipo == "MIXTA":
                atopadas.extend(_titulares_da_cela_mixta(texto, peza_inicio, peza_fin, ocupado, cela.fila))
                continue
            for tramo_inicio, tramo_fin in _tramos_libres(peza_inicio, peza_fin, ocupado):
                inicio, fin = _recortar_bordos_cela(texto, tramo_inicio, tramo_fin)
                if fin > inicio and _texto_de_cela_e_nome(texto[inicio:fin]):
                    persoas_por_fila.setdefault(cela.fila, []).append([inicio, fin])
    for fila, tramos in persoas_por_fila.items():
        tramos.sort()
        unidos = [tramos[0]]
        for inicio, fin in tramos[1:]:
            if not texto[unidos[-1][1]:inicio].strip():
                unidos[-1][1] = max(unidos[-1][1], fin)
            else:
                unidos.append([inicio, fin])
        for inicio, fin in unidos:
            atopadas.append(Entidade(inicio, fin, texto[inicio:fin], "PERSOA", multilinea=True, cela=True, fila=fila))
    for entidade in atopadas:
        for i in range(entidade.inicio, entidade.fin):
            ocupado[i] = True
    return atopadas


_ETIQUETAS_PERSOA = ("PERSOA", "PERSOA_EXENTA_CARGO_PUBLICO")
_ETIQUETAS_ABSORBIBLES = ("PERSOA", "LOCALIZACION", "ORGANIZACION")
_PALABRA_NOME_PROPAGABLE_RE = re.compile(r"[A-ZÁÉÍÓÚÑÜ][^\W\d_]*(?:[-'’][^\W\d_]+)*")
_SEPARADOR_NOME_RE = r"(?:[ \t]+|[ \t]*\n[ \t]*)"


_PIA_ANTES_RE = re.compile(r"(?:^|(?<=[\n\t])|(?<=\d )|(?<=[,;:] ))(M[ªa]\.?|M\.ª|[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)[ \t]\Z")
_APELIDOS_ANTES_DO_GUION_RE = re.compile(
    r"(?:^|\n)(?:\d+[ \t]+)?((?:[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑa-záéíóúñ]+[ \t]+){0,2}[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑa-záéíóúñ]+)-[ \t]*\n[ \t]*\Z")
_ULTIMA_PALABRA_DA_FICHA_RE = re.compile(r"[ \t]+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)[ \t]*(?=\n|\Z)")
_ETIQUETA_DE_FICHA_RE = re.compile(r"(?:^|\n)[^\n:]{3,40}:[ \t]*\Z")
_CONXUNCION_APELIDO_RE = re.compile(r"[ \t]+[iy][ \t]+([A-ZÁÉÍÓÚÑ][a-záéíóúñàèòïç·]+)(?=[ \t]*(?:[.,;)]|\n|\Z))")


def _completar_bordos_do_nome(entidades: list, texto: str) -> None:
    """Lote 4 (03/10/2026), FUGAS: o primeiro nome de pía ao principio dunha
    liña dunha táboa quedaba fóra ("Florencio PERSOA [ENDEREZO]", "Mª PERSOA"),
    e o último apelido tras a conxunción catalá ou castelá ("Josep Maria
    Vallès i Navarro.")."""
    nomes, apelidos = nomes_ine.nomes(), nomes_ine.apelidos()
    ocupado = {i for e in entidades for i in range(e.inicio, e.fin)}
    for e in entidades:
        if e.etiqueta != "PERSOA" or e.cela:
            continue
        # "17 REVUELTA SANCHEZ-\nBEATO, M. AURORA" (BOE-A-2025-15144, FUGA):
        # apelido partido con guión ao final da liña anterior dunha táboa.
        guion = _APELIDOS_ANTES_DO_GUION_RE.search(texto, max(0, e.inicio - 60), e.inicio)
        if guion and not any(i in ocupado for i in range(guion.start(1), e.inicio)) \
                and all(apelidos.get(nomes_ine.normalizar(p), 0) >= 100 for p in guion.group(1).split()):
            ocupado.update(range(guion.start(1), e.inicio))
            e.inicio = guion.start(1)
            e.multilinea = True
        antes = _PIA_ANTES_RE.search(texto, max(0, e.inicio - 20), e.inicio)
        if antes and not any(i in ocupado for i in range(antes.start(1), antes.end(1))):
            pia = antes.group(1)
            if re.fullmatch(r"M[ªa]\.?|M\.ª", pia) or nomes.get(nomes_ine.normalizar(pia), 0) >= 100:
                ocupado.update(range(antes.start(1), e.inicio))
                e.inicio = antes.start(1)
        # "Peticionario: Eduardo Guerrero Mayo\n" (BOE-B-2025-35020): nunha liña
        # de ficha, a palabra con maiúscula que pecha a liña é do nome
        # ("Marzo" non está no INE coma apelido).
        peche = _ULTIMA_PALABRA_DA_FICHA_RE.match(texto, e.fin)
        if peche and _ETIQUETA_DE_FICHA_RE.search(texto, max(0, e.inicio - 50), e.inicio) \
                and len(e.texto.split()) >= 2 and not any(i in ocupado for i in range(e.fin, peche.end(1))) \
                and not _e_organismo(peche.group(1)) and peche.group(1).lower() not in _TERRITORIOS:
            ocupado.update(range(e.fin, peche.end(1)))
            e.fin = peche.end(1)
        despois = _CONXUNCION_APELIDO_RE.match(texto, e.fin)
        if despois and apelidos.get(nomes_ine.normalizar(despois.group(1)), 0) >= 100 \
                and not any(i in ocupado for i in range(e.fin, despois.end())) \
                and len(e.texto.split()) >= 2:
            ocupado.update(range(e.fin, despois.end()))
            e.fin = despois.end()
        e.texto = texto[e.inicio:e.fin]


def _rua_sen_tipo_de_via(entidades: list, texto: str) -> None:
    """"Reina Sofía, Santa Isabel, 52,\n28012 Madrid" (BOE-A-2026-1546): nome
    + número de portal + código postal é un enderezo, non unha persoa (o mesmo
    enderezo con "C/" xa saía [ENDEREZO])."""
    for e in entidades:
        if e.etiqueta != "PERSOA" or e.cela:
            continue
        m = re.match(r",[ \t]*\d{1,4}[A-Za-z]?(?=,?[ \t\n]*\d{5}\b)", texto[e.fin:e.fin + 12])
        if m:
            e.etiqueta = "ENDEREZO"
            e.fin += m.end()
            e.texto = texto[e.inicio:e.fin]


def _recortar_reina_sofia(entidade, texto: str) -> None:
    """"Centro de Arte Reina\nSofía, Manuel Sobral Lourido" (BOE-A-2026-1546,
    lectura do usuario): partida por liñas, a entidade empeza en "Sofía," e o
    "Reina" queda na liña anterior; "Sofía" é do museo, non da persoa."""
    m = re.match(r"Sof[ií]a,?[ \t\n]+", entidade.texto)
    if m and m.end() < len(entidade.texto) and re.search(r"\bReina[ \t\n]+\Z",
                                                          texto[max(0, entidade.inicio - 10):entidade.inicio]):
        entidade.inicio += m.end()
        entidade.texto = texto[entidade.inicio:entidade.fin]


def _resto_con_forma_de_nome(texto: str) -> bool:
    """"Eloy Sáez Herrero" si; "Patronato de la Tate Gallery" ou "Pobo" non."""
    palabras = [p for p in re.findall(r"[^\W\d_]+", texto) if p.lower() not in _PARTICULAS_APELIDO]
    if len(palabras) < 2 or not all(p[:1].isupper() for p in palabras) or _e_organismo(texto):
        return False
    nomes, apelidos = nomes_ine.nomes(), nomes_ine.apelidos()
    return nomes.get(nomes_ine.normalizar(palabras[0]), 0) >= 100 or \
        sum(apelidos.get(nomes_ine.normalizar(p), 0) >= 1000 for p in palabras[1:]) >= 2


def _outras_aparicions_da_mesma_persoa(entidades: list, texto: str, texto_suavizado: str,
                                        ocupado_directas: list) -> list:
    """Cada persoa xa detectada (nome de 2+ palabras) búscase noutras
    aparicións LITERAIS do documento, tamén partidas por un salto de liña,
    e todas levan o mesmo trato. Lote 3 (03/10/2026):
    - FUGA: o sumario do DOG ("a Xiana\nFerrín-Ulla Bacarizo") quedaba á
      vista aínda que o corpo tapase a mesma persoa;
    - criterio CENDOJ (decisión do usuario): se NUNHA aparición a persoa leva
      cargo exento ("la Magistrada doña X"), queda á vista en TODAS --
      antes tapábase alí onde o cargo non ía ao lado (BOE-A-2026-2890)."""
    persoas = [e for e in entidades
               if e.etiqueta in _ETIQUETAS_PERSOA and not e.cela]
    por_chave = {}
    nomes = nomes_ine.nomes()
    for e in persoas:
        palabras = texto[e.inicio:e.fin].split()
        # Só nomes con forma clara de persoa: nome de pía do INE ao principio e
        # polo menos outra palabra con maiúscula, sen comas nin artigos
        # ("la TATE", "la Parte", "Reino Unido" non se espallan).
        contido = [p for p in palabras if p.lower() not in _PARTICULAS_APELIDO]
        if len(contido) < 2 or palabras[0] is not contido[0] \
                or nomes_ine.normalizar(palabras[0]) not in nomes \
                or not all(_PALABRA_NOME_PROPAGABLE_RE.fullmatch(p) for p in contido):
            continue
        por_chave.setdefault(tuple(p.lower() for p in palabras), []).append(e)
    if not por_chave:
        return entidades

    # Índice por inicio (un documento longo pode ter decenas de miles de
    # entidades e de coincidencias: percorrelas todas en cada unha era cadrático).
    ordenadas = sorted(entidades, key=lambda e: e.inicio)
    inicios = [e.inicio for e in ordenadas]
    lonxitude_maxima = max((e.fin - e.inicio for e in ordenadas), default=0)
    ocupado_novas = bytearray(len(texto))

    def solapadas_con(inicio, fin):
        desde = bisect.bisect_left(inicios, inicio - lonxitude_maxima)
        ata = bisect.bisect_left(inicios, fin)
        return [e for e in ordenadas[desde:ata] if e.inicio < fin and inicio < e.fin]

    eliminar = set()
    for chave, existentes in por_chave.items():
        patron = re.compile(
            r"(?<![\w-])" + _SEPARADOR_NOME_RE.join(re.escape(p) for p in chave) + r"(?![\w-])",
            re.IGNORECASE,
        )
        exenta = next((e for e in existentes if e.etiqueta == "PERSOA_EXENTA_CARGO_PUBLICO"), None)
        cargo = exenta.cargo if exenta else None
        novas = []
        for m in patron.finditer(texto):
            if any(ocupado_directas[m.start():m.end()]) or any(ocupado_novas[m.start():m.end()]):
                continue
            solapadas = solapadas_con(m.start(), m.end())
            if any(e.inicio == m.start() and e.fin == m.end() and e.etiqueta in _ETIQUETAS_PERSOA
                   for e in solapadas):
                continue
            # Só se absorben anacos de persoa (ou o mesmo nome que spaCy
            # etiquetou coma lugar/organización) que caian DENTRO ("Xiana
            # Fernández" + resto). Unha PERSOA mal cortada que só colle parte
            # do nome ("del Patronato de la Tate Gallery, Helen" + "Lidd" á
            # vista, BOE-A-2026-1546) recórtase ata o nome; calquera outro
            # solapamento déixase.
            dentro = [e for e in solapadas if e.etiqueta in _ETIQUETAS_ABSORBIBLES
                      and m.start() <= e.inicio and e.fin <= m.end()]
            # Só cando o resto vai separado do nome por puntuación ("Gallery,
            # Helen"): unha entidade máis longa que empeza no mesmo sitio é OUTRO
            # nome máis completo ("José Antonio Bermudo Iribeñ") e non se toca
            # -- recortala deixaba "Iribeñ" á vista (BOE-A-2026-4392).
            mal_cortadas = [e for e in solapadas if e not in dentro and e.etiqueta == "PERSOA" and not e.cela
                            and ((e.inicio < m.start() < e.fin <= m.end()
                                  and re.search(r"[,;(][ \t\n]*\Z", texto[e.inicio:m.start()]))
                                 or (m.start() < e.inicio < m.end() < e.fin
                                     and re.match(r"[ \t\n]*[,;)]", texto[m.end():e.fin])))]
            if len(dentro) + len(mal_cortadas) < len(solapadas):
                continue
            for e in mal_cortadas:
                if e.inicio < m.start():
                    e.fin = m.start()
                    while e.fin > e.inicio and texto[e.fin - 1] in " \t\n,;":
                        e.fin -= 1
                else:
                    e.inicio = m.end()
                    while e.inicio < e.fin and texto[e.inicio] in " \t\n,;":
                        e.inicio += 1
                # "de Eloy Sáez Herrero, Marisol..." (AnuncioC3K1-180825,
                # REGRESIÓN da propia pasada): a preposición que spaCy pegou ao
                # principio non fai que o resto deixe de ser un nome.
                inicial = re.match(r"(?:(?:de|del|do|da|dos|das|a|al|ao|e|y|o)[ \t\n]+)+", texto[e.inicio:e.fin])
                if inicial and inicial.end() < e.fin - e.inicio \
                        and _resto_con_forma_de_nome(texto[e.inicio + inicial.end():e.fin]):
                    e.inicio += inicial.end()
                e.texto = texto[e.inicio:e.fin]
            # O que sobra só segue sendo persoa se ten forma de nome ("Entre",
            # "do Pobo", "del Patronato de la Tate Gallery" non).
            solapadas = dentro + [e for e in mal_cortadas if e.fin <= e.inicio or not e.texto[:1].isupper()
                                  or _tramo_sen_ine(e.texto) or _e_organismo(e.texto)
                                  or e.texto.split()[0].lower() in _PARTICULAS_APELIDO]
            nova = Entidade(m.start(), m.end(), m.group(), "PERSOA", multilinea="\n" in m.group())
            novas.append((nova, solapadas))
            if cargo is None:
                match_cargo = _cargo_publico_exento(texto_suavizado, m.start(), m.end())
                if match_cargo is not None:
                    cargo = match_cargo.group().strip(" ,\n\t")
        for nova, solapadas in novas:
            ocupado_novas[nova.inicio:nova.fin] = b"\x01" * (nova.fin - nova.inicio)
            eliminar.update(id(e) for e in solapadas)
            entidades.append(nova)
            existentes.append(nova)
        if cargo is not None:
            for e in existentes:
                e.etiqueta = "PERSOA_EXENTA_CARGO_PUBLICO"
                e.cargo = e.cargo or cargo
    return [e for e in entidades if id(e) not in eliminar]


# Guións tipográficos que o DOG usa no canto do "-" (U+2010 HYPHEN e U+2011
# NON-BREAKING HYPHEN), tamén coma guión de fin de liña ("acor\u2011\ndo").
# Lote 3 (03/10/2026), FUGA: "Xiana Ferrín\u2011Ulla Bacarizo" só se
# tapaba ata o guión, porque ningún patrón de nome os coñecía. Detéctase
# sobre unha copia co "-" normal (mesma lonxitude: as posicións valen igual)
# e o texto de cada entidade vólvese tomar do ORIXINAL.
_GUIONS_TIPOGRAFICOS = {"\u2010": "-", "\u2011": "-"}
# Lote 4 (03/10/2026), FUGAS: "don Pavol Šinál" e "Curic Špehar" (letras
# latinas doutros idiomas) e "Ferrándiz O´Dempsey" (acento agudo U+00B4 coma
# apóstrofo) deixaban o apelido á vista: os patróns de nome só coñecen as
# letras do español. Na copia de detección lense pola letra base (Š -> S) e
# coma "'"; sempre UN carácter por outro, así que as posicións non cambian.
_APOSTROFOS = {"\u00b4": "'", "\u2019": "'", "\u02bc": "'", "\u2018": "'"}
_LETRAS_ESPAÑOL = set("áéíóúüñÁÉÍÓÚÜÑ")


@lru_cache(maxsize=4096)
def _letra_para_deteccion(c: str) -> str:
    if c in _GUIONS_TIPOGRAFICOS:
        return _GUIONS_TIPOGRAFICOS[c]
    if c in _APOSTROFOS:
        return _APOSTROFOS[c]
    if c.isascii() or c in _LETRAS_ESPAÑOL or not c.isalpha():
        return c
    base = unicodedata.normalize("NFD", c)[0]
    return base if base.isascii() and base.isalpha() else c


def _texto_para_deteccion(texto: str) -> str:
    if texto.isascii():
        return texto
    return "".join(_letra_para_deteccion(c) for c in texto)


def detectar(texto: str, celas: list | None = None):
    """Coma `_detectar`, pero cos guións tipográficos (U+2010/U+2011), os
    apóstrofos tipográficos e as letras latinas doutros idiomas lidas coma as
    do español (ver `_letra_para_deteccion`)."""
    normalizado = _texto_para_deteccion(texto)
    if normalizado == texto:
        return _detectar(texto, celas)
    entidades, doc = _detectar(normalizado, celas)
    for e in entidades:
        e.texto = texto[e.inicio:e.fin]
    return entidades, doc


def _detectar(texto: str, celas: list | None = None):
    """Devolve (entidades, doc_spacy). `entidades` mestura persoas/lugares do
    NER con identificadores directos detectados por patron, sen solapamentos
    (os identificadores directos, mais especificos, teñen prioridade).

    A detección faise sobre unha copia do texto con palabras TODO EN
    MAIÚSCULAS suavizadas a Title Case (`_suavizar_maiusculas_para_deteccion`),
    pero todo o texto que se devolve nas entidades procede sempre do texto
    ORIXINAL -- a copia suavizada é só unha axuda interna para o modelo.

    Documentos moi longos procésanse en varios anacos (`_anacos_para_ner`)
    para non superar o límite de caracteres de spaCy; `doc_spacy` devolve
    entón só o correspondente ao PRIMEIRO anaco (uso interno, non crítico:
    ningún chamador depende hoxe del para nada máis que depuración)."""
    nlp = cargar_modelo()

    directas = recognizers.detectar(texto)
    ocupado = [False] * len(texto)
    for e in directas:
        for i in range(e.inicio, e.fin):
            ocupado[i] = True
    # Fotografía do ocupado SÓ polos identificadores directos (enderezo,
    # DNI...), ANTES de que ningún recoñecedor de persoa marque nada --
    # necesaria máis abaixo para distinguir "solapa cun identificador
    # directo máis específico" (recuperable, ver esa nota) de "solapa con
    # OUTRA detección de persoa xa feita" (non recuperable).
    ocupado_directas = list(ocupado)

    entidades = list(directas)
    # Celas de táboa (PDF): antes que calquera recoñecedor de persoa, para
    # que ningún deles as recorte nin as estenda (ver `_entidades_de_celas`).
    if celas:
        entidades.extend(_entidades_de_celas(texto, celas, ocupado, directas))
    doc_referencia = None

    # Recoñecedor de reserva: corre ANTES ca spaCy. Ten que ir primeiro --
    # non despois -- para poder GAÑARLLE a unha entidade que o NER
    # etiquete mal por completo (ver `_detectar_persoas_por_honorifico`):
    # un caso real ("Dña. María Nieves...") tiña o propio modelo a
    # etiquetar "María Nieves..." coma LOC, e se o recoñecedor de reserva
    # correse despois, atoparíase esa zona xa "ocupada" pola LOC
    # incorrecta e nunca chegaría a corrixila.
    texto_suavizado_completo = _suavizar_ordinais_para_deteccion(_suavizar_maiusculas_para_deteccion(texto))
    for entidade in _detectar_persoas_partidas_con_guion(texto, ocupado):
        entidades.append(entidade)
        for i in range(entidade.inicio, entidade.fin):
            ocupado[i] = True
    for entidade in _detectar_persoas_por_honorifico(texto, texto_suavizado_completo, ocupado):
        entidades.append(entidade)
        for i in range(entidade.inicio, entidade.fin):
            ocupado[i] = True
    for entidade in _outras_aparicions_de_iniciais(entidades, texto, ocupado):
        entidades.append(entidade)
        for i in range(entidade.inicio, entidade.fin):
            ocupado[i] = True
    for entidade in _maria_abreviada(texto, ocupado):
        entidades.append(entidade)
        for i in range(entidade.inicio, entidade.fin):
            ocupado[i] = True
    for entidade in _iniciais_soltas(texto, ocupado):
        entidades.append(entidade)
        for i in range(entidade.inicio, entidade.fin):
            ocupado[i] = True

    # Mesmo principio, pero ancorado por unha profesión/cargo DESPOIS do
    # nome (bloque de sinatura sen tratamento honorífico ningún diante):
    # caso real, unha epígrafe en maiúsculas repetindo o mesmo nome xusto
    # enriba facía que o modelo etiquetase a liña de sinatura enteira coma
    # LOC (ver `_detectar_persoas_por_profesion`).
    for entidade in _detectar_persoas_por_profesion(texto, texto_suavizado_completo, ocupado):
        entidades.append(entidade)
        for i in range(entidade.inicio, entidade.fin):
            ocupado[i] = True

    # Terceiro recoñecedor de reserva: "Apelidos, Nome" en listaxes
    # oficiais de persoal (ver `_detectar_persoas_apelidos_nome_inverso`).
    for entidade in _detectar_persoas_apelidos_nome_inverso(texto, texto_suavizado_completo, ocupado):
        entidades.append(entidade)
        for i in range(entidade.inicio, entidade.fin):
            ocupado[i] = True
    for entidade in _detectar_persoas_apelidos_liña_nome_liña(texto, ocupado):
        entidades.append(entidade)
        for i in range(entidade.inicio, entidade.fin):
            ocupado[i] = True

    # Cuarto recoñecedor de reserva: nome INTEGRAMENTE en minúscula tras
    # un verbo de comparecencia/sinatura (ver `_detectar_persoas_minusculas`).
    # Sobre o texto ORIXINAL, non o suavizado: unha palabra en minúscula
    # non se toca en ningures pola suavización de maiúsculas.
    for entidade in _detectar_persoas_minusculas(texto, ocupado):
        entidades.append(entidade)
        for i in range(entidade.inicio, entidade.fin):
            ocupado[i] = True

    # Quinto recoñecedor de reserva: nome da táboa oficial do INE + apelido
    # da táboa (ver `_detectar_persoas_por_taboa`). Vai o ÚLTIMO dos de
    # reserva: os anteriores están ancorados por sinais máis fortes
    # (tratamento, profesión, orde invertida) e deben gañarlle.
    for entidade in _detectar_persoas_por_taboa(texto, texto_suavizado_completo, ocupado, nlp):
        entidades.append(entidade)
        for i in range(entidade.inicio, entidade.fin):
            ocupado[i] = True

    for inicio_anaco, anaco in _anacos_para_ner(texto):
        anaco_suavizado = _suavizar_ordinais_para_deteccion(_suavizar_maiusculas_para_deteccion(anaco))
        doc = nlp(anaco_suavizado)
        if doc_referencia is None:
            doc_referencia = doc

        # PERSOAS PRIMEIRO: así a extensión dunha persoa (cara adiante ou
        # cara atrás) gáñalle a un LOC/ORG veciño mal etiquetado (caso
        # real: "Xosé" coma LOC diante de "Manuel Carballo Portela" PER).
        ents_ordenadas = sorted(
            _ents_sen_persoas_multilinea(nlp, doc, anaco),
            key=lambda par: _MAPA_SPACY.get(par[0].label_) != "PERSOA",
        )
        for ent, desprazamento in ents_ordenadas:
            etiqueta = _MAPA_SPACY.get(ent.label_)
            if etiqueta is None:
                continue

            if etiqueta == "PERSOA":
                # `ent` pode vir dun doc dunha SOA LIÑA (desprazamento > 0):
                # tódalas funcións traballan en coordenadas dese doc.
                base = anaco[desprazamento:desprazamento + len(ent.doc.text)]
                recortada = _recortar_entidade_persoa(_estender_entidade_persoa(ent), base)
                if recortada is None:
                    continue
                inicio_local, fin_local, _ = recortada
                sen_tratamentos = _recortar_tratamentos(base, ent.doc.text, inicio_local, fin_local)
                if sen_tratamentos is None:
                    continue
                inicio_local, fin_local = sen_tratamentos
                inicio_local = _estender_cara_atras(ent.doc, inicio_local)
                inicio_local += desprazamento
                fin_local += desprazamento
                texto_ent = anaco[inicio_local:fin_local]
                # spaCy tamén devolve PER palabras en minúscula ("concesión
                # da") ou siglas soltas de 1-2 letras ("SY", ruído de OCR).
                minusculas = _MINUSCULAS_INICIAIS_RE.match(texto_ent)
                if minusculas and not all(
                    p.lower() in _PARTICULAS_APELIDO for p in minusculas.group().split()
                ):
                    texto_ent = texto_ent[minusculas.end():]
                    inicio_local += minusculas.end()
                    if not texto_ent[:1].isupper():
                        continue
                if len(texto_ent.split()) == 1 and sum(c.isalpha() for c in texto_ent) <= 2:
                    continue
            else:
                inicio_local, fin_local = ent.start_char, ent.end_char
                texto_ent = anaco[inicio_local:fin_local]

            inicio, fin = inicio_anaco + inicio_local, inicio_anaco + fin_local
            if any(ocupado[inicio:fin]):
                # Un identificador DIRECTO máis específico (enderezo, DNI...
                # -- ver `ocupado_directas`) xa reclamou parte deste span --
                # descartalo ENTEIRO deixaría escapar SEN REDACTAR a parte
                # boa. Caso real atopado nunha carta: spaCy funde "Nome
                # Apelidos" coa "Rúa..." que vén xusto despois (sen coma nin
                # punto de por medio, coma nun enderezo de remitente pegado
                # á sinatura) nunha soa entidade PER; o enderezo quedaba ben
                # redactado polo seu propio recoñecedor, pero o NOME ENTEIRO
                # escapaba sen redactar porque a entidade fusionada de spaCy
                # se descartaba por completo ao solapar con el. Recórtase
                # xusto antes do primeiro punto xa ocupado POR UN
                # IDENTIFICADOR DIRECTO (nunca por outra detección de
                # persoa: se o solapamento é con ela, o span xa contén só
                # título/cargo pegado a un nome que OUTRO recoñecedor xa
                # capturou aparte -- caso real atopado arranxando isto
                # mesmo: "Sr. Magistrado-Juez D." quedaba coma "persoa" á
                # parte de "Xoán Páez Veiga", xa ben detectado polo
                # recoñecedor de honorífico -- así que descártase enteiro
                # coma antes).
                if etiqueta != "PERSOA" or ocupado_directas[inicio]:
                    continue
                if _unir_con_persoa_existente(
                    entidades, ocupado, ocupado_directas, texto,
                    texto_suavizado_completo, inicio, fin,
                ):
                    continue
                primeiro_directo = next(
                    (i for i in range(inicio, fin) if ocupado_directas[i]), None
                )
                if primeiro_directo is None:
                    continue
                fin = primeiro_directo
                while fin > inicio and texto[fin - 1] in " \t\n":
                    fin -= 1
                if fin <= inicio or any(ocupado[inicio:fin]):
                    continue
                fin_local = fin - inicio_anaco
                texto_ent = anaco[inicio_local:fin_local]
            entidades.append(Entidade(inicio, fin, texto_ent, etiqueta))
            for i in range(inicio, fin):
                ocupado[i] = True

    _estender_apelido_na_liña_seguinte(entidades, ocupado, texto, texto_suavizado_completo)

    # Rede de seguridade: NINGUNHA persoa pode cruzar un salto de liña/páxina,
    # veña do recoñecedor que veña (ver `_partir_persoa_por_linas`). Única
    # excepción: a cela "Apelidos,\nNome." dunha táboa, xa validada pola
    # súa forma (`multilinea`); partida, a mesma persoa levaría dous códigos.
    entidades = [
        peza
        for entidade in entidades
        for peza in (
            _partir_persoa_por_linas(entidade, texto, texto_suavizado_completo)
            if entidade.etiqueta == "PERSOA" and not entidade.multilinea else [entidade]
        )
    ]

    entidades = _unir_persoas_partidas_por_guion(entidades, texto)
    entidades = _completar_nome_de_pia(entidades, texto)

    # Nin un membrete nin o nome dun organismo público son datos persoais
    # (ver `_ORGANISMOS_RE`): quítanse das persoas detectadas, veñan de onde
    # veñan, pero só o anaco que é o organismo.
    entidades = [
        peza
        for entidade in entidades
        for peza in _quitar_organismos(entidade, texto)
    ]
    entidades = [peza for entidade in entidades for peza in _quitar_anacos_sen_ine(entidade, texto)]

    # Marcas ("VInnovate") e topónimos ("MVMC Acevedo", "Parroquia da
    # Pereira") non son persoas, veñan de onde veñan.
    entidades = [
        e for e in entidades
        if not (e.etiqueta == "PERSOA" and not e.cela and (
            _e_marca(e) or _e_toponimo(e, texto_suavizado_completo) or _e_fragmento_de_palabra(e, texto)
            or _e_lugar_oficial(e, texto) or _e_encabezado_ou_termo(e, texto) or _e_termo_non_persoa(e, texto)
            or _sen_palabras_de_nome_ine(e, texto) or _e_ruido_de_boletin(e, texto)))
    ]

    # Cargo ANTES do nome nun bloque de sinatura sen honorífico
    # ("El Secretario General Técnico, Xoán Páez Veiga"): spaCy adoita
    # devolver cargo+nome coma UNHA SOA entidade -- sobre-anonimización,
    # non fuga, pero innecesaria (ver `_recortar_cargo_inicial`).
    for entidade in entidades:
        if entidade.etiqueta == "PERSOA":
            _recortar_reina_sofia(entidade, texto)
            _recortar_cargo_inicial(entidade, texto, texto_suavizado_completo)
            if not entidade.cela:
                _recortar_iniciais_con_coma(entidade, texto)
                _recortar_verbo_inicial(entidade, texto, texto_suavizado_completo)
    entidades = [e for e in entidades if not (e.etiqueta == "PERSOA" and not e.cela and _e_cargo_de_lugar(e, texto))]
    # Despois dos recortes (organismo, cargo): antes, "el Servicio Público de Justicia, Maria"
    # aínda non era só "Maria" e non se podía xuntar con "Àngels Galán Viana".
    entidades = _xuntar_anacos_da_mesma_persoa(entidades, texto, texto_suavizado_completo)

    # Última pasada: exención por cargo público (ver `_cargo_publico_exento`)
    # sobre CALQUERA persoa xa detectada, sen importar por cal dos catro
    # camiños de arriba se atopou. Múdase a etiqueta en vez de eliminar a
    # entidade -- así `resolution.agrupar` (que só colle "PERSOA") e a
    # substitución en `pipeline.py` (que só actúa sobre etiquetas
    # coñecidas) ignóranas automaticamente, pero seguen visibles no informe
    # para que un letrado poida detectar unha exención mal aplicada.
    for entidade in entidades:
        if entidade.etiqueta != "PERSOA" or entidade.cela:
            # Nunha cela, o "contexto" arredor son OUTRAS columnas (o
            # posto adxudicado: "Subdirector General..."), non un cargo
            # que acompañe ao nome nunha frase.
            continue
        match_cargo = _cargo_publico_exento(texto_suavizado_completo, entidade.inicio, entidade.fin)
        if match_cargo is not None:
            entidade.etiqueta = "PERSOA_EXENTA_CARGO_PUBLICO"
            entidade.cargo = match_cargo.group().strip(" ,\n\t")

    _completar_bordos_do_nome(entidades, texto)
    entidades = _outras_aparicions_da_mesma_persoa(entidades, texto, texto_suavizado_completo, ocupado_directas)
    entidades = [e for e in entidades
                 if not (e.etiqueta == "PERSOA" and not e.cela
                         and (_e_nome_de_centro_educativo(e, texto) or _e_termo_non_persoa(e, texto)))]
    _rua_sen_tipo_de_via(entidades, texto)

    # A cela de cabeceira dunha columna de dato persoal é un rótulo, nunca
    # un nome nin un lugar ("Persoa interesada/DNI").
    if celas:
        cabeceiras = [peza for cela in celas if cela.tipo == "CABECEIRA" for peza in cela.pezas]
        entidades = [
            e for e in entidades
            if e.etiqueta not in ("PERSOA", "LOCALIZACION", "ORGANIZACION")
            or not any(a <= e.inicio and e.fin <= b for a, b in cabeceiras)
        ]

    entidades.sort(key=lambda e: e.inicio)
    return entidades, doc_referencia
