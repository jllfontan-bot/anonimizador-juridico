# Instaladores e scripts de arranque

Orixe versionada de todo o que se entrega para que alguén sen coñecementos
técnicos poida instalar e usar o programa.

| SO | Entregable | Como se instala |
|----|-----------|-----------------|
| **Windows** | `Anonimizador-Xuridico-Instalador-<VERSION>.exe` (un só ficheiro, na raíz do repo) | Asistente gráfico NSIS con barra de progreso en porcentaxe; desinstalador propio |
| **Mac** | `anonimizador-xuridico-instalacion-<VERSION>-mac.zip` | `instalar-mac.command` (dobre clic, unha vez) e despois `Iniciar-Anonimizador.command` |
| **Linux** | `anonimizador-xuridico-instalacion-<VERSION>-linux.zip` | `instalar-linux.sh` e despois `Iniciar-Anonimizador.sh` |

`<VERSION>` = `AAAAMMDD-<commit curto>[-suxo]` (`-suxo` se o repo tiña cambios
sen commitear ao xerar o paquete).

## Xerar os paquetes

```
./instalador/crear-paquetes.sh windows   # só o .exe de Windows
./instalador/crear-paquetes.sh mac
./instalador/crear-paquetes.sh linux
./instalador/crear-paquetes.sh           # os tres
```

Todo o que se descarga (Python portátil, Tesseract, wheels) queda cacheado
en `build/cache/` (ignorado por git) e reutilízase: non se descarga dúas
veces. Para o `.exe` de Windows precísase ademais `makensis` no equipo que
constrúe (`brew install makensis`; é un cross-compile, non fai falta Windows).
`INSTALADOR_PROBA=1 ./instalador/crear-paquetes.sh windows` xera un `.exe` SEN
compresión en `build/proba/` (7 segundos en vez de 2-3 minutos) para iterar
sobre o propio instalador.

## Windows: como funciona

O instalador **non executa pip nin crea ningún venv** na máquina de destino:
copia un árbore xa feito, así a barra de progreso é a de verdade. En
`crear-paquetes.sh` (función `xerar_windows`) móntase `build/staging-windows/`:

- `runtime/python/` — Python portátil (python-build-standalone) coas
  librarías xa desempaquetadas en `Lib/site-packages` (`bundle/montar_site_packages.py`
  descomprime os wheels; `odfpy` e `proxy_tools`, que só existen coma sdist,
  conviértense antes a wheel e cachéanse en `build/cache/wheels/_sdist_wheels`).
  Execútase directamente `pythonw.exe`, sen venv.
- `runtime/tesseract/` — Tesseract (OCR) con bibliotecas e `tessdata`.
- `anonimizador-xuridico/` — código (`src/`), `config/`, exemplos.
- `docs/` — PDFs de documentación (o manual de uso ten acceso no menú Inicio).
- `Iniciar-Anonimizador.vbs` e `anonimizador.ico`.

`windows/xerar_arbore_nsh.py` converte ese árbore na lista de `File` de NSIS e
`windows/instalador.nsi` (MUI2, galego; cae a castelán se a versión de NSIS
non traxese o galego) compila o `.exe`.

**Instalación por usuario, sen UAC.** Programa en
`%LOCALAPPDATA%\Programs\Anonimizador`; desinstalador e entrada de
"Aplicacións instaladas" en `HKCU`; accesos no menú Inicio
(programa, manual de uso, desinstalar) e opcionalmente no escritorio.
`/S` fai a instalación / desinstalación en silencio (`/D=ruta` para outro
cartafol, sempre de último argumento).

**Arranque.** Os accesos directos executan `wscript.exe Iniciar-Anonimizador.vbs`,
que fixa `TESSDATA_PREFIX`, `PATH` e `PYTHONPATH` **só para ese proceso**, pon
como cartafol de traballo `%LOCALAPPDATA%\Anonimizador` e lanza
`runtime\python\pythonw.exe -m anonimizador.cli escritorio --porto 5050
--chaveiro-sistema`, sen ninguén consola. Os datos do usuario
(`datos_rexistro`, `anonimizador.log`) viven en `%LOCALAPPDATA%\Anonimizador`,
FÓRA do cartafol do programa: actualizar ou desinstalar non os toca.
Nota: o `.vbs` lanza con modo de ventá 1 (normal) a propósito; con 0 (oculta)
Windows herda "oculta" na primeira ventá do proceso fillo e a xanela de
pywebview naceria invisible.

**Reinstalar / actualizar.** Instalar enriba dunha instalación previa funciona:
se o programa está aberto avisa e péchao (en `/S` péchao sen preguntar; só
procesos que corren dende o `runtime` da instalación, `pechar-programa.ps1`),
borra os cartafoles do programa (`runtime`, `anonimizador-xuridico`, `docs`) e
copia o novo. Os datos do usuario non se tocan.

**Desinstalar.** Borra só o que puxo a instalación (nunca `$INSTDIR` enteiro),
os accesos e a clave de `HKCU`. Pregunta (Si/Non, por defecto NON) se tamén se
borra `%LOCALAPPDATA%\Anonimizador\datos_rexistro`; en modo silencioso nunca os
borra. A clave de cifrado vive no Administrador de credenciais de Windows e o
desinstalador non a toca.

**Sen sinatura de código.** O `.exe` non vai asinado: Windows SmartScreen
amosará o aviso "Windows protexeu o seu PC" (Máis información > Executar de
todos modos) ata que se compre un certificado de sinatura.

Requírese Windows de 64 bits. A xanela do programa usa o compoñente
Microsoft Edge WebView2 (vén con Windows 11); se falta, o instalador avisa e o
programa ofrece abrirse no navegador.

Ficheiros de `windows/`: `instalador.nsi`, `xerar_arbore_nsh.py`,
`Iniciar-Anonimizador.vbs`, `pechar-programa.ps1`, `xerar_icona.py` (xera
`anonimizador.ico` e `asistente.bmp` con Pillow; ambos van versionados, non fai
falta rexeneralos para construír).

## Mac e Linux

- `instalar-mac.command` / `instalar-linux.sh` — instalación completa
  (Python, Tesseract, ambiente virtual, dependencias, modelo de idioma).
- `Iniciar-Anonimizador.command` / `.sh` — arrancan a interface nunha xanela
  de escritorio propia (`anonimizador escritorio`, pywebview -- non nunha
  pestana do navegador), coa clave de cifrado no chaveiro do sistema
  (`--chaveiro-sistema`) xa activada. En Linux cae automaticamente ao
  navegador se falta GTK3/WebKit2GTK no sistema (non se inclúen no paquete
  offline, ver `crear-paquetes.sh`).
- `LEEME.txt` / `LEEME.pdf` — nota de benvida (mesmo contido nos dous formatos;
  o PDF segue o mesmo estilo visual có resto de informes).

Estes scripts asumen que se executan situados **xunto a unha copia completa
do proxecto** nun cartafol chamado `anonimizador-xuridico/`
(`./anonimizador-xuridico/src`, `./anonimizador-xuridico/requirements.txt`...
ao seu carón): a estrutura do paquete final que se entrega ao usuario, non a
deste repositorio. `crear-paquetes.sh` monta ese paquete (código limpo, PDFs
de `docs/`, runtime e wheels) e cómprimeo.
