"""A Mobile Maintenance digital invoices. Preserve truncated printed item codes."""
import hashlib
import re
from decimal import Decimal
from core.models import Invoice, LineItem
from core.pdf_utils import lines, decimal
from core.validation import check_delta, TOL

HEADER = 'Quantity Item Code Description Price Each Amount'
FEES = {'SERVICE CALL': 'Service Call', 'FUEL SURCHARGE FEE': 'Fuel Surcharge Fee',
        'SHOP SUPPLY FEE': 'Shop Supply Fee'}


def _row(line, width):
    groups = [[] for _ in range(5)]
    for w in line.words:
        x = w['x0'] * 612 / width
        i = 0 if x < 85 else 1 if x < 158 else 2 if x < 445 else 3 if x < 505 else 4
        groups[i].append(w['text'])
    return [' '.join(g) for g in groups]


def read(pdf, path=None):
    doc = Invoice('a_mobile_maintenance_v1', vendor='A Mobile Maintenance', document_type='invoice', pages=len(pdf.pages))
    if path is not None:
        doc.metadata['Source SHA-256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    pending = None
    table_seen = False
    table_total = None
    complaint = []
    def flush():
        nonlocal pending
        if pending is None: return
        cells, pn = pending
        q, code, desc, p, a = cells
        taxable = bool(re.fullmatch(r'[\d,]+\.\d+T',a,re.I))
        qty, price, amount = map(decimal, (q,p,a[:-1] if taxable else a))
        consistent = None if None in (qty,price,amount) else abs(qty*price-amount)<=TOL
        label = FEES.get(code.upper()) or FEES.get(desc.upper())
        if code.upper() == 'SERVICE CALL' and desc.lower().startswith('service location'):
            doc.metadata['Service location'] = re.sub(r'^Service Location\s*:\s*','',desc,flags=re.I)
        labor = desc.upper() in ('TOTAL DRIVE TIME','TOTAL REPAIR LABOR')
        category = 'Misc' if label else 'Labor' if labor else 'Unclassified'
        # H... is truncated; no invented full item code or hourly UOM.
        eligible = bool(label and consistent is True and qty == 1 and amount > 0)
        doc.items.append(LineItem(label or desc or code, pn, category, code=code if '...' not in code else '',
                                  quantity=qty, unit='EA' if label else '', unit_price=price, amount=amount,
                                  price_source='printed Price Each' if price is not None else 'missing',
                                  comparison_eligible=eligible, amount_consistent=consistent,
                                  printed=dict(zip(('Quantity','Item Code','Description','Price Each','Amount'),(qty,code,desc,price,amount))) | ({'Taxable marker':'T'} if taxable else {})))
        if consistent is not True: doc.warnings.append('Missing or inconsistent quantity, price or amount; review.')
        pending=None
    for pn,page in enumerate(pdf.pages,1):
        ls=lines(page)
        idx=next((i for i,l in enumerate(ls) if l.text.casefold()==HEADER.casefold()),None)
        if pn==1:
            for l in ls[:idx] if idx is not None else ls:
                right=' '.join(w['text'] for w in l.words if w['x0']>=page.width*0.56)
                for key in ('Invoice #','Date','P.O. Number','Carrier','Unit #','Reference #','License #','Mileage','DR#'):
                    if right.startswith(key+' '): doc.metadata[key]=right[len(key):].strip()
            doc.metadata['Vendor address']=' '.join(l.text for l in ls[:idx] if re.match(r'^(\d+ .* Rd\.,|Cartersville, GA \d+)$',l.text)) if idx is not None else ''
        # Footer is a distinct box; crop away promotional text on the left.
        footer=page.crop((page.width*.63,0,page.width,page.height)).extract_text() or ''
        for key in ('Subtotal','Total','Payments/Credits','Balance Due','Sales Tax','Tax','Discount'):
            m=re.search(r'^'+re.escape(key)+r'\s*\n?\s*(\$[\d,]+\.\d{2})\s*$',footer,re.M|re.I)
            if m:
                value=decimal(m[1])
                if key in doc.summary and doc.summary[key]!=value: doc.warnings.append('Conflicting '+key)
                doc.summary[key]=value; doc.summary_pages[key]=pn
        # Tax may be printed inside the table after the driver notes, not the footer.
        for l in ls:
            c=_row(l,page.width)
            if re.match(r'^Sales Tax(?:\s*-|\s|$)',c[2],re.I) and re.fullmatch(r'\d+(?:\.\d+)?%',c[3]) and decimal(c[4]) is not None:
                value=decimal(c[4])
                if 'Sales Tax' in doc.summary and doc.summary['Sales Tax']!=value: doc.warnings.append('Conflicting Sales Tax')
                doc.summary['Sales Tax']=value; doc.summary_pages['Sales Tax']=pn
                doc.metadata['Sales tax label']=c[2]; doc.metadata['Sales tax rate']=c[3]
        if idx is None:
            doc.warnings.append(f'Page {pn}: detail header absent; continuation not validated.')
            continue
        table_seen=True
        for l in ls[idx+1:]:
            c=_row(l,page.width)
            if re.match(r'^(BILL TO CUSTOMER|DRIVER.S (NAME|NUMBER)|Due to recent FRAUD)', l.text,re.I):
                flush(); break
            if c[4] and not any(c[:4]) and decimal(c[4]) is not None:
                flush(); table_total=decimal(c[4]); break
            if c[0] or c[1] or c[3] or c[4]:
                flush(); pending=(c,pn)
            elif c[2]:
                if pending: pending[0][2]+=' '+c[2]
                elif not doc.items: complaint.append(c[2])
                else: doc.warnings.append('Unassigned detail text; review.')
        flush()
    if complaint: doc.notes['Complaint']=' '.join(complaint)
    if not table_seen or not doc.items: doc.warnings.append('No recognized detail items.')
    known=sum((i.amount for i in doc.items if i.amount is not None),Decimal(0))
    complete=bool(doc.items) and all(i.amount is not None for i in doc.items)
    subtotal=doc.summary.get('Subtotal'); total=doc.summary.get('Total')
    check_delta(doc,'Printed subtotal vs rows',subtotal,known if complete else None)
    if table_total is not None: check_delta(doc,'Table total vs rows',table_total,known if complete else None)
    check_delta(doc,'Printed total vs subtotal and adjustments',total,subtotal+doc.summary.get('Tax',doc.summary.get('Sales Tax',Decimal(0)))-doc.summary.get('Discount',Decimal(0)) if subtotal is not None else None)
    if 'Payments/Credits' in doc.summary or 'Balance Due' in doc.summary:
        credits=doc.summary.get('Payments/Credits')
        check_delta(doc,'Balance due vs total less credits',doc.summary.get('Balance Due'),total-credits if total is not None and credits is not None else None)
    if doc.warnings or any(v is None or abs(v)>TOL for v in doc.checks.values()):
        for i in doc.items: i.comparison_eligible=False
    doc.warnings.append('Truncated item codes and unprinted units are preserved; drive time and repair labor remain separate. Service location is not a verified branch. Invoice is not proof of payment.')
    return doc
