#!/bin/bash
# Xera o instalador de Windows do Anonimizador de expedientes xurídicos
# -- ver instalador/README.md para o porqué.
#
# O instalador leva TODO o necesario para instalar sen tocar nada máis no
# ordenador de destino nin precisar conexión a internet: Python, Tesseract
# (OCR) coas súas bibliotecas, e tódolos paquetes de Python.
#
# Uso: ./instalador/crear-paquetes.sh [windows]
# Saída: Anonimizador-Xuridico-Instalador-<VERSION>.exe (na raíz do
#        repositorio): instalador gráfico NSIS con barra de progreso,
#        desinstalador e entrada en "Aplicacións instaladas" -- ver
#        instalador/windows/instalador.nsi.
#
# O .exe leva xa o árbore FINAL (Python portátil cos paquetes
# desempaquetados en site-packages, sen venv nin pip), así que na máquina
# de destino só copia ficheiros -- a barra de progreso do asistente é a de
# verdade. Precisa `makensis` (paquete nsis).
#
# O cartafol build/ (descargas e paquetes montados) é un caché reutilizable
# entre execucións -- está en .gitignore, bórrao se queres partir de cero.
#
# Precisa: curl, python3 (con pip) e makensis.

set -euo pipefail
cd "$(dirname "$0")/.."   # raíz do repositorio

RAIZ="$(pwd)"
INSTALADOR="$RAIZ/instalador"
DOCS="$RAIZ/docs"
# ONDE SE TRABALLA. O empaquetado ocupa varios GB (staging + caché de
# wheels). Por defecto vai en `build/` dentro do repo;
# para levalo a outro disco:
#     ANONIMIZADOR_BUILD=/onde/queiras ./instalador/crear-paquetes.sh windows
BUILD="${ANONIMIZADOR_BUILD:-$RAIZ/build}"
mkdir -p "$BUILD"
CACHE="$BUILD/cache"
# Versión do PAQUETE (non do programa -- este proxecto non leva un
# número de versión formal): data de xeración + hash curto do commit
# actual, para saber dun vistazo de cando é o zip e de que código exacto
# saíu, sen ter que abrilo. Se o repo ten cambios sen commitear, engade
# "-suxo" para non confundilo cun build limpo e reproducible.
_VERSION_DATA="$(date +%Y%m%d)"
_VERSION_COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo "sencommit")"
_VERSION_SUXO=""
git diff --quiet 2>/dev/null && git diff --cached --quiet 2>/dev/null || _VERSION_SUXO="-suxo"
VERSION="${_VERSION_DATA}-${_VERSION_COMMIT}${_VERSION_SUXO}"
NOME="anonimizador-xuridico-instalacion-${VERSION}"

PY_TAG="20260901"
PY_VERSION="3.12.14"
MICROMAMBA="$CACHE/tools/micromamba"

