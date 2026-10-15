#!/bin/bash
# Instalador para Linux/Ubuntu do Anonimizador de expedientes xurídicos.
# Executa: ./instalar-linux.sh (dando antes permiso de execución se fai falta:
# chmod +x instalar-linux.sh)
#
# Este paquete xa inclúe Python e Tesseract -- non fai falta instalar nada
# máis no sistema, nin conexión a internet durante a instalación.

set -e
RAIZ="$(cd "$(dirname "$0")" && pwd)"
cd "$RAIZ/anonimizador-xuridico"

echo "======================================================"
echo " Instalador do Anonimizador de expedientes xurídicos"
echo "======================================================"
echo

echo "[1/3] Creando o ambiente illado de Python (.venv)..."
"$RAIZ/runtime/python/bin/python3" -m venv .venv
source .venv/bin/activate

echo "[2/3] Instalando as librarías necesarias..."
pip install --quiet --no-index --find-links "$RAIZ/wheels" -r requirements.txt

echo "[3/3] Instalando o modelo de recoñecemento de idioma..."
pip install --quiet --no-index "$RAIZ"/wheels/es_core_news_md-*.whl

# En GNOME (Ubuntu), facer DOBLE CLIC nun .sh NON o executa: ábreo no editor
# de texto -- pasoulle ao usuario o 25/09/2026, que viu o script aberto no vim
# en vez de arrincar o programa. Ademais, se o paquete se descomprime nun
# pendrive exFAT/FAT (é o medio habitual aquí), pérdese o permiso de
# execución. Por iso se crea unha entrada de escritorio: iso si se abre cun
# clic dende o menú de aplicacións, e non depende dos permisos do .sh.
echo "[4/4] Creando a entrada no menú de aplicacións..."
chmod +x "$RAIZ/Iniciar-Anonimizador.sh" "$RAIZ/instalar-linux.sh" 2>/dev/null || true
LANZADOR="$HOME/.local/share/applications/anonimizador-xuridico.desktop"
mkdir -p "$(dirname "$LANZADOR")"
ICONA="$RAIZ/anonimizador-xuridico/src/anonimizador/static/anonimizador.png"
cat > "$LANZADOR" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Anonimizador de expedientes xurídicos
Comment=Anonimiza documentos xurídicos (PDF, .docx, .odt, .txt)
Exec=bash "$RAIZ/Iniciar-Anonimizador.sh"
Path=$RAIZ
Terminal=true
Categories=Office;Utility;
DESKTOP
[ -f "$ICONA" ] && echo "Icon=$ICONA" >> "$LANZADOR"
chmod +x "$LANZADOR"
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo
echo "======================================================"
echo " Instalación completada correctamente."
echo
echo " Para abrir o programa, calquera destas dúas:"
echo "   - busca \"Anonimizador\" no menú de aplicacións (recomendado);"
echo "   - ou, nun terminal: bash \"$RAIZ/Iniciar-Anonimizador.sh\""
echo
echo " (Facer DOBLE CLIC no ficheiro .sh dende o explorador de ficheiros"
echo "  NON o executa: Ubuntu ábreo no editor de texto.)"
echo "======================================================"
read -p "Preme Intro para pechar..."
