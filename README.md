# C.R. England — FleetPerform-style Synthetic Demo (20 PDFs)

## Qué contiene

- **20_PDFs/**: veinte invoices digitales **100 % sintéticos**, de una sola tienda ficticia. Su disposición de columnas y resumen se basó en el *tipo* de documento FleetPerform entregado para estudiar el lector. No incluyen identidad, dirección, teléfono, VIN ni referencias del documento original. Cada archivo indica que no es una factura real.
- **expected_document_totals.csv** y **expected_line_items.csv**: valores esperados independientes del parser; permiten verificar cada lectura.
- **manifest.json**: identificadores, fechas, sumas y hashes SHA-256 para evitar duplicados.
- **validation/l10_parser_report.csv**: resultados de ejecutar el L10 sobre los veinte documentos.
- **generate_fleetperform_demo.py**: generador determinista (requiere `reportlab`).
- **GitHub_Update/**: proyecto Streamlit actualizado con vista de PDF lado a lado, lector L10 completo, adaptación de columnas FleetPerform, comparador Same Shop, Global pendiente, y scripts SQL para el demo.

La muestra original aportada por el usuario **no está incluida** en este paquete ni fue subida a servicios de nube.

## Resultado de validación local

- 20 de 20 PDFs: una página, con texto digital.
- 20 de 20 documentos: el L10 reconoció la tabla principal, sus renglones y el total general.
- 132 de 132 partidas: extraídas como renglones del parser.
- 102 de 102 partidas comparables (Parts/Labor): el adaptador reconoció código, categoría y precio unitario impresos.
- 0 inconsistencias aritméticas en los importes generados y extraídos por el adaptador.

**Limitación conocida:** el L10 a veces duplica palabras de la descripción en la columna `Position Codes` de estos archivos sintéticos. La interfaz muestra las tablas sin ocultar ese defecto. No equivale a una certificación de que todas las columnas y todas las facturas reales se interpretarán perfectamente.

## Actualizar Streamlit / GitHub

1. Conserva la versión actual de GitHub como respaldo. Crea una rama `fleetperform-demo` si deseas probar antes de actualizar `main`.
2. Descomprime `GitHub_Update/`. Sustituye en la raíz del repositorio los archivos `app.py`, `invoice_reader_l10.py`, `extracted_items.py`, `roadservice_db.py`, `pricing.py` y `requirements.txt`. Copia también `.streamlit/config.toml` y la carpeta `tests/` si deseas conservar las pruebas.
3. **No subas** credenciales ni `.streamlit/secrets.toml`; deja tu `DATABASE_URL` actual en los Secrets privados de Streamlit.
4. Publica los cambios en GitHub; el servicio Streamlit vuelve a desplegar desde el repositorio.
5. Prueba subir `20_PDFs/FP-DEMO-0001.pdf` en `1. Upload Invoice`. Verás a la izquierda el PDF en un visor nativo `st.pdf`, y a la derecha las tablas y el resumen. Las filas comparables se encuentran en el panel desplegable de detalles.
6. `2. Same Shop Comparison` consulta Supabase y requiere elegir la tienda exacta y confirmar la referencia; `3. Global Comparison` está reservada.

Se usa `streamlit[pdf]>=1.55` para habilitar `st.pdf`, según su documentación oficial. Si no se puede mostrar por configuración del navegador, abre el botón **Download PDF** para comparar manualmente.

## Agregar los 20 registros sintéticos a PostgreSQL/Supabase

**No subas el PDF de origen ni datos reales al entorno gratuito sin autorización de IT.** El demo supone que ya existe el esquema `roadservice_demo` instalado con `sql/01_schema.sql` del Prototipo 01.

1. Entra a tu proyecto Supabase > **SQL Editor**.
2. Abre `GitHub_Update/sql/03_seed_fleetperform_synthetic.sql`, copia su contenido y ejecútalo. Es idempotente por los índices únicos y `ON CONFLICT DO NOTHING`.
3. Esta operación crea una tienda ficticia con `shop_code = FP-DEMO-FORT-LUPTON`, 20 documentos de prueba y 132 partidas (si no estaban ya insertados). Se marca todo como demo; nunca es información real de FleetPerform.
4. Verifica con la consulta al final de ese archivo, que debe devolver **20 synthetic_documents y 132 synthetic_items** para esta tienda. Si la base todavía conserva la semilla de 14 documentos y 57 partidas, el total del esquema será 34 documentos y 189 partidas.
5. Regresa a Streamlit: en **Same Shop Comparison** selecciona `FleetPerform-style Synthetic Demo · Demo Fort Lupton - Synthetic (Fort Lupton, CO)`, carga uno de los PDFs y escoge una partida `Parts` o `Labor`. Los importes anteriores se obtendrán de Supabase.

**Esto inserta los DATOS de las facturas, no los archivos PDF binarios.** Estos objetos se administran por separado mediante Supabase Storage.

## Subir los propios PDFs a Supabase Storage, si también quieres guardarlos

1. En Supabase abre **Storage** > **New bucket**. Nombre sugerido `roadservice-synthetic-pdfs`.
2. Elige **Private** (NO Public), MIME `application/pdf` y un límite razonable de tamaño.
3. Abre el bucket, crea la carpeta `fleetperform/` y sube los 20 archivos desde `20_PDFs/`.
4. Cuando hayas comprobado que los 20 archivos figuran en el bucket y las rutas son `fleetperform/FP-DEMO-0001.pdf`, etc., ejecuta de manera **opcional** `GitHub_Update/sql/04_link_private_storage_after_upload.sql` para registrar rutas internas en `documents.original_pdf_url`.
5. Esas rutas `storage://...` son **referencias internas**, NO enlaces públicos. Esta versión no descarga automáticamente los PDFs almacenados; solamente muestra el PDF que el empleado acaba de cargar.

Para consultar PDFs privados desde una futura aplicación corporativa, necesitarás autenticación, políticas adecuadas y descarga autorizada o enlaces firmados temporales. No publiques el bucket para simplificar la visualización.

## Seguridad y migración futura

- Solo se generan y cargan datos falsos. **No mezcles este esquema `roadservice_demo` con datos reales en el futuro**. Usa un entorno y base corporativos aprobados por IT, roles PostgreSQL de mínimo privilegio, autenticación y control de acceso a PDFs.
- El lector **no guarda PDFs automáticamente** en Supabase. El SQL demo se ejecuta **manualmente** desde SQL Editor.
- El usuario de conexión actual `postgres` es privilegiado. Antes de utilizar invoices reales se deberá sustituir por un rol de consulta restringida y separar la carga/validación del historial.
- Se conservan hashes SHA-256 del contenido PDF para detectar duplicados exactos. No son cifrado ni sustituyen autorización.
- Las muestras ilustran el tipo de documento. No validan una supuesta equivalencia universal entre códigos de diferentes tiendas.

## Validaciones

Tests del adaptador:

```bash
pip install -r requirements.txt pytest
pytest -q tests/
```

El directorio `validation/` contiene un CSV con el resultado de las pruebas locales de los 20 PDFs. No se verificó una conexión real con tu Supabase ni el despliegue de esta actualización en tu cuenta.
