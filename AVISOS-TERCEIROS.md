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
| Python (python-build-standalone, nos instaladores e no paquete da Store) | PSF-2.0 e licenzas das súas bibliotecas |

## Paquete de Windows (Microsoft Store)

O paquete MSIX leva dentro todo o que o programa precisa para funcionar sen instalar nada
máis. Ademais dos compoñentes da táboa anterior:

### Python portátil (`runtime/python`)

Python 3.12 de **python-build-standalone** (PSF-2.0), coas bibliotecas que trae compiladas:
OpenSSL 3 (Apache-2.0), SQLite (dominio público), libffi (MIT), Tcl/Tk (licenza de Tcl/Tk,
de tipo BSD), bzip2 (licenza bzip2), XZ/liblzma (0BSD), zlib (Zlib), Expat (MIT) e
mpdecimal (BSD-2-Clause).

### Outras bibliotecas de Python (dependencias indirectas)

| Licenza | Paquetes |
|---|---|
| MIT | annotated-doc, annotated-types, blinker, bottle, catalogue, charset-normalizer, clr-loader, cloudpathlib, confection, cymem, jaraco.classes, jaraco.context, jaraco.functools, jeepney, langcodes, markdown-it-py, mdurl, more-itertools, murmurhash, pip, preshed, proxy-tools, pydantic, pydantic-core, pythonnet, rich, setuptools, smart-open, spacy-legacy, spacy-loggers, srsly, typer, typer-slim, typing-inspection, urllib3, wasabi, weasel |
| MIT-0 | cffi |
| BSD-3-Clause | blis, click, colorama, idna, pycparser, pywin32-ctypes, SecretStorage |
| BSD-2-Clause | Pygments, wrapt |
| Apache-2.0 | requests |
| Apache-2.0 ou BSD-2-Clause | packaging |
| ISC | shellingham |
| MPL-2.0 | certifi |
| MPL-2.0 e MIT | tqdm |
| PSF-2.0 | defusedxml, typing-extensions |

### Bibliotecas nativas que van dentro dos paquetes de Python

| Onde | Compoñente | Licenza |
|---|---|---|
| `numpy.libs` | OpenBLAS (co runtime de gfortran) | BSD-3-Clause (runtime de GCC: GPL-3.0 coa excepción de bibliotecas de runtime) |
| `cv2/opencv_videoio_ffmpeg*.dll` | FFmpeg | LGPL-2.1 |
| `pymupdf/mupdfcpp64.dll` | MuPDF e as bibliotecas que integra | AGPL-3.0 |
| `PIL/*.pyd` | libjpeg-turbo, libpng, libtiff, libwebp, libavif, FreeType, HarfBuzz, Little CMS, OpenJPEG, Brotli, XZ e zlib-ng | as indicadas no `LICENSE` de Pillow |

### Tesseract OCR (`runtime/tesseract`)

Tesseract 5.5 e as bibliotecas que precisa, tomadas de **conda-forge**:

| DLL | Compoñente | Licenza |
|---|---|---|
| `tesseract.exe`, `tesseract55.dll` | Tesseract OCR | Apache-2.0 |
| `tessdata/spa`, `glg`, `eng.traineddata` | Datos de Tesseract (tessdata) | Apache-2.0 |
| `leptonica-1.87.0.dll` | Leptonica | BSD-2-Clause |
| `archive.dll` | libarchive | BSD-2-Clause |
| `libcurl.dll` | curl | licenza curl (tipo MIT) |
| `libssh2.dll` | libssh2 | BSD-3-Clause |
| `libcrypto-3-x64.dll` | OpenSSL 3 | Apache-2.0 |
| `icuuc78.dll`, `icudt78.dll` | ICU | Unicode-3.0 |
| `libxml2.dll` | libxml2 | MIT |
| `iconv.dll`, `charset.dll` | GNU libiconv | LGPL-2.1 |
| `psl-5.dll` | libpsl | MIT |
| `zstd.dll` | Zstandard | BSD-3-Clause |
| `lz4.dll` | LZ4 | BSD-2-Clause |
| `liblzma.dll` | XZ Utils | 0BSD |
| `libbz2.dll` | bzip2 | licenza bzip2 |
| `zlib.dll`, `deflate.dll` | zlib, libdeflate | Zlib, MIT |
| `libpng16.dll` | libpng | licenza libpng |
| `tiff.dll` | libtiff | licenza libtiff (HPND) |
| `jpeg8.dll` | libjpeg-turbo | IJG, BSD-3-Clause e Zlib |
| `openjp2.dll` | OpenJPEG | BSD-2-Clause |
| `libwebp.dll`, `libwebpmux.dll`, `libsharpyuv.dll` | libwebp | BSD-3-Clause |
| `gif-7.dll` | giflib | MIT |
| `Lerc.dll` | LERC (Esri) | Apache-2.0 |

O código fonte das bibliotecas LGPL (GNU libiconv e FFmpeg) está nos seus proxectos
(https://www.gnu.org/software/libiconv/, https://ffmpeg.org/) e nas receitas de conda-forge
(`https://github.com/conda-forge/<nome>-feedstock`) e opencv-python coas que se compilaron.

### Runtime de Microsoft Visual C++

`vcruntime140.dll`, `vcruntime140_1.dll`, `msvcp140.dll` e `api-ms-win-crt-*.dll` (no
cartafol de Python e no de Tesseract) son código redistribuíble de **Microsoft** (Visual C++
2015-2022 e Windows SDK). Non son software libre: van no paquete segundo as condicións de
redistribución de Microsoft, e non están cubertos pola AGPL.

O paquete non inclúe **Microsoft Edge WebView2 Runtime**, que forma parte de Windows.

## Datos

- `src/anonimizador/datos/nomes_ine.tsv` e `apelidos_ine.tsv`: elaboración propia con datos
  extraídos do sitio web do **INE** (www.ine.es). Licenza **CC BY 4.0**.
- `src/anonimizador/datos/lugares_oficiais.tsv`: obra derivada da Relación de municipios do
  **INE** (CC BY 4.0) e do **Nomenclátor de Galicia** da Xunta de Galicia (**CC BY-SA 4.0**).
  Esta táboa compártese con **CC BY-SA 4.0**. Detalle en `datos/lugares/LEEME.md`.

Os textos completos das licenzas:

- **Paquetes de Python:** dentro de cada cartafol `*.dist-info`. Os das bibliotecas nativas que
  levan dentro están no mesmo sitio: `LICENSE.txt` de NumPy, `LICENSE-3RD-PARTY.txt` de
  opencv-python-headless, `COPYING` de PyMuPDF e `LICENSE` de Pillow.
- **Python portátil:** `runtime/python/LICENSE.txt` e, para as bibliotecas compiladas dentro,
  `runtime/python/licenzas/` (un `LICENSE.<biblioteca>.txt` por cada unha).
- **Tesseract e as súas bibliotecas:** `runtime/tesseract/licenzas/`, un cartafol por paquete de
  conda-forge. `INDICE.txt` di de que paquete vén cada DLL e cal é a súa licenza. Aí van tamén
  as condicións de Microsoft para o runtime de Visual C++ (`vc14_runtime-*`, `ucrt-*`).
