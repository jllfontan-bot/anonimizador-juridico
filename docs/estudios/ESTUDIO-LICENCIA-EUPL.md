# Estudio: ¿pasar el Anonimizador jurídico a la licencia EUPL 1.2?

**Fecha:** 25/10/2026 (corregido el mismo día). **Estado:** estudio, sin cambios en ningún
repositorio. No es asesoramiento jurídico: los puntos marcados ⚖️ conviene confirmarlos con
un abogado especialista en propiedad intelectual.

> **Corrección:** la primera versión de este estudio partía de este repositorio privado
> (`anonimizador-xuridico`, sin licencia). La versión publicada es otra:
> `~/proyectos/anonimizador-xuridico-publico`, en GitHub `jllfontan-bot/anonimizador-juridico`
> (**público, AGPL-3.0**, historial nuevo desde el 15/10/2026, con `AVISOS-TERCEIROS.md`), y es
> la que está en la Microsoft Store (ID 9PK1J429MNN5). La licencia libre y la limpieza de
> nombres **ya se hicieron allí**. La pregunta es, por tanto, si conviene **cambiar o añadir**
> la EUPL 1.2.

## 1. Situación actual (repositorio público)

- Licencia **AGPL-3.0** (`LICENSE`), con avisos de cada componente en `AVISOS-TERCEIROS.md`.
- Las condiciones de uso de la Store (`docs/store/condiciones-de-uso.md`) remiten a la AGPL-3.0.
- **Los 32 commits son tuyos** (José Luis López Fontán). Como no hay código de terceros
  mezclado, puedes cambiar o ampliar la licencia de las versiones futuras sin pedir permiso a
  nadie. ⚖️ (Ver también el punto 5 sobre el código escrito con ayuda de IA.)
- Lo ya publicado con AGPL-3.0 **sigue con AGPL-3.0** para quien lo recibió: un cambio de
  licencia solo vale de esa versión en adelante.

## 2. Por qué la AGPL encaja hoy

El programa usa **PyMuPDF (AGPL-3.0)** y el **modelo `es_core_news_md` (GPL-3.0)**, y los dos
van dentro del paquete MSIX de la Store. Según la lectura de la AGPL (Artifex, FSF), el paquete
completo es una obra combinada que tiene que cumplir la AGPL. Con la AGPL para todo, la licencia
es **una sola y coherente** de principio a fin.

## 3. Qué cambiaría con la EUPL 1.2

**Ventajas**
- Tiene **texto oficial en castellano** y está pensada para el derecho europeo: se aplica la
  ley del país de quien la concede y fija el tribunal competente.
- El **Esquema Nacional de Interoperabilidad** (Real Decreto 4/2010, art. 16.3) dice que
  «se procurará» aplicar la EUPL al software de fuentes abiertas de las Administraciones.
  Ayuda si el programa acaba en un juzgado o en una Administración. (Se consultó en el texto
  consolidado del BOE en la sesión del Transcriptor.)
- Protege igual contra la apropiación (art. 16.1.b del mismo Real Decreto): copyleft y
  cláusula de uso en red, como la AGPL.

**Inconvenientes**
- **El paquete de la Store seguiría siendo, en la práctica, AGPL.** La EUPL permite combinar
  el código con obras AGPL y distribuir el conjunto con la AGPL (art. 5 y anexo de
  compatibles), y eso es justo lo que pasa con PyMuPDF dentro del MSIX. Se tendría código EUPL
  y paquete AGPL: dos licencias que explicar en vez de una.
- Hay que cambiar `LICENSE`, las cabeceras, `AVISOS-TERCEIROS.md`, las condiciones de uso de la
  Store (en castellano y gallego), el README y el PDF 01, y publicar una versión nueva.
- La FSF considera la EUPL 1.2 incompatible con la GPL «o cualquier versión posterior», porque
  el anexo nombra versiones concretas. No afecta a este programa, pero se cita a veces como
  inconveniente.

## 4. Opciones

| Opción | Qué supone | Valoración |
|---|---|---|
| **A. Seguir con AGPL-3.0** | Nada que cambiar | **La más sencilla y coherente con PyMuPDF** |
| **B. Doble licencia «EUPL-1.2 o AGPL-3.0»** para tu código | Quien lo reciba elige; las Administraciones pueden quedarse con la EUPL. El paquete de la Store se sigue distribuyendo con la AGPL | Buena si se quiere facilitar el uso en Administraciones sin romper nada |
| C. Solo EUPL-1.2 | Código EUPL y paquete combinado con AGPL | Más trabajo que la B y sin ventaja clara sobre ella |

**Recomendación:** la **A** mientras no haya una Administración interesada. Si la hay, la
**B**: añade la EUPL sin quitar la AGPL, de modo que nada de lo publicado entra en
contradicción. ⚖️

## 5. Titularidad ⚖️

Gran parte del código se ha escrito con ayuda de IA. En la UE, la protección por derechos de
autor exige creación intelectual humana; la dirección, selección y revisión humanas cuentan,
pero es una zona todavía poco definida. No impide licenciar; conviene saberlo.

## Fuentes

- [Texto oficial EUPL v1.2 (Interoperable Europe)](https://interoperable-europe.ec.europa.eu/sites/default/files/distribution/access_url/2025-06/79193bac-a3a9-4a5b-8159-94694cb5b8fa/EUPL%20v1.2.pdf)
- [Preguntas frecuentes de la EUPL (Interoperable Europe)](https://interoperable-europe.ec.europa.eu/collection/eupl/faqs)
- [EUPL overview 2020 (Comisión Europea)](https://interoperable-europe.ec.europa.eu/sites/default/files/news/2020-12/EUPL%20overview%202020.pdf)
- [Rationale for the EUPL v1.2 (Joinup)](https://joinup.ec.europa.eu/sites/default/files/document/2014-02/Rationale%20for%20the%20EUPL%20v1.2.%20v06.pdf)
- [European Union Public Licence (Wikipedia)](https://en.wikipedia.org/wiki/European_Union_Public_Licence)
