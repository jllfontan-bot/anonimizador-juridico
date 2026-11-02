# Reductor de tokens 1.1.0: mejoras respecto a la 1.0.0

(Antes «Conversor de archivos para IA». La identidad del paquete, el editor y las carpetas internas no cambian.)

## Novedades
- **Nuevo nombre visible: «Reductor de tokens»**, igual en gallego y en castellano: ventana, «Acerca de», manifiesto MSIX,
  instaladores clásicos de Windows y Mac, manuales, ficha de la Store y política de privacidad.
- **Hojas grandes a un .csv aparte.** Las hojas de cálculo de más de 500 filas ya no se meten enteras en el `.md`: se guardan
  en un `.csv` junto a él, y el `.md` lleva solo los nombres de las columnas y la ruta del `.csv`. La IA lee el `.csv` solo si
  lo necesita, así que el `.md` gasta muchos menos tokens.
  - Activado por defecto; en la pantalla, casilla «Hojas grandes a un .csv aparte»; en la CLI, `--sen-csv-aparte` lo desactiva.
  - Con varios documentos homónimos los `.csv` llevan contador; la ruta sale en el resultado y en los avisos.
  - No se aplica al anonimizar (los formatos nuevos siguen sin pruebas de fugas).
- Manual (gallego y castellano) y ficha de la Store con la novedad; capturas regeneradas.

## Otros cambios
- Tests del conversor con un DNI inventado en vez del de un caso real.
- Estudios previos en `docs/estudios/` y `ESTADO.md` con el estado de los dos programas.

## Versiones
Reductor de tokens: 1.1.0 (paquete MSIX 1.1.0.0). Anonimizador jurídico: sin cambios (1.1.1).
