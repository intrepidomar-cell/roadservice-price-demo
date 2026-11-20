"""Road Service — Prototipo 02. Solo PDFs sintéticos autorizados para demostración."""

import hashlib
import tempfile
from pathlib import Path
from decimal import Decimal

import pandas as pd
import pdfplumber
import psycopg
import streamlit as st

from invoice_reader_l10 import leer_invoice
from extracted_items import extract_candidates
from pricing import summarize_prices
from roadservice_db import shops, catalog, history

st.set_page_config(page_title="Road Service | Invoice Comparator", page_icon="🚚", layout="wide")
st.title("Road Service | Invoice Price Comparator")
st.caption("PROTOTYPE 02 · SYNTHETIC TEST DATA ONLY · Lab 10 PDF Reader")

MAX_PDF_BYTES = 15 * 1024 * 1024
MAX_PAGES = 25


def clean_frame(frame):
    """Show original rows while keeping the source tables untouched."""
    if not isinstance(frame, pd.DataFrame):
        return pd.DataFrame()
    return frame.reset_index(drop=True).fillna("")


def get_url():
    try:
        return st.secrets["DATABASE_URL"]
    except (KeyError, FileNotFoundError):
        return None


def safe_sql_error(exc):
    st.error("Could not query PostgreSQL. Check the database connection and permissions.")
    st.caption(f"Error type: {type(exc).__name__}; SQLSTATE: {getattr(exc, 'sqlstate', None) or 'N/A'}")


def run_l10(pdf_bytes):
    """Use a short-lived local file; reader works with Path, not Google Colab."""
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise ValueError("PDF exceeds the 15 MB demo limit.")
    if not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("The uploaded file does not have a PDF header.")
    with tempfile.TemporaryDirectory(prefix="roadservice_l10_") as directory:
        filepath = Path(directory) / "upload.pdf"
        filepath.write_bytes(pdf_bytes)
        with pdfplumber.open(filepath) as pdf:
            if len(pdf.pages) > MAX_PAGES:
                raise ValueError(f"PDF exceeds the {MAX_PAGES}-page demo limit.")
        return leer_invoice(str(filepath))


# Files are processed only in the user's session. Nothing is inserted into Supabase.
tab_upload, tab_shop, tab_global = st.tabs(
    ["1. Upload Invoice", "2. Same Shop Comparison", "3. Global Comparison"]
)

