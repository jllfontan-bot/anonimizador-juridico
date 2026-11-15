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

O usuario non quere que os dous programas se mesturen nin en GitHub nin na Microsoft Store.

**Feito agora (só textos e ligazóns, antes de publicar 1.1.2 / 1.2.0):** `8222d5b`, `03fc30a`, `b701228`. Ficha,
política, condicións, manual (e PDF) e NOVEDADES do Reductor sen nomear o Anonimizador, e ficha do Anonimizador sen
nomear o Reductor. O rexistro compartido descríbese sen nomear o outro programa («outra aplicación do mesmo
desenvolvedor pode compartilo»), para que a política siga sendo exacta.

**Queda (non se tocou por ser `src/`, que edita outra sesión, ou o instalador clásico):**
- Textos da app: `conversor.cli.axuda_anonimizar`, `conversor.cli.axuda_rexistro`, `conversor.cli.axuda_chaveiro`,
  `conversor.cli.rexistro` e `pantalla_conversor.modo_revisar_axuda` (es e gl) nomean «o anonimizador». Despois,
  rexenerar as capturas do manual do Reductor (a de inicio amosa `modo_revisar_axuda`) e da súa ficha.
- Instalador clásico do Reductor (`instalador/windows/instalador-conversor.nsi`, textos do desinstalador
  `TXT_UN_FIN` e `TXT_UN_BENVIDA`): «compartidos co anonimizador».
- As tres URL da ficha do Reductor (política, condicións e sitio web) levan o nome do repositorio actual
  (`anonimizador-juridico`), e o sitio web é o README do Anonimizador.

**Obxectivo seguinte (non agora; Opus · alto, unha fase por punto):**
1. Repositorio de GitHub propio para o Reductor: o seu código (ou o motor compartido como dependencia), política,
   condicións, manual, `AVISOS-TERCEIROS.md`, workflow MSIX e etiquetas propios; cambiar as tres URL da ficha.
2. Rexistro cifrado propio do Reductor (o seu cartafol e a súa entrada no Administrador de credenciais), sen
   compartir o do Anonimizador.
3. Workflow e etiquetas separados (`msix-conversor-v*` deixa de vivir no repo do Anonimizador).

**Riscos:** migrar o rexistro sen perder correspondencias de quen xa usou o Reductor anonimizando (copiar, non
mover; os códigos deixarán de coincidir entre programas); URL da ficha: publicar primeiro no repo novo e cambiar a
ficha despois, sen deixar ligazóns rotas; o cambio altera a política e as condicións do Reductor, así que fai falta
unha valoración xurídica nova antes de envialo á Store.

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

## Ramas vivas

- `follas-csv-aparte`: traballo en curso.
- `instalador-mac-1.1.0`, `instalador-mac-1.1.1`: instaladores de Mac do Anonimizador.

## Onde está o arquivo

O historial de decisións e medicións de 09–10/2026 e os datos reais viven nun repositorio privado
(non público). Para consultalo, contactar co titular.

## Regra de ouro

Non engadir nunca ao repositorio datos reais (nomes, DNI, expedientes). Ver `docs/estudios/` e `medicion/README.md`.
