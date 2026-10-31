# Ficha de la Microsoft Store — Conversor de archivos para IA

Textos para Partner Center. Es una **aplicación propia**, distinta del Anonimizador jurídico
(otra ficha, otra certificación y otra clasificación IARC), con el mismo editor y la misma licencia.
Idiomas del paquete: español (España, `es-ES`) y gallego (`gl-ES`), los dos declarados en
`instalador/msix/AppxManifest-conversor.xml`, así que Partner Center pedirá una ficha para cada uno.

## Antes de enviar
1. **Reservar el nombre** «Conversor de archivos para IA» en Partner Center (Aplicaciones y juegos ›
   Nueva aplicación). Partner Center da entonces la identidad del paquete (*Product identity*):
   `Package/Identity/Name` y `Publisher`. Copiarlos letra a letra en
   `instalador/msix/AppxManifest-conversor.xml`: el `Name` que hay ahora es provisional (vale para
   la copia de prueba en la VM) y, si no coincide, la Store rechaza el paquete. El `Publisher`
   debería ser el mismo que el del anonimizador (la misma cuenta).
2. Compilar el paquete con el workflow «Paquete MSIX (Microsoft Store)», aplicación `conversor`
   (o con una etiqueta `msix-conversor-v1.0.0`), y probar en la VM la copia firmada de prueba.
3. Subir `Conversor-archivos-IA-<versión>-x64.msix` (artefacto `paquete-msix-store-conversor`).

## Pricing and availability
- Precio: **Gratis**. Sin compras dentro de la aplicación.
- Mercados: todos (por defecto).
- Visibilidad: pública.

## Properties
- Categoría: **Productividad**. Alternativa: Empresa › Legal y RR. HH., como el anonimizador (el
  conversor sirve para cualquier documento, pero el modo anonimizado está pensado para despachos).
- URL de la política de privacidad:
  `https://github.com/jllfontan-bot/anonimizador-juridico/blob/main/docs/store/politica-privacidad-conversor.md`
  (existirá en esa dirección cuando el conversor esté en `main`).
- Condiciones de uso: las del anonimizador sirven igual (mismo autor, misma licencia, sin garantía):
  `https://github.com/jllfontan-bot/anonimizador-juridico/blob/main/docs/store/condiciones-de-uso.md`.
- Sitio web: https://github.com/jllfontan-bot/anonimizador-juridico
- Contacto de soporte: jllfontan@gmail.com
- La aplicación no recoge datos personales; no requiere cuenta; no tiene publicidad.

## Age ratings (cuestionario IARC)
- Categoría: **Aplicación** (no juego).
- Violencia, sexo, lenguaje soez, drogas, apuestas: **No** a todo.
- ¿Los usuarios interactúan o intercambian contenido entre ellos?: **No**.
- ¿Comparte la ubicación del usuario?: **No**.
- ¿Permite compras digitales?: **No**.
- ¿Acceso sin restricciones a internet (navegador web)?: **No**. La aplicación no se conecta a
  internet ni abre ningún puerto; solo el enlace al código fuente de «Acerca de» se abre en el
  navegador del sistema, y únicamente si el usuario lo pulsa.
- Resultado esperado: apta para todos los públicos (PEGI 3 / equivalente).

## Store listing (es-ES)

**Nombre:** Conversor de archivos para IA

**Descripción corta** (≤ 270 caracteres):
Convierte documentos a Markdown (.md) en tu propio ordenador, con o sin anonimizar, para pasárselos
a una IA gastando menos tokens: PDF (también escaneados), Word, LibreOffice, hojas de cálculo,
presentaciones, páginas web y correos. Sin internet.

**Descripción:**
Conversor de archivos para IA pasa tus documentos a Markdown (.md), el formato que las inteligencias artificiales leen mejor y más barato. Si le das un PDF o un Word a una IA, gasta tokens y herramientas en convertirlo, y a veces lo lee mal; con el .md ya hecho, la IA recibe solo el texto, con sus títulos, listas y tablas. Todo se hace en tu ordenador: ni los documentos ni ningún dato salen a internet.

QUÉ CONVIERTE
• PDF con texto y escaneados (con OCR), .docx, .odt, .txt e imágenes.
• Hojas de cálculo (.xlsx, .ods, .csv), presentaciones (.pptx, .odp), páginas web guardadas (.html) y correos (.eml).
• Un archivo, una carpeta entera o un .zip, en un .md por documento o en un solo .md para todo el expediente.

