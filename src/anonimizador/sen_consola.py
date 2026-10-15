"""Evita o PARPADEO de consolas en Windows mentres se anonimiza.

Cada chamada ao OCR lanza `tesseract.exe` coma proceso fillo. `pytesseract`
xa pide ocultar a xanela (`STARTUPINFO` + `SW_HIDE`), pero iso NON abonda en
Windows 11 cando a "consola predeterminada" é Windows Terminal: o sistema
crea igual unha xanela de consola para o fillo e vese un destello. Como o
programa OCRea unha vez por páxina e outra por cada zona con imaxe (logotipos
incluídos), os destellos repítense durante todo o proceso -- molesto,
sobre todo se se está a traballar noutra cousa na mesma pantalla.

Comprobado na VM de Windows 11 (27/09/2026), mostrexando cada 50 ms as
xanelas visibles de clase de consola: sen traballo son 2 constantes;
mentres anonimiza chegan a 4, sempre con `tesseract` en execución.

A solución é `CREATE_NO_WINDOW`, que si impide crear a consola. `pytesseract`
non deixa pasar `creationflags`, así que se substitúe o módulo `subprocess`
que ve `pytesseract` por un envoltorio que engade esa bandeira.

NON abonda con parchear `subprocess_args()` (a función que constrúe os
argumentos do OCR): `get_tesseract_version()` lanza ademais
`tesseract --version` cun `subprocess.check_output` que NON pasa por aí --
comprobado espiando `subprocess.Popen` na VM: a chamada do OCR saía con
`creationflags=0x8000000` e a da versión con `0x0`. Por iso se envolve o
módulo enteiro (só dentro de `pytesseract`, non globalmente).

En Mac e Linux non hai nada que facer: este módulo non toca nada.
"""

from __future__ import annotations

import os
import subprocess

_MARCA = "_anonimizador_sen_consola"
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


class _SubprocessSenXanela:
    """Fai de `subprocess` para `pytesseract`: igual en todo, pero engadindo
    `CREATE_NO_WINDOW` a `Popen` e a `check_output`, que son as dúas vías
    polas que esa libraría lanza `tesseract.exe`."""

    _anonimizador_sen_consola = True

    def __init__(self, real):
        self._real = real

    def __getattr__(self, nome):
        return getattr(self._real, nome)

    def _con_bandeira(self, kwargs):
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | _CREATE_NO_WINDOW
        return kwargs

    def Popen(self, *args, **kwargs):  # noqa: N802 -- nome da API de subprocess
        return self._real.Popen(*args, **self._con_bandeira(kwargs))

    def check_output(self, *args, **kwargs):
        return self._real.check_output(*args, **self._con_bandeira(kwargs))

    def run(self, *args, **kwargs):
        return self._real.run(*args, **self._con_bandeira(kwargs))


def aplicar() -> bool:
    """Parchea `pytesseract` para que non cree consolas. Devolve `True` se
    quedou aplicado (ou xa o estaba). É idempotente: pódese chamar dende
    varios módulos sen apilar parches."""
    if os.name != "nt":
        return False
    try:
        from pytesseract import pytesseract as _pt
    except Exception:  # pragma: no cover -- sen pytesseract non hai OCR
        return False

    modulo = getattr(_pt, "subprocess", None)
    if modulo is None:  # pragma: no cover -- versión inesperada
        return False
    if getattr(modulo, _MARCA, False):
        return True

    _pt.subprocess = _SubprocessSenXanela(modulo)
    return True
