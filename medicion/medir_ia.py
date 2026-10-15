#!/usr/bin/env python3
"""Pasa o mesmo corpus (xa anonimizado pola v1) por qwen2.5-coder:3b en
PAPEL DE AUDITOR (nunca toca o documento, só sinala) e compara contra a
liña base da v1 (`medir_v1.py`). Punto 6.3 do plan: probar UN modelo
pequeno, en modo "avisa", e medir -- se non mellora, dicilo e parar.

Reutiliza o `texto_anonimizado` xa calculado por `medir_v1.py --gardar`
(non volve executar o pipeline) -- o auditor traballa SEMPRE sobre o texto
XA anonimizado, nunca sobre o orixinal.

Métricas (sempre as dúas, nunca soamente unha):
  - Das FUGAS reais que a v1 deixou (`fugas` no informe da v1), cantas
    detecta a IA?
  - Cantos FALSOS POSITIVOS xera a IA (marca coma fuga un anaco que
    `debe_permanecer`)?
  - Métrica informativa: das categorías especiais (que a v1 non marca
    coma tal hoxe), cantas detecta a IA?

Uso:
    .venv/bin/python medicion/medir_ia.py --entrada medicion/resultados/v1-baseline-XXXX.json [--limite N] [--gardar]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

MODELO = "qwen2.5-coder:3b"
HOST = "http://localhost:11434"

PROMPT_SISTEMA = (
    "Es un auditor que revisa un texto YA anonimizado buscando fallos. "
    "IMPORTANTE: los códigos que ya aparecen en el texto como PERSOA_000001, [DNI_NIE], "
    "[TELEFONO], [PASAPORTE], [EMAIL], [ENDEREZO], [IBAN], [COLEXIADO], [CSV], [REFERENCIA], "
    "[SEGURIDADE_SOCIAL] o similares YA están correctamente anonimizados -- NUNCA los "
    "marques como fuga, ni tampoco el texto que los rodea. Solo marcas FUGA cuando quede "
    "un nombre y apellidos de una persona física, un DNI, NIE, pasaporte, teléfono, email "
    "o dirección escrito en texto NORMAL (no como uno de esos códigos). "
    "Señala CATEGORIA_ESPECIAL cuando el texto mencione salud, religión, orientación "
    "sexual o afiliación sindical de una persona identificada, sin marcar."
)

PROMPT_PLANTILLA = """No modifiques el texto. Responde EXCLUSIVAMENTE en JSON, sin nada más.
Usa "tipo": "FUGA" o "tipo": "CATEGORIA_ESPECIAL" (nunca los dos juntos, nunca inventes otro tipo).
Ejemplo de formato (no es el contenido real): {{"hallazgos": [{{"tipo": "FUGA", "texto": "Xoán Pérez"}}]}}
Si no hay nada que señalar: {{"hallazgos": []}}.

TEXTO A REVISAR:
{texto}"""


def preguntar_ia(texto: str, timeout: int = 90) -> list[dict]:
    payload = {
        "model": MODELO,
        "system": PROMPT_SISTEMA,
        "prompt": PROMPT_PLANTILLA.format(texto=texto),
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 400, "seed": 42},
    }
    req = urllib.request.Request(
        f"{HOST}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        res = json.loads(resp.read().decode("utf-8"))
    bruto = res.get("response", "").strip()
    try:
        inicio = bruto.index("{")
        fin = bruto.rindex("}") + 1
        return json.loads(bruto[inicio:fin]).get("hallazgos", [])
    except (ValueError, json.JSONDecodeError):
        return []


def medir(resultados_v1: list[dict]) -> list[dict]:
    saida = []
    total = len(resultados_v1)
    for i, r in enumerate(resultados_v1, 1):
        inicio = time.monotonic()
        hallazgos = preguntar_ia(r["texto_anonimizado"])
        duracion = time.monotonic() - inicio

        textos_marcados = [h.get("texto", "") for h in hallazgos]
        fugas_v1 = r["fugas"]
        fugas_detectadas_pola_ia = [
            f for f in fugas_v1 if any(f in tm or tm in f for tm in textos_marcados if tm)
        ]
        falsos_positivos = [
            tm for tm in textos_marcados
            if any(tm in p or p in tm for p in r.get("_debe_permanecer", []) if tm)
        ]
        saida.append({
            "id": r["id"],
            "categoria": r["categoria"],
            "duracion_seg": round(duracion, 2),
            "hallazgos_ia": hallazgos,
            "fugas_v1": fugas_v1,
            "fugas_v1_detectadas_pola_ia": fugas_detectadas_pola_ia,
            "falsos_positivos": falsos_positivos,
        })
        print(f"[{i}/{total}] {r['id']} ({duracion:.1f}s) -> {len(hallazgos)} hallazgo(s)")
    return saida


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", required=True, help="Informe de medir_v1.py --gardar")
    ap.add_argument("--limite", type=int, default=None, help="Só os N primeiros casos (proba rápida)")
    ap.add_argument("--gardar", action="store_true")
    args = ap.parse_args()

    with open(args.entrada, encoding="utf-8") as f:
        datos_v1 = json.load(f)

    # Cruza co corpus orixinal para ter `debe_permanecer` (non vai no informe da v1).
    corpus_por_id = {}
    for nome_ficheiro in ("corpus_sintetico.json", "corpus_generado.json"):
        ruta = Path(__file__).parent / nome_ficheiro
        if ruta.exists():
            with open(ruta, encoding="utf-8") as f:
                for c in json.load(f):
                    corpus_por_id[c["id"]] = c

    resultados_v1 = datos_v1["resultados"]
    for r in resultados_v1:
        r["_debe_permanecer"] = corpus_por_id.get(r["id"], {}).get("debe_permanecer", [])

    if args.limite:
        resultados_v1 = resultados_v1[: args.limite]

    saida = medir(resultados_v1)

    total_fugas_v1 = sum(len(r["fugas_v1"]) for r in saida)
    total_detectadas = sum(len(r["fugas_v1_detectadas_pola_ia"]) for r in saida)
    total_falsos = sum(len(r["falsos_positivos"]) for r in saida)
    total_duracion = sum(r["duracion_seg"] for r in saida)

    casos_categoria_especial = [r for r in saida if r["categoria"] == "categoria_especial"]
    detectou_cat_especial = sum(
        1 for r in casos_categoria_especial
        if any(h.get("tipo") == "CATEGORIA_ESPECIAL" for h in r["hallazgos_ia"])
    )

    print()
    print(f"Casos procesados: {len(saida)}")
    print(f"Tempo total: {total_duracion:.0f}s ({total_duracion/max(1,len(saida)):.1f}s/caso)")
    print(f"Fugas reais da v1 no lote: {total_fugas_v1}")
    print(f"  ...detectadas pola IA: {total_detectadas}")
    print(f"Falsos positivos da IA (marcou algo que debía permanecer): {total_falsos}")
    if casos_categoria_especial:
        print(f"Categoría especial: {detectou_cat_especial}/{len(casos_categoria_especial)} detectados")

    if args.gardar:
        destino = Path(__file__).parent / "resultados" / f"ia-qwen-{int(time.time())}.json"
        with open(destino, "w", encoding="utf-8") as f:
            json.dump({"resultados": saida}, f, ensure_ascii=False, indent=2)
        print(f"\nInforme gardado en {destino}")


if __name__ == "__main__":
    main()
