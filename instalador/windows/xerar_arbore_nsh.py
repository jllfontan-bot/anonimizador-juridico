#!/usr/bin/env python3
"""Xera, a partir do árbore de ficheiros xa montado (`build/staging-windows`),
os dous ficheiros `.nsh` que inclúe `instalador.nsi`:

  - <saida>/arbore.nsh     un `File` por cada ficheiro do árbore (con
                           `SetOutPath` ao cambiar de cartafol) e, cada
                           poucos ficheiros, unha chamada a `ActualizarPct`
                           que refresca o texto "NN %" baixo a barra.
  - <saida>/arbore-un.nsh  `RMDir /r` dos cartafoles de paquetes, un a un, para
                           que a barra do desinstalador avance de verdade en
                           vez de saltar de 0 a 100 cun só borrado.
  - <saida>/tamano.nsh     `!define TAMANO_KB` (para "Tamaño" en Aplicacións
                           instaladas).

A barra de progreso de NSIS avanza por INSTRUCCIÓN executada (non por
bytes): despois de cada ficheiro grande engádense `Nop` proporcionais ao seu
tamaño para que a barra siga o volume real de datos e non o número de
ficheiros (senón pararía varios segundos nun `.dll` de 100 MB e correría
polos miles de ficheiros pequenos).

Uso: xerar_arbore_nsh.py <staging> <saida> [--paso-kb 512]
"""

import argparse
import os
import sys
from pathlib import Path


def nsis(cadea: str) -> str:
    if '"' in cadea or "`" in cadea:
        sys.exit(f"ERRO: nome con caracteres non admitidos por NSIS: {cadea!r}")
    return cadea.replace("$", "$$")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("staging")
    ap.add_argument("saida")
    ap.add_argument("--paso-kb", type=int, default=512, help="bytes por cada Nop de reénchido (0 = sen Nop)")
    ap.add_argument("--cada", type=int, default=40, help="ficheiros entre actualizacións do texto de %%")
    a = ap.parse_args()

    raiz = Path(a.staging).resolve()
    saida = Path(a.saida)
    saida.mkdir(parents=True, exist_ok=True)

    ficheiros = []
    for dirpath, _dirs, nomes in os.walk(raiz):
        for n in nomes:
            p = Path(dirpath) / n
            ficheiros.append((p.parent.relative_to(raiz).as_posix(), p.name, p.stat().st_size, p))
    ficheiros.sort(key=lambda t: (t[0], t[1]))

    paso = a.paso_kb * 1024
    total = sum(t[2] for t in ficheiros)
    dir_actual = None
    desde_pct = 0
    with open(saida / "arbore.nsh", "w", encoding="utf-8-sig") as f:
        f.write(f"; Xerado por xerar_arbore_nsh.py -- non editar. {len(ficheiros)} ficheiros, {total} bytes.\n")
        for rel, nome, tam, p in ficheiros:
            if rel != dir_actual:
                destino = "$INSTDIR" if rel == "." else "$INSTDIR\\" + nsis(rel).replace("/", "\\")
                f.write(f'SetOutPath "{destino}"\n')
                dir_actual = rel
            f.write(f'File "{nsis(str(p))}"\n')
            if paso:
                for _ in range(min(tam // paso, 600)):
                    f.write("Nop\n")
            desde_pct += 1
            if desde_pct >= a.cada or tam >= 4 * 1024 * 1024:
                f.write("Call ActualizarPct\n")
                desde_pct = 0
        f.write("Call ActualizarPct\n")

    # Desinstalador: cada paquete de site-packages por separado, despois o resto.
    sp = raiz / "runtime" / "python" / "Lib" / "site-packages"
    with open(saida / "arbore-un.nsh", "w", encoding="utf-8-sig") as f:
        f.write("; Xerado por xerar_arbore_nsh.py -- non editar.\n")
        if sp.is_dir():
            for d in sorted(sp.iterdir()):
                if d.is_dir():
                    rel = d.relative_to(raiz).as_posix().replace("/", "\\")
                    f.write(f'RMDir /r "$INSTDIR\\{nsis(rel)}"\n')
                    f.write("Call un.ActualizarPct\n")
    with open(saida / "tamano.nsh", "w", encoding="utf-8-sig") as f:
        f.write(f"!define TAMANO_KB {total // 1024 + 1}\n")
    print(f"{len(ficheiros)} ficheiros, {total / 1e6:.0f} MB")


if __name__ == "__main__":
    main()
