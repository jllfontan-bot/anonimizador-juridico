#!/usr/bin/env python3
"""Resolve, para un binario Mach-O de macOS, o peche transitivo de
bibliotecas ".dylib" das que depende, buscando só en <prefixo>/lib
(ignora as bibliotecas do propio sistema operativo, "/usr/lib/..." e
"/System/...", que xa están garantidas en calquera Mac).

Uso: resolve_deps_macho.py <prefixo_conda> <ruta_relativa_ao_binario_inicial>
  ex: resolve_deps_macho.py /tmp/env-osx-arm64 bin/tesseract
Imprime, unha por liña, o nome de cada ".dylib" do peche (dentro de lib/).

Precisa o paquete 'macholib' (pip install macholib).
"""
import sys
import os
from macholib.MachO import MachO
from macholib.mach_o import LC_LOAD_DYLIB


def deps_of(path):
    try:
        m = MachO(path)
    except Exception:
        return []
    out = []
    for header in m.headers:
        for lc, cmd, data in header.commands:
            if lc.cmd == LC_LOAD_DYLIB:
                out.append(data[: data.find(b"\x00")].decode())
    return out


def main():
    prefix, start_rel = sys.argv[1], sys.argv[2]
    libdir = os.path.join(prefix, "lib")
    available = {f.lower(): f for f in os.listdir(libdir)} if os.path.isdir(libdir) else {}

    seen_libs = set()
    queue = [os.path.join(prefix, start_rel)]
    while queue:
        cur = queue.pop()
        for dep in deps_of(cur):
            if dep.startswith("@rpath/"):
                fname = dep[len("@rpath/") :]
            elif dep.startswith("/usr/lib/") or dep.startswith("/System/"):
                continue
            else:
                fname = os.path.basename(dep)
            if fname.lower() in seen_libs:
                continue
            if fname.lower() in available:
                seen_libs.add(fname.lower())
                queue.append(os.path.join(libdir, available[fname.lower()]))

    for f in sorted(seen_libs):
        print(available[f])


if __name__ == "__main__":
    main()