# paquetes de Python que precisan resolverse por plataforma (todo
# requirements.txt agás pywin32, que é só para Windows, e odfpy, que ao
# non ter wheel compilado se descarga á parte coma paquete independente
# da plataforma).
#
# VERSIÓNS FIXADAS a propósito (non ">=makesolto"/sen versión): "pip
# download" para OUTRA plataforma/versión de Python distinta da
# anfitrioa (aquí: Mac/Python 3.9 descargando para Windows/Python 3.12)
# xa é máis lento por si só; combinado con especificadores SOLTOS coma
# "spacy>=3.8.4" (a árbore de dependencias de spaCy ten decenas de
# paquetes, cada un con moitas versións publicadas), o resolvedor de pip
# chega a entrar en backtracking patolóxico -- bug real atopado
# executando este script: case 8 HORAS de CPU sen rematar nin fallar,
# tivo que matarse a man. Cada versión de abaixo é a que xa está
# instalada e probada no venv de desenvolvemento (`pip freeze`); "spacy"
# ademais TIÑA QUE coincidir coa fixada en requirements.txt (3.7.5), non
# ">=3.8.4" coma estaba -- outra inconsistencia que tamén contribuía ao
# espazo de busca do resolvedor.
#
# "pywebview" NON vai aquí a propósito (ver `descargar_pywebview`): as
# súas dependencias transitivas CONDICIONAIS (pyobjc-* só en Mac,
# pythonnet só en Windows) avalíanse segundo a plataforma ONDE se
# executa pip (o host, Mac), non a de DESTINO -- así que un "pip
# download --platform win_amd64" tentaba igualmente resolver pyobjc-*
# (só existe wheel para Mac) e fallaba con "No matching distribution".
# Mesmo motivo xa documentado máis abaixo para pywin32 (`descargar_extras_windows`).
#
# cryptography, pymupdf e opencv-python-headless: fixadas nas versións
# xa probadas co instalador de Windows; ao subilas, comprobar antes que
# hai wheel para win_amd64 / cp312.
PAQUETES_COMUNS="cryptography==46.0.7 PyYAML==6.0.3 python-docx==1.2.0 pymupdf==1.26.0 pytesseract==0.3.13 pillow==11.3.0 flask==3.1.3 keyring==25.7.0 spacy==3.7.5 numpy==1.26.4 opencv-python-headless==4.10.0.84"

mkdir -p "$CACHE/tools" "$CACHE/runtime" "$CACHE/wheels" "$BUILD"

# ---------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------

log() { echo ">> $*"; }

asegurar_ferramentas() {
    command -v curl >/dev/null || { echo "ERRO: precísase 'curl' instalado."; exit 1; }
    if [ ! -x "$MICROMAMBA" ]; then
        log "Descargando micromamba (ferramenta de empaquetado, non se distribúe)..."
        # SEN "--strip-components=0": é un no-op (stripar CERO compoñentes
        # non cambia nada), pero en bsdtar (macOS) facía que "tar" deixase
        # de recoñecer "bin/micromamba" coma patrón de extracción e
        # fallase con "Not found in archive" -- bug real de portabilidade
        # atopado executando este script en Mac.
        #
        # O propio BINARIO de micromamba ten que coincidir coa máquina
        # ANFITRIÓA que executa este script (é unha ferramenta de
        # construción, non un paquete de destino) -- estaba fixado a
        # "linux-64" a secas, así que fallaba con "cannot execute binary
        # file" executando isto en Mac (bug real de portabilidade
        # atopado igual cós dous de arriba).
        case "$(uname -s)-$(uname -m)" in
            Darwin-arm64) _plataforma_micromamba="osx-arm64" ;;
            Darwin-x86_64) _plataforma_micromamba="osx-64" ;;
            Linux-aarch64) _plataforma_micromamba="linux-aarch64" ;;
            *) _plataforma_micromamba="linux-64" ;;
        esac
        curl -Ls "https://micro.mamba.pm/api/micromamba/${_plataforma_micromamba}/latest" \
            | tar xj -C "$CACHE/tools" bin/micromamba
        mv "$CACHE/tools/bin/micromamba" "$MICROMAMBA"
        rmdir "$CACHE/tools/bin" 2>/dev/null || true
    fi
}

# ---------------------------------------------------------------------
# Python portátil (python-build-standalone) -- unha por triple
# ---------------------------------------------------------------------

descargar_python() {
    # $1 = triple (ex. x86_64-pc-windows-msvc)   $2 = cartafol destino cacheado
    local triple="$1" destino="$2"
    if [ -d "$destino" ]; then return; fi
    log "Descargando Python portátil ($triple)..."
    local url="https://github.com/astral-sh/python-build-standalone/releases/download/${PY_TAG}/cpython-${PY_VERSION}%2B${PY_TAG}-${triple}-install_only.tar.gz"
    local tmp="$CACHE/runtime/_tmp_python.tar.gz"
    curl -Ls "$url" -o "$tmp"
    mkdir -p "$(dirname "$destino")"
    local extraido="$CACHE/runtime/_extraido_$$"
    mkdir -p "$extraido"
    tar xzf "$tmp" -C "$extraido"
    mv "$extraido/python" "$destino"
    rm -rf "$tmp" "$extraido"
}

