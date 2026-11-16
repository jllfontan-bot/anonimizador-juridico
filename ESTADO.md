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

## Progreso e rendemento da fase final (rama `progreso-fase-final`, 15-16/11/2026)

Caso real (Windows, 4 núcleos): PDF de 351 páxinas anonimizado, ~11 min (4-5 min despois do contador de páxinas, sen
indicador); perfil real do usuario (847 s con perfilador): copia_md/`find_tables` 32 %, lectura e OCR 37 %, NER 26 %.

Feito (un commit por cambio; cada optimización con test de equivalencia coa versión anterior e saídas de referencia
byte a byte idénticas no Anonimizador, incluída a súa copia .md, e no Reductor; mesmos códigos de persoa):
- Indicador (`etapas.py`, `converter(progreso_etapa=...)`): pantalla (es/gl) e CLI (stderr) din a etapa despois das
  páxinas: detectar (avance por anacos), axustar, agrupar (avance por mención), codigos, riscos, markdown, gardar.
- `resolution._emparellar`: distancia antes da busca do ANEXO (era cúbico).
- `copia_md`: non chama a `find_tables` en páxinas sen `get_drawings()` (coa estratexia «lines» non pode haber
  táboa); só con PyMuPDF 1.26/1.28 (lido o código; os paquetes levan 1.26.0) e sen `pymupdf.layout`.
- `ner._detectar`: `doc.text`/`doc.ents` unha vez por doc (spaCy reconstrúeos en cada acceso; era cuadrático).
- CLI (`consola.saida_utf8`, en `cli_conversor` e `cli`): stdout/stderr en UTF-8 con `errors=replace` (en Windows, con
  saída redirixida en cp1252, «⚠» facía saír cun erro despois de escribir o .md).

Medicións (Mac, PDF sintéticos con texto inventado, anonimizando, s):

| documento | NER | `resolution.agrupar` | copia_md | total: inicio → agora |
|---|---|---|---|---|
| escrito 50 páx.  | 37 → 7    | ~51 → 0,1  | 3 → 0,03 | 104 → 17 |
| escrito 100 páx. | 102 → 16  | ~416 → 0,3 | 6 → 0,05 | 557 → 35 |
| táboas 100 páx. (filetes e táboas) | 104 → 14 | 0,8 | 4,3 → 2,4 | 123 → 32 |

- Sen tocar (só documentado): o OCR (Tesseract, proceso aparte) e a lectura de PyMuPDF; `find_tables` de
  `taboas_pdf` na lectura (camiño de detección; só nas páxinas con pista de cabeceira); `mosaic.analizar` (~linear,
  7-11 s/100 páx.); spaCy (linear).
- Planos: sen texto vectorizado, A1 = A4. Con rótulos vectorizados, o OCR das zonas de trazos densos a 300 ppp crece
  coa área (A4 2,5 s/páx. e ~315 MB; A1 8,6 s/páx. e ~1 GB); vai na lectura. Un tope de ppp cambiaría o texto lido: non se
  puxo. Paralelizar o OCR (pool de procesos): non; risco alto en Windows (spawn, pythonw, MSIX) e non é o que pesa despois.
- Sen probar en Windows nin na xanela real: tempos do Mac; no PDF real o aforro de copia_md depende de cantas páxinas
  non teñen ningún debuxo (filetes e logotipos vectoriais contan coma debuxo).
- Tests novos: `test_progreso_etapas`, `test_resolucion_emparellar`, `test_copia_md_sen_debuxos`, `test_ner_texto_do_doc`,
  `test_consola`. Suite completa (16/11/2026): 1264 tests OK (1 omitido), en 6 min (antes ~24 min: a propia suite
  vaise máis rápida co NER).

## Ramas vivas

- `follas-csv-aparte`: traballo en curso.
- `instalador-mac-1.1.0`, `instalador-mac-1.1.1`: instaladores de Mac do Anonimizador.

## Onde está o arquivo

O historial de decisións e medicións de 09–10/2026 e os datos reais viven nun repositorio privado
(non público). Para consultalo, contactar co titular.

