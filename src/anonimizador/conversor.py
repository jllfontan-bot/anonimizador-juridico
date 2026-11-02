"""Conversor de ficheiros a .md para IA (ESTUDIO-CONVERSOR-MD, fase 2).

Converte en local un ficheiro, un cartafol ou un .zip a Markdown, para que
a IA non gaste tokens nin chamadas a ferramentas convertíndoo ela. Usa o
mesmo motor có anonimizador, nunca unha copia:

- **Sen anonimizar**: `lectura.cargar_documento_estruturado` +
  `copia_md.xerar` co texto orixinal. Este camiño NON importa `pipeline`,
  `ner` nin `spacy` (`tests/test_conversor.py` compróbao nun subproceso):
  un paquete que só converta non ten que levar o NER.
- **Anonimizando**: `pipeline.anonimizar_texto_detallado` sobre o mesmo
  texto lido, e `copia_md.xerar` co texto anonimizado (do orixinal só a
  estrutura, coma na copia .md do anonimizador). Os nomes de ficheiro e
  de cartafol anonimízanse coma no zip do anonimizador. Sen o enganche
  `revisar` (a liña de comandos) non hai revisión humana: quen chama debe
  avisalo, e o .md leva `revisado: non`.

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
Aforro para IA (`aforro_ia`, fase 3), por defecto: cabeceiras e pés
repetidos unha vez, liñas partidas unidas e espazos de sobra fóra, en cada
documento (`aforro=False` para non tocalo). Con `caracteres_por_parte`, un
.md máis longo trócease en `<nome>.parte-01.md`... e `<nome>.indice.md`,
cada un coa súa cabeceira (`anonimizado: si/non` vai en todos: as partes
pásanse soltas á IA). `Resultado.tokens_antes`/`tokens_despois`: estimación.

- `POSPROCESADOS`: funcións `str -> str` que se aplican, en orde, ao
  Markdown de cada documento antes da cabeceira (`aforro_ia.py`). No modo
  anonimizado reciben o texto xa anonimizado, así que non poden sacar á
  luz nada orixinal.

Enganches da pantalla (`pantalla_conversor.py`, fase 2b), argumentos de
`converter`: `progreso(feito, total, nome)` antes de cada documento e ao
remate; `cancelar() -> bool`, mirado antes de cada documento (se di que
si, `Cancelado` e non se escribe nada: as escrituras van todas despois de
ler); e, anonimizando, `revisar(nome, texto, contexto, texto_anonimizado,
informe, substitucions)`, que devolve `(texto_anonimizado, substitucions)`
xa revisados (o documento leva `revisado: si`) ou `None` (queda coma
automático, `revisado: non`). A revisión en si (`pipeline.aplicar_decisions`)
faina quen chama: aquí só se usa o seu resultado.
"""

from __future__ import annotations

import datetime
import json
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Callable

from . import aforro_ia, copia_md, formatos, idioma, lectura, titulos_pdf
from .arranque_windows import NOME_CARTAFOL, cartafol_documentos

if TYPE_CHECKING:
    from .registry import RexistroCorrespondencias

VERSION = "1.0.0"

LECTORES_EXTRA: dict[str, Callable] = {ext: formatos.convertir for ext in formatos.EXTENSIONS}
POSPROCESADOS: list[Callable[[str], str]] = []


class Cancelado(Exception):
    """A pantalla cancelou a conversión (`cancelar` ou `revisar`)."""


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

    def resumo_tokens(self) -> str:
        """Frase da estimación de tokens antes e despois (di que é unha estimación)."""
        return aforro_ia.Resultado("", 0, 0, self.tokens_antes, self.tokens_despois).resumo()


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
    csv: list = field(default_factory=list)  # .csv á parte que o lector deixou nun cartafol temporal


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


