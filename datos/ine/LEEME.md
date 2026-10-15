# Táboas oficiais de nomes e apelidos (INE)

Fonte das táboas `src/anonimizador/datos/nomes_ine.tsv` e `apelidos_ine.tsv`, que usa o
recoñecedor de persoas por táboa (`ner.py`, `nomes_ine.py`). Descargadas o 28/09/2026 con
permiso expreso do usuario.

## Por que o INE e non o IGE

O IGE (Instituto Galego de Estatística) ten dúas consultas de nomes, pero ningunha servía:
- "Nomes máis frecuentes por concello" (datos a 01/01/2023): só os **25** máis frecuentes de cada
  concello, en HTML, sen ficheiro descargable. Para toda Galicia saen MARIA, MANUEL...; nin Roi
  nin Breixo.
- "Nomes máis frecuentes segundo a década de nacemento": o 28/09/2026 devolvía **erro do
  servidor** ("Produciuse un erro") en calquera consulta, tamén dende o navegador.

O INE publica TODOS os nomes e apelidos con 20 ou máis persoas. É unha lista nacional, pero
abondo detallada para incluír os nomes galegos pouco frecuentes (Ledicia: 112 persoas; Xacobe:
262; Tareixa: 30).

## Ficheiros orixinais (NON van en git: pesan 18 MB; consérvanse aparte)

| Ficheiro | URL | Tamaño | SHA-256 |
|---|---|---|---|
| `nombres_por_edad_media.xlsx` | https://www.ine.es/daco/daco42/nombyapel/nombres_por_edad_media.xlsx | 2.503.760 | `1edb4e05f9ba539efb19205c94d5c1c0d97124f4e99fa5a30163d7b67bab7305` |
| `apellidos_frecuencia.xls` | https://www.ine.es/daco/daco42/nombyapel/apellidos_frecuencia.xls | 14.858.752 | `93e894da8e33332a11725bf07295db5607d64e2d40d3a8d3607fcd42f8f2cf28` |
| `nombres_por_fecha.xlsx` (só referencia: escoller os nomes "galegos" da reserva) | https://www.ine.es/daco/daco42/nombyapel/nombres_por_fecha.xlsx | 547.477 | `4170306134ef4aea163d68285b6e01a1dca3459ad2a88440772ee6fcee619c5d` |

Datos: "Censos de población anuales a fecha 01/01/2025". Última modificación no servidor do INE:
23/04/2026. Páxina: INEbase > Demografía y población > Apellidos y nombres más frecuentes >
Resultados.

## Condicións de reutilización (comprobadas o 28/09/2026 no Aviso legal do INE)

- Licenza **Creative Commons Recoñecemento 4.0 (CC BY 4.0)**: permite copiar, distribuír e
  facer obras derivadas, **tamén con fin comercial** (importa: o programa úsase nun despacho).
- Hai que **citar a fonte**. Como os datos se tratan (filtrado, normalización), a fórmula que
  pide o INE é: "Elaboración propia con datos extraídos del sitio web del INE: www.ine.es".
  Vai na cabeceira de cada `.tsv`.
- Hai que mencionar a **data da última actualización** (01/01/2025; publicada o 23/04/2026).
- Non se pode suxerir que o INE participa, patrocina ou apoia este uso.
- O uso é por conta e risco de quen reutiliza (o INE non responde de danos).
- Só se autoriza reutilizar información cuxa fonte orixinal sexa o propio INE (é o caso).

Do IGE (non usado ao final) anotouse igualmente: permite reutilizar citando "Fonte: IGE:
https://www.ige.gal" e a data de actualización, sen desnaturalizar o sentido da información.

## Contido das táboas xeradas

- Só entradas dunha soa palabra (os nomes compostos, "MARIA DEL CARMEN", xa se cobren pola súa
  primeira palabra). Normalizadas coma o INE: maiúsculas, sen acentos, coa Ñ.
- `nomes_ine.tsv`: 20.857 nomes; frecuencia = homes + mulleres.
- `apelidos_ine.tsv`: 76.900 apelidos; frecuencia = o maior de 1º e 2º apelido.
- **Sen filtrar**: os filtros contra palabras que tamén son nomes ("Sala", "Mayo"...) están no
  código, con tests. As frecuencias gárdanse porque a futura regra de bloqueo por "nome pouco
  habitual" (plan interno da v2, punto 7.4) podería usalas.

Rexenerar (cando o INE publique datos novos): descargar os ficheiros aquí e executar
`datos/ine/xerar_taboas.py` (instrucións no propio script).
