# Estado dos dous programas (02/11/2026)

Este repositorio contén dous programas que comparten o mesmo motor:
o **Anonimizador xurídico** e o **Reductor de tokens** (antes «Conversor de arquivos para IA»).
Este ficheiro é un resumo curto. Non leva datos reais nin notas persoais.

## Anonimizador xurídico

- Microsoft Store: **publicado**, Store ID `9PK1J429MNN5`.
- Publicado na Store: **1.1.1.0**. Preparada, sen publicar: **1.1.2** (`VERSION`; paquete 1.1.2.0): correccións de fugas, explorador con carpetas reais de Windows e copia `.md` co mesmo motor ca o Reductor.
- Política de privacidade: `docs/store/politica-privacidad.md`; condicións de uso: `docs/store/condiciones-de-uso.md`.
- Só Windows 10/11 na Store. As versións de Mac e Linux quitáronse da oferta do Anonimizador;
  hai instaladores clásicos de Mac nas ramas `instalador-mac-*`.
- Pendente: nada urxente.

## Reductor de tokens (antes «Conversor de arquivos para IA»)

- Microsoft Store: **publicado**, Store ID `9NMM4DRL6FCC`, paquete 1.1.0.0. Preparada, sen publicar: **1.2.0** (`conversor.VERSION`; paquete 1.2.0.0).
- Política de privacidade: `docs/store/politica-privacidad-conversor.md`; ficha: `docs/store/ficha-store-conversor.md`.
- Instaladores clásicos sen asinar para Windows e Mac (`instalador/crear-paquetes.sh windows-conversor|mac-conversor`).
- Notas de deseño e límites en `src/anonimizador/formatos/ESCONDITES.md` e estudos previos en `docs/estudios/`.
- Rama `motor-md-unico` (inclúe `correcciones-fugas-reductor`; sen publicar): en automático nunca se detén e o resumo final lista os
  «Documentos con posibles fugas» cun botón «Revisar» (`conversor.substituir_revisado`); un `.zip` dentro dun
  cartafol ábrese en `<nome do zip>-md` (un `.zip` dentro dun `.zip`, non; límite de 2 GiB descomprimidos);
  subtítulo novo. Falta probar a xanela real (pywebview) con «Revisar» no portátil Windows.
- Pendente: formatos novos en modo anonimizado (con tests de fugas), adxuntos de `.eml` nun `.zip`,
  menú contextual de Windows, extensión para Claude Desktop.

## Compartido

- Motor: `pipeline`, `lectura`, `copia_md` (en `src/anonimizador/`). Suite de tests: uns 1.100
  (`python3 -m unittest discover -s tests`; tarda ata ~25 min).
- Empaquetado: `instalador/crear-paquetes.sh`. A caché de rodas pódese poñer noutra carpeta
  con `ANONIMIZADOR_BUILD=<carpeta local>`.
- Workflow «Paquete MSIX» (`.github/workflows/msix.yml`): só se lanza con etiquetas `msix-v*` /
  `msix-conversor-v*` ou á man (`app=anonimizador|conversor`). Subir ramas ou commits non xera paquetes.
- O rexistro de persoas gárdase en `Documentos\Anonimizador`.
- Non mover nin renomear `docs/store/*`: a Store e o código enlazan a esas rutas.

## Plan de publicación (15/11/2026)

Orde das fases; cada unha cabe nunha sesión curta e termina co seu criterio de «feito».

1. **Fase 0 · Explorador do Anonimizador** (esta sesión; Sonnet · medio): `explorador.py` usa as carpetas
   reais de Windows. Feito = suite en verde + commit en `correcciones-fugas-reductor`.
2. **Fase 1 · Valoración xurídica nova** (Opus · alto): modelo = a do Anonimizador (condicións de uso
   revisadas por un avogado o 15/10/2026, só esas). Feito = informe fóra do repositorio público, cos puntos ⚖️
   para o avogado e as propostas de texto sen aplicar ás condicións aprobadas.
3. **Fase 1b · Mesmo motor Markdown nos dous programas** (Opus · alto; cartafol de traballo propio): hoxe a copia
   `.md` do Anonimizador usa `copia_md.xerar`, pero NON aplica `titulos_pdf.marcar_titulos_md` nin `aforro_ia`
   (cabeceiras repetidas, liñas unidas) coma o Reductor. Feito = a mesma función serve aos dous camiños (con proba
   que o garanta), tests de fugas en verde e sen cambios na anonimización do texto.
