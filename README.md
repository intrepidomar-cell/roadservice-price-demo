# Road Service · Prototipo 02 · Historical PDF Viewer (solo datos sintéticos)

## Resultado

Esta actualización **conserva las tres pestañas** y el Laboratorio 10 existente:

1. **Upload Invoice:** recibe un PDF digital sintético, lo procesa con `leer_invoice()` del Laboratorio 10 y muestra el PDF original junto a sus tablas extraídas.
2. **Same Shop Comparison:** compara una partida del estimate contra **datos de PostgreSQL de la misma tienda**. Debajo permite elegir **una factura histórica** (de esa misma tienda), descargar *solamente ese PDF* desde un bucket **privado** de Supabase Storage y ejecutarle **Laboratorio 10 en ese momento**. Muestra su PDF y sus tablas, y permite examinar sus registros SQL.
3. **Global Comparison:** permanece vacía como `Coming Soon`.

**Importante:** el historial sintético de los 20 documentos fue cargado previamente mediante `03_seed_fleetperform_synthetic.sql`; **esos registros NO fueron insertados a partir del lector**. La extracción L10 en el visor histórico se ejecuta realmente sobre el PDF seleccionado y se contrasta contra los datos que ya existen en SQL. Esta versión **NO sube PDFs automáticamente**, **NO ingiere resultados L10 a la base** y **NO vuelve a leer los 20 PDFs en cada comparación**. Es exactamente la separación requerida para validar la interfaz antes de desarrollar actualizaciones del historial.

## Paso A. Subir los 20 PDFs a Supabase Storage

Requisitos: ya ejecutaste `03_seed_fleetperform_synthetic.sql` y obtuviste 20 documentos / 132 partidas en PostgreSQL.

1. Entra en [Supabase Dashboard](https://supabase.com/dashboard), abre tu proyecto DEMO y elige **Storage**.
2. Crea un bucket llamado exactamente **`roadservice-synthetic-pdfs`**. Déjalo **Private**, no público. Puedes limitar a `application/pdf` y 15 MB por archivo.
3. Abre el bucket, crea la carpeta exacta **`fleetperform`**, en minúsculas.
4. Dentro de `fleetperform`, sube los 20 archivos `FP-DEMO-0001.pdf` ... `FP-DEMO-0020.pdf` **desde el ZIP sintético** que ya recibiste. No subas el estimate original con datos reales.
5. Confirma que existen rutas como `fleetperform/FP-DEMO-0001.pdf` (el nombre y las mayúsculas deben coincidir).

## Paso B. Asociar cada documento SQL con su PDF

1. En Supabase > **SQL Editor**, ejecuta **`sql/04_link_private_storage_after_upload.sql`**, incluido en este proyecto. Esto llena `roadservice_demo.documents.original_pdf_url` con rutas como:

   `storage://roadservice-synthetic-pdfs/fleetperform/FP-DEMO-0001.pdf`

2. Ejecuta **`sql/05_verify_pdf_links.sql`**. Esperas ver **20 filas y `storage_status = FOUND`**.
3. Si sale `MISSING`, corrige el nombre de bucket, carpeta o archivo en Storage. No cambies el código Python ni vuelvas a ejecutar el seed de 132 partidas para arreglar una ruta.

**Distinción:** SQL solo vincula una referencia. No almacena el archivo binario. El objeto PDF vive en Storage.

## Paso C. Actualizar GitHub / Streamlit

1. Conserva una copia o rama de tu aplicación actual. Después descomprime este ZIP.
2. Sube a la **raíz de tu repositorio** los archivos `app.py`, `roadservice_db.py`, `storage_reader.py`, `reconciliation.py`, `invoice_reader_l10.py`, `extracted_items.py`, `pricing.py`, y `requirements.txt` (los archivos existentes se sustituyen; los nuevos se agregan). `sql/` es para Supabase y **no necesita desplegarse** para que Streamlit funcione.
3. Haz **Commit changes** y revisa el redeploy de Streamlit.
4. En **Streamlit > Manage app > Settings > Secrets** mantén `DATABASE_URL` y agrega dos valores **privados** (sustituye los marcadores por valores reales):

   ```toml
   DATABASE_URL = "postgresql://TU_CONEXION_POSTGRESQL"
   SUPABASE_URL = "https://TU_PROJECT_REF.supabase.co"
   SUPABASE_SECRET_KEY = "sb_secret_TU_CLAVE_PRIVADA"
   ```

   `SUPABASE_URL` se obtiene del panel Connect / Project URL. La `SUPABASE_SECRET_KEY` es un **secreto de servidor privilegiado** desde Supabase > Project Settings > API Keys. La biblioteca oficial `supabase` se conecta con esa clave **solo desde el servidor de Streamlit**, sin mostrarla al navegador.

5. **Haz privada la aplicación antes de agregar la clave de servidor.** No utilices esta estructura para documentos empresariales reales sin revisión de IT: las claves secretas pueden saltarse RLS y el prototipo aún no implementa autenticación ni permisos por empleado. No envíes la clave por chat, no la pegues en código ni la subas a GitHub.

6. Sube `FP-DEMO-0001.pdf` en **Upload Invoice**, comprueba las tablas. En **Same Shop Comparison**, selecciona la tienda **Demo Fort Lupton - Synthetic**, elige una factura histórica, y verifica las dos columnas: **PDF histórico** (izquierda) y **Lab 10 extraído en ese momento** (derecha). Expande **Stored SQL rows** si quieres ver los registros de SQL.

La aplicación verifica el SHA-256 del PDF recibido contra el hash guardado en `documents.original_file_sha256`; si no coincide, muestra un error de integridad. Adicionalmente compara Parts y Labor por categoría, código, UOM, cantidad y precio unitario. Los cargos Misc no se contabilizan en esa conciliación porque el parser aún no suministra códigos de concepto suficientemente seguros.

## Qué no está implementado

- Carga automática de PDFs a Supabase Storage.
- Procesamiento semanal / por lotes e inserción automática de extracción en SQL.
- Autenticación corporativa, mínimo privilegio y seguridad de producción.
- Comparación global entre talleres.

La base conserva registros SQL sintéticos preinsertados. Esta nueva vista demuestra visualmente qué produce L10 al leer la fuente histórica y si coincide con las filas almacenadas. **No sustituye las futuras pruebas de ingestión automática.**

## Comprobaciones efectuadas localmente

- `python -m pytest -q tests` — pruebas unitarias del adaptador, rutas de Storage, integridad SHA-256 y conciliación.
- `python -m py_compile ...` — compila los archivos Python.
- Lector L10 ejecutado sobre los 20 PDFs sintéticos; 102/102 partidas Parts/Labor coincidieron en código, UOM, cantidad y precio unitario con el manifiesto generado.

**No** se ha probado la descarga en tu cuenta Supabase real, porque no tenemos sus credenciales y no debemos compartirlas. Tampoco se ha realizado el redeploy real de la aplicación.
