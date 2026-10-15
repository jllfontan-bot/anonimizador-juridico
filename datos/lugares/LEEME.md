# Listas oficiais de lugares (INE e Nomenclátor de Galicia)

Fonte da táboa `src/anonimizador/datos/lugares_oficiais.tsv`, que usa `lugares_oficiais.py` e
`ner._e_lugar_oficial` para NON tapar coma persoa un topónimo (Braña, San Clodio, Cartelle,
municipios cataláns...). Descargadas o 04/10/2026 con permiso expreso do usuario.

## Ficheiros orixinais (NON van en git; consérvanse aparte)

| Ficheiro | URL | Tamaño | SHA-256 |
|---|---|---|---|
| `diccionario26.xlsx` | https://www.ine.es/daco/daco42/codmun/diccionario26.xlsx | 306.819 | `07f8e8d64eba73fe9d425196fe82f4e09a9886a287abd650e88ca8d98dd49052` |
| `nomenclator-galicia.csv` | https://abertos.xunta.gal/catalogo/territorio-vivienda-transporte/-/dataset/0270/nomenclator-galicia/001/descarga-directa-ficheiro.csv | 3.605.645 | `f60b0efae7561dcebe2900eeeab371d56ccb025bcf4015d320733846cd18ce7e` |

- INE: Relación de municipios y códigos por comunidades autónomas y provincias, a 1/1/2026
  (8.132 municipios). Licenza **CC BY 4.0**. Cita: "Elaboración propia con datos extraídos del sitio
  web del INE: www.ine.es".
- Xunta de Galicia: Nomenclátor de Galicia (Decreto 27/2026): provincias, concellos, parroquias e
  lugares (nomes oficiais de 2003 e de 2025). Licenza **CC BY-SA 4.0**.

## Licenza da táboa derivada

`lugares_oficiais.tsv` é unha obra derivada do Nomenclátor: **compártese con CC BY-SA 4.0**, citando
as dúas fontes (vai na cabeceira do propio ficheiro). A licenza afecta só a esa táboa, non ao
resto do código do programa.

## Contido

Un nome normalizado por liña (a MESMA normalización que os nomes do INE: maiúsculas, sen acentos,
coa Ñ) e as súas orixes (I municipio do INE, C concello, F parroquia, L lugar, P provincia). Do
"Adro, O" xéranse "O ADRO" e "ADRO"; do "A/B" dos municipios bilingües, cada alternativa. Non se
usa a advocación das parroquias (o santo) nin se filtra nada contra nomes e apelidos: iso vive no
código, con tests.

Rexenerar: poñer os dous ficheiros neste cartafol e executar `python3 datos/lugares/xerar_lugares.py`.
