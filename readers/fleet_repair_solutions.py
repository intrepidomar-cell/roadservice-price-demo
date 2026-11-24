"""Direct Fleet Repair Solutions layout, including operations split across pages."""
import hashlib
import re
from decimal import Decimal
from core.models import Invoice, LineItem, Operation
from core.pdf_utils import lines, decimal
from core.validation import check_delta, TOL

HEADER = 'Item Description Quantity Rate Amount'
MONEY = r'-?\$[\d,]+\.\d{2}'


def read(pdf, path=None):
    doc = Invoice('fleet_repair_solutions_v1', 'Fleet Repair Solutions', 'estimate', pages=len(pdf.pages))
    if path is not None: doc.metadata['Source SHA-256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    doc.metadata['Billing format'] = 'Direct'
    op = None; pending = None; note = None; detail = False; summary = False; ended = False
    def flush():
        nonlocal pending
        if pending is None: return
        item = pending
        if item.category == 'Labor':
            m = re.search(r'/\s*(\d{3}-\d{3}-\d{3})\s*/', item.description)
            if m: item.code = m[1]
        item.printed['Description'] = (item.printed.get('Description','') + ' ' + item.description).strip() if item.printed.get('Description','').endswith('Correction:') else item.description
        doc.items.append(item); pending = None
    def close_operation():
        nonlocal op, note
        flush()
        if op is not None:
            if 'cause' in op.notes and ' Type:' in op.notes['cause']:
                cause, repair_type = op.notes['cause'].split(' Type:',1)
                op.notes['cause'] = cause.strip() + ' | Type: ' + repair_type.strip()
            op.title = op.notes.pop('concern', op.title)
            for item in doc.items:
                if item.operation == str(op.number): item.operation = f'{op.number}. {op.title}'
            op = None; note = None
    for pn, page in enumerate(pdf.pages, 1):
        ls = lines(page)
        if pn == 1:
            for j, l in enumerate(ls):
                if l.text.startswith('Fleet Repair Solutions -'):
                    branch = ' '.join(w['text'] for w in l.words if w['x0']<page.width*.56).split(' -',1)[-1].strip()
                    if j+1<len(ls):
                        nxt=ls[j+1].text
                        if not re.match(r'^(Date:|PO Box|\d)',nxt): branch = (branch+' '+nxt).strip()
                    doc.metadata['Shop name']=branch
                    match=re.search(r'\b(Estimate|Invoice)\s+([A-Z0-9-]+)$',l.text)
                    if match: doc.document_type=match[1].lower(); doc.metadata['Document number']=match[2]
                if l.text.startswith('Date:'): doc.metadata['Date']=l.text[5:].strip()
                if re.fullmatch(r'.+,\s*[A-Z]{2}\s+\d{5}(?:-\d{4})?',l.text) and l.top<150: doc.metadata['Shop city/state/ZIP']=l.text
                if l.text.startswith('Service Order Purchase Order Service Writer Authorizer') and j+1<len(ls):
                    for key, lo, hi in [('Service Order',0,.32),('Purchase Order',.32,.55),('Service Writer',.55,.77),('Authorizer',.77,1)]:
                        v=' '.join(w['text'] for w in ls[j+1].words if lo*page.width<=w['x0']<hi*page.width)
                        if v: doc.metadata[key]=v
        for l in ls:
            t=l.text
            if t==HEADER: detail=True; continue
            if not detail or ended: continue
            if t.startswith('*: Core charges') or t.startswith('We appreciate your business'):
                close_operation(); ended=True; continue
            # Economic summary begins with vehicle data, not an operation subtotal.
            if t.startswith('Unit:'):
                close_operation(); summary=True
                left=' '.join(w['text'] for w in l.words if w['x0']<page.width*.64)
                for key,pattern in [('Unit',r'Unit:\s*(\S+)'),('VIN',r'VIN:\s*(\S+)'),('Serial Number',r'Serial Number:\s*(\S+)')]:
                    m=re.search(pattern,left)
                    if m: doc.metadata[key]=m[1]
            if summary:
                left=' '.join(w['text'] for w in l.words if w['x0']<page.width*.64)
                right=' '.join(w['text'] for w in l.words if w['x0']>=page.width*.64)
                sm=re.fullmatch(r'(Labor|Parts|Subtotal|Total|(?:PA )?Exempt.*|Tax(?:es)?|Shop Supplies)\s+('+MONEY+r')',right,re.I)
                if sm:
                    key=sm[1]; doc.summary[key]=decimal(sm[2]); doc.summary_pages[key]=pn
                if left.startswith(('License Plate:','Chassis:')): doc.metadata[left.split(':',1)[0]]=left.split(':',1)[1].strip()
                elif re.match(r'^20\d\d',left): doc.metadata['Vehicle']=left
                continue
            if t.startswith('Concern:'):
                close_operation(); op=Operation(len(doc.operations)+1,'Concern',page=pn,end_page=pn,notes={'concern':t[8:].strip()}); doc.operations.append(op); note='concern'; continue
            if t.startswith('Cause:') and op:
                flush(); op.notes['cause']=t[6:].strip(); note='cause'; continue
            # Column coordinates are stable across the observed direct format.
            cols=[' '.join(w['text'] for w in l.words if lo*page.width<=w['x0']<hi*page.width) for lo,hi in [(0,.15),(.15,.68),(.68,.766),(.766,.85),(.85,1)]]
            kind, desc, q, rate, amt=cols
            m=re.fullmatch(r'Subtotal\s+('+MONEY+r')',t)
            if m and op:
                flush(); op.total=decimal(m[1]); op.end_page=pn; close_operation(); continue
            if kind in ('Labor','Parts'):
                flush(); note=None
                if op is None: doc.warnings.append('Detail row without an operation; review.')
                qty,price,amount=map(decimal,(q,rate,amt))
                # Labor labels are printed separately from the correction narrative.
                # Keep whether correction was recommended or stated.
                correction_label = re.match(r'^(?:Recommended )?Correction:',desc)
                desc=re.sub(r'^(?:Recommended )?Correction:\s*','',desc)
                consistent=None if None in (qty,price,amount) else abs(qty*price-amount)<=TOL
                pending=LineItem(desc,pn,kind,quantity=qty,unit='HR' if kind=='Labor' else '',unit_price=price,amount=amount,price_source='printed Rate' if price is not None else 'missing',amount_consistent=consistent,operation=str(op.number) if op else '',printed={'Item':kind,'Description':desc,'Quantity':qty,'Rate':price,'Amount':amount})
                if correction_label: pending.printed['Description']=correction_label[0]
                if op: op.end_page=pn
                if consistent is not True: doc.warnings.append('Incomplete or inconsistent line arithmetic; review.')
                continue
            if re.fullmatch(r'Shop Supplies\s+'+MONEY,t,re.I):
                close_operation(); amount=decimal(t.split()[-1]); doc.items.append(LineItem('SHOP SUPPLIES',pn,'Misc',amount=amount,price_source='printed Amount',comparison_eligible=amount>0,printed={'Item':'','Description':'Shop Supplies','Quantity':None,'Rate':None,'Amount':amount})); continue
            if pending is not None and kind=='' and desc and not (q or rate or amt):
                pending.description=' '.join(filter(None,[pending.description,desc])); continue
            if op is not None and note and not pending:
                op.notes[note]+=' '+t; continue
            if t.strip(): doc.warnings.append(f'Unrecognized detail text on page {pn}; review.')
    close_operation()
    def amounts(items):
        return sum((i.amount for i in items),Decimal(0)) if all(i.amount is not None for i in items) else None
    for operation in doc.operations:
        check_delta(doc,f'Operation {operation.number} subtotal',operation.total,amounts([i for i in doc.items if i.operation==f'{operation.number}. {operation.title}']))
    for cat in ('Labor','Parts'):
        check_delta(doc,f'Printed {cat} vs rows',doc.summary.get(cat),amounts([i for i in doc.items if i.category==cat]))
    check_delta(doc,'Printed subtotal vs rows',doc.summary.get('Subtotal'),amounts(doc.items) if doc.items else None)
    subtotal=doc.summary.get('Subtotal'); tax=[v for k,v in doc.summary.items() if 'exempt' in k.lower() or k.lower() in ('tax','taxes')]
    check_delta(doc,'Printed total vs subtotal and tax',doc.summary.get('Total'),subtotal+sum(tax,Decimal(0)) if subtotal is not None else None)
    if doc.warnings or any(v is None or abs(v)>TOL for v in doc.checks.values()):
        for i in doc.items: i.comparison_eligible=False
    # Core lines are kept signed and included only as actually printed; no additional core charge inferred.
    return doc
