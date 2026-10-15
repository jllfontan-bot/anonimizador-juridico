"""Crea un expediente de exemplo con datos TOTALMENTE SINTÉTICOS (persoas,
DNI e teléfonos inventados) para facer as capturas da documentación.
Nunca se usan documentos reais.

Uso (co Python do proxecto, que ten python-docx e PyMuPDF):
    .venv/bin/python docs/fonte/datos_exemplo.py <cartafol-base>
Crea <cartafol-base>/Expediente_0142/ cos documentos de proba."""
import sys
from pathlib import Path

import docx
import fitz

DECLARACION = """Declaración de Marta Lourenzo Vidal

Marta Lourenzo Vidal, con DNI 12345678Z e teléfono 600 123 456, veciña de Lugo, declara que coñecía a Xosé Antón Pereiro Neira desde había dez anos. O seu correo electrónico é marta.lourenzo@exemplo.invalid.

O día 3 de febreiro de 2024, Marta Lourenzo Vidal volveu comparecer perante o xulgado para ratificar a súa declaración anterior sobre os feitos do 3 de febreiro.
"""

NOTIFICACION = """Xulgado de Primeira Instancia. Notificación.

Por medio da presente comunícase a Xosé Antón Pereiro Neira, con DNI 87654321X, que o expediente administrativo 84013276 foi incorporado ás actuacións, solicitando a revisión do seu caso.

O único cirurxián cardiovascular do hospital da Ponte, de 52 anos, foi intervido o 14 de marzo de 2021 tras un accidente de tráfico.
"""

INFORME = """Informe pericial

Xosé Antón Pereiro Neira, con DNI 87654321X, presenta este informe sobre a parcela situada na rúa do Sol, 14, Lugo. Acompáñase o testemuño de Marta Lourenzo Vidal, DNI 12345678Z.
"""

ACTA = """Acta da reunión

Asisten Marta Lourenzo Vidal e Xosé Antón Pereiro Neira. Acórdase remitir a documentación ao xulgado antes do 30 de setembro.
"""


def crear_docx(ruta: Path, texto: str) -> None:
    d = docx.Document()
    for parrafo in texto.strip().split("\n\n"):
        d.add_paragraph(parrafo)
    d.save(ruta)


def crear_pdf(ruta: Path, texto: str) -> None:
    d = fitz.open()
    p = d.new_page()
    p.insert_textbox(fitz.Rect(56, 60, 540, 780), texto, fontsize=11, fontname="helv")
    d.save(ruta)


def main(base: Path) -> Path:
    exp = base / "Expediente_0142"
    (exp / "Anexos").mkdir(parents=True, exist_ok=True)
    # os .txt levan o texto repetido varias veces: así cada ficheiro tarda un pouco
    # e a barra de progreso dos lotes pódese captar a medias
    (exp / "01_declaracion_cliente.txt").write_text(DECLARACION * 250, encoding="utf-8")
    crear_docx(exp / "02_escritura_poder.docx", INFORME)
    crear_pdf(exp / "03_notificacion_xulgado.pdf", NOTIFICACION)
    (exp / "04_informe_pericial.txt").write_text(INFORME * 250, encoding="utf-8")
    crear_docx(exp / "05_acta_reunion.docx", ACTA)
    (exp / "06_correspondencia.txt").write_text(DECLARACION * 250, encoding="utf-8")
    crear_pdf(exp / "07_resolucion.pdf", ACTA + "\n" + INFORME)
    (exp / "08_escrito_alegacions.txt").write_text(ACTA * 250, encoding="utf-8")
    crear_docx(exp / "09_poder_representacion.docx", DECLARACION)
    (exp / "10_notas_reunion.txt").write_text(INFORME * 250, encoding="utf-8")
    (exp / "Anexos" / "anexo_a_testemuno.txt").write_text(DECLARACION, encoding="utf-8")
    crear_docx(exp / "Anexos" / "anexo_b_acta.docx", ACTA)
    # un PDF estragado, para ver como se listan os fallos ao final do lote
    (exp / "11_escaneo_danado.pdf").write_bytes(b"%PDF-1.4\nisto non e un PDF valido\n")
    # ficheiros doutros tipos: amósanse en gris no explorador e omítense ao procesar
    (exp / "plano_parcela.dwg").write_bytes(b"\0" * 64)
    (exp / "foto_lugar.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"\0" * 60)
    return exp


if __name__ == "__main__":
    print(main(Path(sys.argv[1])))
