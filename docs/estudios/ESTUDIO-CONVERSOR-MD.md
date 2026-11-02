# Estudio: «Conversor de archivos para IA, con y sin anonimización, formato .md»

**Fecha:** 31/10/2026. **Estado:** estudio, sin código escrito.
**Base:** Anonimizador jurídico **1.1.0** (repositorio público `anonimizador-juridico`, commit `9199407`, 25/10/2026).
Comprobado que el espejo git del público y los instaladores 1.1.0 coinciden con ese commit; lo posterior (28–30/10)
son las fichas del alta en el portal Interoperable Europe, no código. GitHub también está en `9199407`.

## 1. Qué se quiere

Un programa **nuevo y propio**, en local, que convierta a `.md` cualquier archivo que se le vaya a pasar a una IA,
para que la IA no gaste tokens ni llamadas a herramientas convirtiéndolo ella. Dos modos:

- **Convertir sin anonimizar**: documentos públicos o propios (normativa, boletines, informes técnicos…).
- **Convertir anonimizando**: el mismo motor que el anonimizador, con el `.md` como resultado principal.

Esto cambia la conclusión del `ESTUDIO-SALIDA-MARKDOWN.md` (en esta misma carpeta) (25/10), que recomendaba no hacer un programa aparte.
Aquella decisión era sobre la **copia `.md` del anonimizado**, que ya está hecha y publicada en la 1.1.0. Lo que
se pide ahora es otro producto: un conversor general, donde «sin anonimizar» es el uso normal y no la excepción.

## 2. Qué se ahorra

Lo medido en el estudio anterior sigue valiendo:

| Lo que recibe la IA | Coste aproximado |
|---|---|
| PDF | Texto + **imagen de cada página** (unos 1.500–2.000 tokens más por página) |
| `.docx`, `.xlsx`, `.pptx`… | La IA tiene que escribir y ejecutar un script de conversión (tokens del script, de la salida y de los reintentos) |
| `.md` | Solo el texto (una página densa ≈ 4.200 caracteres ≈ 1.100–1.300 tokens) |

**Un `.md` cuesta entre la mitad y un tercio que el PDF**, y en escaneados más, porque el OCR ya lo hace el programa.

Un conversor pensado para IA puede ahorrar **además** quitando lo que se repite o no aporta (punto 5): en un
boletín o una sentencia, la cabecera y el pie de cada página son fácilmente el 5–10 % del texto.

## 3. Qué se reutiliza del anonimizador

La parte difícil ya existe, probada con un corpus real y 789 tests:

| Pieza | Dónde | Uso en el conversor |
|---|---|---|
| Lectura de `.docx` (cabeceras, pies, tablas, control de cambios aceptado) | `pipeline.cargar_documento_estruturado` (`pipeline.py:390`) | Tal cual |
| Lectura de `.odt` (títulos, tablas) | ídem | Tal cual |
| PDF palabra a palabra, texto nativo + OCR por zonas, rotaciones, letreado separado, texto «basura» sin ToUnicode | `pdf_estrutura.cargar_pdf_estruturado` (`pdf_estrutura.py:886`) | Tal cual: es lo que más valor tiene |
| Tablas de PDF con líneas | `taboas_pdf.py` | Tal cual |
| Imágenes con OCR (`spa+glg`) | `imaxes.cargar` | Tal cual |
| Generador de Markdown (títulos, listas numeradas, tablas, `<!-- página N -->`, escapado de `#`, `>`, `---`) | `copia_md.xerar` (`copia_md.py:77`) | Tal cual en modo anonimizado; con el texto original en modo sin anonimizar |
| Anonimización completa, registro cifrado, revisión humana, nombre de archivo anonimizado | `pipeline`, `registry`, `web` | Modo «anonimizando» |
| Carpetas, `.zip`, barra de progreso, cancelar, selector de carpetas, preferencias | `web.py`, `explorador.py`, `selector.py` | La lógica sí; las rutas de Flask no (punto 10) |
| Ventana de escritorio, idiomas es/gl, arranque en Windows | `desktop.py`, `idioma.py`, `textos/`, `arranque_windows.py` | pywebview, los textos y el arranque sí; el servidor Flask no (punto 10) |
| Plantillas HTML y estilos | `templates/` | Como punto de partida de las pantallas |
| Paquete MSIX y workflow de GitHub | `instalador/msix/`, `.github/workflows/msix.yml` | Copiar y adaptar |

