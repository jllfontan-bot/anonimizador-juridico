"""Rexistro de correspondencias codigo<->persoa.

E o unico compoñente que ve identidades reais (informe, seccion 03 e 07):
gardase cifrado en repouso (Fernet/AES), cun ficheiro de clave separado con
permisos restrinxidos (ou, opcionalmente, gardada no chaveiro do sistema
operativo -- ver `_cargar_ou_crear_clave`), e cada resolucion queda nun
rexistro de auditoria tamen cifrado. A xeracion de codigos usa un contador
propio (nunca un hash do nome) para garantir unicidade por construcion.

Regra de deseno: sen DNI que o confirme, dous nomes identicos NUNCA se
fusionan automaticamente -- creanse rexistros distintos marcados para
revision humana.

Garantía de concorrencia: varias instancias sobre o MESMO cartafol (fíos
da interface web, CLI e aplicación á vez, varios procesos) nunca repiten
un código nin perden cambios unhas doutras. Toda operación pública
(modificacións E lecturas) faise baixo un bloqueo exclusivo:
  - entre procesos, cun ficheiro de bloqueo `rexistro.lock` no propio
    cartafol (`fcntl.flock` en macOS/Linux, `msvcrt.locking` en Windows;
    o sistema operativo sóltao só se o proceso morre);
  - entre fíos do mesmo proceso, cun `threading.RLock` compartido por
    TODAS as instancias dese cartafol (reentrante: un método público
    pode chamar a outro).
Dentro do bloqueo recárgase o estado desde disco se o ficheiro cambiou
(outra instancia ou proceso gardou), modifícase e gárdase (escritura
atómica: `.tmp` + renomeamento) ANTES de soltalo. Así o contador
`seguinte_numero` sempre parte do último valor gardado. O mesmo vale
para `sesions.enc` (ler-modificar-escribir) e para as liñas de
`auditoria.enc`. A creación dunha clave nova tamén vai baixo o bloqueo,
para que dous procesos que abren a vez un rexistro novo non xeren
claves distintas. Límite coñecido: o bloqueo é consultivo -- só o
respectan instancias deste código; e en cartafoles de rede (SMB/NFS) o
bloqueo depende do servidor.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
import errno
import threading
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet

from .resolution import Grupo, normalizar

if os.name == "nt":
    import msvcrt
    fcntl = None
else:
    import fcntl
    msvcrt = None

_ERRNO_SEN_SOPORTE = {
    getattr(errno, n) for n in ("ENOTSUP", "EOPNOTSUPP", "ENOLCK", "EINVAL") if hasattr(errno, n)
}

_ITERACIONS_PBKDF2 = 200_000
_LONXITUDE_MINIMA_CONTRASINAL = 8


def _hash_contrasinal(contrasinal: str, sal: bytes) -> str:
    derivado = hashlib.pbkdf2_hmac("sha256", contrasinal.encode("utf-8"), sal, _ITERACIONS_PBKDF2)
    return derivado.hex()

try:
    import keyring
    _KEYRING_DISPONIBLE = True
except ImportError:  # a libraria e opcional -- sen ela, reserva a ficheiro
    keyring = None
    _KEYRING_DISPONIBLE = False

# Nome de servizo baixo o que se garda a clave no chaveiro do sistema
# (macOS Keychain, Windows Credential Manager, ou SecretService en Linux --
# `keyring` escolle o backend correcto para cada sistema operativo).
_SERVIZO_CHAVEIRO = "anonimizador-xuridico"


def normalizar_dni(dni: str) -> str:
    return dni.upper().replace(" ", "").replace("-", "")


def substituir_con_reintentos(tmp: Path, destino: Path) -> None:
    """`tmp.replace(destino)`, pero con reintentos -- en Windows (nunca en
    Mac/Linux) un antivirus ou o indexador de ficheiros pode abrir por un
    instante un ficheiro recen escrito xusto antes de renomealo, e o
    renomeamento falla con "PermissionError: [WinError 32] ... está sendo
    utilizado por outro proceso" aínda que ningún código propio o teña
    aberto. É sempre transitorio (confirmado en vivo: o mesmo renomeamento
    que falla varias veces seguidas remata por funcionar sen máis cambios)."""
    agarda = 0.05
    for intento in range(8):
        try:
            tmp.replace(destino)
            return
        except PermissionError:
            if intento == 7:
                raise
            time.sleep(agarda)
            agarda = min(agarda * 2, 1.0)


class _BloqueoCartafol:
    """Bloqueo exclusivo dun cartafol de rexistro, compartido por TODAS as
    instancias do proceso que usan ese cartafol (ver `_bloqueo_para`).
    Reentrante no mesmo fío: o ficheiro de bloqueo só se bloquea na
    primeira entrada e só se solta na última saída."""

    def __init__(self, ruta_bloqueo: Path):
        self._ruta = ruta_bloqueo
        self._rlock = threading.RLock()
        self._profundidade = 0
        self._ficheiro = None
        self._aviso_sen_flock = False

    def __enter__(self):
        self._rlock.acquire()
        try:
            if self._profundidade == 0:
                self._bloquear_ficheiro()
            self._profundidade += 1
        except BaseException:
            self._rlock.release()
            raise
        return self

    def __exit__(self, *exc):
        try:
            self._profundidade -= 1
            if self._profundidade == 0:
                self._soltar_ficheiro()
        finally:
            self._rlock.release()
        return False

    def _bloquear_ficheiro(self) -> None:
        f = open(self._ruta, "a+b")
        try:
            try:
                os.chmod(self._ruta, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass
            if fcntl is not None:
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                except OSError as e:
                    if e.errno not in _ERRNO_SEN_SOPORTE:
                        raise
                    # sistema de ficheiros sen `flock` (algúns cartafoles de
                    # rede): mellor seguir só co bloqueo entre fíos que
                    # deixar a aplicación inutilizable -- avísase unha vez.
                    if not self._aviso_sen_flock:
                        self._aviso_sen_flock = True
                        warnings.warn(
                            f"o sistema de ficheiros de {self._ruta.parent} non admite "
                            "bloqueo de ficheiros: non use este rexistro desde dous "
                            "programas á vez",
                            RuntimeWarning,
                        )
            else:
                # `LK_LOCK` reintenta durante ~10 s e despois falla: seguir
                # agardando (outro proceso ten o rexistro ocupado).
                while True:
                    f.seek(0)
                    try:
                        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
                        break
                    except OSError:
                        time.sleep(0.1)
        except BaseException:
            f.close()
            raise
        self._ficheiro = f

    def _soltar_ficheiro(self) -> None:
        f, self._ficheiro = self._ficheiro, None
        if f is None:
            return
        try:
            if fcntl is not None:
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass  # pechar o ficheiro solta igualmente o bloqueo
            else:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            f.close()


_BLOQUEOS: dict = {}
_BLOQUEOS_MUTEX = threading.Lock()


def _bloqueo_para(directorio: Path) -> _BloqueoCartafol:
    clave = os.path.normcase(str(directorio.resolve()))
    with _BLOQUEOS_MUTEX:
        bloqueo = _BLOQUEOS.get(clave)
        if bloqueo is None:
            bloqueo = _BloqueoCartafol(Path(clave) / "rexistro.lock")
            _BLOQUEOS[clave] = bloqueo
        return bloqueo


def _con_bloqueo(metodo):
    """Executa un método público baixo o bloqueo do cartafol, co estado
    recargado desde disco se outra instancia/proceso o cambiou. Se o
    método falla a medias, invalídase o estado en memoria para que a
    seguinte operación o recargue desde disco (nunca se garda un estado
    modificado a medias)."""

    def envoltorio(self, *args, **kwargs):
        with self._bloqueo:
            self._refrescar_estado()
            try:
                return metodo(self, *args, **kwargs)
            except BaseException:
                self._sinatura_estado = None
                raise

    envoltorio.__name__ = metodo.__name__
    envoltorio.__qualname__ = metodo.__qualname__
    envoltorio.__doc__ = metodo.__doc__
    return envoltorio


class RexistroCorrespondencias:
    def __init__(self, directorio: str | Path, usar_chaveiro: bool = False):
        """`usar_chaveiro` so determina onde se garda unha clave NOVA (ver
        `_cargar_ou_crear_clave`): por defecto en `False` para que instancias
        de proba (tests, scripts) nunca toquen o chaveiro real do sistema
        operativo -- iso pode abrir un dialogo de autorizacion que bloquea
        o proceso ata que un humano o confirme. Para uso real (CLI, seccion
        07 do informe: "en produción debe moverse a un chaveiro do sistema
        operativo"), pasa `usar_chaveiro=True` (flag `--chaveiro-sistema`)."""
        self.directorio = Path(directorio)
        self.directorio.mkdir(parents=True, exist_ok=True)
        self._ficheiro_clave = self.directorio / "clave.key"
        self._ficheiro_datos = self.directorio / "rexistro.enc"
        self._ficheiro_auditoria = self.directorio / "auditoria.enc"
        self._ficheiro_sesions = self.directorio / "sesions.enc"
        # Marcador SEN datos sensibles (nunca contén a clave en si) que
        # indica que ESTE rexistro concreto garda a súa clave no chaveiro
        # do sistema, non nun ficheiro local. Isto e o que permite que
        # calquera proceso -- CLI, interface web -- saiba ONDE mirar sen
        # ter que consultar o chaveiro real por defecto (ver máis abaixo
        # por que iso importa para os tests).
        self._ficheiro_marcador_chaveiro = self.directorio / "clave.chaveiro"
        self._usar_chaveiro_para_crear = usar_chaveiro
        self._id_chaveiro = str(self.directorio.resolve())
        self.orixe_clave = None  # "ficheiro" ou "chaveiro_sistema"; para diagnostico/tests
        self._bloqueo = _bloqueo_para(self.directorio)
        # Contido cifrado de `rexistro.enc` cando se cargou ou gardou por
        # última vez; se o do disco é distinto, outra instancia gardou.
        self._sinatura_estado = None
        with self._bloqueo:
            self._fernet = self._cargar_ou_crear_clave()
            self._estado = self._cargar_estado()

    # -- persistencia cifrada -------------------------------------------------

    def _cargar_ou_crear_clave(self) -> Fernet:
        """Orde de busca dunha clave xa existente:
        1. Ficheiro `clave.key` local, se existe (compatibilidade con
           rexistros creados antes desta funcionalidade, ou gardados así
           a propósito).
        2. Chaveiro do sistema operativo, PERO só se xa existe o ficheiro
           marcador `clave.chaveiro` -- é dicir, só para rexistros que xa
           se crearon explicitamente con `usar_chaveiro=True`. IMPORTANTE:
           o chaveiro REAL nunca se consulta "por se acaso" cando non hai
           marcador -- así os tests (e calquera script que non pida o
           chaveiro a propósito) non o tocan nunca, evitando calquera risco
           de que o sistema operativo abra un diálogo de autorización que
           bloquearía o proceso agardando a un humano que nunca chega.
        3. Se non existe ningunha das dúas (rexistro NOVO): `usar_chaveiro`
           decide ONDE se garda a clave nova -- no chaveiro (con reserva
           automática a ficheiro se algo falla, ex. sen sesión de
           escritorio) ou directamente en ficheiro."""
        if self._ficheiro_clave.exists():
            self.orixe_clave = "ficheiro"
            return Fernet(self._ficheiro_clave.read_bytes())

        if self._ficheiro_marcador_chaveiro.exists():
            if not _KEYRING_DISPONIBLE:
                raise RuntimeError(
                    "este rexistro garda a súa clave no chaveiro do sistema "
                    "operativo, pero a libraría 'keyring' non está instalada "
                    "(pip install keyring) -- sen ela non se pode descifrar"
                )
            # O identificador co que se gardou a clave vai no propio marcador:
            # se o cartafol se moveu (en Mac/Linux o rexistro pasou a vivir
            # fóra do cartafol do programa, 04/10/2026), a ruta actual xa non
            # é a que se usou ao crealo.
            gardado = re.search(r"^Identificador: (.+)$",
                                self._ficheiro_marcador_chaveiro.read_text(encoding="utf-8"), re.MULTILINE)
            if gardado:
                self._id_chaveiro = gardado.group(1).strip()
            clave_existente = self._ler_clave_chaveiro()
            if clave_existente is None:
                raise RuntimeError(
                    "non se atopou a clave no chaveiro do sistema operativo "
                    f"para este rexistro ({self._id_chaveiro}); sen ela non "
                    "se pode descifrar o rexistro de correspondencias"
                )
            self.orixe_clave = "chaveiro_sistema"
            return Fernet(clave_existente)

        if self._usar_chaveiro_para_crear and _KEYRING_DISPONIBLE:
            clave = Fernet.generate_key()
            if self._gardar_clave_chaveiro(clave):
                self._ficheiro_marcador_chaveiro.write_text(
                    "A clave de cifrado deste rexistro gárdase no chaveiro "
                    "do sistema operativo (macOS Keychain / Windows "
                    "Credential Manager), NON neste cartafol.\n"
                    f"Identificador: {self._id_chaveiro}\n",
                    encoding="utf-8",
                )
                self.orixe_clave = "chaveiro_sistema"
                return Fernet(clave)
            # o chaveiro non estaba dispoñible (ex. sen sesión de
            # escritorio, backend non soportado) -- reserva a ficheiro,
            # sen deixar o rexistro sen clave ningunha

        clave = Fernet.generate_key()
        self._ficheiro_clave.write_bytes(clave)
        os.chmod(self._ficheiro_clave, stat.S_IRUSR | stat.S_IWUSR)  # 600
        self.orixe_clave = "ficheiro"
        return Fernet(clave)

    def _ler_clave_chaveiro(self) -> bytes | None:
        try:
            valor = keyring.get_password(_SERVIZO_CHAVEIRO, self._id_chaveiro)
        except Exception:
            # calquera fallo do backend (sen chaveiro dispoñible, sen
            # sesión de escritorio, erro de permisos...) trátase igual:
            # non hai clave utilizable por esta vía
            return None
        return valor.encode("ascii") if valor else None

    def _gardar_clave_chaveiro(self, clave: bytes) -> bool:
        try:
            keyring.set_password(_SERVIZO_CHAVEIRO, self._id_chaveiro, clave.decode("ascii"))
            return True
        except Exception:
            return False

    def _ler_cifrado_datos(self) -> bytes | None:
        try:
            return self._ficheiro_datos.read_bytes()
        except FileNotFoundError:
            return None

    def _cargar_estado(self, cifrado: bytes | None = None) -> dict:
        # chamar SEMPRE co bloqueo collido
        if cifrado is None:
            cifrado = self._ler_cifrado_datos()
        self._sinatura_estado = cifrado if cifrado is not None else b""
        if cifrado is None:
            return {"seguinte_numero": 1, "persoas": {}, "dni_indice": {}}
        return json.loads(self._fernet.decrypt(cifrado).decode("utf-8"))

    def _refrescar_estado(self) -> None:
        """Recarga o estado desde disco só se o ficheiro cambiou desde a
        última carga/gardado desta instancia (chamar co bloqueo collido).
        Compárase o CONTIDO cifrado, non a data de modificación: en
        pendrives exFAT/FAT a data ten resolución de segundos e dous
        gardados seguidos poderían parecer iguais. Fernet usa un IV
        aleatorio, así que cada gardado produce bytes distintos."""
        cifrado = self._ler_cifrado_datos()
        actual = cifrado if cifrado is not None else b""
        if self._sinatura_estado is None or actual != self._sinatura_estado:
            self._estado = self._cargar_estado(cifrado)

    def _gardar_estado(self) -> None:
        # chamar SEMPRE co bloqueo collido (ver `_con_bloqueo`)
        contido = json.dumps(self._estado, ensure_ascii=False).encode("utf-8")
        cifrado = self._fernet.encrypt(contido)
        tmp = self._ficheiro_datos.with_suffix(".tmp")
        tmp.write_bytes(cifrado)
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
        substituir_con_reintentos(tmp, self._ficheiro_datos)
        self._sinatura_estado = cifrado

    def _rexistrar_auditoria(self, accion: str, codigo: str, motivo: str | None) -> None:
        evento = {
            "cando": datetime.now(timezone.utc).isoformat(),
            "accion": accion,
            "codigo": codigo,
            "motivo": motivo,
        }
        token = self._fernet.encrypt(json.dumps(evento, ensure_ascii=False).encode("utf-8"))
        with open(self._ficheiro_auditoria, "ab") as f:
            f.write(token + b"\n")
        os.chmod(self._ficheiro_auditoria, stat.S_IRUSR | stat.S_IWUSR)

    @_con_bloqueo
    def ler_auditoria(self) -> list:
        if not self._ficheiro_auditoria.exists():
            return []
        eventos = []
        with open(self._ficheiro_auditoria, "rb") as f:
            for liña in f:
                liña = liña.strip()
                if liña:
                    eventos.append(json.loads(self._fernet.decrypt(liña).decode("utf-8")))
        return eventos

    # -- sesions de revision pendentes ----------------------------------------
    # A interface web (web.py) garda aqui unha copia cifrada de cada sesion
    # de revision AINDA NON CONFIRMADA, para que sobreviva a un reinicio do
    # servidor sen perder o traballo do letrado. O informe de deteccion
    # (nomes, DNI, telefonos... detectados) e datos tan sensibles coma o
    # propio rexistro (seccion 03 do informe: "quen a lea reverte todo o
    # sistema de golpe"), asi que se cifra coa MESMA clave -- nunca en JSON
    # plano. O documento orixinal en memoria (`contexto`, con python-docx/
    # odfpy) NON se garda aqui: reconstruese sempre desde `ruta_orixe` no
    # disco, que segue intacto ata que se confirma a revision.

    def _cargar_sesions(self) -> dict:
        if not self._ficheiro_sesions.exists():
            return {}
        cifrado = self._ficheiro_sesions.read_bytes()
        return json.loads(self._fernet.decrypt(cifrado).decode("utf-8"))

    def _gardar_sesions(self, sesions: dict) -> None:
        contido = json.dumps(sesions, ensure_ascii=False).encode("utf-8")
        cifrado = self._fernet.encrypt(contido)
        tmp = self._ficheiro_sesions.with_suffix(".tmp")
        tmp.write_bytes(cifrado)
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
        substituir_con_reintentos(tmp, self._ficheiro_sesions)

    @_con_bloqueo
    def gardar_sesion(self, sid: str, datos: dict) -> None:
        sesions = self._cargar_sesions()
        sesions[sid] = datos
        self._gardar_sesions(sesions)

    @_con_bloqueo
    def eliminar_sesion(self, sid: str) -> None:
        sesions = self._cargar_sesions()
        if sid in sesions:
            del sesions[sid]
            self._gardar_sesions(sesions)

    @_con_bloqueo
    def ler_sesions_pendentes(self) -> dict:
        return self._cargar_sesions()

    # -- xeracion de codigos ---------------------------------------------------

    def _novo_codigo(self, prefixo: str = "PERSOA") -> tuple[str, int]:
        numero = self._estado["seguinte_numero"]
        self._estado["seguinte_numero"] = numero + 1
        return f"{prefixo}_{numero:06d}", numero

    # -- resolucion --------------------------------------------------------

    @_con_bloqueo
    def resolver_ou_crear(self, grupo: Grupo) -> tuple[str, bool, str | None, list]:
        """Devolve (codigo, marcado_para_revision, motivo, posibles_coincidencias).

        `posibles_coincidencias` so se enche cando hai códigos xa existentes
        que un humano podería confirmar coma a mesma persoa (interface de
        revisión, `web.py`); para o caso "ambiguo" (apelido solto) queda
        baleiro porque a ambigüidade non apunta a códigos concretos."""

        if grupo.ambiguo:
            codigo, numero = self._novo_codigo()
            self._crear_persoa(codigo, numero, grupo, dni=None)
            self._rexistrar_auditoria("crear_ambiguo", codigo, grupo.motivo_ambiguidade)
            return codigo, True, grupo.motivo_ambiguidade, []

        if grupo.dni:
            dni_norm = normalizar_dni(grupo.dni)
            codigo_existente = self._estado["dni_indice"].get(dni_norm)
            if codigo_existente:
                self._engadir_variante_nome(codigo_existente, grupo.representante)
                self._rexistrar_auditoria("recuperar_por_dni", codigo_existente, None)
                return codigo_existente, False, None, []

            codigo, numero = self._novo_codigo()
            # IMPORTANTE: o índice actualízase ANTES de crear (e gardar) a
            # persoa -- `_crear_persoa` chama a `_gardar_estado()`, así que
            # facelo ao revés escribiría en disco sen o índice de DNI e
            # unha recarga posterior (outra execución do CLI, outra
            # petición web) xa non atoparía a coincidencia.
            self._estado["dni_indice"][dni_norm] = codigo
            self._crear_persoa(codigo, numero, grupo, dni=dni_norm)
            self._rexistrar_auditoria("crear_con_dni", codigo, None)
            return codigo, False, None, []

        # Sen DNI: buscar coincidencia de nome exacta noutra persoa xa
        # rexistrada. NUNCA se fusiona so por isto -- crease sempre un
        # codigo novo, marcado para que un humano confirme se e a mesma
        # persoa xa vista.
        nome_norm = normalizar(grupo.representante)
        coincidencias = [
            codigo for codigo, dados in self._estado["persoas"].items()
            if nome_norm in {normalizar(n) for n in dados["nomes"]}
        ]

        codigo, numero = self._novo_codigo()
        self._crear_persoa(codigo, numero, grupo, dni=None)

        if coincidencias:
            motivo = (
                f"posible homonimo: o nome '{grupo.representante}' coincide con "
                f"{', '.join(coincidencias)} sen DNI que o confirme — verificar se e a mesma persoa"
            )
            self._rexistrar_auditoria("crear_posible_homonimo", codigo, motivo)
            return codigo, True, motivo, coincidencias

        self._rexistrar_auditoria("crear_novo", codigo, None)
        return codigo, False, None, []

    # -- confirmacion humana -------------------------------------------------

    @_con_bloqueo
    def fusionar(self, manter: str, eliminar: str) -> None:
        """Aplica a decision dun letrado: `eliminar` era en realidade a
        mesma persoa que `manter`. Refusase se ambos teñen DNI confirmado
        e son distintos (iso xa non seria un homonimo dubidoso, senon un
        erro de revision)."""
        if manter == eliminar:
            return
        if manter not in self._estado["persoas"] or eliminar not in self._estado["persoas"]:
            raise KeyError("código descoñecido no rexistro")

        datos_manter = self._estado["persoas"][manter]
        datos_eliminar = self._estado["persoas"][eliminar]
        if datos_eliminar.get("dni") and datos_manter.get("dni") and datos_eliminar["dni"] != datos_manter["dni"]:
            raise ValueError(
                f"{manter} e {eliminar} teñen DNI distintos confirmados: non se poden fusionar"
            )

        for nome in datos_eliminar["nomes"]:
            if nome not in datos_manter["nomes"]:
                datos_manter["nomes"].append(nome)

        if datos_eliminar.get("dni") and not datos_manter.get("dni"):
            datos_manter["dni"] = datos_eliminar["dni"]
            self._estado["dni_indice"][datos_eliminar["dni"]] = manter

        self._estado.setdefault("alias", {})[eliminar] = manter
        del self._estado["persoas"][eliminar]
        self._gardar_estado()
        self._rexistrar_auditoria("fusion_confirmada_por_humano", manter, f"fusionado con {eliminar}")

    @_con_bloqueo
    def manter_separadas(self, codigo_a: str, codigo_b: str) -> None:
        """Rexistra que un letrado revisou un posible homónimo e confirmou
        que SON persoas distintas (deixa o rexistro tal como estaba, so
        queda constancia na auditoría)."""
        self._rexistrar_auditoria(
            "confirmado_persoas_distintas", codigo_a, f"confirmado distinto de {codigo_b}"
        )

    @_con_bloqueo
    def descartar_por_humano(self, codigo: str, motivo: str | None = None) -> None:
        """Rexistra que quen revisou decidiu que `codigo` NON é unha persoa
        (ou non hai que anonimizala) e deixouna á vista no documento. O código
        segue no rexistro (pode aparecer noutros documentos); queda constancia
        na auditoría para medir a precisión do detector co uso real."""
        self._rexistrar_auditoria("descartada_por_humano", codigo, motivo)

    def _resolver_alias(self, codigo: str) -> str:
        """Se un código foi fusionado noutro (`fusionar`), segue a cadea de
        alias ata o código vixente."""
        alias = self._estado.get("alias", {})
        vistos = set()
        while codigo in alias and codigo not in vistos:
            vistos.add(codigo)
            codigo = alias[codigo]
        return codigo

    # -- contrasinal de reversion -----------------------------------------
    # Segunda barreira, A NIVEL DE APLICACIÓN, para `reverter` (ver máis
    # abaixo): separada da clave de cifrado (`clave.key`/chaveiro) a
    # propósito. IMPORTANTE, e hai que dicirllo claro a quen a configure:
    # isto NON é unha capa de cifrado adicional -- gárdase (coma hash, con
    # sal, nunca en claro) dentro do propio `_estado`, que xa vai cifrado
    # con Fernet coa MESMA clave que abre todo o resto. Quen teña acceso a
    # `clave.key` E `rexistro.enc` pode descifrar as identidades reais
    # directamente coa libraría `cryptography`, sen pasar por aquí nin
    # coñecer esta contrasinal. O que si evita é que outra persoa que
    # comparte o mesmo ordenador (sen coñecementos técnicos) abra a
    # interface web ou a CLI e reverta identidades reais sen coñecela.

    @_con_bloqueo
    def ten_contrasinal_reversion(self) -> bool:
        return "contrasinal_reversion" in self._estado

    def _verificar_contrasinal_reversion(self, intento: str) -> bool:
        datos = self._estado.get("contrasinal_reversion")
        if not datos:
            return False
        sal = bytes.fromhex(datos["sal"])
        return _hash_contrasinal(intento or "", sal) == datos["hash"]

    @_con_bloqueo
    def definir_contrasinal_reversion(self, nova: str, actual: str | None = None) -> None:
        """Establece a contrasinal (primeira vez) ou cámbiaa (se xa existe
        unha, hai que confirmala primeiro coma `actual`)."""
        if not nova or len(nova) < _LONXITUDE_MINIMA_CONTRASINAL:
            raise ValueError(
                f"a contrasinal de reversión ten que ter polo menos "
                f"{_LONXITUDE_MINIMA_CONTRASINAL} caracteres"
            )
        if self.ten_contrasinal_reversion():
            if not actual or not self._verificar_contrasinal_reversion(actual):
                raise ValueError("a contrasinal actual non coincide")

        sal = secrets.token_bytes(16)
        self._estado["contrasinal_reversion"] = {
            "sal": sal.hex(),
            "hash": _hash_contrasinal(nova, sal),
        }
        self._gardar_estado()
        self._rexistrar_auditoria("contrasinal_reversion_definida", "-", None)

    # -- reversion controlada e listado completo ---------------------------

    @_con_bloqueo
    def reverter(self, codigo: str, motivo: str, contrasinal: str, solicitante: str | None = None) -> dict:
        """Reversión controlada (informe, seccións 04 e 07): a única función
        de todo o sistema que devolve unha identidade real a partir dun
        código. Esixe sempre un motivo -- non e opcional -- porque queda
        gravado na auditoría cifrada xunto con quen o solicitou; sen iso,
        non hai forma de xustificar despois por que se abriu o rexistro.
        Esixe ademais a contrasinal de reversión (ver arriba); un intento
        fallido tamén queda rexistrado na auditoría, coma sinal de alerta
        se alguén tenta reverter identidades reais sen coñecela."""
        motivo = (motivo or "").strip()
        if not motivo:
            raise ValueError("a reversión require un motivo; queda rexistrado na auditoría")

        if not self.ten_contrasinal_reversion():
            raise ValueError(
                "aínda non hai contrasinal de reversión definida para este rexistro -- "
                "hai que definila antes de poder reverter ningunha identidade"
            )
        if not self._verificar_contrasinal_reversion(contrasinal):
            detalle = "intento fallido"
            if solicitante:
                detalle += f" | solicitante: {solicitante}"
            self._rexistrar_auditoria("reversion_denegada", codigo, detalle)
            raise ValueError("contrasinal de reversión incorrecta")

        # A26 (revisión 21/09/2026): ata o 29/09/2026 o DNI redactábase
        # coma "ID_000042" (mesma numeración ca "PERSOA_000042"); dende
        # entón leva o mesmo código ca o titular, pero os documentos xa
        # entregados seguen tendo "ID_..." e teñen que poder reverterse.
        codigo_normalizado = codigo
        if codigo_normalizado.startswith("ID_"):
            codigo_normalizado = "PERSOA_" + codigo_normalizado[len("ID_"):]

        codigo_actual = self._resolver_alias(codigo_normalizado)
        if codigo_actual not in self._estado["persoas"]:
            raise KeyError(f"código descoñecido no rexistro: {codigo}")

        dados = self._estado["persoas"][codigo_actual]
        detalle_auditoria = f"motivo: {motivo}"
        if solicitante:
            detalle_auditoria += f" | solicitante: {solicitante}"
        self._rexistrar_auditoria("reversion", codigo_actual, detalle_auditoria)

        return {
            "codigo_solicitado": codigo,
            "codigo_actual": codigo_actual,
            "nomes": list(dados["nomes"]),
            "dni": dados.get("dni"),
            "contexto": dados.get("contexto"),
            "creado": dados.get("creado"),
        }

    @_con_bloqueo
    def listar_correspondencias(
        self,
        motivo: str,
        contrasinal: str,
        solicitante: str | None = None,
        desde: int = 0,
        limite: int | None = None,
    ) -> dict:
        """Listado COMPLETO código↔persoa dun rexistro -- a diferenza de
        `reverter` (un código xa coñecido de antemán), esta expón de golpe
        TODO o rexistro, así que esixe exactamente a MESMA barreira (motivo
        obrigatorio + contrasinal de reversión) pero queda auditada á
        parte, cunha acción distinta (`listado_completo`/
        `listado_completo_denegado`, nunca `reversion`), para que a
        auditoría distinga sempre un acceso masivo dunha consulta dun só
        código. Non se recorta ningún campo respecto a `reverter` (nomes,
        DNI, contexto, creación) -- a barreira xa se pasou, e ocultar
        algo aquí só obrigaría a reverter persoa a persoa sen gañar nada.

        Os códigos fusionados (`fusionar`) NON teñen fila propia -- xa non
        están en `_estado["persoas"]` -- pero listar isto tal cal faría
        parecer que un código antigo (o que aparece nun documento vello)
        desapareceu do rexistro. Devólvense coma `fusionados` do código
        vixente, resolvendo cadeas de fusións (A→B→C) coma `_resolver_alias`.

        `desde`/`limite` paxinan (a web pide de novo a contrasinal en cada
        páxina -- ver `web.py` -- así que cada tanda queda auditada co seu
        propio rango, non un só evento "viu todo"). Un rexistro BALEIRO
        non é un erro: devolve `total=0` e AÍNDA ASÍ audita o acceso --
        silencialo abriría unha vía para probar contrasinales sen deixar
        rastro nun rexistro recén creado."""
        motivo = (motivo or "").strip()
        if not motivo:
            raise ValueError("o listado completo require un motivo; queda rexistrado na auditoría")

        if not self.ten_contrasinal_reversion():
            raise ValueError(
                "aínda non hai contrasinal de reversión definida para este rexistro -- "
                "hai que definila antes de poder listar as correspondencias"
            )
        if not self._verificar_contrasinal_reversion(contrasinal):
            detalle = f"intento fallido | motivo: {motivo}"
            if solicitante:
                detalle += f" | solicitante: {solicitante}"
            self._rexistrar_auditoria("listado_completo_denegado", "*", detalle)
            raise ValueError("contrasinal de reversión incorrecta")

        fusionados_por_codigo: dict[str, list[str]] = {}
        alias_orfos = []
        for eliminado in self._estado.get("alias", {}):
            vixente = self._resolver_alias(eliminado)
            if vixente in self._estado["persoas"]:
                fusionados_por_codigo.setdefault(vixente, []).append(eliminado)
            else:
                alias_orfos.append(eliminado)

        total = len(self._estado["persoas"])
        entradas_ordenadas = sorted(
            self._estado["persoas"].items(), key=lambda par: (par[1].get("numero", 0), par[0])
        )
        desde = max(0, desde)
        fin = None if limite is None else desde + max(0, limite)
        pagina = entradas_ordenadas[desde:fin]

        entradas = [
            {
                "codigo": codigo,
                # Código que levaba o DNI nos documentos anonimizados antes
                # do 29/09/2026 (ver `reverter`): segue aparecendo neles.
                "codigo_id": f"ID_{dados.get('numero', 0):06d}",
                "numero": dados.get("numero"),
                "nomes": list(dados["nomes"]),
                "dni": dados.get("dni"),
                "contexto": dados.get("contexto"),
                "creado": dados.get("creado"),
                "fusionados": sorted(fusionados_por_codigo.get(codigo, [])),
            }
            for codigo, dados in pagina
        ]

        detalle_auditoria = f"motivo: {motivo}"
        if solicitante:
            detalle_auditoria += f" | solicitante: {solicitante}"
        detalle_auditoria += f" | LISTADO COMPLETO: {len(entradas)} de {total} correspondencia(s) (desde {desde})"
        self._rexistrar_auditoria("listado_completo", "*", detalle_auditoria)

        return {
            "total": total,
            "desde": desde,
            "limite": limite,
            "entradas": entradas,
            "alias_orfos": sorted(alias_orfos),
        }

    def _crear_persoa(self, codigo: str, numero: int, grupo: Grupo, dni: str | None) -> None:
        self._estado["persoas"][codigo] = {
            "numero": numero,
            "nomes": [grupo.representante],
            "dni": dni,
            "contexto": grupo.contexto,
            "creado": datetime.now(timezone.utc).isoformat(),
        }
        self._gardar_estado()

    def _engadir_variante_nome(self, codigo: str, nome: str) -> None:
        dados = self._estado["persoas"][codigo]
        if nome not in dados["nomes"]:
            dados["nomes"].append(nome)
            self._gardar_estado()

    @_con_bloqueo
    def codigo_por_dni(self, dni: str) -> str | None:
        """Código da persoa dun DNI xa coñecido, buscado DIRECTAMENTE (sen
        pasar por un `Grupo` de `resolution.agrupar`, que esixe un nome de
        persoa preto para asocialo) -- caso real: un nome de ficheiro que
        só trae o DNI ("DNI_30014811Z.pdf", un escaneado do propio
        documento de identidade). O DNI leva o MESMO código ca o seu
        titular (decisión do usuario, 29/09/2026). Devolve `None` se ese
        DNI aínda non está rexistrado."""
        codigo = self._estado["dni_indice"].get(normalizar_dni(dni))
        return None if codigo is None else self._resolver_alias(codigo)
