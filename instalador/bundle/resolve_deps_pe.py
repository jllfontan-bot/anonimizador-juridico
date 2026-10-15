#!/usr/bin/env python3
"""Resolve, para un .exe/.dll de Windows (formato PE), o peche transitivo de
DLL das que depende, buscando só entre os ficheiros presentes no cartafol
indicado (ignora as DLL do propio sistema operativo, que non están aí).

Uso: resolve_deps_pe.py <cartafol_bin> <ficheiro_inicial>
Imprime, unha por liña, o nome de cada ficheiro do peche (o inicial incluído).

Precisa 'objdump' (paquete binutils, adoita vir instalado en Linux/Mac).
"""
import subprocess
import sys
import os


def deps_of(path):
    out = subprocess.run(["objdump", "-p", path], capture_output=True, text=True).stdout
    return [
        line.split("DLL Name:")[1].strip()
        for line in out.splitlines()
        if "DLL Name:" in line
    ]


def main():
    bindir, start = sys.argv[1], sys.argv[2]
    available = {f.lower(): f for f in os.listdir(bindir)}

    seen = set()
    queue = [start]
    while queue:
        cur = queue.pop()
        if cur.lower() in seen:
            continue
        seen.add(cur.lower())
        cur_path = os.path.join(bindir, available.get(cur.lower(), cur))
        if not os.path.isfile(cur_path):
            continue
        for dep in deps_of(cur_path):
            if dep.lower() in available and dep.lower() not in seen:
                queue.append(dep)

    for f in sorted(seen):
        if f in available:
            print(available[f])


if __name__ == "__main__":
    main()
