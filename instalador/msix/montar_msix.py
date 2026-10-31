#!/usr/bin/env python3
"""Monta o cartafol do paquete MSIX a partir do árbore de Windows que xa
xera `crear-paquetes.sh` (build/staging-windows).

Uso: montar_msix.py <staging-windows> <destino> [anonimizador|conversor]

O destino queda listo para `makeappx pack /d <destino>` (iso faise en
Windows, ver .github/workflows/msix.yml):
- todo o árbore menos o lanzador .vbs do instalador clásico;
- `anonimizador.pth` en site-packages, para que `python -m
  anonimizador.arranque_windows` atope o código (ruta relativa: o paquete
  instálase onde Windows queira);
- AppxManifest.xml coa versión do ficheiro VERSION (a.b.c -> a.b.c.0: a
  Store esixe o cuarto número a 0) e as iconas en Assets/.

Co terceiro argumento `conversor` monta o paquete do Conversor de archivos
para IA, unha aplicación propia na Store co mesmo árbore: o seu manifesto
(`AppxManifest-conversor.xml`), a súa versión (`conversor.VERSION`) e a súa
icona.

Precisa Pillow (as iconas debúxanse con instalador/windows/xerar_icona.py).
"""
import re
import shutil
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[1]
sys.path.insert(0, str(RAIZ / "instalador" / "windows"))

from PIL import Image  # noqa: E402

from xerar_icona import debuxar, debuxar_conversor  # noqa: E402

# - o lanzador do instalador clásico;
# - a plantilla DESEMPAQUETADA de python-docx (leva un `[Content_Types].xml`,
#   nome reservado do propio formato do paquete: makeappx fallaba con
#   0x8007007b). En execución python-docx só usa `templates/default.docx`.
_SEN_EMPAQUETAR = {"Iniciar-Anonimizador.vbs", "default-docx-template"}
# Nomes que usa o propio formato do paquete (OPC/MSIX)
_NOMES_DO_PAQUETE = {"[content_types].xml", "appxblockmap.xml", "appxsignature.p7x", "appxmetadata"}
# relativo a runtime\python\Lib\site-packages
_PTH = "..\\..\\..\\..\\anonimizador-xuridico\\src\n"


# app -> (manifesto, función que le a versión a.b.c, icona)
def _version_anonimizador() -> str:
    return (RAIZ / "VERSION").read_text(encoding="utf-8").strip()


def _version_conversor() -> str:
    codigo = (RAIZ / "src" / "anonimizador" / "conversor.py").read_text(encoding="utf-8")
    atopada = re.search(r'^VERSION = "([^"]+)"$', codigo, re.M)
    if not atopada:
        raise SystemExit("Non se atopou VERSION en src/anonimizador/conversor.py")
    return atopada.group(1)


APPS = {
    "anonimizador": ("AppxManifest.xml", _version_anonimizador, debuxar),
    "conversor": ("AppxManifest-conversor.xml", _version_conversor, debuxar_conversor),
}


def version_msix(app: str = "anonimizador") -> str:
    partes = APPS[app][1]().split(".")
    if len(partes) != 3 or not all(p.isdigit() and int(p) <= 65535 for p in partes):
        raise SystemExit(f"VERSION ten que ser a.b.c (números <= 65535), non {partes!r}")
    return ".".join(partes) + ".0"


_RESERVADOS = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(10)), *(f"lpt{i}" for i in range(10))}
_PROHIBIDOS = set('<>:"|?*%') | {chr(i) for i in range(32)}


def nomes_invalidos(cartafol: Path) -> list[str]:
    """Rutas que Windows/makeappx non aceptan (makeappx só di 0x8007007b,
    sen dicir cal): nomes de dispositivo (CON, AUX... tamén con extensión),
    caracteres prohibidos, remate en punto ou espazo, ou rutas longas."""
    malos = []
    for ruta in cartafol.rglob("*"):
        rel = ruta.relative_to(cartafol)
        for parte in rel.parts:
            if (parte.split(".")[0].lower() in _RESERVADOS or set(parte) & _PROHIBIDOS
                    or (parte.lower() in _NOMES_DO_PAQUETE and rel != Path("AppxManifest.xml"))
                    or parte.endswith((".", " ")) or len(parte) > 255):
                malos.append(str(rel))
                break
        else:
            if len(str(rel)) > 200:
                malos.append(f"{rel} (ruta de {len(str(rel))} caracteres)")
    return malos


def iconas(assets: Path, debuxar_icona=debuxar) -> None:
    assets.mkdir(parents=True, exist_ok=True)
    icona = debuxar_icona()

    def cadrada(nome, lado):
        icona.resize((lado, lado), Image.LANCZOS).save(assets / nome)

    cadrada("Square44x44Logo.png", 44)
    cadrada("Square150x150Logo.png", 150)
    cadrada("StoreLogo.png", 50)
    ancha = Image.new("RGBA", (310, 150), (0, 0, 0, 0))
    ancha.paste(icona.resize((130, 130), Image.LANCZOS), (90, 10))
    ancha.save(assets / "Wide310x150Logo.png")


def main() -> None:
    if len(sys.argv) not in (3, 4) or (len(sys.argv) == 4 and sys.argv[3] not in APPS):
        raise SystemExit(__doc__)
    staging, destino = Path(sys.argv[1]), Path(sys.argv[2])
    app = sys.argv[3] if len(sys.argv) == 4 else "anonimizador"
    manifesto_orixe, _, debuxar_icona = APPS[app]
    if not (staging / "runtime" / "python" / "pythonw.exe").is_file():
        raise SystemExit(f"{staging} non parece o árbore de Windows (falta runtime/python/pythonw.exe)")
    shutil.rmtree(destino, ignore_errors=True)
    shutil.copytree(staging, destino, ignore=lambda d, nomes: [n for n in nomes if n in _SEN_EMPAQUETAR])
    (destino / "runtime" / "python" / "Lib" / "site-packages" / "anonimizador.pth").write_text(_PTH, encoding="ascii")
    version = version_msix(app)
    manifesto = (AQUI / manifesto_orixe).read_text(encoding="utf-8").replace("{VERSION}", version)
    (destino / "AppxManifest.xml").write_text(manifesto, encoding="utf-8")
    iconas(destino / "Assets", debuxar_icona)
    if app == "conversor":
        # O manual do conversor (`pantalla_conversor.MANUAL`) só vai no seu paquete.
        for pdf in [*(RAIZ / "docs").glob("10-*.pdf"), *(RAIZ / "docs" / "es").glob("10-*.pdf")]:
            copia = destino / "docs" / pdf.relative_to(RAIZ / "docs")
            copia.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(pdf, copia)
    malos = nomes_invalidos(destino)
    if malos:
        raise SystemExit("Nomes que non admite un MSIX:\n  " + "\n  ".join(malos))
    print(f"Paquete de {app} montado en {destino} (versión {version})")


if __name__ == "__main__":
    main()
