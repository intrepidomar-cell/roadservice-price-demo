"""C.R. England — comparador demostrativo; únicamente datos sintéticos.

El prototipo NO procesa PDFs ni tiene autorización de uso productivo.
"""

from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import psycopg
from psycopg.rows import dict_row
import streamlit as st

from pricing import summarize_prices

st.set_page_config(page_title="Road Service | Historical Price Demo", page_icon="🚚", layout="wide")
st.title("Road Service | Historical Price Comparator")
st.caption("PROTOTIPO 01 · Datos 100 % ficticios · USD · Sin procesamiento de PDFs")


def fetch_rows(query: str, parameters: tuple = ()) -> list[dict]:
    """La conexión se crea en el servidor; las credenciales nunca se envían al navegador."""
    try:
        url = st.secrets["DATABASE_URL"]
    except (KeyError, FileNotFoundError):
        st.error("Falta DATABASE_URL en los Secrets de Streamlit. Revisa README.md.")
        st.stop()

    try:
        # Session pooler 5432 es la conexión recomendada en el README.
        # Desactivar auto-prepared statements mantiene compatibilidad con poolers.
        with psycopg.connect(url, sslmode="require", connect_timeout=10, prepare_threshold=None) as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute(query, parameters)
                return cursor.fetchall()
    except psycopg.Error:
        st.error("No fue posible consultar PostgreSQL. Revisa proyecto Supabase, conexión y Secrets.")
        st.stop()


@st.cache_data(ttl=90, show_spinner=False)
def load_catalog() -> list[dict]:
    return fetch_rows(
        """
        SELECT li.category, li.item_code, li.unit_of_measure,
               MIN(li.description_original) AS description,
               COUNT(*) AS sample_count
        FROM roadservice_demo.line_items li
        JOIN roadservice_demo.documents d ON d.document_id = li.document_id
        WHERE d.document_type = 'invoice'
          AND d.validation_status = 'validated'
          AND d.currency_code = 'USD'
          AND li.category IN ('Parts', 'Labor')
        GROUP BY li.category, li.item_code, li.unit_of_measure
        ORDER BY li.category, li.item_code, li.unit_of_measure
        """
    )


@st.cache_data(ttl=90, show_spinner=False)
def load_vendors() -> list[dict]:
    return fetch_rows(
        """SELECT vendor_code, vendor_name
           FROM roadservice_demo.vendors ORDER BY vendor_name"""
    )


with st.sidebar:
    st.header("Estado")
    st.info("Solo pruebas con datos ficticios. No subir facturas ni información interna.")
    if st.button("Comprobar conexión"):
        result = fetch_rows("SELECT current_database() AS database_name, 1 AS connected")
        st.success(f"Conectado a PostgreSQL: {result[0]['database_name']}")
    st.caption("No hay carga de PDFs en esta versión.")

catalog = load_catalog()
if not catalog:
    st.warning("La conexión existe, pero no hay datos comparables. Ejecuta sql/02_seed_demo.sql.")
    st.stop()

st.subheader("1. Seleccionar un concepto equivalente")
st.write(
    "Se comparan precios unitarios solamente si coinciden **categoría, código y unidad de medida**. "
    "También se filtran únicamente *invoices finales validadas* en USD."
)

category = st.radio("Categoría", ["Parts", "Labor"], horizontal=True)
options = [row for row in catalog if row["category"] == category]
if not options:
    st.warning("No hay registros de esta categoría.")
    st.stop()

selected = st.selectbox(
    "Código histórico",
    options,
    format_func=lambda r: f"{r['item_code']} · {r['description']} · {r['unit_of_measure']}",
)

vendors = load_vendors()
vendor_map = {r["vendor_name"]: r["vendor_code"] for r in vendors}

st.subheader("2. Introducir el precio nuevo")
with st.form("price_comparison"):
    a, b, c = st.columns(3)
    with a:
        proposed_price = st.number_input(
            f"Precio nuevo por {selected['unit_of_measure']} (USD)",
            min_value=0.0,
            value=45.0 if category == "Parts" else 110.0,
            step=0.50,
            format="%.2f",
        )
    with b:
        proposed_quantity = st.number_input("Cantidad del nuevo estimate", min_value=0.001, value=1.0, step=1.0)
    with c:
        vendor_label = st.selectbox("Proveedor (filtro opcional)", ["Todos"] + list(vendor_map))

    d1, d2 = st.columns(2)
    with d1:
        start_date = st.date_input("Histórico desde", date.today() - timedelta(days=730))
    with d2:
        end_date = st.date_input("Histórico hasta", date.today())
    submitted = st.form_submit_button("Comparar con el histórico", type="primary", use_container_width=True)

if not submitted:
    st.caption("Introduce un precio y presiona Comparar con el histórico.")
    st.stop()

if start_date > end_date:
    st.error("La fecha inicial no puede ser posterior a la fecha final.")
    st.stop()