**Un obstáculo concreto:** `pipeline.py` importa `ner` (spaCy) en la línea 33, y `copia_md.py` importa de
`pipeline`; `ner.py` importa `spacy` al empezar (el modelo se carga después, solo al detectar). Hoy **no se puede
leer un documento sin tener spaCy instalado e importarlo**, así que un paquete sin anonimización tendría que llevar
spaCy igualmente. Para un conversor sin anonimización hay que separar la lectura en un módulo propio (`lectura.py`)
que no dependa del NER. Es un cambio mecánico (mover funciones, sin cambiar lo que hacen), y los 789 tests sirven para
comprobar que no se rompe nada.

## 4. Formatos

### Ya leídos por el anonimizador (fase 1)

`.pdf` (nativo y escaneado), `.docx`, `.odt`, `.txt`, `.md`, imágenes (`.jpg`, `.png`, `.tif`, `.bmp`, `.webp`,
`.gif`) y `.zip`.

### Nuevos

| Formato | Cómo | Librería y licencia | Peso | Fase | Notas |
|---|---|---|---|---|---|
| `.xlsx` | Cada hoja como tabla Markdown | openpyxl (MIT) | Pequeño | 2 | Hojas grandes: ver punto 5 |
| `.ods` | ídem | odfpy (ya está) | 0 | 2 | |
| `.csv` | Tabla Markdown (o tal cual si es muy ancha) | biblioteca estándar | 0 | 2 | Detectar `;` y `,` |
| `.pptx` | Una sección por diapositiva: título, texto, tablas y **notas del orador** | python-pptx (MIT) | Pequeño | 2 | |
| `.odp` | ídem | odfpy | 0 | 2 | |
| `.html`, `.htm` | Quitar menús y scripts; títulos, listas, tablas y enlaces | beautifulsoup4 + markdownify (MIT) | Pequeño | 2 | Páginas del BOE/DOG guardadas |
| `.eml` | Cabeceras (De, Para, Fecha, Asunto), cuerpo y lista de adjuntos; los adjuntos se convierten | biblioteca estándar (`email`) | 0 | 2 | Muy habitual en expedientes |
| `.msg` (Outlook) | ídem | extract-msg (GPL-3.0, compatible con AGPL; **comprobar**) | Pequeño | 3 | |
| `.rtf` | Texto | striprtf (**comprobar licencia**) | Pequeño | 3 | |
| `.epub` | Es un zip de HTML: por capítulos | lo de HTML | 0 | 3 | |
| `.json`, `.xml` | Bloque de código, sangrado | estándar | 0 | 3 | |
| `.doc`, `.xls`, `.ppt` (antiguos) | Solo con LibreOffice instalado (se usaría si está; no se incluye) | — | — | 3 | Incluirlo serían unos 300 MB más. Si no está: aviso «guárdelo como .docx» |
| Audio y vídeo | Transcripción local | Motor del **Transcriptor JM-JL** (Whisper sobre OpenVINO) | Grande (modelos) | Aparte | Mejor que el Transcriptor saque también `.md`, en vez de meter los modelos en el conversor |

### Calidad esperable

| Entrada | Títulos | Listas | Tablas | Páginas |
|---|---|---|---|---|
| `.docx`, `.odt` | Sí | Sí, con numeración | Sí | No existen en el archivo |
| `.xlsx`, `.ods`, `.csv` | Nombre de la hoja | — | Sí | — |
| `.pptx`, `.odp` | Título de la diapositiva | Sí | Sí | Diapositiva N |
| HTML | Sí | Sí | Sí | — |
| PDF con texto | **Hoy no** (ver punto 9: tamaño de letra) | No | Las que tienen líneas | Sí |
| PDF escaneado, imagen | No | No | No | Sí; texto del OCR con sus errores |

## 5. Pensado para IA: ahorrar más que convirtiendo

Esto distingue al conversor de un `pandoc` cualquiera. Todo opcional, con valores por defecto prudentes:

1. **Cabeceras y pies repetidos** (PDF): una línea que aparece igual, en la misma posición, en la mayoría de las
   páginas («Diario Oficial de Galicia», «Página 3 de 20», el CSV del pie) se escribe **una sola vez** al
   principio, no en cada página. Los números de página ya están en `<!-- página N -->`.
2. **Unir líneas partidas** en párrafos y quitar el guion de corte de palabra («adminis-\ntración»). Ahorra poco
   en tokens pero mucho en calidad: la IA lee frases enteras y cita mejor.
