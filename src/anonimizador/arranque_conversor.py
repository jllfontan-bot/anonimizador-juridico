"""Arranque do Conversor de archivos para IA instalado dende a Microsoft
Store (o seu propio paquete MSIX).

O manifesto do paquete lanza `runtime\\python\\pythonw.exe -m
anonimizador.arranque_conversor` (ver `instalador/msix/`). Coma o
anonimizador (`arranque_windows`):

- Tesseract (OCR): `TESSDATA_PREFIX` e `PATH` só para este proceso.
- Cartafol de traballo en `Documentos\\Anonimizador`, o MESMO có
  anonimizador: o mesmo rexistro (unha persoa recibe o mesmo código nos dous
  programas) e o mesmo `preferencias.json`. NON en `%LOCALAPPDATA%`: nun
  MSIX Windows desvía esas escrituras a un cartafol privado do paquete e
  bórrao ao desinstalar.
"""

from __future__ import annotations

import os

from .arranque_windows import NOME_CARTAFOL, cartafol_documentos, preparar_entorno, raiz_instalacion


def main() -> None:
    preparar_entorno(raiz_instalacion())
    datos = cartafol_documentos() / NOME_CARTAFOL
    datos.mkdir(parents=True, exist_ok=True)
    os.chdir(datos)
    from .pantalla_conversor import executar

    executar()


if __name__ == "__main__":
    main()
