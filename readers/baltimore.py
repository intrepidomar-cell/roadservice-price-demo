"""Baltimore Freightliner Service Order; repeated job header on continuation pages."""
import re, hashlib
from decimal import Decimal
from core.models import Invoice, Operation, LineItem
from core.pdf_utils import lines, decimal, field
from core.validation import check_delta,TOL


def read(pdf,path=None):
    d=Invoice('baltimore_v1','Baltimore Freightliner','service_order',pages=len(pdf.pages))
    if path: d.metadata['Source SHA-256']=hashlib.sha256(path.read_bytes()).hexdigest()
    d.metadata['Shop city/state/ZIP']='Baltimore, MD 21230'
    first=pdf.pages[0].extract_text() or ''
    d.metadata['Service Order']=field(first,r'RO:\s*(\S+)')
    warranty='FREIGHTLINER WARRANTY SERVICE' in first
    if warranty: d.metadata['Bill-to status']='Freightliner Warranty Service'
    d.metadata['Document status']='Service Order — invoice date not established'
    op=None; active=False; note=None; pending=None; footer=False; state='Sold'
    def cells(l,bounds):return [' '.join(w['text'] for w in l.words if a<=w['x0']<b) for a,b in zip(bounds,bounds[1:])]
    def flush():
        nonlocal pending
        if pending is None:return
        (q,code,desc,p,a),pn,owner=pending
        qty,price,amt=map(decimal,(q,p,a))
        cat='Parts' if re.match(r'\d{3}[A-Z]/',code) else 'Labor' if code in ('BDYDEFAULT','REP-CUSTOM') else 'Misc' if code=='SSTORA' else 'Unclassified'
        d.items.append(LineItem(desc,pn,cat,code=code,quantity=qty,unit_price=price,amount=amt,price_source='printed Price' if price is not None else 'missing',amount_consistent=None if None in (qty,price,amt) else abs(qty*price-amt)<=TOL,operation=f'{owner.number}. {owner.title}',printed=dict(zip(('Qty','Item','Description','Price','Extended'),(qty,code,desc,price,amt)))))
        pending=None
    for pn,p in enumerate(pdf.pages,1):
        ls=lines(p); footer=False; active=False; note=None
        for n,l in enumerate(ls):
            t=l.text
            if pn==1:
                if t.startswith('Date In Date In Service') and n+1<len(ls):
                    for k,v in zip(('Date In','Date In Service','Mileage','Date Out','Terms','Writer','Reviewer','Invoice Date','P.O. Number'),cells(ls[n+1],[0,80,150,215,285,350,400,455,530,580])):
                        if v:d.metadata[k]=v
                for prefix,key in [('Unit#','Dealer Unit #'),('VIN','VIN'),('Fleet ID #','Fleet ID #')]:
                    if t.startswith(prefix+' '):
                        val=' '.join(w['text'] for w in l.words if 60<=w['x0']<220)
                        if val:d.metadata[key]=val
                if t.startswith('Unit# ') and 'Make' in t:d.metadata['Make']=cells(l,[265,470])[0]
                if t.startswith('VIN ') and 'Model' in t:d.metadata['Model']=cells(l,[265,470])[0]
                if t.startswith('Fleet ID #') and 'Year' in t:d.metadata['Year']=cells(l,[265,470])[0]
                m=re.search(r'C\.R\. ENGLAND / (\S+)',t)
                if m:d.metadata['Owner unit reference']=m[1]
            if t.startswith('I hereby authorize'):flush();footer=True;active=False;note=None
            if footer:
                right=cells(l,[450,612])[0];m=re.fullmatch(r'(Misc\. Charges|Parts:|Labor:|Sublet:|Misc Supplies|Diagnostics:|Taxes:|Total:)\s+([\d,]+\.\d{2})',right)
                if m:d.summary[m[1].rstrip(':')]=decimal(m[2]);d.summary_pages[m[1].rstrip(':')]=pn
                continue
            m=re.fullmatch(r'(Sold|Estimate|Rejected) Operations(?: \(Cont\.\))?',t)
            if m:flush();state=m[1];active=False;note=None;continue
            m=re.match(r'Job#\s*(\d+)\s+(\S+)\s+(.*)',t,re.I)
            if m:
                flush();num=int(m[1]);title=f'[{state}] {m[3]}'
                if op and (op.number,op.title,op.code)==(num,title,m[2]):op.end_page=pn
                else:op=Operation(num,title,m[2],warranty=warranty,page=pn,end_page=pn,notes={'status':state});d.operations.append(op)
                note=None;active=False;continue
            if t=='Qty Item Description Price Extended':active=op is not None;note=None;continue
            if not op:continue
            if re.match(r'^\d+/\d+/\d+.*Page \d+ of \d+',t) or t=='Service Order':flush();active=False;note=None;continue
            m=re.match(r'^(Condition|Cause|Correction)\s*(.*)$',t)
            if m:
                flush();active=False;note={'Condition':'complaint','Cause':'cause','Correction':'correction'}[m[1]];op.notes[note]=m[2];continue
            if t.startswith('Claim Number#'):note=None;continue
            if active:
                c=cells(l,[20,62,175,450,535,612])
                if c[1] and c[2]:flush();pending=(c,pn,op);op.end_page=pn
                elif pending and c[2] and not any(c[:2]+c[3:]):pending[0][2]+=' '+c[2]
                elif t:d.warnings.append('Unrecognized Baltimore detail row; review.')
            elif note and t:op.notes[note]+=(' ' if op.notes[note] else '')+t
        flush()
    if d.metadata.get('Fleet ID #') and d.metadata.get('Owner unit reference') and d.metadata['Fleet ID #']!=d.metadata['Owner unit reference']:d.warnings.append('Printed Fleet ID and owner unit reference differ; verify unit mapping.')
    if d.summary:
        keys=('Misc. Charges','Parts','Labor','Sublet','Misc Supplies','Diagnostics','Taxes')
        check_delta(d,'Printed total',d.summary.get('Total'),sum((d.summary[k] for k in keys),Decimal(0)) if all(k in d.summary for k in keys) else None)
        check_delta(d,'Detail rows vs printed charges',sum((d.summary[k] for k in ('Misc. Charges','Parts','Labor','Sublet','Diagnostics')),Decimal(0)) if all(k in d.summary for k in ('Misc. Charges','Parts','Labor','Sublet','Diagnostics')) else None,sum((i.amount for i in d.items),Decimal(0)) if d.items and all(i.amount is not None for i in d.items) else None)
    else:d.warnings.append('No printed economic summary; unpriced warranty work is not zero.')
    if any(i.amount is None for i in d.items):d.warnings.append('Unpriced rows retained as missing.')
    return d