3. **Espacios y líneas vacías** de sobra, fuera.
4. **Un solo `.md` por expediente**: convertir una carpeta (o un `.zip`) en `expediente.md`, con un índice y una
   sección por archivo. La IA lo lee de una vez en vez de abrir 30 archivos.
5. **Troceado** de documentos muy largos (p. ej. la memoria de 351 páginas): `memoria.parte-01.md`… con un
   `memoria.indice.md`, para que la IA lea solo lo que necesita.
6. **Hojas de cálculo grandes**: por encima de un límite (p. ej. 500 filas), aviso y opción de dejar la hoja en
   `.csv` aparte; una tabla Markdown enorme cuesta muchos tokens en barras y guiones.
7. **Estimación de tokens** antes y después, en pantalla. El contador real de Claude solo existe en línea, así que
   es una estimación (≈ 3,5 caracteres por token en castellano, según lo medido) y debe decirlo.
8. **Imágenes dentro de documentos**: el texto del OCR si lo tienen; si no, una marca `[imagen]`, nunca la imagen.

## 6. Modo «convertir anonimizando»

- **El mismo motor, no una copia.** El conversor llama al pipeline del anonimizador. Cualquier corrección de una
  fuga beneficia a los dos programas a la vez.
- **Automático o con revisión**, como ahora. Por defecto, revisión (es la garantía central del anonimizador).
- **Registro compartido**: si el conversor usa la misma carpeta de registro que el anonimizador
  (`Documentos\Anonimizador`), una persona recibe **el mismo código** en los dos programas. Hay que comprobar que
  dos programas abiertos a la vez no lo estropean (`tests/test_rexistro_concorrencia.py` cubre la concurrencia
  dentro del mismo programa; habría que ampliarlo a dos procesos).
- **Solo el `.md`**: el documento anonimizado en su formato original pasa a ser opcional.
- **Nombre de archivo anonimizado** (`nome_ficheiro_anonimizado`), como ahora.
- **Formatos nuevos**: cada uno necesita, además del lector, su prueba de fugas. En `.xlsx` y `.pptx` hay sitios
  donde se esconden datos (comentarios, notas, hojas ocultas, metadatos de autor, nombres en propiedades). Lo
  prudente: los formatos nuevos se convierten anonimizando **solo cuando tengan sus tests de fugas**; hasta
  entonces, en modo anonimizado se rechazan con un aviso, igual que hoy el `.zip` deja fuera lo que no sabe revisar.

## 7. Modo «convertir sin anonimizar»: cautelas

Un `.md` sin anonimizar que se pasa a una IA en la nube **saca del equipo los datos personales**. Para un despacho
eso puede ser un tratamiento no previsto. El programa no puede impedirlo, pero sí ponerlo difícil por error:

- **Elección explícita del modo** en cada tanda (dos botones grandes, sin valor por defecto escondido).
- **Aviso** en el modo sin anonimizar: «Este archivo conserva los datos personales».
- **Marca en el propio archivo**, una cabecera mínima (pocos tokens), útil también para la IA:

  ```markdown
  ---
  origen: demanda.pdf
  paginas: 12
  anonimizado: no
  convertido: 2026-10-31, Conversor para IA 1.0
  ---
  ```

  En modo anonimizado, `origen` lleva el nombre ya anonimizado.
- Si el modo sin anonimizar detecta DNI, correos o teléfonos (los reconocedores por patrón son baratos y no
  necesitan spaCy), **un aviso**: «Este documento parece tener datos personales: ¿convertirlo anonimizando?».
  Un aviso, no un bloqueo.

## 8. Arquitectura: tres opciones

| | **A. Mismo repositorio, dos programas** | B. Repositorio aparte que depende del anonimizador | C. Repositorio aparte sobre MarkItDown/Docling |
|---|---|---|---|
| Código | Núcleo compartido (`lectura`, `copia_md`, anonimización) y dos aplicaciones encima | El conversor instala el anonimizador como librería (por versión) | Conversión con una herramienta externa; anonimización con el anonimizador |
| Correcciones | Llegan a los dos a la vez | Hay que subir la versión de la dependencia | Dos motores de lectura distintos |
| Tests | Una sola suite | Dos, con riesgo de desfase | Dos |
| Instaladores | Dos paquetes desde el mismo workflow | Dos | Dos |
| Calidad en PDF escaneado y documentos jurídicos | La del anonimizador | La del anonimizador | Peor (punto 9) |
| Riesgo de fuga en modo anonimizado | El mismo texto alimenta el `.md` | Ídem | Si el texto del conversor no es el mismo que anonimiza el anonimizador, puede quedar algo fuera |

