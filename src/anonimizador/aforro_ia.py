"""Aforro para IA: menos tokens no Markdown que xera `copia_md.xerar`
(fase 3 do conversor a .md, ESTUDIO-CONVERSOR-MD punto 5).

Funcións puras sobre o texto Markdown (nada de ler nin de gardar, agás
`escribir`), todas opcionais e con `aforrar` coma única entrada:

  1. Cabeceiras e pés repetidos (PDF): unha liña igual en case todas as
     páxinas, nas primeiras ou nas últimas liñas, escríbese unha vez ao
     principio. Os contadores («Páx. 47408», «Página 3 de 20») bótanse: a
     páxina xa vai na marca `<!-- páxina N -->`.
  2. Unir as liñas partidas dun parágrafo e quitar o guión de corte
     («adminis-\\ntración»), sen tocar táboas, listas, títulos nin marcas.
  3. Espazos e liñas baleiras de sobra.
  4. Troceado dun documento moi longo en partes (`memoria.parte-01.md`...)
     máis un índice (`memoria.indice.md`), cortando por páxina ou título e
     nunca no medio dunha táboa.
  5. Estimación de tokens antes e despois (≈ 3,5 caracteres por token).

Nada que non sexa repetido se perde: o que se quita queda en
`Resultado.eliminadas` e os tests comproban que as letras de antes son as
de despois máis as eliminadas.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, fields
from pathlib import Path

from . import idioma

CARACTERES_POR_TOKEN = 3.5
CARACTERES_POR_PARTE = 60000  # valor razoable para `Opcions.caracteres_por_parte` (≈ 17.000 tokens)

# Cabeceiras e pés: só se miran as primeiras e as últimas liñas de cada páxina
# e só se quitan se aparecen en polo menos esta fracción das páxinas.
_LIÑAS_COMEZO = 8
_LIÑAS_FINAL = 12
_FRACCION_PAXINAS = 0.6
_MINIMO_PAXINAS = 3

# Unir liñas: unha liña ten "ancho completo" se mide polo menos esta fracción
# do ancho habitual do documento; se ese ancho é maior ca isto, o texto non
# está partido a man (parágrafos dunha soa liña, ex. un .docx) e non se une.
_FRACCION_ANCHO = 0.6
_ANCHO_MAXIMO = 150

_MARCAS_PAXINA = ("gl", "es")


@dataclass(frozen=True)
class Opcions:
    quitar_repetidas: bool = True
    unir_liñas: bool = True
    limpar_espazos: bool = True
    caracteres_por_parte: int | None = None  # None: non trocear


@dataclass
class Parte:
    nome: str
    texto: str
    paxina_inicial: int | None
    paxina_final: int | None
    resumo: str


@dataclass
class Resultado:
    texto: str
    caracteres_antes: int
    caracteres_despois: int
    tokens_antes: int
    tokens_despois: int
    repetidas: list = field(default_factory=list)  # liñas escritas unha vez ao principio
    eliminadas: list = field(default_factory=list)  # cada liña quitada (incluídos os contadores)
    partes: list = field(default_factory=list)
    indice: str | None = None
    nome_indice: str | None = None

    @property
    def aforro_porcentaxe(self) -> int:
        if not self.tokens_antes:
            return 0
        return round(100 * (self.tokens_antes - self.tokens_despois) / self.tokens_antes)

    def resumo(self, lingua: str | None = None) -> str:
        """Frase para amosar: tokens antes e despois, dicindo que é unha estimación."""
        return idioma.t(
            "aforro_ia.estimacion", lingua,
            antes=_miles(self.tokens_antes), despois=_miles(self.tokens_despois), aforro=self.aforro_porcentaxe,
        )


def estimar_tokens(texto: str) -> int:
    """ESTIMACIÓN: uns 3,5 caracteres por token. O contador real de Claude só
    existe en liña."""
    return math.ceil(len(texto) / CARACTERES_POR_TOKEN) if texto else 0


def nome_base(ruta_md: str | Path) -> str:
    """`dir/memoria.md` -> `memoria` (o que leva diante `.parte-01.md`)."""
    return Path(ruta_md).stem


def _miles(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _opcions(opcions) -> Opcions:
    if opcions is None:
        return Opcions()
    if isinstance(opcions, Opcions):
        return opcions
    return Opcions(**dict(opcions))  # TypeError se hai unha opción descoñecida


# -- entrada ----------------------------------------------------------------

def aforrar(md: str, opcions: Opcions | dict | None = None, nome_base: str = "documento") -> Resultado:
    """Aplica as transformacións pedidas ao Markdown `md`. Sen `opcions`:
    as tres primeiras e sen trocear. `nome_base` dá nome ás partes e ao índice."""
    op = _opcions(opcions)
    texto, repetidas, eliminadas = md, [], []
    if op.limpar_espazos:
        texto = _limpar_espazos(texto)
    if op.quitar_repetidas:
        sen_repetidas, repetidas, eliminadas = _quitar_repetidas(texto)
        # Co comentario do bloque, quitar tres liñas curtas podería custar máis ca aforrar.
        if repetidas and len(_con_bloque_de_repetidas(sen_repetidas, repetidas)) >= len(texto):
            sen_repetidas, repetidas, eliminadas = texto, [], []
        texto = sen_repetidas
    if op.unir_liñas:
        texto = _unir_liñas(texto)
    if op.limpar_espazos:
        texto = _limpar_espazos(texto)
    if repetidas:
        texto = _con_bloque_de_repetidas(texto, repetidas)
    resultado = Resultado(
        texto=texto,
        caracteres_antes=len(md), caracteres_despois=len(texto),
        tokens_antes=estimar_tokens(md), tokens_despois=estimar_tokens(texto),
        repetidas=repetidas, eliminadas=eliminadas,
    )
    if op.caracteres_por_parte and len(texto) > op.caracteres_por_parte:
        resultado.partes = _trocear(texto, op.caracteres_por_parte, nome_base)
        resultado.nome_indice = f"{nome_base}.indice.md"
        resultado.indice = _indice(resultado.partes, nome_base)
    return resultado


def escribir(resultado: Resultado, ruta_md: str | Path) -> list:
    """Garda o resultado: `ruta_md` se non hai partes; se as hai, cada parte e
    o índice no mesmo cartafol (`<base>.parte-01.md`, `<base>.indice.md`).
    Devolve as rutas escritas."""
    ruta = Path(ruta_md)
    if not resultado.partes:
        ruta.write_text(resultado.texto, encoding="utf-8")
        return [str(ruta)]
    escritos = []
    for nome, texto in [(p.nome, p.texto) for p in resultado.partes] + [(resultado.nome_indice, resultado.indice)]:
        destino = ruta.with_name(nome)
        destino.write_text(texto, encoding="utf-8")
        escritos.append(str(destino))
    return escritos


# -- espazos ----------------------------------------------------------------

_ESPAZOS_RAROS = str.maketrans({" ": " ", "\t": " ", "\r": ""})
_ESPAZOS_REPETIDOS = re.compile(r"(?<=\S) {2,}")


def _limpar_espazos(texto: str) -> str:
    if not texto:
        return ""
    liñas = []
    for liña in texto.translate(_ESPAZOS_RAROS).split("\n"):
        sangria = len(liña) - len(liña.lstrip(" "))
        liñas.append(liña[:sangria] + _ESPAZOS_REPETIDOS.sub(" ", liña[sangria:]).rstrip() if liña.strip() else "")
    return re.sub(r"\n{3,}", "\n\n", "\n".join(liñas)).strip("\n") + "\n"


# -- páxinas ----------------------------------------------------------------

def _patron_marca() -> re.Pattern:
    """Marca de páxina nos dous idiomas (`<!-- páxina 3 -->` / `<!-- página 3 -->`)."""
    modelos = []
    for lingua in _MARCAS_PAXINA:
        modelo = idioma.t("copia_md.paxina", lingua, n="NNN")
        modelos.append(re.escape(modelo).replace("NNN", r"(\d+)"))
    return re.compile(r"^<!-- (?:" + "|".join(modelos) + r") -->[ \t]*$", re.M)


def _dividir_paxinas(texto: str):
    """(preámbulo, [(liña_da_marca, número, corpo)]). Sen marcas: (texto, [])."""
    marcas = list(_patron_marca().finditer(texto))
    if not marcas:
        return texto, []
    paxinas = []
    for i, m in enumerate(marcas):
        fin = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
        numero = int(next(g for g in m.groups() if g))
        paxinas.append((m.group(0).rstrip(), numero, texto[m.end():fin].strip("\n")))
    return texto[:marcas[0].start()], paxinas


def _e_liña_de_texto(liña: str) -> bool:
    """Liña simple: nin táboa, nin título, nin comentario, nin baleira."""
    s = liña.strip()
    return bool(s) and not s.startswith(("|", "#", "<!--"))


# -- cabeceiras e pés repetidos --------------------------------------------

# Liña que é só un contador de páxina: «Páx. #», «Página # de #», «- # -», «#»
# ou con ata dúas palabras de código diante («Sec. II.B. Pág. #»). Unha frase
# normal que remate en «páxina 3» non vale: as palabras de diante van en minúsculas.
_CONTADOR_PAXINA = re.compile(
    r"^(?:[A-ZÁÉÍÓÚÑ0-9][\w.\-]*\s+){0,2}(?i:p[áa]x(?:ina)?|p[áa]g(?:ina)?|pag|page|p|folio|f[óo]lio|hoja|folla)\.?\s*#"
    r"(?:\s*(?i:de|do|/|of)\s*#)?[\W_]*$"
    r"|^[\W_]*#(?:[\W_]*(?i:de|do|/|of|\|)?[\W_]*#)?[\W_]*$"
)


def _clave_exacta(liña: str) -> str:
    return " ".join(liña.split())


def _clave_numerica(liña: str) -> str:
    return re.sub(r"\d+", "#", _clave_exacta(liña))


def _indices_de_zona(corpo_liñas: list) -> list:
    """Índices das liñas que están nas primeiras ou últimas liñas de texto da páxina."""
    candidatas = [i for i, l in enumerate(corpo_liñas) if _e_liña_de_texto(l)]
    return candidatas[:_LIÑAS_COMEZO] + candidatas[max(_LIÑAS_COMEZO, len(candidatas) - _LIÑAS_FINAL):]


def _quitar_repetidas(texto: str):
    preambulo, paxinas = _dividir_paxinas(texto)
    n = len(paxinas)
    if n < _MINIMO_PAXINAS:
        return texto, [], []
    minimo = max(_MINIMO_PAXINAS, math.ceil(_FRACCION_PAXINAS * n))
    liñas_por_paxina = [corpo.split("\n") for _, _, corpo in paxinas]
    zonas = [_indices_de_zona(l) for l in liñas_por_paxina]
    exactas, numericas = {}, {}
    for liñas, zona in zip(liñas_por_paxina, zonas):
        for chave in {_clave_exacta(liñas[i]) for i in zona}:
            exactas[chave] = exactas.get(chave, 0) + 1
        for chave in {_clave_numerica(liñas[i]) for i in zona}:
            numericas[chave] = numericas.get(chave, 0) + 1
    repetidas_exactas = {k for k, c in exactas.items() if c >= minimo}
    contadores = {k for k, c in numericas.items() if c >= minimo and _CONTADOR_PAXINA.search(k)}

    repetidas, eliminadas, escritas = [], [], set()
    novos_corpos = []
    for liñas, zona in zip(liñas_por_paxina, zonas):
        zona = set(zona)
        conservadas = []
        for i, liña in enumerate(liñas):
            if i in zona:
                exacta = _clave_exacta(liña)
                if exacta in repetidas_exactas:
                    if exacta in escritas:
                        eliminadas.append(liña)
                    else:
                        escritas.add(exacta)
                        repetidas.append(exacta)
                    continue
                if _clave_numerica(liña) in contadores:
                    eliminadas.append(liña)
                    continue
            conservadas.append(liña)
        novos_corpos.append("\n".join(conservadas).strip("\n"))
    if not repetidas and not eliminadas:
        return texto, [], []
    partes = []
    if preambulo.strip():
        partes.append(preambulo.strip("\n"))
    for (marca, _, _), corpo in zip(paxinas, novos_corpos):
        partes.append(marca + ("\n\n" + corpo if corpo else ""))
    return "\n\n".join(partes) + "\n", repetidas, eliminadas


def _con_bloque_de_repetidas(texto: str, repetidas: list) -> str:
    """Ao principio, unha soa vez; despois de unir liñas para que non se mesturen."""
    bloque = f"<!-- {idioma.t('copia_md.cabeceiras')} -->\n\n" + "\n".join(repetidas)
    return bloque + ("\n\n" + texto if texto.strip() else "\n")


# -- unir liñas -------------------------------------------------------------

_FIN_DE_FRASE = re.compile(r"[.:;?!…]['\"”»’)\]]*$")
_GUION_DE_CORTE = re.compile(r"[^\W\d_]-$")
_ELEMENTO_DE_LISTA = re.compile(r"^(?:[-*+•–—]\s|\(?\d+[.)]\s|\(?[A-Za-zª]\)\s|[IVXLCDM]+[.)]\s)")
_COMEZO_DE_BLOQUE = re.compile(
    r"(?i)^(?:art[íi]culo|artigo|cap[íi]tulo|t[íi]tulo|secci[óo]n|sec[cç][ãa]o|disposici[óo]n|anexo|"
    r"anexe|exposici[óo]n|preámbulo|pre[aá]mbulo|primero|segundo|tercero|cuarto|quinto|sexto|primeiro|terceiro|"
    r"cuarto|quinto|sexto|xeral|resolvo|resuelvo|dispoño|dispongo|acordo|acuerdo|fdo\.?|asdo\.?)\b"
)
_ABREVIATURAS = {
    "art.", "arts.", "núm.", "nº.", "n.º", "apdo.", "p.", "pp.", "sr.", "sra.", "srta.", "d.", "dª.", "dña.", "ud.",
    "uds.", "excmo.", "excma.", "ilmo.", "ilma.", "c/", "vid.", "cfr.", "ref.", "pág.", "págs.", "páx.", "páxs.",
    "tel.", "etc.", "dto.", "dpto.", "ctra.", "avda.", "pza.", "cap.", "disp.", "ex.", "vol.", "fol.", "sec.",
}
# Palabra antes do guión + palabra despois: o guión é de verdade, non de corte.
_GUION_FIXO = {("decreto", "ley"), ("decreto", "lei"), ("decreto", "legislativo"), ("decreto", "lexislativo")}


def _e_maiusculas(liña: str) -> bool:
    letras = [c for c in liña if c.isalpha()]
    return len(letras) >= 3 and all(c.isupper() for c in letras)


def _empeza_en_minuscula(liña: str) -> bool:
    return bool(liña) and liña[0].isalpha() and liña[0].islower()


def _ancho_habitual(liñas: list) -> int | None:
    longos = sorted(len(l.strip()) for l in liñas if _e_liña_de_texto(l) and len(l.strip()) >= 20)
    if len(longos) < 4:
        return None
    ancho = longos[int(0.9 * (len(longos) - 1))]
    return ancho if ancho <= _ANCHO_MAXIMO else None


def _desescapar(liña: str) -> str:
    """O `\\` do comezo (`\\#`, `\\>`...) só facía falta ao principio de liña."""
    if len(liña) > 1 and liña[0] == "\\" and liña[1] in "#>-*_=~`":
        return liña[1:]
    return liña


def _ultima_palabra(liña: str) -> str:
    partes = liña.split()
    return partes[-1].lower() if partes else ""


def _unir_dúas(a: str, b: str, ancho: int | None) -> str | None:
    """`a` + `b` como unha soa liña, ou `None` se son liñas distintas."""
    if not _e_liña_de_texto(a) or not _e_liña_de_texto(b):
        return None
    if a[0] in " \t" or b[0] in " \t":
        return None  # sangría: continuación de lista
    a_s, b_s = a.rstrip(), b.strip()
    if _ELEMENTO_DE_LISTA.match(b_s) or _COMEZO_DE_BLOQUE.match(b_s):
        return None
    if _GUION_DE_CORTE.search(a_s):
        if _empeza_en_minuscula(b_s):
            anterior = a_s[:-1].split()[-1].lower() if a_s[:-1].split() else ""
            seguinte = re.match(r"[^\W\d_]+", b_s)
            if (anterior, seguinte.group(0).lower() if seguinte else "") in _GUION_FIXO:
                return a_s + _desescapar(b_s)
            return a_s[:-1] + b_s
        if b_s[0].isalpha():
            return a_s + _desescapar(b_s)  # nome composto: Pérez-García
        return None
    if ancho is None or len(a_s) < _FRACCION_ANCHO * ancho:
        return None
    if _e_maiusculas(a_s) != _e_maiusculas(b_s):
        return None
    if _FIN_DE_FRASE.search(a_s) and not (
        _empeza_en_minuscula(b_s) and _ultima_palabra(a_s) in _ABREVIATURAS
    ):
        return None
    return a_s + " " + _desescapar(b_s)


def _marcas_de_cabeceiras() -> set:
    return {f"<!-- {idioma.t('copia_md.cabeceiras', lingua)} -->" for lingua in _MARCAS_PAXINA}


def _unir_liñas(texto: str) -> str:
    liñas = texto.split("\n")
    ancho = _ancho_habitual(liñas)
    cabeceiras = _marcas_de_cabeceiras()
    saida, estado = [], 0  # estado: 0 normal, 1 despois da marca das cabeceiras, 2 nas súas liñas (cada unha a súa)
    for liña in liñas:
        if liña.strip() in cabeceiras:
            estado = 1
        elif not liña.strip():
            estado = 1 if estado == 1 else 0
        elif estado == 1:
            estado = 2
        if saida and not estado:
            unida = _unir_dúas(saida[-1], liña, ancho)
            if unida is not None:
                saida[-1] = unida
                continue
        saida.append(liña)
    return "\n".join(saida)


# -- troceado ---------------------------------------------------------------

_PARTE_MINIMA = 0.3  # un corte forte (páxina/título) só vale se a parte xa chega a esta fracción


def _bloques(texto: str) -> list:
    return [b for b in re.split(r"\n{2,}", texto.strip("\n")) if b.strip()]


def _e_taboa(bloque: str) -> bool:
    liñas = [l for l in bloque.split("\n") if l.strip()]
    return bool(liñas) and all(l.lstrip().startswith("|") for l in liñas)


def _e_corte_forte(bloque: str, patron: re.Pattern) -> bool:
    return bool(patron.match(bloque.split("\n", 1)[0])) or bloque.startswith("#")


def _trocear(texto: str, maximo: int, base: str) -> list:
    patron = _patron_marca()
    bloques = _bloques(texto)
    n = len(bloques)
    taboas = [_e_taboa(b) for b in bloques]
    # Pódese cortar antes do bloque i salvo entre dúas táboas seguidas.
    cortable = [i > 0 and not (taboas[i - 1] and taboas[i]) for i in range(n)]
    forte = [_e_corte_forte(b, patron) for b in bloques]
    tamaño = [len(b) + 2 for b in bloques]

    rangos, inicio = [], 0
    while inicio < n:
        fin, total = inicio, 0
        while fin < n and (fin == inicio or total + tamaño[fin] <= maximo):
            total += tamaño[fin]
            fin += 1
        if fin == n:
            rangos.append((inicio, n))
            break
        opcions = [k for k in range(inicio + 1, fin + 1) if cortable[k]]
        if not opcions:  # unha táboa máis grande ca unha parte: vai enteira
            k = next((k for k in range(fin + 1, n) if cortable[k]), n)
        else:
            fortes = [k for k in opcions if forte[k] and sum(tamaño[inicio:k]) >= _PARTE_MINIMA * maximo]
            k = max(fortes) if fortes else max(opcions)
        rangos.append((inicio, k))
        inicio = k

    cifras = max(2, len(str(len(rangos))))
    partes, ultima_paxina = [], None
    for numero, (a, b) in enumerate(rangos, 1):
        corpo = "\n\n".join(bloques[a:b])
        primeira = patron.search(corpo)
        paxinas = [int(next(g for g in m.groups() if g)) for m in patron.finditer(corpo)]
        if paxinas:
            inicial = paxinas[0] if primeira.start() == 0 else (ultima_paxina or paxinas[0])
            final = paxinas[-1]
            ultima_paxina = final
        else:
            inicial = final = None
        partes.append(Parte(
            nome=f"{base}.parte-{numero:0{cifras}d}.md", texto=corpo, paxina_inicial=inicial,
            paxina_final=final, resumo=_resumo_da_parte(bloques[a:b]),
        ))
    total = len(partes)
    for numero, parte in enumerate(partes, 1):
        cabeceira = idioma.t("aforro_ia.parte", n=numero, total=total)
        if parte.paxina_inicial is not None:
            cabeceira += " · " + idioma.t("aforro_ia.paxinas", a=parte.paxina_inicial, b=parte.paxina_final)
        parte.texto = f"<!-- {cabeceira} -->\n\n" + parte.texto + "\n"
    return partes


def _resumo_da_parte(bloques: list, maximo: int = 90) -> str:
    """Primeiro título da parte ou, se non hai, a primeira liña de texto."""
    for b in bloques:
        for liña in b.split("\n"):
            if liña.startswith("#"):
                return _acurtar(liña.lstrip("# "), maximo)
    for b in bloques:
        for liña in b.split("\n"):
            if _e_liña_de_texto(liña):
                return _acurtar(liña.strip(), maximo)
    return ""


def _acurtar(texto: str, maximo: int) -> str:
    return texto if len(texto) <= maximo else texto[: maximo - 1].rstrip() + "…"


def _indice(partes: list, base: str) -> str:
    liñas = [f"# {idioma.t('aforro_ia.indice', nome=base)}", "", idioma.t("aforro_ia.indice_aviso"), ""]
    for p in partes:
        datos = []
        if p.paxina_inicial is not None:
            datos.append(idioma.t("aforro_ia.paxinas", a=p.paxina_inicial, b=p.paxina_final))
        datos.append(f"{idioma.t('aforro_ia.caracteres', n=_miles(len(p.texto)))} (≈ {_miles(estimar_tokens(p.texto))} tokens)")
        liña = f"- [{p.nome}]({p.nome}): " + " · ".join(datos)
        if p.resumo:
            liña += f" · «{p.resumo}»"
        liñas.append(liña)
    return "\n".join(liñas) + "\n"
