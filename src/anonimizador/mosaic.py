"""Deteccion de risco de efecto mosaico (informe, seccion 10): combinacions
de detalles moi especificos -- profesion, lugar, data ou idade exacta -- que
poden identificar a alguen aínda despois de retirar o seu nome.

Isto non se substitue automaticamente (facelo perderia informacion que o
letrado pode necesitar); marcase para revision humana, seguindo o mesmo
principio de deseno conservador que a resolucion de identidade.

Nota: os enderezos con número (rúa/calle + nome + nº) xa non se tratan
aquí -- son un identificador DIRECTO e redáctanse antes, en
`recognizers.py`. Este módulo queda para combinacións que, por separado,
non son identificadores directos pero xuntas si poden selo.
"""

import re
from dataclasses import dataclass

import yaml

_DATA_RE = re.compile(
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"
    r"|\b\d{1,2}\s+de\s+"
    # galego + castelan (informe A24: os expedientes tamen chegan en
    # castelan e a versión anterior so recoñecia os meses en galego).
    r"(?:xaneiro|febreiro|marzo|abril|maio|xu[ñn]o|xullo|agosto|setembro|outubro|novembro|decembro"
    r"|enero|febrero|mayo|junio|julio|septiembre|octubre|noviembre|diciembre)"
    r"\s+de\s+\d{4}\b",
    re.IGNORECASE,
)
# "anos" (galego) e "años" (castelan) -- ver nota de _DATA_RE, mesmo motivo.
_IDADE_RE = re.compile(r"\bde\s+\d{1,3}\s+a[ñn]os\b", re.IGNORECASE)


@dataclass
class RiscoMosaico:
    tipo: str
    frase: str
    detalle: str


def _cargar_profesions(ficheiro_config: str) -> set:
    with open(ficheiro_config, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return {p.lower() for p in config.get("mosaico", {}).get("categorias_profesion", [])}


def analizar(texto: str, nlp, ficheiro_config: str) -> list:
    """Analiza o texto (xa anonimizado nos nomes) e devolve unha lista de
    RiscoMosaico. `nlp` e un modelo spaCy xa cargado (para fronteiras de
    frase e localizacions).

    A analise faise parrafo a parrafo (separados por liña en branco): un
    parrafo adoita corresponder a un feito ou declaracion distinta, e sen
    este corte a xanela de frases podia cruzar unha profesion mencionada
    nun parrafo con un lugar ou data doutro parrafo sen relacion."""
    profesions = _cargar_profesions(ficheiro_config)
    achados = []
    for paragrafo in re.split(r"\n\s*\n", texto):
        paragrafo = paragrafo.strip()
        if paragrafo:
            achados.extend(_analizar_paragrafo(paragrafo, nlp, profesions))
    return _sen_duplicados(achados)


def _analizar_paragrafo(paragrafo: str, nlp, profesions: set) -> list:
    doc = nlp(paragrafo)
    achados = []

    frases = list(doc.sents)
    for i, frase in enumerate(frases):
        texto_frase = frase.text

        # Xanela de ata 2 frases para cruzar profesion + lugar + data/idade,
        # tal como describe o informe (combinacions, non sinais illados).
        xanela = " ".join(f.text for f in frases[i:i + 3])
        xanela_lower = xanela.lower()

        profesion_atopada = next((p for p in profesions if p in xanela_lower), None)
        ten_lugar = any(
            ent.label_ == "LOC" for f in frases[i:i + 3]
            for ent in doc.ents
            if ent.start_char >= f.start_char and ent.end_char <= f.end_char
        )
        ten_data = bool(_DATA_RE.search(xanela)) or bool(_IDADE_RE.search(xanela))

        if profesion_atopada and ten_lugar and ten_data:
            achados.append(RiscoMosaico(
                tipo="combinacion_alta_especificidade",
                frase=texto_frase.strip(),
                detalle=(
                    f"profesion ('{profesion_atopada}') + lugar + data/idade "
                    "na mesma zona do texto"
                ),
            ))

    return achados


def _sen_duplicados(achados: list) -> list:
    vistos = set()
    unicos = []
    for a in achados:
        chave = (a.tipo, a.frase)
        if chave not in vistos:
            vistos.add(chave)
            unicos.append(a)
    return unicos