# ---------------------------------------------------------------------
# Tesseract mínimo (binario + peche de bibliotecas + tessdata) por
# para Windows (plataforma conda win-64)
# ---------------------------------------------------------------------

descargar_tesseract() {
    # $1 = plataforma conda   $2 = cartafol destino cacheado
    local plataforma="$1" destino="$2"
    if [ -d "$destino" ]; then return; fi
    log "Construíndo o paquete mínimo de Tesseract ($plataforma)..."

    local env="$CACHE/runtime/_env_$plataforma"
    rm -rf "$env"
    "$MICROMAMBA" create -p "$env" -c conda-forge --platform "$plataforma" -y -q tesseract >/dev/null

    mkdir -p "$destino/bin" "$destino/tessdata"

    python3 "$INSTALADOR/bundle/resolve_deps_pe.py" "$env/Library/bin" tesseract.exe \
        | while read -r f; do cp "$env/Library/bin/$f" "$destino/bin/"; done
    for idioma in spa glg eng; do
        cp "$env/share/tessdata/$idioma.traineddata" "$destino/tessdata/"
    done
    rm -rf "$env"
}

# ---------------------------------------------------------------------
# Roda de paquetes de Python (.whl / .tar.gz) por plataforma pip
# ---------------------------------------------------------------------

descargar_wheels_comuns() {
    # $1 = etiqueta cacheada   $2.. = argumentos --platform/--python-version/etc. de pip
    local etiqueta="$1"; shift
    local destino="$CACHE/wheels/$etiqueta"
    if [ -d "$destino" ]; then return; fi
    log "Descargando paquetes de Python ($etiqueta)..."
    mkdir -p "$destino"
    python3 -m pip download --quiet --dest "$destino" "$@" --only-binary=:all: $PAQUETES_COMUNS
}

descargar_odfpy() {
    # odfpy non ten wheel compilado (é Python puro) -- descárgase unha soa
    # vez, sen restrición de plataforma, e reutilízase en tódolos paquetes
    local destino="$CACHE/wheels/_odfpy"
    if [ -d "$destino" ]; then return; fi
    mkdir -p "$destino"
    python3 -m pip download --quiet --dest "$destino" odfpy
}

descargar_proxy_tools() {
    # proxy_tools (dependencia transitiva de pywebview, TODAS as
    # plataformas) só publica distribución fonte en PyPI -- nunca tivo
    # wheel ningunha -- así que "--only-binary=:all:" (usado en
    # descargar_wheels_comuns) o descarta sempre con "No matching
    # distribution found". Mesmo principio ca odfpy: descárgase á parte,
    # sen esa restrición, unha soa vez. É un paquete pequeno e Python
    # puro (sen compilación), así que instala sen problema en calquera
    # plataforma igualmente.
    local destino="$CACHE/wheels/_proxy_tools"
    if [ -d "$destino" ]; then return; fi
    mkdir -p "$destino"
    python3 -m pip download --quiet --dest "$destino" proxy_tools
}

descargar_pywebview() {
    # pywebview en si mesmo TEN wheel universal ("py3-none-any"), pero
    # "--no-deps" evita que pip tente resolver as súas dependencias
    # CONDICIONAIS (pyobjc-* en Mac, pythonnet en Windows) -- ver
    # comentario en PAQUETES_COMUNS por que iso rompe a descarga
    # multiplataforma. "bottle" e "typing_extensions" son as súas
    # dependencias INCONDICIONAIS (tódalas plataformas), tamén wheel
    # universal -- descárganse xunto, unha soa vez, reutilizadas en
    # tódolos paquetes coma odfpy/proxy_tools.
    local destino="$CACHE/wheels/_pywebview"
    if [ -d "$destino" ]; then return; fi
    mkdir -p "$destino"
    python3 -m pip download --quiet --dest "$destino" --no-deps pywebview==6.2.1
    python3 -m pip download --quiet --dest "$destino" bottle==0.13.4 typing_extensions==4.16.0
}

