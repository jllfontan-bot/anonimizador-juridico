# Anonimizador de expedientes xurídicos — documentación técnica (galego)

Implementación inicial do sistema descrito no informe *"Sistema de
anonimización de expedientes por código de persoa"*. Cubre a **Fase 1**
(decisións de deseño en [`config/entidades.yaml`](../config/entidades.yaml)),
a **Fase 2** (proba de concepto, xa probada contra un PDF real do despacho)
e arranca a **Fase 3** cunha interface web local de revisión humana.

Funciona 100&nbsp;% en local: nin o texto nin ningún dato sae nunca a internet.

## Licenza

Copyright © 2026 José Luis López Fontán.

Este programa é software libre: pode redistribuílo e/ou modificalo baixo os termos da
**GNU Affero General Public License** publicada pola Free Software Foundation, versión 3
(ver [`LICENSE`](../LICENSE)). Distribúese coa esperanza de que sexa útil, pero **SEN NINGUNHA
GARANTÍA**, nin sequera a garantía implícita de COMERCIABILIDADE ou ADECUACIÓN A UN FIN
DETERMINADO. Os compoñentes e datos de terceiros, coas súas licenzas, están en
[`AVISOS-TERCEIROS.md`](../AVISOS-TERCEIROS.md).

## Que fai

1. **Le o documento** (`pdf.py`, `pipeline.py`): `.txt`, `.docx`, `.odt`,
   `.pdf` e imaxes (`.jpg`, `.png`, `.tif`, `.bmp`, `.webp`, `.gif`; `imaxes.py`:
   trátanse coma unha páxina escaneada e gárdanse no MESMO formato e tamaño,
   sen metadatos EXIF) — nun PDF, extrae o texto da capa nativa páxina a páxina e, só
   nas páxinas sen texto extraíble (escaneadas), fai OCR con Tesseract
   (`spa+glg`, con `eng` de reserva; escala de grises + autocontraste antes
   do OCR para reducir erros en dixitalizacións de pouco contraste).