with tab_upload:
    uploaded = st.file_uploader("Upload synthetic digital PDF", type=["pdf"], help="Only synthetic demo PDFs. Scanned PDFs require OCR, which is not supported.")
    if uploaded is None:
        st.session_state.pop("l10_result", None)
        st.session_state.pop("l10_candidates", None)
        st.session_state.pop("l10_pdf_hash", None)
        st.info("Upload a synthetic PDF to preview the tables extracted by Lab 10.")
    else:
        pdf_bytes = uploaded.getvalue()
        digest = hashlib.sha256(pdf_bytes).hexdigest()
        if st.session_state.get("l10_pdf_hash") != digest:
            st.session_state.pop("l10_result", None)
            st.session_state.pop("l10_candidates", None)
            st.session_state["l10_pdf_hash"] = digest
            try:
                with st.spinner("Reading invoice with Lab 10..."):
                    result = run_l10(pdf_bytes)
                st.session_state["l10_result"] = result
                st.session_state["l10_candidates"] = extract_candidates(result)
            except ValueError as exc:
                st.error(str(exc))
            except (Exception,) as exc:
                # Avoid printing raw document content, credentials or traceback.
                st.error("The PDF could not be processed by the digital invoice reader.")
                st.caption(f"Error type: {type(exc).__name__}")
        result = st.session_state.get("l10_result")
        if result:
            st.caption(f"Parser: {result.get('parser', '—')} · L10 strategy: {result.get('estrategia_l10', '—')} · Pages: {result.get('paginas', '—')}")
            tables=result.get('tablas',[])
            subtables=result.get('subtablas',[])
            st.write(f"**{len(tables)} tables · {sum(len(t.get('datos',[])) for t in tables)} extracted rows · {len(subtables)} subtables**")
            left,right=st.columns([0.9,1.1],gap='medium')
            with left:
                st.markdown('**Original PDF**')
                st.pdf(pdf_bytes,height=780,alt='Uploaded PDF for visual verification')
                st.download_button('Download PDF',data=pdf_bytes,file_name=uploaded.name,mime='application/pdf')
            with right:
                st.markdown('**Extracted tables (Laboratory 10)**')
                if result.get('parser')=='REQUIERE OCR':st.warning('Scanned PDF: OCR is outside this prototype.')
                if not tables:st.warning('No main table detected; extraction needs review.')
                for t in tables:
                    st.caption(f"Table {t.get('id','')} — {t.get('titulo') or 'Main table'}")
                    st.dataframe(clean_frame(t.get('datos')),hide_index=True,use_container_width=True,height=260)
                for i,sub in enumerate(subtables,start=1):
                    st.caption(f'Economic subtable {i}')
                    st.dataframe(clean_frame(sub.get('datos')),hide_index=True,use_container_width=True,height=170)
                for i,charges in enumerate(result.get('cargos_adicionales',[]),start=1):
                    st.caption(f'Other charges {i}')
                    st.dataframe(clean_frame(charges.get('datos')),hide_index=True,use_container_width=True,height=150)
                summ=result.get('resumen_final')
                if summ and isinstance(summ.get('datos'),pd.DataFrame):
                    st.markdown('**Economic summary**')
                    st.dataframe(clean_frame(summ['datos']),hide_index=True,use_container_width=True,height=235)
                with st.expander('Comparison candidates & validation notes'):
                    items=st.session_state.get('l10_candidates',[])
                    if items:
                        frame=pd.DataFrame([dict(Type=x['category'],Code=x['code'],Description=x['description'],
                            Qty=str(x['quantity'] or ''),Unit=x['unit'],Rate=str(x['unit_price'] or ''),
                            Amount=str(x['amount'] or ''),Check=('OK' if x['amount_consistent'] else 'REVIEW'),
                            Notes=x['validation_notes']) for x in items])
                        st.dataframe(frame,hide_index=True,use_container_width=True)
                    else:st.caption('No candidates extracted.')
                with st.expander('Reader warnings and pending rows'):
                    for note in result.get('avisos',[]):st.write(f'• {note}')
                    for key in ('pendientes_l10','pendientes_l09','sin_clasificar'):
                        table=result.get(key)
                        if isinstance(table,pd.DataFrame) and not table.empty:
                            st.caption(key)
                            st.dataframe(clean_frame(table),hide_index=True,use_container_width=True)
            st.caption('Compare original PDF and extracted table side by side. No upload or extraction is automatically stored in Supabase.')

