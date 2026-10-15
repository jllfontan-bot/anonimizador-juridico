# Política de privacidad — Anonimizador jurídico (aplicación de escritorio)

*[Versión en galego más abajo.](#política-de-privacidade--anonimizador-jurídico-aplicación-de-escritorio)*

**Última actualización:** 15 de octubre de 2026
**Desarrollador:** José Luis López Fontán (desarrollador particular). Aplicación gratuita y de código abierto (AGPL-3.0), sin ánimo de lucro.
**Contacto:** jllfontan@gmail.com

## Resumen

La aplicación **no recoge, no envía y no vende datos personales**. No tiene cuentas de usuario, ni publicidad, ni analítica, ni telemetría, y no se conecta a internet. El desarrollador no recibe ningún dato de quien la usa ni de los documentos que procesa.

## Qué hace la aplicación

Sustituye los nombres, DNI y demás datos personales de los documentos que el usuario elige por códigos (`PERSONA_000001`, `[DIRECCIÓN]`…). Todo el proceso se hace **en el propio ordenador del usuario**:

- La lectura de los documentos, el reconocimiento de texto (OCR) y la detección de datos personales funcionan sin conexión: todo lo necesario va dentro del paquete instalado.
- La interfaz es una ventana propia del programa (componente Microsoft Edge WebView2 de Windows) que solo muestra páginas del propio programa, servidas por un servidor interno que escucha únicamente en `127.0.0.1`: no es accesible desde otros equipos.
- La aplicación no envía a internet ni los documentos, ni su contenido, ni los resultados, ni ningún otro dato.
- Lo único que se abre fuera del programa son los dos enlaces de la página «Acerca de» (código fuente y texto de la licencia), en el navegador del usuario y solo si los pulsa; esa visita se rige por las condiciones de cada sitio web.

## Qué se guarda en el ordenador

La aplicación lee únicamente los archivos y carpetas que el usuario le indica y guarda:

- **Los documentos anonimizados**, junto al original o en la carpeta de salida que elija el usuario. El documento original nunca se modifica ni se borra.
- En la carpeta **`Documentos\Anonimizador`** del usuario:
  - `datos_rexistro`: el **registro de correspondencias** entre cada código y la persona real, la **auditoría** (creación de códigos, posibles homónimos, reversiones y sus motivos, intentos fallidos) y las **revisiones pendientes**. Es la carpeta de registro por defecto; el usuario puede indicar otra para cada caso. Todo ello **cifrado**; nada que contenga identidades reales se escribe en disco sin cifrar.
  - `preferencias.json`: el idioma elegido.
  - `anonimizador.log`: un registro técnico de errores, que puede incluir rutas o nombres de archivos.
- La **clave de cifrado** del registro, en el **Administrador de credenciales de Windows**, separada de lo que cifra.

Si la carpeta Documentos del usuario se sincroniza con OneDrive u otro servicio en la nube, ese servicio copiará también estos archivos: lo hace el sistema, no la aplicación, y el registro, la auditoría y las revisiones pendientes viajan cifrados (la clave no está en esa carpeta).

Si el usuario usaba una versión anterior del programa instalada con el instalador clásico, la primera vez se **copia** su registro desde `%LOCALAPPDATA%\Anonimizador` a `Documentos\Anonimizador`; el original no se toca.

Estos datos **no se borran al desinstalar** la aplicación, a propósito: sin el registro y su clave ya no se podría saber a quién corresponde cada código de los documentos anonimizados. Para eliminarlos, el usuario puede borrar la carpeta `Documentos\Anonimizador` y, en el Administrador de credenciales de Windows (Credenciales de Windows), las entradas que llevan «anonimizador-xuridico» en el nombre. Hecho esto, la anonimización de los documentos ya generados no podrá revertirse.

## Recuperación de identidades (reversión controlada)

Recuperar la identidad real detrás de un código, o ver el listado completo de un registro, exige una contraseña de reversión definida por el usuario y un motivo obligatorio, y queda anotado en la auditoría cifrada junto con el usuario de Windows y la fecha. Todo ello ocurre en el ordenador del usuario; el desarrollador no tiene acceso al registro, a la clave ni a la contraseña, y no puede recuperarlos.

## Responsabilidad sobre los datos de los documentos

Los documentos que se procesan pueden contener datos personales de terceros. **El usuario (o la organización para la que trabaja) es el responsable del tratamiento** de esos datos conforme al Reglamento (UE) 2016/679 (RGPD) y a la Ley Orgánica 3/2018 (LOPDGDD): decide qué documentos procesa, con qué finalidad, quién accede al registro y a los documentos, y cuánto tiempo los conserva. El desarrollador no accede a esos datos ni los trata por cuenta de nadie.

Mientras se conserve el registro, los documentos resultantes están **seudonimizados** (art. 4.5 RGPD), no anonimizados de forma irreversible, y siguen siendo datos personales para quien tenga acceso al registro. Además, ningún sistema automático detecta todos los datos personales de un documento real: la aplicación avisa de posibles fugas y de riesgos de reidentificación, pero la revisión final corresponde al usuario.

## Menores

La aplicación es una herramienta profesional para documentos jurídicos y no está dirigida a menores. No recoge datos de nadie.

## Cambios

Cualquier cambio de esta política se publicará en esta misma dirección, con su fecha. Si una versión futura añadiera alguna función que se conecte a internet, esta política se actualizará antes de publicarla, indicando qué se envía, a quién y cuándo.

---

# Política de privacidade — Anonimizador jurídico (aplicación de escritorio)

**Última actualización:** 15 de outubro de 2026
**Desenvolvedor:** José Luis López Fontán (desenvolvedor particular). Aplicación gratuíta e de código aberto (AGPL-3.0), sen ánimo de lucro.
**Contacto:** jllfontan@gmail.com

## Resumo

A aplicación **non recolle, non envía e non vende datos persoais**. Non ten contas de usuario, nin publicidade, nin analítica, nin telemetría, e non se conecta a internet. O desenvolvedor non recibe ningún dato de quen a usa nin dos documentos que procesa.

## Que fai a aplicación

Substitúe os nomes, DNI e demais datos persoais dos documentos que o usuario escolle por códigos (`PERSOA_000001`, `[ENDEREZO]`…). Todo o proceso faise **no propio ordenador do usuario**:

- A lectura dos documentos, o recoñecemento de texto (OCR) e a detección de datos persoais funcionan sen conexión: todo o necesario vai dentro do paquete instalado.
- A interface é unha xanela propia do programa (compoñente Microsoft Edge WebView2 de Windows) que só amosa páxinas do propio programa, servidas por un servidor interno que escoita unicamente en `127.0.0.1`: non é accesible dende outros equipos.
- A aplicación non envía a internet nin os documentos, nin o seu contido, nin os resultados, nin ningún outro dato.
- O único que se abre fóra do programa son as dúas ligazóns da páxina «Acerca de» (código fonte e texto da licenza), no navegador do usuario e só se as preme; esa visita réxese polas condicións de cada sitio web.

## Que se garda no ordenador

A aplicación le unicamente os ficheiros e cartafoles que o usuario lle indica e garda:

- **Os documentos anonimizados**, xunto ao orixinal ou no cartafol de saída que escolla o usuario. O documento orixinal nunca se modifica nin se borra.
- No cartafol **`Documentos\Anonimizador`** do usuario:
  - `datos_rexistro`: o **rexistro de correspondencias** entre cada código e a persoa real, a **auditoría** (creación de códigos, posibles homónimos, reversións e os seus motivos, intentos fallidos) e as **revisións pendentes**. É o cartafol de rexistro por defecto; o usuario pode indicar outro para cada caso. Todo iso **cifrado**; nada que conteña identidades reais se escribe en disco sen cifrar.
  - `preferencias.json`: o idioma escollido.
  - `anonimizador.log`: un rexistro técnico de erros, que pode incluír rutas ou nomes de ficheiros.
- A **clave de cifrado** do rexistro, no **Administrador de credenciais de Windows**, separada do que cifra.

Se o cartafol Documentos do usuario se sincroniza con OneDrive ou outro servizo na nube, ese servizo copiará tamén estes ficheiros: faino o sistema, non a aplicación, e o rexistro, a auditoría e as revisións pendentes viaxan cifrados (a clave non está nese cartafol).

Se o usuario usaba unha versión anterior do programa instalada co instalador clásico, a primeira vez **cópiase** o seu rexistro dende `%LOCALAPPDATA%\Anonimizador` a `Documentos\Anonimizador`; o orixinal non se toca.

Estes datos **non se borran ao desinstalar** a aplicación, adrede: sen o rexistro e a súa clave xa non se podería saber a quen corresponde cada código dos documentos anonimizados. Para eliminalos, o usuario pode borrar o cartafol `Documentos\Anonimizador` e, no Administrador de credenciais de Windows (Credenciais de Windows), as entradas que levan «anonimizador-xuridico» no nome. Feito isto, a anonimización dos documentos xa xerados non se poderá reverter.

## Recuperación de identidades (reversión controlada)

Recuperar a identidade real detrás dun código, ou ver o listado completo dun rexistro, esixe un contrasinal de reversión definido polo usuario e un motivo obrigatorio, e queda anotado na auditoría cifrada xunto co usuario de Windows e a data. Todo iso ocorre no ordenador do usuario; o desenvolvedor non ten acceso ao rexistro, á clave nin ao contrasinal, e non pode recuperalos.

## Responsabilidade sobre os datos dos documentos

Os documentos que se procesan poden conter datos persoais de terceiros. **O usuario (ou a organización para a que traballa) é o responsable do tratamento** deses datos conforme ao Regulamento (UE) 2016/679 (RXPD) e á Lei orgánica 3/2018 (LOPDGDD): decide que documentos procesa, con que finalidade, quen accede ao rexistro e aos documentos, e canto tempo os conserva. O desenvolvedor non accede a eses datos nin os trata por conta de ninguén.

Mentres se conserve o rexistro, os documentos resultantes están **seudonimizados** (art. 4.5 RXPD), non anonimizados de forma irreversible, e seguen sendo datos persoais para quen teña acceso ao rexistro. Ademais, ningún sistema automático detecta todos os datos persoais dun documento real: a aplicación avisa de posibles fugas e de riscos de reidentificación, pero a revisión final correspóndelle ao usuario.

## Menores

A aplicación é unha ferramenta profesional para documentos xurídicos e non está dirixida a menores. Non recolle datos de ninguén.

## Cambios

Calquera cambio desta política publicarase nesta mesma dirección, coa súa data. Se unha versión futura engadise algunha función que se conecte a internet, esta política actualizarase antes de publicala, indicando que se envía, a quen e cando.
