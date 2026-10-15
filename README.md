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

El programa se distribuye para Windows. El instalador se genera con
`instalador/crear-paquetes.sh` (ver [`instalador/README.md`](instalador/README.md)). La guía
para usuarios está en `docs/`.

Para desarrollar también se puede ejecutar desde el código fuente en Linux o macOS
(Python 3.9 o posterior):

```bash
python3 -m venv .venv
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

La suite completa tarda unos 35 minutos: una de las pruebas procesa un documento de más de un
millón de caracteres.

## Documentación técnica

El diseño, las decisiones y las limitaciones conocidas están en
[`docs/TECNICO.gl.md`](docs/TECNICO.gl.md) (en gallego, como los comentarios del código).

## Licencia

Copyright © 2026 José Luis López Fontán.

Este programa es software libre: puedes redistribuirlo y/o modificarlo bajo los términos de la
**GNU Affero General Public License** publicada por la Free Software Foundation, versión 3 (ver
[`LICENSE`](LICENSE)). Se distribuye con la esperanza de que sea útil, pero **SIN NINGUNA
GARANTÍA**, ni siquiera la garantía implícita de COMERCIABILIDAD o ADECUACIÓN A UN FIN
DETERMINADO. Los componentes y datos de terceros, con sus licencias, están en
[`AVISOS-TERCEIROS.md`](AVISOS-TERCEIROS.md).