## INVARIANTE: onde vive o rexistro cifrado (fixado o 16/11/2026) — MOI IMPORTANTE
O rexistro de correspondencias (código ↔ nome real) vive **sempre** en `Documentos\Anonimizador\datos_rexistro`, na Store e no instalador clásico (o lanzador clásico usa agora
`anonimizador.arranque_windows`, a mesma entrada ca a Store). As actualizacións e desinstalacións **non o moven nin o borran**: o desinstalador clásico non toca Documentos e só pregunta polos datos
ANTIGOS de `%LOCALAPPDATA%\Anonimizador`; a Store non borra Documentos. Se o rexistro cambia de sitio, as persoas reciben códigos distintos e non se pode reverter nin manter a coherencia.
Protexido por `tests/test_rexistro_ubicacion_estable.py` (nome do cartafol, lanzador clásico, entrada MSIX, desinstalador) e un comentario en `arranque_windows.py`.
Se algún día cambia (fase B: rexistro propio do Reductor) fágase con migración que COPIE (nunca mova) e aviso, e cámbiense eses tests deliberadamente no mesmo commit. Caso real que o motivou: o `.exe` clásico
traballaba en `%LOCALAPPDATA%\Anonimizador` (rexistro distinto, `PERSONA_000001` de novo) mentres a Store usaba Documentos.

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
- **Anonimizador con `.zip` dentro dun cartafol (rama `anon-zip-en-carpetas`, xa unida), probado pola API web real do programa aberto no portátil**:
  - AN4 (código anterior ao arranxo): 4 de 5 ben; `demandapresentada.zip` fallou con `PermissionError WinError 32` ao borrar o PDF temporal
    (mesmo fallo que o do Reductor; o código novo dos zips non usaba `temporales.DirectorioTemporal`). Reproducido illado en AN5.
  - Arranxo (90f4f83) e proba de novo en AN6: **5 de 5**, dous `.anonimizado.zip` ben formados (estrutura e `.md` dentro, comentario baleiro),
    sen `.tmp` en AN6. Os 3 PDF soltos coa copia `.md`; mesmos códigos.
  - NON probado en Windows: modo revisar manual con zips; limpeza ao pechar a xanela a mitad de lote.
- **`progreso-fase-final`** (a944329, sen integrar): medido no portátil co doc real de 351 páxinas: 738 s sen o cambio e 734 s con el,
  `.md` idéntico (SHA-256 igual) → `_emparellar` non acelera ese documento (si o PDF sintético de 100 páxinas: 557→129 s). Perfil cProfile
  do doc real en curso no portátil (prueba-final\perfil.txt) para achar o cuello real.
- **Non probado aínda en Windows**: `progreso-fase-final`, o paquete MSIX, o rexistro propio do Reductor (fase B).

## Suite sobre o resultado integrado (15/11/2026, noite)
`motor-md-unico` fda1f53 (escritura incremental + `.zip` dentro de cartafoles + textos da valoración xurídica): **1277 tests, OK (skipped=1)**, 24 min.
Probado en Windows: ver «Probas en Windows» (AN6: `.zip` en cartafol 5/5; RT8/RT9 escritura incremental). `progreso-fase-final` (a944329) NON integrada.

## Perfil real del doc de 351 páxinas en Windows (16/11/2026, cProfile, anonimizando, prueba-prog = progreso-fase-final a944329)
859 s con profiler (734 s sen el). Reparto acumulado: **copia_md (crear o .md) ~278 s (32 %)**, case todo `pymupdf find_tables` (351 páxinas, 0,77 s/páx); lectura de páxinas ~315 s (37 %) con OCR Tesseract 146 s (384 chamadas);
**NER `_detectar` 227 s (26 %)**, 84,6 s de tempo propio + spaCy 60 s. `resolution._emparellar` xa non pesa. Pedido á sesión de rendemento (Opus): propoñer arranxos SÓ se son seguros (saída idéntica byte a byte,
sen cambiar detección): reutilizar/saltar `find_tables`, o bucle propio de `ner._detectar`; o demais documentar. Fallo atopado: a CLI do Reductor rebenta en consolas cp1252 de Windows ao imprimir «⚠» (`cli_conversor.py:123`,
despois de escribir o .md); arranxo pedido (stdout/stderr a utf-8 con errors=replace) con test. Non integrado nada.

## Medición final de `progreso-fase-final` (ac49dc9) co doc real de 351 páxinas en Windows (16/11/2026)
Anonimizando, mesmo PDF e mesma máquina: **483 s** (antes 738 s: −35 %). `.md` de 22960 liñas **idéntico ao anterior agás a data da cabeceira** (liña 7, `convertido: 2026-11-15` → `2026-11-16`); 121 persoas (48 marcadas), igual.
O hash SHA-256 difire só por esa data. Probado só neste documento; a suite do Mac (1264 OK) e os tests de equivalencia da rama cubren o resto. Rama NON integrada (decide o usuario).

## Suite sobre motor-md-unico con progreso-fase-final integrado (16/11/2026)
`motor-md-unico` 442b29c (escritura incremental + `.zip` en cartafoles + progreso-fase-final): **1302 tests, OK (skipped=1)**, 6 min. Conflicto resolto en `cli.py` (imports: `consola, copia_md, idioma` + `ZipRexeitado, gardar_zip_preparado, preparar_zip`).
Pendente en Windows: reprobar co código integrado (copia en prueba-prog xa leva progreso a44329+4 commits; prueba-zip leva a rama .zip). Fase B e decisións do usuario seguen abertas (ver RETOMA-20261115.md).

