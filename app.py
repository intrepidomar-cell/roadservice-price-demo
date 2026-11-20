"""Road Service — simple PDF reading and same-vendor invoice comparison.
Synthetic demonstration data only. No real C.R. England invoices on this host.
"""
import hashlib
import tempfile
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pdfplumber
import psycopg
import streamlit as st

from invoice_reader_l10 import leer_invoice
from extracted_items import extract_candidates
from psycopg.rows import dict_row

# DB query functions are embedded in this file to avoid module-version mismatches.
# The historical SQL remains parameterized and read-only.
def query(database_url: str, sql: str, args=()):
    with psycopg.connect(
        database_url, sslmode="require", connect_timeout=10, prepare_threshold=None
    ) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, args)
            return cur.fetchall()


def shops(database_url: str):
    return query(database_url, """
        SELECT s.shop_id, s.shop_code, s.shop_name, s.city, s.state_code,
               v.vendor_id, v.vendor_name
        FROM roadservice_demo.shops s
        JOIN roadservice_demo.vendors v ON v.vendor_id = s.vendor_id
        ORDER BY v.vendor_name, s.city, s.state_code
    """)


def historical_prices(database_url: str, vendor_id: int, selected_shop_ids: list[int], item: dict):
    """Find same-vendor historical invoice lines matching a particular parsed item.

    Parts and Labor require exact code and UOM. Misc charge rows (e.g. SHOP SUPPLIES)
    lack a code in the source PDF; use exact normalized category+description and
    compare printed line amounts. No fuzzy matching or cross-vendor fallback.
    """
    if not selected_shop_ids or not item.get('category') in ('Parts', 'Labor', 'Misc'):
        return []
    common = """
        SELECT d.document_id, d.document_number, d.issued_on,
               d.original_pdf_url, d.original_file_sha256,
               s.shop_id, s.shop_name, s.city, s.state_code,
               v.vendor_name, li.category, li.item_code,
               li.description_original, li.quantity, li.unit_of_measure,
               li.unit_price, li.line_amount, li.line_number
        FROM roadservice_demo.line_items li
        JOIN roadservice_demo.documents d ON d.document_id = li.document_id
        JOIN roadservice_demo.shops s ON s.shop_id = d.shop_id
        JOIN roadservice_demo.vendors v ON v.vendor_id = s.vendor_id
        WHERE v.vendor_id = %s
          AND s.shop_id = ANY(%s::bigint[])
          AND d.document_type = 'invoice'
          AND d.validation_status = 'validated'
          AND d.currency_code = 'USD'
          AND li.category = %s
    """
    args = [vendor_id, selected_shop_ids, item['category']]
    if item['category'] == 'Misc':
        # The PDF typically has no part code for fees. Avoid invented codes.
        # Exact normalised-description matching, not a substring fuzzy match.
        import re
        description = re.sub(r'[^A-Z0-9]', '', (item.get('description') or '').upper())
        if not description or item.get('amount') is None:
            return []
        common += """
          AND UPPER(REGEXP_REPLACE(li.description_original, '[^A-Za-z0-9]', '', 'g')) = %s
        """
        args.append(description)
        common += ' ORDER BY li.line_amount DESC, d.issued_on DESC, d.document_number DESC'
    else:
        code, unit = (item.get('code') or '').strip().upper(), (item.get('unit') or '').strip().upper()
        if not code or not unit or item.get('unit_price') is None:
            return []
        common += """
          AND UPPER(TRIM(li.item_code)) = %s
          AND UPPER(TRIM(li.unit_of_measure)) = %s
        """
        args.extend((code, unit))
        common += ' ORDER BY li.unit_price DESC, d.issued_on DESC, d.document_number DESC'
    return query(database_url, common, tuple(args))
from storage_reader import download_private_pdf, verify_pdf_hash, StorageDocumentError

st.set_page_config(page_title='Road Service | Price Comparator', page_icon='🚚', layout='wide')
st.title('Road Service | Price Comparator')
st.caption('PROTOTYPE · SYNTHETIC DATA ONLY · LABORATORY 10')

