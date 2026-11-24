"""Ocala Freightliner: independent sold/estimated/rejected jobs and printed totals."""
import hashlib
import re
from decimal import Decimal
from core.models import Invoice, LineItem, Operation
from core.pdf_utils import lines, decimal
from core.validation import check_delta, TOL

MONEY=r'-?\$[\d,]+\.\d{2}'

def read(pdf,path=None):
    text='\n'.join(p.extract_text() or '' for p in pdf.pages)
    final=bool(re.search(r'SERVICE INVOICE:\s*\S+',text)) and 'NOT AN INVOICE' not in text
    doc=Invoice('ocala_v1','Ocala Freightliner','invoice' if final else 'estimate',pages=len(pdf.pages))
    if path:doc.metadata['Source SHA-256']=hashlib.sha256(path.read_bytes()).hexdigest()
    doc.metadata['Shop city/state/ZIP']='Ocala, FL 34482'
    m=re.search(r'SERVICE (ORDER|INVOICE):\s*(\S+)',text)
    if m:doc.metadata['Document number']=m[2];doc.metadata['Service Order']=m[2].split(':')[0]
    doc.metadata['Document status']='Final invoice' if final else 'NOT AN INVOICE / service order'
    m=re.search(r'Estimate#\s*(\d+)',text)
    if m:doc.metadata['Estimate version']=m[1]
    state='';op=None;note=None; in_table=False; summary=False
    totals={}; group_totals={}; status_by_key={}
    def cropwords(l,lo,hi):return ' '.join(w['text'] for w in l.words if lo<=w['x0']<hi)
    for pn,p in enumerate(pdf.pages,1):
        clean=p.filter(lambda o:o.get('object_type')!='char' or o.get('size',0)<20)
        ls=lines(clean)
        if pn==1:
            for n,l in enumerate(ls[:-1]):
                if l.text.startswith('DATE ARRIVED DATE INVOICE'):
                    for name,lo,hi in [('Date arrived',0,125),('Date invoice',125,215),('Sales type',215,320),('Advisor',320,420),('Terms',420,500),('Customer PO',500,612)]:
                        v=cropwords(ls[n+1],lo,hi)
                        if v:doc.metadata[name]=v
                if l.text.startswith('YEAR MAKE MODEL VIN'):
                    for name,lo,hi in [('Year',0,70),('Make',70,130),('Model',130,190),('VIN',190,290),('Unit',290,365),('Engine Hours',365,430),('In Service',430,475),('Component Serial #',475,545),('Odometer',545,612)]:
                        v=cropwords(ls[n+1],lo,hi)
                        if v:doc.metadata[name]=v
        tables=[t for t in p.find_tables() if t.bbox[0]<100 and t.extract() and (t.extract()[0] or [''])[0]=='QTY']
        # Identify table intervals from geometry, then read text in printed columns;
        # merged PDF cells must not move a unit price into the description.
        regions={}
        for t in tables:
            hdr=t.extract()[0];regions[t.bbox[1]]=(t.bbox[3],len(hdr)==5)
        for l in ls:
            t=l.text
            if 'ESTIMATED BILLED' in t:summary=True;op=None;note=None;continue
            if summary:
                right=cropwords(l,409,612)
                m=re.match(r'^(LABOR|PARTS|MISC CHG|SUBLET|PREPAY|SUBTOTAL|SHOP SUPPLIES|TAX|TOTAL w/ EST|TOTAL)\s+',right)
                if m:
                    label=m[1];vals=[w for w in l.words if w['x0']>=480 and re.fullmatch(MONEY,w['text'])]
                    for w in vals:
                        k=('Estimated — ' if w['x0']<545 else 'Billed — ') + label if label in ('LABOR','PARTS','MISC CHG','SUBLET','PREPAY','SUBTOTAL') else label
                        doc.summary[k]=decimal(w['text']);doc.summary_pages[k]=pn
                if 'Paid via' in t:doc.metadata['Payment section']='Present (see original PDF)'
                continue
            m=re.fullmatch(r'(Sold|Estimate|Rejected) Operations(?: \(Cont\.\))?',t)
            if m:
                if m[1]!=state:op=None;note=None
                state=m[1];continue
            m=re.match(r'JOB #(\d+)\s+(\S+)\s+(.*)',t)
            if m:
                title=f'[{state}] {m[3]}'
                op=Operation(int(m[1]),title,code=m[2],page=pn,end_page=pn,notes={'status':state});doc.operations.append(op);note=None
                status_by_key[f'{op.number}. {op.title}']=state;continue
            if 'Prepay:' in t and state:
                vals=re.findall(MONEY,t)
                if 'Operations Totals' in t:
                    if vals:
                        group_totals[state]=decimal(vals[-1]);doc.notes[f'{state} Operations Totals']=t
                elif op:
                    if len(vals)==6:
                        op.total=decimal(vals[-1]);op.notes['economic breakdown']=' | '.join(f'{k}: {v}' for k,v in zip(['Prepay','Parts','Labor','Misc','Sublet'],vals[:5]))
                        totals[f'{op.number}. {op.title}']=[decimal(v) for v in vals[:5]]
                    op.end_page=pn;note=None
                continue
            region=next(((b,wide) for a,(b,wide) in regions.items() if a<=l.top<=b),None)
            if region and op:
                if t.startswith('QTY '):note=None;continue
                if region[1]:q,code,desc,rate,amt=[cropwords(l,a,b) for a,b in [(22,54),(54,202),(202,445),(445,520),(520,612)]]
                else:q,desc=cropwords(l,22,54),cropwords(l,54,612);code=rate=amt=''
                if not(code or desc or q or rate or amt):continue
                qty,price,amount=map(decimal,(q,rate,amt))
                cat='Labor' if 'LABOR' in code or desc=='TRUCK REPAIR LABOR GUIDE' else 'Misc' if 'SUPPLIES' in desc or '>>TAX<<' in desc else 'Parts' if qty is not None or code else 'Unclassified'
                key=f'{op.number}. {op.title}'
                # Availability notes in their own printed row are retained, not interpreted as a price.
                if not q and not code and not rate and not amt and 'AVAIL @' in desc:cat='Unclassified'
                i=LineItem(desc,pn,cat,code=code,quantity=qty,unit_price=price,amount=amount,price_source='printed Unit Price' if price is not None else 'missing',amount_consistent=None if None in (qty,price,amount) else abs(qty*price-amount)<=TOL,operation=key,printed={'Qty':qty,'Item':code,'Description':desc,'Unit Price':price,'Extd Price':amount})
                doc.items.append(i);op.end_page=pn;continue
            if op and not t.startswith(('Page ','SERVICE ORDER','SERVICE INVOICE','ALL PARTS ARE NEW')):
                m=re.match(r'^(COMPLAINT|CAUSE|CORRECTION)\b\s*(.*)',t)
                if m:note=m[1].lower();op.notes[note]=m[2];continue
                if note and t!='NOT AN INVOICE':op.notes[note]+=(' ' if op.notes[note] else '')+t
    for op in doc.operations:
        key=f'{op.number}. {op.title}';its=[i for i in doc.items if i.operation==key]
        op.warranty='>>WARRANTY<<' in op.notes.get('complaint','')
        if op.total is not None and key in totals:
            pre,parts,lab,misc,sub=totals[key];check_delta(doc,f'Job {op.number} printed components',op.total,parts+lab+misc+sub-pre)
        if its:
            check_delta(doc,f'Job {op.number} item total',op.total,sum(i.amount for i in its) if all(i.amount is not None for i in its) else None)
    for st,amount in group_totals.items():
        check_delta(doc,f'{st} operations total',amount,sum((o.total for o in doc.operations if status_by_key[f'{o.number}. {o.title}']==st and o.total is not None),Decimal(0)))
    for st,label in [('Sold','Billed'),('Estimate','Estimated')]:
        vals=[o.total for o in doc.operations if status_by_key[f'{o.number}. {o.title}']==st and o.total is not None]
        if vals:check_delta(doc,f'{st} jobs vs {label} subtotal',doc.summary.get(f'{label} — SUBTOTAL'),sum(vals,Decimal(0)))
    s=doc.summary;sub=s.get('Billed — SUBTOTAL');fees=s.get('SHOP SUPPLIES');tax=s.get('TAX')
    check_delta(doc,'Billed total',s.get('TOTAL'),sub+fees+tax if None not in (sub,fees,tax) else None)
    if 'TOTAL w/ EST' in s:check_delta(doc,'Total with estimate (excludes rejected)',s['TOTAL w/ EST'],s['TOTAL']+s['Estimated — SUBTOTAL'] if 'TOTAL' in s and 'Estimated — SUBTOTAL' in s else None)
    # Only actual final invoice fee may be compared, never rejected/estimated lines.
    if fees is not None:
        doc.items.append(LineItem('SHOP SUPPLIES',doc.summary_pages['SHOP SUPPLIES'],'Misc',amount=fees,price_source='printed Billed amount',comparison_eligible=final and fees>0 and all(v is not None and abs(v)<=TOL for v in doc.checks.values()) and not doc.warnings,printed={'Description':'SHOP SUPPLIES','Extd Price':fees}))
    return doc
