"""Carpetas temporales que non fan fallar o traballo ao borrarse.

Caso real (portátil con Windows 11, 15/11/2026): ao converter un cartafol
con .zip, a conversión parouse con `PermissionError: [WinError 32] ... tmp\\2\\Justificante
presentacion demanda.pdf`. O documento xa estaba convertido, pero PyMuPDF
segue co PDF aberto ata que Python libera o obxecto e Windows non deixa
borrar un ficheiro aberto: o borrado da carpeta temporal tirou abaixo o
lote enteiro. Aquí primeiro libérase a memoria, reintentase o borrado un
pouco e, se aínda non se pode, déixase o cartafol (o sistema limparao) en
vez de perder o resultado."""
from __future__ import annotations

import gc
import shutil
import tempfile
import time

_INTENTOS = 6
_ESPERA = 0.25


class DirectorioTemporal(tempfile.TemporaryDirectory):
    def cleanup(self) -> None:
        gc.collect()  # solta os PDF que PyMuPDF aínda ten abertos
        for intento in range(_INTENTOS):
            try:
                shutil.rmtree(self.name)
                break
            except FileNotFoundError:
                break
            except OSError:
                if intento == _INTENTOS - 1:
                    shutil.rmtree(self.name, ignore_errors=True)
                    break
                time.sleep(_ESPERA)
                gc.collect()
        self._finalizer.detach()