MAX_PDF_BYTES = 15 * 1024 * 1024
MAX_PAGES = 25


def clean_frame(frame):
    if not isinstance(frame, pd.DataFrame):
        return pd.DataFrame()
    return frame.reset_index(drop=True).fillna('')


def money(value):
    return f'${Decimal(str(value)):,.2f}'


def get_database_url():
    try:
        return st.secrets['DATABASE_URL']
    except (KeyError, FileNotFoundError):
        return None


def get_storage_config():
    try:
        return st.secrets['SUPABASE_URL'], st.secrets['SUPABASE_SECRET_KEY']
    except (KeyError, FileNotFoundError):
        return None, None


def run_l10(pdf_bytes):
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise ValueError('PDF exceeds the 15 MB demo limit.')
    if not pdf_bytes.startswith(b'%PDF-'):
        raise ValueError('The uploaded file does not have a PDF header.')
    with tempfile.TemporaryDirectory(prefix='roadservice_l10_') as folder:
        local_path = Path(folder) / 'invoice.pdf'
        local_path.write_bytes(pdf_bytes)
        with pdfplumber.open(local_path) as pdf:
            if len(pdf.pages) > MAX_PAGES:
                raise ValueError(f'PDF exceeds {MAX_PAGES} pages.')
        return leer_invoice(str(local_path))


def show_l10_tables(result):
    tables = result.get('tablas') or []
    if not tables:
        st.warning('No main table detected by the reader.')
    for i, table in enumerate(tables, 1):
        st.caption(f'Table {i} — {table.get("titulo") or "Line items"}')
        st.dataframe(clean_frame(table.get('datos')), hide_index=True,
                     use_container_width=True, height=260)
    for i, table in enumerate(result.get('subtablas') or [], 1):
        st.caption(f'Economic subtable {i}')
        st.dataframe(clean_frame(table.get('datos')), hide_index=True,
                     use_container_width=True, height=160)
    for i, table in enumerate(result.get('cargos_adicionales') or [], 1):
        st.caption(f'Other charges {i}')
        st.dataframe(clean_frame(table.get('datos')), hide_index=True,
                     use_container_width=True, height=140)
    summary = result.get('resumen_final') or {}
    if isinstance(summary.get('datos'), pd.DataFrame):
        st.markdown('**Economic summary**')
        st.dataframe(clean_frame(summary['datos']), hide_index=True,
                     use_container_width=True, height=210)


def show_historical_pdf(row):
    locator = row.get('original_pdf_url')
    if not locator:
        st.info('This invoice has no PDF linked in Supabase Storage.')
        return
    url, secret = get_storage_config()
    if not url or not secret:
        st.info('PDF viewer needs SUPABASE_URL and SUPABASE_SECRET_KEY in Streamlit Secrets.')
        return
    key = (row['document_id'], locator, row.get('original_file_sha256'))
    if st.session_state.get('pdf_history_key') != key:
        st.session_state['pdf_history_key'] = key
        st.session_state.pop('pdf_history_bytes', None)
        st.session_state.pop('pdf_history_parsed', None)
        st.session_state.pop('pdf_history_error', None)
        try:
            with st.spinner('Loading invoice and checking its extracted tables...'):
                data = download_private_pdf(locator, url, secret)
                parsed = run_l10(data)
            st.session_state['pdf_history_bytes'] = data
            st.session_state['pdf_history_parsed'] = parsed
        except (StorageDocumentError, ValueError) as error:
            st.session_state['pdf_history_error'] = str(error)
        except Exception as error:
            st.session_state['pdf_history_error'] = f'Historical PDF unavailable ({type(error).__name__}).'
    if st.session_state.get('pdf_history_error'):
        st.error(st.session_state['pdf_history_error'])
        return
    data = st.session_state.get('pdf_history_bytes')
    parsed = st.session_state.get('pdf_history_parsed')
    if not data or not parsed:
        return
    verified, reason = verify_pdf_hash(data, row.get('original_file_sha256'))
    if verified is False:
        st.error('Warning: the PDF fingerprint differs from the historical record. Do not trust this link.')
        return
    if verified is None:
        st.warning(reason)
    pdf_col, table_col = st.columns([0.9, 1.1], gap='medium')
    with pdf_col:
        st.markdown('**Historical PDF**')
        st.pdf(data, height=700)
    with table_col:
        st.markdown('**Tables extracted from that PDF — Lab 10**')
        show_l10_tables(parsed)