4. **Fase 2 · Preparar versións** (Sonnet · medio): fusionar a rama en `main` (só local), subir versións,
   fichas, manuais e paquetes MSIX de ambos programas. Feito = tests en verde, paquetes montados e lista do
   que sube o usuario ao Partner Center. Sen push nin etiquetas `msix-v*` sen permiso do usuario.
   **Condición previa á entrega:** o usuario está probando no portátil Windows o Reductor e o Anonimizador
   (explorador, modo automático sen paradas, lista final con «Revisar», `.zip` en cartafoles). A fase 2 pode
   preparar todo, pero nada se dá por listo para publicar sen o resultado desas probas; calquera fallo que saia
   volve á fase 0/1b antes de montar os paquetes definitivos.
5. **Fase 3 · Limpeza dos rastros de proba** (Haiku · baixo): só o que creou Claude no portátil
   (rexistros temporais, scripts, instaladores e cartafoles de `C:\Users\Public\Documents`). Os cartafoles do
   escritorio decide o usuario cales quedan.

### Estado das fases (15/11/2026, tarde)

- Feitas: 0 (explorador), 1 (informe en `~/Documents/anonimizador-xuridico/VALORACION-JURIDICA-20261115.md`, fóra
  do repositorio), 1b (`markdown_ia.xerar`) e a parte de «versións e textos» da 2 (commits en `motor-md-unico`).
- Para enviar á Store (etiquetas, sen poñer): `msix-v1.1.2` (Anonimizador) e `msix-conversor-v1.2.0` (Reductor), sobre
  o commit final de `main`. Subir a `main` e etiquetar require permiso do usuario; as políticas e condicións enlazadas
  polas fichas tamén teñen que estar en `main` antes do envío.
- R1 do informe, feito (`535fd0f`, `93248fb`): en automático, os `.md` con posibles fugas levan `posibles_fugas: N`
  na cabeceira (co .md único, tamén na sección de cada documento), que se quita ao revisar; ficha e manual (PDF
  rexenerados) din o mesmo. Fóra: o aviso ao pechar a xanela con documentos sen revisar (só se o usuario o pide;
  hai que probalo en Windows).
- Decisión do usuario: probas en Windows (condición previa), agora tamén coa marca `posibles_fugas`.
- Textos ⚖️ do informe APROBADOS POLO USUARIO o 15/11/2026, sen revisión do avogado (que só revisou as condicións
  do Anonimizador do 15/10/2026), e aplicados (`ab69492`..`e8e1720`): diferenza A (condicións do Anonimizador),
  diferenza B (condicións propias do Reductor, `docs/store/condiciones-de-uso-reductor.md`, enlazadas na súa ficha),
  P1 das políticas (correos e datos de Microsoft), subtítulo e CLI («menos tokens», «O programa non envía nada fóra
  do equipo»), frase das marcas de Anthropic (fichas e «Acerca de») e artigo 5 da EUPL fóra de AVISOS e README.
  Quedan para o avogado, se se quere: confirmar eses textos e os puntos de só verificación do informe (L3 LGPL,
  L4 termos de Microsoft, D2 TXUE, D3 Regulamento de IA).
- Capturas rexeneradas (`4987588`, `237e2d2`, PDF en `e83944a`): todas as do manual do Reductor (o subtítulo sae en
  todas) e «Acerca de» do Anonimizador. Capturas da ficha do Reductor 1.2.0, fóra do repo:
  `~/Documents/anonimizador-xuridico/store-reductor-1.2.0/capturas/{gl,es}`. As da ficha do Anonimizador 1.1.2
  (`lenzos.py` do pendrive sobre as do manual), en `~/Documents/anonimizador-xuridico/store-anonimizador-1.1.2/capturas/`:
  non levan «Acerca de»; cinco son idénticas ás do 15/10 e cambia só a de inicio.
- Pendente menor: a copia `NOVEDADES`.

## Separar Anonimizador e Reductor (decidido 15/11/2026)

O usuario non quere que os dous programas se mesturen nin en GitHub nin na Microsoft Store. O repositorio propio
do Reductor faise **antes** de publicar o Reductor 1.2.0 (o Anonimizador 1.1.2 non depende disto).

