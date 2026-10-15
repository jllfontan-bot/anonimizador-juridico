"""PDF CONFIDENCIAL co listado completo de correspondencias código <-> persoa.

Petición do usuario (03/10/2026): poder xerar un PDF do listado, advertindo de
que é un documento de extrema sensibilidade, cunha marca de auga
"CONFIDENCIAL". O PDF sae do rexistro cifrado: quen o teña ve as identidades
reais sen ningunha contrasinal. Por iso a web pide un aviso expreso, a
contrasinal de reversión e deixa constancia na auditoría (ver
`web.listar_correspondencias_pdf`).

Só PyMuPDF (xa vai no instalador). A fonte é a "cjk" que trae MuPDF: ten
tamén as letras doutros idiomas ("Šinál", "Łukasz") que a Helvetica base
non pinta; incrústase só co subconxunto de caracteres usados.
"""

from __future__ import annotations

from datetime import datetime

import fitz  # PyMuPDF

from . import idioma

_ANCHO, _ALTO = fitz.paper_size("a4-l")  # apaisado: cabe a táboa enteira
_MARXE = 36
_FONTE = "uni"
_TAMANO = 8.5
_ENTRELIÑA = 11.5


def _columnas(entradas: list, lingua: str) -> list:
    """(título, chave, ancho relativo), sen as columnas que van baleiras."""
    t = lambda clave: idioma.t(clave, lingua)  # noqa: E731
    columnas = [(t("pdf.col_codigo"), "codigo", 1.2), (t("pdf.col_nomes"), "nomes", 3.2), ("DNI", "dni", 1.2)]
    if any(e.get("contexto") for e in entradas):
        columnas.append((t("pdf.col_contexto"), "contexto", 2.2))
    columnas.append((t("pdf.col_creado"), "creado", 0.9))
    if any(e.get("fusionados") for e in entradas):
        columnas.append((t("pdf.col_fusionados"), "fusionados", 1.6))
    return columnas


def _valor(entrada: dict, chave: str, lingua: str) -> str:
    valor = entrada.get(chave)
    if chave == "codigo":
        return idioma.codigo_visible(valor, lingua) if valor else "—"
    if chave == "fusionados":
        return ", ".join(idioma.codigo_visible(c, lingua) for c in valor or [])
    if chave == "nomes":
        return ", ".join(valor or [])
    if chave == "creado":
        return (valor or "")[:10]
    return valor or "—"


def _partir(texto: str, ancho: float, fonte: "fitz.Font") -> list:
    liñas, actual = [], ""
    for palabra in texto.split():
        proba = f"{actual} {palabra}".strip()
        if fonte.text_length(proba, fontsize=_TAMANO) <= ancho or not actual:
            actual = proba
        else:
            liñas.append(actual)
            actual = palabra
    return liñas + [actual] if actual else [""]


def _marca_de_auga(paxina: "fitz.Page") -> None:
    centro = fitz.Point(_ANCHO / 2, _ALTO / 2)
    texto, tamano = "CONFIDENCIAL", 92
    ancho = fitz.Font("helv").text_length(texto, fontsize=tamano)
    inicio = fitz.Point(centro.x - ancho / 2, centro.y + tamano / 3)
    paxina.insert_text(inicio, texto, fontsize=tamano, fontname="helv", color=(0.85, 0.1, 0.1),
                       fill_opacity=0.13, stroke_opacity=0.13,
                       morph=(centro, fitz.Matrix(30)), overlay=True)


def _cabeceira(paxina: "fitz.Page", motivo: str, solicitante: str | None, data: str, total: int,
               lingua: str) -> float:
    y = _MARXE
    paxina.insert_text((_MARXE, y + 14), idioma.t("pdf.titulo", lingua),
                       fontname=_FONTE, fontsize=15, color=(0.55, 0.05, 0.05))
    y += 26
    detalle = idioma.t("pdf.xerado", lingua, data=data)
    if solicitante:
        detalle += idioma.t("pdf.por", lingua, solicitante=solicitante)
    detalle += idioma.t("pdf.motivo_total", lingua, motivo=motivo, total=total)
    paxina.insert_text((_MARXE, y + 9), detalle, fontname=_FONTE, fontsize=9, color=(0.2, 0.2, 0.2))
    y += 16
    caixa = fitz.Rect(_MARXE, y, _ANCHO - _MARXE, y + 40)
    paxina.draw_rect(caixa, color=(0.75, 0.2, 0.2), fill=(1, 0.95, 0.93), width=0.8)
    paxina.insert_textbox(caixa + (6, 4, -6, -4), idioma.t("pdf.aviso", lingua), fontname=_FONTE, fontsize=8.5,
                          color=(0.45, 0.05, 0.05))
    return y + 52


