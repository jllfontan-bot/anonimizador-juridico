"""Aviso de datos de categoría especial (art. 9 RGPD) no texto XA anonimizado:
saúde, relixión ou conviccións, orientación sexual e afiliación sindical.

Só AVISA no informe, nunca redacta nada (decisión do 27/09/2026, ver
o plan interno da v2): a persoa xa vai substituída polo seu código, pero un
dato así xunto a outros detalles pode reidentificala ou ser sensible por si
mesmo, así que o letrado debe velo -- mesmo papel ca `mosaic.py`.

Lista DETERMINISTA de termos, sen ningún modelo de linguaxe dentro do
programa: a medición cun LLM local (qwen2.5-coder:3b, 88,6% en 44 casos)
serviu para confirmar que isto paga a pena, pero ese modelo ten licenza só non
comercial e engadiría ~2 GB a cada instalador. A cobertura mídese contra
`medicion/corpus_categoria_especial_reserva.json` (frases redactadas ANTES
desta lista, con vocabulario distinto ao do xerador do corpus).

Criterio para cada termo: que case cun dato DUNHA PERSOA, non co vocabulario
institucional que abunda nos documentos xurídicos. Por iso non están
"saúde", "sanidade", "Seguridade Social", "igrexa", "parroquia" (unidade
territorial en Galicia), "orientación" soa, "baixa" soa (vehículo, padrón),
"libertade relixiosa/sindical", nin nomes de drogas (en penal adoitan ser o
obxecto do delito, non o consumo de ninguén).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_I = r"(?<!\w)"
_F = r"(?!\w)"

_SAUDE = (
    r"VIH|sida|seropositiv[oa]s?|antirretroviral(?:es)?"
    r"|c[aá]ncer|cancro|tumor(?:es)?|leucemia|quimioterapia|radioterapia"
    r"|diabetes|esclerosis|alzh?[eé]imer|p[aá]rkinson|epilepsia|hepatitis"
    r"|esquizofrenia|depresi[oó]n|trastorno|s[ií]ndrome|autismo|TDAH"
    r"|infarto|ictus|lesi[oó]n medular|tetrapl[eé]xic[oa]|tetrapl[eé]jic[oa]"
    r"|parapl[eé]xic[oa]|parapl[eé]jic[oa]"
    r"|psiquiatr[ií]a|psiqui[aá]tric[oa]|sa[uú]de mental|salud mental"
    r"|embarazad[oa]|embarazo|xestaci[oó]n|gestaci[oó]n"
    r"|drogodependencia|toxicoman[ií]a|adicci[oó]n|desintoxicaci[oó]n|alcoholismo|ludopat[ií]a"
    r"|(?:certificado|grao|grado|porcentaxe|porcentaje) de discapacidade?"
    r"|discapacidade? (?:recoñecida|reconocida|do|del|dun|de un)"
    r"|con discapacidade?"
    r"|incapacidade? (?:temporal|permanente|absoluta)"
    r"|bai(?:x|j)a m[eé]dica|bai(?:x|j)a por enfermidade|baja por enfermedad"
    r"|(?:padec|sufr)\w*\s+(?:de\s+)?(?:unha?\s+|una?\s+)?(?:enfermidade|enfermedad|patolox[ií]a|patolog[ií]a)"
    r"|diagnostic\w+"
)

_RELIXION = (
    # "practicante" só non: tamén é o nome antigo do enfermeiro.
    r"profesa|practicante (?:de|da|do|del)"
    r"|motivos (?:relixiosos|religiosos)|conviccións? relixiosas?|convicciones religiosas"
    r"|creenzas relixiosas|creencias religiosas|confesi[oó]n (?:relixiosa|religiosa)"
    r"|(?:relixi[oó]n|religi[oó]n) (?:cat[oó]lica|musulmá|musulmana|isl[aá]mica|evang[eé]lica"
    r"|xud[ií]a|jud[ií]a|budista|hind[uú]|protestante|cristi[aá]|cristiana)"
    r"|musulm[aá]n|musulmana|musulmá|isl[aá]mic[oa]|evang[eé]lic[oa]"
    r"|xudeu|xud[ií]a|jud[ií][oa]|budista|hind[uú]|protestante|testemuña de Xehová"
    r"|testigo de Jehov[aá]|adventista|morm[oó]n|ate[oa]|agn[oó]stic[oa]"
    r"|hiyab|hijab|velo isl[aá]mico|kip[aá]|ramad[aá]n|sinagoga|mezquita|mesquita"
    r"|misa|lugar de culto|bautizad[oa]"
)

_ORIENTACION = (
    r"homosexual(?:es)?|heterosexual(?:es)?|bisexual(?:es)?|lesbianas?|gays?|gai"
    r"|transexual(?:es)?|transx[eé]nero|transg[eé]nero|intersexual"
    r"|orientaci[oó]n (?:sexual|homosexual|bisexual|heterosexual)"
    r"|identidade de x[eé]nero|identidad de g[eé]nero"
    r"|transici[oó]n de (?:x[eé]nero|g[eé]nero)"
    r"|(?:parella|pareja|matrimonio) (?:do|del) mesmo sexo|(?:parella|pareja|matrimonio) del mismo sexo"
    r"|LGTBI?Q?\+?"
)

_SIGLAS_SINDICATOS = r"CIG|CCOO|CC\.\s?OO\.?|UGT|CSIF|CSI-F|USO|CNT|CGT|ELA|LAB|SATSE|STEG|ANPE"

_SINDICAL = (
    r"afiliad[oa]s?\s+(?:a|al|á|ao|a la|del|de la|da|do|en)\s+(?:(?:o|el|la)\s+)?"
    r"(?:sindicato|central sindical|" + _SIGLAS_SINDICATOS + r")"
    r"|delegad[oa]s?\s+sindica(?:l|is|les)|secci[oó]n sindical|liberad[oa]s?\s+sindica(?:l|is|les)"
    r"|representante sindical|militante (?:de|del|da|do) (?:sindicato|" + _SIGLAS_SINDICATOS + r")"
    r"|cotiza (?:en|no) (?:el |o )?sindicato"
    r"|(?:miembro|membro|forma parte) (?:del|do) comit[eé] de empresa"
    r"|comit[eé] de empresa (?:por|pola) (?:a |la )?candidatura"
)

_PATRONS = (
    ("saude", re.compile(_I + r"(?:" + _SAUDE + r")" + _F, re.IGNORECASE)),
    ("relixion", re.compile(_I + r"(?:" + _RELIXION + r")" + _F, re.IGNORECASE)),
    ("orientacion_sexual", re.compile(_I + r"(?:" + _ORIENTACION + r")" + _F, re.IGNORECASE)),
    ("sindical", re.compile(_I + r"(?:" + _SINDICAL + r")" + _F, re.IGNORECASE)),
)


@dataclass
class AvisoCategoriaEspecial:
    categoria: str
    termo: str
    contexto: str
    inicio: int
    fin: int


def _contexto(texto: str, inicio: int, fin: int, marxe: int = 60) -> str:
    return " ".join(texto[max(0, inicio - marxe):min(len(texto), fin + marxe)].split())


_MAX_DISTANCIA_UNION = 40


def escanear_categoria_especial(texto_anonimizado: str) -> list[AvisoCategoriaEspecial]:
    """Devolve os avisos ordenados por posición, sen solapamentos (o
    primeiro patrón de `_PATRONS` que casa nun anaco gaña). Dous termos da
    MESMA categoría na mesma frase e preto ("profesa la religión musulmana")
    xúntanse nun só aviso: son o mesmo dato, e dous avisos duplicarían o
    ruído do informe."""
    atopados: list[tuple[str, int, int]] = []
    ocupado = [False] * len(texto_anonimizado)
    for categoria, patron in _PATRONS:
        for match in patron.finditer(texto_anonimizado):
            inicio, fin = match.span()
            if any(ocupado[inicio:fin]):
                continue
            for i in range(inicio, fin):
                ocupado[i] = True
            atopados.append((categoria, inicio, fin))
    atopados.sort(key=lambda a: a[1])

    unidos: list[list] = []
    for categoria, inicio, fin in atopados:
        if unidos:
            anterior = unidos[-1]
            entre = texto_anonimizado[anterior[2]:inicio]
            if (anterior[0] == categoria and len(entre) <= _MAX_DISTANCIA_UNION
                    and not any(c in entre for c in ".;\n")):
                anterior[2] = fin
                continue
        unidos.append([categoria, inicio, fin])

    return [
        AvisoCategoriaEspecial(
            categoria, texto_anonimizado[inicio:fin],
            _contexto(texto_anonimizado, inicio, fin), inicio, fin,
        )
        for categoria, inicio, fin in unidos
    ]
