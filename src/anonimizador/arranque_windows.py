"""Arranque do programa instalado dende a Microsoft Store (paquete MSIX).

O manifesto do paquete lanza `runtime\\python\\pythonw.exe -m
anonimizador.arranque_windows` (o código atópao por un `.pth` en
site-packages, ver `instalador/msix/`). Fai o mesmo có lanzador `.vbs` do
instalador clásico, pero en Python:

- Tesseract (OCR): `TESSDATA_PREFIX` e `PATH` só para este proceso.
- Cartafol de traballo en `Documentos\\Anonimizador`: alí viven
  `datos_rexistro`, `preferencias.json` e `anonimizador.log`. NON en
  `%LOCALAPPDATA%`: nun MSIX Windows desvía esas escrituras a un cartafol
  privado do paquete e bórrao ao desinstalar, e sen o rexistro xa non se
  pode saber quen é cada PERSONA_ dos documentos anonimizados.
- Se hai un rexistro da versión anterior (instalador clásico, en
  `%LOCALAPPDATA%\\Anonimizador`) e aínda non hai ningún en Documentos,
  cópiao (o orixinal non se toca) e deixa un aviso para a pantalla de
  inicio (`web._aviso_migracion`).
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

PORTO = 5050
NOME_CARTAFOL = "Anonimizador"
# Ficheiro que deixa a copia do rexistro antigo; a pantalla de inicio amósao
# ata que o usuario o pecha. Leva dentro a ruta da que se copiou.
AVISO_MIGRACION = "aviso-rexistro-copiado.txt"
_COPIAR = ("datos_rexistro", "preferencias.json")


def raiz_instalacion() -> Path:
    """Cartafol do paquete: `runtime\\python\\pythonw.exe` -> raíz."""
    return Path(sys.executable).resolve().parents[2]


def cartafol_documentos() -> Path:
    """Documentos do usuario tal como os ve o Explorador (inclúe a
    redirección a OneDrive ou a outra unidade, que `~/Documents` non ve)."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            import uuid

            folderid_documents = uuid.UUID("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}")
            guid = (ctypes.c_byte * 16).from_buffer_copy(folderid_documents.bytes_le)
            ruta = ctypes.c_wchar_p()
            shell32 = ctypes.windll.shell32
            shell32.SHGetKnownFolderPath.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.HANDLE,
                                                     ctypes.POINTER(ctypes.c_wchar_p)]
            if shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(ruta)) == 0:
                try:
                    return Path(ruta.value)
                finally:
                    ctypes.windll.ole32.CoTaskMemFree(ruta)
        except Exception as e:  # nunca deixar o programa sen arrincar por isto
            print(f"Non se puido ler o cartafol Documentos: {e!r}")
    return Path.home() / "Documents"


def preparar_entorno(raiz: Path) -> None:
    tesseract = raiz / "runtime" / "tesseract"
    os.environ["TESSDATA_PREFIX"] = str(tesseract / "tessdata")
    os.environ["PATH"] = str(tesseract / "bin") + os.pathsep + os.environ.get("PATH", "")


def copiar_rexistro_antigo(datos: Path, antigo: Path) -> bool:
    """Copia o rexistro do instalador clásico se en `datos` aínda non hai
    ningún. Devolve `True` se copiou. A clave segue no Administrador de
    credenciais co mesmo identificador (gardado dentro do rexistro), así que
    a copia ábrese igual cá orixinal."""
    if (datos / "datos_rexistro").exists() or not (antigo / "datos_rexistro").is_dir():
        return False
    for nome in _COPIAR:
        orixe = antigo / nome
        if orixe.is_dir():
            shutil.copytree(orixe, datos / nome)
        elif orixe.is_file():
            shutil.copy2(orixe, datos / nome)
    (datos / AVISO_MIGRACION).write_text(str(antigo / "datos_rexistro"), encoding="utf-8")
    return True


def main() -> None:
    raiz = raiz_instalacion()
    preparar_entorno(raiz)
    datos = cartafol_documentos() / NOME_CARTAFOL
    datos.mkdir(parents=True, exist_ok=True)
    local = os.environ.get("LOCALAPPDATA")
    if local:
        try:
            copiar_rexistro_antigo(datos, Path(local) / NOME_CARTAFOL)
        except OSError as e:
            print(f"Non se puido copiar o rexistro da versión anterior: {e!r}")
    # ANTES de importar `desktop`: ao importarse abre o log no cartafol de traballo
    os.chdir(datos)
    from .desktop import executar

    executar(porto=PORTO, usar_chaveiro=True)


if __name__ == "__main__":
    main()
