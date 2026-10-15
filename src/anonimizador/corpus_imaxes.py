"""Debuxa as páxinas dun PDF coma PNG para o visor do modo corpus.

Execútase coma PROCESO APARTE (`python -I corpus_imaxes.py PDF CARTAFOL PPP`):
PyMuPDF non admite varios fíos no mesmo proceso, e así o visor non ten que
esperar polo bloqueo do servidor mentres se precarga o seguinte documento
(o DOG de 34 páxinas tardaba minutos). Só importa `fitz`, sen nada do paquete.

Escribe primeiro `paxinas.txt` (número de páxinas) e despois `1.png`, `2.png`...
en orde; cada ficheiro créase con outro nome e renoméase, de xeito que quen le
nunca atopa un ficheiro a medias."""

import os
import sys
from pathlib import Path


def _escribir(ruta: Path, datos: bytes) -> None:
    temporal = ruta.with_name(ruta.name + ".tmp")
    temporal.write_bytes(datos)
    os.replace(temporal, ruta)


def debuxar(pdf: str, cartafol: str, ppp: int) -> None:
    import fitz

    cartafol = Path(cartafol)
    cartafol.mkdir(parents=True, exist_ok=True)
    with fitz.open(pdf) as d:
        _escribir(cartafol / "paxinas.txt", str(len(d)).encode())
        for n, paxina in enumerate(d, start=1):
            destino = cartafol / f"{n}.png"
            if not destino.exists():
                _escribir(destino, paxina.get_pixmap(dpi=ppp).tobytes("png"))


if __name__ == "__main__":
    debuxar(sys.argv[1], sys.argv[2], int(sys.argv[3]))
