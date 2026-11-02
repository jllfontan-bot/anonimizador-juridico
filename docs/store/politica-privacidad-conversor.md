# Política de privacidad — Reductor de tokens (aplicación de escritorio)

*[Versión en galego más abajo.](#política-de-privacidade--conversor-de-archivos-para-ia-aplicación-de-escritorio)*

**Última actualización:** 31 de octubre de 2026
**Desarrollador:** José Luis López Fontán (desarrollador particular). Aplicación gratuita y de código abierto (EUPL-1.2 o AGPL-3.0), sin ánimo de lucro.
**Contacto:** jllfontan@gmail.com

## Resumen

La aplicación **no recoge, no envía y no vende datos personales**. No tiene cuentas de usuario, ni publicidad, ni analítica, ni telemetría, no se conecta a internet y no abre ningún puerto en el ordenador. El desarrollador no recibe ningún dato de quien la usa ni de los documentos que convierte.

## Qué hace la aplicación

Convierte a Markdown (`.md`) los documentos que el usuario elige, con o sin anonimizarlos. Todo el proceso se hace **en el propio ordenador del usuario**:

- La lectura de los documentos, el reconocimiento de texto (OCR) y, en el modo anonimizado, la detección de datos personales funcionan sin conexión: todo lo necesario va dentro del paquete instalado.
- La interfaz es una ventana propia del programa (componente Microsoft Edge WebView2 de Windows) que llama directamente al programa, **sin servidor**: no hay ningún puerto abierto al que pueda conectarse otro programa o equipo.
- La aplicación no envía a internet ni los documentos, ni su contenido, ni los `.md` resultantes, ni ningún otro dato.
- Lo único que se abre fuera del programa es el enlace al código fuente de la página «Acerca de», en el navegador del usuario y solo si lo pulsa, y el manual de uso (un PDF del propio paquete), en el visor de PDF del sistema.

## Los .md sin anonimizar

En el modo **sin anonimizar**, el `.md` conserva los datos personales del documento original, y el programa lo avisa. Si el usuario pasa ese `.md` a un servicio de inteligencia artificial en línea, los datos salen del equipo hacia ese servicio: lo decide y lo hace el usuario, fuera de esta aplicación, y se rige por las condiciones de ese servicio.

## Qué se guarda en el ordenador

La aplicación lee únicamente los archivos, carpetas y `.zip` que el usuario le indica y guarda:

- **Los `.md`**, junto al original o en la carpeta de salida que elija el usuario. El documento original nunca se modifica ni se borra.
- En la carpeta **`Documentos\Anonimizador`** del usuario, la misma que usa el Anonimizador jurídico:
  - `preferencias.json`: el idioma elegido y si el modo anonimizado revisa cada documento o es automático.
  - Solo si se usa el modo anonimizado, `datos_rexistro`: el **registro de correspondencias** entre cada código y la persona real y su **auditoría**, **cifrados**, compartidos con el Anonimizador jurídico para que una persona reciba el mismo código en los dos programas.
- La **clave de cifrado** del registro, en el **Administrador de credenciales de Windows**, separada de lo que cifra.

Si la carpeta Documentos del usuario se sincroniza con OneDrive u otro servicio en la nube, ese servicio copiará también estos archivos: lo hace el sistema, no la aplicación, y el registro viaja cifrado (la clave no está en esa carpeta).

Estos datos **no se borran al desinstalar** la aplicación, a propósito: el registro lo usa también el Anonimizador jurídico, y sin él ya no se podría saber a quién corresponde cada código. Para eliminarlos, el usuario puede borrar la carpeta `Documentos\Anonimizador` y, en el Administrador de credenciales de Windows (Credenciales de Windows), las entradas que llevan «anonimizador-xuridico» en el nombre.

## Responsabilidad sobre los datos de los documentos

Los documentos que se convierten pueden contener datos personales de terceros. **El usuario (o la organización para la que trabaja) es el responsable del tratamiento** de esos datos conforme al Reglamento (UE) 2016/679 (RGPD) y a la Ley Orgánica 3/2018 (LOPDGDD): decide qué documentos convierte, en qué modo, a quién pasa los `.md` y cuánto tiempo los conserva. El desarrollador no accede a esos datos ni los trata por cuenta de nadie.

En el modo anonimizado, mientras se conserve el registro, los `.md` están **seudonimizados** (art. 4.5 RGPD), no anonimizados de forma irreversible. Además, ningún sistema automático detecta todos los datos personales de un documento real: la revisión final corresponde al usuario.

## Menores

La aplicación es una herramienta profesional y no está dirigida a menores. No recoge datos de nadie.

## Cambios

Cualquier cambio de esta política se publicará en esta misma dirección, con su fecha. Si una versión futura añadiera alguna función que se conecte a internet, esta política se actualizará antes de publicarla, indicando qué se envía, a quién y cuándo.

---

# Política de privacidade — Reductor de tokens (aplicación de escritorio)

**Última actualización:** 31 de outubro de 2026
**Desenvolvedor:** José Luis López Fontán (desenvolvedor particular). Aplicación gratuíta e de código aberto (EUPL-1.2 ou AGPL-3.0), sen ánimo de lucro.
**Contacto:** jllfontan@gmail.com

## Resumo

A aplicación **non recolle, non envía e non vende datos persoais**. Non ten contas de usuario, nin publicidade, nin analítica, nin telemetría, non se conecta a internet e non abre ningún porto no ordenador. O desenvolvedor non recibe ningún dato de quen a usa nin dos documentos que converte.

## Que fai a aplicación

Converte a Markdown (`.md`) os documentos que o usuario escolle, con ou sen anonimizalos. Todo o proceso faise **no propio ordenador do usuario**:

- A lectura dos documentos, o recoñecemento de texto (OCR) e, no modo anonimizado, a detección de datos persoais funcionan sen conexión: todo o necesario vai dentro do paquete instalado.
- A interface é unha xanela propia do programa (compoñente Microsoft Edge WebView2 de Windows) que chama directamente ao programa, **sen servidor**: non hai ningún porto aberto ao que se poida conectar outro programa ou equipo.
- A aplicación non envía a internet nin os documentos, nin o seu contido, nin os `.md` resultantes, nin ningún outro dato.
- O único que se abre fóra do programa é a ligazón ao código fonte da páxina «Acerca de», no navegador do usuario e só se a preme, e o manual de uso (un PDF do propio paquete), no visor de PDF do sistema.

## Os .md sen anonimizar

No modo **sen anonimizar**, o `.md` conserva os datos persoais do documento orixinal, e o programa avísao. Se o usuario pasa ese `.md` a un servizo de intelixencia artificial en liña, os datos saen do equipo cara a ese servizo: decídeo e faino o usuario, fóra desta aplicación, e réxese polas condicións dese servizo.

## Que se garda no ordenador

A aplicación le unicamente os ficheiros, cartafoles e `.zip` que o usuario lle indica e garda:

- **Os `.md`**, canda o orixinal ou no cartafol de saída que escolla o usuario. O documento orixinal nunca se modifica nin se borra.
- No cartafol **`Documentos\Anonimizador`** do usuario, o mesmo que usa o Anonimizador jurídico:
  - `preferencias.json`: o idioma escollido e se o modo anonimizado revisa cada documento ou é automático.
  - Só se se usa o modo anonimizado, `datos_rexistro`: o **rexistro de correspondencias** entre cada código e a persoa real e a súa **auditoría**, **cifrados**, compartidos co Anonimizador jurídico para que unha persoa reciba o mesmo código nos dous programas.
- A **clave de cifrado** do rexistro, no **Administrador de credenciais de Windows**, separada do que cifra.

Se o cartafol Documentos do usuario se sincroniza con OneDrive ou outro servizo na nube, ese servizo copiará tamén estes ficheiros: faino o sistema, non a aplicación, e o rexistro viaxa cifrado (a clave non está nese cartafol).

Estes datos **non se borran ao desinstalar** a aplicación, a propósito: o rexistro úsao tamén o Anonimizador jurídico, e sen el xa non se podería saber a quen corresponde cada código. Para eliminalos, o usuario pode borrar o cartafol `Documentos\Anonimizador` e, no Administrador de credenciais de Windows (Credenciais de Windows), as entradas que levan «anonimizador-xuridico» no nome.

## Responsabilidade sobre os datos dos documentos

Os documentos que se converten poden conter datos persoais de terceiros. **O usuario (ou a organización para a que traballa) é o responsable do tratamento** deses datos conforme ao Regulamento (UE) 2016/679 (RXPD) e á Lei orgánica 3/2018 (LOPDGDD): decide que documentos converte, en que modo, a quen pasa os `.md` e canto tempo os conserva. O desenvolvedor non accede a eses datos nin os trata por conta de ninguén.

No modo anonimizado, mentres se conserve o rexistro, os `.md` están **seudonimizados** (art. 4.5 RXPD), non anonimizados de forma irreversible. Ademais, ningún sistema automático detecta todos os datos persoais dun documento real: a revisión final correspóndelle ao usuario.

## Menores

A aplicación é unha ferramenta profesional e non está dirixida a menores. Non recolle datos de ninguén.

## Cambios

Calquera cambio desta política publicarase neste mesmo enderezo, coa súa data. Se unha versión futura engadise algunha función que se conecte a internet, esta política actualizarase antes de publicala, indicando que se envía, a quen e cando.
