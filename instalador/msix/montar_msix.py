#!/usr/bin/env python3
"""Monta o cartafol do paquete MSIX a partir do árbore de Windows que xa
xera `crear-paquetes.sh` (build/staging-windows).

Uso: montar_msix.py <staging-windows> <destino>

O destino queda listo para `makeappx pack /d <destino>` (iso faise en
Windows, ver .github/workflows/msix.yml):
- todo o árbore menos o lanzador .vbs do instalador clásico;
- `anonimizador.pth` en site-packages, para que `python -m
  anonimizador.arranque_windows` atope o código (ruta relativa: o paquete
  instálase onde Windows queira);
- AppxManifest.xml coa versión do ficheiro VERSION (a.b.c -> a.b.c.0: a
  Store esixe o cuarto número a 0) e as iconas en Assets/.

Precisa Pillow (as iconas debúxanse con instalador/windows/xerar_icona.py).
"""
import shutil
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[1]
sys.path.insert(0, str(RAIZ / "instalador" / "windows"))

from PIL import Image  # noqa: E402

from xerar_icona import debuxar  # noqa: E402

_SEN_EMPAQUETAR = {"Iniciar-Anonimizador.vbs"}
# relativo a runtime\python\Lib\site-packages
_PTH = "..\\..\\..\\..\\anonimizador-xuridico\\src\n"


def version_msix() -> str:
    partes = (RAIZ / "VERSION").read_text(encoding="utf-8").strip().split(".")
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
                    or parte.endswith((".", " ")) or len(parte) > 255):
                malos.append(str(rel))
                break
        else:
            if len(str(rel)) > 200:
                malos.append(f"{rel} (ruta de {len(str(rel))} caracteres)")
    return malos


def iconas(assets: Path) -> None:
    assets.mkdir(parents=True, exist_ok=True)
    icona = debuxar()

    def cadrada(nome, lado):
        icona.resize((lado, lado), Image.LANCZOS).save(assets / nome)

    cadrada("Square44x44Logo.png", 44)
    cadrada("Square150x150Logo.png", 150)
    cadrada("StoreLogo.png", 50)
    ancha = Image.new("RGBA", (310, 150), (0, 0, 0, 0))
    ancha.paste(icona.resize((130, 130), Image.LANCZOS), (90, 10))
    ancha.save(assets / "Wide310x150Logo.png")


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    staging, destino = Path(sys.argv[1]), Path(sys.argv[2])
    if not (staging / "runtime" / "python" / "pythonw.exe").is_file():
        raise SystemExit(f"{staging} non parece o árbore de Windows (falta runtime/python/pythonw.exe)")
    shutil.rmtree(destino, ignore_errors=True)
    shutil.copytree(staging, destino, ignore=lambda d, nomes: [n for n in nomes if n in _SEN_EMPAQUETAR])
    (destino / "runtime" / "python" / "Lib" / "site-packages" / "anonimizador.pth").write_text(_PTH, encoding="ascii")
    version = version_msix()
    manifesto = (AQUI / "AppxManifest.xml").read_text(encoding="utf-8").replace("{VERSION}", version)
    (destino / "AppxManifest.xml").write_text(manifesto, encoding="utf-8")
    iconas(destino / "Assets")
    malos = nomes_invalidos(destino)
    if malos:
        raise SystemExit("Nomes que non admite un MSIX:\n  " + "\n  ".join(malos))
    print(f"Paquete montado en {destino} (versión {version})")


if __name__ == "__main__":
    main()
