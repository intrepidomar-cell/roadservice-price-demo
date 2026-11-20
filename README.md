# C.R. England — Prototipo 02 · Laboratorio 10 + Same Shop Comparison

**Entorno DEMO: solamente datos ficticios y PDFs sintéticos.** No subir facturas reales, documentos internos, credenciales ni datos comerciales de C.R. England al despliegue gratuito sin autorización escrita de IT.

## Qué cambió

El `app.py` del Prototipo 01 solamente comparaba precios manualmente: **no tenía integrado el motor L09 ni L10**. Esta versión integra el **Laboratorio 10 completo**, conservando las capas de los Laboratorios 08 y 09 del notebook original (no se reescribieron sus parsers).

Tres pestañas:

1. **Upload Invoice** — subir PDF digital sintético, ejecutar `leer_invoice()` del Laboratorio 10 y visualizar las tablas, subtablas, cargos y resumen final tal como fueron extraídos.
2. **Same Shop Comparison** — seleccionar la tienda exacta de la base ficticia, una partida extraída y una referencia histórica de esa tienda. Exige confirmación de equivalencia antes de comparar precios unitarios. Solo consulta **facturas finales validadas en USD**.
3. **Global Comparison** — reservado, sin lógica aún.

Ningún PDF ni extracción se incorpora automáticamente a PostgreSQL. Los PDF se procesan en un archivo temporal que se elimina al terminar; el resultado permanece en la sesión de Streamlit hasta que cambie el archivo. La contraseña sigue en `st.secrets["DATABASE_URL"]`.

## Archivos

```text
app.py                 # 3 pestañas Streamlit
invoice_reader_l10.py  # motor L08 + L09 + L10 original, concatenado en orden
extracted_items.py     # vista conservadora de candidatos; no modifica el lector
roadservice_db.py      # consultas SQL filtradas por shop_id
pricing.py             # cálculos del prototipo anterior
requirements.txt       # incluye pdfplumber y Pillow
.streamlit/config.toml # límite de subida 15 MB
.gitignore             # ignora credenciales locales
sql/                   # archivos SQL originales; NO volver a ejecutar
README.md
```

Se conservaron los archivos de esquema, semillas ficticias y pruebas del Prototipo 01. Se añadieron pruebas para normalización y ejecución del motor.

## Cómo subirlo a GitHub

1. Conserva un **respaldo** del repositorio actual (es buena idea crear una nueva rama `prototype-02-l10` antes de actualizar `main`).
2. Descarga este ZIP y **descomprímelo**.
3. En GitHub, abre `intrepidomar-cell/roadservice-price-demo` y la rama de trabajo.
4. Elige **Add file → Upload files**. Sube `app.py`, `invoice_reader_l10.py`, `extracted_items.py`, `roadservice_db.py`, `pricing.py`, `requirements.txt`, `README.md`, y conserva las rutas de `.streamlit/config.toml`, `tests/` y `sql/` tal como están. Si la interfaz de GitHub dificulta conservar carpetas, sube primero los archivos de la raíz y edita el resto en su ubicación correspondiente.
5. Haz **Commit changes** y revisa que `invoice_reader_l10.py` y `app.py` aparezcan en la **raíz** del repo.
6. Streamlit Community Cloud usa `app.py` como entry point. Tras actualizar el repositorio y reconstruirse las dependencias, debería aparecer la interfaz de tres pestañas.
7. En **App settings → Secrets**, mantén la variable `DATABASE_URL` existente; no copies ni vuelvas a publicar la contraseña en GitHub.

**No pegues el notebook `.ipynb` dentro de `app.py`** ni reemplaces el contenido de `app.py` con una sola función: todos los archivos son necesarios.

## Pruebas de funcionamiento

- Abre la app y revisa que se vean exactamente tres pestañas.
- Sube **únicamente** un PDF sintético con texto digital, no escaneado.
- Revisa las tablas y el resumen en Upload Invoice contra el PDF. La detección no implica 100 % de exactitud.
- En Same Shop selecciona **la tienda exacta**, no solo el proveedor. Los registros del SQL original son deliberadamente ficticios (`Demo Fleet Atlanta`, etc.).
- Selecciona una fila extraída; si no coincide con la base ficticia en código/categoría/unidad, el selector no inferirá equivalencia automáticamente. Puedes seleccionar manualmente una referencia solo si confirmas que son conceptos realmente equivalentes. Si no hay precio unitario, no compara.
- Global Comparison debe permanecer como “Coming Soon”.
- Verifica que el esquema en Supabase siga intacto: tres vendors, tres shops, 14 documents y 57 line items. No se requiere ninguna migración SQL.

## Límites actuales

- El Laboratorio 10 **no usa OCR**. PDFs escaneados no serán reconocidos.
- El lector utiliza encabezados variables. `extracted_items.py` trata de localizar código, cantidad, tarifa y unidad conservadoramente; sin evidencia, deja el campo vacío. Las tablas originales del laboratorio siempre se presentan para revisión.
- Una tabla detectada **no** significa una extracción económicamente validada.
- No se infiere el ID de tienda del nombre del PDF: el operador selecciona la tienda.
- Mismo nombre de empresa no implica misma tienda. Las consultas usan `shop_id`.
- Cuando los códigos sintéticos de las tablas demo no coincidan con el PDF, puede no haber coincidencias exactas. Esto **no** es un error del lector.
- El comparador solo contrasta **una partida seleccionada a la vez** en esta versión. No está implementado todavía un comparador por múltiples ítems, equivalencias globales ni comparación automática de Jobs.
- Los criterios de seguridad para uso productivo están pendientes de revisión por IT, roles mínimos y autenticación empresarial.
- La interpretación de una tarifa Labor sin horas o unidad explícita requiere revisión manual. No se inventa $/hora.

## Dependencias y verificación local

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
streamlit run app.py
```

Al ejecutar localmente, agrega `.streamlit/secrets.toml` únicamente en tu equipo, siguiendo `.streamlit/secrets.example.toml`; **nunca** lo subas a GitHub.

## Origen exacto del lector

`invoice_reader_l10.py` procede de estas celdas de código del archivo proporcionado por el usuario:

`CR_England_Laboratorio_10_Multitablas_Jobs_y_Subtablas_WIG_Colab(2).ipynb`

- Celda 10: motor base L08.
- Celda 12: módulo L09.
- Celda 14: módulo L10.

Se concatenaron respetando su orden y sin alterar el código interno. Las celdas de Google Colab, upload de archivos, visualización IPython y pruebas del notebook no están dentro del módulo de producción: las sustituyen componentes Streamlit separados.