def item_label(item):
    price = item.get('amount') if item.get('category') == 'Misc' else item.get('unit_price')
    display = money(price) if price is not None else 'Price unavailable'
    code = f" · {item['code']}" if item.get('code') else ''
    return f"{item['description'][:85]}{code} — {display}"


tab_work, tab_global = st.tabs(['1. Invoice & Comparison', '2. Global Comparison'])
with tab_work:
    uploaded = st.file_uploader('Upload invoice (synthetic PDF)', type=['pdf'])
    if uploaded is None:
        for key in ('l10_result', 'l10_items', 'l10_hash', 'pdf_history_key',
                    'pdf_history_bytes', 'pdf_history_parsed'):
            st.session_state.pop(key, None)
        st.info('Upload a PDF to see the original document and the tables extracted by Laboratory 10.')
    else:
        pdf_bytes = uploaded.getvalue()
        pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()
        if st.session_state.get('l10_hash') != pdf_hash:
            st.session_state['l10_hash'] = pdf_hash
            st.session_state.pop('l10_result', None)
            st.session_state.pop('l10_items', None)
            st.session_state.pop('historical_open_id', None)
            try:
                with st.spinner('Reading invoice with Laboratory 10...'):
                    parsed = run_l10(pdf_bytes)
                    items = extract_candidates(parsed)
                st.session_state['l10_result'] = parsed
                st.session_state['l10_items'] = items
            except ValueError as error:
                st.error(str(error))
            except Exception as error:
                st.error(f'Unable to read this digital PDF ({type(error).__name__}).')
        parsed = st.session_state.get('l10_result')
        if parsed:
            st.markdown('### Uploaded invoice')
            left, right = st.columns([0.9, 1.1], gap='medium')
            with left:
                st.markdown('**Original PDF**')
                st.pdf(pdf_bytes, height=720)
            with right:
                st.markdown('**Extracted tables · Laboratory 10**')
                show_l10_tables(parsed)
                with st.expander('Reader warnings and pending rows'):
                    warnings = parsed.get('avisos') or []
                    if not warnings:
                        st.caption('No reader warnings.')
                    for warning in warnings:
                        st.write(str(warning))
                    for field in ('pendientes_l10', 'pendientes_l09', 'sin_clasificar'):
                        df = parsed.get(field)
                        if isinstance(df, pd.DataFrame) and not df.empty:
                            st.caption(field)
                            st.dataframe(clean_frame(df), hide_index=True, use_container_width=True)
            st.divider()
            st.markdown('### Compare with historical prices')
            items = st.session_state.get('l10_items') or []
            items = [i for i in items if i.get('category') in ('Parts', 'Labor', 'Misc') and
                     (i.get('amount') is not None if i.get('category') == 'Misc' else i.get('unit_price') is not None)]
            if not items:
                st.info('No priced items were extracted from this PDF.')
            else:
                item_index = st.selectbox('What do you want to compare?',
                                          range(len(items)), format_func=lambda i: item_label(items[i]))
                chosen_item = items[item_index]
                if not chosen_item.get('amount_consistent'):
                    st.warning('This extracted item needs verification against the original PDF.')
                current = (chosen_item.get('amount') if chosen_item['category'] == 'Misc'
                           else chosen_item.get('unit_price'))
                st.caption(f'Price in uploaded invoice: {money(current)} · '
                           + ('Charge total' if chosen_item['category'] == 'Misc' else 'Unit price / hourly rate'))
                database_url = get_database_url()
                if not database_url:
                    st.warning('DATABASE_URL is not configured in Streamlit Secrets.')
                else:
                    try:
                        available = shops(database_url)
                        vendor_list = sorted({(s['vendor_id'], s['vendor_name']) for s in available},
                                             key=lambda v: v[1].lower())
                        if not vendor_list:
                            st.info('There is no historical shop data in PostgreSQL.')
                        else:
                            is_fleetperform = uploaded.name.upper().startswith('FP-DEMO-') or '892410' in uploaded.name
                            default_vendor = next((i for i, (_, name) in enumerate(vendor_list)
                                                   if 'fleetperform' in name.lower()), None) if is_fleetperform else None
                            vendor_pos = st.selectbox('Historical vendor', range(len(vendor_list)),
                                format_func=lambda i: vendor_list[i][1], index=default_vendor,
                                placeholder='Choose vendor', key='historical_vendor')
                            if vendor_pos is not None:
                                vendor_id, vendor_name = vendor_list[vendor_pos]
                                vendor_shops = [s for s in available if s['vendor_id'] == vendor_id]
                                location_mode = st.radio('Locations',
                                    ['All locations of this vendor', 'Choose locations'], horizontal=True)
                                if location_mode == 'Choose locations':
                                    shop_ids = st.multiselect('Select locations',
                                        options=[s['shop_id'] for s in vendor_shops],
                                        format_func=lambda sid: next(
                                            f"{s['city']}, {s['state_code']} · {s['shop_name']}"
                                            for s in vendor_shops if s['shop_id'] == sid),
                                        default=[s['shop_id'] for s in vendor_shops[:1]])
                                else:
                                    shop_ids = [s['shop_id'] for s in vendor_shops]
                                if shop_ids:
                                    matches = historical_prices(database_url, vendor_id, shop_ids, chosen_item)
                                    if not matches:
                                        st.info('No matching historical prices in these locations.')
                                    else:
                                        is_fee = chosen_item['category'] == 'Misc'
                                        values = [Decimal(str(row['line_amount'] if is_fee else row['unit_price']))
                                                  for row in matches]
                                        rows_display = [{
                                            'Historical price (USD)': money(value),
                                            'Invoice': row['document_number'],
                                            'Date': str(row['issued_on']),
                                            'Location': f"{row['city']}, {row['state_code']}",
                                            'Shop': row['shop_name'],
                                        } for row, value in zip(matches, values)]
                                        st.caption(f'{len(matches)} historical records · Highest to lowest · '
                                                   + ('Charge total' if is_fee else 'Unit price / hourly rate'))
                                        st.dataframe(pd.DataFrame(rows_display), hide_index=True, use_container_width=True)
                                        st.markdown('**Price summary**')
                                        c1, c2, c3 = st.columns(3)
                                        c1.metric('Average', money(sum(values) / len(values)))
                                        c2.metric('Lowest', money(min(values)))
                                        c3.metric('Highest', money(max(values)))
                                        with st.expander('View historical invoice PDF'):
                                            unique_docs = {int(r['document_id']): r for r in matches}
                                            doc_ids = list(unique_docs)
                                            doc_id = st.selectbox('Invoice', doc_ids,
                                                format_func=lambda did: unique_docs[did]['document_number'],
                                                key='historical_invoice_choice')
                                            if st.button('Open PDF and extracted tables', key='open_historical_pdf'):
                                                st.session_state['historical_open_id'] = doc_id
                                            if st.session_state.get('historical_open_id') == doc_id:
                                                show_historical_pdf(unique_docs[doc_id])
                                else:
                                    st.info('Select at least one location.')
                    except psycopg.Error as error:
                        st.error('Could not query PostgreSQL. Check the connection or permissions.')
                        st.caption(f'Error type: {type(error).__name__}; SQLSTATE: {getattr(error, "sqlstate", None) or "N/A"}')

with tab_global:
    st.info('Global Comparison — Coming Soon')
