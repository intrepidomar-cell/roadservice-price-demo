"""B.J. Trailer & Truck Repair: printed labor and parts groups."""
import hashlib,re
from decimal import Decimal
from core.models import Invoice, LineItem, Operation
from core.pdf_utils import lines,decimal
from core.validation import check_delta,TOL

def read(pdf,path=None):
    d=Invoice('bj_trailer_v1',vendor='B.J. Trailer & Truck Repair',document_type='invoice',pages=len(pdf.pages))
    if path: d.metadata['Source SHA-256']=hashlib.sha256(path.read_bytes()).hexdigest()
    d.metadata['Vendor location']='Chicago, IL'
    group=0; pending=None; table=False
    def flush():
        nonlocal pending
        if pending is None: return
        desc,q,rate,amt,pn=pending; op=d.operations[-1]; name=desc.casefold()
        cat='Labor' if group==1 else 'Parts'; unit=''
        if 'service call' in name: cat='Misc'
        elif re.match(r'\d+(?:\.\d+)? miles\b',name): cat='Misc';unit='MI'
        elif name=='shop supply': cat='Misc'
        consistent=None if None in (q,rate,amt) else abs(q*rate-amt)<=TOL
        if consistent is False: d.warnings.append('Line arithmetic mismatch.')
        d.items.append(LineItem(desc,pn,cat,quantity=q,unit=unit,unit_price=rate,amount=amt,price_source='printed Rate/Price',amount_consistent=consistent,operation=f'{op.number}. {op.title}',printed={'Description':desc,'Hrs/Qty':q,'Rate/Price':rate,'Amount':amt}))
        pending=None
    def new_group(pn):
        nonlocal group
        group+=1; d.operations.append(Operation(group,'Labor' if group==1 else 'Parts',page=pn))
    for pn,p in enumerate(pdf.pages,1):
        ls=lines(p); footer=False
        for n,l in enumerate(ls):
            t=l.text
            if pn==1 and 'DATE INVOICE #' in t:
                for r in ls[n+1:n+4]:
                    m=re.search(r'(\d+/\d+/\d{4})\s+(\d+)$',r.text)
                    if m: d.metadata.update({'Invoice date':m[1],'Invoice #':m[2]});break
            if t.startswith('P.O. NO '): d.metadata['PO #']=t[8:].strip()
            if t.startswith('TERMS '): d.metadata['Terms']=t[6:]
            if t.startswith('UNIT # MAKE, YEAR') and n+1<len(ls):
                r=ls[n+1]; d.metadata['Unit number']=' '.join(w['text'] for w in r.words if w['x0']<220);d.metadata['Vehicle']=' '.join(w['text'] for w in r.words if 220<=w['x0']<520);d.metadata['Mechanic']=' '.join(w['text'] for w in r.words if w['x0']>=520)
            if t=='DESCRIPTION HRS/QTY RATE/PRICE AMOUNT': table=True;continue
            if t.startswith('Thank you for your business.'): flush();footer=True;table=False;continue
            if footer:
                if t.startswith('Total') or t.startswith('NOT RESPONSIBLE'):
                    amounts=[decimal(w['text']) for w in l.words if w['x0']>520 and w['text'].startswith('$')]
                    if amounts and amounts[-1] is not None: d.summary['Total']=amounts[-1];d.summary_pages['Total']=pn
                continue
            if not table: continue
            if t.startswith('Reference #'): d.metadata['Reference #']=t[11:].strip();continue
            cells=[' '.join(w['text'] for w in l.words if a<=w['x0']<b) for a,b in [(0,383),(383,445),(445,520),(520,612)]]
            desc,q,r,a=cells; amt=decimal(a)
            if desc.upper() in ('LABOR TOTAL','PARTS TOTAL'):
                flush()
                if not d.operations or d.operations[-1].total is not None: new_group(pn)
                op=d.operations[-1];op.total=amt;op.end_page=pn;op.notes['total label']=desc.title()
                d.summary[desc.title()]=amt;d.summary_pages[desc.title()]=pn
                check_delta(d,desc,amt,sum((i.amount for i in d.items if i.operation==f'{op.number}. {op.title}' and i.amount is not None),Decimal(0)))
                continue
            if desc.casefold()=='sales tax':
                flush();d.summary['Sales Tax']=amt;d.summary_pages['Sales Tax']=pn;d.metadata['Sales tax rate']=r;continue
            if amt is not None:
                flush()
                if not d.operations or d.operations[-1].total is not None: new_group(pn)
                pending=[desc,decimal(q),decimal(r),amt,pn]
            elif desc:
                if pending: pending[0]+=' '+desc
                else: d.notes['Complaint']=' '.join(filter(None,[d.notes.get('Complaint',''),desc]))
            elif any((q,r,a)): d.warnings.append('Unrecognized numeric detail row.')
    flush()
    check_delta(d,'Total vs detail plus tax',d.summary.get('Total'),sum((i.amount for i in d.items if i.amount is not None),Decimal(0))+d.summary.get('Sales Tax',Decimal(0)) if d.items else None)
    check_delta(d,'Total vs printed groups and tax',d.summary.get('Total'),sum((d.summary[k] for k in ('Labor Total','Parts Total','Sales Tax') if d.summary.get(k) is not None),Decimal(0)))
    if d.items and not d.warnings and all(v is not None and abs(v)<=TOL for v in d.checks.values()):
        # The printed unit is missing for parts and shop supplies. Do not infer quantity=1.
        for i in d.items:
            if i.description.casefold()=='shop supply' and i.quantity==1 and i.amount is not None and i.amount>0 and i.amount==i.unit_price: i.comparison_eligible=True
    d.warnings.append('Invoice is not proof of payment. Missing quantity remains blank. Tax percentage is not a unit price.')
    return d
