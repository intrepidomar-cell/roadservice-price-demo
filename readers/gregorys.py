"""Gregory's five-column service order layout; retain precision and subtotals."""
import hashlib
import re
from decimal import Decimal, ROUND_HALF_UP
from core.models import Invoice, LineItem, Operation
from core.pdf_utils import lines, decimal
from core.validation import check_delta, TOL

HEADER = 'Item Description Quantity Rate Amount'
MONEY = r'-?\$[\d,]+\.\d+'

def read(pdf, path=None):
    doc = Invoice('gregorys_v1', "Gregory's Trailer and Truck Service", 'unknown', pages=len(pdf.pages))
    if path: doc.metadata['Source SHA-256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    op=None; pending=None; active=False; summary=False; tax_label=''; ended=False
    def flush():
        nonlocal pending
        if pending is None: return
        i=pending
        i.printed['Description']=i.description
        if i.category=='Parts':
            m=re.search(r'\s-\s([A-Z0-9][A-Z0-9-]+)$',i.description)
            if m and re.search(r'\d',m[1]): i.code_candidates=[m[1]]
        doc.items.append(i); pending=None
    for pn,p in enumerate(pdf.pages,1):
        for l in lines(p):
            t=l.text
            if pn==1 and not active:
                m=re.search(r'\b(Estimate|Invoice)\s+(\S+)$',t)
                if m: doc.document_type=m[1].lower();doc.metadata['Document number']=m[2]
                if t.startswith('Date:'): doc.metadata['Date']=t[5:].strip()
                if 'Greer, SC' in t: doc.metadata['Remit city/state/ZIP']='Greer, SC 29650'
                if 'NOT AN INVOICE' in t: doc.document_type='estimate'
            if t==HEADER: active=True;continue
            if not active or ended or t.startswith('Page:'): continue
            if t.startswith('*: Core charges'): flush();ended=True;continue
            if t.startswith('Unit:'):
                flush();summary=True
                for key,pat in [('Unit',r'Unit:\s*(\S+)'),('VIN',r'VIN:\s*(\S+)')]:
                    m=re.search(pat,t)
                    if m: doc.metadata[key]=m[1]
            if summary:
                left=' '.join(w['text'] for w in l.words if w['x0']<p.width*.55)
                right=' '.join(w['text'] for w in l.words if w['x0']>=p.width*.55)
                if left.startswith('License Plate:'): doc.metadata['License Plate']=left.split(':',1)[1].strip()
                elif re.match(r'^20\d\d',left):doc.metadata['Vehicle']=left
                m=re.fullmatch(r'(Labor|Parts|Shop Supplies|Subtotal|Total)\s+('+MONEY+r')',right,re.I)
                if m:doc.summary[m[1]]=decimal(m[2]);doc.summary_pages[m[1]]=pn
                elif right.startswith('SC STATE & COUNTY'):
                    tax_label='Tax — SC STATE & COUNTY'
                    m=re.search(r'\$[\d,]+\.\d{2}$',right)
                    if m:doc.summary[tax_label]=decimal(m[0]);doc.summary_pages[tax_label]=pn;tax_label=''
                elif tax_label and re.fullmatch(MONEY,right):doc.summary[tax_label]=decimal(right);doc.summary_pages[tax_label]=pn;tax_label=''
                continue
            cols=[' '.join(w['text'] for w in l.words if lo*p.width<=w['x0']<hi*p.width) for lo,hi in [(0,.23),(.23,.50),(.50,.65),(.65,.82),(.82,1)]]
            kind,desc,q,rate,amt=cols
            m=re.fullmatch(r'Subtotal\s+('+MONEY+r')',t)
            if m:
                flush()
                if op:op.total=decimal(m[1]);op.end_page=pn;op=None
                else:doc.warnings.append('Subtotal without group.')
                continue
            if kind in ('Labor','Parts') or (not kind and desc.casefold()=='shop supplies'):
                flush()
                cat=kind or 'Misc'
                if cat!='Misc' and op is None:
                    op=Operation(len(doc.operations)+1,'Repair group',page=pn,end_page=pn);doc.operations.append(op)
                qty,price,amount=map(decimal,(q,rate,amt))
                consistent=None if None in (qty,price,amount) else (qty*price).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)==amount
                pending=LineItem(desc,pn,cat,quantity=qty,unit='HR' if cat=='Labor' else '',unit_price=price,amount=amount,price_source='printed Rate' if price is not None else 'missing',amount_consistent=consistent,operation=f'{op.number}. {op.title}' if op and cat!='Misc' else '',printed={'Item':kind,'Description':desc,'Quantity':qty,'Rate':price,'Amount':amount})
                if op:op.end_page=pn
                continue
            if pending and not kind and desc and not(q or rate or amt):
                pending.description+=('' if pending.description.endswith('-') and not pending.description.endswith(' -') else ' ')+desc
            elif t:doc.warnings.append(f'Unrecognized detail row on page {pn}.')
    flush()
    def total(items):return sum((i.amount for i in items),Decimal(0)) if all(i.amount is not None for i in items) else None
    for op in doc.operations:check_delta(doc,f'Group {op.number} subtotal',op.total,total([i for i in doc.items if i.operation==f'{op.number}. {op.title}']))
    for cat in ('Labor','Parts'):check_delta(doc,cat,doc.summary.get(cat),total([i for i in doc.items if i.category==cat]))
    check_delta(doc,'Subtotal vs detail',doc.summary.get('Subtotal'),total(doc.items))
    sub=doc.summary.get('Subtotal');tax=doc.summary.get('Tax — SC STATE & COUNTY')
    check_delta(doc,'Total vs subtotal and tax',doc.summary.get('Total'),sub+tax if None not in (sub,tax) else None)
    return doc