**Fase A · Textos e ligazóns (feita):** `8222d5b`, `03fc30a`, `b701228`. Ficha, política, condicións, manual (e PDF)
e NOVEDADES do Reductor sen nomear o Anonimizador, e ficha do Anonimizador sen nomear o Reductor. O rexistro
compartido descríbese sen nomear o outro programa («outra aplicación do mesmo desenvolvedor pode compartilo»), para
que a política siga sendo exacta mentres o rexistro sexa compartido. Quedou sen tocar, para facelo cando remate a
sesión «escritura-incremental» (edita `src/`) ou na fase B:
- Textos da app: `conversor.cli.axuda_anonimizar`, `conversor.cli.axuda_rexistro`, `conversor.cli.axuda_chaveiro`,
  `conversor.cli.rexistro` e `pantalla_conversor.modo_revisar_axuda` (es e gl) nomean «o anonimizador»; despois,
  rexenerar as capturas do manual do Reductor e da súa ficha (a de inicio amosa `modo_revisar_axuda`).
- Instalador clásico do Reductor (`instalador/windows/instalador-conversor.nsi`, `TXT_UN_FIN` e `TXT_UN_BENVIDA`):
  «compartidos co anonimizador».

**Fase B · Repositorio propio do Reductor** (sesión nova, Opus · alto; despois de que remate «escritura-incremental»,
se integre en `motor-md-unico` e pase a suite completa):
1. Crear en local `~/proyectos/reductor-de-tokens` (repo `jllfontan-bot/reductor-de-tokens`) cun **commit inicial**
   co do Reductor e unha **copia do motor**, sen o historial nin o exclusivo do Anonimizador: README, política,
   condicións, ficha, manual, `AVISOS-TERCEIROS.md`, licenzas, workflow MSIX só do Reductor coa etiqueta `msix-v*`,
   `VERSION` propia.
2. **Rexistro cifrado propio** do Reductor: cartafol de datos propio e entrada propia no Administrador de credenciais;
   migración ou aviso para quen xa usou o rexistro compartido (copiar, non mover).
3. Quitar do repo do Anonimizador o exclusivo do Reductor, o seu workflow e as etiquetas `msix-conversor-v*`.
4. Pór na ficha do Reductor as URL do repo novo (política, condicións e sitio web).
5. Crear o repo en GitHub e subilo faino ou autorízao o usuario á parte (contido público).

**Fase C (decidida 15/11/2026, o usuario aceptou a versión curta):**
- **Valoración xurídica CURTA, non completa:** ninguén a esixe; case todo o texto do Reductor xa se valorou nesta rolda
  (condicións propias, políticas, ficha, marcas). Só comparar os textos do repo novo cos xa valorados e mirar o que
  cambie (URL, descrición do rexistro propio). Opcional, decisión do usuario: enviar ao avogado as condicións e a política
  do Reductor e os textos ⚖️ aprobados sen avogado (el só revisou as condicións do Anonimizador, versión AGPL do 15/10/2026).
- **Probas en Windows OBRIGATORIAS** (non se poden verificar no Mac: escritura incremental, rexistro propio e migración,
  paquete MSIX sen abrir aínda). Eu preparo a instalación no portátil e comprobo hashes; o usuario fai unha pasada curta:
  abrir; converter un cartafol cun `.zip` sen anonimizar; converter anonimizando; comprobar que se crea o rexistro novo
  e que sae o aviso de migración. Mesma comprobación co Anonimizador despois de quitar o exclusivo do Reductor.

**Conflito asumido (decisión do usuario):** deixa de cumprirse «o motor .md do Anonimizador = o do Reductor» coma un
único código (fase 1b, `markdown_ia.xerar`): quedan dúas copias coa mesma versión inicial, que evolucionan por
separado. Unha corrección de fugas nunha non chega soa á outra.

**Riscos:** migración do rexistro (os códigos deixarán de coincidir entre programas; non perder as correspondencias
de quen xa anonimizou co Reductor); URL da ficha (publicar primeiro no repo novo e cambiar a ficha despois, sen
ligazóns rotas); política e condicións cambian, así que a fase C vai antes de enviar á Store; dúas copias do motor
que poden separarse en calidade.

