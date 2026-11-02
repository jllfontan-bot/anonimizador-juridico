# Estado dos dous programas (02/11/2026)

Este repositorio contén dous programas que comparten o mesmo motor:
o **Anonimizador xurídico** e o **Reductor de tokens** (antes «Conversor de arquivos para IA»).
Este ficheiro é un resumo curto. Non leva datos reais nin notas persoais.

## Anonimizador xurídico

- Microsoft Store: **publicado**, Store ID `9PK1J429MNN5`.
- Versión vixente: **1.1.1** (ficheiro `VERSION`), tamén publicada na Store.
- Política de privacidade: `docs/store/politica-privacidad.md`; condicións de uso: `docs/store/condiciones-de-uso.md`.
- Só Windows 10/11 na Store. As versións de Mac e Linux quitáronse da oferta do Anonimizador;
  hai instaladores clásicos de Mac nas ramas `instalador-mac-*`.
- Pendente: nada urxente.

## Reductor de tokens (antes «Conversor de arquivos para IA»)

- Microsoft Store: **publicado**, Store ID `9NMM4DRL6FCC`, paquete 1.0.0.0.
- Política de privacidade: `docs/store/politica-privacidad-conversor.md`; ficha: `docs/store/ficha-store-conversor.md`.
- Instaladores clásicos sen asinar para Windows e Mac (`instalador/crear-paquetes.sh windows-conversor|mac-conversor`).
- Notas de deseño e límites en `src/anonimizador/formatos/ESCONDITES.md` e estudos previos en `docs/estudios/`.
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

## Ramas vivas

- `follas-csv-aparte`: traballo en curso.
- `instalador-mac-1.1.0`, `instalador-mac-1.1.1`: instaladores de Mac do Anonimizador.

## Onde está o arquivo

O historial de decisións e medicións de 09–10/2026 e os datos reais viven nun repositorio privado
(non público). Para consultalo, contactar co titular.

## Regra de ouro

Non engadir nunca ao repositorio datos reais (nomes, DNI, expedientes). Ver `docs/estudios/` e `medicion/README.md`.
