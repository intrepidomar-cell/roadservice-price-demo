"""Shared, read-only invoice view: document information, detail, economic summary.
Never modify parser results, prices, comparison eligibility or database records.
"""
from decimal import Decimal

import pandas as pd
import streamlit as st


def _display(value):
    return format(value, 'f') if isinstance(value, Decimal) else '' if value is None else value


def _frame(frame, max_height=720):
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        st.caption('No extracted rows in this section.')
        return
    st.dataframe(frame.reset_index(drop=True), hide_index=True, use_container_width=True,
                 height=min(max_height, 39 + 35 * len(frame)))


def _rows(items):
    # Keep the reader's printed columns, not internal matching classifications.
    return [{'Page': str(item.page) if item.page is not None else '', **{k: str(_display(v)) for k, v in item.printed.items()}}
            for item in items]


def _note(label, value):
    if value and str(value).strip():
        st.markdown(f'**{label}**')
        st.text(str(value))


def _document_information(doc):
    with st.expander('Document Information', expanded=False):
        fields = {'Vendor': doc.vendor, 'Document type': doc.document_type.title(),
                  'Pages': doc.pages, 'Reader': doc.reader, **doc.metadata}
        _frame(pd.DataFrame([{'Field': k, 'Value': str(v)} for k, v in fields.items()
                             if v is not None and v != '']))
        if doc.checks:
            st.markdown('**Validation / reconciliation**')
            for name, delta in doc.checks.items():
                if delta is None:
                    st.caption(f'{name}: unavailable')
                elif abs(delta) <= Decimal('.02'):
                    st.caption(f'{name}: matches (within $0.02)')
                else:
                    st.warning(f'{name}: ${delta:,.2f} difference')
        if doc.warnings:
            st.markdown('**Reader warnings**')
            for warning in doc.warnings:
                st.write(str(warning))
        if doc.legacy_result is not None:
            for key in ('pendientes_l10', 'pendientes_l09', 'sin_clasificar'):
                frame = doc.legacy_result.get(key)
                if isinstance(frame, pd.DataFrame) and not frame.empty:
                    st.caption(key)
                    _frame(frame)
        if doc.notes.get('Tire details'):
            _note('Tire details', doc.notes['Tire details'])


def _operation_frame(op, items):
    """Display-only subtotal rows in the original economic column, never new items."""
    rows = _rows(items)
    # Decisiv prints Parts Total after the parts and before additional charges.
    # Use the actual column name for totals. No subtotal is calculated here.
    columns = list(dict.fromkeys(k for row in rows for k in row))
    if not columns:
        columns = ['Page', 'Description', 'Totals']
    description = next((k for k in columns if k.casefold() == 'description'), None)
    total = next((k for k in columns if k.casefold() in ('totals', 'total', 'ext amt', 'extension', 'amount')), None)
    if description is None:
        description = 'Description'; columns.append(description)
    if total is None:
        total = 'Totals'; columns.append(total)
    def closing(label, value, page=None):
        return {**dict.fromkeys(columns, ''), 'Page': str(page) if page is not None else '',
                description: label, total: _display(value)}
    if op.parts_total is not None:
        # Keep original line order and insert at the end of the parts section.
        last = max((n for n, item in enumerate(items) if item.category == 'Parts'), default=None)
        pos = last + 1 if last is not None else next((n for n, item in enumerate(items) if item.category == 'Misc'), len(rows))
        rows.insert(pos, closing('Parts Total', op.parts_total))
    rows.append(closing('Operation Total' if op.total is not None else 'Operation Total (not printed)',
                        op.total, op.end_page))
    return pd.DataFrame(rows, columns=columns).fillna('')


def _legacy_detail(result):
    """Group L10 subtables with their explicit parent, never guess associations."""
    tables = result.get('tablas') or []
    extras = [('Subtotal', t) for t in (result.get('subtablas') or [])]
    extras += [('Additional charges', t) for t in (result.get('cargos_adicionales') or [])]
    shown = set()
    if not tables:
        st.warning('No main table detected in this PDF.')
    for n, table in enumerate(tables, 1):
        if table.get('hidden_in_operation_display'):
            continue
        if n > 1:
            st.divider()
        st.markdown(f"**{table.get('titulo') or f'Table {n}'}**")
        _frame(table.get('datos'))
        for index, (label, sub) in enumerate(extras):
            parent = sub.get('tabla_id') or sub.get('task_id')
            if parent is not None and str(parent) == str(table.get('id')) and index not in shown:
                st.caption(sub.get('titulo') or label)
                _frame(sub.get('datos'))
                shown.add(index)
    for index, (label, sub) in enumerate(extras):
        if index not in shown:
            st.caption(f"{sub.get('titulo') or label} (no confirmed parent table)")
            _frame(sub.get('datos'))


def show_invoice_tables(doc):
    if doc.reader == 'unsupported':
        st.warning('Invoice format not recognized. No extraction or comparison performed.')
        return
    _document_information(doc)
    with st.expander('Repair Details', expanded=True):
        _note('Complaint', doc.notes.get('Complaint'))
        if doc.legacy_result is not None:
            _legacy_detail(doc.legacy_result)
        elif doc.operations:
            for index, op in enumerate(doc.operations):
                if index:
                    st.divider()
                st.markdown(f'**{op.number}. {op.title}**' + (' — WARRANTY' if op.warranty else ''))
                st.caption(f'Pages {op.page}–{op.end_page}' + (f' · Operation code: {op.code}' if op.code else ''))
                for label in ('complaint', 'cause', 'correction'):
                    _note(label.title(), op.notes.get(label))
                items = [i for i in doc.items if i.operation == f'{op.number}. {op.title}']
                _frame(_operation_frame(op, items))
        elif doc.items:
            _frame(pd.DataFrame(_rows(doc.items)))
        else:
            st.warning('No detail rows detected.')
        st.caption('Blank = not printed; zero = printed zero. Subtotals are not additional charges.')
    # Keep the original L10 summary (labels, page and raw printed amounts).
    if doc.legacy_result is not None:
        summary = (doc.legacy_result.get('resumen_final') or {}).get('datos')
    else:
        summary = pd.DataFrame([{'Concept': k, 'Amount (USD)': f'${v:,.2f}'}
                                for k, v in doc.summary.items()])
    if isinstance(summary, pd.DataFrame) and not summary.empty:
        with st.expander('Economic Summary', expanded=True):
            _frame(summary, max_height=620)
            if any(delta is None or abs(delta) > Decimal('.02') for delta in doc.checks.values()):
                st.caption('Some validation checks require review. See Document Information.')
    # Service comments, case notes and other administrative narratives remain
    # in the structured extraction; they are intentionally not rendered here.
