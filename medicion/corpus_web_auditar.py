#!/usr/bin/env python3
"""Auditoría automática do anonimizador sobre o corpus REAL (BOE + DOG).

Circuíto: PDF real -> pipeline completo (o mesmo ca a app: cargar ->
anonimizar -> gardar PDF) -> RELER o PDF de saída -> buscar indicios de
fallo -> informe clasificado por tipo.

Con documentos reais NON hai verdade coñecida: ninguén di que debía
desaparecer. Por iso isto só dá INDICIOS (e as cifras son estimacións); a
metodoloxía do proxecto esixe ademais lectura humana dunha mostra
(`corpus_web_mostra.py`).

Comprobacións (todas sobre o PDF de SAÍDA relido, non sobre o texto que
devolve o pipeline -- os fallos graves do pasado estaban na escritura do
PDF: sinatura en widget, texto oculto):

  - entidade_literal_no_texto: un anaco que o propio pipeline detectou e
    substituíu segue literal noutro sitio do texto anonimizado (outra
    aparición que a detección non viu). Fuga case segura.
  - entidade_literal_no_pdf: está no PDF de saída pero NON no texto
    anonimizado -> fallo ao escribir o PDF (redacción que non tapou).
  - entidade_oculta_no_pdf: non se ve coma texto da páxina pero está nos
    bytes do PDF (anotacións, formularios, metadatos, fluxos).
  - estrutura_pdf: o PDF de saída conserva anotacións, widgets, metadatos
    ou ficheiros incrustados.
  - risco_residual_alta: a rede de seguridade (`risco_residual.py`) sobre o
    texto relido do PDF de saída, confianza alta.
  - dni_parcial: DNI enmascarado ao estilo BOE ("***1234**") que segue no
    texto; con nome ao lado identifica.
  - posible_sobre_anonimizacion: unha "persoa" substituída que contén
    palabras de institución/lugar (Consellería, Concello, Xulgado...).
  - erro: excepción procesando o documento.
  - risco_residual_baixa: só se conta (moi ruidoso a propósito).

Saídas:
  - En `DIR/auditoria/` (LOCAL, fóra do repo): PDF anonimizados, textos e
    informe completo con contexto -> contén datos reais.
  - Con `--gardar-resumo`: `medicion/resultados/corpus-web-*.json` SÓ con
    contas por tipo e fonte, sen ningún texto dos documentos.

Uso:
    .venv/bin/python medicion/corpus_web_auditar.py [--dir DIR] [--limite N] [--gardar-resumo]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
import traceback
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import fitz  # noqa: E402

from anonimizador.pipeline import (  # noqa: E402
    anonimizar_texto_detallado, cargar_documento_estruturado, gardar_documento_estruturado,
)
from anonimizador.registry import RexistroCorrespondencias, normalizar_dni  # noqa: E402
from anonimizador.risco_residual import escanear_risco_residual  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus_web_descargar import DIR_POR_DEFECTO  # noqa: E402

GRAVIDADE = {
    "identificador_documental": "crítica",
    "nome_partido_en_linas": "crítica",
    "entidade_literal_no_pdf": "crítica",
    "entidade_oculta_no_pdf": "crítica",
    "estrutura_pdf": "crítica",
    "entidade_literal_no_texto": "alta",
    "risco_residual_alta": "alta",
    "dni_parcial": "media",
    "posible_sobre_anonimizacion": "media",
    "palabra_comun_tapada": "media",
    "erro": "alta",
    # Ficheiro de correspondencias código <-> persoa real (ver `comprobar_rexistro`).
    "rexistro_codigo_sen_entrada": "crítica",
    "rexistro_nome_non_corresponde": "crítica",
    "rexistro_dni_non_corresponde": "crítica",
    "rexistro_codigo_sen_uso": "media",
}

# Palabras que case nunca forman parte do nome dunha persoa física: se unha
# "persoa" substituída as leva, probablemente se tapou unha institución ou
# un lugar (sobre-anonimización). Castelán e galego.
_INSTITUCION_RE = re.compile(
    r"\b(consell[eé]r[ií]a|conseller[oa]?|concell?o|ayuntamiento|xulgado|juzgado|tribunal|"
    r"ministerio|universidad[ea]?|servizo|servicio|direcci[oó]n|"
    r"secretar[ií]a|delegaci[oó]n|subdelegaci[oó]n|diputaci[oó]n|deputaci[oó]n|xunta|"
    r"junta|gobierno|goberno|agencia|axencia|instituto|fundaci[oó]n|asociaci[oó]n|"
    r"colexio|colegio|hospital|centro|comisi[oó]n|consejo|consello|sociedad|sociedade|"
    r"s\.\s?l\.|s\.\s?a\.|rúa|calle|avenida|praza|plaza|provincia|real decreto|ley|lei|"
    r"boe|dog|bop|oficial|general|xeral|nacional|estado|español[a]?|galicia)\b",
    re.IGNORECASE,
)

# DNI parcialmente enmascarado (disposición adicional 7ª LOPDGDD): o BOE
# publica "***1234**"; variantes con X ou bolas.
_DNI_PARCIAL_RE = re.compile(r"(?<![\w*])[*xX•]{2,4}\d{3,5}[*xX•]{1,4}(?![\w*])|(?<!\w)\*{3,4}\d{4}[A-Z]?(?!\w)")


# Liña só con palabras en maiúsculas (apelidos) e a seguinte empeza por un
# código de persoa: "RODRIGUEZ LORENZO,\nPERSOA_000015."
_NOME_PARTIDO_RE = re.compile(
    r"(?m)^[ \t]*(?P<resto>[A-ZÁÉÍÓÚÑÜÇ][A-ZÁÉÍÓÚÑÜÇ'\-]+(?:[ \t]+[A-ZÁÉÍÓÚÑÜÇ'\-]+){0,4}[ \t]*,?)[ \t]*\n"
    r"[ \t]*(?P<codigo>PERSOA_\d{6})"
)
_NON_APELIDO_RE = re.compile(
    r"\b(SECRETAR[IÍ]A|DIVISI[OÓ]N|DATA|ACR[OÓ]NIMO|PORCENTAXES?|MATERIAL|FERROVIARIAS|TECNIC[OA]|"
    r"PUESTO|NIVEL|GRUPO|CUERPO|ESCALA|ANEXO|RELACI[OÓ]N|APELLIDOS|APELIDOS|NOMBRE|NOME)\b"
)
# Etiqueta de documento de identidade e, despois, un identificador que non
# é DNI/NIE (que xa se tapan): pasaportes e documentos estranxeiros.
_ETIQUETA_DOCUMENTO_RE = re.compile(
    r"\b(DNI/NIE/PAS|pasaporte|passport|documento de identidade|documento de identidad|"
    r"representante|NIE|DNI)\b", re.IGNORECASE)
_IDENTIFICADOR_RE = re.compile(
    r"(?<![\w\-/.])(?:(?=(?:[A-Z]*\d){5})(?=[A-Z0-9]*[A-Z])[A-Z0-9]{6,24}|\d{9,12})(?![\w\-/])")


def _norm(texto: str) -> str:
    """Espazos colapsados e guións de corte de liña eliminados: o texto
    relido dun PDF parte liñas onde o orixinal non as tiña."""
    texto = re.sub(r"-\n(?=\w)", "", texto)
    return " ".join(texto.split())


def _contexto(texto: str, inicio: int, fin: int, marxe: int = 50) -> str:
    return " ".join(texto[max(0, inicio - marxe):fin + marxe].split())


def _buscar_palabra(agulla: str, palleiro: str) -> re.Match | None:
    patron = r"(?<!\w)" + re.escape(_norm(agulla)).replace(r"\ ", r"\s+") + r"(?!\w)"
    return re.search(patron, palleiro, re.IGNORECASE)


def _ler_pdf(ruta: Path) -> dict:
    """Todo o que se pode ler do PDF: texto das páxinas, anotacións,
    widgets, metadatos, ficheiros incrustados e os bytes crus de todos os
    obxectos (fluxos descomprimidos)."""
    with fitz.open(str(ruta)) as doc:
        texto = "\n".join(p.get_text(sort=True) for p in doc)
        anotacions = sum(len(list(p.annots())) for p in doc)
        widgets = sum(len(list(p.widgets())) for p in doc)
        metadatos = {k: v for k, v in (doc.metadata or {}).items()
                     if v and k not in ("format", "encryption", "producer", "creator")}
        xml_meta = doc.get_xml_metadata() or ""
        incrustados = doc.embfile_count()
        crus = []
        for xref in range(1, doc.xref_length()):
            try:
                crus.append(doc.xref_object(xref))
                if doc.xref_is_stream(xref):
                    crus.append((doc.xref_stream(xref) or b"").decode("latin-1", "replace"))
            except Exception:
                continue
    return {"texto": texto, "anotacions": anotacions, "widgets": widgets,
            "metadatos": metadatos, "xml_meta": xml_meta, "incrustados": incrustados,
            "crus": "\n".join(crus)}


_CODIGO_PERSOA_RE = re.compile(r"PERSOA_\d{6}")
_CONTRASINAL_PROBA = "auditoria-local-so-proba"


def _palabras(texto: str) -> set:
    sen_tiles = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    return {p.lower() for p in re.findall(r"[^\W\d_]{2,}", sen_tiles)}


def comprobar_rexistro(directorio: str, texto: str, substitucions: list) -> list:
    """O ficheiro de correspondencias código <-> persoa real garda ben o que
    se tapou? (petición do usuario, 03/10/2026). Reabre o rexistro DESDE O
    DISCO (outra instancia, coma outra sesión do programa) e comproba, para
    cada código usado no documento: que ten entrada, que o nome gardado
    corresponde ao texto tapado (polo menos unha palabra común) e que o DNI
    tapado co mesmo código é o gardado; e que non quedan entradas sen uso."""
    achados = []
    rexistro = RexistroCorrespondencias(directorio)
    if not rexistro.ten_contrasinal_reversion():
        rexistro.definir_contrasinal_reversion(_CONTRASINAL_PROBA)
    listado = rexistro.listar_correspondencias("auditoría automática do rexistro", _CONTRASINAL_PROBA)
    por_codigo = {e["codigo"]: e for e in listado["entradas"]}
    for e in listado["entradas"]:
        for vello in e["fusionados"]:
            por_codigo[vello] = e
    usados = set()
    for inicio, fin, novo in substitucions:
        if not _CODIGO_PERSOA_RE.fullmatch(novo):
            continue
        usados.add(novo)
        orixinal = " ".join(texto[inicio:fin].split())
        entrada = por_codigo.get(novo)
        if entrada is None:
            achados.append({"tipo": "rexistro_codigo_sen_entrada", "texto": orixinal, "codigo": novo,
                            "contexto": "o código está no documento pero non no rexistro"})
            continue
        dni_tapado = normalizar_dni(orixinal) if re.search(r"\d{4}", orixinal) else None
        # Documento (DNI, NIE, pasaporte "FK9081726"): o código é o do titular.
        if dni_tapado and re.fullmatch(r"[A-Za-z*]{0,3}[\d*.\s-]{5,}[A-Za-z*]{0,2}", orixinal):
            # DNI/NIE completo ou parcial: compárase co DNI gardado se o hai.
            # Só os díxitos: o programa garda o DNI coa letra de control
            # RECALCULADA (ocr_dni.py), non a que trae o texto.
            if entrada.get("dni") and "*" not in orixinal \
                    and re.sub(r"\D", "", entrada["dni"]) != re.sub(r"\D", "", dni_tapado):
                achados.append({"tipo": "rexistro_dni_non_corresponde", "texto": orixinal, "codigo": novo,
                                "contexto": f"DNI gardado: {entrada['dni']}"})
            continue
        gardado = set().union(*(_palabras(n) for n in entrada["nomes"])) if entrada["nomes"] else set()
        if _palabras(orixinal) and not (_palabras(orixinal) & gardado):
            achados.append({"tipo": "rexistro_nome_non_corresponde", "texto": orixinal, "codigo": novo,
                            "contexto": f"nomes gardados: {entrada['nomes']}"})
    for e in listado["entradas"]:
        if e["codigo"] not in usados and not set(e["fusionados"]) & usados:
            achados.append({"tipo": "rexistro_codigo_sen_uso", "texto": " / ".join(e["nomes"]),
                            "codigo": e["codigo"], "contexto": "entrada do rexistro que non aparece no documento"})
    return achados


def auditar_documento(ruta_pdf: Path, dir_saida: Path) -> dict:
    achados = []
    with tempfile.TemporaryDirectory() as d:
        rexistro = RexistroCorrespondencias(d)
        t0 = time.time()
        texto, contexto = cargar_documento_estruturado(str(ruta_pdf))
        anon, informe, substitucions = anonimizar_texto_detallado(texto, rexistro, contexto=contexto)
        ruta_saida = dir_saida / "pdf" / ruta_pdf.name
        ruta_saida.parent.mkdir(parents=True, exist_ok=True)
        gardar_documento_estruturado(contexto, anon, str(ruta_saida), substitucions)
        segundos = time.time() - t0
        achados.extend(comprobar_rexistro(d, texto, substitucions))

    (dir_saida / "textos").mkdir(parents=True, exist_ok=True)
    (dir_saida / "textos" / f"{ruta_pdf.stem}.orixinal.txt").write_text(texto, encoding="utf-8")
    (dir_saida / "textos" / f"{ruta_pdf.stem}.anonimizado.txt").write_text(anon, encoding="utf-8")

    saida = _ler_pdf(ruta_saida)
    texto_saida = _norm(saida["texto"])
    anon_norm = _norm(anon)

    marcado_por_codigo = {p["codigo"]: p["marcado_para_revision"] for p in informe.get("persoas", [])}
    palabras_minuscula = set(re.findall(r"(?<![\w])[a-záéíóúñüç]+(?![\w])", texto))

    # 1-3: cada anaco que o pipeline substituíu non debe estar en ningures.
    tapados = {}
    for inicio, fin, novo in substitucions:
        orixinal = " ".join(texto[inicio:fin].split())
        if (len(orixinal) >= 3 and not orixinal.isdigit()) or len(orixinal) >= 6:
            tapados.setdefault(orixinal, novo)
    for orixinal, novo in sorted(tapados.items()):
        m_anon = _buscar_palabra(orixinal, anon_norm)
        m_pdf = _buscar_palabra(orixinal, texto_saida)
        base = {"texto": orixinal, "codigo": novo, "marcado": marcado_por_codigo.get(novo)}
        if m_anon:
            # Se o anaco é unha palabra común (aparece en minúscula noutro
            # sitio do documento: "Lei"/"lei", "Non"/"non") ou leva palabra
            # de institución, o problema é o contrario dunha fuga: tapouse
            # algo que non era persoa nun sitio e noutro non.
            comun = (" " not in orixinal and orixinal.lower() in palabras_minuscula) \
                or bool(_INSTITUCION_RE.search(orixinal))
            achados.append({**base, "tipo": "palabra_comun_tapada" if comun else "entidade_literal_no_texto",
                            "contexto": _contexto(anon_norm, *m_anon.span())})
        elif m_pdf:
            achados.append({**base, "tipo": "entidade_literal_no_pdf",
                            "contexto": _contexto(texto_saida, *m_pdf.span())})
        elif len(orixinal) >= 5 and _buscar_palabra(orixinal, saida["crus"]):
            achados.append({**base, "tipo": "entidade_oculta_no_pdf", "contexto": "(bytes crus do PDF)"})

    # 1b: resto dun nome partido en dúas liñas (táboas do BOE): a liña cos
    # apelidos queda á vista e só a seguinte ("NOME.") se substitúe.
    for m in _NOME_PARTIDO_RE.finditer(anon):
        resto = m.group("resto").strip(" ,")
        if _INSTITUCION_RE.search(resto) or _NON_APELIDO_RE.search(resto):
            continue
        achados.append({"tipo": "nome_partido_en_linas", "texto": resto, "codigo": m.group("codigo"),
                        "marcado": marcado_por_codigo.get(m.group("codigo")),
                        "contexto": _contexto(anon, *m.span())})

    # 1c: número de documento (pasaporte, documento estranxeiro...) que non
    # ten forma de DNI/NIE e segue á vista tras unha etiqueta de documento.
    for m in _ETIQUETA_DOCUMENTO_RE.finditer(anon_norm):
        for t in _IDENTIFICADOR_RE.finditer(anon_norm, m.end(), min(len(anon_norm), m.end() + 90)):
            achados.append({"tipo": "identificador_documental", "texto": t.group(),
                            "contexto": _contexto(anon_norm, *t.span())})

    # 4: restos estruturais no PDF de saída.
    for chave in ("anotacions", "widgets", "incrustados"):
        if saida[chave]:
            achados.append({"tipo": "estrutura_pdf", "texto": f"{chave}={saida[chave]}", "contexto": ""})
    if saida["metadatos"]:
        achados.append({"tipo": "estrutura_pdf", "texto": f"metadatos={sorted(saida['metadatos'])}",
                        "contexto": json.dumps(saida["metadatos"], ensure_ascii=False)[:200]})
    if saida["xml_meta"].strip():
        achados.append({"tipo": "estrutura_pdf", "texto": "xml_metadata", "contexto": saida["xml_meta"][:200]})

    # 5: rede de seguridade sobre o que REALMENTE quedou no PDF.
    riscos = escanear_risco_residual(saida["texto"])
    baixa = 0
    for r in riscos:
        if r.confianza == "alta":
            achados.append({"tipo": "risco_residual_alta", "texto": r.texto, "subtipo": r.tipo,
                            "contexto": r.contexto})
        else:
            baixa += 1

    # 6: DNI parcial enmascarado.
    for m in _DNI_PARCIAL_RE.finditer(texto_saida):
        achados.append({"tipo": "dni_parcial", "texto": m.group(), "contexto": _contexto(texto_saida, *m.span())})

    # 7: posible sobre-anonimización.
    for p in informe.get("persoas", []):
        for mencion in p["mencions"]:
            if _INSTITUCION_RE.search(mencion):
                achados.append({"tipo": "posible_sobre_anonimizacion", "texto": mencion,
                                "codigo": p["codigo"], "marcado": p["marcado_para_revision"],
                                "contexto": ""})

    return {
        "segundos": round(segundos, 1),
        "caracteres": len(texto),
        "persoas": len(informe.get("persoas", [])),
        "marcadas_revision": sum(1 for p in informe.get("persoas", []) if p["marcado_para_revision"]),
        "identificadores_directos": len(informe.get("identificadores_directos", [])),
        "substitucions": len(substitucions),
        "risco_residual_baixa": baixa,
        "categoria_especial": len(informe.get("categoria_especial", [])),
        "achados": achados,
    }


def _informe_markdown(resultados: list[dict], ruta: Path) -> None:
    liñas = ["# Auditoría automática do corpus web (LOCAL: contén datos reais)", ""]
    contas = Counter(a["tipo"] for r in resultados for a in r.get("achados", []))
    docs_con = Counter()
    for r in resultados:
        for t in {a["tipo"] for a in r.get("achados", [])}:
            docs_con[t] += 1
    # "marcado" (marcado_para_revision do informe do pipeline): un achado
    # xa sinalado para revisión humana NON é un fallo silencioso -- é o
    # comportamento deliberado do proxecto (mellor falso positivo de máis
    # ca fuga sen avisar, ver risco_residual.py). Só se conta á parte para
    # os tipos que realmente levan ese campo (`base`/nome_partido_en_linas/
    # posible_sobre_anonimizacion); nos demais ("-") a distinción non
    # aplica, para non facelos parecer "100% sen marcar" por non tela.
    tipos_con_marcado = {a["tipo"] for r in resultados for a in r.get("achados", []) if "marcado" in a}
    sen_marcar = Counter(a["tipo"] for r in resultados for a in r.get("achados", []) if not a.get("marcado"))
    liñas.append(f"Documentos: {len(resultados)}\n")
    liñas.append("| Tipo | Gravidade | Achados | SEN marcar p/ revisión | Documentos |")
    liñas.append("|---|---|---|---|---|")
    for tipo, n in sorted(contas.items(), key=lambda x: (list(GRAVIDADE).index(x[0]) if x[0] in GRAVIDADE else 99)):
        col_marcar = sen_marcar.get(tipo, 0) if tipo in tipos_con_marcado else "-"
        liñas.append(f"| {tipo} | {GRAVIDADE.get(tipo, '-')} | {n} | {col_marcar} | {docs_con[tipo]} |")
    liñas.append("")
    for tipo in GRAVIDADE:
        filas = [(r, a) for r in resultados for a in r.get("achados", []) if a["tipo"] == tipo]
        if not filas:
            continue
        liñas.append(f"## {tipo} ({len(filas)})\n")
        for r, a in filas[:200]:
            extra = f" -> {a['codigo']}" if a.get("codigo") else ""
            marca = " **[marcado para revisión]**" if a.get("marcado") else ""
            liñas.append(f"- `{r['id']}` [{r['seccion']}] `{a['texto']}`{extra}{marca} — {a.get('contexto', '')}")
        liñas.append("")
    ruta.write_text("\n".join(liñas), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=DIR_POR_DEFECTO)
    ap.add_argument("--limite", type=int, default=0, help="Só os N primeiros (probas)")
    ap.add_argument("--refacer", action="store_true", help="Volver auditar os xa feitos")
    ap.add_argument("--gardar-resumo", action="store_true",
                    help="Garda en medicion/resultados/ un resumo SÓ con contas (sen texto)")
    args = ap.parse_args()

    manifesto = json.loads((args.dir / "manifesto.json").read_text(encoding="utf-8"))
    documentos = manifesto["documentos"][: args.limite or None]
    dir_saida = args.dir / "auditoria"
    dir_cache = dir_saida / "por_documento"
    dir_cache.mkdir(parents=True, exist_ok=True)

    resultados = []
    for i, doc in enumerate(documentos, 1):
        cache = dir_cache / f"{doc['id']}.json"
        if cache.exists() and not args.refacer:
            resultados.append(json.loads(cache.read_text(encoding="utf-8")))
            continue
        base = {k: doc[k] for k in ("fonte", "id", "data", "seccion", "titulo", "ficheiro")}
        try:
            r = {**base, **auditar_documento(args.dir / "docs" / doc["ficheiro"], dir_saida)}
        except Exception as e:
            r = {**base, "achados": [{"tipo": "erro", "texto": f"{type(e).__name__}: {e}",
                                       "contexto": traceback.format_exc()[-600:]}]}
        cache.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        resultados.append(r)
        tipos = Counter(a["tipo"] for a in r["achados"])
        print(f"[{i}/{len(documentos)}] {doc['id']} {r.get('segundos', '?')}s "
              f"{dict(tipos) or 'sen achados'}", flush=True)

    _informe_markdown(resultados, dir_saida / "informe.md")
    (dir_saida / "informe.json").write_text(json.dumps(resultados, ensure_ascii=False, indent=1),
                                           encoding="utf-8")

    contas = Counter(a["tipo"] for r in resultados for a in r.get("achados", []))
    print(f"\nDocumentos: {len(resultados)}")
    for tipo, n in contas.most_common():
        docs = sum(1 for r in resultados if any(a["tipo"] == tipo for a in r.get("achados", [])))
        print(f"  {tipo:32s} {n:5d} achados en {docs} documentos ({GRAVIDADE.get(tipo, '-')})")
    print(f"Informe completo (LOCAL): {dir_saida / 'informe.md'}")

    if args.gardar_resumo:
        resumo = {
            "data": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "documentos": len(resultados),
            "por_fonte": dict(Counter(r["fonte"] for r in resultados)),
            "achados_por_tipo": dict(contas),
            "documentos_por_tipo": {
                t: sum(1 for r in resultados if any(a["tipo"] == t for a in r.get("achados", [])))
                for t in contas
            },
            "por_fonte_e_seccion": dict(Counter(f"{r['fonte']} {r['seccion']}" for r in resultados)),
        }
        agora = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        destino = RAIZ / "medicion" / "resultados" / f"corpus-web-{agora}.json"
        destino.write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Resumo sen datos reais: {destino}")


if __name__ == "__main__":
    main()
