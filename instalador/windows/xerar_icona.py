#!/usr/bin/env python3
"""Xera `anonimizador.ico` (icona do programa, dos accesos directos e do
instalador de Windows) e `asistente.bmp` (imaxe lateral do asistente): un documento con liñas de texto ocultadas por
barras (o que fai o programa) sobre fondo verde #1f6f5c.

Uso (co venv do repositorio, que ten Pillow):
    .venv/bin/python instalador/windows/xerar_icona.py

O `.ico` xerado VERSIÓNASE xunto a este script (e usase directamente en
`crear-paquetes.sh`), así non fai falta Pillow para construír o instalador.
"""

from pathlib import Path

from PIL import Image, ImageDraw

VERDE = (31, 111, 92, 255)
BRANCO = (255, 255, 255, 255)
CINTO = (226, 232, 230, 255)
LIÑA = (150, 170, 164, 255)
BARRA = (24, 32, 30, 255)

BASE = 1024  # debúxase grande e redúcese (suavizado dos bordos)


def debuxar() -> Image.Image:
    im = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    # fondo: cadrado arredondado verde
    d.rounded_rectangle((32, 32, BASE - 32, BASE - 32), radius=200, fill=VERDE)
    # folla do documento con esquina dobrada
    x0, y0, x1, y1 = 250, 170, 774, 854
    dobra = 150
    d.polygon([(x0, y0), (x1 - dobra, y0), (x1, y0 + dobra), (x1, y1), (x0, y1)], fill=BRANCO)
    d.polygon([(x1 - dobra, y0), (x1 - dobra, y0 + dobra), (x1, y0 + dobra)], fill=CINTO)
    # liñas de texto: as tres primeiras tachadas coa barra escura, a última visible
    ys = [400, 500, 600, 700]
    for i, y in enumerate(ys):
        ancho = 524 - 2 * 60 if i < 3 else 524 - 2 * 60 - 130
        xa, xb = x0 + 60, x0 + 60 + ancho
        if i in (0, 2):
            d.rounded_rectangle((xa - 8, y - 30, xb + 8, y + 30), radius=16, fill=BARRA)
        else:
            d.rounded_rectangle((xa, y - 14, xb, y + 14), radius=14, fill=LIÑA)
    return im


def bitmap_asistente(icona: Image.Image) -> Image.Image:
    """164x314, o tamaño que espera MUI2 para as páxinas de benvida/final:
    degradado verde con a icona arriba."""
    ancho, alto = 164, 314
    bm = Image.new("RGB", (ancho, alto))
    d = ImageDraw.Draw(bm)
    arriba, abaixo = (38, 132, 108), (16, 62, 50)
    for y in range(alto):
        t = y / (alto - 1)
        d.line([(0, y), (ancho, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(arriba, abaixo)))
    ic = icona.resize((112, 112), Image.LANCZOS)
    bm.paste(ic, ((ancho - 112) // 2, 34), ic)
    return bm


if __name__ == "__main__":
    im = debuxar()
    bitmap_asistente(im).save(Path(__file__).with_name("asistente.bmp"), format="BMP")
    saida = Path(__file__).with_name("anonimizador.ico")
    tamanos = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    im.resize((256, 256), Image.LANCZOS).save(saida, format="ICO", sizes=tamanos)
    print("Xerado", saida)
