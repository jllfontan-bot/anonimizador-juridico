#!/usr/bin/env python3
"""Descarga un corpus REAL de documentos públicos (BOE + DOG) para medir o
anonimizador fóra do corpus sintético.

Liña "corpus real da web" do plan interno da v2. Motivo: cada fallo grave
arranxado ata agora apareceu cun documento real (listaxe do BOE, sinatura
dixital en widget, cabeceira sen coma), nunca co corpus sintético.

Fontes e licenzas (comprobadas o 28/09/2026, ver medicion/README.md):
  - BOE: API de datos abertos (sumario diario JSON -> PDF de cada disposición).
    Reutilización comercial e non comercial citando a fonte, sen
    desnaturalizar e respectando o RGPD.
  - DOG: índice diario por seccións (HTML) -> PDF. Reutilización comercial e
    non comercial citando a fonte e sen desnaturalizar.
  - EXCLUÍDOS: Taboleiro Edictal Único (só os interesados e as
    administracións poden conservar/tratar eses datos) e CENDOJ (prohibida a
    descarga masiva).

Os documentos levan datos persoais reais (aínda que publicados): gárdanse SÓ
en local, FÓRA de git (por defecto en `build/corpus_web/`, ignorado por git).

Cortesía: un ficheiro cada `--pausa` segundos (2 por defecto), User-Agent
identificado, e nunca se volve descargar o que xa está no disco.

Uso:
    .venv/bin/python medicion/corpus_web_descargar.py [--dir DIR] [--boe 100] [--dog 50]
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import random
import re
import sys
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

DIR_POR_DEFECTO = Path(__file__).resolve().parent.parent / "build" / "corpus_web"
USER_AGENT = "anonimizador-xuridico-medicion/0.1 (proba de calidade, descarga puntual con pausas)"
SEMENTE = 20260928
TAMANO_MAXIMO = 3_000_000  # bytes: evita boletíns enteiros de centos de páxinas

# Cota por sección, en proporción sobre o total pedido. Variedade a propósito:
# nomeamentos (nomes + cargos), oposicións (listaxes con DNI parcial), outras
# disposicións (subvencións, sentenzas), xustiza (edictos) e anuncios.
COTAS_BOE = {"2A": 0.20, "2B": 0.30, "3": 0.20, "4": 0.20, "5B": 0.10}
COTAS_DOG = {
    "II. Autoridades e persoal": 0.20,
    "III. Outras disposicións": 0.20,
    "IV. Oposicións e concursos": 0.20,
    "V. Administración de xustiza": 0.15,
    "VI. Anuncios": 0.25,
}


def _get(url: str, aceptar: str | None = None) -> bytes:
    cabeceiras = {"User-Agent": USER_AGENT}
    if aceptar:
        cabeceiras["Accept"] = aceptar
    peticion = urllib.request.Request(url, headers=cabeceiras)
    with urllib.request.urlopen(peticion, timeout=60) as resposta:
        return resposta.read()


def _dias_laborables(desde: date, ata: date) -> list[date]:
    dias, d = [], desde
    while d <= ata:
        if d.weekday() < 5:
            dias.append(d)
        d += timedelta(days=1)
    return dias


# -- BOE --------------------------------------------------------------------

def _items_boe(nodo):
    """Percorre o sumario JSON (a API mestura listas e dicionarios segundo
    haxa un ou varios elementos) e devolve cada disposición con PDF."""
    if isinstance(nodo, list):
        for x in nodo:
            yield from _items_boe(x)
    elif isinstance(nodo, dict):
        if "identificador" in nodo and "url_pdf" in nodo:
            yield nodo
        else:
            for v in nodo.values():
                yield from _items_boe(v)


def candidatos_boe(dias: list[date], dir_fontes: Path, pausa: float) -> list[dict]:
    candidatos = []
    for d in dias:
        destino = dir_fontes / f"boe-sumario-{d:%Y%m%d}.json"
        if destino.exists():
            datos = destino.read_bytes()
        else:
            try:
                datos = _get(f"https://www.boe.es/datosabiertos/api/boe/sumario/{d:%Y%m%d}",
                             aceptar="application/json")
            except Exception as e:  # día sen boletín ou erro puntual: seguir
                print(f"  BOE {d}: sen sumario ({e})")
                continue
            destino.write_bytes(datos)
            time.sleep(pausa)
        sumario = json.loads(datos)["data"]["sumario"]
        diarios = sumario["diario"] if isinstance(sumario["diario"], list) else [sumario["diario"]]
        for diario in diarios:
            seccions = diario["seccion"] if isinstance(diario["seccion"], list) else [diario["seccion"]]
            for seccion in seccions:
                if seccion["codigo"] not in COTAS_BOE:
                    continue
                for item in _items_boe(seccion):
                    pdf = item["url_pdf"]
                    url = pdf["texto"] if isinstance(pdf, dict) else pdf
                    tamano = int(pdf.get("szBytes", 0)) if isinstance(pdf, dict) else 0
                    if tamano > TAMANO_MAXIMO:
                        continue
                    candidatos.append({
                        "fonte": "BOE", "id": item["identificador"], "data": f"{d:%Y-%m-%d}",
                        "seccion": seccion["codigo"], "titulo": item["titulo"], "url": url,
                    })
    return candidatos


# -- DOG --------------------------------------------------------------------

# Ficheiro directo de cada sección: a páxina "mostrarContenido.do" devolve
# o índice xeral en vez da sección 1 (descuberto o 28/09/2026).
_DOG_URL_SECCION = "https://www.xunta.gal/dog/Publicados/{ano}/{dia}/Secciones{n}_gl.html"
_DOG_TOKEN = re.compile(
    r'<p class="dog-toc-nivel-1">(?P<seccion>[^<]+)</p>'
    r'|<li class="dog-toc-sumario"><a href="[^"]+"[^>]*>(?P<titulo>[^<]+)</a>'
    r'|<p class="dog-descargar"><a href="(?P<pdf>[^"]+\.pdf)"'
)


def candidatos_dog(dias: list[date], dir_fontes: Path, pausa: float) -> list[dict]:
    candidatos = []
    for d in dias:
        for n in range(1, 10):
            destino = dir_fontes / f"dog-{d:%Y%m%d}-Secciones{n}_gl.html"
            if destino.exists():
                texto = destino.read_text(encoding="utf-8", errors="replace")
            else:
                try:
                    texto = _get(_DOG_URL_SECCION.format(ano=d.year, dia=f"{d:%Y%m%d}", n=n)).decode(
                        "utf-8", errors="replace")
                except Exception as e:
                    print(f"  DOG {d} seccións{n}: {e}")
                    break
                destino.write_text(texto, encoding="utf-8")
                time.sleep(pausa)
            seccion, titulo, atopados = None, None, 0
            for m in _DOG_TOKEN.finditer(texto):
                if m.group("seccion"):
                    seccion = html.unescape(m.group("seccion")).strip()
                elif m.group("titulo"):
                    titulo = " ".join(html.unescape(m.group("titulo")).split())
                elif m.group("pdf") and seccion:
                    atopados += 1
                    if seccion not in COTAS_DOG:
                        continue
                    ruta = m.group("pdf")
                    candidatos.append({
                        "fonte": "DOG", "id": Path(ruta).stem, "data": f"{d:%Y-%m-%d}",
                        "seccion": seccion, "titulo": titulo or "",
                        "url": "https://www.xunta.gal" + ruta,
                    })
            if not atopados:
                break
    return candidatos


# -- selección e descarga ---------------------------------------------------

def escoller(candidatos: list[dict], cotas: dict, total: int, azar: random.Random) -> list[dict]:
    """Reparte `total` segundo as cotas; se unha sección non chega, o que
    sobra pásase ás outras (para chegar ao total sen inflar ningunha)."""
    por_seccion: dict[str, list] = {s: [] for s in cotas}
    for c in candidatos:
        por_seccion[c["seccion"]].append(c)
    for lista in por_seccion.values():
        azar.shuffle(lista)
    escollidos = []
    for s, peso in cotas.items():
        escollidos += por_seccion[s][:round(total * peso)]
    restantes = [c for s in cotas for c in por_seccion[s][round(total * cotas[s]):]]
    azar.shuffle(restantes)
    escollidos += restantes[:max(0, total - len(escollidos))]
    return escollidos[:total]


def descargar(escollidos: list[dict], dir_docs: Path, pausa: float) -> list[dict]:
    feitos = []
    for i, c in enumerate(escollidos, 1):
        destino = dir_docs / c["fonte"].lower() / f"{c['id']}.pdf"
        destino.parent.mkdir(parents=True, exist_ok=True)
        if not destino.exists():
            try:
                datos = _get(c["url"])
            except Exception as e:
                print(f"  [{i}/{len(escollidos)}] ERRO {c['id']}: {e}")
                continue
            if not datos.startswith(b"%PDF"):
                print(f"  [{i}/{len(escollidos)}] NON é PDF: {c['id']}")
                continue
            destino.write_bytes(datos)
            time.sleep(pausa)
        datos = destino.read_bytes()
        feitos.append({**c, "ficheiro": str(destino.relative_to(dir_docs)),
                       "bytes": len(datos), "sha256": hashlib.sha256(datos).hexdigest()})
        if i % 10 == 0:
            print(f"  {i}/{len(escollidos)}")
    return feitos


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=DIR_POR_DEFECTO)
    ap.add_argument("--boe", type=int, default=100)
    ap.add_argument("--dog", type=int, default=50)
    ap.add_argument("--desde", default="2026-09-01")
    ap.add_argument("--ata", default="2026-09-25")
    ap.add_argument("--pausa", type=float, default=2.0)
    args = ap.parse_args()

    raiz_repo = Path(__file__).resolve().parent.parent
    if args.dir.resolve().is_relative_to(raiz_repo):
        sys.exit("O corpus real NON pode ir dentro do repo (datos persoais reais).")

    dir_docs = args.dir / "docs"
    dir_fontes = args.dir / "fontes"
    dir_fontes.mkdir(parents=True, exist_ok=True)
    dias = _dias_laborables(date.fromisoformat(args.desde), date.fromisoformat(args.ata))
    azar = random.Random(SEMENTE)

    escollidos = []
    if args.boe:
        print("BOE: lendo sumarios...")
        cands = candidatos_boe(dias, dir_fontes, args.pausa)
        print(f"  {len(cands)} candidatos")
        escollidos += escoller(cands, COTAS_BOE, args.boe, azar)
    if args.dog:
        print("DOG: lendo índices...")
        cands = candidatos_dog(dias, dir_fontes, args.pausa)
        print(f"  {len(cands)} candidatos")
        escollidos += escoller(cands, COTAS_DOG, args.dog, azar)

    print(f"Descargando {len(escollidos)} PDF (pausa {args.pausa}s)...")
    feitos = descargar(escollidos, dir_docs, args.pausa)

    manifesto = args.dir / "manifesto.json"
    manifesto.write_text(json.dumps({
        "licenzas": {
            "BOE": "Fonte: Agencia Estatal Boletín Oficial del Estado (https://www.boe.es). "
                   "Reutilización segundo o seu aviso legal.",
            "DOG": "Fonte: Diario Oficial de Galicia, Xunta de Galicia (https://www.xunta.gal/diario-oficial-galicia). "
                   "Reutilización segundo o seu aviso legal.",
        },
        "documentos": feitos,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    total_mb = sum(f["bytes"] for f in feitos) / 1e6
    print(f"Feito: {len(feitos)} PDF, {total_mb:.1f} MB -> {dir_docs}")


if __name__ == "__main__":
    main()