## Para a seguinte versión: anonimizar os formatos novos do Reductor (decidido 15/11/2026)

Decisión de José Luis: a **1.2.0 sae como está** (as follas, presentacións, `.html` e `.eml`
seguen convertíndose só SEN anonimizar; a ficha, as condicións e a valoración xurídica xa o din).
Traballo apuntado para a versión seguinte, non para esta:

- **Que**: facer que o motor anonimice `.xlsx/.ods/.csv`, `.pptx/.odp`, `.html` e `.eml`. Hoxe
  `conversor.py` (~167-173) omíteos con `sen_proba_de_fugas` e `formatos.EXTENSIONS_SO_SEN_ANONIMIZAR`
  inclúe todos.
- **Mapa**: `src/anonimizador/formatos/ESCONDITES.md` (columna «que hai que facer»). Entra no `.md`
  e hai que anonimizalo: comentarios e notas de cela, notas do orador, URL de ligazóns http(s)/mailto,
  nomes de follas e diapositivas, cabeceiras de correo (De/Para/Asunto), o `.csv` á parte das follas
  grandes e os nomes de arquivo e cartafol. O que hoxe non se le (metadatos, comentarios con fíos,
  embeddings) debe seguir fóra.
- **Como**: formato a formato (ou por familia: follas / presentacións / web+correo), cada un cos seus
  tests de fugas (datos inventados en cada escondite -> ningún no `.md` nin no `.csv`). Un formato
  só sae de `EXTENSIONS_SO_SEN_ANONIMIZAR` cando os seus tests pasan.
- **Sesións**: Opus / esforzo alto (risco de fugas), unha por familia, en rama propia desde `main`.
- **Ao publicalo cambian**: `docs/store/ficha-store-conversor.md` (es ~76, gl ~148: «só se convirten
  sen anonimizar»), a diferenza B das condicións do Reductor, a sección 4.1 da valoración xurídica
  (`~/Documents/anonimizador-xuridico/VALORACION-JURIDICA-20261115.md`), e unha **valoración xurídica
  nova** antes de enviar á Store.

## Escritura incremental do Reductor (rama `escritura-incremental`, 15/11/2026)

Motivo: no portátil de probas un lote longo (.zip e centos de folios) non gardou nada porque os `.md` se
escribían todos ao final (`conversor._converter`); un fallo tardío deixou a carpeta de saída baleira.

Deseño (sen tocar detectores, `markdown_ia` nin o texto anonimizado):
1. Cada documento escríbese en canto se converte (con e sen anonimizar); un documento roto, ou que non se pode
   escribir (`erro_escritura`), vai a `omitidos`/`erros` e o lote segue; tres erros de escritura seguidos páranlo.
   Escritura atómica: primeiro todos os `.tmp` (tamén as partes) e despois `os.replace`, con reintentos en Windows e
   escritura directa como último recurso; o `.tmp` non queda nunca. Un fallo a metade non borra partes anteriores.
2. Destino por documento (`usadas`, `usados_csv`, `-2`, `_colocar_csv`, partes), no mesmo orde ca antes; o nome e o
   cartafol de cada documento fíxanse ao anonimizalo. Un `.csv` á parte non queda se o seu `.md` non se garda.
3. Anonimizando, o nome do `.zip` (cartafol `-md` ou `.md` único) e o dun cartafol co `.md` único anonimízanse AO
   PECHAR, con `nome_ficheiro_anonimizado` sen persoas, coma antes (facelo antes rexistraba a persoa do nome antes
   do documento que a nomeaba: outro código e un «posible homónimo» falso). Ata pechar, o `.parcial` e o cartafol
   `-md` levan un nome neutro `conversion-en-curso-<data>` (`NOME_PROVISIONAL`); ao pechar renoméanse (ou, se o
   final xa existe, fúndense sen perder ficheiros alleos). Os nomes de cada documento e dos seus cartafoles non cambian.
4. `un_so_md`: as seccións engádense a `<nome>.md.parcial` (sen índice, `conversión: incompleta`); ao rematar
   constrúese `<nome>.md` e bórrase o `.parcial`. Se o lote para (cancelar, erro), o convertido vai a
   `<nome>.incompleto.md` (`conversión: incompleta`): o nome de sempre só o leva unha conversión completa e unha
   anterior non se pisa. Se o proceso morre (kill, apagado), queda só o `.parcial`. Se falla o peche dun lote
   rematado, queda o `.parcial` (non se marca incompleto); se só falla borrar o `.parcial`, o lote remata ben.
