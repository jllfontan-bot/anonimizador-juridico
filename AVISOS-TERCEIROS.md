# Avisos de terceiros

O Anonimizador de expedientes xurídicos distribúese baixo a licenza
**GNU Affero General Public License v3.0** (ver `LICENSE`). Inclúe ou usa os
compoñentes seguintes, cada un baixo a súa propia licenza:

| Compoñente | Licenza |
|---|---|
| PyMuPDF / MuPDF (Artifex) | AGPL-3.0 |
| Modelo spaCy `es_core_news_md` (Explosion) | GPL-3.0 |
| spaCy, thinc e dependencias (Explosion) | MIT |
| Tesseract OCR e datos `tessdata` | Apache-2.0 |
| pytesseract | Apache-2.0 |
| OpenCV (`opencv-python-headless`) | Apache-2.0 |
| NumPy | BSD-3-Clause |
| Pillow | MIT-CMU (HPND) |
| Flask, Werkzeug, Jinja2, Click, MarkupSafe, itsdangerous | BSD-3-Clause |
| pywebview | BSD-3-Clause |
| cryptography | Apache-2.0 ou BSD-3-Clause |
| keyring | MIT |
| python-docx | MIT |
| odfpy | Apache-2.0 (licenza triple; escóllese Apache-2.0) |
| PyYAML | MIT |
| lxml | BSD-3-Clause |
| pywin32 (só Windows) | PSF |
| Python (python-build-standalone, só nos instaladores) | PSF-2.0 e licenzas das súas bibliotecas |

## Datos

- `src/anonimizador/datos/nomes_ine.tsv` e `apelidos_ine.tsv`: elaboración propia con datos
  extraídos do sitio web do **INE** (www.ine.es). Licenza **CC BY 4.0**.
- `src/anonimizador/datos/lugares_oficiais.tsv`: obra derivada da Relación de municipios do
  **INE** (CC BY 4.0) e do **Nomenclátor de Galicia** da Xunta de Galicia (**CC BY-SA 4.0**).
  Esta táboa compártese con **CC BY-SA 4.0**. Detalle en `datos/lugares/LEEME.md`.

Os textos completos das licenzas de cada paquete van dentro do propio paquete
(cartafoles `*.dist-info` de Python e `share/` de Tesseract).
