"""Shared display of normalized fields; preserve original columns per reader."""
import pandas as pd
import streamlit as st
from decimal import Decimal


def _display(v):
    return format(v,'f') if isinstance(v,Decimal) else '' if v is None else v


def show_invoice_tables(doc):
    st.caption(f'Reader: {doc.reader} · {doc.document_type.title()} · {doc.pages} page(s)')
    if doc.reader=='unsupported':
        st.warning('Invoice format not recognized. No extraction or comparison performed.')
        return
    if doc.metadata:
        with st.expander('Document information',expanded=True):
            st.dataframe(pd.DataFrame([{'Field':k,'Value':v} for k,v in doc.metadata.items()]),hide_index=True,use_container_width=True)
    if doc.legacy_result is not None:
        from legacy.invoice_display import show_invoice_tables as show_legacy
        show_legacy(doc.legacy_result)
        return
    if doc.operations:
        for op in doc.operations:
            st.markdown(f'**{op.number}. {op.title}**' + (' — WARRANTY' if op.warranty else ''))
            st.caption(f'Pages {op.page}–{op.end_page}' + (f' · Operation code: {op.code}' if op.code else ''))
            if op.notes:
                with st.expander('Complaint / Cause / Correction'):
                    for name, value in op.notes.items():
                        st.markdown(f'**{name.title()}**')
                        st.text(value)
            items = [i for i in doc.items if i.operation == f'{op.number}. {op.title}']
            if items:
                rows = [{'Page':i.page, **{k:_display(v) for k,v in i.printed.items()}} for i in items]
                st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
            if op.parts_total is not None:
                st.write(f'Parts Total: ${op.parts_total:,.2f}')
            st.write(f'Operation Total: ${op.total:,.2f}' if op.total is not None else 'Operation Total: not printed')
        st.caption('Blank = not printed. Price and extended amount are preserved separately. Summary-only charges are displayed once below.')
    elif doc.items:
        st.markdown('**Line items — printed values**')
        rows=[{'Page':i.page,**{k:_display(v) for k,v in i.printed.items()},'Category (classified)':i.category,'Possible part codes (review)':', '.join(i.code_candidates)} for i in doc.items]
        st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True,height=min(650,38+35*len(rows)))
        st.caption('Blank = not printed; 0.00 = printed zero. Original monetary columns are kept separate.')
    else: st.warning('No detail rows detected.')
    if doc.summary:
        st.markdown('**Economic summary**')
        st.dataframe(pd.DataFrame([{'Concept':k,'Amount (USD)':f'${v:,.2f}'} for k,v in doc.summary.items()]),hide_index=True,use_container_width=True,height=min(420,38+35*len(doc.summary)))
    if doc.checks:
        st.markdown('**Reconciliation**')
        for k,v in doc.checks.items():
            if v is None: st.caption(f'{k}: unavailable')
            elif abs(v)<=Decimal('.02'): st.caption(f'{k}: matches ($0.00 within tolerance)')
            else: st.warning(f'{k}: ${v:,.2f} difference')
    if doc.notes:
        for k,v in doc.notes.items():
            with st.expander(k): st.text(v)
