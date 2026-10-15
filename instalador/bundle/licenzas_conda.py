#!/usr/bin/env python3
"""Copia os textos de licenza dos paquetes de conda dos que saíron os
ficheiros dun cartafol (o Tesseract mínimo: bin/ e tessdata/).

Os textos non se instalan no contorno: quedan en `info/licenses` do paquete
desempaquetado na caché de micromamba, que cada `conda-meta/*.json` indica
en `extracted_package_dir`. Só se copian os dos paquetes que achegan algún
ficheiro de verdade ao cartafol, non os de todo o contorno.

Uso: licenzas_conda.py <contorno> <cartafol_copiado> <saida>
Deixa en <saida> un subcartafol <paquete>-<versión> por paquete e un
INDICE.txt con que ficheiros vén de cada un e a súa licenza.
"""
import json
import os
import shutil
import sys
from pathlib import Path


def main():
    contorno, copiado, saida = (Path(a) for a in sys.argv[1:4])
    ficheiros = {f.name.lower() for f in copiado.rglob("*") if f.is_file()}

    donos = {}
    for meta in sorted((contorno / "conda-meta").glob("*.json")):
        d = json.loads(meta.read_text(encoding="utf-8"))
        seus = sorted({os.path.basename(f.replace("\\", "/")) for f in d.get("files", [])
                       if os.path.basename(f.replace("\\", "/")).lower() in ficheiros})
        if seus:
            donos[f"{d['name']}-{d['version']}"] = (d, seus)

    sen_dono = ficheiros - {f.lower() for _, seus in donos.values() for f in seus}
    if sen_dono:
        sys.exit(f"ERRO: ficheiros sen paquete de conda coñecido: {sorted(sen_dono)}")

    saida.mkdir(parents=True, exist_ok=True)
    indice = []
    for nome, (d, seus) in sorted(donos.items()):
        orixe = Path(d["extracted_package_dir"]) / "info" / "licenses"
        if not orixe.is_dir():
            sys.exit(f"ERRO: {nome} non trae info/licenses ({orixe})")
        shutil.copytree(orixe, saida / nome)
        indice.append(f"{nome}  [{d.get('license', '?')}]\n    " + ", ".join(seus))
    (saida / "INDICE.txt").write_text(
        "Paquetes de conda-forge dos que saíron estes ficheiros e as súas licenzas.\n\n"
        + "\n".join(indice) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