descargar_extras_windows() {
    # pywin32 (requirements.txt, marcado "; sys_platform == win32"),
    # pywin32-ctypes (dependencia transitiva de keyring), colorama
    # (dependencia transitiva de wasabi, unha dependencia de spaCy) e
    # pythonnet (dependencia transitiva de pywebview en Windows -- fai a
    # ponte .NET có backend WebView2 da xanela de escritorio) -- tódalas
    # SÓ en Windows. "pip download --platform" filtra o formato do .whl
    # que descarga, pero avalía os marcadores condicionais das
    # dependencias TRANSITIVAS (coma estas) segundo a plataforma ONDE se
    # executa pip (Linux aquí), non a de destino -- por iso hai que
    # pedilas á man, unha por unha, en vez de confiar en que
    # "pip download" as atope soas. Se no futuro aparece outro ERROR
    # "Could not find a version" ao instalar nunha máquina real, case
    # sempre é outra dependencia condicional coma estas: engádea aquí.
    local destino="$CACHE/wheels/windows"
    mkdir -p "$destino"
    [ -n "$(ls "$destino"/pywin32-312-* 2>/dev/null)" ] \
        && [ -n "$(ls "$destino"/pywin32_ctypes-* 2>/dev/null)" ] \
        && [ -n "$(ls "$destino"/colorama-* 2>/dev/null)" ] \
        && [ -n "$(ls "$destino"/pythonnet-* 2>/dev/null)" ] && return
    python3 -m pip download --quiet --dest "$destino" --python-version 3.12 --platform win_amd64 \
        --implementation cp --abi cp312 --only-binary=:all: pywin32 pywin32-ctypes colorama pythonnet
}

# A versión do modelo TEN QUE corresponderse coa de spaCy fixada arriba
# (spacy==3.7.5 -> modelo 3.7.x; a serie 3.8.x pide spaCy >=3.8). Non é
# unha regra teórica: ata o 27/09/2026 este script baixaba o modelo 3.8.0
# xunto con spaCy 3.7.5, e os tres instaladores saíron con esa mestura.
# spaCy carga o modelo igual, só cun UserWarning que nun programa de
# escritorio non ve ninguén, pero DETECTA PEOR: o programa instalado en
# Windows marcaba coma persoa o membrete "XUNTA DE GALICIA" que a copia de
# desenvolvemento (modelo 3.7.0) deixa intacto. Comprobado comparando as
# dúas na VM. Se algún día se sobe spaCy, hai que subir tamén isto.
MODELO_IDIOMA="es_core_news_md-3.7.0"

descargar_modelo_idioma() {
    local destino="$CACHE/wheels/_modelo"
    if [ -f "$destino/${MODELO_IDIOMA}-py3-none-any.whl" ]; then return; fi
    mkdir -p "$destino"
    # non deixar aí modelos doutras versións: o instalador colle todo o
    # que haxa no cartafol e acabaría metendo dous modelos no paquete
    rm -f "$destino"/es_core_news_md-*.whl
    log "Descargando o modelo de idioma de spaCy ($MODELO_IDIOMA)..."
    curl -Ls -o "$destino/${MODELO_IDIOMA}-py3-none-any.whl" \
        "https://github.com/explosion/spacy-models/releases/download/${MODELO_IDIOMA}/${MODELO_IDIOMA}-py3-none-any.whl"
    # o .whl de spaCy declara en que versións de spaCy funciona: se non
    # casa coa fixada, é mellor fallar aquí ca publicar outro paquete que
    # detecte peor en silencio
    local esixido
    esixido=$(unzip -p "$destino/${MODELO_IDIOMA}-py3-none-any.whl" "*/meta.json" 2>/dev/null \
        | tr ',' '\n' | grep -m1 '"spacy_version"' | cut -d'"' -f4)
    log "O modelo pide spaCy: ${esixido:-descoñecido}"
    case "$esixido" in
        *">=3.7"*) : ;;
        "") log "AVISO: non se puido ler a versión de spaCy que pide o modelo." ;;
        *) log "ERRO: o modelo $MODELO_IDIOMA pide spaCy $esixido, pero o paquete leva spacy==3.7.5"; exit 1 ;;
    esac
}

