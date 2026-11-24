"""Road Service — simple PDF reading and same-vendor invoice comparison.
Synthetic demonstration data only. No real C.R. England invoices on this host. 
"""
import hashlib
import tempfile
from decimal import Decimal
from pathlib import Path

import pandas as pd
import psycopg
import streamlit as st

from core.invoice_router import read_invoice
from invoice_display import show_invoice_tables
from extracted_items import extract_candidates
from roadservice_db import shops_with_prices_for_item, historical_prices
from pricing import summarize_prices
from storage_reader import download_private_pdf, verify_pdf_hash, StorageDocumentError

st.set_page_config(page_title='Road Service | Price Comparator', page_icon='🚚', layout='wide')
st.title('Road Service | Price Comparator')
st.caption('PROTOTYPE · SYNTHETIC DATA ONLY · MODULAR READERS V1')

MAX_PDF_BYTES = 15 * 1024 * 1024


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


def run_reader(pdf_bytes):
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise ValueError('PDF exceeds the 15 MB demo limit.')
    if not pdf_bytes.startswith(b'%PDF-'):
        raise ValueError('The uploaded file does not have a PDF header.')
    with tempfile.TemporaryDirectory(prefix='roadservice_modular_') as folder:
        local_path = Path(folder) / 'invoice.pdf'
        local_path.write_bytes(pdf_bytes)
        return read_invoice(local_path)


def show_extracted_tables(result):
    show_invoice_tables(result)


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
                verified, _ = verify_pdf_hash(data, row.get('original_file_sha256'))
                if verified is False:
                    raise StorageDocumentError('Historical PDF fingerprint mismatch.')
                parsed = run_reader(data)
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
        st.markdown('**Tables extracted from that PDF**')
        show_extracted_tables(parsed)


def item_label(item):
    price = item.get('amount') if item.get('category') == 'Misc' else item.get('unit_price')
    display = money(price) if price is not None else 'Price unavailable'
    code = f" · {item['code']}" if item.get('code') else ''
    return f"{item['description'][:85]}{code} — {display}"


