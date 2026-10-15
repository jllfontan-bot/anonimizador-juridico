"""Detección de QR e códigos de barras: un elemento VISUAL, independente
do formato de documento (PDF, .docx, .odt) e de se hai texto extraíble
arredor -- pode codificar datos persoais directamente, ou seren a clave
para consultalos no portal do organismo emisor (mesmo risco xa asumido
para o CSV en texto, ver `recognizers._CSV_ETIQUETA`).

Só se DETECTA a posición/presenza, nunca se esixe poder DECODIFICAR: un
código danado, rotado ou de resolución insuficiente para ler segue a
poder conter datos persoais igual, aínda sen poder comprobalo. Mellor
redactar un código de máis (falso positivo raro) que deixar escapar un
de menos.

Usado por `pdf_estrutura.py` (códigos incrustados coma imaxe nunha
páxina) e por `pipeline.py` (imaxes incrustadas en .docx/.odt).

LÍMITE COÑECIDO (A25, sen resolver): os dous detectores que se usan aquí
son os de OpenCV, e entre ambos só cobren os QR e os códigos de BARRAS
lineais. Un DataMatrix -- o código 2D cadrado, con bordo sólido en L e
temporización alterna nos outros dous lados, habitual en etiquetas de
rexistro e en selos de entrada de moitas administracións -- non o detecta
ningún dos dous (comprobado: os dous devolven `False` cun DataMatrix
sintético). Cubrilo esixe unha libraría nova con compoñente nativo
(`pylibdmtx`/`libdmtx`, ou `pyzbar`/`zbar`, que engadiría tamén Code128 e
PDF417), decisión que NON se tomou aquí porque obriga a instalar unha
dependencia do sistema en Mac e Windows, co que iso implica para o
instalador. Mentres tanto: un DataMatrix cun dato persoal sae INTACTO.
"""

from __future__ import annotations

import cv2
import numpy as np

ETIQUETA = "[CODIGO]"


def _detectores():
    return (cv2.QRCodeDetector(), cv2.barcode_BarcodeDetector())


def ten_codigo(imaxe_gris: np.ndarray) -> bool:
    for detector in _detectores():
        try:
            atopado, _ = detector.detectMulti(imaxe_gris)
        except cv2.error:
            continue
        if atopado:
            return True
    return False


def redactar_imaxe_se_ten_codigo(datos: bytes) -> bytes | None:
    """Se `datos` (bytes dunha imaxe PNG/JPEG/...) contén un QR ou código
    de barras, devolve unha nova imaxe PNG en branco coa etiqueta
    "[CODIGO]" (mesmo tamaño en píxeles có orixinal, para non desaliñar o
    deseño do documento). Se non hai ningún código -- ou os bytes non se
    poden decodificar coma imaxe -- devolve `None`, e o chamador non toca
    nada."""
    arr = np.frombuffer(datos, dtype=np.uint8)
    imaxe = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if imaxe is None or not ten_codigo(imaxe):
        return None

    branco = np.full_like(imaxe, 255)
    fonte = cv2.FONT_HERSHEY_SIMPLEX
    escala = max(min(imaxe.shape) / 200, 0.4)
    (largo_texto, alto_texto), _ = cv2.getTextSize(ETIQUETA, fonte, escala, 1)
    punto = ((imaxe.shape[1] - largo_texto) // 2, (imaxe.shape[0] + alto_texto) // 2)
    cv2.putText(branco, ETIQUETA, punto, fonte, escala, (0,), 1, cv2.LINE_AA)
    return cv2.imencode(".png", branco)[1].tobytes()