# ---------------------------------------------------------------------
# Montaxe dun paquete
# ---------------------------------------------------------------------

copiar_fonte_limpa() {
    local destino="$1/anonimizador-xuridico"
    mkdir -p "$destino"
    cp -R "$RAIZ/src" "$destino/"
    cp -R "$RAIZ/config" "$destino/"
    cp -R "$RAIZ/ejemplos" "$destino/"
    cp "$RAIZ/requirements.txt" "$destino/"
    cp "$RAIZ/README.md" "$destino/"
    find "$destino" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    find "$destino" -name "*.pyc" -delete
}

# ---------------------------------------------------------------------
# Windows: instalador gráfico NSIS (un único .exe)
# ---------------------------------------------------------------------

convertir_sdists_a_wheel() {
    # odfpy e proxy_tools só existen en PyPI coma distribución fonte
    # (.tar.gz, Python puro). O instalador de Windows NON executa pip na
    # máquina de destino, así que convértense aquí, unha soa vez, a wheel
    # (un zip que se pode desempaquetar directamente en site-packages).
    # Cacheado en wheels/_sdist_wheels.
    local destino="$CACHE/wheels/_sdist_wheels"
    if [ -n "$(ls "$destino"/odfpy-*.whl 2>/dev/null)" ] && [ -n "$(ls "$destino"/proxy_tools-*.whl 2>/dev/null)" ]; then return; fi
    log "Convertendo odfpy e proxy_tools (sdist) a wheel..."
    mkdir -p "$destino"
    python3 -m pip wheel --quiet --no-deps --timeout 30 --retries 1 --wheel-dir "$destino" \
        "$CACHE/wheels/_odfpy/"odfpy-*.tar.gz "$CACHE/wheels/_proxy_tools/"proxy_tools-*.tar.gz
}

