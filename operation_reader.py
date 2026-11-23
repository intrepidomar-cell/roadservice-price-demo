"""Fallback for itemized-by-operation PDF estimates (no conventional parts grid).

Keeps the original Laboratory 10 result intact when that reader finds tables.
Only a cautious supplemental reader for PDFs with numbered operations, labor
amounts and 'Operation Total' rows. Does not infer labor hours or hourly rates.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pdfplumber

# Matches numbered repair operations, not any specific vendor name.
_OPERATION = re.compile(r"^\s*(\d{1,3})\s+(.+?)\s+\[([\w-]+)\](?:\s+[A-Z])?\s*$")
_MONEY = re.compile(r"\$\s*([0-9][0-9,]*\.\d{2})")
_CHARGE = re.compile(r"^Additional\s+Charges\s*:\s*(.*)$", re.I)
_LABOR = re.compile(r"^Labor\s*:\s*(.*)$", re.I)
_OP_TOTAL = re.compile(r"^Operation\s+Total\s*:\s*(.*)$", re.I)


def _amounts(text: str) -> list[Decimal]:
    return [Decimal(s.replace(',', '')) for s in _MONEY.findall(text)]


def _display(amount: Decimal) -> str:
    return f"${amount:,.2f}"


def _record(kind: str, description: str, amount: Decimal, unit_price: str = "", quantity: str = "") -> dict:
    return {
        "Type": kind, "Description": description, "Hrs/Qty": quantity,
        "UOM": "", "Rate/Price": unit_price, "Ext Amt": _display(amount),
    }


def read_operation_tables(pdf_path: str | Path, existing_result: dict) -> dict:
    """Return the Lab10 result, augmented only when Lab10 found no tables.

    Recognizes costs printed under numbered operations; summary remains the
    authoritative printed economic summary. This function is read-only.
    """
    if existing_result.get('tablas'):
        return existing_result

    operations = []
    extracted_pages = []
    with pdfplumber.open(str(pdf_path)) as document:
        for page_number, page in enumerate(document.pages, 1):
            # Avoid OCR; these PDFs already include selectable digital text.
            page_lines = (page.extract_text(layout=False) or '').splitlines()
            extracted_pages.append(page_lines)
            for line in page_lines:
                line = line.strip()
                heading = _OPERATION.match(line)
                if heading:
                    idx, title, code = heading.groups()
                    operations.append({"number": int(idx), "title": title.strip(),
                                       "code": code, "page": page_number,
                                       "rows": [], "total": None})
                    continue
                if not operations:
                    continue
                current = operations[-1]
                op_total = _OP_TOTAL.match(line)
                if op_total:
                    amounts = _amounts(op_total.group(1))
                    if amounts:
                        current['total'] = amounts[-1]
                    continue
                labor = _LABOR.match(line)
                if labor:
                    amounts = _amounts(labor.group(1))
                    if amounts:
                        current['rows'].append(_record(
                            'L', 'LABOR — ' + current['title'], amounts[-1]))
                    continue
                charge = _CHARGE.match(line)
                if charge:
                    text = charge.group(1)
                    amounts = _amounts(text)
                    if amounts:
                        # Description precedes the first monetary amount, and
                        # may include 'n/a'. No printed quantity assumed.
                        description = _MONEY.split(text, maxsplit=1)[0]
                        description = re.sub(r'\s+(?:n/?a|\d+(?:\.\d+)?)\s*$', '', description, flags=re.I)
                        current['rows'].append(_record('M', description.strip(), amounts[-1]))

    if not operations or not any(op['total'] is not None for op in operations):
        return existing_result

    tables = []
    subtables = []
    for op in operations:
        data = op['rows']
        # Retain operations even when labor is 0; useful for tracing estimate.
        df = pd.DataFrame(data, columns=['Type','Description','Hrs/Qty','UOM','Rate/Price','Ext Amt'])
        tables.append({
            'id':f"operation-{op['number']}", 'titulo':f"{op['number']}. {op['title']}",
            'codigo':op['code'], 'inicio':op['page'], 'fin':op['page'],
            'datos':df, 'encabezados_pdf':[], 'columnas_inferidas':[],
        })
        if op['total'] is not None:
            subtables.append({
                'id':f"operation-total-{op['number']}",
                'titulo':f"Operation {op['number']} subtotal", 'tipo':'OPERATION_TOTAL',
                'datos':pd.DataFrame([{'Concepto':'Operation Total','Importe':_display(op['total'])}])
            })

    # Include invoice-level charges (not previously in job rows) as a separate
    # amount-only table. Do not duplicate HOOKUP already charged to Operation 2.
    summary = (existing_result.get('resumen_final') or {}).get('datos')
    summary_rows = []
    if isinstance(summary, pd.DataFrame):
        all_descriptions = ' '.join(str(row['Description']).upper() for t in tables
                                    for _,row in t['datos'].iterrows())
        for _,r in summary.iterrows():
            label = str(r.get('Concepto', '')).strip()
            amounts = _amounts(str(r.get('Importe', '')))
            if not amounts:
                continue
            if re.search(r'SHOP\s*SUPPLIES', label, re.I):
                if 'SHOP SUPPLIES' not in all_descriptions:
                    summary_rows.append(_record('M', 'SHOP SUPPLIES', amounts[-1]))
    if not summary_rows:
        for page_lines in extracted_pages:
            for text in page_lines:
                m = re.match(r'^\s*Shop\s+Supplies\s+(\$[\d,]+\.\d{2})\s*$', text, re.I)
                if m:
                    values = _amounts(m.group(1))
                    if values:
                        summary_rows.append(_record('M', 'SHOP SUPPLIES', values[-1]))
                    break
            if summary_rows:
                break
    if summary_rows:
        tables.append({
            'id':'summary-charges', 'titulo':'Additional summary charges',
            'codigo':'', 'inicio':len(operations) and operations[-1]['page'],
            'fin':len(operations) and operations[-1]['page'],
            'datos':pd.DataFrame(summary_rows), 'encabezados_pdf':[], 'columnas_inferidas':[],
        })

    # Reconcile printed operation totals against their printed detail amounts.
    review_warnings = []
    for op in operations:
        if op['total'] is None:
            continue
        row_total = sum((_amounts(r['Ext Amt'])[-1] for r in op['rows']
                         if _amounts(r['Ext Amt'])), Decimal('0.00'))
        if abs(row_total - op['total']) > Decimal('0.02'):
            review_warnings.append(f"Operation {op['number']}: detail sum differs from printed operation total.")

    output = dict(existing_result)
    if not output.get('resumen_final'):
        summary_detected = []
        for page_idx, page_lines in enumerate(extracted_pages, start=1):
            for text in page_lines:
                m = re.match(r'^\s*(Labor|HOOKUP|Shop Supplies|Taxes|Total)\s+(\$[\d,]+\.\d{2})\s*$', text, re.I)
                if m:
                    summary_detected.append({'pagina':page_idx, 'Concepto':m.group(1), 'Importe':m.group(2)})
        if any(str(row['Concepto']).lower()=='total' for row in summary_detected):
            output['resumen_final'] = {'pagina':summary_detected[-1]['pagina'],
                                      'titulo':'', 'datos':pd.DataFrame(summary_detected),
                                      'cierre':'Total', 'origen':'RESUMEN_IMPRESO'}
    output['tablas'] = tables
    output['subtablas'] = [*(existing_result.get('subtablas') or []), *subtables]
    output['parser'] = f"{existing_result.get('parser','L10')} + numbered-operations fallback"
    output['n_partidas'] = sum(len(t['datos']) for t in tables)
    output['avisos'] = [*(existing_result.get('avisos') or []),
        'Numbered operations recognized by supplementary parser; Labor rows show amounts, NOT hourly rates.',
        'Shop Supplies comes from the printed final summary; verify source before comparing.',
        *review_warnings]
    output['operation_fallback_used'] = True
    return output


def leer_invoice(pdf_file: str | Path) -> dict:
    """Drop-in interface for the existing app: original Lab10 + fallback.

    Replace only `from invoice_reader_l10 import leer_invoice` in app.py with
    `from operation_reader import leer_invoice`.
    """
    from invoice_reader_l10 import leer_invoice as original_reader
    base_result = original_reader(str(pdf_file))
    return read_operation_tables(pdf_file, base_result)