PENSADO PARA GASTAR MENOS TOKENS
• Quita las cabeceras y pies de página que se repiten en cada hoja, une las líneas cortadas y los guiones de final de línea, y marca los títulos, también los de los PDF (anexos, capítulos, artículos).
• Puede trocear los documentos largos en partes de un tamaño dado, con un índice.
• Estima los tokens antes y después de la conversión.
• Cada .md lleva una cabecera mínima con el origen y si está anonimizado o no.

CON O SIN ANONIMIZAR
• Convertir sin anonimizar: el .md conserva los datos personales y el programa lo avisa con claridad, porque al pasarlo a una IA en línea esos datos salen del equipo.
• Convertir anonimizando: usa el mismo motor que el Anonimizador jurídico (nombres, DNI y demás datos personales pasan a códigos) y el mismo registro cifrado, de modo que una persona recibe el mismo código en los dos programas. Por defecto revisas cada documento antes de guardarlo; si prefieres el modo automático, el .md lo indica (revisado: no) y los documentos con más riesgo pasan igual a revisión.
• Las hojas de cálculo, presentaciones, páginas web y correos solo se convierten sin anonimizar, hasta que cada formato tenga sus propias pruebas de fugas.

TODO EN LOCAL, SIN PUERTOS ABIERTOS
No hay cuentas, ni publicidad, ni analítica. El programa no se conecta a internet ni abre ningún puerto en el ordenador: la ventana llama directamente al programa, sin servidor. El reconocimiento de texto y todo lo necesario van dentro del paquete.

Interfaz en castellano o gallego. Software libre con doble licencia, a tu elección: EUPL v1.2 o AGPL-3.0, con el código fuente publicado. Se distribuye sin garantía: revisa siempre el resultado antes de usarlo.

Desarrollado con la ayuda de Claude, la inteligencia artificial de Anthropic. El programa no está afiliado a Anthropic.

**Novedades de esta versión (1.0.0):**
Primera versión publicada en la Microsoft Store.

**Características del producto** (hasta 20, una por línea):
- Convierte a Markdown (.md) en tu ordenador: nada sale a internet
- PDF (también escaneados), .docx, .odt, .txt e imágenes
- Hojas de cálculo, presentaciones, páginas web y correos (.eml)
- Carpetas enteras y .zip, con un .md por documento o uno solo
- Quita cabeceras y pies repetidos y une las líneas cortadas
- Títulos también en los PDF: anexos, capítulos y artículos
- Troceado de documentos largos y estimación de tokens
- Modo anonimizado con el motor del Anonimizador jurídico
- Mismo registro cifrado: el mismo código en los dos programas
- Revisión de cada documento por defecto, o automático
- Avisos claros en el modo sin anonimizar
- Sin servidor ni puertos abiertos
- Interfaz en castellano y gallego
- Software libre (EUPL-1.2 o AGPL-3.0). Sin cuentas, publicidad ni recogida de datos
- Desarrollado con la ayuda de Claude, la IA de Anthropic (sin afiliación a Anthropic)

**Palabras clave** (hasta 7): markdown, convertir PDF, IA, tokens, anonimizar, documentos, Claude

**Capturas:** pendientes (pantalla de inicio, progreso, revisión, resultado con el resumen de tokens), con
datos inventados.

**Información de copyright:** © 2026 José Luis López Fontán. Doble licencia EUPL-1.2 o AGPL-3.0. Datos: INE (CC BY 4.0) y Nomenclátor de Galicia de la Xunta de Galicia (CC BY-SA 4.0).

**Términos de licencia adicionales:** Licencia Pública de la Unión Europea (EUPL) v1.2 — https://interoperable-europe.ec.europa.eu/collection/eupl/eupl-text-eupl-12 — o GNU Affero General Public License v3.0 — https://www.gnu.org/licenses/agpl-3.0.html, a elección del usuario; el paquete, por sus componentes, se distribuye con la AGPL-3.0. Condiciones de uso: https://github.com/jllfontan-bot/anonimizador-juridico/blob/main/docs/store/condiciones-de-uso.md

## Store listing (gl-ES)

**Nome:** Conversor de archivos para IA

(Partner Center só deixa escoller entre os nomes reservados. Para usar «Conversor de ficheiros para
IA» habería que reservalo tamén e comprobar que a certificación o acepta co `DisplayName` do
manifesto, que é único para os dous idiomas; o mesmo caso ca «Anonimizador xurídico».)

