"""Liña de comandos do conversor a .md para IA (`conversor.py`).

Uso:
    python -m anonimizador.cli_conversor ARQUIVO|CARTAFOL|ZIP \\
        [--anonimizar] [--un-solo-md] [--saida DIR] [--rexistro DIR]
        [--sen-aforro] [--trocear TOKENS]

Sen `--anonimizar` non se carga o NER (spaCy). Con el, a anonimización é
AUTOMÁTICA, sen revisión humana, e avísase diso: a revisión chegará coa
pantalla do conversor. O rexistro por defecto é o do anonimizador da
Store, para que cada persoa teña o mesmo código nos dous programas.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import aforro_ia, conversor, idioma


def main(argv: list | None = None) -> int:
    t = idioma.t
    parser = argparse.ArgumentParser(prog="conversor", description=t("conversor.cli.descricion"))
    parser.add_argument("entrada", help=t("conversor.cli.axuda_entrada"))
    parser.add_argument("--anonimizar", action="store_true", help=t("conversor.cli.axuda_anonimizar"))
    parser.add_argument("--un-solo-md", "--un-so-md", dest="un_so_md", action="store_true",
                        help=t("conversor.cli.axuda_un_so_md"))
    parser.add_argument("--saida", default=None, help=t("conversor.cli.axuda_saida"))
    parser.add_argument("--rexistro", default=None,
                        help=t("conversor.cli.axuda_rexistro", ruta=conversor.rexistro_por_defecto()))
    parser.add_argument("--chaveiro-sistema", action="store_true", help=t("conversor.cli.axuda_chaveiro"))
    parser.add_argument("--sen-aforro", dest="aforro", action="store_false", help=t("conversor.cli.axuda_sen_aforro"))
    parser.add_argument("--trocear", type=int, default=None, metavar="TOKENS", help=t("conversor.cli.axuda_trocear"))
    args = parser.parse_args(argv)

    if not Path(args.entrada).exists():
        parser.error(t("conversor.cli.non_existe", ruta=args.entrada))

    rexistro = None
    if args.anonimizar:
        from .registry import RexistroCorrespondencias

        print(t("conversor.cli.aviso_automatico"))
        cartafol_rexistro = Path(args.rexistro) if args.rexistro else conversor.rexistro_por_defecto()
        # No rexistro por defecto, coma o anonimizador da Store: clave dun
        # rexistro novo no chaveiro (un xa creado segue onde estea a súa).
        rexistro = RexistroCorrespondencias(
            cartafol_rexistro, usar_chaveiro=args.chaveiro_sistema or args.rexistro is None
        )
        print(t("conversor.cli.rexistro", ruta=cartafol_rexistro))
    else:
        print(t("conversor.cli.aviso_sen_anonimizar"))

    resultado = conversor.converter(
        args.entrada, anonimizar=args.anonimizar, un_so_md=args.un_so_md, saida=args.saida, rexistro=rexistro,
        aforro=args.aforro,
        caracteres_por_parte=round(args.trocear * aforro_ia.CARACTERES_POR_TOKEN) if args.trocear else None,
    )

    for ruta in resultado.saidas:
        print(t("conversor.cli.saida", ruta=ruta))
    if resultado.saidas:
        print(resultado.resumo_tokens())
    for nome, avisos in resultado.avisos.items():
        print(t("conversor.cli.avisos", nome=nome))
        for aviso in avisos:
            print(t("conversor.cli.aviso", aviso=aviso))
    for nome, informe in resultado.informes.items():
        marcadas = sum(1 for p in informe["persoas"] if p["marcado_para_revision"])
        print(t("conversor.cli.informe", nome=nome, persoas=len(informe["persoas"]), marcadas=marcadas))
        fugas = sum(1 for r in informe.get("risco_residual", []) if r["confianza"] == "alta")
        if fugas:
            print(t("conversor.cli.fugas", nome=nome, n=fugas))
    if resultado.omitidos:
        print(t("conversor.cli.omitidos"))
        for nome, motivo in resultado.omitidos:
            print(t("conversor.cli.omitido", nome=nome, motivo=t("conversor.motivo." + motivo)))
            if nome in resultado.erros:
                print(t("conversor.cli.erro", erro=resultado.erros[nome]))
    if not resultado.saidas:
        print(t("conversor.cli.nada"))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
