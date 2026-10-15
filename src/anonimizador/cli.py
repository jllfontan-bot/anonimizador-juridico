"""Interface de liña de comandos da proba de concepto.

Uso:
    python -m anonimizador.cli anonimizar entrada.txt --saida saida.txt \\
        --informe informe.json --rexistro ./datos_rexistro
"""

import argparse
import getpass
import json
from pathlib import Path

from .pipeline import anonimizar_e_gardar, anonimizar_zip, ruta_saida_por_defecto
from .registry import RexistroCorrespondencias, substituir_con_reintentos

_DESCRICION_ORIXE_CLAVE = {
    "ficheiro": "ficheiro local (clave.key)",
    "chaveiro_sistema": "chaveiro do sistema operativo",
}


def main():
    parser = argparse.ArgumentParser(prog="anonimizador")
    sub = parser.add_subparsers(dest="comando", required=True)

    _AXUDA_CHAVEIRO = (
        "Garda a clave de cifrado do rexistro no chaveiro do sistema operativo "
        "(macOS Keychain / Windows Credential Manager) en vez dun ficheiro local -- "
        "recomendado para uso real (informe, sección 07). Só afecta a rexistros NOVOS: "
        "un xa creado segue a usar onde xa gardase a súa clave. A primeira vez pode "
        "amosar un diálogo de autorización do propio sistema operativo."
    )

    p_anon = sub.add_parser("anonimizar", help="Anonimiza un documento")
    p_anon.add_argument("entrada", help="Ficheiro .txt ou .docx de entrada")
    p_anon.add_argument("--saida", default=None, help="Ficheiro de saida (por defecto, mesma extension ca entrada para .docx/.odt -- conserva formato -- e .anonimizado.txt nos demais casos)")
    p_anon.add_argument("--informe", default=None, help="Ficheiro JSON co informe de revision")
    p_anon.add_argument("--rexistro", default="./datos_rexistro", help="Cartafol do rexistro de correspondencias cifrado")
    p_anon.add_argument("--chaveiro-sistema", action="store_true", help=_AXUDA_CHAVEIRO)

    p_servir = sub.add_parser("servir", help="Abre a interface web local de revisión humana")
    p_servir.add_argument("--porto", type=int, default=5000)
    p_servir.add_argument("--chaveiro-sistema", action="store_true", help=_AXUDA_CHAVEIRO)

    p_escritorio = sub.add_parser(
        "escritorio",
        help="Coma 'servir', pero nunha xanela nativa de escritorio (pywebview) en vez de no navegador",
    )
    p_escritorio.add_argument("--porto", type=int, default=5000)
    p_escritorio.add_argument("--chaveiro-sistema", action="store_true", help=_AXUDA_CHAVEIRO)

    p_reverter = sub.add_parser(
        "reverter", help="Reversión controlada: recupera a identidade real dun código"
    )
    p_reverter.add_argument("codigo", help="Código a reverter, ex. PERSOA_000007")
    p_reverter.add_argument("--motivo", required=True, help="Xustificación (obrigatoria, queda na auditoría)")
    p_reverter.add_argument("--rexistro", default="./datos_rexistro")
    p_reverter.add_argument("--chaveiro-sistema", action="store_true", help=_AXUDA_CHAVEIRO)

    p_listar = sub.add_parser(
        "listar-correspondencias",
        help="Listado COMPLETO código↔persoa dun rexistro (acceso masivo: motivo, contrasinal e --confirmar)",
    )
    p_listar.add_argument("--motivo", required=True, help="Xustificación (obrigatoria, queda na auditoría)")
    p_listar.add_argument("--rexistro", default="./datos_rexistro")
    p_listar.add_argument("--desde", type=int, default=0, help="Saltar as N primeiras correspondencias")
    p_listar.add_argument("--limite", type=int, default=None, help="Amosar como moito N correspondencias")
    p_listar.add_argument(
        "--confirmar", action="store_true",
        help="Obrigatorio: confirma que entendes que isto amosa TODAS as identidades reais do rexistro",
    )
    p_listar.add_argument("--chaveiro-sistema", action="store_true", help=_AXUDA_CHAVEIRO)

    p_contrasinal = sub.add_parser(
        "contrasinal-reversion",
        help="Define ou cambia o contrasinal esixido para 'reverter' (segunda barreira, á parte da clave de cifrado)",
    )
    p_contrasinal.add_argument("--rexistro", default="./datos_rexistro")
    p_contrasinal.add_argument("--chaveiro-sistema", action="store_true", help=_AXUDA_CHAVEIRO)

    args = parser.parse_args()

    if args.comando == "anonimizar":
        rexistro = RexistroCorrespondencias(args.rexistro, usar_chaveiro=args.chaveiro_sistema)
        print(f"Clave de cifrado: {_DESCRICION_ORIXE_CLAVE[rexistro.orixe_clave]}")
        # o nome de ficheiro só se anonimiza DESPOIS de procesar o contido
        # (senón unha persoa mencionada nos dous sitios, con DNI, podería
        # acabar con dous códigos distintos -- ver nota en `web._procesar_automatico`);
        # se o usuario indicou `--saida` a man, respétase tal cal.
        saida_explicita = args.saida is not None
        saida = args.saida or ruta_saida_por_defecto(args.entrada)

        if Path(args.entrada).suffix.lower() == ".zip":
            resultado = anonimizar_zip(args.entrada, saida, rexistro)
            if not saida_explicita:
                saida_final = ruta_saida_por_defecto(args.entrada, rexistro=rexistro)
                if saida_final != saida:
                    substituir_con_reintentos(Path(saida), Path(saida_final))
                    saida = saida_final
            print(f"Arquivo anonimizado -> {saida}")
            if args.informe:
                Path(args.informe).write_text(
                    json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print(f"Informe de revision -> {args.informe}")
            for nome, informe in resultado["ficheiros"].items():
                n_marcados = sum(1 for p in informe["persoas"] if p["marcado_para_revision"])
                n_risco = sum(1 for r in informe.get("risco_residual", []) if r["confianza"] == "alta")
                aviso_risco = f" -- ⚠ {n_risco} posible(s) fuga(s) sen detectar" if n_risco else ""
                n_especial = len(informe.get("categoria_especial", []))
                aviso_especial = f" -- {n_especial} dato(s) de categoría especial" if n_especial else ""
                print(f"  {nome}: {len(informe['persoas'])} persoa(s) ({n_marcados} marcadas){aviso_risco}{aviso_especial}")
            if resultado["omitidos"]:
                print("Ficheiros OMITIDOS do zip de saida (formato non analizable):")
                for nome in resultado["omitidos"]:
                    print(f"  {nome}")
            return

        texto_anon, informe = anonimizar_e_gardar(args.entrada, saida, rexistro)
        if not saida_explicita:
            saida_final = ruta_saida_por_defecto(
                args.entrada,
                rexistro=rexistro,
                persoas_do_documento=informe["persoas"],
                ruta_provisional_propia=saida,
            )
            if saida_final != saida:
                substituir_con_reintentos(Path(saida), Path(saida_final))
                saida = saida_final
        print(f"Documento anonimizado -> {saida}")

        if args.informe:
            Path(args.informe).write_text(
                json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"Informe de revision -> {args.informe}")

        n_marcados = sum(1 for p in informe["persoas"] if p["marcado_para_revision"])
        n_mosaico = len(informe["riscos_mosaico"])
        risco_residual = informe.get("risco_residual", [])
        n_risco_alto = sum(1 for r in risco_residual if r["confianza"] == "alta")
        n_risco_baixo = len(risco_residual) - n_risco_alto
        print(f"Persoas detectadas: {len(informe['persoas'])} ({n_marcados} marcadas para revision)")
        print(f"Riscos de efecto mosaico detectados: {n_mosaico}")
        categoria_especial = informe.get("categoria_especial", [])
        if categoria_especial:
            print(f"Datos de categoría especial (saúde, relixión, orientación sexual, afiliación sindical): {len(categoria_especial)}")
            for a in categoria_especial:
                print(f'   - [{a["categoria"]}] "{a["termo"]}" -- ...{a["contexto"]}...')
        if n_risco_alto:
            print(f"⚠ POSIBLES FUGAS SEN DETECTAR: {n_risco_alto} (revisa o documento final a man antes de darllo por bo)")
            for r in risco_residual:
                if r["confianza"] == "alta":
                    print(f'   - "{r["texto"]}" -- ...{r["contexto"]}...')
        if n_risco_baixo:
            print(f"  ({n_risco_baixo} revision(s) opcional(is) mais de confianza baixa -- ver --informe)")

    elif args.comando == "servir":
        from .web import executar
        print(f"Interface de revision en http://127.0.0.1:{args.porto} (so nesta maquina)")
        executar(porto=args.porto, usar_chaveiro=args.chaveiro_sistema)

    elif args.comando == "escritorio":
        from .desktop import executar as executar_escritorio
        executar_escritorio(porto=args.porto, usar_chaveiro=args.chaveiro_sistema)

    elif args.comando == "reverter":
        rexistro = RexistroCorrespondencias(args.rexistro, usar_chaveiro=args.chaveiro_sistema)
        print(f"Clave de cifrado: {_DESCRICION_ORIXE_CLAVE[rexistro.orixe_clave]}")
        if not rexistro.ten_contrasinal_reversion():
            print(
                "Erro: aínda non hai contrasinal de reversión definido. "
                "Execute primeiro 'anonimizador contrasinal-reversion "
                f"--rexistro {args.rexistro}'."
            )
            return
        contrasinal = getpass.getpass("Contrasinal de reversión: ")
        try:
            dados = rexistro.reverter(
                args.codigo, args.motivo, contrasinal, solicitante=getpass.getuser()
            )
        except (KeyError, ValueError) as e:
            print(f"Erro: {e}")
            return
        print("ATENCION: accion de alto risco -- reversion de pseudonimizacion")
        print(f"  Codigo solicitado : {dados['codigo_solicitado']}")
        if dados["codigo_actual"] != dados["codigo_solicitado"]:
            print(f"  Codigo vixente    : {dados['codigo_actual']} (fusionado)")
        print(f"  Nome(s)           : {', '.join(dados['nomes'])}")
        print(f"  DNI               : {dados['dni'] or '(non rexistrado)'}")
        print(f"  Contexto          : {dados['contexto'] or '(ningun)'}")
        print("Esta consulta quedou rexistrada na auditoria cifrada do rexistro.")

    elif args.comando == "listar-correspondencias":
        rexistro = RexistroCorrespondencias(args.rexistro, usar_chaveiro=args.chaveiro_sistema)
        print(f"Clave de cifrado: {_DESCRICION_ORIXE_CLAVE[rexistro.orixe_clave]}")
        if not args.confirmar:
            print(
                "Isto amosa TODAS as identidades reais deste rexistro de golpe. "
                "Repita o comando engadindo --confirmar se é o que quere facer."
            )
            return
        if not rexistro.ten_contrasinal_reversion():
            print(
                "Erro: aínda non hai contrasinal de reversión definido. "
                "Execute primeiro 'anonimizador contrasinal-reversion "
                f"--rexistro {args.rexistro}'."
            )
            return
        contrasinal = getpass.getpass("Contrasinal de reversión: ")
        try:
            resultado = rexistro.listar_correspondencias(
                args.motivo, contrasinal, solicitante=getpass.getuser(),
                desde=args.desde, limite=args.limite,
            )
        except (KeyError, ValueError) as e:
            print(f"Erro: {e}")
            return
        print("ATENCION: accion de alto risco -- LISTADO COMPLETO de correspondencias")
        print(
            f"Rexistro: {args.rexistro} -- {resultado['total']} correspondencia(s), "
            f"amosando {len(resultado['entradas'])} (desde {resultado['desde']})"
        )
        if not resultado["entradas"]:
            print("(rexistro baleiro)")
        for e in resultado["entradas"]:
            fusionados = ", ".join(e["fusionados"]) if e["fusionados"] else "-"
            print(
                f"  {e['codigo']:<15} {e['codigo_id']:<15} "
                f"{', '.join(e['nomes']):<30} {e['dni'] or '(non rexistrado)':<12} "
                f"{e['contexto'] or '-':<10} {(e['creado'] or '-')[:10]:<12} {fusionados}"
            )
        if resultado["alias_orfos"]:
            print(f"Códigos fusionados sen destino no rexistro: {', '.join(resultado['alias_orfos'])}")
        print("Esta consulta quedou rexistrada na auditoria cifrada do rexistro coma acceso masivo.")

    elif args.comando == "contrasinal-reversion":
        rexistro = RexistroCorrespondencias(args.rexistro, usar_chaveiro=args.chaveiro_sistema)
        xa_existe = rexistro.ten_contrasinal_reversion()
        actual = getpass.getpass("Contrasinal actual: ") if xa_existe else None
        nova = getpass.getpass("Novo contrasinal de reversion (minimo 8 caracteres): ")
        confirmacion = getpass.getpass("Repite o novo contrasinal: ")
        if nova != confirmacion:
            print("Erro: os dous contrasinais non coinciden.")
            return
        try:
            rexistro.definir_contrasinal_reversion(nova, actual=actual)
        except ValueError as e:
            print(f"Erro: {e}")
            return
        print("Contrasinal de reversion definido correctamente.")
        print()
        print("IMPORTANTE -- garda estes DOUS ficheiros nun lugar seguro (non son o mesmo):")
        print(f"  - {Path(args.rexistro) / 'rexistro.enc'}  (as identidades reais, cifradas)")
        if rexistro.orixe_clave == "ficheiro":
            print(f"  - {Path(args.rexistro) / 'clave.key'}  (a CLAVE que as abre -- sen ela, NUNCA se poden recuperar)")
        else:
            print("  - a clave de cifrado vive no chaveiro do sistema operativo, non nun ficheiro local")
        print(
            "Este contrasinal é unha segunda barreira só a nivel de aplicación: "
            "non substitúe gardar ben ese ficheiro de clave."
        )


if __name__ == "__main__":
    main()