xerar_windows() {
    log "== Windows =="
    command -v makensis >/dev/null || { echo "ERRO: precísase 'makensis' (paquete nsis)."; exit 1; }
    descargar_python "x86_64-pc-windows-msvc" "$CACHE/runtime/python-windows"
    descargar_tesseract "win-64" "$CACHE/runtime/tesseract-windows"
    descargar_wheels_comuns "windows" --python-version 3.12 --platform win_amd64 --implementation cp --abi cp312
    descargar_extras_windows
    convertir_sdists_a_wheel

    # 1) Árbore FINAL a instalar (build/staging-windows): o Python portátil
    #    coas librarías xa desempaquetadas en site-packages (sen venv nin pip
    #    na máquina de destino), Tesseract, código, documentación e lanzador.
    local stage="$BUILD/staging-windows"
    rm -rf "$stage"; mkdir -p "$stage/runtime" "$stage/docs"
    # "cp -c" (clonado APFS, case instantáneo); se o sistema de ficheiros non
    # o soporta cae á copia normal.
    cp -Rc "$CACHE/runtime/python-windows" "$stage/runtime/python" 2>/dev/null \
        || { rm -rf "$stage/runtime/python"; cp -R "$CACHE/runtime/python-windows" "$stage/runtime/python"; }
    cp -Rc "$CACHE/runtime/tesseract-windows" "$stage/runtime/tesseract" 2>/dev/null \
        || { rm -rf "$stage/runtime/tesseract"; cp -R "$CACHE/runtime/tesseract-windows" "$stage/runtime/tesseract"; }
    python3 "$INSTALADOR/bundle/montar_site_packages.py" "$stage/runtime/python/Lib/site-packages" \
        "$CACHE/wheels/windows" "$CACHE/wheels/_sdist_wheels" "$CACHE/wheels/_odfpy" \
        "$CACHE/wheels/_pywebview" "$CACHE/wheels/_modelo"
    # Sobras que non fan falta para executar: símbolos de depuración (.pdb) e
    # o IDE/demos de Python.
    find "$stage/runtime/python" -maxdepth 1 -name "*.pdb" -delete
    rm -rf "$stage/runtime/python/Lib/idlelib" "$stage/runtime/python/Lib/turtledemo"
    copiar_fonte_limpa "$stage"
    # só as guías de usuario: as notas de versións antigas (04-07) quedan no
    # repo coma histórico, pero non van no paquete
    cp "$DOCS/"0[1-3]-*.pdf "$DOCS/"criterios_*.pdf "$stage/docs/"
    if [ -d "$DOCS/es" ]; then mkdir -p "$stage/docs/es"; cp "$DOCS/es/"*.pdf "$stage/docs/es/"; fi
    cp "$INSTALADOR/windows/Iniciar-Anonimizador.vbs" "$INSTALADOR/windows/anonimizador.ico" "$stage/"

    # 2) Lista de ficheiros para NSIS + compilación (cross-compile con makensis)
    local xerado="$BUILD/nsis"
    rm -rf "$xerado"; mkdir -p "$xerado"
    python3 "$INSTALADOR/windows/xerar_arbore_nsh.py" "$stage" "$xerado"
    # versión numérica a.b.c.d para as propiedades do .exe: AAAA.M.D.0
    local numerica="${_VERSION_DATA:0:4}.$((10#${_VERSION_DATA:4:2})).$((10#${_VERSION_DATA:6:2})).0"
    local saida="$RAIZ/Anonimizador-Xuridico-Instalador-${VERSION}.exe" extra=""
    if [ -n "${INSTALADOR_PROBA:-}" ]; then
        # so desenvolvemento: sen compresión, para iterar rápido (build/proba/)
        mkdir -p "$BUILD/proba"; saida="$BUILD/proba/Anonimizador-Xuridico-Instalador-PROBA.exe"; extra="-DPROBA=1"
    fi
    rm -f "$saida"
    log "Compilando o instalador (LZMA sobre ~$(du -sm "$stage" | cut -f1) MB; pode tardar varios minutos)..."
    # makensis (Unicode) le o script en UTF-8 só se a locale o é
    local loc="en_US.UTF-8"; if [ "$(uname -s)" = "Linux" ]; then loc="C.UTF-8"; fi
    LC_ALL="$loc" makensis -V2 $extra -DVERSION="$VERSION" -DVERSION_NUM="$numerica" -DXERADO="$xerado" \
        -DRECURSOS="$INSTALADOR/windows" -DSAIDA="$saida" "$INSTALADOR/windows/instalador.nsi"
    log "Xerado: $(basename "$saida") ($(du -sh "$saida" | cut -f1))"
}

# ---------------------------------------------------------------------
# Principal
# ---------------------------------------------------------------------

OBXECTIVO="${1:-todo}"
case "$OBXECTIVO" in
    windows|todo) ;;
    *) echo "Uso: $0 [windows]"; exit 1 ;;
esac

asegurar_ferramentas
descargar_odfpy
descargar_proxy_tools
descargar_pywebview
descargar_modelo_idioma

xerar_windows

echo
log "Feito ($OBXECTIVO). Os ficheiros xerados están en $RAIZ/"
