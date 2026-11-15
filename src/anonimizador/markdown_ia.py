"""Markdown final dun documento: UNHA soa cadea para os dous programas.

O Reductor de tokens (`conversor.py`, nos dous modos) e a copia .md do
Anonimizador (`pipeline.py` e `web.py`; `cli.py` vai por `pipeline`) chaman
a `xerar`, e só a ela, para pasar dun texto lido (ou xa anonimizado) ao
Markdown que se escribe:

  1. `copia_md.xerar`: estrutura (títulos e listas de .docx/.odt, táboas,
     marcas de páxina do PDF, texto do OCR). Con `xa_markdown` (un `.md` de
     entrada, ou o que devolve un lector de `formatos/`) o texto xa é
     Markdown e vai tal cal: `copia_md.xerar` escaparía os seus títulos.
  2. `titulos_pdf.marcar_titulos_md`: títulos dun PDF con texto, polo
     tamaño da letra.
  3. `posprocesados`: funcións `str -> str`, en orde (o enganche
     `conversor.POSPROCESADOS`; o Anonimizador non pasa ningunha).
  4. `aforro_ia.aforrar` coas opcións `aforro`: cabeceiras e pés repetidos
     escritos unha vez, liñas partidas unidas, espazos de sobra fóra.

O único que distingue a un programa do outro é o parámetro `aforro`:

- Reductor: `AFORRO` ou `SEN_AFORRO`, segundo a casa «aforro» da
  pantalla ou `--sen-aforro` (por defecto, `AFORRO`).
- Anonimizador: sempre `AFORRO_ANONIMIZADOR`, que é o mesmo `AFORRO`. A
  copia .md vai canda o documento anonimizado para que unha IA a lea sen
  convertela, que é o mesmo fin có do Reductor; e os tres pasos só quitan ou
  xuntan o que xa está no texto anonimizado (as cabeceiras repetidas xa van
  cos seus códigos e escríbense unha vez ao principio; o número de cada
  páxina segue na marca `<!-- páxina N -->`). O documento anonimizado, que é
  o que se revisa e se entrega, non cambia. O que si queda fóra do
  Anonimizador é o RESUMO do aforro (`Resultado.resumo`, «≈ N tokens antes
  e despois»): é unha mensaxe da pantalla do Reductor, non parte do .md.
- O troceado en partes (`Opcions.caracteres_por_parte`) non é desta cadea:
  é unha forma de ESCRIBIR o .md (varios ficheiros, cada un coa súa
  cabeceira) que só fai o Reductor (`conversor._escribir`); aquí rexéitase.

SEGURIDADE (modo anonimizado): todo o texto do resultado sae de `texto`, o
texto xa anonimizado. `copia_md` e `titulos_pdf` só len do orixinal a
estrutura (estilos, táboas, tamaño da letra), e `titulos_pdf` só pon `#`
diante de liñas que xa están no Markdown; `aforro_ia` só quita, move ou
xunta liñas do propio Markdown. `tests/test_markdown_ia.py` compróbao cun
documento sintético. Chamar ANTES de gardar o documento anonimizado: gardar
un PDF redacta `contexto["documento"]` no sitio.

Este módulo non importa `pipeline`, `ner` nin `spacy`: o Reductor sen
anonimizar non ten que levar o NER.
"""

from __future__ import annotations

from typing import Callable, Iterable

from . import aforro_ia, copia_md, titulos_pdf

AFORRO = aforro_ia.Opcions()
SEN_AFORRO = aforro_ia.Opcions(quitar_repetidas=False, unir_liñas=False, limpar_espazos=False)
AFORRO_ANONIMIZADOR = AFORRO


def xerar(
    contexto: dict | None,
    texto: str,
    substitucions: list | None = None,
    *,
    aforro: aforro_ia.Opcions,
    xa_markdown: bool = False,
    posprocesados: Iterable[Callable[[str], str]] = (),
) -> aforro_ia.Resultado:
    """Markdown final de `texto` (orixinal, ou anonimizado coas súas
    `substitucions`). Devolve o `aforro_ia.Resultado`: o Markdown en
    `.texto` e a estimación de tokens antes e despois do aforro. `aforro` é
    obrigatorio para que cada chamada diga explicitamente cal usa."""
    if aforro.caracteres_por_parte:
        raise ValueError("O troceado non é desta cadea: faino quen escribe (conversor._escribir)")
    if xa_markdown:
        md = texto
    else:
        md = titulos_pdf.marcar_titulos_md(copia_md.xerar(contexto, texto, substitucions),
                                           contexto, texto, substitucions)
    for funcion in posprocesados:
        md = funcion(md)
    return aforro_ia.aforrar(md, aforro)


def copia_do_anonimizador(contexto: dict | None, texto_anon: str, substitucions: list | None, sufixo: str) -> str:
    """Texto da copia .md do anonimizador (`copia_md.escribir` a garda):
    `xerar` con `AFORRO_ANONIMIZADOR`. `sufixo`: o da entrada (un `.md` vai
    tal cal, coma no Reductor; hoxe `copia_md.ruta_copia` non lle fai copia)."""
    return xerar(contexto, texto_anon, substitucions, aforro=AFORRO_ANONIMIZADOR,
                 xa_markdown=sufixo.lower() == ".md").texto


def opcions_do_reductor(aforro: bool) -> aforro_ia.Opcions:
    """A casa «aforro» do Reductor (`converter(aforro=...)`) en opcións."""
    return AFORRO if aforro else SEN_AFORRO
