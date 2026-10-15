#!/usr/bin/env python3
"""Desempaqueta wheels (.whl, que son zips) directamente en `site-packages`
dun Python portátil de Windows, SEN pip nin venv -- así o instalador NSIS
de Windows pode levar o árbore FINAL xa feito e limitarse a copialo (coa
barra de progreso VERDADEIRA), en vez de executar `pip install` na máquina
de destino.

Uso:
    montar_site_packages.py <site-packages destino> <cartafol-con-wheels> [<cartafol> ...]

Trátase de reproducir o que fai pip ao instalar un wheel "á man":
  - `<paquete>.data/purelib/` e `<paquete>.data/platlib/` van á raíz de
    site-packages (coma o resto do contido do wheel);
  - `.data/scripts`, `.data/headers` e `.data/data` NON se instalan (só
    serven para scripts de liña de comandos / cabeceiras C, que este
    programa non usa: sempre se arranca con `python -m anonimizador.cli`);
  - os ficheiros `.pth` (ex. o de pywin32) quedan na raíz de site-packages,
    onde `site.py` os procesa ao arrincar Python;
  - avisa se dous wheels escriben o mesmo ficheiro con contido distinto.

Só usa a biblioteca estándar: corre co Python 3 de calquera Mac/Linux.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

IGNORAR_DATA = {"scripts", "headers", "data"}


def instalar_wheel(wheel: Path, destino: Path, escritos: dict[str, str]) -> int:
    n = 0
    with zipfile.ZipFile(wheel) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            nome = info.filename
            partes = nome.split("/")
            if partes[0].endswith(".data"):
                if len(partes) < 3 or partes[1] not in ("purelib", "platlib"):
                    if len(partes) >= 2 and partes[1] not in IGNORAR_DATA:
                        print(f"  AVISO: {wheel.name}: ignorado {nome}", file=sys.stderr)
                    continue
                rel = "/".join(partes[2:])
            else:
                rel = nome
            if rel.startswith("/") or ".." in rel.split("/"):
                raise SystemExit(f"ERRO: ruta insegura en {wheel.name}: {nome}")
            saida = destino / rel
            datos = z.read(info)
            if rel in escritos and saida.exists() and saida.read_bytes() != datos:
                print(f"  AVISO: {rel} escrito por {escritos[rel]} e por {wheel.name} (distinto)", file=sys.stderr)
            saida.parent.mkdir(parents=True, exist_ok=True)
            saida.write_bytes(datos)
            escritos[rel] = wheel.name
            n += 1
    return n


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    destino = Path(sys.argv[1])
    destino.mkdir(parents=True, exist_ok=True)
    wheels: list[Path] = []
    for carpeta in sys.argv[2:]:
        wheels += sorted(Path(carpeta).glob("*.whl"))
    escritos: dict[str, str] = {}
    total = 0
    vistos: set[str] = set()
    for w in wheels:
        nome_dist = w.name.split("-")[0].lower().replace("_", "-").replace(".", "-")
        if nome_dist in vistos:
            print(f"  AVISO: distribución duplicada: {w.name}", file=sys.stderr)
        vistos.add(nome_dist)
        total += instalar_wheel(w, destino, escritos)
    print(f"{len(wheels)} wheels, {total} ficheiros -> {destino}")


if __name__ == "__main__":
    main()
