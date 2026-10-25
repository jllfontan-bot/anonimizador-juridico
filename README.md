# Anonimizador de expedientes jurídicos

Programa de escritorio que sustituye los nombres, DNI y demás datos personales de documentos
jurídicos por códigos (`PERSONA_000001`, `[DIRECCIÓN]`, `[TELÉFONO]`…). Las identidades reales
quedan solo en un registro cifrado en tu ordenador, del que se pueden recuperar con una contraseña
y dejando constancia en una auditoría.

**Funciona 100 % en local:** ni el texto ni ningún dato sale nunca a internet.

Interfaz en **castellano** (por defecto) o **gallego**, a elegir en la pantalla de inicio.

## Qué hace

- **Lee** `.txt`, `.docx`, `.odt`, `.pdf` (también escaneados, con OCR) e imágenes, una a una o
  una carpeta entera, y guarda el resultado **con el mismo formato** que el original.
- **Detecta** personas (modelo de lenguaje de spaCy, tablas de nombres y apellidos del INE y
  reglas propias para escritos judiciales y boletines oficiales), DNI/NIE, pasaportes,
  teléfonos, correos, direcciones, matrículas, IBAN, tarjetas, número de la Seguridad Social,
  referencia catastral, número de colegiado, CSV y referencias de trámites.
- **Asigna un código estable a cada persona**, el mismo en todos los documentos del despacho.
  Dos nombres iguales sin DNI que lo confirme **nunca** se fusionan: se tratan como personas
  distintas y el programa avisa del posible homónimo.
- **Avisa** de posibles fugas que no ha podido tapar, de riesgos de efecto mosaico
  (combinaciones de datos que reidentifican) y de datos de categoría especial (art. 9 RGPD).
- **Revisión humana** opcional antes de guardar, y **reversión controlada** de identidades con
  contraseña, motivo obligatorio y auditoría cifrada.

## Instalación

El programa se distribuye para Windows 10 y 11 en la **Microsoft Store**:
[Anonimizador jurídico](https://apps.microsoft.com/detail/9PK1J429MNN5). La guía de instalación
y el manual de uso están en `docs/` (en castellano en `docs/es/`).

El paquete de la Store (MSIX) lo genera GitHub Actions con `.github/workflows/msix.yml`; el
instalador clásico (.exe) se genera con `instalador/crear-paquetes.sh` (ver
[`instalador/README.md`](instalador/README.md)).

Para desarrollar también se puede ejecutar desde el código fuente en Linux o macOS con
**Python 3.12** (spaCy 3.7.5 no se instala con 3.13 ni 3.14):

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download es_core_news_md
```

Para el OCR de PDF escaneados hace falta además el programa **Tesseract** con los idiomas
español y gallego (`spa`, `glg`).

## Uso

Interfaz de escritorio:

```bash
PYTHONPATH=src python -m anonimizador.cli escritorio
```

Interfaz en el navegador (solo en `127.0.0.1`):

```bash
PYTHONPATH=src python -m anonimizador.cli servir --porto 5050
```

Línea de órdenes:

```bash
PYTHONPATH=src python -m anonimizador.cli anonimizar ejemplos/declaracion.txt --rexistro ./datos_rexistro
```

El idioma se elige en la pantalla de inicio y se guarda en `preferencias.json`. La variable de
entorno `ANONIMIZADOR_IDIOMA=es` o `gl` lo fija para pruebas y scripts.

## Tests

```bash
python3 -m unittest discover -s tests
```

La suite completa tarda unos 25 minutos: una de las pruebas procesa un documento de más de un
millón de caracteres.

## Documentación técnica

El diseño, las decisiones y las limitaciones conocidas están en
[`docs/TECNICO.gl.md`](docs/TECNICO.gl.md) (en gallego, como los comentarios del código).

## Licencia

Copyright © 2026 José Luis López Fontán.
Licencia cedida con arreglo a la EUPL v1.2 o, a elección del licenciatario, a la GNU AGPL v3.

Este programa se ha desarrollado con la ayuda de **Claude**, el modelo de inteligencia artificial
de **Anthropic**, a través de Claude Code: el autor ha dirigido, revisado y probado el trabajo.
Claude y Anthropic son marcas de Anthropic, PBC; el programa no está afiliado a Anthropic ni
cuenta con su respaldo.

Este programa es software libre con **doble licencia**: puedes usarlo, redistribuirlo y/o
modificarlo, a tu elección, bajo los términos de la **Licencia Pública de la Unión Europea
(EUPL) v1.2** (ver [`LICENCIA-EUPL-1.2.txt`](LICENCIA-EUPL-1.2.txt), texto oficial en
castellano) o de la **GNU Affero General Public License** publicada por la Free Software
Foundation, versión 3 (ver [`LICENSE`](LICENSE)). Identificador SPDX:
`EUPL-1.2 OR AGPL-3.0-only`. Las versiones publicadas hasta la 1.0.0 se distribuyeron solo con
la AGPL-3.0.

Los paquetes ya montados (Microsoft Store e instaladores) llevan dentro PyMuPDF (AGPL-3.0) y el
modelo `es_core_news_md` (GPL-3.0), así que el paquete completo se distribuye con la AGPL-3.0,
como permite la cláusula de compatibilidad de la EUPL (artículo 5 y anexo). La elección entre
las dos licencias es para el código de este repositorio.

Se distribuye con la esperanza de que sea útil, pero **SIN NINGUNA
GARANTÍA**, ni siquiera la garantía implícita de COMERCIABILIDAD o ADECUACIÓN A UN FIN
DETERMINADO. Los componentes y datos de terceros, con sus licencias, están en
[`AVISOS-TERCEIROS.md`](AVISOS-TERCEIROS.md).
