# C.R. England — Prototipo 01: Comparador Histórico de Precios

> **Ambiente de demostración: SOLO DATOS FICTICIOS.** Este paquete no tiene relación con la infraestructura oficial de C.R. England. No contiene invoices reales ni credenciales. No debe emplearse con información interna sin autorización de IT.

## Objetivo

Validar el circuito **aplicación Streamlit en la nube → PostgreSQL en Supabase → consulta histórica → comparación de precio unitario**, accesible desde otro equipo con permiso de visualización. **No se reconstruye ni se integra todavía el lector del Laboratorio 10.**

## Archivos

```text
CR_England_Prototipo_01/
├── app.py                         # Streamlit: formulario, consulta SQL, tabla y gráfica
├── pricing.py                     # Estadística y diferencias de precio
├── requirements.txt              # Dependencias Python
├── sql/
│   ├── 01_schema.sql             # Esquema relacional PostgreSQL
│   └── 02_seed_demo.sql          # 57 partidas ficticias
├── .streamlit/
│   └── secrets.example.toml      # Ejemplo SIN contraseña real
├── .gitignore                    # Evita subir secretos
└── tests/test_pricing.py         # Pruebas unitarias
```

## Paso 1 — Crear la base compartida en Supabase

1. Entra en <https://supabase.com/dashboard> con una cuenta personal para el prototipo. No uses tu cuenta corporativa si no está autorizado.
2. Elige **New project**, asigna un nombre como `roadservice-price-demo`, elige una región y establece una **contraseña de base de datos fuerte**. Guárdala en tu gestor de contraseñas; no la compartas en el chat.
3. Selecciona el plan Free si está disponible para tu cuenta. Espera a que el proyecto quede listo.
4. Abre **SQL Editor → New query**, copia el contenido de `sql/01_schema.sql` y ejecútalo.
5. En una segunda consulta, copia `sql/02_seed_demo.sql` y ejecútalo. El resultado de conteo esperado es:

   | vendors | shops | documents | line_items |
   |---:|---:|---:|---:|
   | 3 | 3 | 14 | 57 |

**Qué acabas de configurar:** un esquema llamado `roadservice_demo`, con relaciones entre proveedores, tiendas, documentos y renglones económicos. La información se encuentra **en PostgreSQL alojado en la nube**, no en un archivo local ni en SQLite.

El esquema personalizado `roadservice_demo` evita exponer estas tablas por defecto a la Data API de Supabase. La aplicación consulta PostgreSQL por conexión de servidor, no desde el navegador. Para una solución corporativa habrá que endurecer los roles y permisos con IT.

## Paso 2 — Obtener la cadena de conexión a PostgreSQL

1. Desde el proyecto de Supabase haz clic en **Connect**.
2. Selecciona **Session pooler** (habitualmente puerto **5432**), no `Direct connection` ni `Transaction pooler`.
3. Copia la URI real indicada por Supabase. Un formato ilustrativo es:

   ```text
   postgresql://postgres.PROJECT_REF:DB_PASSWORD@POOLER_HOST:5432/postgres
   ```

4. Usa exactamente el host, usuario, proyecto y puerto que muestre tu panel. No construyas el host a mano.
5. Si la contraseña contiene caracteres especiales (p. ej. `@`, `:`, `/`, `#`, `%`), deben ir codificados dentro de la URI. **Nunca pegues la URI real en un repositorio ni en este chat.**

**Por qué Session pooler:** admite redes IPv4, frecuente en despliegues de aplicaciones, y evita ciertas limitaciones de conexiones directas IPv6.

Referencia: <https://supabase.com/docs/guides/database/connecting-to-postgres>

## Paso 3 — Probar en tu computadora (opcional)

