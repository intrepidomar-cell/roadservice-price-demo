# Road Service — soporte de estimates con operaciones numeradas

Actualización mínima para `roadservice-price-demo`. Este paquete **no incluye documentos reales** ni modifica el Laboratorio 10.

## Instalación en GitHub

1. Conserva un respaldo (commit o rama) de la versión actual que sí inicia.
2. En la raíz del repositorio, junto a `app.py` e `invoice_reader_l10.py`, agrega **`operation_reader.py`**.
3. Abre `app.py` en el editor (lápiz en GitHub, o Visual Studio Code) y localiza esta línea:

   ```python
   from invoice_reader_l10 import leer_invoice
   ```

4. Reemplaza **únicamente esa línea** por:

   ```python
   from operation_reader import leer_invoice
   ```

5. Guarda los cambios y realiza un **commit**. No hace falta borrar `app.py`, `invoice_reader_l10.py` ni `requirements.txt`.
6. La aplicación en Streamlit Community Cloud obtiene los commits del repositorio. Si no actualiza, revisa la rama conectada y los logs.

## Qué hace

- Llama primero al Laboratorio 10 original.
- Si L10 ya encontró tablas, **no hace ningún cambio**.
- Si L10 no encontró tablas y el PDF contiene **operaciones numeradas** con `Labor:`, `Additional Charges:` y `Operation Total:`, recupera esas operaciones como tablas visualizables.
- Recupera `Shop Supplies` del resumen impreso cuando está disponible.
- Conserva el resumen económico, agrega subtotales por operación y señala la ausencia de horas o tarifas unitarias.
- No inventa precios por hora, cantidades ni equivalencias con otros trabajos.

## Prueba segura

Utiliza `Operation_Estimate_Synthetic_Test.pdf`, contenido en este paquete. Es un PDF **100 % ficticio**, creado únicamente para verificar la lectura en una aplicación pública de demostración.

Deberías ver tres operaciones, una tabla adicional de `SHOP SUPPLIES`, y un total de `$720.00` en el resumen.

## Resultados de la prueba local (solo lectura; no guardados en Supabase)

Se probaron dos versiones de un mismo estimate real de Freightliner Northwest: ambas contienen cuatro operaciones, laboratorio 10 detecta el resumen, y el complemento recupera las cuatro operaciones, el cargo por hookup y el importe de shop supplies. Las dos versiones tienen el mismo total de `$1,809.52`. **No** representan dos facturas históricas independientes. El Laboratorio 10 original también fue probado con un PDF sintético de FleetPerform, y su detección de tabla original se mantuvo intacta.

## Límites

Esta extensión es una ayuda estructural para PDFs digitales con este patrón. No es un parser universal ni hace OCR. Los importes de Labor se muestran como totales, no como tarifas/hora. Hay que revisar visualmente los resultados y agregar documentos históricos distintos y validados para comparar por la misma tienda.

Por seguridad, no subas PDFs reales ni credenciales a GitHub o al Streamlit Community Cloud de pruebas sin autorización de IT. Mantén los PDFs originales en una ubicación corporativa aprobada.

## Flujo GitHub más práctico

- Para cambios pequeños: abre el archivo en GitHub, pulsa el lápiz, edita y haz **Commit changes**. No hace falta borrarlo ni volver a subirlo.
- Para cambios frecuentes: clona el repositorio con **GitHub Desktop**, ábrelo en **Visual Studio Code**, guarda cambios, usa **Commit** y luego **Push origin**. Streamlit detectará el nuevo commit. Trabaja en una rama de desarrollo y fusiona a `main` cuando las pruebas pasen.
