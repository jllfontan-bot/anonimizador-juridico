#!/bin/bash
# Instalador para macOS del Anonimizador de expedientes jurídicos.
# Haz doble clic en este archivo para ejecutarlo (la primera vez, macOS puede
# pedir confirmación en Ajustes del Sistema > Privacidad y seguridad).
#
# Este paquete ya incluye Python y Tesseract (para Intel y Apple Silicon):
# no hace falta instalar nada más en el sistema ni conexión a internet.

set -e
RAIZ="$(cd "$(dirname "$0")" && pwd)"
cd "$RAIZ/anonimizador-xuridico"

if [ "$(uname -m)" = "arm64" ]; then
    ARQ="arm64"
else
    ARQ="x64"
fi

echo "======================================================"
echo " Instalador del Anonimizador de expedientes jurídicos"
echo "======================================================"
echo

echo "[1/3] Creando el entorno aislado de Python (.venv)..."
rm -rf .venv
"$RAIZ/runtime/python-$ARQ/bin/python3" -m venv .venv
source .venv/bin/activate

echo "[2/3] Instalando las librerías necesarias..."
pip install --quiet --no-index --find-links "$RAIZ/wheels" -r requirements.txt

echo "[3/3] Instalando el modelo de reconocimiento del idioma..."
pip install --quiet --no-index "$RAIZ"/wheels/es_core_news_md-*.whl

echo
echo "======================================================"
echo " Instalación completada correctamente."
echo " A partir de ahora, usa 'Iniciar-Anonimizador.command' para abrir el programa."
echo "======================================================"
read -p "Pulsa Intro para cerrar..."
