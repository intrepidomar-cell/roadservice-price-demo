"""Normalize Lab 10 line rows for a cautious, explicit comparison workflow.

This is an adapter, not a parser replacement. No speculative part-number matching.
A special case handles the printed FleetPerform Type/P/L/M, Labor/Part, Hrs/Qty
and Rate/Price columns; the original tables remain untouched for review.
"""
import re
from decimal import Decimal, InvalidOperation
import pandas as pd


def _simplify(s):
    return re.sub(r'[^a-z0-9]', '', str(s).lower())


def _field(row, *, exact=(), contains=()):
    cols={str(k):_simplify(k) for k in row}
    for key,normal in cols.items():
        if normal in exact and pd.notna(row[key]) and str(row[key]).strip():
            return str(row[key]).strip()
    for key,normal in cols.items():
        if any(t in normal for t in contains) and pd.notna(row[key]) and str(row[key]).strip():
            return str(row[key]).strip()
    return ''


def money(v):
    s=str(v or '').strip().replace(',','').replace('$','')
    if not s or s in {'—','-'}:
        return None
    neg=s.startswith('(') and s.endswith(')')
    if neg:s=s[1:-1]
    try:
        n=Decimal(s)
        if not n.is_finite():return None
        return -n if neg else n
    except InvalidOperation:return None


def _category(type_code, section, desc):
    type_code=(type_code or '').strip().upper()
    if type_code in ('L','LABOR','LABOUR'):return 'Labor'
    if type_code in ('P','PART','PARTS'):return 'Parts'
    if type_code in ('M','MISC','MISCELLANEOUS'):return 'Misc'
    label=(section+' '+desc).lower()
    if re.search(r'\blabor\b|\blabour\b',label):return 'Labor'
    if re.search(r'\bparts?\b',label):return 'Parts'
    if re.search(r'\bmisc\b',label):return 'Misc'
    return 'Unclassified'


def extract_candidates(result):
    """Create a reviewable list; mark unknown/inconsistent values rather than invent them."""
    rows=[]
    sections=result.get('partidas_seccionadas_l09')
    section_by_row={}
    if isinstance(sections,pd.DataFrame) and not sections.empty:
        for _,r in sections.iterrows():
            try:section_by_row[(str(r.get('tabla_id')),int(r.get('fila')))]=str(r.get('Seccion',''))
            except (TypeError,ValueError):pass
    for tab in result.get('tablas',[]):
        df=tab.get('datos')
        if not isinstance(df,pd.DataFrame) or df.empty:continue
        table_id=str(tab.get('id',''))
        for pos,(_,series) in enumerate(df.iterrows(),start=1):
            row=series.to_dict()
            desc=_field(row,exact=('descripcion','description','itemdescription','concepto','laborperformedpartsusedforrepairs'),contains=('description','descripcion'))
            typecode=_field(row,exact=('type',))
            code=_field(row,exact=('laborpart','partnumber','partno','part','itemnumber','itemno','refnumber','sku','code'),contains=('partnumber','itemnumber','refnumber'))
            qty_str=_field(row,exact=('hrsqty','qty','quantity','hours','laborhours','salesqty','qtyhours','labortimepartsqty'))
            unit=_field(row,exact=('uom','um','unitofmeasure','unit','units','measure'))
            rate=_field(row,exact=('rateprice','unitprice','unitrate','rate','price'))
            amount=_field(row,exact=('amount','totalcost','total','totals','extendedprice','extprice','extdprice','extension','extamount','extamt'))
            q=money(qty_str); price=money(rate); total=money(amount)
            category=_category(typecode,section_by_row.get((table_id,pos),''),desc)
            adjusted=q; normalized_unit=unit.strip().upper()
            evidence=[]
            multiplier=1
            if category=='Labor' and ('hrsqty' in [_simplify(k) for k in row]):
                # On this template UOM sometimes contains '6 (Units)' while
                # Hrs/Qty holds 0.40 hours per unit and Ext Amt = 6*0.40*rate.
                mt=re.match(r'^\s*(\d+)\s*\(\s*units?\s*\)\s*$',unit,re.I)
                if mt and q is not None and price is not None and total is not None:
                    n=int(mt.group(1))
                    if n>1 and abs((q*n*price)-total)<=Decimal('.02'):
                        adjusted=q*n;multiplier=n
                        evidence.append('Hours normalized from printed UOM count × Hrs/Qty; verify source row')
                normalized_unit='HR'
                evidence.append('HR inferred from labor rate / Hrs/Qty headings')
            if category=='Misc' and not normalized_unit and q is not None:
                # Show but do not auto-match Misc; item_code stays blank.
                normalized_unit='EA'
                evidence.append('EA assumed for display; not an automatic match')
            price_source='printed' if price is not None else 'missing'
            if price is None and adjusted is not None and adjusted>0 and total is not None:
                price=total/adjusted
                price_source='derived_from_total_and_quantity'
            consistent=(adjusted is not None and price is not None and total is not None and
                abs((adjusted*price)-total)<=Decimal('.02'))
            if total is not None and not consistent:evidence.append('Line amount needs review: quantity × rate does not match printed amount')
            if not desc:desc=str(tab.get('titulo') or 'Partida sin descripción reconocida')
            rows.append(dict(row_id=f'{table_id}:{pos}',table=table_id,job=str(tab.get('titulo') or ''),
                description=desc,code=code.strip(),category=category,quantity=adjusted,printed_quantity=q,
                position_multiplier=multiplier,unit=normalized_unit,printed_unit=unit.strip(),
                unit_price=price,amount=total,price_source=price_source,amount_consistent=consistent,
                validation_notes='; '.join(evidence),raw_row=row))
    return rows
