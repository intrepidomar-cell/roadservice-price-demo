"""Amoretti's direct invoice: complaint groups and pre-charge economic summary."""
import hashlib
import re
from decimal import Decimal, ROUND_HALF_UP
from core.models import Invoice, LineItem, Operation
from core.pdf_utils import lines, decimal
from core.validation import check_delta

HEADER = 'Item Description Quantity Rate Amount'
MONEY = r'-?\$[\d,]+\.\d+'


def read(pdf, path=None):
    doc = Invoice('amoretti_v1', 'Amoretti Diesel Repair and Service', 'invoice', pages=len(pdf.pages))
    if path: doc.metadata['Source SHA-256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    active = summary = ended = False
    op = pending = note = tax_label = None
    def flush():
        nonlocal pending
        if pending is not None:
            label = pending.printed['Description']
            pending.printed['Description'] = (label + ' ' + pending.description).strip() if label else pending.description
            doc.items.append(pending)
            pending = None
    def close():
        nonlocal op, note
        flush()
        op = note = None
    def add_summary(key, value, pn):
        if key in doc.summary and doc.summary[key] != value:
            doc.warnings.append('Conflicting summary: '+key)
        doc.summary[key] = value
        doc.summary_pages[key] = pn
    for pn,p in enumerate(pdf.pages,1):
        ls=lines(p)
        for j,l in enumerate(ls):
            t=l.text
            if pn==1 and not active:
                m=re.search(r'\bInvoice:\s*(\S+)$',t)
                if m: doc.metadata['Document number']=m[1]
                if t.startswith('Date:'): doc.metadata['Date']=t[5:].strip()
                if re.fullmatch(r'.+,\s*[A-Z]{2}\s+\d{5}(?:-\d{4})?',t) and l.top<150:
                    doc.metadata['Shop city/state/ZIP']=t
                if t.startswith('Service Order Terms Due Date Authorizer Customer PO Unit #') and j+1<len(ls):
                    anchors=[('Service Order',0,.23),('Terms',.23,.40),('Due Date',.40,.55),('Authorizer',.55,.70),('Customer PO',.70,.85),('Unit #',.85,1)]
                    for key,lo,hi in anchors:
                        v=' '.join(w['text'] for w in ls[j+1].words if lo*p.width<=w['x0']<hi*p.width)
                        if v: doc.metadata[key]=v
            if t==HEADER: active=True;continue
            if not active or ended or t.startswith('Page:'): continue
            if t.startswith(('Any warranties on the parts','Customer Signature:','Printed Name:')):
                close();ended=True;continue
            if t.startswith('Unit:'):
                close();summary=True
                for key,pat in [('Unit',r'Unit:\s*(\S+)'),('VIN',r'VIN:\s*(\S+)')]:
                    m=re.search(pat,t)
                    if m: doc.metadata[key]=m[1]
            if summary:
                left=' '.join(w['text'] for w in l.words if w['x0']<p.width*.55)
                right=' '.join(w['text'] for w in l.words if w['x0']>=p.width*.55)
                if left.startswith('Chassis:'): doc.metadata['Chassis']=left.split(':',1)[1].strip()
                elif re.match(r'^20\d\d',left): doc.metadata['Vehicle']=left
                m=re.fullmatch(r'(Labor|Parts|Shop Supplies|Pre-Charge Subtotal|Call out fee|milage|mileage|Total|Payments & Credits|Balance Due)\s+('+MONEY+r')',right,re.I)
                if m: add_summary(m[1],decimal(m[2]),pn);continue
                if right=='State': tax_label='State';continue
                if tax_label and re.fullmatch(MONEY,right):
                    add_summary('Tax — '+tax_label,decimal(right),pn);tax_label=None;continue
                if re.fullmatch(r'\([\d.]+% of \$[\d,]+\.\d+\)',right):
                    doc.metadata['Tax basis']=right;continue
                if right: doc.warnings.append(f'Unrecognized economic summary on page {pn}; review.')
                continue
            if t.startswith('Complaint:'):
                close();title=t.split(':',1)[1].strip()
                op=Operation(len(doc.operations)+1,title,page=pn,end_page=pn,notes={'complaint':title});doc.operations.append(op);note='complaint';continue
            if t.startswith('Cause:') and op:
                flush();op.notes['cause']=t.split(':',1)[1].strip();note='cause';continue
            m=re.fullmatch(r'Subtotal\s+('+MONEY+r')',t)
            if m:
                flush()
                if op: op.total=decimal(m[1]);op.end_page=pn
                else: doc.warnings.append('Subtotal without operation.')
                close();continue
            kind,desc,q,rate,amt=[' '.join(w['text'] for w in l.words if lo*p.width<=w['x0']<hi*p.width) for lo,hi in [(0,.15),(.15,.68),(.68,.78),(.78,.86),(.86,1)]]
            if kind in ('Labor','Parts') or (not kind and desc and decimal(amt) is not None):
                flush();note=None
                cat=kind or 'Misc';qty,price,amount=map(decimal,(q,rate,amt))
                if kind and not op: doc.warnings.append('Detail row without complaint.')
                label=re.match(r'^(?:Recommended )?Correction:\s*',desc)
                desc=re.sub(r'^(?:Recommended )?Correction:\s*','',desc)
                consistent=None if None in (qty,price,amount) else (qty*price).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)==amount
                unit='HR' if kind=='Labor' else 'MI' if desc.casefold() in ('milage','mileage') else 'EA' if desc.casefold()=='call out fee' and qty==1 else ''
                pending=LineItem(desc,pn,cat,quantity=qty,unit=unit,unit_price=price,amount=amount,price_source='printed Rate' if price is not None else 'missing',amount_consistent=consistent,operation=f'{op.number}. {op.title}' if op and kind else '',printed={'Item':kind,'Description':label[0].strip() if label else '', 'Quantity':qty,'Rate':price,'Amount':amount})
                if op: op.end_page=pn
                if consistent is False: doc.warnings.append('Inconsistent line arithmetic; review.')
                continue
            if pending is not None and not kind and desc and not(q or rate or amt):
                pending.description=' '.join(filter(None,[pending.description,desc]));continue
            if op and note and pending is None:
                op.notes[note]+=' '+t;continue
            if t: doc.warnings.append(f'Unrecognized detail on page {pn}; review.')
    close()
    # Shop supplies is printed only in the summary. Keep provenance and do not
    # create another charge if an identical detail row already exists.
    if 'Shop Supplies' in doc.summary and not any(i.description.casefold()=='shop supplies' for i in doc.items):
        doc.items.append(LineItem('Shop Supplies',doc.summary_pages['Shop Supplies'],'Misc',amount=doc.summary['Shop Supplies'],price_source='printed summary Amount',printed={'Item':'','Description':'Shop Supplies','Quantity':None,'Rate':None,'Amount':doc.summary['Shop Supplies']}))
    def total(items):
        return sum((i.amount for i in items),Decimal(0)) if all(i.amount is not None for i in items) else None
    for o in doc.operations: check_delta(doc,f'Operation {o.number} subtotal',o.total,total([i for i in doc.items if i.operation==f'{o.number}. {o.title}']))
    for cat in ('Labor','Parts'):
        if cat in doc.summary: check_delta(doc,cat,doc.summary[cat],total([i for i in doc.items if i.category==cat]))
    for key in ('Shop Supplies','Call out fee','milage','mileage'):
        if key in doc.summary: check_delta(doc,key,doc.summary[key],total([i for i in doc.items if i.description.casefold()==key.casefold()]))
    base=total([i for i in doc.items if i.operation or i.description.casefold()=='shop supplies'])
    check_delta(doc,'Pre-Charge Subtotal vs rows',doc.summary.get('Pre-Charge Subtotal'),base)
    net=total(doc.items);tax=doc.summary.get('Tax — State')
    check_delta(doc,'Total vs detail and tax',doc.summary.get('Total'),net+tax if None not in (net,tax) else None)
    if 'Balance Due' in doc.summary:
        gross=doc.summary.get('Total');paid=doc.summary.get('Payments & Credits')
        check_delta(doc,'Balance Due',doc.summary['Balance Due'],gross-paid if None not in (gross,paid) else None)
    return doc