def _documentos(entrada: Path, tmp: Path, anonimizar: bool) -> tuple[list, list]:
    """(documentos, omitidos) dun ficheiro, un cartafol ou un .zip."""
    documentos, omitidos = [], []

    def engadir(nome: PurePosixPath, ruta_ou_lector):
        motivo = _motivo_omision(nome.name, anonimizar)
        if motivo:
            omitidos.append((str(nome), motivo))
        else:
            documentos.append(_Documento(nome, ruta_ou_lector()))

    if entrada.is_dir():
        for ruta in sorted(entrada.rglob("*")):
            if ruta.is_dir():
                continue
            nome = PurePosixPath(ruta.relative_to(entrada).as_posix())
            if _e_saida_anterior(nome.name):
                omitidos.append((str(nome), "saida_anterior"))
            else:
                engadir(nome, lambda ruta=ruta: ruta)
    elif entrada.suffix.lower() == ".zip":
        with zipfile.ZipFile(entrada) as zip_entrada:
            for i, info in enumerate(zip_entrada.infolist()):
                if info.is_dir():
                    continue
                nome = PurePosixPath(info.filename)
                if "__MACOSX" in nome.parts or nome.name.startswith("._"):
                    omitidos.append((info.filename, "metadatos_macos"))
                    continue

                def extraer(info=info, nome=nome, i=i):
                    # Só o nome do ficheiro, nun cartafol propio: nunca a
                    # ruta do zip ("../") nin choques entre homónimos.
                    destino = tmp / str(i) / nome.name
                    destino.parent.mkdir()
                    destino.write_bytes(zip_entrada.read(info))
                    return destino

                engadir(nome, extraer)
    else:
        engadir(PurePosixPath(entrada.name), lambda: entrada)
    return documentos, omitidos


def _con_salto_final(texto: str) -> str:
    return texto.rstrip("\n") + "\n"


def _converter_documento(doc: _Documento, anonimizar: bool, rexistro, revisar=None, dir_csv: Path | None = None) -> tuple:
    """(_Convertido, informe ou None). `dir_csv`: onde o lector deixa os .csv
    á parte (só sen anonimizar; ver `converter`)."""
    sufixo_orixinal = PurePosixPath(doc.nome.name).suffix
    sufixo = sufixo_orixinal.lower()
    if sufixo not in lectura.EXTENSIONS_SOPORTADAS:  # formato novo: só chega aquí sen anonimizar
        # Nunca se pide o .csv á parte anonimizando: o .csv non pasaría polo anonimizador.
        opcions = {"dir_csv": str(dir_csv)} if dir_csv is not None and not anonimizar else {}
        lido = LECTORES_EXTRA[sufixo](str(doc.ruta), **opcions)
        corpo, avisos, ficheiros = (lido, [], []) if isinstance(lido, str) else (
            lido.markdown, list(lido.avisos), list(lido.ficheiros))
        return _Convertido(doc.nome.parent, PurePosixPath(doc.nome.name).stem, sufixo_orixinal + ".md",
                           str(doc.nome), corpo, None, avisos, csv=ficheiros), None

    texto, contexto = lectura.cargar_documento_estruturado(str(doc.ruta))
    paxinas = None
    if contexto and contexto.get("tipo") == "pdf" and not contexto.get("imaxe"):
        paxinas = len(contexto["paxinas"])

    if not anonimizar:
        # Un .md de entrada xa é Markdown: tal cal (`xerar` escaparía os seus títulos).
        corpo = texto if sufixo == ".md" else titulos_pdf.marcar_titulos_md(copia_md.xerar(contexto, texto), contexto, texto)
        return _Convertido(doc.nome.parent, PurePosixPath(doc.nome.name).stem, sufixo_orixinal + ".md",
                           str(doc.nome), corpo, paxinas), None

    from . import pipeline  # só aquí: o modo sen anonimizar non carga o NER

    texto_anon, informe, substitucions = pipeline.anonimizar_texto_detallado(texto, rexistro, contexto=contexto)
    revisado = None
    if revisar is not None:
        revisado = revisar(str(doc.nome), texto, contexto, texto_anon, informe, substitucions)
        if revisado is not None:
            texto_anon, substitucions = revisado
    corpo = texto_anon if sufixo == ".md" else titulos_pdf.marcar_titulos_md(
        copia_md.xerar(contexto, texto_anon, substitucions), contexto, texto_anon, substitucions)
    # O nome DESPOIS do contido, cos seus códigos (A17, ver `nome_ficheiro_anonimizado`).
    nome_ficheiro = pipeline.nome_ficheiro_anonimizado(doc.nome.name, rexistro, informe["persoas"])
    cartafol = pipeline._anonimizar_cartafoles_ruta(doc.nome.parent, rexistro, informe["persoas"])
    nome_visible = str(cartafol / nome_ficheiro)
    stem = PurePosixPath(nome_ficheiro).stem
    return _Convertido(cartafol, stem, ".anonimizado" + sufixo_orixinal + ".md", nome_visible, corpo, paxinas,
                       revisado=revisado is not None), informe


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
               ficheiros: int | None = None, revisado: bool = False) -> str:
    liñas = ["---", f"{idioma.t('conversor.orixe')}: {_valor_yaml(orixe)}"]
    if paxinas:
        liñas.append(f"{idioma.t('conversor.paxinas')}: {paxinas}")
    if ficheiros is not None:
        liñas.append(f"{idioma.t('conversor.ficheiros')}: {ficheiros}")
    liñas.append(f"anonimizado: {idioma.t('conversor.si' if anonimizado else 'conversor.non')}")
    if anonimizado:
        liñas.append(f"{idioma.t('conversor.revisado')}: {idioma.t('conversor.si' if revisado else 'conversor.non')}")
    liñas.append(f"{idioma.t('conversor.convertido')}: {data.isoformat()}, {idioma.t('conversor.nome')} {VERSION}")
    return "\n".join(liñas) + "\n---\n"