No necesitas instalar PostgreSQL ni SQLite. Solo Python (3.11+ recomendado) y dependencias.

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate
pip install -r requirements.txt
```

Copia `.streamlit/secrets.example.toml` a `.streamlit/secrets.toml`. Sustituye el valor de `DATABASE_URL` con tu URI real de Supabase y ejecuta:

```bash
streamlit run app.py
```

El archivo `secrets.toml` real está ignorado en Git y no debe subirse. Puedes omitir esta etapa local y desplegar directamente en Streamlit Community Cloud.

## Paso 4 — Publicar el código en GitHub

1. Crea un repositorio **privado** de GitHub, por ejemplo `roadservice-price-demo`.
2. Sube todos los archivos de este paquete conservando las carpetas, **excepto** `.streamlit/secrets.toml` si creaste uno real.
3. Comprueba que `app.py` y `requirements.txt` queden en la raíz del repositorio.
4. No subas PDFs reales, hojas de cálculo internas ni datos históricos de C.R. England.

## Paso 5 — Desplegar en Streamlit Community Cloud

1. Entra en <https://share.streamlit.io> y vincula GitHub.
2. Selecciona **Create app / Deploy an app** y elige tu repositorio, la rama y **Entry point: `app.py`**.
3. En el campo **Secrets** del proceso de despliegue pega una línea TOML como esta, usando el valor real solo allí:

   ```toml
   DATABASE_URL = "postgresql://postgres.PROJECT_REF:DB_PASSWORD@POOLER_HOST:5432/postgres"
   ```

4. Inicia el despliegue. La instancia Streamlit utilizará estas credenciales desde el servidor; no tienen que escribirse en la interfaz.
5. Si el campo Secrets no aparece durante la creación, configúralo después en **App settings → Secrets** y reinicia la aplicación.
6. En **App settings → Sharing**, elige **Only specific people can view this app** e invita solamente a quienes deban probar el prototipo.

**Qué acabas de configurar:** una app hospedada de manera independiente a tu laptop y Colab, conectada a la misma base en Supabase para todos los usuarios autorizados. El acceso privado de Streamlit Community Cloud **no equivale todavía a Microsoft Entra ID**, por lo que no debe tratarse como una solución de seguridad corporativa final.

Referencias:
- <https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy>
- <https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app>
- <https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management>

## Paso 6 — Validar el comparador

En la app elige:

1. **Parts** → `DEMO-P-FILTER-01` (`EA`).
2. **Nuevo precio unitario:** `$45.00`.
3. **Proveedor:** `Todos`.
4. **Fechas:** que incluyan enero 2025–octubre 2026.
5. Haz clic en **Comparar con el histórico**.

Resultado esperado con la muestra: **12 partidas**, mediana **$38.50**, diferencia **+$6.50 por unidad**, aproximadamente **+16.9 %**. Podrás ver la gráfica, talleres y números de factura ficticios.

Prueba también `Labor` y filtra por proveedor. Observa que **el estimate** y **la factura pendiente de validación** no se consideran en las comparaciones, aunque existan dentro de PostgreSQL.

## Qué incluye y qué no incluye esta versión

**Incluye:** relación documental básica, precios unitarios, cantidades, moneda, fecha, proveedor, taller, categoría, estado de validación, filtro de facturas, visualización y CSV de resultados.

**No incluye:** lector de PDFs, OCR, PDF original real, autenticación Microsoft, histórico real, carga de datos, búsqueda semántica de reparaciones similares ni normalización de números de parte de proveedores diferentes.

Para datos reales habrá que definir el criterio de equivalencia entre números de parte/códigos de reparación, una validación documental y permisos adecuados. Los valores de ejemplo **no son referencias reales del mercado**.

## Pruebas y diagnóstico

Ejecuta pruebas de cálculo sin conexión a la base:

```bash
python -m unittest discover -s tests -v
```

Si no carga la app:

- **Falta `DATABASE_URL`:** verifica Secrets, con las comillas TOML.
- **Timeout / could not connect:** comprueba Supabase activo, host real, **Session pooler** y puerto 5432.
- **Password authentication failed:** revisa usuario y contraseña; no copies la contraseña al chat.
- **Relation `roadservice_demo.line_items` does not exist:** ejecuta primero `sql/01_schema.sql` y después `sql/02_seed_demo.sql` en el **mismo proyecto**.
- **No hay datos:** comprueba que `02_seed_demo.sql` haya devuelto 57 partidas.
- **Proyecto en pausa:** los proyectos Free pueden pausarse por inactividad; reanúdalo en Supabase.

## Próximo paso tras validar el circuito

Integrar una salida **validada** del Laboratorio 10 con estas tablas, preservando original/Task/Job, sin tratar detección de tablas como evidencia de extracción exacta. Después: trazabilidad al PDF, desduplicación mediante hash y/o claves de documento, catálogo de equivalencias, permisos de solo lectura para la web, autenticación corporativa y despliegue autorizado.
