# Escondites de datos nos formatos novos (fase 4)

Estes lectores só valen no modo **sen anonimizar**. No modo anonimizado rexéitanse
(`formatos.EXTENSIONS_SO_SEN_ANONIMIZAR`) ata que cada formato teña os seus tests de fuga (punto 6 do
estudo). Este documento fixa dúas cousas:

1. **Que le hoxe o modo sen anonimizar** (decisión: o que ve a persoa ao abrir o arquivo, máis os
   comentarios; nunca metadatos).
2. **A lista de escondites** que deberán cubrir os tests de fuga: sitios onde un arquivo garda datos
   persoais que NON están no texto que ve a persoa. Para anonimizar, cada un hai que (a) detectalo e
   anonimizalo, ou (b) borralo do arquivo de saída, ou (c) non lelo e avisalo.

Criterio do modo sen anonimizar: o texto que a persoa ve vai ao `.md` (a IA recibe o que a persoa
leria). O que está agochado -- follas, filas, columnas, diapositivas agochadas -- queda fóra **e
avísase** (`Conversion.avisos`), porque case sempre é material descartado, e porque un `.md` non ten
forma de marcar "isto estaba agochado". Os metadatos do arquivo non son contido e non se len.

## .xlsx

| Escondite | Modo sen anonimizar | Para o modo anonimizado |
|---|---|---|
| Follas agochadas e «moi agochadas» (`sheet_state`) | Fóra, con aviso | Anonimizar (ou borrar) tamén as follas agochadas do arquivo de saída |
| Filas e columnas agochadas (incluídas as agochadas por un filtro) | Fóra, con aviso | Idem |
| Comentarios das celas (notas) | **Entran**, sen autor | Anonimizar o texto; o autor do comentario é un nome: borralo |
| Comentarios «con fíos» (threaded, `xl/threadedComments`) e a lista de persoas (`persons`) | Non se len | Hai que borrar a lista de persoas e anonimizar os fíos |
| Metadatos do documento (`docProps/core.xml`: creador, último en modificar, título, asunto, palabras clave, descrición; `app.xml`: empresa, xestor) | Non se len | Borrar |
| Nomes definidos (`definedNames`) e rangos con nome | Non se len | Revisar: poden levar texto |
| Texto de gráficos (títulos, series, categorías) e caixas de texto / formas (`drawings`) | Non se len | Anonimizar |
| Ligazóns (`hyperlink`, fórmula `HYPERLINK`), con URL que pode levar un nome ou un correo | **Entran** as `http(s)` e `mailto:` coma `[texto](url)`; as internas non | Anonimizar o URL (ou deixar só o texto) |
| Validacións de datos (listas desplegables, mensaxes) | Non se len | Revisar |
| Cabeceiras e pés de impresión (`headerFooter`) | Non se len | Anonimizar |
| Fórmulas con texto literal (`="Ana Pena"`) | Entra o valor gardado | Anonimizar o valor **e** a fórmula do arquivo de saída |
| Follas con protección sen contrasinal, comentarios de cambios (`revisions`) | Non se len | Revisar |
| Imaxes incrustadas (DNI escaneado, firma) | Non se len | OCR ou borrar |
| Datos externos / ligazóns a outros libros (`externalLinks`) | Non se len | Revisar: rutas con nome de usuario (`C:\Users\Ana...`) |
| Cor e estilo das celas; o formato dos números SI se aplica (millares, decimais, moeda, `%`, ceros á esquerda) | Só o formato numérico | — |

## .ods

| Escondite | Modo sen anonimizar | Para o modo anonimizado |
|---|---|---|
| Follas agochadas (estilo con `table:display="false"`) | Fóra, con aviso | Idem .xlsx |
| Filas e columnas agochadas ou filtradas (`table:visibility`) | Fóra, con aviso | Idem |
| Anotacións das celas (`office:annotation`) | **Entran**, sen autor nin data | Anonimizar o texto; borrar `dc:creator` e `dc:date` |
| `meta.xml` (creador inicial, creador, datas, palabras clave, xerador) | Non se le | Borrar |
| Texto de formas e gráficos (`draw:*`, `chart`) | Non se le | Anonimizar |
| Ligazóns (`text:a`) | **Entran** as `http(s)` e `mailto:` coma `[texto](url)`; as internas non | Anonimizar o URL (ou deixar só o texto) |
| Rexistro de cambios (`text:tracked-changes`) | Non se le | Borrar / aceptar cambios, como no .docx |
| Imaxes incrustadas (`Pictures/`) e miniatura (`Thumbnails/thumbnail.png`: imaxe da primeira folla) | Non se len | Borrar a miniatura; OCR ou borrar as imaxes |
| Estilos con nomes, `settings.xml` (último cursor, impresora, usuario) | Non se len | Revisar |

## .csv

Non ten escondites: é texto. Só a codificación (`utf-8`, `cp1252`, `latin-1`) e o delimitador, que
se detectan. Un `.csv` anonimizado debería escribirse de novo con delimitador e codificación coñecidos.

## .pptx

