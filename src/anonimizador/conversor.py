"""Conversor de ficheiros a .md para IA (ESTUDIO-CONVERSOR-MD, fase 2).

Converte en local un ficheiro, un cartafol ou un .zip a Markdown, para que
a IA non teña que convertelos e gaste menos tokens ao lelos. Usa o
mesmo motor có anonimizador, nunca unha copia:

- **Sen anonimizar**: `lectura.cargar_documento_estruturado` +
  `markdown_ia.xerar` co texto orixinal. Este camiño NON importa `pipeline`,
  `ner` nin `spacy` (`tests/test_conversor.py` compróbao nun subproceso):
  un paquete que só converta non ten que levar o NER.
- **Anonimizando**: `pipeline.anonimizar_texto_detallado` sobre o mesmo
  texto lido, e `markdown_ia.xerar` co texto anonimizado (do orixinal só a
  estrutura): a MESMA función, coas mesmas opcións, cá copia .md do
  anonimizador (`tests/test_markdown_ia.py`). Os nomes de ficheiro e
  de cartafol anonimízanse coma no zip do anonimizador. Sen o enganche
  `revisar` (a liña de comandos) non hai revisión humana: quen chama debe
  avisalo, e o .md leva `revisado: non`; se a detección atopou posibles
  fugas (risco residual alto), tamén `posibles_fugas: N`, que se quita ao
  revisalo (`substituir_revisado`). Co .md único, a cabeceira leva o total
  e a sección de cada documento afectado, a súa liña.

Nomes de saída: `demanda.pdf.md` sen anonimizar e
`<nome anonimizado>.anonimizado.pdf.md` anonimizando (o criterio da copia
.md da 1.1.0: un `.pdf` e un `.docx` co mesmo nome non se pisan, e un
`notas.md` de entrada non se sobrescribe). Unha saída doutra execución
co mesmo nome substitúese; dúas saídas da MESMA execución co mesmo nome
levan un contador (`demanda-2.pdf.md`).

Cada .md leva unha cabeceira mínima (`orixe`, `paxinas`, `anonimizado:
si/non`, `convertido`). Con `un_so_md`, un cartafol ou un .zip xera un só
.md cun índice e unha sección por ficheiro. O que non se sabe converter
queda en `Resultado.omitidos`, coma os `omitidos` de `anonimizar_zip`.

Puntos de enganche (as ramas que os enchen intégranse ao fusionar):

- `LECTORES_EXTRA`: extensión -> lector, para formatos novos. Un lector
  devolve o Markdown (`str`) ou un `formatos.Conversion` (Markdown e avisos,
  que van a `Resultado.avisos`). Énchese cos de `formatos/` (fase 4). Só se
  usan SEN anonimizar: un formato novo non se converte anonimizando ata ter
  as súas probas de fugas (estudo, punto 6; `formatos/ESCONDITES.md`); ata
  entón queda omitido con motivo `sen_proba_de_fugas`.
Aforro para IA (`aforro_ia`, fase 3, dentro de `markdown_ia.xerar`), por
defecto: cabeceiras e pés repetidos unha vez, liñas partidas unidas e
espazos de sobra fóra, en cada documento (`aforro=False` para non tocalo). Con `caracteres_por_parte`, un
.md máis longo trócease en `<nome>.parte-01.md`... e `<nome>.indice.md`,
cada un coa súa cabeceira (`anonimizado: si/non` vai en todos: as partes
pásanse soltas á IA). `Resultado.tokens_antes`/`tokens_despois`: estimación.

- `POSPROCESADOS`: funcións `str -> str` que se aplican, en orde, ao
  Markdown de cada documento, despois dos títulos e antes do aforro
  (`markdown_ia.xerar`). No modo
  anonimizado reciben o texto xa anonimizado, así que non poden sacar á
  luz nada orixinal.

Escritura incremental (15/11/2026): cada .md escríbese en canto se converte o
seu documento, non ao final do lote; un lote longo que falla ou se cancela
non perde o xa convertido. Sen `un_so_md`, cada .md é un ficheiro completo
(escrito dunha vez, `.tmp` + `os.replace`). Con `un_so_md`, as seccións
engádense a `<nome>.md.parcial` (sen índice, con `conversión: incompleta`) e,
ao rematar, ao cancelar ou ao fallar, constrúese o `.md` definitivo e bórrase
o `.parcial`; se o proceso morre sen poder pechar, queda só o `.parcial`.
`Cancelado` e calquera excepción que pare o lote levan `resultado_parcial`.

Enganches da pantalla (`pantalla_conversor.py`, fase 2b), argumentos de
`converter`: `progreso(feito, total, nome)` antes de cada documento e ao
remate; `cancelar() -> bool`, mirado antes de cada documento (se di que
si, `Cancelado`: o que xa se gardou queda gardado, ver abaixo); e, anonimizando, `revisar(nome, texto, contexto, texto_anonimizado,
informe, substitucions)`, que devolve `(texto_anonimizado, substitucions)`
xa revisados (o documento leva `revisado: si`) ou `None` (queda coma
automático, `revisado: non`). A revisión en si (`pipeline.aplicar_decisions`)
faina quen chama: aquí só se usa o seu resultado.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Callable

from . import aforro_ia, formatos, idioma, lectura, markdown_ia, pdf_estrutura
from .temporales import DirectorioTemporal
from .arranque_windows import NOME_CARTAFOL, cartafol_documentos

if TYPE_CHECKING:
    from .registry import RexistroCorrespondencias

VERSION = "1.2.0"

LECTORES_EXTRA: dict[str, Callable] = {ext: formatos.convertir for ext in formatos.EXTENSIONS}
POSPROCESADOS: list[Callable[[str], str]] = []


class Cancelado(Exception):
    """A pantalla cancelou a conversión (`cancelar` ou `revisar`). O que xa se
    gardou queda gardado: `resultado_parcial` (poñeo `converter`) di o que."""

    resultado_parcial = None


def rexistro_por_defecto() -> Path:
    """O rexistro do anonimizador da Store (`Documentos\\Anonimizador`, ver
    `arranque_windows`): co mesmo rexistro, unha persoa recibe o mesmo
    código nos dous programas (estudo, proposta 12.2). O bloqueo entre
    procesos de `registry` permite telos abertos á vez."""
    return cartafol_documentos() / NOME_CARTAFOL / "datos_rexistro"


@dataclass
class Resultado:
    saidas: list = field(default_factory=list)  # rutas dos .md escritos
    omitidos: list = field(default_factory=list)  # (nome orixinal, motivo)
    erros: dict = field(default_factory=dict)  # nome orixinal -> erro ao ler
    informes: dict = field(default_factory=dict)  # nome anonimizado -> informe (só anonimizando)
    avisos: dict = field(default_factory=dict)  # nome orixinal -> avisos do lector (formatos novos)
    tokens_antes: int = 0  # estimación (`aforro_ia.estimar_tokens`) do Markdown sen aforro
    tokens_despois: int = 0  # ... e do escrito
    revisados: list = field(default_factory=list)  # nomes anonimizados (coma `informes`) revisados por unha persoa
    csv: list = field(default_factory=list)  # rutas dos .csv á parte (follas grandes), canda o seu .md
    documentos: dict = field(default_factory=dict)  # nome orixe (o que recibe `revisar`) -> DocumentoSaida
    _lote: object = field(default=None, repr=False, compare=False)  # o que fai falta para `substituir_revisado`

    def resumo_tokens(self) -> str:
        """Frase da estimación de tokens antes e despois (di que é unha estimación)."""
        return aforro_ia.Resultado("", 0, 0, self.tokens_antes, self.tokens_despois).resumo()


@dataclass
class DocumentoSaida:
    """Un documento convertido: de onde ven e onde quedou."""

    orixe: str  # nome relativo á entrada (un ficheiro solto: o seu nome), coma o que recibe `revisar`
    nome_visible: str  # o mesmo nome tal como sae no .md (anonimizado se cómpre): a chave de `Resultado.informes`
    informe: dict | None = None  # só anonimizando
    saidas: list = field(default_factory=list)  # .md escritos (o .md único, se hai `un_so_md`; con partes e índice, todos)


@dataclass
class _Documento:
    nome: PurePosixPath  # relativo á entrada (un ficheiro solto: o seu nome)
    ruta: Path  # ficheiro local que se le


@dataclass
class _Convertido:
    cartafol: PurePosixPath  # cartafol de saída, relativo (anonimizado se cómpre)
    stem: str  # nome de saída sen `cola`
    cola: str  # ".pdf.md" ou ".anonimizado.pdf.md"
    nome_visible: str  # nome do orixinal (anonimizado se cómpre) para cabeceira e índice
    corpo: str
    paxinas: int | None
    avisos: list = field(default_factory=list)
    revisado: bool = False
    fugas: int = 0  # posibles fugas (risco residual alto) sen revisar: van á cabeceira (`posibles_fugas: N`)
    csv: list = field(default_factory=list)  # .csv á parte que o lector deixou nun cartafol temporal
    orixe: str = ""  # str(_Documento.nome)
    ruta: Path | None = None  # o .md principal escrito (sen `un_so_md`)
    tokens_antes: int = 0  # estimación do Markdown antes do aforro (`markdown_ia.xerar`)
    tokens_despois: int = 0


@dataclass
class _Lote:
    """O necesario para volver escribir un documento xa convertido (`substituir_revisado`)."""

    convertidos: dict  # nome orixe -> _Convertido
    anonimizar: bool
    un_so_md: bool
    aforro: bool
    caracteres_por_parte: int | None
    data: datetime.date
    nome_entrada: str
    ruta_unico: Path | None = None  # o .md único (`un_so_md`)
    omitidos: list = field(default_factory=list)  # (nome visible, motivo) para o índice do .md único
    saidas_unico: list = field(default_factory=list)
    incompleto: bool = False  # o lote parou (cancelado ou erro) antes de converter todo: o .md único di `conversión: incompleta`


def _extensions() -> tuple:
    return (*lectura.EXTENSIONS_SOPORTADAS, *LECTORES_EXTRA)


def _motivo_omision(nome: str, anonimizar: bool) -> str | None:
    sufixo = PurePosixPath(nome).suffix.lower()
    if sufixo in lectura.EXTENSIONS_SOPORTADAS:
        return None
    if sufixo in LECTORES_EXTRA:
        return "sen_proba_de_fugas" if anonimizar else None
    return "formato"


_PARTE_OU_INDICE = re.compile(r"\.(parte-\d+|indice)\.md$")


def _e_saida_anterior(nome: str) -> bool:
    """`demanda.pdf.md`, `x.anonimizado.pdf.md` (conversor ou copia .md do
    anonimizador), `x.anonimizado.pdf` (anonimizador), `expediente.zip.md`,
    e as partes e índices dun troceado (`demanda.pdf.parte-01.md`,
    `expediente.indice.md`): nun cartafol, volver convertelos enchería o
    cartafol de `.md.md`."""
    if _PARTE_OU_INDICE.search(nome.lower()):
        return True
    ruta = PurePosixPath(nome.lower())
    if ruta.stem.endswith(".anonimizado"):
        return True
    return ruta.suffix == ".md" and PurePosixPath(ruta.stem).suffix in (*_extensions(), ".zip")


MAX_DESCOMPRIMIDO = 2 * 1024**3  # bytes que unha execución descomprime en total dos .zip (contra zip bombs)
SUFIXO_CARTAFOL_ZIP = "-md"  # un .zip nun cartafol sae no subcartafol `<nome do zip sen .zip>-md`
_ESPERA_SUBSTITUIR = 0.2  # segundos entre intentos de `os.replace` (Windows: antivirus ou indexador co ficheiro aberto)


class _ZipRexeitado(Exception):
    """Un .zip que non se abre enteiro (demasiado grande ao descomprimir); leva o motivo."""

    def __init__(self, motivo: str):
        super().__init__(motivo)
        self.motivo = motivo


def _nome_seguro(nome: str) -> PurePosixPath:
    """Ruta dunha entrada dun .zip sen `..`, raíz nin unidade: o cartafol de
    saída sae desta ruta, así que un `../../x.pdf` nunca escribe fóra del."""
    partes = [p for p in nome.replace("\\", "/").split("/") if p not in ("", ".", "..") and not p.endswith(":")]
    return PurePosixPath(*partes) if partes else PurePosixPath("_")


def _documentos(entrada: Path, tmp: Path, anonimizar: bool) -> tuple[list, list]:
    """(documentos, omitidos) dun ficheiro, un cartafol ou un .zip.

    Un .zip dentro dun cartafol ábrese coma se fose a entrada, e os seus
    documentos saen no subcartafol `<nome do zip sen .zip>-md` (á altura do
    zip). Un .zip dentro dun .zip non se abre (profundidade 1: `zip_dentro_de_zip`).
    Un .zip que descomprimiría máis do que queda de `MAX_DESCOMPRIMIDO` ou
    que non se pode abrir omítese enteiro (`zip_demasiado_grande`,
    `zip_ilexible`); non se escribe nada a medias."""
    documentos, omitidos = [], []
    queda = [MAX_DESCOMPRIMIDO]
    numero = [0]

    def engadir(nome: PurePosixPath, ruta_ou_lector, docs=documentos, omit=omitidos):
        motivo = _motivo_omision(nome.name, anonimizar)
        if motivo:
            omit.append((str(nome), motivo))
        else:
            docs.append(_Documento(nome, ruta_ou_lector()))

    def abrir_zip(ruta_zip: Path, prefixo: PurePosixPath, aniñado: bool, docs: list, omit: list) -> None:
        """Documentos e omitidos dun .zip en `docs` e `omit`. `prefixo`: o
        subcartafol de saída dos seus documentos (baleiro se o zip é a
        entrada); `aniñado`: o zip está dentro doutro (un .zip dentro non se abre)."""
        usados = 0

        def nome_visible(nome: PurePosixPath) -> str:
            return str(prefixo / nome) if prefixo.parts else str(nome)

        with zipfile.ZipFile(ruta_zip) as zip_entrada:
            candidatos = []
            for info in zip_entrada.infolist():
                if info.is_dir():
                    continue
                nome = _nome_seguro(info.filename)
                if "__MACOSX" in nome.parts or nome.name.startswith("._"):
                    omit.append((nome_visible(nome), "metadatos_macos"))
                elif nome.suffix.lower() == ".zip":
                    omit.append((nome_visible(nome), "zip_dentro_de_zip"))
                elif _motivo_omision(nome.name, anonimizar):
                    omit.append((nome_visible(nome), _motivo_omision(nome.name, anonimizar)))
                else:
                    candidatos.append((info, nome))
            if sum(info.file_size for info, _ in candidatos) > queda[0]:
                raise _ZipRexeitado("zip_demasiado_grande")
            for info, nome in candidatos:
                numero[0] += 1
                # Só o nome do ficheiro, nun cartafol propio: nunca a ruta do
                # zip nin choques entre homónimos.
                destino = tmp / str(numero[0]) / nome.name
                destino.parent.mkdir()
                with zip_entrada.open(info) as orixe, destino.open("wb") as saida:
                    while bloque := orixe.read(1 << 20):
                        usados += len(bloque)
                        if usados > queda[0]:  # a cabeceira do zip mentía sobre o tamaño
                            raise _ZipRexeitado("zip_demasiado_grande")
                        saida.write(bloque)
                docs.append(_Documento(prefixo / nome, destino))
        queda[0] -= usados

    def abrir_zip_de_cartafol(ruta: Path, nome: PurePosixPath) -> None:
        subcartafol = nome.parent / (nome.stem + SUFIXO_CARTAFOL_ZIP)
        docs, omit = [], []
        try:
            abrir_zip(ruta, subcartafol, False, docs, omit)
        except _ZipRexeitado as e:
            omitidos.append((str(nome), e.motivo))
            return
        except Exception:  # noqa: BLE001 -- un .zip roto ou cifrado non para o cartafol
            omitidos.append((str(nome), "zip_ilexible"))
            return
        documentos.extend(docs)
        omitidos.extend(omit)

    if entrada.is_dir():
        for ruta in sorted(entrada.rglob("*")):
            if ruta.is_dir():
                continue
            nome = PurePosixPath(ruta.relative_to(entrada).as_posix())
            if _e_saida_anterior(nome.name):
                omitidos.append((str(nome), "saida_anterior"))
            elif nome.suffix.lower() == ".zip":
                abrir_zip_de_cartafol(ruta, nome)
            else:
                engadir(nome, lambda ruta=ruta: ruta)
    elif entrada.suffix.lower() == ".zip":
        try:
            abrir_zip(entrada, PurePosixPath(), True, documentos, omitidos)
        except _ZipRexeitado as e:
            omitidos.append((entrada.name, e.motivo))
    else:
        engadir(PurePosixPath(entrada.name), lambda: entrada)
    return documentos, omitidos


def _con_salto_final(texto: str) -> str:
    return texto.rstrip("\n") + "\n"


def _converter_documento(doc: _Documento, anonimizar: bool, rexistro, revisar=None, dir_csv: Path | None = None,
                         aforro: bool = True) -> tuple:
    """(_Convertido, informe ou None). `dir_csv`: onde o lector deixa os .csv
    á parte (só sen anonimizar; ver `converter`). O corpo sae SEMPRE de
    `markdown_ia.xerar`, a mesma cadea cá copia .md do anonimizador."""
    opcions = markdown_ia.opcions_do_reductor(aforro)
    sufixo_orixinal = PurePosixPath(doc.nome.name).suffix
    sufixo = sufixo_orixinal.lower()
    if sufixo not in lectura.EXTENSIONS_SOPORTADAS:  # formato novo: só chega aquí sen anonimizar
        # Nunca se pide o .csv á parte anonimizando: o .csv non pasaría polo anonimizador.
        opcions_lector = {"dir_csv": str(dir_csv)} if dir_csv is not None and not anonimizar else {}
        lido = LECTORES_EXTRA[sufixo](str(doc.ruta), **opcions_lector)
        corpo, avisos, ficheiros = (lido, [], []) if isinstance(lido, str) else (
            lido.markdown, list(lido.avisos), list(lido.ficheiros))
        md = markdown_ia.xerar(None, corpo, aforro=opcions, xa_markdown=True, posprocesados=POSPROCESADOS)
        return _Convertido(doc.nome.parent, PurePosixPath(doc.nome.name).stem, sufixo_orixinal + ".md",
                           str(doc.nome), md.texto, None, avisos, csv=ficheiros, orixe=str(doc.nome),
                           tokens_antes=md.tokens_antes, tokens_despois=md.tokens_despois), None

    texto, contexto = lectura.cargar_documento_estruturado(str(doc.ruta))
    paxinas = None
    if contexto and contexto.get("tipo") == "pdf" and not contexto.get("imaxe"):
        paxinas = len(contexto["paxinas"])

    if not anonimizar:
        # Un .md de entrada xa é Markdown: tal cal (`copia_md.xerar` escaparía os seus títulos).
        md = markdown_ia.xerar(contexto, texto, aforro=opcions, xa_markdown=sufixo == ".md",
                               posprocesados=POSPROCESADOS)
        return _Convertido(doc.nome.parent, PurePosixPath(doc.nome.name).stem, sufixo_orixinal + ".md",
                           str(doc.nome), md.texto, paxinas, orixe=str(doc.nome),
                           tokens_antes=md.tokens_antes, tokens_despois=md.tokens_despois), None

    from . import pipeline  # só aquí: o modo sen anonimizar non carga o NER

    texto_anon, informe, substitucions = pipeline.anonimizar_texto_detallado(texto, rexistro, contexto=contexto)
    revisado = None
    if revisar is not None:
        revisado = revisar(str(doc.nome), texto, contexto, texto_anon, informe, substitucions)
        if revisado is not None:
            texto_anon, substitucions = revisado
    md = _corpo_anonimizado(sufixo, contexto, texto_anon, substitucions, aforro)
    # En automático, as posibles fugas quedan marcadas no propio .md: se a
    # persoa non pulsa «Revisar», o ficheiro segue avisando (valoración R1).
    fugas = 0 if revisado is not None else _contar_fugas(informe)
    # O nome DESPOIS do contido, cos seus códigos (A17, ver `nome_ficheiro_anonimizado`).
    nome_ficheiro = pipeline.nome_ficheiro_anonimizado(doc.nome.name, rexistro, informe["persoas"])
    cartafol = pipeline._anonimizar_cartafoles_ruta(doc.nome.parent, rexistro, informe["persoas"])
    nome_visible = str(cartafol / nome_ficheiro)
    stem = PurePosixPath(nome_ficheiro).stem
    return _Convertido(cartafol, stem, ".anonimizado" + sufixo_orixinal + ".md", nome_visible, md.texto, paxinas,
                       revisado=revisado is not None, fugas=fugas, orixe=str(doc.nome),
                       tokens_antes=md.tokens_antes, tokens_despois=md.tokens_despois), informe


def _contar_fugas(informe: dict) -> int:
    """As posibles fugas que o resumo final lista (risco residual de confianza alta)."""
    return sum(1 for r in informe.get("risco_residual", []) if r.get("confianza") == "alta")


def _corpo_anonimizado(sufixo: str, contexto, texto_anon: str, substitucions, aforro: bool) -> aforro_ia.Resultado:
    return markdown_ia.xerar(contexto, texto_anon, substitucions, aforro=markdown_ia.opcions_do_reductor(aforro),
                             xa_markdown=sufixo == ".md", posprocesados=POSPROCESADOS)


def _nome_omitido_visible(nome: str, rexistro) -> str:
    """Nome dun omitido tal como pode saír nun .md anonimizado."""
    from . import pipeline

    ruta = PurePosixPath(nome)
    return str(pipeline._anonimizar_cartafoles_ruta(ruta.parent, rexistro)
               / pipeline.nome_ficheiro_anonimizado(ruta.name, rexistro))


# -- Markdown -----------------------------------------------------------------

_YAML_ESPECIAL = re.compile(r"""^[-?:,\[\]{}#&*!|>'"%@`\s]|:\s|\s#|\s$""")


def _valor_yaml(valor: str) -> str:
    valor = " ".join(str(valor).split())
    return json.dumps(valor, ensure_ascii=False) if not valor or _YAML_ESPECIAL.search(valor) else valor


def _cabeceira(orixe: str, anonimizado: bool, data: datetime.date, paxinas: int | None = None,
               ficheiros: int | None = None, revisado: bool = False, posibles_fugas: int = 0,
               incompleto: bool = False) -> str:
    liñas = ["---", f"{idioma.t('conversor.orixe')}: {_valor_yaml(orixe)}"]
    if paxinas:
        liñas.append(f"{idioma.t('conversor.paxinas')}: {paxinas}")
    if ficheiros is not None:
        liñas.append(f"{idioma.t('conversor.ficheiros')}: {ficheiros}")
    liñas.append(f"anonimizado: {idioma.t('conversor.si' if anonimizado else 'conversor.non')}")
    if anonimizado:
        liñas.append(f"{idioma.t('conversor.revisado')}: {idioma.t('conversor.si' if revisado else 'conversor.non')}")
        if posibles_fugas:
            liñas.append(_liña_fugas(posibles_fugas))
    if incompleto:
        liñas.append(f"{idioma.t('conversor.conversion')}: {idioma.t('conversor.incompleta')}")
    liñas.append(f"{idioma.t('conversor.convertido')}: {data.isoformat()}, {idioma.t('conversor.nome')} {VERSION}")
    return "\n".join(liñas) + "\n---\n"


_TITULO = re.compile(r"(#{1,5})(\s)")
_VALADO = re.compile(r"(```|~~~)")


def _liña_fugas(n: int) -> str:
    return f"{idioma.t('conversor.posibles_fugas')}: {n}"


def _baixar_titulos(corpo: str) -> str:
    """Os títulos dun documento, un nivel por debaixo da súa sección no .md
    único (fóra dos bloques de código dun .md de entrada)."""
    liñas, en_codigo = [], False
    for liña in corpo.split("\n"):
        if _VALADO.match(liña):
            en_codigo = not en_codigo
        elif not en_codigo:
            liña = _TITULO.sub(r"#\1\2", liña, count=1) if _TITULO.match(liña) else liña
        liñas.append(liña)
    return "\n".join(liñas)


def _paxinas_texto(paxinas: int) -> str:
    return idioma.t("conversor.unha_paxina") if paxinas == 1 else idioma.t("conversor.n_paxinas", n=paxinas)


def _indice_unico(convertidos: list, omitidos: list) -> str:
    indice = [f"# {idioma.t('conversor.indice')}", ""]
    for i, c in enumerate(convertidos, 1):
        indice.append(f"{i}. {c.nome_visible}" + (f" ({_paxinas_texto(c.paxinas)})" if c.paxinas else ""))
    if omitidos:
        indice += ["", f"{idioma.t('conversor.sen_converter')}:", ""]
        indice += [f"- {nome} ({idioma.t('conversor.motivo.' + motivo)})" for nome, motivo in omitidos]
    return "\n".join(indice)


def _seccion_unica(c: _Convertido, corpo: str) -> str:
    """A sección dun documento no .md único (a mesma no .parcial e no definitivo)."""
    corpo = _baixar_titulos(corpo).strip("\n")
    aviso = "\n\n" + _liña_fugas(c.fugas) if c.fugas else ""
    return f"# {c.nome_visible}" + aviso + ("\n\n" + corpo if corpo else "")


def _un_so_md(convertidos: list, corpos: list, omitidos: list) -> str:
    """Corpo (sen cabeceira) do .md único. `corpos`: o de cada convertido,
    xa posprocesado. `omitidos`: [(nome visible, motivo)]."""
    partes = [_indice_unico(convertidos, omitidos)]
    partes += [_seccion_unica(c, corpo) for c, corpo in zip(convertidos, corpos)]
    return "\n\n".join(partes) + "\n"


def _corpo_final(c: _Convertido, resultado: Resultado) -> str:
    """Corpo xa posprocesado e aforrado (`markdown_ia.xerar`); suma a estimación de tokens."""
    resultado.tokens_antes += c.tokens_antes
    resultado.tokens_despois += c.tokens_despois
    return c.corpo


def _colocar_csv(c: _Convertido, destino: Path, usados: set, resultado: Resultado) -> None:
    """Move os .csv á parte de `c` ao cartafol do seu .md. Se o nome xa o
    colleu outro documento da mesma execución, leva un contador, e o .md e os
    avisos (que o nomean) cámbianse con el."""
    destino.mkdir(parents=True, exist_ok=True)
    for orixe in map(Path, c.csv):
        final = destino / orixe.name
        contador = 2
        while final in usados:
            final = destino / f"{orixe.stem}-{contador}{orixe.suffix}"
            contador += 1
        usados.add(final)
        shutil.move(str(orixe), final)
        if final.name != orixe.name:
            c.corpo = c.corpo.replace(orixe.name, final.name)
            c.avisos[:] = [a.replace(orixe.name, final.name) for a in c.avisos]  # no sitio: `Resultado.avisos` comparte a lista
        c.avisos.append(idioma.t("conversor.aviso_csv_aparte", ruta=final))
        resultado.csv.append(str(final))


def _escribir_tmp(destino: Path, texto: str) -> Path:
    """`destino` + `.tmp`, enteiro; se falla, sen deixar o `.tmp`."""
    tmp = destino.with_name(destino.name + ".tmp")
    try:
        tmp.write_text(texto, encoding="utf-8")
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return tmp


def _substituir(tmp: Path, destino: Path, texto: str) -> None:
    """Pon `tmp` no lugar de `destino` (`os.replace`: nunca un .md a medias).
    En Windows pode fallar un intre (antivirus, indexador): reinténtase; se
    segue sen deixar (o .md aberto noutro programa), escríbese directamente,
    que xa non é atómico. O `.tmp` non queda nunca, nin se isto falla."""
    try:
        for intento in range(3):
            try:
                os.replace(tmp, destino)
                return
            except PermissionError:
                if intento < 2:
                    time.sleep(_ESPERA_SUBSTITUIR)
        destino.write_text(texto, encoding="utf-8")
    finally:
        tmp.unlink(missing_ok=True)


def _gardar_texto(destino: Path, texto: str) -> None:
    _substituir(_escribir_tmp(destino, texto), destino, texto)


def _escribir(ruta: Path, cabeceira: str, corpo: str, caracteres_por_parte: int | None, saidas: list) -> None:
    """Escribe `ruta` ou, se o corpo pasa de `caracteres_por_parte`, as súas
    partes e o índice no mesmo cartafol, todos coa cabeceira. Primeiro todos
    os `.tmp` e despois as substitucións: se falla un `.tmp`, os ficheiros de
    antes (doutra execución, ou o .md que se revisa) quedan intactos. Un fallo
    xa substituíndo (moi raro) pode deixar partes novas e vellas mesturadas,
    pero non se borra ningunha. `saidas` só recibe as rutas se todo vai ben."""
    textos = [(ruta, corpo)]
    if caracteres_por_parte and len(corpo) > caracteres_por_parte:
        so_trocear = aforro_ia.Opcions(quitar_repetidas=False, unir_liñas=False, limpar_espazos=False,
                                       caracteres_por_parte=caracteres_por_parte)
        troceado = aforro_ia.aforrar(corpo, so_trocear, nome_base=ruta.name.removesuffix(".md"))
        if troceado.partes:
            textos = [(ruta.with_name(p.nome), p.texto) for p in troceado.partes]
            textos.append((ruta.with_name(troceado.nome_indice), troceado.indice))
    preparados = []
    try:
        for destino, texto in textos:
            contido = cabeceira + "\n" + _con_salto_final(texto)
            preparados.append((destino, _escribir_tmp(destino, contido), contido))
        escritos = []
        for destino, tmp, contido in preparados:
            _substituir(tmp, destino, contido)
            escritos.append(str(destino))
    finally:
        for _, tmp, _ in preparados:
            tmp.unlink(missing_ok=True)
    saidas.extend(escritos)


# -- conversión -----------------------------------------------------------------

def converter(
    entrada: str,
    *,
    anonimizar: bool = False,
    un_so_md: bool = False,
    saida: str | None = None,
    rexistro: RexistroCorrespondencias | None = None,
    data: datetime.date | None = None,
    aforro: bool = True,
    caracteres_por_parte: int | None = None,
    progreso: Callable[[int, int, str], None] | None = None,
    cancelar: Callable[[], bool] | None = None,
    revisar: Callable | None = None,
    csv_aparte: bool = True,
    progreso_paxina: Callable[[int, int], None] | None = None,
) -> Resultado:
    """Converte `entrada` (ficheiro, cartafol ou .zip) a .md.

    Saída (`saida`, un cartafol, se se indica):
    - ficheiro: canda o orixinal;
    - cartafol: cada .md canda o seu orixinal (coma o anonimizador cos
      cartafoles); con `saida`, a mesma estrutura de subcartafoles alí;
    - .zip: un cartafol `<nome>-md` canda o zip;
    - `un_so_md` (cartafol ou .zip): `expediente.md` / `expediente.zip.md`
      canda a entrada.
    Anonimizando, os nomes de cartafoles e ficheiros de saída tamén van
    anonimizados. `rexistro` é obrigatorio para anonimizar. `progreso`,
    `cancelar` e `revisar`: ver o comezo do módulo.

    `csv_aparte` (por defecto si): as follas de máis de `follas.MAX_FILAS`
    filas van a un `.csv` canda o seu `.md` (no mesmo cartafol; a ruta sae
    en `Resultado.csv` e nos avisos) e o `.md` leva só a cabeceira de
    columnas; sen el a táboa sae enteira, cun aviso. Só afecta aos formatos
    novos, que só se converten sen anonimizar."""
    with DirectorioTemporal() as tmp_csv:  # os .csv viven aquí ata a fase de escritura
        return _converter(entrada, Path(tmp_csv), anonimizar, un_so_md, saida, rexistro, data, aforro,
                          caracteres_por_parte, progreso, cancelar, revisar, csv_aparte,
                          progreso_paxina)


_ERROS_SEGUIDOS_DE_ESCRITURA = 3  # tres documentos seguidos sen poder gardarse: a saída non vale, para o lote


class _Escritor:
    """Garda cada documento en canto se converte (ver o comezo do módulo).

    Sen `un_so_md`, un .md por documento no seu sitio de sempre. Con
    `un_so_md`, as seccións van a `<nome>.md.parcial` e `finalizar` constrúe o
    definitivo. O nome da entrada (un .zip anonimizando) fíxase unha vez, ao
    gardar o primeiro documento, e non cambia en todo o lote."""

    def __init__(self, entrada: Path, e_zip: bool, anonimizar: bool, un_so_md: bool, saida: str | None, rexistro,
                 data: datetime.date, caracteres_por_parte: int | None, resultado: Resultado, paquete: _Lote):
        self.entrada, self.e_zip, self.anonimizar, self.un_so_md = entrada, e_zip, anonimizar, un_so_md
        self.saida, self.rexistro, self.data, self.caracteres_por_parte = saida, rexistro, data, caracteres_por_parte
        self.resultado, self.paquete = resultado, paquete
        self.usadas: set = set()
        self.usados_csv: set = set()
        self.convertidos: list = []  # os gardados, en orde (o .md único sae deles)
        self.destino: Path | None = None
        self.ruta_unico: Path | None = None
        self.ruta_parcial: Path | None = None
        self.finalizado = False
        self._fixado = False
        self._parcial_iniciado = False

    def fixar_nomes(self, informe: dict | None) -> None:
        """Nome da entrada tal como pode saír (anonimizado DESPOIS do contido)
        e destino, unha soa vez. Co `informe` do primeiro documento, un nome
        de persoa do .zip que tamén sae no contido recibe o seu mesmo código
        (A17); non se pode facer antes de converter ese documento: rexistraría
        a persoa antes do contido e cambiaría o seu código e o aviso de homónimo."""
        if self._fixado:
            return
        entrada, e_zip, anonimizar = self.entrada, self.e_zip, self.anonimizar
        nome_entrada = entrada.name
        if anonimizar and (e_zip or (self.un_so_md and entrada.is_dir())):
            from . import pipeline

            nome_entrada = pipeline.nome_ficheiro_anonimizado(
                entrada.name, self.rexistro, informe["persoas"] if informe else None)
        base_entrada = PurePosixPath(nome_entrada).stem if e_zip else nome_entrada
        if self.un_so_md:
            cola = (".anonimizado" if anonimizar else "") + (".zip" if e_zip else "") + ".md"
            self.destino = Path(self.saida) if self.saida else entrada.parent
            self.ruta_unico = self.destino / (base_entrada + cola)
            self.ruta_parcial = self.ruta_unico.with_name(self.ruta_unico.name + ".parcial")
        elif self.saida:
            self.destino = Path(self.saida)
        elif entrada.is_dir():
            self.destino = entrada
        elif e_zip:
            self.destino = entrada.parent / (base_entrada + (".anonimizado" if anonimizar else "") + "-md")
        else:
            self.destino = entrada.parent
        self.paquete.nome_entrada = nome_entrada
        self._fixado = True

    def gardar(self, c: _Convertido) -> None:
        """Escribe o documento `c` (despois de `fixar_nomes`). Se falla, non queda rexistrado."""
        resultado = self.resultado
        if self.un_so_md:
            self.destino.mkdir(parents=True, exist_ok=True)
            _colocar_csv(c, self.destino, self.usados_csv, resultado)
            self._engadir_ao_parcial(c)
            self.convertidos.append(c)
        else:
            ruta = self.destino / c.cartafol / (c.stem + c.cola)
            contador = 2
            while ruta in self.usadas:
                ruta = self.destino / c.cartafol / (f"{c.stem}-{contador}" + c.cola)
                contador += 1
            ruta.parent.mkdir(parents=True, exist_ok=True)
            _colocar_csv(c, ruta.parent, self.usados_csv, resultado)
            cabeceira = _cabeceira(c.nome_visible, self.anonimizar, self.data, paxinas=c.paxinas,
                                   revisado=c.revisado, posibles_fugas=c.fugas)
            saidas: list = []
            _escribir(ruta, cabeceira, c.corpo, self.caracteres_por_parte, saidas)
            self.usadas.add(ruta)
            c.ruta = ruta
            resultado.saidas.extend(saidas)
            resultado.documentos[c.orixe].saidas = saidas
            c.corpo = ""  # xa está en disco: `substituir_revisado` pon o novo
        resultado.tokens_antes += c.tokens_antes
        resultado.tokens_despois += c.tokens_despois
        self.paquete.convertidos[c.orixe] = c

    def _engadir_ao_parcial(self, c: _Convertido) -> None:
        novo = not self._parcial_iniciado  # un .parcial doutra execución que morreu non se continúa: substitúese
        texto = ""
        if novo:
            texto = _cabeceira(self.paquete.nome_entrada, self.anonimizar, self.data, incompleto=True)
        texto += "\n" + _seccion_unica(c, c.corpo) + "\n"
        with self.ruta_parcial.open("w" if novo else "a", encoding="utf-8") as f:
            f.write(texto)
        self._parcial_iniciado = True

    def finalizar(self, incompleto: bool = False) -> None:
        """Constrúe o .md único definitivo (co índice) e quita o .parcial.
        `incompleto`: o lote parou; sen documentos gardados non hai nada que pechar."""
        if not self.un_so_md or self.finalizado or (incompleto and not self.convertidos):
            return
        resultado, paquete = self.resultado, self.paquete
        self.fixar_nomes(None)
        omitidos = resultado.omitidos
        if self.anonimizar:
            omitidos = [(_nome_omitido_visible(n, self.rexistro), m) for n, m in omitidos]
        convertidos = self.convertidos
        cabeceira = _cabeceira(paquete.nome_entrada, self.anonimizar, self.data, ficheiros=len(convertidos),
                               revisado=bool(convertidos) and all(c.revisado for c in convertidos),
                               posibles_fugas=sum(c.fugas for c in convertidos), incompleto=incompleto)
        saidas: list = []
        self.destino.mkdir(parents=True, exist_ok=True)
        _escribir(self.ruta_unico, cabeceira, _un_so_md(convertidos, [c.corpo for c in convertidos], omitidos),
                  self.caracteres_por_parte, saidas)
        self.finalizado = True
        resultado.saidas.extend(saidas)
        paquete.ruta_unico, paquete.omitidos, paquete.saidas_unico = self.ruta_unico, omitidos, list(saidas)
        paquete.incompleto = incompleto
        for c in convertidos:
            resultado.documentos[c.orixe].saidas = paquete.saidas_unico
        self.ruta_parcial.unlink(missing_ok=True)

    def pechar_incompleto(self) -> None:
        """O lote para (cancelado ou erro): péchase o .md único co que hai. Se nin
        así se pode, queda o .parcial, que se anota en `saidas`."""
        try:
            self.finalizar(incompleto=True)
        except Exception:  # noqa: BLE001 -- xa hai outro erro en marcha; non o tapamos con este
            if self.ruta_parcial is not None and self.ruta_parcial.exists():
                self.resultado.saidas.append(str(self.ruta_parcial))


def _converter(entrada, tmp_csv, anonimizar, un_so_md, saida, rexistro, data, aforro, caracteres_por_parte,
               progreso, cancelar, revisar, csv_aparte, progreso_paxina=None) -> Resultado:
    entrada = Path(entrada)
    if anonimizar and rexistro is None:
        raise ValueError("Para anonimizar fai falta o rexistro de correspondencias")
    if not entrada.exists():
        raise FileNotFoundError(str(entrada))
    data = data or datetime.date.today()
    e_zip = entrada.is_file() and entrada.suffix.lower() == ".zip"
    lote = entrada.is_dir() or e_zip
    un_so_md = un_so_md and lote
    resultado = Resultado()
    paquete = _Lote({}, anonimizar, un_so_md, aforro, caracteres_por_parte, data, entrada.name)
    if anonimizar:  # só se pode revisar despois o que se anonimizou
        resultado._lote = paquete
    escritor = _Escritor(entrada, e_zip, anonimizar, un_so_md, saida, rexistro, data, caracteres_por_parte,
                         resultado, paquete)

    with DirectorioTemporal() as tmp:
        documentos, resultado.omitidos = _documentos(entrada, Path(tmp), anonimizar)
        try:
            erros_de_escritura = 0
            for i, doc in enumerate(documentos):
                if cancelar is not None and cancelar():
                    raise Cancelado
                if progreso is not None:
                    progreso(i, len(documentos), str(doc.nome))
                dir_csv = None
                if csv_aparte and not anonimizar:
                    dir_csv = tmp_csv / str(i)
                    dir_csv.mkdir()

                def _paxina(feita, total_paxinas):
                    if cancelar is not None and cancelar():  # tamén no medio dun PDF longo
                        raise Cancelado
                    if progreso_paxina is not None:
                        progreso_paxina(feita, total_paxinas)

                try:
                    with pdf_estrutura.progreso_paxinas(_paxina):
                        convertido, informe = _converter_documento(
                            doc, anonimizar, rexistro, revisar if anonimizar else None, dir_csv, aforro)
                except Cancelado:
                    raise
                except Exception as e:  # noqa: BLE001 -- un documento roto non para o lote
                    resultado.omitidos.append((str(doc.nome), "erro"))
                    resultado.erros[str(doc.nome)] = f"{type(e).__name__}: {e}"
                    continue
                escritor.fixar_nomes(informe)  # un fallo aquí para o lote: afecta a todos os documentos
                resultado.documentos[convertido.orixe] = DocumentoSaida(
                    convertido.orixe, convertido.nome_visible, informe)
                try:
                    escritor.gardar(convertido)  # o .md queda en disco AGORA, non ao final do lote
                except Exception as e:  # noqa: BLE001 -- un .md que non se pode gardar non para o lote
                    del resultado.documentos[convertido.orixe]
                    resultado.omitidos.append((str(doc.nome), "erro_escritura"))
                    resultado.erros[str(doc.nome)] = f"{type(e).__name__}: {e}"
                    erros_de_escritura += 1
                    if erros_de_escritura >= _ERROS_SEGUIDOS_DE_ESCRITURA:
                        raise
                    continue
                erros_de_escritura = 0
                if convertido.avisos:
                    resultado.avisos[str(doc.nome)] = convertido.avisos
                if informe is not None:
                    resultado.informes[convertido.nome_visible] = informe
                if convertido.revisado:
                    resultado.revisados.append(convertido.nome_visible)
            escritor.finalizar()
        except BaseException as e:
            escritor.pechar_incompleto()
            e.resultado_parcial = resultado
            raise
        if progreso is not None:
            progreso(len(documentos), len(documentos), "")
    return resultado


def substituir_revisado(resultado: Resultado, orixe: str, texto_anon: str, substitucions, contexto) -> tuple[list, list]:
    """Despois de converter en automático: un documento que unha persoa
    acaba de revisar (co motor do anonimizador, fóra de `converter`) substitúe
    o seu .md, agora con `revisado: si`. `orixe`: a chave de
    `Resultado.documentos`; `texto_anon` e `substitucions`: o resultado da
    revisión (`pipeline.aplicar_decisions`); `contexto`: o da lectura. O nome
    de saída non cambia. Con `un_so_md`, rescríbese o .md único enteiro (o
    seu índice e as demais seccións quedan como estaban). Devolve
    (saídas de antes, saídas de agora); a estimación de tokens do
    `Resultado` non se corrixe."""
    lote: _Lote = resultado._lote
    c = lote.convertidos[orixe]
    antes = (c.corpo, c.tokens_antes, c.tokens_despois, c.revisado, c.fugas)
    try:
        return _substituir_revisado(resultado, lote, c, orixe, texto_anon, substitucions, contexto)
    except BaseException:
        c.corpo, c.tokens_antes, c.tokens_despois, c.revisado, c.fugas = antes  # o .md segue sendo o de antes
        raise


def _substituir_revisado(resultado, lote, c, orixe, texto_anon, substitucions, contexto) -> tuple[list, list]:
    md = _corpo_anonimizado(PurePosixPath(orixe).suffix.lower(), contexto, texto_anon, substitucions, lote.aforro)
    c.corpo, c.tokens_antes, c.tokens_despois = md.texto, md.tokens_antes, md.tokens_despois
    c.revisado, c.fugas = True, 0  # revisado por unha persoa: fóra a marca de posibles fugas
    marcador = Resultado()  # a estimación dos tokens non se conta dúas veces
    if lote.un_so_md:
        antigas = list(lote.saidas_unico)
        convertidos = list(lote.convertidos.values())
        corpos = [_corpo_final(x, marcador) for x in convertidos]
        cabeceira = _cabeceira(lote.nome_entrada, lote.anonimizar, lote.data, ficheiros=len(convertidos),
                               revisado=all(x.revisado for x in convertidos),
                               posibles_fugas=sum(x.fugas for x in convertidos), incompleto=lote.incompleto)
        novas: list = []
        # Primeiro o novo, despois quitar o que sobra (outro número de partes): nunca se perde o .md.
        _escribir(lote.ruta_unico, cabeceira, _un_so_md(convertidos, corpos, lote.omitidos),
                  lote.caracteres_por_parte, novas)
        _borrar([a for a in antigas if a not in novas])
        lote.saidas_unico[:] = novas
        for x in convertidos:
            resultado.documentos[x.orixe].saidas = lote.saidas_unico
    else:
        antigas = list(resultado.documentos[orixe].saidas)
        novas = []
        cabeceira = _cabeceira(c.nome_visible, lote.anonimizar, lote.data, paxinas=c.paxinas, revisado=True)
        _escribir(c.ruta, cabeceira, _corpo_final(c, marcador), lote.caracteres_por_parte, novas)
        _borrar([a for a in antigas if a not in novas])
        c.corpo = ""  # xa está en disco
        resultado.documentos[orixe].saidas = novas
    resultado.saidas = [s for s in resultado.saidas if s not in antigas] + novas
    if c.nome_visible not in resultado.revisados:
        resultado.revisados.append(c.nome_visible)
    return antigas, novas


def _borrar(rutas: list) -> None:
    for ruta in rutas:
        Path(ruta).unlink(missing_ok=True)
