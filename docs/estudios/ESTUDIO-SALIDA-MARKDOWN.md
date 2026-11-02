# Estudio: salida en Markdown (.md) — ¿en el mismo programa o en uno aparte?

**Fecha:** 25/10/2026. **Estado:** estudio, sin código escrito.

## 1. Qué se quiere

Que el programa, en local, deje los documentos en `.md` para que Claude los lea
directamente, sin tener que convertirlos él (cada conversión cuesta llamadas a
herramientas y tokens). Dos variantes pedidas:

- **anonimizar y además** guardar una copia `.md` del resultado;
- **solo convertir** a `.md`, sin anonimizar.

## 2. ¿Cuánto se ahorra de verdad?

| Lo que recibe Claude | Cómo lo lee | Coste aproximado |
|---|---|---|
| PDF anonimizado | Cada página va como texto **y además como imagen** | El de la tabla de abajo, por página |
| `.docx` / `.odt` | No lo lee directamente: tiene que escribir y ejecutar un script de conversión | Tokens del script + de la salida, y a veces varios intentos |
| `.txt` o `.md` | Lo lee tal cual | Solo el texto |

Medido en este repositorio: una página densa de PDF (`docs/criterios_anonimizacion_cendoj.pdf`)
tiene unos **4.200 caracteres ≈ 1.100–1.300 tokens de texto**. Leída como PDF se
suma la imagen de la página (del orden de **1.500–2.000 tokens más por página**).
**Estimación: un `.md` cuesta entre la mitad y un tercio que el PDF.** En
escaneados la ganancia es mayor, porque el OCR ya lo hace el programa.

Entre `.txt` y `.md` la diferencia de tokens es mínima. Lo que aporta `.md` es la
**estructura** (títulos, listas, tablas, marcas de página), que ayuda a Claude a
entender y a citar («página 3», «cláusula segunda») sin releer.

## 3. Qué tiene ya el programa

La parte difícil de un conversor a `.md` **ya está hecha y probada** dentro del anonimizador:

- **Lectura de todos los formatos** (`cargar_documento_estruturado`, `pipeline.py:390`):
  `.docx` con cabeceras, pies, tablas y control de cambios aceptado; `.odt` con
  títulos y pies; PDF con texto nativo y OCR (Tesseract `spa+glg`) en las páginas
  escaneadas; imágenes con OCR.
- **Páginas del PDF ya separadas** (`SEPARADOR_PAXINAS = "\n\f\n"`, `pdf_estrutura.py:72`).
- **Tablas de PDF con líneas ya localizadas celda a celda** (`taboas_pdf.py`).
- **Párrafos de `.docx`/`.odt` uno a uno**, cada línea del texto anonimizado
  corresponde a un párrafo del original, así que se le puede poner su estilo
  (título, lista…) sin volver a anonimizar nada.
- **Nombre de archivo anonimizado**, carpeta de salida, procesado de carpetas y `.zip`,
  revisión humana y barra de progreso.

## 4. Opción A — dentro del mismo programa

**Qué cambia:**

1. Un módulo nuevo (`markdown.py`) que convierte a Markdown el texto anonimizado
   (o, en modo «solo convertir», el original) usando la estructura que ya se lee.
2. Guardar la copia `.md` en los puntos donde hoy se guarda el resultado:
   - modo automático (`web._procesar_automatico`);
   - revisión confirmada (`web.confirmar`), **sobrescribiendo** la copia del
     automático para que el `.md` sea siempre el texto revisado;
   - línea de comandos (`cli.py`, opción `--markdown`);
   - `.zip` (la copia va dentro del zip de salida).
3. Una casilla en la pantalla de inicio: «Guardar también una copia en Markdown (.md)».
4. Aceptar `.md` como entrada (hoy no está en `EXTENSIONS_SOPORTADAS`, `pipeline.py:1080`).
5. Al reprocesar una carpeta, no volver a coger las copias `.md` como entrada
   (como ya se hace con `*.anonimizado.*`, `pipeline.py:1101`).

**Ventajas:**

- **Seguridad:** el `.md` sale del **mismo texto ya anonimizado** (y revisado, si
  hubo revisión), con el **mismo código de persona** y el **mismo nombre de archivo
  anonimizado**. No hay un segundo camino que pueda dejar un nombre a la vista.
- No se duplica nada: OCR, cabeceras y pies, control de cambios, tablas…
- **Un solo instalador** (155 MB, ya probado en la VM de Windows) y una sola
  suite de tests (759).