def listado_correspondencias(resultado: dict, motivo: str, solicitante: str | None = None,
                             data: str | None = None) -> bytes:
    """`resultado` é o que devolve `RexistroCorrespondencias.listar_correspondencias`."""
    data = data or datetime.now().strftime("%d/%m/%Y %H:%M")
    lingua = idioma.actual()
    entradas = resultado.get("entradas", [])
    columnas = _columnas(entradas, lingua)
    fonte = fitz.Font("cjk")
    total_relativo = sum(c[2] for c in columnas)
    anchos = [(_ANCHO - 2 * _MARXE) * c[2] / total_relativo for c in columnas]

    documento = fitz.open()
    def nova_paxina():
        paxina = documento.new_page(width=_ANCHO, height=_ALTO)
        paxina.insert_font(fontname=_FONTE, fontbuffer=fonte.buffer)
        return paxina

    def alto_da_fila(valores):
        return max(len(_partir(v, a - 8, fonte)) for v, a in zip(valores, anchos)) * _ENTRELIÑA + 6

    def fila(paxina, y, valores, cabeceira=False):
        alto = alto_da_fila(valores)
        x = _MARXE
        for valor, ancho in zip(valores, anchos):
            rect = fitz.Rect(x, y, x + ancho, y + alto)
            paxina.draw_rect(rect, color=(0.75, 0.75, 0.75), fill=(0.16, 0.36, 0.3) if cabeceira else None,
                             width=0.4)
            for n, liña in enumerate(_partir(valor, ancho - 8, fonte)):
                paxina.insert_text((x + 4, y + 4 + _TAMANO + n * _ENTRELIÑA), liña, fontname=_FONTE,
                                   fontsize=_TAMANO, color=(1, 1, 1) if cabeceira else (0, 0, 0))
            x += ancho
        return y + alto

    paxina = nova_paxina()
    y = _cabeceira(paxina, motivo, solicitante, data, resultado.get("total", len(entradas)), lingua)
    titulos = [c[0] for c in columnas]
    y = fila(paxina, y, titulos, cabeceira=True)
    if not entradas:
        paxina.insert_text((_MARXE, y + 16), idioma.t("pdf.baleiro", lingua),
                           fontname=_FONTE, fontsize=10)
    for entrada in entradas:
        valores = [_valor(entrada, c[1], lingua) for c in columnas]
        if y + alto_da_fila(valores) > _ALTO - _MARXE - 14:
            paxina = nova_paxina()
            y = fila(paxina, _MARXE, titulos, cabeceira=True)
        y = fila(paxina, y, valores)
    if resultado.get("alias_orfos"):
        paxina.insert_text((_MARXE, min(y + 16, _ALTO - _MARXE - 20)),
                           idioma.t("pdf.orfos", lingua)
                           + ", ".join(idioma.codigo_visible(c, lingua) for c in resultado["alias_orfos"]),
                           fontname=_FONTE, fontsize=8.5, color=(0.5, 0.1, 0.1))

    # As páxinas vellas quedan sen documento ao crear outras: pídense de novo.
    for n in range(1, len(documento) + 1):
        paxina = documento[n - 1]
        paxina.insert_text((_MARXE, _ALTO - _MARXE + 10),
                           idioma.t("pdf.pe", lingua, n=n, total=len(documento)),
                           fontname=_FONTE, fontsize=8, color=(0.55, 0.05, 0.05))
        _marca_de_auga(paxina)

    documento.subset_fonts()
    documento.set_metadata({"title": idioma.t("pdf.metadatos", lingua), "producer": "", "creator": ""})
    datos = documento.tobytes(garbage=4, deflate=True)
    documento.close()
    return datos
