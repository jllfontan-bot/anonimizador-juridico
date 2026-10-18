# Ficha de la Microsoft Store — Anonimizador jurídico

Textos para Partner Center (Store ID `9PK1J429MNN5`). Idiomas del paquete: español (España,
`es-ES`) y gallego (`gl-ES`), los dos declarados en `instalador/msix/AppxManifest.xml`, así que
Partner Center pedirá una ficha para cada uno.

## Pricing and availability
- Precio: **Gratis**. Sin compras dentro de la aplicación.
- Mercados: todos (por defecto).
- Visibilidad: pública.

## Properties
- Categoría: **Empresa**, subcategoría **Legal y RR. HH.** (*Business › Legal & HR*). Es donde
  buscará el público al que va dirigido (despachos, procuradores, gestorías, administración).
  Alternativa: Productividad (sin subcategoría).
- URL de la política de privacidad:
  `https://github.com/jllfontan-bot/anonimizador-juridico/blob/main/docs/store/politica-privacidad.md`.
- Condiciones de uso: `docs/store/condiciones-de-uso.md` (es y gl en el mismo archivo), enlazadas
  en «Términos de licencia adicionales» de cada ficha:
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
  internet; solo los dos enlaces de «Acerca de» (código fuente y texto de la licencia) se abren
  en el navegador del sistema, y únicamente si el usuario los pulsa.
- Resultado esperado: apta para todos los públicos (PEGI 3 / equivalente).

## Store listing (es-ES)

**Nombre:** Anonimizador jurídico

**Descripción corta** (≤ 270 caracteres):
Anonimiza documentos jurídicos en tu propio ordenador: sustituye nombres, DNI, teléfonos,
direcciones y otros datos personales por códigos, conservando el formato. Sin internet: las
identidades quedan en un registro cifrado local, con reversión controlada.

**Descripción:**
Anonimizador jurídico sustituye los nombres, DNI y demás datos personales de documentos jurídicos por códigos (PERSONA_000001, [DIRECCIÓN], [TELÉFONO]…) antes de compartirlos, publicarlos o usarlos fuera del expediente. Pensado para despachos de abogados, procuradores, gestorías y administraciones públicas. Todo el proceso se hace en tu ordenador: ni los documentos ni ningún dato salen nunca a internet.

QUÉ HACE
• Lee documentos .txt, .docx, .odt y .pdf (también escaneados, con OCR), imágenes (.jpg, .png, .tif y otras) y archivos .zip, uno a uno o una carpeta entera.
• Guarda el resultado con el mismo formato que el original: los .docx y .odt conservan tablas, listas y estilos; en los PDF los datos se eliminan de verdad del archivo, no se tapan con un recuadro.
• Detecta personas y más de quince tipos de identificador: DNI/NIE, pasaporte, teléfono, correo, dirección, matrícula, IBAN, tarjeta, número de la Seguridad Social, referencia catastral, número de colegiado, CSV, números de referencia y de expediente, N.R.P.
• Da a cada persona un código estable, el mismo en todos los documentos de un caso. Dos nombres iguales sin un DNI que lo confirme nunca se fusionan: se tratan como personas distintas y el programa avisa del posible homónimo.
• Revisa también el nombre del archivo, para que no deje a la vista la identidad que el contenido ya tapa.
• No anonimiza a jueces, magistrados, letrados de la Administración de Justicia ni médicos forenses que actúan en su función (criterio de la AEPD), y los lista aparte para que compruebes la exención.

REVISIÓN HUMANA Y AVISOS
Ningún sistema automático detecta el 100 % de los datos personales de un documento real. Por eso el programa:
• Permite revisar cada documento antes de guardarlo: desmarcar lo que no es una persona, tapar lo que se haya escapado o generalizar un dato.
• Vuelve a escanear el texto ya anonimizado y avisa de posibles fugas (lo que todavía parece un nombre o un número identificativo).
• Avisa de riesgos de efecto mosaico (combinaciones como profesión + lugar + edad que pueden identificar a alguien) y de datos de categoría especial (art. 9 RGPD). Estos riesgos no se corrigen solos: los decide quien revisa.
Para lotes grandes hay un modo automático; el resumen indica qué documentos conviene revisar.

REGISTRO CIFRADO Y REVERSIÓN CONTROLADA
La correspondencia entre cada código y la persona real se guarda cifrada en tu ordenador (carpeta Documentos\Anonimizador), con la clave en el Administrador de credenciales de Windows. Recuperar una identidad exige una contraseña de reversión y un motivo, y queda anotado en una auditoría cifrada cuyas entradas no se pueden editar ni borrar desde el programa. Como se puede revertir, en términos del RGPD el resultado es una seudonimización: tú decides quién accede al registro.

TODO EN LOCAL
No hay cuentas, ni publicidad, ni analítica. El programa no se conecta a internet: el reconocimiento de texto, el modelo de lenguaje y todo lo necesario van dentro del paquete.

Interfaz en castellano o gallego. Software libre (AGPL-3.0), con el código fuente publicado. Se distribuye sin garantía: no sustituye la revisión profesional del documento ni el asesoramiento jurídico.

