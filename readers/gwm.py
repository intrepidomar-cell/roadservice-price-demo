"""GWM Commercial Auto Glass: digital invoice, five-column product/service table.
No assumption about the number of rows. Printed product label is the matching
identifier; its description may contain a different manufacturer reference.
"""
import hashlib
import re
from datetime import datetime
from decimal import Decimal
from core.models import Invoice, LineItem
from core.pdf_utils import lines, decimal
from core.validation import check_delta, TOL

HEADER = 'Product/Service Description Qty. Unit Price Total'
FIELDS = ('Product/Service', 'Description', 'Qty.', 'Unit Price', 'Total')
DATE = re.compile(r'^[A-Za-z]{3} \d{1,2}, \d{4}$')
SUMMARY = re.compile(r'^(Subtotal|Tax|Sales Tax|Discount|Total)\s+(\$[\d,]+\.\d{2})$', re.I)


def _date(value):
    try:
        return datetime.strptime(value, '%b %d, %Y').date().isoformat()
    except ValueError:
        return value


def _cells(line, bounds):
    description_start, quantity_start, price_split, total_split = bounds
    groups = [[] for _ in FIELDS]
    for w in line.words:
        # Numeric cells are right aligned: use their right edge so a large
        # dollar amount cannot drift into the preceding column.
        if w['x1'] >= quantity_start and re.fullmatch(r'[+$-]?[\d,]+(?:\.\d+)?\*?', w['text']):
            i = 2 + (w['x1'] >= price_split) + (w['x1'] >= total_split)
        else:
            i = int(w['x0'] >= description_start)
        groups[i].append(w['text'])
    return dict(zip(FIELDS, (' '.join(g) for g in groups)))


def _item(c, page, service_date, non_taxable):
    product, desc = c['Product/Service'], c['Description']
    qty, price = decimal(c['Qty.']), decimal(c['Unit Price'])
    amount = decimal(c['Total'].rstrip('*'))
    consistent = (abs(qty * price - amount) <= TOL
                  if None not in (qty, price, amount) else None)
    # Conservative exact product/service names, not an inferred hourly rate.
    category = ('Labor' if product.casefold() == 'sri remove & install' else
                'Parts' if re.fullmatch(r'CR England DW\d+[A-Z0-9-]*', product, re.I) else 'Unclassified')
    eligible = (category != 'Unclassified' and consistent is True and qty > 0 and price > 0 and amount > 0)
    return LineItem(desc or product, page, category, code=product,
                    quantity=qty, unit='EA' if category != 'Unclassified' else '',
                    unit_price=price, amount=amount, price_source='printed Unit Price' if price is not None else 'missing',
                    comparison_eligible=eligible, amount_consistent=consistent,
                    printed={**c, 'Qty.':qty, 'Unit Price':price, 'Total':amount,
                             'Tax status':'Non-taxable' if non_taxable and c['Total'].endswith('*') else '',
                             'Service date':service_date})


