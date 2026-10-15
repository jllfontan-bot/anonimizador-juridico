# Medición de referencia (punto 5 do plan interno da v2)

Antes de integrar calquera IA na v2, isto dá unha liña base numérica da v1 para poder
comparar despois -- sen isto, "parece que detecta mellor" sería só unha opinión.

## Como funciona

- `corpus_sintetico.json`: casos de proba con **verdade coñecida** (datos inventados, nunca
  documentos reais). Cada caso di que anaco `debe_desaparecer` (dato persoal real) e que
  anaco `debe_permanecer` (contexto que NON é dato persoal, control de sobre-anonimización).
- `medir_v1.py`: executa `anonimizar_texto` de cada caso e comproba as DÚAS métricas SEMPRE
  xuntas (nunca unha soa, ver [[feedback-anonimizador-metodoloxia]]):
  - **Fuga**: un anaco que debía desaparecer segue no texto anonimizado.
  - **Sobre-anonimización**: un anaco que debía quedar intacto desapareceu. Sepárase á súa
    vez en "marcada para revisión humana" (comportamento deliberado do proxecto -- mellor
    un falso positivo de máis, ver `risco_residual.py`) e "sen marcar" (fallo silencioso de
    verdade, o único que preocupa en modo automático).

## Executar

```
.venv/bin/python medicion/medir_v1.py            # só amosa o resumo
.venv/bin/python medicion/medir_v1.py --gardar   # tamén garda un informe en resultados/
```

## Resultado do 27/09/2026 (liña base da v1, antes de calquera IA)

24 casos, 0 fugas, 0 sobre-anonimizacións sen marcar. Os 2 casos de sobre-anonimización que
aparecen están xa marcados para revisión humana (comportamento deliberado, non fallo).
Detalle en `resultados/v1-baseline-20260927-171028.json`.

## Categorías cubertas hoxe

Identificadores directos (DNI/NIE/pasaporte/teléfono/email/enderezo/IBAN/colexiado/
Seguridade Social), nomes en formatos coñecidos (estándar, orde invertida, sen coma antes
de profesión, en contexto de testemuña), controis negativos (non redactar sen etiqueta,
cargos públicos exentos), e catro casos de **categoría especial** (saúde, relixión,
orientación sexual, afiliación sindical) que a v1 NON detecta coma tal hoxe -- métrica
informativa, é precisamente onde se espera que unha IA local poida achegar algo novo (ver
sección "Proba rápida" do plan).

## Categoría especial (27/09/2026): lista determinista, sen IA no programa

`medir_categoria_especial.py` mide `src/anonimizador/categoria_especial.py` a través do
pipeline completo, en tres conxuntos separados:

| Conxunto | Resultado |
|---|---|
| 44 casos do xerador (inflado: a lista coñecía o seu vocabulario) | 44/44 |
| **Corpus de reserva** (`corpus_categoria_especial_reserva.json`, comitado ANTES da lista) | **28/29 (96,6%)**, 0 avisos de máis nas 18 frases trampa |
| Resto do corpus principal (268 casos sen dato sensible) | 0 avisos de máis |

Para comparar: qwen2.5-coder:3b acertara 39/44 (88,6%) no conxunto do xerador. Único fallo
no de reserva: "mantiene una relación sentimental con otro hombre" (non se engadiu un
patrón a propósito, para non axustar a lista ao corpus de reserva). Límite honesto: o corpus
de reserva non é cego (escribiuno o mesmo autor ca lista), e todas as frases son limpas e
sintéticas -- en documentos reais a redacción será máis variada. Falta comprobalo en local
con documentos reais (automático + lectura humana, coma sempre).

## Seguinte paso

Cando se probe un modelo de IA coma auditor (punto 6.3 do plan), correr este MESMO corpus
tamén por el e comparar: cantas categorías especiais detecta, se mantén as 0 fugas e 0
sobre-anonimizacións sen marcar da v1, e se acerta o caso `nome_contexto_testemuna` (a proba
rápida do 27/09 amosou que depende moito do prompt).

## Corpus real da web (28/09/2026): BOE + DOG

Liña "corpus real da web" do plan interno da v2 (Opción B): 150 documentos PDF reais
descargados do BOE (API de datos abertos) e do DOG (índice diario), fase 1 (100-200 docs,
non os 1000 previstos para máis adiante). **Só en local**, fóra do repo:
`build/corpus_web/` (ou o cartafol que se indique con `--dir`) -- levan
datos persoais reais aínda que publicados, nunca van a git. Excluídos o Taboleiro Edictal
Único (só interesados e administracións poden conservar/tratar eses datos) e o CENDOJ
(prohibe a descarga masiva no seu aviso legal). Licenzas comprobadas: ambas permiten
reutilización comercial e non comercial citando a fonte, ver `corpus_web_descargar.py`.