## Probas do .exe clásico co aviso (16/11/2026, tarde)
- Suite completa tras o aviso de dous rexistros: **1315 OK** (1 omitida). `.exe` reconstruído (`Anonimizador-Xuridico-Instalador-20261116-de262bb.exe`, sha256 e1ea7125…da83d), copiado ao portátil con hash igual e instalado en silencio.
- No portátil: o lanzador usa `anonimizador.arranque_windows`; a pantalla inicial mostra o aviso «dous rexistros cifrados distintos» (hai un rexistro de proba en `%LOCALAPPDATA%\Anonimizador`) e crea o ficheiro de aviso en Documentos. Captura para o manual: `~/Documents/anonimizador-xuridico/capturas-manual/`.
- Pendente: comparar os `posibles_fugas` do Reductor co Anonimizador (copia a `.md`) sobre os mesmos documentos (petición do usuario; só se comparaban tamaños e códigos).

## Comparación de `posibles_fugas` Reductor vs Anonimizador (16/11/2026, portátil Windows)
5 PDF pequenos (>30 KB) do Escritorio real (copiados; nada tocado), mesma máquina, rexistros de proba novos, borrados despois.
| doc | Reductor `posibles_fugas` | Anonimizador (resultado web, risco alto) | códigos de persoa (R / A) | tamaño .md R / A |
|---|---|---|---|---|
| 01 | 1 | 1 | 11 / 11 | 3984 / 3840 |
| 02 | 0 (sen liña) | 0 | 4 / 4 | 3084 / 2959 |
| 03 | 1 | 1 | 7 / 7 | 18255 / 18111 |
| 04 | 2 | 2 | 7 / 7 | 14422 / 14278 |
| 05 | 1 | 1 | 10 / 10 | 4038 / 3894 |
Coinciden os avisos (total 5), os códigos e o corpo. **Diferenza: o `.md` da copia do Anonimizador NON leva cabeceira** (nin `posibles_fugas`, nin `paginas`, nin `anonimizado`): 144 bytes menos en 4 de 5 docs (e 125 no doc02); `copia_md.xerar` só devolve o corpo e a cabeceira (`conversor._cabeceira`) escríbena só o Reductor.
O aviso de fugas do Anonimizador vive só na páxina de resultado (`n_risco_alto`), así que quen lea o `.md` solto non o ve. Non é un fallo de detección; si unha laguna de deseño: se se quere paridade, engadir cabeceira ou liña `posibles_fugas` á copia (decide o usuario; non tocado).
Detalle: a CLI do Reductor lanzada á man (fóra do lanzador) non atopa Tesseract (`TesseractNonInstalado`) se non se fixan `PATH` e `TESSDATA_PREFIX`; o lanzador real xa o fai. Tempos: Reductor 28 s, Anonimizador 45 s.

## Para a seguinte versión (1.1.3): `posibles_fugas` na copia `.md` do Anonimizador
- Decisión do usuario (16/11/2026): déixase para a seguinte versión; non se toca código agora.
- Que falta: a copia `.md` do Anonimizador (`copia_md.escribir`, `markdown_ia.copia_do_anonimizador`) non leva cabeceira nin a liña `posibles_fugas: N`; o aviso só sae na páxina de resultado (`n_risco_alto` en `web.py`). O Reductor si a leva (`conversor._cabeceira`, `_liña_fugas`).
- Proposta: engadir só a liña `posibles_fugas: N` (cando N > 0) á copia, co mesmo texto do Reductor; non cambia a detección. Ir co resto de cambios da 1.1.3, sen versión propia.

## DECISIÓN (16/11/2026): publicar xa e deixar a Fase B para unha nova versión
- O usuario decide publicar xa: Anonimizador 1.1.2 e Reductor 1.2.0 (MSIX das etiquetas `msix-v1.1.2` e `msix-conversor-v1.2.0`, en `~/Documents/anonimizador-xuridico/msix-20261116/*/store/`; os sobe o usuario ao Partner Center).
- A **Fase B** (repo `jllfontan-bot/reductor-de-tokens` con historial limpo e rexistro cifrado propio; ~5-6 h, brief en `~/Documents/anonimizador-xuridico/FASE-B-brief.md`) vai nunha versión posterior. Ata entón o Reductor 1.2.0 comparte repositorio e rexistro co Anonimizador (o usuario aceptouno ao decidir publicar).
- Os MSIX NON levan os commits posteriores a `6a09af6` (lanzador clásico, aviso de dous rexistros, nota ESTADO): isto só afecta ao `.exe` clásico e á seguinte versión.
- Para a seguinte versión: Fase B; anonimizar xlsx/pptx/html/eml; `posibles_fugas` na copia `.md` do Anonimizador; modo revisión manual con zips; peche de xanela a metade de lote.