def read(pdf, path=None):
    doc = Invoice('gwm_commercial_auto_glass_v1', vendor='GWM Commercial Auto Glass', pages=len(pdf.pages))
    if path is not None:
        with open(path,'rb') as f: doc.metadata['Source SHA-256'] = hashlib.sha256(f.read()).hexdigest()
    all_lines = [lines(p) for p in pdf.pages]
    first = all_lines[0]
    header_total = None
    table_seen = False
    for l in first:
        if l.text.casefold() == HEADER.casefold(): break
        right = ' '.join(w['text'] for w in l.words if w['x0'] >= pdf.pages[0].width * .55)
        m = re.fullmatch(r'Invoice\s*#\s*(\d+)', right, re.I)
        if m:
            doc.document_type='invoice'; doc.metadata['Invoice number']=m[1]; continue
        for key in ('Issued','Due','Year','Unit #','Make','Model','VIN','PO #','Reference #','Total'):
            if right.startswith(key+' '):
                value=right[len(key):].strip()
                if key=='Total': header_total=decimal(value)
                else: doc.metadata[key]=_date(value) if key in ('Issued','Due') else value
        # Service heading contains vehicle and service location, not a branch ID.
        m = re.search(r'\s-\s\d+\s-\s(.+?,\s*[A-Z]{2})$', l.text)
        if m:
            doc.metadata['Service location']=m[1]
            doc.metadata['Service heading']=l.text
    non_taxable = any(re.match(r'^\*\s*Non-taxable',l.text,re.I) for ls in all_lines for l in ls)
    service_date = ''
    for pn, ls in enumerate(all_lines,1):
        idx = next((n for n,l in enumerate(ls) if l.text.casefold()==HEADER.casefold()), None)
        # Only parse explicitly recognized tables; never guess continuation layout.
        if idx is None:
            if pn>1: doc.warnings.append(f'Page {pn}: no repeated detail header; continuation not validated.')
            continue
        table_seen=True
        h=ls[idx].words
        # Description starts at its header; numeric columns use right edges.
        anchors={w['text']:w for w in h}
        q, p, t = (anchors[k]['x1'] for k in ('Qty.', 'Price', 'Total'))
        bounds=(anchors['Description']['x0']-3, q-12, (q+p)/2, (p+t)/2)
        pending=None
        def flush():
            nonlocal pending
            if pending is not None:
                doc.items.append(_item(pending,pn,service_date,non_taxable)); pending=None
        for l in ls[idx+1:]:
            sm=SUMMARY.fullmatch(l.text)
            if sm:
                flush(); key=sm[1].title(); value=decimal(sm[2])
                if key in doc.summary and doc.summary[key]!=value: doc.warnings.append(f'Conflicting printed {key}.')
                doc.summary[key]=value; doc.summary_pages[key]=pn
                if key=='Total': break
                continue
            if DATE.fullmatch(l.text):
                flush(); service_date=_date(l.text); continue
            if re.match(r'^\*\s*Non-taxable|^Thank you for your business',l.text,re.I):
                flush(); break
            c=_cells(l,bounds)
            if any(c[k] for k in FIELDS[2:]):
                flush(); pending=c
                if not c['Product/Service']: doc.warnings.append(f'Page {pn}: numeric row without product identifier.')
            elif pending is not None and (c['Product/Service'] or c['Description']):
                for k in FIELDS[:2]: pending[k]=' '.join(filter(None,(pending[k],c[k])))
            elif c['Product/Service'] or c['Description']:
                doc.warnings.append(f'Page {pn}: unassigned text before numeric row; review original.')
        flush()
    if non_taxable: doc.notes['Tax legend']='* Non-taxable'
    if not table_seen or not doc.items: doc.warnings.append('Recognized invoice but no supported line items found.')
    total=doc.summary.get('Total')
    check_delta(doc,'Header total vs printed final total',header_total,total)
    known=sum((i.amount for i in doc.items if i.amount is not None),Decimal(0))
    complete=bool(doc.items) and all(i.amount is not None for i in doc.items)
    subtotal=doc.summary.get('Subtotal')
    tax=doc.summary.get('Tax',doc.summary.get('Sales Tax',Decimal(0)))
    discount=doc.summary.get('Discount',Decimal(0))
    if subtotal is not None: check_delta(doc,'Printed subtotal vs line amounts',subtotal,known if complete else None)
    check_delta(doc,'Printed total vs line amounts and printed adjustments',total,known+tax-discount if complete else None)
    for item in doc.items:
        if item.amount_consistent is not True: doc.warnings.append(f'Page {item.page}: missing or inconsistent quantity, unit price or total; review.')
    # Unknown items remain visible; do not guess category. Any extraction or
    # reconciliation warning disables comparison until reviewed.
    if doc.document_type!='invoice' or doc.warnings or any(v is None or abs(v)>TOL for v in doc.checks.values()):
        for item in doc.items: item.comparison_eligible=False
    doc.warnings.append('Invoice is not proof of payment. EA is normalized per printed product/service quantity, not hours. Service location is not a verified vendor branch.')
    return doc