with tab_shop:
    result = st.session_state.get("l10_result")
    items = st.session_state.get("l10_candidates", [])
    if not result:
        st.info("Upload an invoice in the first tab to begin.")
    elif not items:
        st.info("No extracted line items are available for comparison.")
    else:
        st.caption("Compare one extracted line against validated final invoices from the SAME shop. No cross-shop matching.")
        url = get_url()
        if not url:
            st.warning("DATABASE_URL is missing from Streamlit Secrets.")
        else:
            try:
                all_shops = shops(url)
                shop_index = st.selectbox(
                    "Historical shop",
                    range(len(all_shops)),
                    format_func=lambda i: f"{all_shops[i]['vendor_name']} · {all_shops[i]['shop_name']} ({all_shops[i]['city']}, {all_shops[i]['state_code']})",
                    index=None, placeholder="Select exact shop",
                ) if all_shops else None
                if shop_index is None:
                    st.info("Select the shop that issued the PDF; it is not automatically inferred from the file name.")
                else:
                    shop = all_shops[shop_index]
                    references = catalog(url, shop["shop_id"])
                    display_items = pd.DataFrame([
                        {"Row": it["row_id"], "Job / Task": it["job"], "Description": it["description"],
                         "Category (suggested)": it["category"], "Code": it["code"],
                         "Qty": float(it["quantity"]) if it["quantity"] is not None else None,
                         "UOM": it["unit"], "Unit Price": float(it["unit_price"]) if it["unit_price"] is not None else None}
                        for it in items
                    ])
                    st.dataframe(display_items, hide_index=True, use_container_width=True)
                    if not references:
                        st.warning("No validated historical invoice lines exist for this shop.")
                    else:
                        chosen_i = st.selectbox(
                            "Extracted line to compare",
                            range(len(items)),
                            format_func=lambda i: f"{items[i]['row_id']} · {items[i]['description'][:95]}",
                        )
                        item = items[chosen_i]
                        exact = [i for i, ref in enumerate(references)
                                 if ref["category"] == item["category"]
                                 and ref["item_code"].strip().upper() == item["code"].strip().upper()
                                 and ref["unit_of_measure"].strip().upper() == item["unit"].strip().upper()
                                 and item["code"] and item["unit"]]
                        default_ref = exact[0] if exact else None
                        selected_ref = st.selectbox(
                            "Historical reference for this shop",
                            range(len(references)),
                            format_func=lambda i: f"{references[i]['category']} · {references[i]['item_code']} · {references[i]['description']} · {references[i]['unit_of_measure']} ({references[i]['observations']})",
                            index=default_ref,
                            placeholder="Choose an equivalent historical concept",
                        )
                        if default_ref is None:
                            st.caption("No exact code/category/UOM match was found. Manual matching requires verification.")
                        if not item.get('amount_consistent', False):
                            st.warning('This row has an unverified line total or quantity. Check the original PDF before comparing.')
                        if item["unit_price"] is None:
                            st.warning("The reader did not identify a verifiable unit price for this row. Review the extracted table before comparing.")
                        elif item["unit_price"] < 0:
                            st.warning("This line has a negative unit amount (possible credit); this demo does not compare credits.")
                        elif item["price_source"] == "derived_from_total_and_quantity":
                            st.caption("Unit price was calculated as printed amount ÷ printed quantity; verify the source cells.")
                        confirmed = st.checkbox("I verified the part/service, unit and extracted price are equivalent to the chosen reference.")
                        if st.button("Compare selected line", type="primary", disabled=not(confirmed and selected_ref is not None and item["unit_price"] is not None and item["unit_price"] >= 0 and item.get("amount_consistent", False))):
                            ref = references[selected_ref]
                            hist = history(url, shop["shop_id"], ref["category"], ref["item_code"], ref["unit_of_measure"])
                            if not hist:
                                st.warning("No eligible historical records found.")
                            else:
                                stats = summarize_prices(str(item["unit_price"]), [r["unit_price"] for r in hist])
                                st.markdown("**Price comparison**")
                                c1, c2, c3, c4 = st.columns(4)
                                c1.metric("New unit price", f"${stats['proposed']:,.2f}")
                                c2.metric("Historical median", f"${stats['median']:,.2f}")
                                c3.metric("Difference", f"${stats['difference']:+,.2f}", delta=(f"{stats['percent']:+.1f}%" if stats['percent'] is not None else "N/A"), delta_color="inverse")
                                c4.metric("Historical lines", str(stats["count"]))
                                st.caption("Historical references: validated final invoices, USD, from this shop only. Confirmed equivalence does not mean prices are objectively fair.")
                                df = pd.DataFrame(hist)
                                df["unit_price"] = df["unit_price"].astype(float)
                                df["invoice_date"] = pd.to_datetime(df["invoice_date"])
                                st.scatter_chart(df, x="invoice_date", y="unit_price", height=260)
                                st.dataframe(df, hide_index=True, use_container_width=True)
            except psycopg.Error as exc:
                safe_sql_error(exc)

with tab_global:
    st.info("Global Comparison — Coming Soon")