**Inconvenientes:** se toca código que funciona y hay que sacar un instalador
nuevo y probarlo en la VM como siempre. El riesgo es bajo, porque el `.md` se
escribe **aparte**: el documento anonimizado de siempre no cambia.

## 5. Opción B — un programa exclusivo para .md

**Haría falta:**

- La misma lectura de formatos (PyMuPDF, Tesseract, python-docx, odfpy) copiada
  o como dependencia del anonimizador, o sea, otra copia del código que mantener.
- Otro instalador por sistema (Windows/Mac/Linux), con sus pruebas en la VM.
  Sería más pequeño (sin spaCy, unos 60–80 MB estimados), pero **es otro producto
  que distribuir y mantener**.
- Si tiene que trabajar con documentos anonimizados, convertiría el **PDF ya
  tapado**, perdiendo la estructura que el anonimizador sí conoce, o tendría
  que llamar al anonimizador, y entonces ya no es independiente.

**Solo tendría sentido** para convertir documentos **no confidenciales** sin
instalar el anonimizador. Para eso ya existen herramientas libres (pandoc,
MarkItDown de Microsoft) y no hace falta escribir una propia.

## 6. «Solo convertir a .md, sin anonimizar»: el riesgo

Técnicamente es trivial dentro del mismo programa (leer → Markdown, sin el paso de
anonimizar). Pero un `.md` **sin anonimizar** que se le pase a Claude **saca del
equipo los datos personales**, que es justo lo que el programa evita. Si se incluye:

- que **no** sea la opción por defecto;
- un aviso claro en pantalla («Este archivo conserva los datos personales: no lo
  envíes a servicios externos»);
- un nombre de archivo que lo deje claro (`demanda.SIN-ANONIMIZAR.md`).

## 7. Calidad esperable del Markdown por formato

| Entrada | Títulos | Listas | Tablas | Páginas | Notas |
|---|---|---|---|---|---|
| `.docx` | Sí (estilos «Título 1…») | Sí | Sí (hoy se leen celda a celda; hay que montarlas en filas) | No existen en el archivo | Bien |
| `.odt` | Sí (`text:h`) | Sí | Sí, igual que `.docx` | No | Bien |
| PDF con texto | No fiable (habría que adivinarlo por tamaño de letra) | No | Solo las que tienen líneas | **Sí** (`<!-- página N -->`) | Se pueden unir las líneas partidas en párrafos |
| PDF escaneado / imagen | No | No | No | Sí | Texto del OCR, con sus errores |
| `.txt` / `.md` | Lo que traiga | Lo que traiga | Lo que traiga | No | |

Hay que escapar lo justo: una línea de un escrito que empiece por `#` o con `*`
no debe convertirse en título ni en negrita. Los códigos (`PERSOA_000001`,
`[DNI_NIE]`) no rompen el Markdown.

## 8. Decisiones pendientes (del usuario)

1. **¿La casilla «copia .md» activada por defecto?** Propuesta: desactivada, y que
   el programa recuerde la última elección. A quien no use Claude no le aparecen
   archivos de más.
2. **Nombre de la copia.** Propuesta: `demanda.anonimizado.pdf.md`. Si fuera
   `demanda.anonimizado.md`, un `demanda.pdf` y un `demanda.docx` de la misma
   carpeta escribirían en el mismo archivo y uno se perdería.
3. **¿Se incluye «solo convertir, sin anonimizar»?** Propuesta: sí, con las
   cautelas del punto 6. O dejarlo fuera y que, para documentos públicos, se
   use una herramienta general.

## 9. Recomendación

**Dentro del mismo programa (opción A).** Lo que hace falta para un buen `.md`
(leer bien cada formato, OCR, anonimizar el nombre del archivo, respetar la
revisión) ya existe en el anonimizador. Un programa aparte lo duplicaría, sería
otro instalador que mantener y abriría un segundo camino por donde podría
escaparse un dato.

**Fases propuestas:**

1. Copia `.md` del resultado: texto, títulos y listas de `.docx`/`.odt`, marcas de
   página en PDF, `.md` como entrada, casilla en la pantalla y `--markdown` en
   la línea de comandos. Con tests (cada uno fallando antes) y la suite completa.
2. Tablas: `.docx`/`.odt` y PDF con líneas.
3. «Solo convertir», si se decide en el punto 8.3.
4. Instalador nuevo de Windows, probado en la VM, y PDF de novedades.
