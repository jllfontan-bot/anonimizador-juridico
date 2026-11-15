# Condiciones de uso — Reductor de tokens

*[Versión en galego más abajo.](#condicións-de-uso--reductor-de-tokens)*

**Última actualización:** 15 de noviembre de 2026
**Desarrollador:** José Luis López Fontán (desarrollador particular). Aplicación gratuita, sin ánimo de lucro.
**Contacto:** jllfontan@gmail.com

## 1. Licencia

Reductor de tokens es software libre con **doble licencia**, a elección de quien lo recibe: **Licencia Pública de la Unión Europea (EUPL) v1.2** (https://interoperable-europe.ec.europa.eu/collection/eupl/eupl-text-eupl-12) o **GNU Affero General Public License v3.0** (AGPL-3.0, https://www.gnu.org/licenses/agpl-3.0.html). El paquete de la Microsoft Store lleva dentro componentes de terceros con licencia AGPL-3.0 (PyMuPDF) y GPL-3.0 (el modelo de idioma), así que el paquete completo se distribuye con la AGPL-3.0, una de las dos licencias del programa; cada componente de terceros conserva su propia licencia (relación en el archivo AVISOS-TERCEIROS.md, dentro del paquete). Estas condiciones no limitan ninguno de los derechos que dan esas licencias (usar, estudiar, modificar y redistribuir el programa). Explican para qué sirve el programa, cómo debe usarse y qué corresponde a cada parte. Si algo de lo que aquí se dice contradijera la licencia aplicable, prevalece la licencia.

## 2. Sin garantía

El programa se ofrece gratis y «tal cual», sin garantía de ningún tipo, en los términos de los artículos 7 y 8 de la EUPL y de los apartados 15 y 16 de la AGPL-3.0, y en la medida en que lo permita la ley aplicable.

## 3. Es una herramienta de apoyo: la revisión final es del usuario

La conversión a Markdown es automática: puede perder o alterar parte del contenido (tablas complejas, texto reconocido por OCR, cabeceras y pies que quita la opción «Ahorro para IA») y no convierte lo que el documento guarda fuera del texto visible (metadatos, algunos comentarios, objetos incrustados). Antes de basarse en un `.md`, el usuario debe comprobar que recoge lo que necesita del original.

En el modo anonimizado, la detección de datos personales es automática y **no garantiza encontrar todos los datos de un documento real**: puede dejar alguno sin tapar o tapar algo que no es un dato personal. Las hojas de cálculo, presentaciones, páginas web y correos solo se convierten sin anonimizar. Por eso, antes de pasar a otra persona o a un servicio en línea un `.md` anonimizado, el usuario debe:

- revisarlo, preferiblemente con el modo «Revisar cada documento antes de guardarlo»;
- si ha usado el modo automático, tener en cuenta que los `.md` se guardan sin revisión humana (llevan «revisado: no») y revisarlos todos, empezando por los que el resumen final lista como «Documentos con posibles fugas»: que un documento no esté en esa lista no significa que no conserve ningún dato;
- comprobar los avisos de posibles fugas, de efecto mosaico y de datos de categoría especial, que el programa no corrige por sí solo;
- comprobar las personas que el programa deja sin anonimizar por su cargo público (jueces, magistrados, letrados de la Administración de Justicia y médicos forenses en el ejercicio de su función), porque esa exención se detecta automáticamente y puede equivocarse;
- comprobar los nombres de los archivos y carpetas de salida, porque en ellos solo se tapan las personas que el programa haya detectado.

## 4. No es asesoramiento jurídico

El programa no presta asesoramiento jurídico. Decidir en qué modo se convierte cada documento, qué datos hay que suprimir y si el resultado es suficiente para una finalidad concreta (pasarlo a un servicio de inteligencia artificial, publicarlo, aportarlo a un procedimiento, cederlo a terceros, usarlo para formación o investigación…) corresponde al usuario y, en su caso, a quien le asesore.

## 5. Protección de datos

El programa funciona solo en el ordenador del usuario: el desarrollador no recibe, no ve y no trata ningún documento ni ningún dato (ver la política de privacidad). **El usuario, o la organización para la que trabaja, es el responsable del tratamiento** de los datos personales que contienen los documentos que convierte, los `.md` resultantes y el registro de correspondencias, conforme al Reglamento (UE) 2016/679 (RGPD) y a la Ley Orgánica 3/2018 (LOPDGDD). También le corresponde cumplir los deberes de secreto profesional que le afecten.

En el modo sin anonimizar, el `.md` conserva todos los datos personales del original.

Pasar un `.md` a un servicio en línea, por ejemplo de inteligencia artificial, es una comunicación de datos que decide y hace el usuario fuera del programa. Antes de hacerlo, le corresponde comprobar que es lícita: que tiene base jurídica para ello; que el proveedor ofrece las garantías que exige el RGPD (en su caso, un contrato de encargado del tratamiento conforme al art. 28 y, si los datos salen del Espacio Económico Europeo, las garantías del capítulo V); y que no vulnera el secreto profesional ni las condiciones de ese servicio.

Mientras se conserve el registro de correspondencias, los `.md` anonimizados están **seudonimizados** (art. 4.5 RGPD), no anonimizados de forma irreversible: siguen siendo datos personales para quien pueda acceder al registro, también cuando se pasan a un servicio en línea.

## 6. Custodia del registro, de la clave y de los `.md`

El modo anonimizado guarda el registro de correspondencias y su clave de cifrado en este ordenador (en la carpeta Documentos\Anonimizador y en el Administrador de credenciales de Windows), y otra aplicación del mismo desarrollador instalada en el equipo puede compartirlos. Quien tenga a la vez el registro y su clave puede reidentificar a todas las personas de los `.md` anonimizados. Corresponde al usuario:

- controlar quién accede al ordenador, a la carpeta del registro y al Administrador de credenciales de Windows;
- hacer copias de seguridad del registro y guardarlas de forma segura;
- custodiar los `.md` sin anonimizar con el mismo cuidado que los documentos originales, y borrarlos cuando ya no hagan falta.

El Reductor de tokens no revierte la anonimización: no muestra qué persona hay detrás de cada código. Si se pierden el registro o su clave, ya no se puede saber a quién corresponde cada código. El desarrollador no tiene copia de ninguno de ellos y no puede recuperarlos.

## 7. Responsabilidad

En la medida en que lo permita la ley aplicable, el desarrollador no responde de los daños derivados del uso del programa o de la imposibilidad de usarlo. Esto incluye los errores u omisiones de la conversión, los datos personales que el programa no haya detectado, el uso que se haga de los `.md` en servicios de terceros, las decisiones tomadas con sus resultados y la pérdida del registro o de su clave. Esta limitación no se aplica a lo que la ley no permita excluir.

## 8. Cambios

Cualquier cambio de estas condiciones se publicará en esta misma dirección, con su fecha.

---

# Condicións de uso — Reductor de tokens

**Última actualización:** 15 de novembro de 2026
**Desenvolvedor:** José Luis López Fontán (desenvolvedor particular). Aplicación gratuíta, sen ánimo de lucro.
**Contacto:** jllfontan@gmail.com

## 1. Licenza

Reductor de tokens é software libre con **dobre licenza**, á escolla de quen o recibe: **Licenza Pública da Unión Europea (EUPL) v1.2** (https://interoperable-europe.ec.europa.eu/collection/eupl/eupl-text-eupl-12) ou **GNU Affero General Public License v3.0** (AGPL-3.0, https://www.gnu.org/licenses/agpl-3.0.html). O paquete da Microsoft Store leva dentro compoñentes de terceiros con licenza AGPL-3.0 (PyMuPDF) e GPL-3.0 (o modelo de idioma), así que o paquete completo distribúese coa AGPL-3.0, unha das dúas licenzas do programa; cada compoñente de terceiros conserva a súa propia licenza (relación no ficheiro AVISOS-TERCEIROS.md, dentro do paquete). Estas condicións non limitan ningún dos dereitos que dan esas licenzas (usar, estudar, modificar e redistribuír o programa). Explican para que serve o programa, como debe usarse e que lle corresponde a cada parte. Se algo do que aquí se di contradixese a licenza aplicable, prevalece a licenza.

## 2. Sen garantía

O programa ofrécese gratis e «tal cal», sen garantía de ningún tipo, nos termos dos artigos 7 e 8 da EUPL e dos apartados 15 e 16 da AGPL-3.0, e na medida en que o permita a lei aplicable.

## 3. É unha ferramenta de apoio: a revisión final é do usuario

A conversión a Markdown é automática: pode perder ou alterar parte do contido (táboas complexas, texto recoñecido por OCR, cabeceiras e pés que quita a opción «Aforro para IA») e non converte o que o documento garda fóra do texto visible (metadatos, algúns comentarios, obxectos incrustados). Antes de basearse nun `.md`, o usuario debe comprobar que recolle o que precisa do orixinal.

No modo anonimizado, a detección de datos persoais é automática e **non garante atopar todos os datos dun documento real**: pode deixar algún sen tapar ou tapar algo que non é un dato persoal. As follas de cálculo, presentacións, páxinas web e correos só se converten sen anonimizar. Por iso, antes de lle pasar a outra persoa ou a un servizo en liña un `.md` anonimizado, o usuario debe:

- revisalo, preferiblemente co modo «Revisar cada documento antes de gardalo»;
- se usou o modo automático, ter en conta que os `.md` se gardan sen revisión humana (levan «revisado: non») e revisalos todos, comezando polos que o resumo final lista como «Documentos con posibles fugas»: que un documento non estea nesa lista non significa que non conserve ningún dato;
- comprobar os avisos de posibles fugas, de efecto mosaico e de datos de categoría especial, que o programa non corrixe por si só;
- comprobar as persoas que o programa deixa sen anonimizar polo seu cargo público (xuíces, maxistrados, letrados da Administración de Xustiza e médicos forenses no exercicio da súa función), porque esa exención se detecta automaticamente e pode equivocarse;
- comprobar os nomes dos ficheiros e cartafoles de saída, porque neles só se tapan as persoas que o programa detectase.

## 4. Non é asesoramento xurídico

O programa non presta asesoramento xurídico. Decidir en que modo se converte cada documento, que datos hai que suprimir e se o resultado é suficiente para unha finalidade concreta (pasarllo a un servizo de intelixencia artificial, publicalo, achegalo a un procedemento, cedelo a terceiros, usalo para formación ou investigación…) correspóndelle ao usuario e, de ser o caso, a quen o asesore.

## 5. Protección de datos

O programa funciona só no ordenador do usuario: o desenvolvedor non recibe, non ve e non trata ningún documento nin ningún dato (ver a política de privacidade). **O usuario, ou a organización para a que traballa, é o responsable do tratamento** dos datos persoais que conteñen os documentos que converte, os `.md` resultantes e o rexistro de correspondencias, conforme ao Regulamento (UE) 2016/679 (RXPD) e á Lei orgánica 3/2018 (LOPDGDD). Tamén lle corresponde cumprir os deberes de segredo profesional que o afecten.

No modo sen anonimizar, o `.md` conserva todos os datos persoais do orixinal.

Pasarlle un `.md` a un servizo en liña, por exemplo de intelixencia artificial, é unha comunicación de datos que decide e fai o usuario fóra do programa. Antes de facelo, correspóndelle comprobar que é lícita: que ten base xurídica para iso; que o provedor ofrece as garantías que esixe o RXPD (de ser o caso, un contrato de encargado do tratamento conforme ao art. 28 e, se os datos saen do Espazo Económico Europeo, as garantías do capítulo V); e que non vulnera o segredo profesional nin as condicións dese servizo.

Mentres se conserve o rexistro de correspondencias, os `.md` anonimizados están **seudonimizados** (art. 4.5 RXPD), non anonimizados de forma irreversible: seguen sendo datos persoais para quen poida acceder ao rexistro, tamén cando se lle pasan a un servizo en liña.

## 6. Custodia do rexistro, da clave e dos `.md`

O modo anonimizado garda o rexistro de correspondencias e a súa clave de cifrado neste ordenador (no cartafol Documentos\Anonimizador e no Administrador de credenciais de Windows), e outra aplicación do mesmo desenvolvedor instalada no equipo pode compartilos. Quen teña á vez o rexistro e a súa clave pode reidentificar todas as persoas dos `.md` anonimizados. Correspóndelle ao usuario:

- controlar quen accede ao ordenador, ao cartafol do rexistro e ao Administrador de credenciais de Windows;
- facer copias de seguridade do rexistro e gardalas de forma segura;
- custodiar os `.md` sen anonimizar co mesmo coidado ca os documentos orixinais, e borralos cando xa non fagan falta.

O Reductor de tokens non reverte a anonimización: non amosa que persoa hai detrás de cada código. Se se perden o rexistro ou a súa clave, xa non se pode saber a quen corresponde cada código. O desenvolvedor non ten copia de ningún deles e non pode recuperalos.

## 7. Responsabilidade

Na medida en que o permita a lei aplicable, o desenvolvedor non responde dos danos derivados do uso do programa ou da imposibilidade de usalo. Isto inclúe os erros ou omisións da conversión, os datos persoais que o programa non detectase, o uso que se faga dos `.md` en servizos de terceiros, as decisións tomadas cos seus resultados e a perda do rexistro ou da súa clave. Esta limitación non se aplica ao que a lei non permita excluír.

## 8. Cambios

Calquera cambio destas condicións publicarase nesta mesma dirección, coa súa data.