def _posprocesar(corpo: str) -> str:
    for funcion in POSPROCESADOS:
        corpo = funcion(corpo)
    return corpo


_TITULO = re.compile(r"(#{1,5})(\s)")
_VALADO = re.compile(r"(```|~~~)")


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


def _un_so_md(convertidos: list, corpos: list, omitidos: list) -> str:
    """Corpo (sen cabeceira) do .md único. `corpos`: o de cada convertido,
    xa posprocesado. `omitidos`: [(nome visible, motivo)]."""
    partes = []
    indice = [f"# {idioma.t('conversor.indice')}", ""]
    for i, c in enumerate(convertidos, 1):
        indice.append(f"{i}. {c.nome_visible}" + (f" ({_paxinas_texto(c.paxinas)})" if c.paxinas else ""))
    if omitidos:
        indice += ["", f"{idioma.t('conversor.sen_converter')}:", ""]
        indice += [f"- {nome} ({idioma.t('conversor.motivo.' + motivo)})" for nome, motivo in omitidos]
    partes.append("\n".join(indice))
    for c, corpo in zip(convertidos, corpos):
        corpo = _baixar_titulos(corpo).strip("\n")
        partes.append(f"# {c.nome_visible}" + ("\n\n" + corpo if corpo else ""))
    return "\n\n".join(partes) + "\n"


def _corpo_final(c: _Convertido, aforro: bool, resultado: Resultado) -> str:
    """Corpo posprocesado e, con `aforro`, aforrado; suma a estimación de tokens."""
    corpo = _posprocesar(c.corpo)
    resultado.tokens_antes += aforro_ia.estimar_tokens(corpo)
    if aforro:
        corpo = aforro_ia.aforrar(corpo).texto
    resultado.tokens_despois += aforro_ia.estimar_tokens(corpo)
    return corpo


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


def _escribir(ruta: Path, cabeceira: str, corpo: str, caracteres_por_parte: int | None, saidas: list) -> None:
    """Escribe `ruta` ou, se o corpo pasa de `caracteres_por_parte`, as súas
    partes e o índice no mesmo cartafol, todos coa cabeceira."""
    textos = [(ruta, corpo)]
    if caracteres_por_parte and len(corpo) > caracteres_por_parte:
        so_trocear = aforro_ia.Opcions(quitar_repetidas=False, unir_liñas=False, limpar_espazos=False,
                                       caracteres_por_parte=caracteres_por_parte)
        troceado = aforro_ia.aforrar(corpo, so_trocear, nome_base=ruta.name.removesuffix(".md"))
        if troceado.partes:
            textos = [(ruta.with_name(p.nome), p.texto) for p in troceado.partes]
            textos.append((ruta.with_name(troceado.nome_indice), troceado.indice))
    for destino, texto in textos:
        destino.write_text(cabeceira + "\n" + _con_salto_final(texto), encoding="utf-8")
        saidas.append(str(destino))


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
    with tempfile.TemporaryDirectory() as tmp_csv:  # os .csv viven aquí ata a fase de escritura
        return _converter(entrada, Path(tmp_csv), anonimizar, un_so_md, saida, rexistro, data, aforro,
                          caracteres_por_parte, progreso, cancelar, revisar, csv_aparte)