5. `Cancelado` e calquera excepción levan `resultado_parcial`; a pantalla suma o gardado ao resumo e mantén «Revisar».
6. Modo manual: igual; cada documento escríbese ao devolver `revisar`. `substituir_revisado` reescribe os `.md` xa
   escritos, quita `posibles_fugas`, escribe o novo antes de borrar o vello e, se falla, o documento queda coma estaba.

Estado: FEITO na rama `escritura-incremental` (sen mergear en `motor-md-unico`; decide o usuario). Revisión
independente aplicada (1 nome do .zip, 2 incompleto, 3 Windows, 4 partes, 5 peche, 7 .csv). Suite completa: 1239 tests
OK (1 omitido). `tests/test_escritura_incremental.py`: 52 tests.
- Non feito: a cabeceira do `.parcial` non leva o total de `posibles_fugas` (cada sección leva o seu; o total
  obrigaría a reescribir o ficheiro en cada documento, e o `.parcial` non é un produto final).
- Sen probar en Windows nin na xanela real (pywebview): reintentos de `os.replace`, renomeado do cartafol `-md` con
  ficheiros abertos (se non se pode, as saídas quedan no provisional, coas rutas reais no resumo).
- Riscos menores: un `.csv` á parte que substituíra outro do mesmo nome e despois se retira (fallou o seu `.md`) non
  recupera o anterior; nun cartafol sen `.md` único xa non se anonimiza o nome da carpeta de entrada (non se usaba);
  cada documento dunha carpeta anonimiza o seu cartafol cos seus códigos (xa era así). Manual e fichas non din aínda
  «cada .md gárdase ao converterse».

## Anonimizador: `.zip` dentro dun cartafol (rama `anon-zip-en-carpetas`, 15/11/2026, feito sen probar en Windows)

Deseño (o cartafol procesábase sen os `.zip`; e a xanela tampouco abría un `.zip` dado directamente: só a CLI):
- Un `.zip` (directo ou dentro do cartafol) sae coma `<nome anonimizado>.anonimizado.zip` onde saen os demais ficheiros, coa mesma estrutura de subcartafoles e a copia `.md` de cada documento se está activada. Tamén en modo «revisar»: un zip non ten revisión documento a documento, así que se anonimiza en automático e a pantalla dio.
- Dúas fases: (1) no seu sitio da orde do cartafol anonimízase o CONTIDO de cada documento do zip a un temporal; (2) ao rematar o lote (tamén se se cancela) ponse nome ás entradas, aos cartafoles internos e ao propio zip, coas persoas de todos os documentos dese zip, e escríbese o zip de saída. Así un nome no nome do zip ou dun cartafol interno nunca crea antes un código no rexistro: os códigos e o aviso de posible homónimo dos documentos saen igual ca sen o zip.
- Seguridade coma no Reductor (código propio en `pipeline.py`, sen importar `conversor.py`): rutas sen `..`/raíz/unidade; 2 GiB descomprimidos por lote como máximo (cabeceiras e conta real ao descomprimir: zip bomb); `.zip` dentro de `.zip` non se abre; zip con contrasinal, danado ou demasiado grande omítese enteiro, listado, sen escribir nada e sen parar o lote; `__MACOSX`/`._*` omitidos; nomes repetidos tras anonimizar levan contador.
- O que non se pode analizar nunca entra no zip de saída: a pantalla de resultado e a CLI listan, por zip, os omitidos co motivo. Un `.anonimizado.zip` anterior non se volve procesar.
- Mesmo rexistro para cartafol e zips (os códigos dunha persoa con DNI coinciden).

