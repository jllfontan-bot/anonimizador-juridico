#!/usr/bin/env python3
"""Resolve, para un binario ELF de Linux, o peche transitivo de bibliotecas
".so" das que depende, buscando só en <prefixo>/lib (ignora as bibliotecas
que forman parte de calquera sistema Linux normal: libc, libm, libpthread...).

Uso: resolve_deps_elf.py <prefixo_conda> <ruta_relativa_ao_binario_inicial>
  ex: resolve_deps_elf.py /tmp/env-linux64 bin/tesseract
Imprime, unha por liña, o nome de cada ".so" do peche (dentro de lib/).

Precisa 'readelf' (paquete binutils, adoita vir instalado en Linux).
"""
import sys
import os
import re
import subprocess

SYSTEM_ALWAYS = {
    "libc.so.6",
    "libm.so.6",
    "libpthread.so.0",
    "libdl.so.2",
    "librt.so.1",
    "libgcc_s.so.1",
    "ld-linux-x86-64.so.2",
    "libresolv.so.2",
    "libutil.so.1",
}


def needed_of(path):
    out = subprocess.run(["readelf", "-d", path], capture_output=True, text=True).stdout
    names = []
    for line in out.splitlines():
        if "NEEDED" in line:
            m = re.search(r"\[(.*?)\]", line)
            if m:
                names.append(m.group(1))
    return names


def main():
    prefix, start_rel = sys.argv[1], sys.argv[2]
    libdir = os.path.join(prefix, "lib")
    available = {f.lower(): f for f in os.listdir(libdir)} if os.path.isdir(libdir) else {}

    seen = set()
    queue = [os.path.join(prefix, start_rel)]
    while queue:
        cur = queue.pop()
        for dep in needed_of(cur):
            if dep in SYSTEM_ALWAYS or dep.lower() in seen:
                continue
            if dep.lower() in available:
                seen.add(dep.lower())
                queue.append(os.path.join(libdir, available[dep.lower()]))

    for f in sorted(seen):
        print(available[f])


if __name__ == "__main__":
    main()