def _converter(entrada, tmp_csv, anonimizar, un_so_md, saida, rexistro, data, aforro, caracteres_por_parte,
               progreso, cancelar, revisar, csv_aparte) -> Resultado:
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

    with tempfile.TemporaryDirectory() as tmp:
        documentos, resultado.omitidos = _documentos(entrada, Path(tmp), anonimizar)
        convertidos = []
        for i, doc in enumerate(documentos):
            if cancelar is not None and cancelar():
                raise Cancelado
            if progreso is not None:
                progreso(i, len(documentos), str(doc.nome))
            dir_csv = None
            if csv_aparte and not anonimizar:
                dir_csv = tmp_csv / str(i)
                dir_csv.mkdir()
            try:
                convertido, informe = _converter_documento(
                    doc, anonimizar, rexistro, revisar if anonimizar else None, dir_csv)
            except Cancelado:
                raise
            except Exception as e:  # noqa: BLE001 -- un documento roto non para o lote
                resultado.omitidos.append((str(doc.nome), "erro"))
                resultado.erros[str(doc.nome)] = f"{type(e).__name__}: {e}"
                continue
            convertidos.append(convertido)
            if convertido.avisos:
                resultado.avisos[str(doc.nome)] = convertido.avisos
            if informe is not None:
                resultado.informes[convertido.nome_visible] = informe
            if convertido.revisado:
                resultado.revisados.append(convertido.nome_visible)
        if progreso is not None:
            progreso(len(documentos), len(documentos), "")

    # Nome da entrada tal como pode saír (anonimizado DESPOIS do contido).
    nome_entrada = entrada.name
    if anonimizar and lote:
        from . import pipeline

        nome_entrada = pipeline.nome_ficheiro_anonimizado(entrada.name, rexistro)
    base_entrada = PurePosixPath(nome_entrada).stem if e_zip else nome_entrada

    if un_so_md:
        omitidos = resultado.omitidos
        if anonimizar:
            omitidos = [(_nome_omitido_visible(n, rexistro), m) for n, m in omitidos]
        cola = (".anonimizado" if anonimizar else "") + (".zip" if e_zip else "") + ".md"
        destino = Path(saida) if saida else entrada.parent
        destino.mkdir(parents=True, exist_ok=True)
        ruta = destino / (base_entrada + cola)
        usados_csv: set = set()
        for c in convertidos:
            _colocar_csv(c, destino, usados_csv, resultado)
        corpos = [_corpo_final(c, aforro, resultado) for c in convertidos]
        cabeceira = _cabeceira(nome_entrada, anonimizar, data, ficheiros=len(convertidos),
                               revisado=bool(convertidos) and all(c.revisado for c in convertidos))
        _escribir(ruta, cabeceira, _un_so_md(convertidos, corpos, omitidos), caracteres_por_parte, resultado.saidas)
        return resultado

    if saida:
        destino = Path(saida)
    elif entrada.is_dir():
        destino = entrada
    elif e_zip:
        destino = entrada.parent / (base_entrada + (".anonimizado" if anonimizar else "") + "-md")
    else:
        destino = entrada.parent
    usadas = set()
    usados_csv: set = set()
    for c in convertidos:
        ruta = destino / c.cartafol / (c.stem + c.cola)
        contador = 2
        while ruta in usadas:
            ruta = destino / c.cartafol / (f"{c.stem}-{contador}" + c.cola)
            contador += 1
        usadas.add(ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        _colocar_csv(c, ruta.parent, usados_csv, resultado)
        cabeceira = _cabeceira(c.nome_visible, anonimizar, data, paxinas=c.paxinas, revisado=c.revisado)
        _escribir(ruta, cabeceira, _corpo_final(c, aforro, resultado), caracteres_por_parte, resultado.saidas)
    return resultado
