#!/bin/bash
# Arranca el Anonimizador de expedientes jurídicos en una ventana de
# escritorio propia (sin navegador). Haz doble clic en este archivo para
# usarlo.

RAIZ="$(cd "$(dirname "$0")" && pwd)"
cd "$RAIZ/anonimizador-xuridico"

if [ ! -d ".venv" ]; then
    echo "ERROR: no se encuentra la instalación (.venv)."
    echo "Ejecuta primero 'instalar-mac.command'."
    read -p "Pulsa Intro para cerrar..."
    exit 1
fi

source .venv/bin/activate

# Los datos (registro cifrado de correspondencias y anonimizador.log) viven
# FUERA de la carpeta del programa, como en Windows (%LOCALAPPDATA%\Anonimizador):
# así actualizar o borrar el programa no los toca.
DATOS="$HOME/Library/Application Support/Anonimizador"
mkdir -p "$DATOS"
VIEJO="$RAIZ/anonimizador-xuridico/datos_rexistro"
if [ -d "$VIEJO" ] && [ ! -e "$DATOS/datos_rexistro" ]; then
    echo "Trasladando el registro de correspondencias a: $DATOS"
    mv "$VIEJO" "$DATOS/datos_rexistro" || { echo "ERROR: no se pudo trasladar el registro."; read -p "Pulsa Intro para cerrar..."; exit 1; }
elif [ -d "$VIEJO" ]; then
    echo "AVISO: hay dos registros de correspondencias:"
    echo "  - el que se usa:  $DATOS/datos_rexistro"
    echo "  - uno antiguo en: $VIEJO (no se usa; no lo borres sin revisarlo)"
fi

if [ "$(uname -m)" = "arm64" ]; then
    ARQ="arm64"
else
    ARQ="x64"
fi

PUERTO=5050
export TESSDATA_PREFIX="$RAIZ/runtime/tesseract-$ARQ/tessdata"
export PATH="$RAIZ/runtime/tesseract-$ARQ/bin:$PATH"

echo "======================================================"
echo " Anonimizador de expedientes jurídicos"
echo " Abriendo en ventana propia; para salir, cierra esa ventana."
echo "======================================================"

cd "$DATOS"
PYTHONPATH="$RAIZ/anonimizador-xuridico/src" python3 -m anonimizador.cli escritorio --porto $PUERTO --chaveiro-sistema
