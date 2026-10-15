#!/usr/bin/env python3
"""Mide o programa ACTUAL contra as etiquetas da revisión do corpus público
(plan interno de revisión do corpus, punto 5). Sen intervención humana: volve anonimizar
cada documento etiquetado e casa por posición o que tapa co que quen revisou
decidiu.

Por mención (cada aparición no texto):
  - persoa tapada (acerto): unha persoa da referencia cuberta por calquera
    substitución (código de persoa, [ENDEREZO]...);
  - fuga: persoa da referencia sen ningunha substitución enriba;
  - sobreanonimización: un código de persoa sobre algo que NON é persoa na
    referencia (quen revisou desmarcouno, ou non o marcou coma "faltaba").
Por documento: sen fuga / perfecto (sen fuga nin sobreanonimización).
Intervalos de confianza ao 95% (Wilson).

Saída: resumo por pantalla; con --detalle, ficheiro LOCAL no lote con cada fallo
e o seu contexto (leva nomes reais: nunca a git); con --gardar-resumo, contas sen
texto en medicion/resultados/.

Uso:
    .venv/bin/python medicion/corpus_metricas.py --dir LOTE [--detalle] [--gardar-resumo]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from anonimizador.pipeline import anonimizar_texto_detallado, cargar_documento_estruturado  # noqa: E402
from anonimizador.registry import RexistroCorrespondencias  # noqa: E402


def wilson(exitos: int, total: int) -> tuple:
    if total == 0:
        return (float("nan"), float("nan"))
    z = 1.96
    p = exitos / total
    centro = (p + z * z / (2 * total)) / (1 + z * z / total)
    marxe = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return (max(0.0, centro - marxe), min(1.0, centro + marxe))


def _solapa(a: int, b: int, spans: list) -> bool:
    return any(a < f and i < b for i, f in spans)


def avaliar_documento(etiqueta: dict, ruta_doc: Path) -> dict:
    """Compara a versión actual do programa coa etiqueta dun documento."""
    texto, contexto = cargar_documento_estruturado(str(ruta_doc))
    if hashlib.sha256(texto.encode("utf-8")).hexdigest() != etiqueta.get("sha256_texto"):
        return {"id": etiqueta["id"], "erro": "o texto extraído cambiou desde a etiqueta (posicións non comparables)"}
    with tempfile.TemporaryDirectory() as d:
        _, _, substitucions = anonimizar_texto_detallado(texto, RexistroCorrespondencias(d), contexto=contexto)

    persoas_ref = [(m["inicio"], m["fin"]) for p in etiqueta["persoas"] if p["decision"] == "persoa"
                   for m in p["mencions"]]
    persoas_ref += [(m["inicio"], m["fin"]) for e in etiqueta["engadidos"] if e.get("substituto") is None
                    for m in e["mencions"]]
    tapado = [(i, f) for i, f, _ in substitucions]
    codigos_persoa = [(i, f) for i, f, novo in substitucions if novo.startswith("PERSOA_")]

    fugas = [(i, f) for i, f in persoas_ref if not _solapa(i, f, tapado)]
    sobre = [(i, f) for i, f in codigos_persoa if not _solapa(i, f, persoas_ref)]
    contexto_de = lambda i, f: texto[max(0, i - 60):f + 40].replace("\n", " ")  # noqa: E731
    return {
        "id": etiqueta["id"], "fonte": etiqueta["fonte"],
        "persoas_ref": len(persoas_ref), "fugas": len(fugas),
        "tapados_persoa": len(codigos_persoa), "sobre": len(sobre),
        "exentos": len(etiqueta.get("exentos", [])),
        "exentos_incorrectos": sum(e["decision"] == "incorrecta" for e in etiqueta.get("exentos", [])),
        "detalle": [{"tipo": "fuga", "texto": texto[i:f], "contexto": contexto_de(i, f)} for i, f in fugas]
                   + [{"tipo": "sobreanonimizacion", "texto": texto[i:f], "contexto": contexto_de(i, f)} for i, f in sobre],
    }


def resumir(resultados: list) -> dict:
    validos = [r for r in resultados if "erro" not in r]
    persoas = sum(r["persoas_ref"] for r in validos)
    fugas = sum(r["fugas"] for r in validos)
    tapados = sum(r["tapados_persoa"] for r in validos)
    sobre = sum(r["sobre"] for r in validos)
    sen_fuga = sum(r["fugas"] == 0 for r in validos)
    perfectos = sum(r["fugas"] == 0 and r["sobre"] == 0 for r in validos)
    n = len(validos)
    return {
        "documentos": n,
        "documentos_con_erro": len(resultados) - n,
        "persoas_referencia": persoas,
        "exhaustividade": {"valor": (persoas - fugas) / persoas if persoas else None,
                           "ic95": wilson(persoas - fugas, persoas)},
        "precision": {"valor": (tapados - sobre) / tapados if tapados else None,
                      "ic95": wilson(tapados - sobre, tapados)},
        "documentos_sen_fuga": {"n": sen_fuga, "valor": sen_fuga / n if n else None, "ic95": wilson(sen_fuga, n)},
        "documentos_perfectos": {"n": perfectos, "valor": perfectos / n if n else None, "ic95": wilson(perfectos, n)},
        "fugas": fugas, "sobreanonimizacions": sobre,
        "exentos": sum(r["exentos"] for r in validos),
        "exentos_incorrectos": sum(r["exentos_incorrectos"] for r in validos),
    }


def _pct(x) -> str:
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{100 * x:.1f}%"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, required=True)
    ap.add_argument("--detalle", action="store_true", help="Garda os fallos con contexto no lote (LOCAL)")
    ap.add_argument("--gardar-resumo", action="store_true", help="Garda só contas en medicion/resultados/")
    args = ap.parse_args()

    manifesto = {d["id"]: d for d in json.loads((args.dir / "manifesto.json").read_text(encoding="utf-8"))["documentos"]}
    etiquetas = sorted((args.dir / "revision" / "etiquetas").glob("*.json"))
    resultados = []
    for ruta in etiquetas:
        etiqueta = json.loads(ruta.read_text(encoding="utf-8"))
        if not etiqueta.get("revisado"):
            continue
        resultados.append(avaliar_documento(etiqueta, args.dir / "docs" / manifesto[etiqueta["id"]]["ficheiro"]))
    resumo = resumir(resultados)

    print(f"Documentos etiquetados: {resumo['documentos']} (con erro: {resumo['documentos_con_erro']})")
    for clave, nome in (("exhaustividade", "Persoas tapadas (exhaustividade)"),
                        ("precision", "Tapado que era persoa (precisión)"),
                        ("documentos_sen_fuga", "Documentos sen fuga"),
                        ("documentos_perfectos", "Documentos perfectos")):
        v = resumo[clave]
        print(f"  {nome:38s} {_pct(v['valor']):>7s}  IC95 {_pct(v['ic95'][0])}–{_pct(v['ic95'][1])}")
    print(f"  Fugas: {resumo['fugas']} · sobreanonimizacións: {resumo['sobreanonimizacions']} · "
          f"exencións incorrectas: {resumo['exentos_incorrectos']} de {resumo['exentos']}")
    for r in resultados:
        if "erro" in r:
            print(f"  AVISO {r['id']}: {r['erro']}")

    agora = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    if args.detalle:
        ruta = args.dir / "revision" / f"metricas-{agora}.md"
        liñas = [f"# Fallos fronte á referencia ({agora}) — LOCAL, leva nomes reais", ""]
        for r in resultados:
            for d in r.get("detalle", []):
                liñas.append(f"- `{r['id']}` **{d['tipo']}** `{d['texto']}` — …{d['contexto']}…")
        ruta.write_text("\n".join(liñas) + "\n", encoding="utf-8")
        print(f"Detalle (LOCAL): {ruta}")
    if args.gardar_resumo:
        destino = RAIZ / "medicion" / "resultados" / f"corpus-referencia-{agora}.json"
        destino.write_text(json.dumps({"lote": args.dir.name, **resumo}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Resumo sen datos reais: {destino}")


if __name__ == "__main__":
    main()
