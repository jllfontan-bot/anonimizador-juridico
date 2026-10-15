#!/bin/bash
# Arranca o Anonimizador de expedientes xurídicos nunha xanela de
# escritorio propia (sen navegador). Fai dobre clic neste ficheiro para
# usalo.

RAIZ="$(cd "$(dirname "$0")" && pwd)"
cd "$RAIZ/anonimizador-xuridico"

if [ ! -d ".venv" ]; then
    echo "ERRO: non se atopa a instalación (.venv)."
    echo "Executa primeiro 'instalar-mac.command'."
    read -p "Preme Intro para pechar..."
    exit 1
fi

source .venv/bin/activate

# Os datos (rexistro cifrado de correspondencias e anonimizador.log) viven
# FÓRA do cartafol do programa, coma en Windows (%LOCALAPPDATA%\Anonimizador):
# así actualizar ou borrar o programa non os toca (04/10/2026).
DATOS="$HOME/Library/Application Support/Anonimizador"
mkdir -p "$DATOS"
VELLO="$RAIZ/anonimizador-xuridico/datos_rexistro"
if [ -d "$VELLO" ] && [ ! -e "$DATOS/datos_rexistro" ]; then
    echo "Trasladando o rexistro de correspondencias a: $DATOS"
    mv "$VELLO" "$DATOS/datos_rexistro" || { echo "ERRO: non se puido trasladar o rexistro."; read -p "Preme Intro para pechar..."; exit 1; }
elif [ -d "$VELLO" ]; then
    echo "AVISO: hai dous rexistros de correspondencias:"
    echo "  - o que se usa:   $DATOS/datos_rexistro"
    echo "  - un antigo en:   $VELLO (non se usa; non o borres sen revisalo)"
fi

if [ "$(uname -m)" = "arm64" ]; then
    ARQ="arm64"
else
    ARQ="x64"
fi

PORTO=5050
export TESSDATA_PREFIX="$RAIZ/runtime/tesseract-$ARQ/tessdata"
export PATH="$RAIZ/runtime/tesseract-$ARQ/bin:$PATH"

echo "======================================================"
echo " Anonimizador de expedientes xurídicos"
echo " Abrindo en xanela propia -- para pechar, pecha esa xanela."
echo "======================================================"

cd "$DATOS"
PYTHONPATH="$RAIZ/anonimizador-xuridico/src" python3 -m anonimizador.cli escritorio --porto $PORTO --chaveiro-sistema
