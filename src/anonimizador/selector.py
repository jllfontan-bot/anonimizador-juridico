"""Selector nativo de ficheiro/cartafol (informe: "poder seleccionar
carpeta dentro de finder").

Abre o diálogo NATIVO do sistema operativo (Finder en Mac, Explorador en
Windows) para escoller un ficheiro ou un cartafol, sen necesidade de
escribir a ruta a man. Impleméntase lanzando un proceso Python á parte
(`tkinter.filedialog`) en vez de abrir o diálogo dentro do propio proceso
Flask: en macOS, calquera interface gráfica (incluído Tkinter) ten que
vivir no fío PRINCIPAL do proceso -- e o fío principal aquí xa está
ocupado polo servidor web. Un proceso á parte ten sempre o seu propio fío
principal libre, así que evita ese problema en calquera sistema operativo,
sen depender de librarías adicionais (tkinter forma parte da instalación
estándar de Python en Mac e Windows)."""

from __future__ import annotations

import subprocess
import sys

_TEMPO_MAXIMO_S = 300  # 5 minutos de marxe -- é un diálogo que agarda por un humano

_SCRIPT = """
import sys
import tkinter as tk
from tkinter import filedialog

root = tk.Tk()
root.withdraw()
root.attributes("-topmost", True)

if sys.argv[1] == "ficheiro":
    ruta = filedialog.askopenfilename(title="Escolle o documento ou o cartafol a anonimizar")
else:
    ruta = filedialog.askdirectory(title="Escolle o cartafol")

print(ruta)
"""


def escoller(tipo: str) -> str | None:
    """`tipo` é "ficheiro" ou "cartafol". Devolve a ruta escollida, ou
    `None` se o usuario pechou o diálogo sen escoller nada, ou se o
    diálogo non se puido abrir (ex. tkinter non dispoñible)."""
    try:
        resultado = subprocess.run(
            [sys.executable, "-c", _SCRIPT, tipo],
            capture_output=True, text=True, timeout=_TEMPO_MAXIMO_S,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    ruta = resultado.stdout.strip()
    return ruta or None