Feito (commits na rama `anon-zip-en-carpetas`, sen mergear en `motor-md-unico`):
- Código: `pipeline.preparar_zip`/`gardar_zip_preparado` (e `anonimizar_zip` coma as dúas seguidas), `web._ZipsDoLote` (barra de progreso e `/procesar`, modos automático e revisar), CLI con motivos, explorador marca os `.zip` coma soportados. Plantilla nova `templates/_zip.html`; textos `zip.*` en `es.json`/`gl.json`.
- Escritura: o `.anonimizado.zip` vai a un temporal neutro (`.anonimizando-*.zip.tmp`) e só substitúe ao rematar (reintentos por PermissionError); se falla, bórrase o temporal e un zip anterior non se pisa. A CLI calcula o nome final antes de escribir (sen provisional co nome real).
- Revisión independente (15/11, tarde), arranxados con test que fallaba antes: M1 (entradas repetidas no zip perdían o informe e o aviso de fugas: `documentos` por entrada), M2 (CLI con `--saida` igual á entrada substituía o orixinal, tamén con documentos soltos: agora erro 2), B1 (`C:nota.txt`, `a:b`, `<>"|?*` e punto/espazo final saneados; cada entrada escríbese cun ZipInfo propio), B4 (extracción dun orixinal a vez tras comprobar o zip sen escribir; temporais con prefixo e PID; limpeza de órfos), B3 (test do límite axustado), B5 (sen «0 documentos procesados») e B6 (a barra amosa cada zip ao escribilo). Tests novos tamén para «revisar» e zip directo polo traballo en segundo plano.
- Defecto real en Windows (proba no portátil coa versión 1630440, 15/11): un zip cun PDF («Justificante presentacion demanda») fallaba enteiro con `PermissionError: [WinError 32] ... documento.pdf` ao borrar o orixinal extraído (PyMuPDF tíñao aberto). Arranxado (55009f9 + 90f4f83): o PDF pécase, o borrado vai con reintentos e nunca lanza, e se o cartafol temporal non se pode borrar a pantalla e a CLI avisan con onde está e o zip vale; o seguinte zip bórrao (tamén no mesmo proceso). PENDENTE: volver probalo no portátil.
- Suite completa: 1223 tests OK (1 omitido), en Mac.
- Tests: `tests/test_zip_en_cartafol.py` (38: nada sen anonimizar en nomes, cartafoles, contido, metadatos docx/pdf e copias .md; `__MACOSX`; danado, CRC mal, contrasinal; zip dentro de zip; `..`/raíz/unidade; límite compartido e cabeceira mentirosa; nome do zip cunha persoa que aparece despois → mesmo texto e mesmos avisos ca sen o zip; `.anonimizado.zip` non se reprocesa; modo revisar; zip directo na xanela; cancelar; erro ao escribir sen pisar o anterior; PermissionError ao substituír e ao borrar o temporal; persoa no 2.º documento do zip (k>1); CLI). Os dous de orde fallan co código antigo / pechando o zip xusto despois do seu contido (comprobado).
- Textos: ficha 1.1.2 (es e gl) e manual (gl e es, sección 12 e explorador), PDF do manual rexenerados.

Queda:
- PROBAR NO PORTÁTIL WINDOWS e na xanela real (pywebview): cartafol con 2 `.zip` e PDF soltos, en automático e en revisar; un `.zip` directo; ver a pantalla de resultado. Nada disto está probado en Windows.
- Decidir co usuario: en modo «revisar» o zip anonimízase en automático (non hai revisión documento a documento dun zip); alternativa: omitilo nese modo.
- Limitación previa do motor (non nova): nun nome de cartafol «Cliente Xosé Carballo Portela» detecta a persoa con «Cliente» incluído e dálle código propio (sen fuga).
- Temporais (B4): se o programa morre a medias (pechar a xanela), no temporal do sistema queda como moito UN orixinal do zip (o que se procesaba, nome neutro) e os anonimizados á espera dos nomes; na saída, un `.anonimizando-<pid>-*.zip.tmp` (xa anonimizado). Bórranse ao empezar o seguinte zip noutra execución (só os propios, co PID dun proceso morto). NON cobre: se o programa non volve arrancar, quedan ata que Windows limpe o temporal. Valorar se a política de privacidade o debe dicir. A rama de Windows de `_proceso_vivo` (ctypes) está sen probar.
- B2, comportamento coñecido (decisión: mantense a lóxica A17): unha persoa do nome do zip que só aparece nun documento SOLTO do cartafol (non dentro do zip) recibe no nome do zip un código novo distinto do do documento solto, e queda unha segunda entrada no rexistro (pode dar avisos de homónimo en lotes posteriores). Igual ca co nome dun documento solto.
- B7: os tracebacks de documentos que fallan van ao `anonimizador.log` (texto plano); os vistos levan rutas temporais neutras, pero un PermissionError ao escribir leva a ruta de saída (cartafol real + nome xa anonimizado), coma cos documentos soltos.
- Non tratado: nomes reservados de Windows (`CON`, `NUL`...) dentro do zip (non é fuga: só fallaría ao descomprimir en Windows).