vendor_code = vendor_map.get(vendor_label) if vendor_label != "Todos" else None
history = fetch_rows(
    """
    SELECT d.issued_on AS invoice_date,
           d.document_number AS invoice_number,
           v.vendor_name,
           s.shop_name, s.city, s.state_code,
           li.category, li.item_code, li.description_original,
           li.quantity, li.unit_of_measure, li.unit_price,
           li.line_amount, li.task_job_label,
           d.original_pdf_url
    FROM roadservice_demo.line_items li
    JOIN roadservice_demo.documents d ON d.document_id = li.document_id
    JOIN roadservice_demo.shops s ON s.shop_id = d.shop_id
    JOIN roadservice_demo.vendors v ON v.vendor_id = s.vendor_id
    WHERE d.document_type = 'invoice'
      AND d.validation_status = 'validated'
      AND d.currency_code = 'USD'
      AND li.category = %s
      AND li.item_code = %s
      AND li.unit_of_measure = %s
      AND d.issued_on BETWEEN %s AND %s
      AND (%s IS NULL OR v.vendor_code = %s)
    ORDER BY d.issued_on DESC, d.document_number, li.item_code
    """,
    (
        selected["category"], selected["item_code"], selected["unit_of_measure"],
        start_date, end_date, vendor_code, vendor_code,
    ),
)

st.subheader("3. Resultado de la comparación")
if not history:
    st.warning("No existen facturas finales validadas para estos filtros. No se puede inferir un precio comparable.")
    st.stop()

summary = summarize_prices(str(proposed_price), [row["unit_price"] for row in history])
quantity = Decimal(str(proposed_quantity))

m1, m2, m3, m4 = st.columns(4)
m1.metric("Nuevo precio unitario", f"${summary['proposed']:,.2f}")
m2.metric("Mediana histórica", f"${summary['median']:,.2f}")
m3.metric(
    "Diferencia vs mediana",
    f"${summary['difference']:+,.2f}",
    delta=f"{summary['percent']:+.1f}%" if summary['percent'] is not None else "Mediana = $0",
    delta_color="inverse",
)
m4.metric("Partidas históricas", f"{summary['count']}")

st.caption(
    f"Rango histórico: ${summary['minimum']:,.2f} – ${summary['maximum']:,.2f} USD por "
    f"{selected['unit_of_measure']}. Cada renglón histórico cuenta como una observación; "
    "no se ajusta por inflación ni se infiere equivalencia a partir de texto libre."
)
new_total = summary["proposed"] * quantity
median_total = summary["median"] * quantity
st.write(
    f"Para **{quantity:g} {selected['unit_of_measure']}**, el nuevo estimate sería "
    f"**${new_total:,.2f}** frente a **${median_total:,.2f}** a la mediana histórica "
    "(solo este concepto, sin impuestos ni cargos adicionales)."
)

if summary["difference"] > 0:
    st.warning("El precio propuesto está por encima de la mediana histórica comparable.")
elif summary["difference"] < 0:
    st.success("El precio propuesto está por debajo de la mediana histórica comparable.")
else:
    st.info("El precio propuesto coincide con la mediana histórica.")

frame = pd.DataFrame(history)
frame["invoice_date"] = pd.to_datetime(frame["invoice_date"])
frame["unit_price"] = frame["unit_price"].astype(float)
frame["quantity"] = frame["quantity"].astype(float)
frame["line_amount"] = frame["line_amount"].astype(float)

st.subheader("4. Histórico de precios unitarios")
st.scatter_chart(frame, x="invoice_date", y="unit_price", color="vendor_name", height=340)
st.dataframe(
    frame[["invoice_date", "invoice_number", "vendor_name", "shop_name", "city", "state_code", "item_code", "quantity", "unit_of_measure", "unit_price", "line_amount"]],
    column_config={
        "invoice_date": st.column_config.DateColumn("Fecha", format="YYYY-MM-DD"),
        "invoice_number": "Invoice",
        "vendor_name": "Proveedor",
        "shop_name": "Tienda",
        "city": "Ciudad",
        "state_code": "Estado",
        "item_code": "Código",
        "quantity": st.column_config.NumberColumn("Cantidad", format="%.3f"),
        "unit_of_measure": "Unidad",
        "unit_price": st.column_config.NumberColumn("Precio unitario USD", format="$%.2f"),
        "line_amount": st.column_config.NumberColumn("Importe USD", format="$%.2f"),
    },
    hide_index=True,
    use_container_width=True,
)

csv_content = frame.drop(columns=["original_pdf_url"]).to_csv(index=False).encode("utf-8-sig")
st.download_button(
    "Descargar resultados CSV",
    data=csv_content,
    file_name="roadservice_comparacion_demo.csv",
    mime="text/csv",
)
st.caption(
    "Los documentos de este dataset son ficticios y no incluyen PDFs originales. "
    "La trazabilidad a la factura real se integrará solamente con datos autorizados y validados."
)
