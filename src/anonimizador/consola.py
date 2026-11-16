"""Saída de consola que non rompe en Windows.

Caso real (portátil con Windows, 16/11/2026): `cli_conversor` escribiu o .md
e despois saíu con `UnicodeEncodeError` ao imprimir o aviso «⚠» das posibles
fugas: coa saída redirixida (a un ficheiro ou a outro programa), Python usa a
codificación local (cp1252), que non ten ese carácter. As liñas de comandos
chaman a `saida_utf8()` ao empezar: stdout e stderr pasan a UTF-8 e o que
non se poida escribir substitúese en vez de parar o programa.
"""
from __future__ import annotations

import sys


def saida_utf8() -> None:
    for fluxo in (sys.stdout, sys.stderr):
        reconfigurar = getattr(fluxo, "reconfigure", None)  # None con pythonw (sen consola)
        if reconfigurar is None:
            continue
        try:
            reconfigurar(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # un fluxo xa usado ou pechado: mellor seguir coma estaba
            pass
