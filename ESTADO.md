# Estado dos dous programas (02/11/2026)

Este repositorio contén dous programas que comparten o mesmo motor:
o **Anonimizador xurídico** e o **Reductor de tokens** (antes «Conversor de arquivos para IA»).
Este ficheiro é un resumo curto. Non leva datos reais nin notas persoais.

## Anonimizador xurídico

- Microsoft Store: **publicado**, Store ID `9PK1J429MNN5`.
- Publicado na Store: **1.1.1.0**. Preparada, sen publicar: **1.1.2** (`VERSION`; paquete 1.1.2.0): correccións de fugas, explorador con carpetas reais de Windows e copia `.md` co mesmo motor ca o Reductor.
- Política de privacidade: `docs/store/politica-privacidad.md`; condicións de uso: `docs/store/condiciones-de-uso.md`.
- Só Windows 10/11 na Store. As versións de Mac e Linux quitáronse da oferta do Anonimizador;
  hai instaladores clásicos de Mac nas ramas `instalador-mac-*`.
- Pendente: nada urxente.

## Reductor de tokens (antes «Conversor de arquivos para IA»)

- Microsoft Store: **publicado**, Store ID `9NMM4DRL6FCC`, paquete 1.1.0.0. Preparada, sen publicar: **1.2.0** (`conversor.VERSION`; paquete 1.2.0.0).
- Política de privacidade: `docs/store/politica-privacidad-conversor.md`; ficha: `docs/store/ficha-store-conversor.md`.
- Instaladores clásicos sen asinar para Windows e Mac (`instalador/crear-paquetes.sh windows-conversor|mac-conversor`).
- Notas de deseño e límites en `src/anonimizador/formatos/ESCONDITES.md` e estudos previos en `docs/estudios/`.
- Rama `motor-md-unico` (inclúe `correcciones-fugas-reductor`; sen publicar): en automático nunca se detén e o resumo final lista os
  «Documentos con posibles fugas» cun botón «Revisar» (`conversor.substituir_revisado`); un `.zip` dentro dun
  cartafol ábrese en `<nome do zip>-md` (un `.zip` dentro dun `.zip`, non; límite de 2 GiB descomprimidos);
  subtítulo novo. Falta probar a xanela real (pywebview) con «Revisar» no portátil Windows.
- Pendente: formatos novos en modo anonimizado (con tests de fugas), adxuntos de `.eml` nun `.zip`,
  menú contextual de Windows, extensión para Claude Desktop.

## Compartido

- Motor: `pipeline`, `lectura`, `copia_md` (en `src/anonimizador/`). Suite de tests: uns 1.100
  (`python3 -m unittest discover -s tests`; tarda ata ~25 min).
- Empaquetado: `instalador/crear-paquetes.sh`. A caché de rodas pódese poñer noutra carpeta
  con `ANONIMIZADOR_BUILD=<carpeta local>`.
- Workflow «Paquete MSIX» (`.github/workflows/msix.yml`): só se lanza con etiquetas `msix-v*` /
  `msix-conversor-v*` ou á man (`app=anonimizador|conversor`). Subir ramas ou commits non xera paquetes.
- O rexistro de persoas gárdase en `Documentos\Anonimizador`.
- Non mover nin renomear `docs/store/*`: a Store e o código enlazan a esas rutas.

## Plan de publicación (15/11/2026)

Orde das fases; cada unha cabe nunha sesión curta e termina co seu criterio de «feito».

1. **Fase 0 · Explorador do Anonimizador** (esta sesión; Sonnet · medio): `explorador.py` usa as carpetas
   reais de Windows. Feito = suite en verde + commit en `correcciones-fugas-reductor`.
2. **Fase 1 · Valoración xurídica nova** (Opus · alto): modelo = a do Anonimizador (condicións de uso
   revisadas por un avogado o 15/10/2026, só esas). Feito = informe fóra do repositorio público, cos puntos ⚖️
   para o avogado e as propostas de texto sen aplicar ás condicións aprobadas.
3. **Fase 1b · Mesmo motor Markdown nos dous programas** (Opus · alto; cartafol de traballo propio): hoxe a copia
   `.md` do Anonimizador usa `copia_md.xerar`, pero NON aplica `titulos_pdf.marcar_titulos_md` nin `aforro_ia`
   (cabeceiras repetidas, liñas unidas) coma o Reductor. Feito = a mesma función serve aos dous camiños (con proba
   que o garanta), tests de fugas en verde e sen cambios na anonimización do texto.
4. **Fase 2 · Preparar versións** (Sonnet · medio): fusionar a rama en `main` (só local), subir versións,
   fichas, manuais e paquetes MSIX de ambos programas. Feito = tests en verde, paquetes montados e lista do
   que sube o usuario ao Partner Center. Sen push nin etiquetas `msix-v*` sen permiso do usuario.
   **Condición previa á entrega:** o usuario está probando no portátil Windows o Reductor e o Anonimizador
   (explorador, modo automático sen paradas, lista final con «Revisar», `.zip` en cartafoles). A fase 2 pode
   preparar todo, pero nada se dá por listo para publicar sen o resultado desas probas; calquera fallo que saia
   volve á fase 0/1b antes de montar os paquetes definitivos.
5. **Fase 3 · Limpeza dos rastros de proba** (Haiku · baixo): só o que creou Claude no portátil
   (rexistros temporais, scripts, instaladores e cartafoles de `C:\Users\Public\Documents`). Os cartafoles do
   escritorio decide o usuario cales quedan.

### Estado das fases (15/11/2026, tarde)

- Feitas: 0 (explorador), 1 (informe en `~/Documents/anonimizador-xuridico/VALORACION-JURIDICA-20261115.md`, fóra
  do repositorio), 1b (`markdown_ia.xerar`) e a parte de «versións e textos» da 2 (commits en `motor-md-unico`).
- Para enviar á Store (etiquetas, sen poñer): `msix-v1.1.2` (Anonimizador) e `msix-conversor-v1.2.0` (Reductor), sobre
  o commit final de `main`. Subir a `main` e etiquetar require permiso do usuario; as políticas e condicións enlazadas
  polas fichas tamén teñen que estar en `main` antes do envío.
- Decisións do usuario: R1 do informe (marcar os `.md` con posibles fugas: recomendación «a», liña `posibles_fugas: N`
  na cabeceira; sen facer) e probas en Windows (condición previa).
- ⚖️ Agardan ao avogado: diferenzas A e B das condicións de uso (a do Reductor é un ficheiro novo), parágrafo P1 das
  políticas, subtítulo do Reductor, atribución a Claude e outros puntos da táboa do informe. O Anonimizador
  podería enviarse antes que o Reductor (o informe explica por que); o Reductor debería agardar polas súas condicións.
- Pendente menor: recapturar a pantalla de resultado do manual do Reductor (o texto cambiou) e a copia `NOVEDADES`.

## Ramas vivas

- `follas-csv-aparte`: traballo en curso.
- `instalador-mac-1.1.0`, `instalador-mac-1.1.1`: instaladores de Mac do Anonimizador.

## Onde está o arquivo

O historial de decisións e medicións de 09–10/2026 e os datos reais viven nun repositorio privado
(non público). Para consultalo, contactar co titular.

## Regra de ouro

Non engadir nunca ao repositorio datos reais (nomes, DNI, expedientes). Ver `docs/estudios/` e `medicion/README.md`.