Circuíto en tres scripts:
- `corpus_web_descargar.py`: escolle e descarga os PDF con cortesía (pausas, User-Agent
  identificado), repartidos por sección (nomeamentos, oposicións/listaxes, outras
  disposicións, xustiza, anuncios) para variedade. Garda `manifesto.json` con hash de cada
  ficheiro e a licenza da fonte.
- `corpus_web_auditar.py`: pipeline completo (o mesmo ca a app) -> garda o PDF de saída ->
  **RELÉ ese PDF** (nunca o texto que devolve o pipeline: os fallos graves do pasado -- 
  sinatura en widget, cabeceira sen coma -- estaban na ESCRITURA do PDF) -> busca indicios
  de fallo por tipo: entidade detectada que segue literal no texto ou no PDF, restos
  estruturais (anotacións/widgets/metadatos), rede de seguridade sobre o texto relido, DNI
  parcial enmascarado, posible sobre-anonimización (institución/lugar tapado coma persoa).
  `--gardar-resumo` garda SÓ contas por tipo (sen texto real) en `resultados/`.
- `corpus_web_mostra.py`: páxina HTML local (orixinal/anonimizado lado a lado) para a
  LECTURA HUMANA que a metodoloxía esixe sempre ademais do automático.
- `corpus_web_mostra_pdf.py`: o mesmo pero coas PÁXINAS do PDF renderizadas (vese o que
  recibirá o destinatario: liñas borradas, táboas estragadas, códigos superpostos). As
  marcas gárdanse no navegador; o botón "Copiar marcas" xera o resumo para pegar no chat.
- `corpus_web_distorsions.py`: o contrario da auditoría -- texto NON persoal que o
  pipeline conservaba pero FALTA no PDF de saída (29/09/2026 atopou 4446 palabras en 118
  de 150 documentos: o tachado borraba as liñas veciñas). Saída local, datos reais.

**Sen verdade coñecida** (ninguén dixo que debía desaparecer nun documento real): as cifras
de aquí son indicios e estimacións, nunca "fugas confirmadas" coma no corpus sintético --
cada indicio hai que miralo a man antes de dar por bo un arranxo.

### Resultado sobre 150 PDF (28/09/2026)

Liña base (código antes de tocar nada, ficheiro `resultados/corpus-web-antes-20260928.json`):
achados críticos en 4 documentos (79 identificadores documentais sen tapar nun anexo do DOG
-- pasaportes baixo "DNI/NIE/PAS" -- e 3 nomes partidos por unha liña de táboa do BOE).

Cinco arranxos en `src/anonimizador/recognizers.py` e `ner.py` (commits `462b687` e
`e764e95`), cada un reproducido primeiro con texto SINTÉTICO e cun test novo:
1. Pasaportes/documentos estranxeiros baixo etiqueta ("pasaporte", "representante") ou
   columna "DNI/NIE/PAS" dunha táboa.
2. O contexto (etiqueta/columna) gaña ao formato de teléfono cando un documento de 9 díxitos
   empeza por 6-9.
