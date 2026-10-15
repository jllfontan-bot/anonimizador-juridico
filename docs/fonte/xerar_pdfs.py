#!/usr/bin/env python3
"""Xera os PDF de documentación a partir dos HTML de docs/fonte/.

    python3 docs/fonte/xerar_pdfs.py            # todos
    python3 docs/fonte/xerar_pdfs.py 02 03      # só algúns (01, 02, 03, 04, 05, 06, 07, leeme, 01es, 02es, 03es, leemees)

Imprime cada HTML a PDF con Chrome/Chromium en modo headless (o mesmo
método co que se fixeron os PDF orixinais). Non precisa instalar nada: só
un Chrome, Chromium ou Edge. Ruta propia: variable de contorno CHROME.

  01-caracteristicas-tecnicas-e-seguridade.html -> docs/01-Caracteristicas-tecnicas-e-seguridade.pdf
  02-guia-de-instalacion.html                   -> docs/02-Guia-de-instalacion.pdf
  03-manual-de-uso.html                         -> docs/03-Manual-de-uso.pdf
  leeme.html                                    -> instalador/LEEME.pdf  (mesmo contido ca instalador/LEEME.txt)
  (en castelán: *.es.html -> docs/es/, e leeme.es.html -> instalador/LEEME.es.pdf, igual ca LEEME.es.txt)

As imaxes están en docs/fonte/img/. As capturas da interface web fanse con
docs/fonte/capturar_pantallas.py (datos sintéticos). As do asistente de
instalación, SmartScreen e desinstalador de Windows son capturas reais feitas
a man nunha máquina virtual Windows 11 co instalador real.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

FONTE = Path(__file__).resolve().parent
RAIZ = FONTE.parents[1]

DOCUMENTOS = {
    "01": ("01-caracteristicas-tecnicas-e-seguridade.html", RAIZ / "docs" / "01-Caracteristicas-tecnicas-e-seguridade.pdf"),
    "02": ("02-guia-de-instalacion.html", RAIZ / "docs" / "02-Guia-de-instalacion.pdf"),
    "03": ("03-manual-de-uso.html", RAIZ / "docs" / "03-Manual-de-uso.pdf"),
    "04": ("04-novidades.html", RAIZ / "docs" / "04-Novidades-outubro-2026.pdf"),
    "05": ("05-estatistica-20261011.html", RAIZ / "docs" / "05-Estatistica-version-20261011.pdf"),
    "06": ("06-novidades.html", RAIZ / "docs" / "06-Novidades-segunda-version-11-outubro-2026.pdf"),
    "07": ("07-novidades.html", RAIZ / "docs" / "07-Novidades-version-12-outubro-2026.pdf"),
    "leeme": ("leeme.html", RAIZ / "instalador" / "LEEME.pdf"),
    # en castelán
    "01es": ("01-caracteristicas-tecnicas-y-seguridad.es.html", RAIZ / "docs" / "es" / "01-Caracteristicas-tecnicas-y-seguridad.pdf"),
    "02es": ("02-guia-de-instalacion.es.html", RAIZ / "docs" / "es" / "02-Guia-de-instalacion.pdf"),
    "03es": ("03-manual-de-uso.es.html", RAIZ / "docs" / "es" / "03-Manual-de-uso.pdf"),
    "leemees": ("leeme.es.html", RAIZ / "instalador" / "LEEME.es.pdf"),
}

CANDIDATOS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]


def buscar_chrome() -> str:
    if os.environ.get("CHROME"):
        return os.environ["CHROME"]
    for c in CANDIDATOS:
        if os.path.isabs(c) and os.path.exists(c):
            return c
        if not os.path.isabs(c) and shutil.which(c):
            return shutil.which(c)
    sys.exit("Non se atopou Chrome/Chromium/Edge. Indica a ruta coa variable CHROME.")


def imprimir(chrome: str, html: Path, saida: Path) -> None:
    saida.parent.mkdir(parents=True, exist_ok=True)
    if saida.exists():
        saida.unlink()
    with tempfile.TemporaryDirectory() as perfil:  # perfil novo: nada de cachés nin extensións
        cmd = [chrome, "--headless=new", "--disable-gpu", "--no-sandbox", f"--user-data-dir={perfil}",
               "--no-pdf-header-footer", f"--print-to-pdf={saida}", html.as_uri()]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Algunhas versións de Chrome escriben o PDF pero non rematan o proceso:
        # agárdase a que o ficheiro exista e deixe de medrar, e entón péchase.
        tamano, estable, inicio = -1, 0, time.time()
        while time.time() - inicio < 180:
            if saida.exists():
                actual = saida.stat().st_size
                estable = estable + 1 if actual == tamano and actual > 0 else 0
                tamano = actual
                if estable >= 4:
                    break
            elif proc.poll() is not None:
                break
            time.sleep(0.5)
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(10)
            except subprocess.TimeoutExpired:
                proc.kill()
    if not saida.exists() or saida.stat().st_size == 0:
        sys.exit(f"Non se puido xerar {saida}")
    print(f"xerado: {os.path.relpath(saida, RAIZ)} ({saida.stat().st_size // 1024} KB)")


def main() -> None:
    escollidos = sys.argv[1:] or list(DOCUMENTOS)
    chrome = buscar_chrome()
    for clave in escollidos:
        if clave not in DOCUMENTOS:
            sys.exit(f"Documento descoñecido: {clave} (opcións: {', '.join(DOCUMENTOS)})")
        html, saida = DOCUMENTOS[clave]
        imprimir(chrome, FONTE / html, saida)


if __name__ == "__main__":
    main()