## Ramas vivas

- `follas-csv-aparte`: traballo en curso.
- `instalador-mac-1.1.0`, `instalador-mac-1.1.1`: instaladores de Mac do Anonimizador.

## Onde está o arquivo

O historial de decisións e medicións de 09–10/2026 e os datos reais viven nun repositorio privado
(non público). Para consultalo, contactar co titular.

## Regra de ouro

Non engadir nunca ao repositorio datos reais (nomes, DNI, expedientes). Ver `docs/estudios/` e `medicion/README.md`.

## Probas en Windows (portátil Windows 11, 15/11/2026) — resultados

Feitas polo usuario co meu apoio por SSH (só lectura e copia de ficheiros comprobada con hash):
- **Reductor 1.2.0 (instalación clásica, sen escritura incremental), RT7**: 2 `.zip` + 6 PDF, automático e anonimizando: 12 `.md`,
  carpetas `<zip>-md`, nomes anonimizados; o PDF que daba WinError 32 (`Justificante presentacion demanda`) convértese. Arranxo
  de `temporales.py` CONFIRMADO en Windows.
- **Anonimizador 1.1.2, carpeta con PDF**: explorador (atallos Escritorio/Documentos a `D:`) ben; 6 PDF anonimizados + 6 `.md`
  co mesmo motor (tamaños case iguais aos do Reductor); códigos de persoa coincidentes co Reductor. Os `.zip` dentro da carpeta
  ignoráronse (entón non se abrían: ver a rama `anon-zip-en-carpetas`).
- **Reductor con escritura incremental (rama `escritura-incremental`, HEAD 7d29f6a), RT8**: os `.md` aparecen un a un; cancelar
  conserva o feito e a xanela final mantén os pendentes de «Revisar»; execución completa con 3 `.zip` (15 `.md`, 0 `.tmp`/`.parcial`);
  `posibles_fugas: N` na cabeceira. Sen fugas reseñables segundo o usuario; os avisos de persoa posible homónima son esperables
  por traballar repetidamente cos mesmos documentos (rexistro compartido con persoas de execucións anteriores).
- Lentitude medida: PDF de 351 páxinas ~11 min (fase posterior ao OCR ~4-5 min); planos (22 páxinas) varios minutos cada un.
  Rama `progreso-fase-final` (indicador de progreso + optimización de `resolution._emparellar`) en curso.
- **Reductor con escritura incremental + correccións da revisión (rama `escritura-incremental`, HEAD 7d29f6a; xa unida en `motor-md-unico`)**:
  - RT9 (`.md` único, anonimizando): `.parcial` durante o traballo, `RT9.anonimizado.md` ao lado da carpeta (non dentro), 6 arquivos,
    `posibles_fugas: 16` (suma das seccións), sen `.parcial` ao rematar.
  - RT9 cancelado co `.md` único: sae `RT9.incompleto.anonimizado.md` (`conversión: incompleta`, 2 arquivos) SEN pisar o completo anterior.
  - `.md` bloqueado (CLI no portátil, sen anonimizar, ficheiro aberto en exclusiva): os outros documentos gárdanse, o bloqueado sae como
    «convertido, pero non se puido gardar o .md» co PermissionError, queda intacto e non hai `.tmp`/`.parcial` orfos. NON probado co bloqueo en modo anonimizado.
  - Rastro do usuario/meu no portátil a limpar ao final: RT7, RT8, RT9, AN3 (Escritorio), `C:\Users\Public\Documents\prueba-final` (copia
    da instalación + RT10), `copia-antes-arreglo-20261115`, `Iniciar-Anonimizador-prueba.vbs`, carpeta de nome estragado «Demanda rǧa…» (10:06).
- **Non probado aínda en Windows**: `progreso-fase-final`, `anon-zip-en-carpetas`, o paquete MSIX, o rexistro propio do Reductor (fase B).