| Escondite | Modo sen anonimizar | Para o modo anonimizado |
|---|---|---|
| Notas do orador (`notesSlides`) | **Entran** | Anonimizar (é onde máis se esquece) |
| Diapositivas agochadas (`show="0"`) | Fóra, con aviso | Anonimizar ou borrar do arquivo de saída |
| Comentarios de revisión (`comments/`, `commentAuthors.xml`, `modernComments`) con nome e iniciais do autor | Non se len | Borrar autores; anonimizar o texto |
| Metadatos (`docProps/core.xml`, `app.xml`: autor, empresa, xestor, título) | Non se len | Borrar |
| Pés, data e número de diapositiva (placeholders) e os do patrón (`slideMasters`, `slideLayouts`: nome do despacho, do autor) | Fóra (os da diapositiva); os do patrón non se len | Anonimizar tamén o patrón e os layouts |
| Texto alternativo das imaxes (`descr`) | **Entra**, salvo que sexa un nome de arquivo | Anonimizar |
| Nomes de arquivo das imaxes (`Pictures/Imaxe_Ana_Pena.jpg`) e das formas (`name="..."`) | Non se len | Revisar: os nomes de forma poden levar texto |
| Imaxes incrustadas (fotos, DNI, capturas) | Marca `[imaxe]` | OCR ou borrar |
| Texto de SmartArt (`diagrams/data*.xml`) e de obxectos incrustados (`embeddings/`: un .xlsx dentro) | Marca `[obxecto non convertido]` | Anonimizar: os `embeddings/` son arquivos completos co seu propio contido e metadatos |
| Texto de gráficos (títulos, series, caches de datos, `charts/` con o seu .xlsx incrustado) | Marca `[gráfico]` | Anonimizar tamén o libro incrustado |
| Ligazóns (`hlinkClick` con URL, nos runs de texto e nas táboas) | **Entran** as `http(s)` e `mailto:` coma `[texto](url)`; a ligazón de toda unha forma non | Anonimizar o URL (ou deixar só o texto) |
| Miniatura (`docProps/thumbnail.jpeg`) | Non se le | Borrar |
| Texto fóra da diapositiva (formas colocadas fóra da área visible) | **Entra** (le todas as formas) | Anonimizar |
| Táboas con celas combinadas (o texto das celas absorbidas) | Entra o texto de cada cela | Anonimizar |

## .odp

| Escondite | Modo sen anonimizar | Para o modo anonimizado |
|---|---|---|
| Notas do orador (`presentation:notes`) | **Entran** | Anonimizar |
| Diapositivas agochadas (estilo da páxina con `presentation:visibility="hidden"`) | Fóra, con aviso | Idem |
| Pés, data e cabeceira (`footer`, `date-time`, `header`, `page-number`) | Fóra | Anonimizar tamén o patrón (`styles.xml`) |
| Anotacións (`office:annotation`) | Non se len | Borrar `dc:creator`; anonimizar o texto |
| `meta.xml` | Non se le | Borrar |
| Imaxes, miniatura (`Thumbnails/thumbnail.png`: imaxe da primeira diapositiva) e obxectos incrustados (`Object N/`) | Marca `[imaxe]` / `[obxecto non convertido]` | Borrar a miniatura; OCR ou borrar |
| Rexistro de cambios | Non se le | Idem .odt |

## .html / .htm

| Escondite | Modo sen anonimizar | Para o modo anonimizado |
|---|---|---|
| Comentarios HTML (`<!-- ... -->`) | Fóra | Borrar |
| `<head>`: `<title>`, `<meta name="author">`, `description`, `keywords`, Open Graph, JSON-LD (`<script type="application/ld+json">`) | Fóra (o `<title>` só entra como `# título` se a páxina non ten `<h1>`) | Anonimizar o título; borrar o resto |
| Scripts, estilos, `<noscript>`, `<template>`, `<iframe>`, `<svg>`, `<canvas>` | Fóra | Borrar |
| Elementos agochados (`hidden`, `style="display:none"`, `visibility:hidden`, `<input type=hidden>`) | Fóra | Borrar |
| Atributos: `title`, `alt`, `data-*`, `aria-label`, `value`, `placeholder`, `id`/`class` con texto | `alt` das imaxes entra (salvo nome de arquivo); o resto fóra | Anonimizar `alt`; borrar o resto |
| URL das ligazóns e das imaxes (poden levar nomes, correos, ids: `?nome=Ana`, `mailto:`) | As ligazóns `http(s)` e `mailto:` **entran** coma `[texto](url)`; as das imaxes non | Anonimizar o URL (ou deixar só o texto) |
| Imaxes en base64 (`data:image/...`) | Fóra | OCR ou borrar |
| Formularios (valores xa escritos en `<input>`, `<textarea>`, `<select>`) | Fóra | Idem (aquí poden estar os datos da persoa) |
| Menús, cabeceiras e pés (`nav`, `aside`, `header`, `footer`, `role=navigation/banner/contentinfo`) e contedores con clase `menu`, `sidebar`... | Fóra | Idem |
| Elementos concretos do BOE e do DOG: botón de audio (`rs_skip`/`rsbtn`), ligazón «Subir» (`linkSubir`), selector de apartados da lei consolidada (`marcadores`), menús e pés do sumario | Fóra | Idem |
| Codificación (`<meta charset>`) | Detéctase | — |

## Nota para o motor

- Todos entran sen anonimizar con `formatos.a_markdown(ruta)` / `formatos.convertir(ruta)`; os avisos
  (`Conversion.avisos`) hai que amosalos á persoa: neles vai o que se deixou fóra.
- En modo anonimizado: rexeitar `formatos.EXTENSIONS_SO_SEN_ANONIMIZAR` cun aviso, igual que o `.zip` deixa
  fóra o que non sabe revisar.
- Follas grandes: pasar `dir_csv` (cartafol de saída) se se quere o `.csv` á parte; sen el a táboa sae
  enteira e só se avisa.