**Descrición curta** (≤ 270 caracteres):
Converte documentos a Markdown (.md) no teu propio ordenador, con ou sen anonimizar, para pasarllos
a unha IA gastando menos tokens: PDF (tamén escaneados), Word, LibreOffice, follas de cálculo,
presentacións, páxinas web e correos. Sen internet.

**Descrición:**
Conversor de archivos para IA pasa os teus documentos a Markdown (.md), o formato que as intelixencias artificiais len mellor e máis barato. Se lle dás un PDF ou un Word a unha IA, gasta tokens e ferramentas en convertelo, e ás veces leo mal; co .md xa feito, a IA recibe só o texto, cos seus títulos, listas e táboas. Todo se fai no teu ordenador: nin os documentos nin ningún dato saen a internet.

QUE CONVERTE
• PDF con texto e escaneados (con OCR), .docx, .odt, .txt e imaxes.
• Follas de cálculo (.xlsx, .ods, .csv), presentacións (.pptx, .odp), páxinas web gardadas (.html) e correos (.eml).
• Un ficheiro, un cartafol enteiro ou un .zip, nun .md por documento ou nun só .md para todo o expediente.

PENSADO PARA GASTAR MENOS TOKENS
• Quita as cabeceiras e pés de páxina que se repiten en cada folla, une as liñas cortadas e os guións de final de liña, e marca os títulos, tamén os dos PDF (anexos, capítulos, artigos).
• Pode trocear os documentos longos en partes dun tamaño dado, cun índice.
• Estima os tokens antes e despois da conversión.
• Cada .md leva unha cabeceira mínima coa orixe e se está anonimizado ou non.

CON OU SEN ANONIMIZAR
• Converter sen anonimizar: o .md conserva os datos persoais e o programa avísao con claridade, porque ao pasalo a unha IA en liña eses datos saen do equipo.
• Converter anonimizando: usa o mesmo motor ca o Anonimizador jurídico (nomes, DNI e demais datos persoais pasan a códigos) e o mesmo rexistro cifrado, de modo que unha persoa recibe o mesmo código nos dous programas. Por defecto revisas cada documento antes de gardalo; se prefires o modo automático, o .md indícao (revisado: non) e os documentos con máis risco pasan igual a revisión.
• As follas de cálculo, presentacións, páxinas web e correos só se converten sen anonimizar, ata que cada formato teña as súas propias probas de fugas.

TODO EN LOCAL, SEN PORTOS ABERTOS
Non hai contas, nin publicidade, nin analítica. O programa non se conecta a internet nin abre ningún porto no ordenador: a xanela chama directamente ao programa, sen servidor. O recoñecemento de texto e todo o necesario van dentro do paquete.

Interface en castelán ou galego. Software libre con dobre licenza, á túa escolla: EUPL v1.2 ou AGPL-3.0, co código fonte publicado. Distribúese sen garantía: revisa sempre o resultado antes de usalo.

Desenvolvido coa axuda de Claude, a intelixencia artificial de Anthropic. O programa non está afiliado a Anthropic.

**Novidades desta versión (1.0.0):**
Primeira versión publicada na Microsoft Store.

**Características do produto** (ata 20, unha por liña):
- Converte a Markdown (.md) no teu ordenador: nada sae a internet
- PDF (tamén escaneados), .docx, .odt, .txt e imaxes
- Follas de cálculo, presentacións, páxinas web e correos (.eml)
- Cartafoles enteiros e .zip, cun .md por documento ou un só
- Quita cabeceiras e pés repetidos e une as liñas cortadas
- Títulos tamén nos PDF: anexos, capítulos e artigos
- Troceado de documentos longos e estimación de tokens
- Modo anonimizado co motor do Anonimizador jurídico
- O mesmo rexistro cifrado: o mesmo código nos dous programas
- Revisión de cada documento por defecto, ou automático
- Avisos claros no modo sen anonimizar
- Sen servidor nin portos abertos
- Interface en castelán e galego
- Software libre (EUPL-1.2 ou AGPL-3.0). Sen contas, publicidade nin recollida de datos
- Desenvolvido coa axuda de Claude, a IA de Anthropic (sen afiliación a Anthropic)

**Palabras clave** (ata 7): markdown, converter PDF, IA, tokens, anonimizar, documentos, Claude

**Información de copyright** e **termos de licenza adicionais:** os mesmos ca na ficha en castelán.
