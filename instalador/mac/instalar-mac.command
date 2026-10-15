#!/bin/bash
# Instalador para macOS do Anonimizador de expedientes xurídicos.
# Fai dobre clic neste ficheiro para executalo (a primeira vez, macOS pode
# pedir confirmación en Preferencias do Sistema > Privacidade e seguridade).
#
# Este paquete xa inclúe Python e Tesseract (para Intel e Apple Silicon) --
# non fai falta instalar nada máis no sistema, nin conexión a internet.

set -e
RAIZ="$(cd "$(dirname "$0")" && pwd)"
cd "$RAIZ/anonimizador-xuridico"

if [ "$(uname -m)" = "arm64" ]; then
    ARQ="arm64"
else
    ARQ="x64"
fi

echo "======================================================"
echo " Instalador do Anonimizador de expedientes xurídicos"
echo "======================================================"
echo

echo "[1/3] Creando o ambiente illado de Python (.venv)..."
"$RAIZ/runtime/python-$ARQ/bin/python3" -m venv .venv
source .venv/bin/activate

echo "[2/3] Instalando as librarías necesarias..."
pip install --quiet --no-index --find-links "$RAIZ/wheels" -r requirements.txt

echo "[3/3] Instalando o modelo de recoñecemento de idioma..."
pip install --quiet --no-index "$RAIZ"/wheels/es_core_news_md-*.whl

echo
echo "======================================================"
echo " Instalación completada correctamente."
echo " A partir de agora, usa 'Iniciar-Anonimizador.command' para abrir o programa."
echo "======================================================"
read -p "Preme Intro para pechar..."
