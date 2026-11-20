# C.R. England — Comparador sencillo (demostración con PDFs sintéticos)

## Qué cambia

- **Dos pestañas:** `1. Invoice & Comparison` (carga + lector L10 + consulta histórica) y `2. Global Comparison` (pendiente).
- Se conserva el visor del PDF nuevo a la izquierda y las **tablas reales que extrae Laboratorio 10** a la derecha.
- Se elimina la tabla desplegable `Comparison candidates & validation notes`.
- `Reader warnings and pending rows` queda disponible bajo un desplegable, para revisar anomalías cuando haga falta.
- Debajo puedes escoger **una partida** del PDF (Parts, Labor o Misc, todo en una lista), un proveedor y **todas sus sucursales** o **solo las sucursales escogidas**.
- Verás **una sola tabla** de precios históricos, **ordenada de mayor a menor**, y tres tarjetas: promedio, precio más barato, precio más caro.
- Al final hay un bloque opcional `View historical invoice PDF`, para consultar **solo el PDF que selecciones**, junto a su extracción L10. El historial de precios no se reprocesa en cada consulta.

## Cómo actualizar GitHub

1. Conserva una versión anterior de los archivos (commit o rama de respaldo).
2. En el repositorio `intrepidomar-cell/roadservice-price-demo`, sustituye **solo** `app.py` y `roadservice_db.py` por los de esta actualización. Sube el archivo real, no su nombre escrito como texto.
3. Haz **Commit changes**. Streamlit Community Cloud tomará el nuevo código del repositorio automáticamente.
4. Conserva los demás módulos de la versión anterior (incluidos `invoice_reader_l10.py`, `extracted_items.py` y `storage_reader.py`). Si no tienes todos, usa el ZIP completo, que los contiene.
5. **No hace falta modificar Supabase ni volver a ejecutar scripts SQL.** Mantén `DATABASE_URL` y, para abrir PDFs históricos, los Secrets privados `SUPABASE_URL` y `SUPABASE_SECRET_KEY`. Nunca incluyas credenciales en GitHub o en una captura.

## Prueba esperada con el PDF de referencia

- Carga `Estimate 892410.pdf` en un entorno autorizado de pruebas **solamente si el tratamiento de ese documento está aprobado**; por ahora usa un PDF sintético equivalente para Streamlit Community Cloud.
- El Laboratorio 10 reconoce el concepto `SHOP SUPPLIES` con importe `$32.41` en el archivo de referencia. Ese valor se usa solo como comprobación del lector, no como registro histórico SQL.
- Selecciona la partida `SHOP SUPPLIES` en `What do you want to compare?`.
- Selecciona el proveedor `FleetPerform-style Synthetic Demo`.
- En `Locations`, selecciona `All locations of this vendor`.
- El SQL de demostración actualmente contiene **una única ubicación** para FleetPerform sintético: Fort Lupton, CO. Por lo tanto, `All locations` y `Choose locations` producirán los mismos resultados hasta que existan más sucursales de ese proveedor.
- Deben aparecer **20 precios históricos** de Shop Supplies, ordenados de mayor a menor. Promedio **$35.18**, mínimo **$27.10**, máximo **$42.33**.
- Si quieres, despliega `View historical invoice PDF`, escoge un invoice y presiona `Open PDF and extracted tables`. Esto requiere que los PDFs estén en el bucket privado de Storage y sus rutas enlazadas en PostgreSQL.

## Lógica de coincidencias

- **Parts y Labor**: misma categoría, código y unidad, dentro del proveedor y las sedes seleccionadas. Labor se compara por tarifa, no automáticamente por horas totales.
- **Misc**: mismo texto de concepto normalizado y categoría. En `SHOP SUPPLIES`, que no trae código en el PDF, se compara el **importe del cargo**. No se hace búsqueda difusa ni se inventan equivalencias.
- Solo se incluyen invoices finales validados, en USD. El nuevo PDF **no se guarda automáticamente** en PostgreSQL ni Storage.
- Para ampliar el historial a más sucursales hace falta registrar esas sucursales y sus líneas económicas en la base; seleccionar `All locations` **no crea datos inexistentes**.

## Seguridad y estado

Este es un prototipo **exclusivamente sintético**. No cargues documentos internos reales en Streamlit Community Cloud ni en un servicio externo sin aprobación de IT. El proyecto no tiene aún controles corporativos de acceso, roles mínimos ni flujo autorizado de ingestión automática.

## Pruebas

La actualización pasó verificaciones de sintaxis y las pruebas unitarias locales del adaptador L10 y la selección de precios. No se ha ejecutado en tu despliegue real ni se ha conectado a tus credenciales de Supabase.