**Novedades de esta versión (1.0.0):**
Primera versión publicada en la Microsoft Store. Los datos de trabajo (registro cifrado, idioma elegido y registro de errores) se guardan en Documentos\Anonimizador, para que no se pierdan al desinstalar o actualizar. Si ya usabas el instalador anterior del programa, la primera vez se copia tu registro a esa carpeta (el original no se toca) y la pantalla de inicio te lo avisa. Nueva página «Acerca de» con la versión, la licencia y el enlace al código fuente, y acceso al manual de uso desde la pantalla de inicio.

**Características del producto** (hasta 20, una por línea):
- Funciona 100 % en local: los documentos nunca salen del ordenador
- .txt, .docx, .odt, .pdf (también escaneados), imágenes y .zip
- Conserva el formato original del documento
- Redacción real en PDF: el dato se elimina, no se tapa
- Más de 15 tipos de identificador: DNI/NIE, IBAN, teléfono, dirección, CSV…
- Código estable por persona en todos los documentos de un caso
- Los posibles homónimos nunca se fusionan
- Anonimiza también el nombre del archivo
- Revisión humana antes de guardar, o modo automático para lotes
- Avisos de posibles fugas, efecto mosaico y datos de categoría especial
- Exención de jueces, magistrados, LAJ y forenses en su función, revisable
- Carpetas enteras, con progreso y cancelación del lote
- Registro de identidades cifrado, con la clave en el llavero de Windows
- Reversión con contraseña, motivo obligatorio y auditoría cifrada
- Interfaz en castellano y gallego
- Software libre (AGPL-3.0). Sin cuentas, publicidad ni recogida de datos

**Palabras clave** (hasta 7): anonimizar, anonimización, seudonimización, RGPD, protección de datos, documentos jurídicos, abogados

**Capturas:** 6, de 1920×1080, con datos inventados (`docs/fonte/datos_exemplo.py`), hechas a partir de las capturas de `docs/fonte/img/`: pantalla de inicio, progreso de un lote, revisión con posibles homónimos y fugas, resultado guardado, reversión controlada.

**Información de copyright:** © 2026 José Luis López Fontán. Licencia AGPL-3.0. Datos: INE (CC BY 4.0) y Nomenclátor de Galicia de la Xunta de Galicia (CC BY-SA 4.0).

**Términos de licencia adicionales:** GNU Affero General Public License v3.0 — https://www.gnu.org/licenses/agpl-3.0.html. Condiciones de uso: https://github.com/jllfontan-bot/anonimizador-juridico/blob/main/docs/store/condiciones-de-uso.md

## Store listing (gl-ES)

**Nome:** Anonimizador jurídico
(Partner Center só deixa escoller entre os nomes reservados. Para usar «Anonimizador xurídico»
habería que reservalo tamén e comprobar que a certificación o acepta co `DisplayName` actual do
manifesto, que é único para os dous idiomas.)

**Descrición curta** (≤ 270 caracteres):
Anonimiza documentos xurídicos no teu propio ordenador: substitúe nomes, DNI, teléfonos,
enderezos e outros datos persoais por códigos, conservando o formato. Sen internet: as
identidades quedan nun rexistro cifrado local, con reversión controlada.

**Descrición:**
Anonimizador jurídico substitúe os nomes, DNI e demais datos persoais de documentos xurídicos por códigos (PERSOA_000001, [ENDEREZO], [TELÉFONO]…) antes de compartilos, publicalos ou usalos fóra do expediente. Pensado para despachos de avogados, procuradores, xestorías e administracións públicas. Todo o proceso faise no teu ordenador: nin os documentos nin ningún dato saen nunca a internet.

QUE FAI
• Le documentos .txt, .docx, .odt e .pdf (tamén escaneados, con OCR), imaxes (.jpg, .png, .tif e outras) e arquivos .zip, un a un ou un cartafol enteiro.
• Garda o resultado co mesmo formato ca o orixinal: os .docx e .odt conservan táboas, listas e estilos; nos PDF os datos elimínanse de verdade do ficheiro, non se tapan cun recadro.
• Detecta persoas e máis de quince tipos de identificador: DNI/NIE, pasaporte, teléfono, correo, enderezo, matrícula, IBAN, tarxeta, número da Seguridade Social, referencia catastral, número de colexiado, CSV, números de referencia e de expediente, N.R.P.
• Dá a cada persoa un código estable, o mesmo en todos os documentos dun caso. Dous nomes iguais sen un DNI que o confirme nunca se fusionan: trátanse como persoas distintas e o programa avisa do posible homónimo.
• Revisa tamén o nome do ficheiro, para que non deixe á vista a identidade que o contido xa tapa.
• Non anonimiza xuíces, maxistrados, letrados da Administración de Xustiza nin médicos forenses que actúan na súa función (criterio da AEPD), e lístaos á parte para que comprobes a exención.