**Recomendación: A.** Un repositorio, un núcleo, dos aplicaciones y dos paquetes. Es lo que menos mantenimiento
pide a una sola persona y lo que garantiza que el modo anonimizado es exactamente el del anonimizador.

Dos paquetes posibles del conversor:

- **Completo** (con anonimización): del tamaño del anonimizador actual, unos 155 MB.
- **Ligero** (solo convertir, sin spaCy, el modelo ni OpenCV): estimado en 60–90 MB. Opcional, más adelante.

## 9. ¿Y las herramientas que ya existen?

| Herramienta | Licencia | Lo bueno | Por qué no basta |
|---|---|---|---|
| MarkItDown (Microsoft) | MIT | Muchos formatos, pensada para IA | PDF sin OCR ni tablas; el audio y la descripción de imágenes usan servicios en línea; no anonimiza |
| Docling (IBM) | MIT | Muy buena maquetación y tablas en PDF | Modelos de IA y PyTorch: varios GB, lento en un ordenador normal |
| pymupdf4llm (Artifex) | AGPL-3.0 | De los autores de PyMuPDF; **títulos por tamaño de letra**, negritas, tablas | Solo PDF; su OCR no es el ajustado del anonimizador |
| pandoc | GPL-2.0+ | Excelente en `.docx`/`.odt`/HTML | No lee PDF; binario aparte |

Conclusión: **no conviene construir sobre ellas**, pero **pymupdf4llm** merece una prueba para lo único que el
anonimizador no hace bien: **detectar títulos en PDF con texto**. Es compatible (AGPL, como PyMuPDF, que ya va
dentro) y apenas añade peso. Lo que se tomaría de ella es la detección de títulos, no la lectura: el texto debe
seguir saliendo de `pdf_estrutura` para que el modo anonimizado no cambie.

## 10. Interfaz y distribución

### Sin servidor local (decidido el 31/10/2026)

El anonimizador no usa internet, pero abre un servidor web en el propio ordenador (Flask en `127.0.0.1`) y la
ventana se conecta a él. Tiene protecciones contra *DNS rebinding* y contra páginas web maliciosas
(`web.py:196`), pero el propio código las llama barrera «blanda», sin clave por sesión. **El conversor no tendrá
servidor**:

- **Cómo:** pywebview con `js_api`. La pantalla (HTML, estilos y textos es/gl, que se aprovechan) llama
  directamente a funciones de Python, sin HTTP. Las tareas largas (carpetas, OCR) van en un hilo, y el progreso
  se envía a la pantalla con `evaluate_js`, como hoy hacen `/estado` y `/cancelar`.
- **Por qué:** ningún puerto abierto (otro programa o usuario del mismo equipo no puede conectarse), sin avisos del
  cortafuegos ni del antivirus, sin choques de puerto, y una frase sencilla para despachos y Administraciones:
  «no abre ningún puerto ni se conecta a nada».
- **Comprobación obligatoria:** pywebview puede arrancar un servidor HTTP interno propio cuando se le dan archivos
  locales. Hay que configurarlo para que no lo haga (cargar el HTML directamente) y **comprobar con `netstat` /
  `lsof` en Mac y en la VM de Windows que el programa no escucha en ningún puerto**. Esta comprobación va en los
  tests o, si no se puede automatizar, en la lista de pruebas de cada versión.
- **Tests:** el cliente de pruebas de Flask ya no sirve. La lógica se prueba llamando a la clase de la API
  directamente (más sencillo que hoy); la pantalla, con alguna prueba de la ventana real.
- **El anonimizador se queda como está**: cambiarlo supondría rehacer 20 rutas, 11 plantillas y 17 archivos de
  tests, y una certificación nueva en la Store, para cerrar un riesgo pequeño. Si más adelante se quiere,
  lo hecho en el conversor sirve de modelo. Mientras tanto, un arreglo barato sería añadir una clave secreta por
  sesión al servidor, para que la barrera deje de ser «blanda».

Con la opción A esto encaja: los dos programas comparten el motor (lectura, Markdown y anonimización) y cada uno
tiene su propia interfaz.

### Pantalla y distribución

- **Textos** en `textos/es.json` y `gl.json`, como el anonimizador.
- **Pantalla**: arrastrar archivos o carpetas, dos botones («Convertir» / «Convertir anonimizando»), carpeta de
  salida, opciones del punto 5 plegadas, progreso y botones «Abrir carpeta» y «Copiar ruta».