2. **Detecta** persoas físicas (spaCy, modelo `es_core_news_md`) e
   identificadores directos — DNI/NIE, teléfono, email, **matrícula**
   (formato actual e o anterior a 2000, con código de provincia), **enderezo**
   (rúa/calle/c//avenida/lugar... en galego e castelán, con número ou "s/n"),
   **número de colexiado/a**, **CSV** (Código Seguro de Verificación) e
   **número de referencia** de trámites administrativos, e número de
   expediente (`recognizers.py`, patróns propios para formatos españois).
   Nestes tres últimos só se redacta a cifra/código, mantendo a etiqueta
   ("colegiado número", "Código Seguro de Verificación", "número de
   referencia") coma contexto visible. O DNI/NIE normalízase sempre
   recalculando o díxito de control a partir dos números (`ocr_dni.py`),
   nunca confiando na letra final tal como a le o OCR; e o símbolo ordinal
   "nº"/"n.º" recoñécese en calquera orde e aínda que o OCR o confunda cunha
   aspa ou o signo de grao, coma ocorreu nun PDF real do despacho.
   > **Corrección crítica**: un CSV permite recuperar o documento ORIXINAL
   > completo no portal do organismo emisor, e un "número de referencia"
   > dun trámite (ex. apoderamentos xudiciais) funciona igual -- deixalos
   > sen redactar anula toda a anonimización aínda que se borren nomes e
   > DNI. Atopado revisando un PDF real do despacho (un certificado de
   > apoderamento cun CSV á vista) e corrixido de inmediato.
   > **Corrección de maior impacto de toda a proba**: o modelo de NER
   > practicamente NON recoñecía persoas en texto TODO EN MAIÚSCULAS --
   > extremadamente habitual en notas de poder, notas simples rexistrais e
   > sinaturas de documentos oficiais españois (ex. "D/Dª JOSE LUIS LOPEZ
   > RABADAN..." non se detectaba en absoluto, quedando o nome real sen
   > anonimizar). Corrixido en `ner.py`: pásase unha copia do texto a
   > "Title Case" só para a detección (a lonxitude non cambia, así que as
   > posicións de caracteres seguen a corresponder ao orixinal), pero
   > distinguindo palabras funcionais ("con", "nif", "domicilio"...) —
   > que se pasan a minúsculas, non a Title Case — para que o recorte de
   > fronteiras as siga a recoñecer coma tal en vez de as tratar coma
   > continuación dun nome.
   > **Corrección complementaria**: o caso oposto tamén ocorre -- nun bloque
   > de sinatura real dun informe de arquitecto, o NER detectaba SÓ o nome
   > de pía ("Leandro"), deixando fóra sen redactar o apelido composto ("del
   > Rio"). Engadida unha pasada de EXTENSIÓN cara adiante en `ner.py`
   > (`_estender_entidade_persoa`) que amplía a entidade mentres o patrón
   > sexa "conector coñecido + palabra en maiúscula inicial", e ampliouse a
   > listaxe de palabras funcionais con profesións/cargos habituais
   > ("arquitecto", "avogado", "notario"...) para que tampouco se confundan
   > con continuación dun nome. Límite residual documentado: un segundo
   > apelido pegado SEN conector despois do primeiro (ex. "Resua" en
   > "Leandro del Valle Resua") pode non quedar incluído, e o mesmo bloque de
   > texto repetido en varias páxinas non sempre se detecta cun 100&nbsp;%
   > de consistencia (o modelo ten en conta o contexto precedente de cada
   > páxina) -- ampliar a heurística sen esixir conector reintroduciría o
   > problema orixinal (verbos/profesións absorbidos en maiúsculas), así
   > que se optou por deixalo coma risco residual para revisión humana en
   > vez dunha heurística máis arriscada.
   > **Documentos moi longos**: spaCy rexeita textos de máis de 1.000.000 de
   > caracteres -- un documento técnico real (unha "memoria" de proxecto de
   > 351 páxinas, 1,3M de caracteres) xa superaba ese límite e facía fallar
   > todo o pipeline. En vez de aumentar ese límite (o propio spaCy avisa de
   > ata 1&nbsp;GB de memoria temporal por cada 100.000 caracteres,
   > inasumible nun "ordenador normal"), o texto trocéase en anacos moi por
   > debaixo do límite (`_anacos_para_ner`), cortando SEMPRE por saltos de
   > liña para non partir unha mención pola metade.
3. **Resolve identidade** (`resolution.py`): agrupa mencións do mesmo
   documento que corresponden á mesma persoa. Cando dúas mencións teñen o
   mesmo nome mais DNI distinto a carón, trátanse como **persoas distintas**
   — é o caso de homónimos que o propio informe sinala como o máis delicado.
4. **Xera ou recupera un código** (`registry.py`) desde un rexistro cifrado
   (Fernet/AES) persistente: a mesma persoa (confirmada por DNI) recibe
   sempre o mesmo código en calquera documento; sen DNI que o confirme, un
   nome repetido **nunca** se fusiona automaticamente — créase un código
   novo marcado para revisión humana.
   > **Corrección importante**: ao afinar a conservación de formato
   > apareceu un fallo real nesta garantía -- o índice de DNI actualizábase
   > en memoria pero gardábase en disco **antes** de incluír esa
   > actualización, así que unha nova execución (outra chamada ao CLI,
   > outra petición web) non atopaba a coincidencia e creaba un código
   > novo en vez de recuperar o existente. Os tests orixinais non o
   > detectaban porque reutilizaban a mesma instancia de rexistro en
   > memoria para as dúas chamadas; corrixido, e engadido un test
   > (`test_consistencia_persiste_entre_execucions_distintas`) que recarga
   > o rexistro desde disco para que non volva pasar desapercibido.
5. **Analiza o risco de efecto mosaico** (`mosaic.py`) despois de anonimizar
   os nomes e enderezos: sinala combinacións de profesión + lugar + data/idade
   exacta que poderían identificar a alguén aínda sen ningún identificador
   directo. Non se substitúe automaticamente — mostra a frase para que un
   letrado decida se cómpre xeneralizala.
6. **Rexistra auditoría** cifrada de cada resolución (quen se creou, cando,
   se quedou marcada e por que).
7. **Interface de revisión humana** (`web.py`, `templates/`): unha aplicación
   web local (só en `127.0.0.1`, nunca exposta á rede) onde un letrado
   ve os posibles homónimos (que quedan SEMPRE coma persoas distintas:
   a revisión non fusiona códigos), revisa os riscos de efecto mosaico e
   escolle que datos se tapan antes de gardar. A decisión queda rexistrada
   na auditoría cifrada (`registry.manter_separadas`).
8. **Reversión controlada e listado completo** (`registry.reverter`/
   `registry.listar_correspondencias`, rutas web `/reverter`/
   `/listar-correspondencias` e subcomandos `reverter`/
   `listar-correspondencias` do CLI): as dúas únicas funcións de todo o
   sistema que devolven datos identificativos. `reverter` recupera UN
   código coñecido de antemán; `listar_correspondencias` amosa TODAS as
   correspondencias dun rexistro dunha vez (máis sensible: esixe ademais
   unha confirmación explícita, paxínase, e queda auditada cunha acción
   distinta -- `listado_completo`, nunca `reversion`). As dúas esixen
   sempre un motivo (nunca opcional) e quedan rexistradas na auditoría
   cifrada con quen as solicitou e cando. Se un código foi fusionado
   noutro (só en rexistros antigos ou dende o CLI), `reverter` segue o
   alias ata o vixente e o listado amosa os fusionados coma columna do
   código vixente.
9. **Conserva o formato orixinal** en `.docx` e `.odt` (`pipeline.py`,
   funcións `cargar_documento_estruturado`/`gardar_documento_estruturado`):
   en vez de escribir sempre texto plano, reescribe o texto anonimizado
   dentro do propio documento orixinal — mantén aliñamento, listas, estilo
   de parágrafo e **táboas** (percorridas expresamente, xa que python-docx
   non as inclúe en `documento.paragraphs`). Conserva ademais a **mestura
   de formatos dentro dun mesmo parágrafo**: se un nome está en negriña e o
   resto da frase non, ou o nome vai repartido entre dúas "runs"/"spans"
   con estilos distintos, cada anaco mantén o seu propio formato tras a
   substitución (`anonimizar_texto_detallado` devolve as substitucións con
   posición exacta para poder repartilas así). Só cae na reserva -- todo o
   parágrafo co formato do seu primeiro anaco -- cando ese parágrafo
   concreto foi editado á man na interface de revisión (nese caso xa non
   hai forma fiable de saber que anaco orixinal correspondía a cada
   cambio). Se ao revisar se engade ou quita un salto de liña enteiro, o
   sistema detecta a desaliñación e garda coma `.txt` plano en vez de
   escribir un documento incorrecto.
9bis. **Conserva o formato E A EXTENSIÓN orixinais tamén en `.pdf`**
    (`pdf_estrutura.py`), tanto con texto nativo coma escaneado:
    - Cárgase **palabra a palabra** (`pagina.get_text("words")`, ou
      `pytesseract.image_to_data` nas páxinas sen texto extraíble) en vez
      de só texto plano, para saber o rectángulo exacto de cada palabra.
    - Ao gardar, cada substitución **redáctase de verdade**
      (`add_redact_annot` + `apply_redactions`) -- elimina o contido
      orixinal por completo, sexa texto vectorial ou píxeles dunha imaxe
      escaneada (`apply_redactions` tamén tapa "píxeles de imaxe
      superpostos" por defecto), non só o tapa visualmente -- e insírese o
      código de substitución nese mesmo rectángulo, cun tamaño de letra
      axustado automaticamente para que caiba.
    - Traballa a nivel de **palabra enteira**, non de carácter (a
      diferenza de `.docx`/`.odt`): calquera substitución redacta a
      palabra ou palabras que toca, nunca menos.
    - Se un letrado edita a man o texto dunha páxina de xeito que xa non
      coincide coas substitucións orixinais, ESA páxina cae na reserva --
      redáctase enteira e reescríbese co texto editado en fonte xenérica
      (perde o formato orixinal desa páxina soa, non do documento enteiro,
      e nunca amosa datos que non debera).
    - Verificado tamén con OCR: despois de gardar, un PDF escaneado
      redactado sométese de novo a OCR sobre a imaxe final para confirmar
      que o dato orixinal xa non é recuperable nin dos propios píxeles.
10. **Procesa arquivos `.zip`** (`pipeline.anonimizar_zip`): moi habitual en
    demandas reais, onde a documentación adxunta ven empaquetada (proxectos
    de arquitectura, memorias con planos...). Anonimiza cada `.pdf`/`.docx`/
    `.odt`/`.txt`/imaxe de dentro mantendo a estrutura de cartafoles e a
    consistencia de códigos ENTRE ficheiros do mesmo zip, conservando
    formato e extensión en tódolos casos. O PDF orixinal NUNCA se
    inclúe no zip de saída baixo ningún concepto — só a versión xa
    anonimizada. Calquera outro tipo de ficheiro (planos CAD, imaxes...)
    tampouco se inclúe no zip de saída, xa que non hai forma de revisalo en
    busca de datos persoais — queda listado en `omitidos` para que quede
    constancia explícita do que non se puido comprobar.

## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download es_core_news_md
```

Para OCR de PDF escaneados, fai falta ademais o binario de Tesseract (non
chega con instalar `pytesseract`, que só é o envoltorio Python):

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install tesseract tesseract-lang   # tesseract-lang inclúe spa e glg
```

Sen o binario instalado, `anonimizar` sobre un PDF con páxinas escaneadas
lanza un erro explicando isto; PDFs con texto nativo funcionan igual sen
Tesseract.

## Uso

```bash
PYTHONPATH=src python3 -m anonimizador.cli anonimizar \
    ejemplos/declaracion.txt \
    --informe informe.json \
    --rexistro ./datos_rexistro
```

Sen `--saida`, o nome por defecto é `<entrada>.anonimizado.<extensión>` —
para `.docx`/`.odt`/`.pdf` e as imaxes mantén a mesma extensión e conserva o
formato orixinal (táboas, estilos, aliñamento; en PDF, tamén con texto
escaneado); para `.txt` garda coma `.txt` plano. O nome e o DNI/NIE/pasaporte
dunha mesma persoa levan o MESMO código ("PERSOA_000001, con DNI
PERSOA_000001").

Para un `.zip` (ex. un proxecto de arquitectura completo cos seus planos),
o mesmo comando xera un `.anonimizado.zip` cos ficheiros procesados por
dentro, mantendo a estrutura de cartafoles, e imprime un resumo por
ficheiro máis a lista dos que quedaron fóra por non seren analizables.

O cartafol `--rexistro` contén `clave.key` (permisos 600) e `rexistro.enc` /
`auditoria.enc` / `sesions.enc`, cifrados con esa clave.

#### Clave de cifrado no chaveiro do sistema operativo

Por defecto a clave vive nun ficheiro local (`clave.key`, permisos 600) --
válido para probas, pero a sección 07 do informe marca isto coma punto
crítico para uso real: a clave debería estar nun chaveiro do sistema
operativo, non xunto aos datos que cifra. Engade `--chaveiro-sistema` a
calquera subcomando (`anonimizar`, `servir`, `reverter`) para que un
rexistro **novo** garde a súa clave aí en vez de en ficheiro:

```bash
PYTHONPATH=src python3 -m anonimizador.cli anonimizar \
    ejemplos/declaracion.txt --rexistro ./datos_rexistro --chaveiro-sistema
```

En Windows a libraría `keyring` usa o **Administrador de credenciais**
(require `pywin32`, xa incluído en `requirements.txt` só para Windows).
Executando dende o código fonte noutros sistemas usa o chaveiro nativo
(Keychain, SecretService) se hai un dispoñible.

Puntos importantes:

- **Só afecta a rexistros NOVOS**. Un rexistro xa existente sabe por si só
  onde está a súa clave (marcador `clave.chaveiro` no seu cartafol, sen
  datos sensibles) e sempre a busca aí -- non hai que repetir o flag en
  cada execución posterior, nin sequera desde outro subcomando (`servir`
  atopará a clave que creou `anonimizar`, e viceversa).
- **A primeira vez pode aparecer un diálogo do propio sistema operativo**
  pedindo autorización para gardar a clave -- é normal, confírmao.
- **Se o chaveiro non está dispoñible** (sen sesión de escritorio, backend
  non soportado...), cae automaticamente en ficheiro local sen perder o
  rexistro; cada comando imprime "Clave de cifrado: ..." para que quede
  claro cal se usou.
- **Non se pode mover un rexistro cuxa clave vive no chaveiro** a outro
  ordenador copiando só o cartafol -- a clave non viaxa con el (é o
  comportamento correcto: se viaxase en claro, xa non protexería nada).
  Para levar un rexistro a outra máquina, usa un que garde a clave en
  ficheiro (sen `--chaveiro-sistema`) e copia ese ficheiro por unha vía
  segura á parte.

### Interface de revisión humana

```bash
PYTHONPATH=src python3 -m anonimizador.cli servir --porto 5000
```

Abre `http://127.0.0.1:5000` (só accesible desde este ordenador). Introduce
a ruta do documento e o cartafol do rexistro, e a interface amosa:

- os posibles homónimos, só coma aviso: cada un queda sempre coma persoa
  distinta (a revisión non fusiona códigos; fusionar a man chegou a deixar
  o nome á vista no documento final);
- os riscos de efecto mosaico detectados, coa frase orixe;
- os datos detectados, para escoller cales se tapan.

Ao confirmar, garda o documento final e dispara `registry.manter_separadas`
para que a decisión do letrado quede tamén na auditoría cifrada do rexistro.

**Escoller ficheiro/cartafol sen escribir a ruta a man**: os botóns
"Escoller ficheiro…"/"Escoller cartafol…" (`selector.py`) abren o diálogo
NATIVO do sistema operativo (Finder/Explorador) e enchen o campo de texto
correspondente coa ruta escollida. Impleméntase lanzando un proceso Python
á parte con `tkinter.filedialog` -- non depende de ningunha librería
adicional, e evita a restrición de macOS de que a interface gráfica teña
que vivir no fío principal (o servidor web xa o ocupa).

**Cartafol de saída distinto do orixinal**: o campo "Cartafol de saída" é
opcional -- baleiro, mantén o comportamento de sempre (gardar canda o
documento orixinal); indicando un cartafol, o ficheiro anonimizado gárdase
aí en vez de alí (creándoo se non existe).

**Anonimizar un cartafol enteiro**: se o campo "Ficheiro OU cartafol"
apunta a un cartafol, procésase automaticamente cada `.pdf`/`.docx`/`.odt`/
`.txt` que atope dentro (recursivamente), creando unha **sesión de
revisión propia para cada un** -- nunca en bloque sen revisión, mantendo a
mesma garantía central do sistema có procesar un só documento. As sesións
créadas quedan listadas en "Revisións pendentes" para revisalas unha a
unha; os ficheiros doutros formatos quedan fóra e cóntanse coma
"omitidos".

**Anonimización automática**: antes de premer o botón, a pantalla inicial
pide escoller entre "Comprobar antes de gardar" (o fluxo descrito arriba)
ou "Anonimización automática" -- garda directamente, sen crear ningunha
sesión de revisión nin pedir confirmación, tanto para un ficheiro solto
coma para un cartafol enteiro (`web._procesar_automatico`). A regra de
seguridade central non cambia: `registry.resolver_ou_crear` xa NUNCA
fusiona un posible homónimo por conta propia, así que en modo automático
un posible homónimo simplemente recibe un código novo, igual ca no modo
de revisión.

As revisións pendentes sobreviven a un reinicio do servidor: gárdanse
cifradas en `<rexistro>/sesions.enc` (mesma clave có resto do rexistro) en
canto se procesa un documento, e elimínanse en canto se confirman. O único
que NUNCA se garda aí é o documento `.docx`/`.odt` orixinal en memoria --
iso recárgase sempre desde o ficheiro de orixe, que segue intacto no disco
mentres a revisión non se confirma. Para retomar revisións pendentes doutra
sesión do navegador ou tras reiniciar o servidor, indica o mesmo cartafol
de rexistro no campo "Ver revisións pendentes doutro cartafol" da páxina
principal.

### Reversión controlada

```bash
PYTHONPATH=src python3 -m anonimizador.cli reverter PERSOA_000007 \
    --motivo "presentación do orixinal en xulgado, expediente 123/2026" \
    --rexistro ./datos_rexistro
```

Ou dende a interface web, na ligazón "Reversión controlada de identidade"
da páxina principal (`/reverter`). En ambos casos o motivo é obrigatorio —
sen el, a chamada falla — e queda escrito na auditoría cifrada xunto co
usuario do sistema que a executou.

### Listado completo de correspondencias

```bash
PYTHONPATH=src python3 -m anonimizador.cli listar-correspondencias \
    --motivo "auditoría interna do expediente 123/2026" \
    --rexistro ./datos_rexistro --confirmar
```

Ou dende a interface web, na ligazón "Listado completo de correspondencias"
da páxina principal (`/listar-correspondencias`). Require o mesmo có
`reverter` (motivo + contrasinal de reversión) máis unha confirmación
explícita (`--confirmar` no CLI, unha casiña na web) -- amosa TODAS as
correspondencias do rexistro dunha soa vez, así que ten MÁIS alcance ca
unha reversión individual, e queda auditado cunha acción propia
(`listado_completo`). Paxínase de 200 en 200 (`--desde`/`--limite` no
CLI); a web volve pedir o contrasinal en cada páxina.

## Executar os tests

```bash
python3 -m unittest discover -s tests -v
```

Os tests cobren os comportamentos centrais: consistencia entre documentos
vía DNI, homónimos con DNI distinto (códigos distintos), homónimos sen DNI
(nunca fusión automática, sempre marcado), límites de entidade do NER (o
modelo esparexendo unha entidade máis alá do nome ou cortándoa demasiado
curta antes dun apelido con conector, e a detección de persoas en texto
TODO EN MAIÚSCULAS sen confundir palabras funcionais/profesións con
continuación do nome), documentos que superan o límite de caracteres de
spaCy (trocéanse en anacos sen partir ningunha mención), detección de risco
de efecto mosaico, lectura de
PDF/.odt, OCR sobre PDF escaneado (sáltase automaticamente se Tesseract non
está instalado), corrección de DNI/NIE mal lidos polo OCR, matrículas
(formato actual e anterior a 2000), enderezos (galego/castelán, "c/", "s/n",
símbolo "nº" mal lido polo OCR), números de colexiado/a, CSV e números de
referencia (en calquera orde etiqueta/código), o fluxo completo da interface
de revisión (procesar → marcar homónimo → manter separado → gardar), a
reversión controlada (motivo
obrigatorio, rexistro na auditoría, seguimento de alias tras unha fusión), a
conservación de formato en `.docx`/`.odt` (negriña, táboas, e o caso de erro
cando a edición desaliña os parágrafos) e o procesamento de `.zip` (ficheiros
soportados anonimizados, non soportados omitidos do zip de saída,
consistencia de códigos entre ficheiros distintos dun mesmo zip), usando o
test client de Flask.

## Limitacións coñecidas desta proba de concepto

Correspóndense coas seccións 10 (riscos residuais) do informe orixinal:

- **Lectura de documentos**: `.txt`, `.docx` (inclúe táboas; non cabeceiras
  nin rodapés), `.odt` (inclúe táboas) e `.pdf` (nativo + OCR).
- **Conservación de formato en `.docx`/`.odt`**: a mestura de formatos
  dentro dun parágrafo consérvase por tramos (ver punto 9 máis arriba)
  mentres ese parágrafo non se edite á man na revisión; se se edita, cae na
  reserva (todo co formato do primeiro anaco). Se ao editar se engade ou
  quita un salto de liña enteiro, o sistema detecta a desaliñación e garda
  coma `.txt` plano en vez de arriscar un documento incorrecto.
- **Conservación de formato en `.pdf`** (punto 9bis): a redacción traballa
  a nivel de PALABRA enteira, non de carácter -- un patrón de tipo
  "colegiado número [cifra]" segue a funcionar (a palabra "2481" é
  independente), pero non hai garantía pixel-perfect quedando o tipo de
  letra do código de substitución exactamente igual có orixinal (usa unha
  fonte estándar con axuste automático de tamaño). Nunha páxina editada a
  man na revisión, redáctase esa páxina ENTEIRA e reescríbese en fonte
  xenérica -- perde formato só nesa páxina, non no resto do documento.
  Documentos con columnas múltiples ou táboas complexas en PDF poden ver
  alterada a orde de lectura do texto reconstruído (limitación herdada da
  extracción de texto por palabra, non específica desta funcionalidade).
- **Calidade do OCR**: aínda con preprocesamento e corrección do díxito de
  control, Tesseract pode confundir díxitos illados en dixitalizacións de
  baixa calidade — un documento anonimizado a partir de OCR debe revisarse
  antes de darse por bo (para iso existe agora a interface de revisión).
- **Enderezos**: só se redactan cando teñen un número (ou "s/n") preto do
  nome da vía, no mesmo treito de texto — un enderezo mencionado sen número,
  ou cun número moi afastado do nome da rúa (habitual en formularios con
  campos separados, coma unha nota simple rexistral), non se detecta como
  identificador directo e queda para revisión humana.
- **Interface de revisión**: as sesións pendentes agora sobreviven a un
  reinicio do servidor (gardadas cifradas en `sesions.enc`, ver punto 7 máis
  arriba); segue sen haber autenticación porque só escoita en `127.0.0.1`;
  o caso "apelido solto ambiguo" só se pode corrixir editando o texto á man,
  sen despregable de fusión (non hai un código concreto candidato ao que
  apuntar).
- **NER en galego**: úsase o modelo de castelán (`es_core_news_md`) porque
  non hai aínda un modelo maduro de spaCy en galego; nomes ou formas moi
  específicas do galego poden escapar á detección. Fase seguinte: avaliar
  un corpus real e, se cómpre, afinar (*fine-tune*) un recoñecedor propio.
  O modelo tamén esparexe ás veces a entidade máis alá do nome (ex. "Xoana
  Veiga Lucas **presentou**"); `ner._recortar_entidade_persoa` corrixe
  isto recortando polo final cando o token sobrante non leva maiúscula
  inicial nin é un conector de apelido coñecido (de, do, van...), pero segue
  a ser unha heurística, non unha garantía para calquera caso.
- **Resolución de identidade** é intencionadamente conservadora (agrupa por
  nome exacto + DNI dentro dun documento); alcumes, iniciais ou grandes
  variacións ortográficas entre documentos distintos aínda requiren
  revisión humana — non se inventou heurística arriscada para cubrilos.
- **Efecto mosaico**: a lista de profesións e o veciñanza de frases son
  configurables (`config/entidades.yaml`) pero é unha heurística, non unha
  garantía; segue a facer falta revisión humana en casos de alto risco.
- **Xestión de claves**: por defecto a clave vive nun ficheiro local con
  permisos restrinxidos; con `--chaveiro-sistema` gárdase no chaveiro do
  sistema operativo (en Windows, o Administrador de credenciais) -- ver
  sección "Clave de cifrado no chaveiro do sistema operativo" máis arriba.
  Un token de hardware (HSM) queda fóra do alcance desta proba de concepto.

## Seguinte paso

Avaliar precisión e cobertura sobre un corpus máis amplo de documentos reais
do despacho.