3. Cela "APELIDOS,\nNOME." dunha táboa partida en DÚAS liñas.
4. Tratamento "don/doña" en MINÚSCULA + cargo pegado sen coma ("Nombrar a doña X Secretaria
   General..."): o nome non se detectaba en absoluto.
5. Cela de táboa en TRES liñas (salto entre apelidos sen conector) e sinatura do BOE co
   segundo apelido só na liña seguinte.

Pendente ao pechar esta sesión: a auditoría final cos 5 arranxos xuntos (a intermedia,
`resultados/corpus-web-intermedio-solo-fix1-2-20260928.json`, só mide os arranxos 1-2 porque
se executou en paralelo coa edición dos arranxos 3-5) -- ver o rexistro interno do proxecto para o resultado e o
seguinte paso.

### Lectura humana

`corpus_web_mostra.py` xera `DIR/mostra/index.html` (LOCAL, datos reais): unha ou dúas
mostras por fonte+sección, alternando documentos con e sen achados automáticos -- os que non
teñen achados son os que máis din sobre fugas que ningunha regra busca hoxe.

## Nomes galegos (28/09/2026): reserva e controis negativos

Para arranxar as 9 fugas de nomes galegos pouco frecuentes (liña base do 28/09/2026: 97,1% OK,
9 fugas, 0 sobre-anonimizacións sen marcar) vaise usar unha táboa OFICIAL de nomes (INE, ver
`datos/ine/LEEME.md`). Como os nomes do xerador (`NOMES` en `generador_corpus.py`) tamén están
nesa táboa, esas 9 fugas desaparecerían POR CONSTRUCIÓN: medilas só alí non demostraría nada.
Por iso, ANTES de escribir o detector, comitéanse dous conxuntos que se miden por separado:

- `corpus_nomes_galegos_reserva.json` (360 casos): 30 nomes galegos da lista oficial que NON
  están en `NOMES`, con apelidos galegos que tampouco están no xerador. Nivel **A** (12 nomes,
  criterio obxectivo): aparecen no top-20 por década dalgunha provincia galega e en NINGUNHA
  outra provincia (`nombres_por_fecha.xlsx` do INE). Nivel **B** (18 nomes): escollidos á man
  pola ortografía galega (Xoán, Martiño, Icía, Tareixa, Fiz...), comprobados na lista INE. Dous
  apelidos inventados ("Vilaboi") NON están na lista INE de apelidos, a propósito: para ver o
  límite da regra. 30 casos con frases propias + 330 coas MESMAS plantillas do xerador (onde
  spaCy falla), cambiando só os nomes.
- `corpus_nomes_controis_negativos.json` (25 casos): topónimos, marcas e vías con nome de persoa
  ("Santiago de Compostela", "A Mariña", "un Mercedes gris", "calle Rosalía de Castro",
  "Hospital Álvaro Cunqueiro"...) e dous cargos públicos exentos. Todo debe quedar intacto.

Liña base v1 (antes do detector):

| Conxunto | OK | Fugas | Sobre-anon. sen marcar |
|---|---|---|---|
| Reserva (360) | 358 | 2 | 0 |
| Controis negativos (25) | 21 | 0 | 4 (xa existían: "Rosalía de Castro" en calle/IES/Premio, "CEIP Manuel Murguía") |

Ollo: a reserva discrimina pouco (spaCy xa acerta 358/360 con eses nomes); serve sobre todo
para comprobar que a táboa non se limita aos nomes do xerador e que non estraga nada.

```
.venv/bin/python medicion/medir_v1.py --corpus corpus_nomes_galegos_reserva.json
.venv/bin/python medicion/medir_v1.py --corpus corpus_nomes_controis_negativos.json
```

### Resultado co recoñecedor por táboa (28/09/2026, `ner._detectar_persoas_por_taboa`)

| Conxunto | Antes: OK / fugas / parciais / sen marcar | Despois: OK / fugas / parciais / sen marcar |
|---|---|---|
| Corpus do xerador (312) -- **inflado**: os seus nomes están na táboa | 303 / 9 / 4 / 0 | 312 / 0 / 0 / 0 |
| Reserva (360) -- nomes que NON están no xerador | 358 / 2 / 1 / 0 | 360 / 0 / 0 / 0 |
| Controis negativos (25) | 21 / 0 / 0 / 4 | 21 / 0 / 0 / 4 (os mesmos 4, xa existían; 0 cambios no texto) |

As "marcadas para revisión" do corpus principal seguen sendo 20 antes e despois.

**Fuga parcial** (métrica nova, `palabras_a_vista` en `medir_v1.py`): lendo as saídas a man
atopouse "Firma el presente documento Breixo PERSOA_000001" -- o caso contaba coma OK porque
o nome COMPLETO xa non estaba, pero o nome de pía seguía á vista. Mídese á parte e NON cambia o
criterio de OK (para seguir podendo comparar con medicións anteriores). A liña base real tiña
pois 4+1 fugas parciais máis das que se contaban.

Lectura humana de TODOS os textos que cambiaron (antes/despois): no corpus principal só
cambian os 9 casos de fuga e os 4 de fuga parcial; na reserva, as 2 fugas, a parcial e dous
casos onde antes se redactaba tamén "veciña" ("Comparece a PERSOA" -> "Comparece a veciña
PERSOA", mellora); nos controis, nada.

Límite coñecido: se NINGÚN apelido está na táboa do INE (apelidos de menos de 20 persoas), o
recoñecedor por táboa non actúa e queda todo en mans de spaCy.

## Comparar dúas versións sen sesgo (11/10/2026): `comparar_tapados.py`

Para saber que cambia un arranxo SEN medilo nos documentos que se miraron para facelo:
executa dúas versións do programa (referencia de git ou cartafol; cada unha no seu proceso)
sobre os documentos dun lote que ninguén revisou (sen etiqueta nin proposta en `LOTE/revision/`)
e lista o que a nova DESTAPA e o que TAPA DE NOVO, con contexto, para lelo palabra a palabra.
Engade os tapados coma PERSOA que son un lugar oficial (candidatos a sobreanonimización).

```
.venv/bin/python medicion/comparar_tapados.py --lote LOTE --vello main --novo . --saida DIR
```

`DIR` (fóra de git: leva nomes reais) queda con `vello.json`, `novo.json` (todos os tapados
de cada versión), `comparacion.json` e `comparacion.txt`. Opcións: `--procesos N`, `--n N`
(mostra ao chou), `--incluir-revisados` (medición SESGADA). Substitúe os scripts soltos do
disco local (`scripts-medicion-04102026/`: `destapado*.py`, `extraer_tapados.py`, `subst_en_lugares.py`)
e o comparador do 11/10 (`/tmp/cmp`).
