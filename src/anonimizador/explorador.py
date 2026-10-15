"""Explorador de cartafoles da interface web (informe: "ao ir seleccionar
o cartafol, debería amosar os arquivos que hai nese cartafol, aínda que
non deixe seleccionalos").

O diálogo NATIVO de escoller cartafol (`selector.py`) só amosa cartafoles
-- é o comportamento do propio sistema operativo (Windows `askdirectory`,
Finder) e non se pode cambiar. Para ver tamén os ficheiros que hai dentro,
a interface ten o seu propio explorador: este módulo só ENUMERA o contido
dun cartafol (nunca le, move nin borra ficheiros) e a xanela modal de
`templates/index.html` móstrao. Os ficheiros aparecen en gris e non se
poden escoller -- só serven para que o usuario recoñeza o cartafol
correcto.

Igual có resto da app, só se serve en 127.0.0.1 (ver `web.executar`)."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from . import idioma
from .pipeline import EXTENSIONS_SOPORTADAS

# Marcador especial de "ruta": en Windows é a vista de UNIDADES (C:\, V:\...),
# que non ten ningún cartafol pai real; en Mac/Linux equivale á raíz "/".
EQUIPO = "@equipo"

_MAX_ENTRADAS = 5000  # un cartafol con máis non se amosa enteiro (sinálase ao usuario)
_NOME_CARTAFOL_INVALIDO = re.compile(r'[\\/:*?"<>|\x00-\x1f]')

_FILE_ATTRIBUTE_HIDDEN = 0x2


def _unidades_windows() -> list[str]:
    listar = getattr(os, "listdrives", None)  # Python 3.12+
    if listar is not None:
        return sorted(listar())
    import string

    return [f"{letra}:\\" for letra in string.ascii_uppercase if Path(f"{letra}:\\").exists()]


def _e_oculto(entrada: os.DirEntry) -> bool:
    if entrada.name.startswith("."):
        return True
    if sys.platform == "win32":
        try:
            return bool(entrada.stat().st_file_attributes & _FILE_ATTRIBUTE_HIDDEN)
        except (OSError, AttributeError):
            return False
    return False


def _atallos() -> list[dict]:
    """Sitios habituais para saltar dun golpe (só os que existen)."""
    casa = Path.home()
    candidatos = [
        (idioma.t("exp.inicio"), casa),
        (idioma.t("exp.documentos"), casa / "Documents"),
        (idioma.t("exp.documentos"), casa / "Documentos"),
        (idioma.t("exp.escritorio"), casa / "Desktop"),
        (idioma.t("exp.descargas"), casa / "Downloads"),
    ]
    atallos, vistos = [], set()
    for nome, ruta in candidatos:
        if ruta.is_dir() and str(ruta) not in vistos:
            vistos.add(str(ruta))
            atallos.append({"nome": nome, "ruta": str(ruta)})
    atallos.append({"nome": idioma.t("exp.este_equipo") if sys.platform == "win32" else idioma.t("exp.raiz"), "ruta": EQUIPO})
    return atallos


def _ruta_inicial() -> Path:
    casa = Path.home()
    for candidato in (casa / "Documents", casa / "Documentos", casa):
        if candidato.is_dir():
            return candidato
    return casa


def _pai(ruta: Path) -> str | None:
    pai = ruta.parent
    if pai != ruta:
        return str(pai)
    # xa é a raíz: en Windows sobe á vista de unidades; en Mac/Linux non hai máis arriba
    return EQUIPO if sys.platform == "win32" else None


def _resolver_existente(ruta: str | None) -> Path | None:
    """Ruta pedida -> cartafol existente máis próximo (se é un ficheiro,
    o cartafol que o contén; se non existe, o primeiro pai que si)."""
    if not ruta:
        return _ruta_inicial()
    # absoluta: "./datos_rexistro" (o valor por defecto do campo) é relativa ao
    # cartafol de traballo do programa, e amosar "." no explorador non serve de nada
    candidata = Path(os.path.abspath(Path(ruta).expanduser()))
    for _ in range(64):
        try:
            if candidata.is_dir():
                return candidata
        except OSError:
            pass
        if candidata.parent == candidata:
            return None
        candidata = candidata.parent
    return None


def listar(ruta: str | None) -> dict:
    """Contido dun cartafol para amosar no explorador. Devolve:

    - `ruta`: cartafol realmente listado ("" na vista de unidades);
    - `pai`: ruta á que sube "Subir" (ou `None` se non hai);
    - `entradas`: lista de {nome, tipo: "cartafol"|"ficheiro", soportado}
      -- cartafoles primeiro, ambos por orde alfabética sen distinguir
      maiúsculas;
    - `n_soportados` / `n_cartafoles`: contas deste nivel (o
      procesamento de cartafol é recursivo, pero contar todo o árbore
      tardaría en unidades de rede);
    - `truncado`: True se había máis de `_MAX_ENTRADAS` e non se amosan todas;
    - `erro`: mensaxe se non se puido ler (permisos...), senón `None`.
    """
    resposta = {
        "ruta": "", "pai": None, "entradas": [], "n_soportados": 0, "n_cartafoles": 0,
        "truncado": False, "erro": None, "atallos": _atallos(), "separador": os.sep,
    }

    if ruta == EQUIPO:
        if sys.platform == "win32":
            resposta["entradas"] = [
                {"nome": u, "tipo": "cartafol", "soportado": False} for u in _unidades_windows()
            ]
            resposta["n_cartafoles"] = len(resposta["entradas"])
            return resposta
        ruta = os.sep  # Mac/Linux: "Raíz" = "/"

    cartafol = _resolver_existente(ruta)
    if cartafol is None:
        resposta["erro"] = idioma.t("exp.non_existe", ruta=ruta)
        return resposta

    resposta["ruta"] = str(cartafol)
    resposta["pai"] = _pai(cartafol)

    cartafoles, ficheiros = [], []
    try:
        with os.scandir(cartafol) as it:
            for entrada in it:
                if _e_oculto(entrada):
                    continue
                try:
                    e_cartafol = entrada.is_dir()
                except OSError:
                    continue
                if e_cartafol:
                    cartafoles.append(entrada.name)
                else:
                    ficheiros.append(entrada.name)
                if len(cartafoles) + len(ficheiros) >= _MAX_ENTRADAS:
                    resposta["truncado"] = True
                    break
    except OSError as e:
        resposta["erro"] = idioma.t("exp.non_se_le", motivo=e.strerror or e)
        return resposta

    clave = str.casefold
    resposta["entradas"] = (
        [{"nome": n, "tipo": "cartafol", "soportado": False} for n in sorted(cartafoles, key=clave)]
        + [
            {
                "nome": n, "tipo": "ficheiro",
                "soportado": Path(n).suffix.lower() in EXTENSIONS_SOPORTADAS,
            }
            for n in sorted(ficheiros, key=clave)
        ]
    )
    resposta["n_cartafoles"] = len(cartafoles)
    resposta["n_soportados"] = sum(1 for e in resposta["entradas"] if e["soportado"])
    return resposta


def crear_cartafol(pai: str, nome: str) -> str:
    """Crea `nome` dentro de `pai` (botón "Nova carpeta" do explorador,
    útil para o cartafol de saída). Lanza `ValueError` cun texto amosable
    ao usuario se o nome non vale ou non se pode crear. Devolve a ruta
    do novo cartafol."""
    nome = (nome or "").strip()
    if not nome or nome in (".", "..") or _NOME_CARTAFOL_INVALIDO.search(nome) or nome.endswith((".", " ")):
        raise ValueError(idioma.t("exp.nome_non_valido"))
    base = Path(pai)
    if not base.is_dir():
        raise ValueError(idioma.t("exp.non_existe", ruta=pai))
    novo = base / nome
    if novo.exists():
        raise ValueError(idioma.t("exp.xa_existe", nome=nome))
    try:
        novo.mkdir()
    except OSError as e:
        raise ValueError(idioma.t("exp.non_se_crea", motivo=e.strerror or e)) from e
    return str(novo)