- **Menú contextual de Windows** «Convertir a .md para IA», como ya hace el Transcriptor. Es lo más cómodo.
- **Línea de comandos**: `conversor ARCHIVO|CARPETA [--anonimizar] [--un-solo-md] [--trocear N]`, útil también para
  que Claude Code lo llame sin gastar tokens en la conversión.
- **Microsoft Store**: una ficha nueva (otra aplicación, otra certificación, su propia clasificación IARC), con el
  mismo workflow MSIX. Licencia: la misma doble EUPL-1.2 o AGPL-3.0 del anonimizador.
- **Nombre de los archivos**: `demanda.pdf.md` sin anonimizar; `<nombre anonimizado>.anonimizado.pdf.md`
  anonimizando (el mismo criterio que la copia `.md` de la 1.1.0, para que un `.pdf` y un `.docx` del mismo nombre
  no se pisen).

### Extra: extensión para Claude Desktop

Ya existe un conector `.mcpb` propio (Consulta Boletines Oficiales). Una extensión «convertir a Markdown» haría que
Claude pidiera la conversión al programa local y recibiera **solo el texto `.md`** (y, en modo anonimizado, solo
el texto anonimizado). Es la forma más directa de ahorrar tokens sin que el usuario tenga que convertir antes.
Requiere el programa instalado (la extensión llamaría a su línea de comandos). Fase posterior, cuando el
conversor esté estable.

## 11. Riesgos

- **Separar la lectura del NER** toca el corazón del anonimizador. Mitigación: cambio sin modificar lógica, suite
  completa y comparar el texto leído antes y después sobre el corpus de medición.
- **Formatos nuevos en modo anonimizado**: cada uno puede tener escondites de datos nuevos (punto 6).
- **Dos productos en la Store**: el doble de fichas, respuestas y certificaciones.
- **Interfaz sin servidor**: es una forma de trabajar nueva en este proyecto (llamadas directas a Python en vez de
  formularios y rutas) y hay que confirmar que pywebview no abre un puerto por su cuenta (punto 10).
- **Expectativa de «todo tipo de archivos»**: siempre habrá formatos fuera (CAD, bases de datos, `.doc` sin
  LibreOffice). El programa debe listar lo que deja fuera, como hace el anonimizador con los `omitidos` del zip.

## 12. Decisiones

**Tomada (31/10/2026):** el conversor no tendrá servidor local (pywebview con `js_api`); el anonimizador sigue
con Flask (punto 10).

**Pendientes:**

1. **¿Mismo repositorio (A) o aparte?** Propuesta: A.
2. **¿Registro compartido con el anonimizador?** Propuesta: sí, mismo `Documentos\Anonimizador`, para que los
   códigos coincidan.
3. **¿Modo anonimizado: revisión o automático por defecto?** Propuesta: revisión, como el anonimizador.
4. **¿Paquete ligero sin anonimización?** Propuesta: no al principio; un solo paquete completo y el ligero solo
   si se pide.
5. **Formatos de la fase 2.** Propuesta: `.xlsx`/`.ods`/`.csv`, `.pptx`/`.odp`, HTML y `.eml`.
6. **¿Publicar en la Microsoft Store?** Propuesta: sí, cuando la fase 2 esté probada en la VM.
7. **Nombre del programa.** Propuestas: «Conversor para IA», «Pasar a Markdown», «Conversor .md jurídico».

## 13. Fases propuestas

1. **Separar la lectura** (`lectura.py` sin spaCy) y adaptar `copia_md` para el texto original. Suite completa.
2. **Conversor mínimo** con los formatos que ya se leen: los dos modos, carpeta y `.zip`, un solo `.md` por
   expediente, cabecera con `anonimizado: sí/no`, pantalla **sin servidor local** (pywebview con `js_api`,
   comprobando que no queda ningún puerto abierto), línea de comandos. Tests de cada modo (cada uno fallando
   antes).
3. **Ahorro para IA**: cabeceras y pies repetidos, unir líneas y guiones, troceado, estimación de tokens.
   Medido sobre el corpus: tokens antes y después.
4. **Formatos nuevos** de la fase 2, primero sin anonimizar y después con sus tests de fugas para el modo
   anonimizado.
5. **Títulos en PDF** (prueba de pymupdf4llm).
6. **Paquete MSIX**, prueba en la VM de Windows (incluida la comprobación de puertos con `netstat`), PDF de
   manual y ficha de la Store.
7. Más adelante: formatos de la fase 3, menú contextual, extensión para Claude Desktop, salida `.md` del
   Transcriptor.