tab_work, tab_global = st.tabs(['1. Invoice & Comparison', '2. Global Comparison'])
with tab_work:
    uploaded = st.file_uploader('Upload invoice (synthetic PDF)', type=['pdf'])
    if uploaded is None:
        for key in ('modular_result', 'modular_items', 'modular_hash', 'pdf_history_key',
                    'pdf_history_bytes', 'pdf_history_parsed'):
            st.session_state.pop(key, None)
        st.info('Upload a PDF to see the original document and the tables extracted by a specialized reader.')
    else:
        pdf_bytes = uploaded.getvalue()
        pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()
        if st.session_state.get('modular_hash') != pdf_hash:
            st.session_state['modular_hash'] = pdf_hash
            st.session_state.pop('modular_result', None)
            st.session_state.pop('modular_items', None)
            st.session_state.pop('historical_open_id', None)
            try:
                with st.spinner('Identifying format and extracting invoice...'):
                    parsed = run_reader(pdf_bytes)
                    items = extract_candidates(parsed)
                st.session_state['modular_result'] = parsed
                st.session_state['modular_items'] = items
            except ValueError as error:
                st.error(str(error))
            except Exception as error:
                st.error(f'Unable to read this digital PDF ({type(error).__name__}).')
        parsed = st.session_state.get('modular_result')
        if parsed:
            st.markdown('### Uploaded invoice')
            left, right = st.columns([0.9, 1.1], gap='medium')
            with left:
                st.markdown('**Original PDF**')
                st.pdf(pdf_bytes, height=720)
            with right:
                st.markdown('**Extracted tables · Specialized reader**')
                show_extracted_tables(parsed)
                with st.expander('Reader warnings and pending rows'):
                    warnings = parsed.warnings
                    if not warnings:
                        st.caption('No reader warnings.')
                    for warning in warnings:
                        st.write(str(warning))
                    if parsed.legacy_result:
                        for field in ('pendientes_l10','pendientes_l09','sin_clasificar'):
                            df=parsed.legacy_result.get(field)
                            if isinstance(df,pd.DataFrame) and not df.empty:
                                st.caption(field)
                                st.dataframe(clean_frame(df),hide_index=True,use_container_width=True)
            st.divider()
            st.markdown('### Compare with historical prices')
            items = st.session_state.get('modular_items') or []
            items = [i for i in items if i.get('category') in ('Parts', 'Labor', 'Misc') and
                     (i.get('amount') is not None if i.get('category') == 'Misc' else i.get('unit_price') is not None)]
            if not items:
                st.info('No eligible comparison items. Printed data remains visible above.')
            else:
                item_index = st.selectbox('What do you want to compare?',
                                          range(len(items)), format_func=lambda i: item_label(items[i]))
                chosen_item = items[item_index]
                if chosen_item.get('amount_consistent') is False:
                    st.warning('This extracted item needs verification against the original PDF.')
                current = (chosen_item.get('amount') if chosen_item['category'] == 'Misc'
                           else chosen_item.get('unit_price'))
                st.caption(f'Price in uploaded {parsed.document_type if parsed.document_type != "unknown" else "document"}: {money(current)} · '
                           + ('Charge total' if chosen_item['category'] == 'Misc' else f"Unit price ({chosen_item.get('unit') or 'unit not specified'})"))
                database_url = get_database_url()
                if not database_url:
                    st.warning('DATABASE_URL is not configured in Streamlit Secrets.')
                else:
                    try:
                        # Only show vendors and shops with an actual comparable historical line.
                        available = shops_with_prices_for_item(database_url, chosen_item)
                        # Never silently compare with an unrelated vendor.
                        import re
                        def norm_vendor(value):
                            return re.sub(r'[^a-z0-9]','',value.lower())
                        source=norm_vendor(parsed.vendor)
                        aliases={'lovesspeedco':('loves','speedco'), 'fleetperform':('fleetperform',)}
                        known=aliases.get(source,(source,) if source else ())
                        available=[v for v in available if any(k in norm_vendor(v['vendor_name']) for k in known)]
                        vendor_list = sorted({(s['vendor_id'], s['vendor_name']) for s in available},
                                             key=lambda v: v[1].lower())
                        if not vendor_list:
                            st.info('No comparable historical prices were found for this item.')
                        else:
                            default_vendor = 0
                            # Keep both selectors visible even when the demo currently has
                            # only one vendor or shop. This is necessary for multi-shop
                            # vendors such as Love's when their history is added later.
                            vendor_pos = st.selectbox(
                                'Historical vendor', range(len(vendor_list)),
                                format_func=lambda i: vendor_list[i][1], index=default_vendor,
                                key=f'historical_vendor_{pdf_hash[:12]}_{item_index}',
                            )
                            vendor_id, vendor_name = vendor_list[vendor_pos]
                            vendor_shops = [s for s in available if s['vendor_id'] == vendor_id]
                            # Here 'all' means all shops with comparable historical
                            # records for the current item, not all physical branches.
                            location_mode = st.radio(
                                'Locations',
                                ['All matching locations', 'Choose locations'], horizontal=True,
                                key=f'location_mode_{pdf_hash[:12]}_{item_index}_{vendor_id}',
                            )
                            if location_mode == 'Choose locations':
                                shop_ids = st.multiselect(
                                    'Select locations',
                                    options=[s['shop_id'] for s in vendor_shops],
                                    format_func=lambda sid: next(
                                        f"{s['city']}, {s['state_code']} · {s['shop_name']}"
                                        for s in vendor_shops if s['shop_id'] == sid
                                    ),
                                    default=[s['shop_id'] for s in vendor_shops],
                                    key=f'location_choice_{pdf_hash[:12]}_{item_index}_{vendor_id}',
                                )
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
                                               + ('Charge total' if is_fee else f"Unit price ({chosen_item.get('unit') or 'unit not specified'})"))
                                    st.dataframe(pd.DataFrame(rows_display), hide_index=True, use_container_width=True)
                                    st.markdown('**Price summary**')
                                    c1, c2, c3 = st.columns(3)
                                    stats=summarize_prices(current, values)
                                    c1.metric('Average', money(stats['average']))
                                    c2.metric('Lowest', money(stats['minimum']))
                                    c3.metric('Highest', money(stats['maximum']))
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
