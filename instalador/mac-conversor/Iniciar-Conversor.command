#!/bin/bash
# Arranca el Conversor de archivos para IA en una ventana propia (sin
# navegador ni servidor: no abre ningún puerto). Haz doble clic en este
# archivo para usarlo.
#
# La carpeta de trabajo (registro cifrado compartido con el anonimizador y
# preferencias) es ~/Documents/Anonimizador, como en Windows: la pone el
# propio programa.

RAIZ="$(cd "$(dirname "$0")" && pwd)"
cd "$RAIZ/anonimizador-xuridico"

if [ ! -d ".venv" ]; then
    echo "ERROR: no se encuentra la instalación (.venv)."
    echo "Ejecuta primero 'instalar-mac.command'."
    read -p "Pulsa Intro para cerrar..."
    exit 1
fi

source .venv/bin/activate

if [ "$(uname -m)" = "arm64" ]; then
    ARQ="arm64"
else
    ARQ="x64"
fi

export TESSDATA_PREFIX="$RAIZ/runtime/tesseract-$ARQ/tessdata"
export PATH="$RAIZ/runtime/tesseract-$ARQ/bin:$PATH"

echo "======================================================"
echo " Conversor de archivos para IA"
echo " Abriendo en ventana propia; para salir, cierra esa ventana."
echo "======================================================"

PYTHONPATH="$RAIZ/anonimizador-xuridico/src" python3 -m anonimizador.pantalla_conversor