REVISIÓN HUMANA E AVISOS
Ningún sistema automático detecta o 100 % dos datos persoais dun documento real. Por iso o programa:
• Permite revisar cada documento antes de gardalo: desmarcar o que non é unha persoa, tapar o que se escapase ou xeneralizar un dato.
• Volve escanear o texto xa anonimizado e avisa de posibles fugas (o que aínda parece un nome ou un número identificativo).
• Avisa de riscos de efecto mosaico (combinacións como profesión + lugar + idade que poden identificar alguén) e de datos de categoría especial (art. 9 RXPD). Estes riscos non se corrixen sós: decídeos quen revisa.
Para lotes grandes hai un modo automático; o resumo indica que documentos convén revisar.

REXISTRO CIFRADO E REVERSIÓN CONTROLADA
A correspondencia entre cada código e a persoa real gárdase cifrada no teu ordenador (cartafol Documentos\Anonimizador), coa clave no Administrador de credenciais de Windows. Recuperar unha identidade esixe un contrasinal de reversión e un motivo, e queda anotado nunha auditoría cifrada con entradas que non se poden editar nin borrar dende o programa. Como se pode reverter, en termos do RXPD o resultado é unha seudonimización: ti decides quen accede ao rexistro.

TODO EN LOCAL
Non hai contas, nin publicidade, nin analítica. O programa non se conecta a internet: o recoñecemento de texto, o modelo de linguaxe e todo o necesario van dentro do paquete.

Interface en castelán ou galego. Software libre (AGPL-3.0), co código fonte publicado. Distribúese sen garantía: non substitúe a revisión profesional do documento nin o asesoramento xurídico.

**Novidades desta versión (1.0.0):**
Primeira versión publicada na Microsoft Store. Os datos de traballo (rexistro cifrado, idioma escollido e rexistro de erros) gárdanse en Documentos\Anonimizador, para que non se perdan ao desinstalar ou actualizar. Se xa usabas o instalador anterior do programa, a primeira vez cópiase o teu rexistro a ese cartafol (o orixinal non se toca) e a pantalla de inicio avísao. Nova páxina «Acerca de» coa versión, a licenza e a ligazón ao código fonte, e acceso ao manual de uso dende a pantalla de inicio.

**Características do produto** (ata 20, unha por liña):
- Funciona 100 % en local: os documentos nunca saen do ordenador
- .txt, .docx, .odt, .pdf (tamén escaneados), imaxes e .zip
- Conserva o formato orixinal do documento
- Redacción real en PDF: o dato elimínase, non se tapa
- Máis de 15 tipos de identificador: DNI/NIE, IBAN, teléfono, enderezo, CSV…
- Código estable por persoa en todos os documentos dun caso
- Os posibles homónimos nunca se fusionan
- Anonimiza tamén o nome do ficheiro
- Revisión humana antes de gardar, ou modo automático para lotes
- Avisos de posibles fugas, efecto mosaico e datos de categoría especial
- Exención de xuíces, maxistrados, LAJ e forenses na súa función, revisable
- Cartafoles enteiros, con progreso e cancelación do lote
- Rexistro de identidades cifrado, coa clave no chaveiro de Windows
- Reversión con contrasinal, motivo obrigatorio e auditoría cifrada
- Interface en castelán e galego
- Software libre (AGPL-3.0). Sen contas, publicidade nin recollida de datos

**Palabras clave** (ata 7): anonimizar, anonimización, seudonimización, RXPD, protección de datos, documentos xurídicos, avogados

**Capturas:** as mesmas pantallas ca en es-ES, coa interface en galego.

**Información de copyright:** © 2026 José Luis López Fontán. Licenza AGPL-3.0. Datos: INE (CC BY 4.0) e Nomenclátor de Galicia da Xunta de Galicia (CC BY-SA 4.0).

**Termos de licenza adicionais:** GNU Affero General Public License v3.0 — https://www.gnu.org/licenses/agpl-3.0.html. Condicións de uso: https://github.com/jllfontan-bot/anonimizador-juridico/blob/main/docs/store/condiciones-de-uso.md#condicións-de-uso--anonimizador-jurídico

## Submission options
**Capacidades restringidas — justificación de runFullTrust** (en inglés, 485 caracteres):
Anonimizador jurídico is a Win32 desktop app (bundled Python runtime, window via WebView2) packaged as MSIX. runFullTrust is needed to run that desktop process: it opens the documents the user picks, saves the anonymized copies next to them or in a folder the user chooses, keeps its encrypted registry in Documents\Anonimizador and stores the key in Windows Credential Manager. It works fully offline: its internal server listens only on 127.0.0.1 and nothing is sent to the internet.

**Notas para la certificación** (en inglés, que es lo que leen los revisores):
No account or credentials are needed and no internet connection is used. To test: create a .txt file with invented data, for example "Marta Lourenzo Vidal, phone 600 123 456, lives at Rúa do Sol, 14, Lugo." Start the app, click «Elegir archivo…» (Choose file) and select it, leave «Comprobar antes de guardar» selected and click «Anonimizar y revisar». On the review screen click «Confirmar revisión y guardar»: a copy named *.anonimizado.txt is saved next to the original with the name, phone and address replaced by codes. The interface language (Spanish/Galician) is switched with the buttons at the top right of the start screen. Working data is stored in Documents\Anonimizador.
