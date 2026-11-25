"""Shared digital Towbook charge layout for explicitly recognized vendors."""
import hashlib
import re
from decimal import Decimal
from core.models import Invoice, LineItem
from core.pdf_utils import lines, decimal
from core.validation import check_delta, TOL

HEADER='Charge Description Quantity Price Line Total'
SUMMARY=re.compile(r'^(Subtotal|Grand Total|Amount Due:|Tax|Taxes|Sales Tax|[A-Za-z ]+ - [0-9.]+% Tax|Discount|Payments|Payments/Credits)\s+(\$[\d,]+\.\d{2})$',re.I)
PARTS={'filter (oil)','filter (fuel)','filter kit (fuel)','cabin air filter','washer fluid','oil (quart)','parts 1','transmission fluid','power steering fluid','stud','lug nut','grease'}
FEES={'shop fee','shop supplies','service call','inspection supplies','inspection (federal)'}
LABOR={'pm tractor','labor','service call labor'}
CODED={'filter (oil)','filter (fuel)','filter kit (fuel)','cabin air filter','parts 1'}


def read(pdf,path=None, *, vendor='Battleground Wrecker', reader='battleground_wrecker_v1'):
    doc=Invoice(reader,vendor=vendor,document_type='invoice',pages=len(pdf.pages))
    towing=vendor!='Battleground Wrecker' 
    if path is not None: doc.metadata['Source SHA-256']=hashlib.sha256(path.read_bytes()).hexdigest()
    pending=None; table_seen=False; summary_seen=False
    def flush():
        nonlocal pending
        if pending is None: return
        desc, details, qty, price, amount,pn=pending
        name=desc.casefold(); details=' '.join(details)
        category='Parts' if name in PARTS else 'Labor' if name in LABOR else 'Misc' if name in FEES else 'Unclassified'
        code=''
        if name in CODED and details:
            token=details.split()[0]
            if re.fullmatch(r'[A-Z0-9-]+',token,re.I) and any(ch.isdigit() for ch in token): code=token
        unit='EA' if code or name in {'stud','lug nut'} or (category=='Misc' and qty==1) else 'QT' if name=='oil (quart)' or (name in {'transmission fluid','power steering fluid'} and re.search(r'\bQTS?\b',details,re.I)) else 'GAL' if name=='washer fluid' and re.search(r'\bGALS?\b',details,re.I) else ''
        if towing:
            if name in {'trailer tandems','misc nuts, bolts, washers','brass fittings - misc'}: category='Parts'
            elif name=='labor': category='Labor'
            elif name=='tow (hourly)': category='Labor'; unit='HR'; code=''
            elif name=='mileage - hd': category='Misc'; unit='MI'
            elif name in {'fuel surcharge','dollies','tow/hook fee','tram bar alignment'}: category='Misc'; unit='EA' if qty==1 else ''
        consistent=None if None in (qty,price,amount) else abs(qty*price-amount)<=TOL
        # Only an explicit item identifier or a single, named fee is eligible.
        eligible=bool(name!='mileage - hd' and consistent is True and qty>0 and price>0 and amount>0 and ((code and unit) or (category=='Misc' and qty==1)))
        doc.items.append(LineItem(desc,pn,category,code=code,quantity=qty,unit=unit,unit_price=price,amount=amount,
            price_source='printed Price' if price is not None else 'missing',comparison_eligible=eligible,amount_consistent=consistent,
            printed={'Charge Description':desc,'Details':details,'Quantity':qty,'Price':price,'Line Total':amount}))
        if consistent is not True: doc.warnings.append('Missing or inconsistent quantity, price or line total; review.')
        pending=None
    for pn,page in enumerate(pdf.pages,1):
        ls=lines(page); idx=next((i for i,l in enumerate(ls) if l.text.casefold()==HEADER.casefold()),None)
        if pn==1 and idx is not None:
            header=ls[:idx]
            for l in header:
                left=' '.join(w['text'] for w in l.words if w['x0']<page.width*.49)
                for key in ('Invoice #','Purchase Order #','Reason','Unit #','Reference #','Date/Time Requested') + (('Call #','Tow Reason','Reference Number','Unit Number','Date/Time Completed','Printed') if towing else ()):
                    if left.casefold().startswith(key.casefold()+' '):
                        val=left[len(key):].strip()
                        if key in doc.metadata and doc.metadata[key]!=val: doc.warnings.append('Conflicting '+key)
                        doc.metadata[key]=val
            # The service location has its own right-side label and value.
            for n,l in enumerate(header):
                mid=' '.join(w['text'] for w in l.words if page.width*.49<=w['x0']<page.width*.60)
                if mid=='Service':
                    vals=[]
                    for r in header[n:n+3]:
                        label=' '.join(w['text'] for w in r.words if page.width*.49<=w['x0']<page.width*.60)
                        if r is not l and label!='Location':
                            if label: break
                            continue
                        vals.append(' '.join(w['text'] for w in r.words if w['x0']>=page.width*.60))
                    doc.metadata['Service location']=' '.join(filter(None,vals)); break
            if towing:
                if len(header)>1:
                    address=' '.join(w['text'] for w in header[1].words if w['x0']<page.width*.75)
                    if address: doc.metadata['Vendor address']=address
                printed=next((l.text[8:].strip() for l in header if l.text.startswith('Printed ')),None)
                if printed: doc.metadata['Printed date']=printed
                # Tow origin and destination may wrap above or below their labels.
                for n,l in enumerate(header):
                    label=' '.join(w['text'] for w in l.words if 300<=w['x0']<365)
                    if label not in ('Tow From','Tow To'): continue
                    vals=[]
                    for j in range(max(0,n-1),min(len(header),n+2)):
                        r=header[j]
                        other=' '.join(w['text'] for w in r.words if 300<=w['x0']<365)
                        if j!=n and (other or abs(r.top-l.top)>12): continue
                        val=' '.join(w['text'] for w in r.words if w['x0']>=365)
                        if val: vals.append(val)
                    if vals: doc.metadata[label]=' '.join(vals)
            notes_idx=next((n for n,l in enumerate(header) if any(w['text']=='Notes' and w['x0']<65 for w in l.words)),None)
            vehicle_idx=next((n for n,l in enumerate(header) if l.text.startswith('Year Make Model Color VIN Plate')),None)
            if vehicle_idx is not None and vehicle_idx+1<len(header):
                h=header[vehicle_idx].words
                anchors=[(w['text'],w['x0']) for w in h if w['text'] in ('Year','Make','Model','Color','VIN','Plate','Odometer','Unit')]
                for j,(k,x) in enumerate(anchors):
                    end=anchors[j+1][1]-2 if j+1<len(anchors) else page.width
                    value=' '.join(w['text'] for w in header[vehicle_idx+1].words if x-2<=w['x0']<end)
                    if value: doc.metadata['Vehicle '+k]=value
            if notes_idx is not None:
                start=notes_idx
                # Multi-line note may be vertically centered next to Notes label.
                while start>0 and header[start-1].top>header[notes_idx].top-35 and not any(w['x0']<90 for w in header[start-1].words): start-=1
                note=' '.join(' '.join(w['text'] for w in l.words if w['x0']>=90) for l in header[start:vehicle_idx if vehicle_idx is not None else len(header)]).strip()
                if note: doc.notes['Complaint']=note
        if idx is None:
            # Actual samples have signature-only continuation pages.
            if summary_seen and all(re.match(r'^(Signature:|_+|Created with Towbook)',l.text,re.I) for l in ls): continue
            doc.warnings.append(f'Page {pn}: unrecognized continuation; review.')
            continue
        if summary_seen: doc.warnings.append('Detail header after final summary; review.')
        table_seen=True
        anchors={w['text']:w for w in ls[idx].words}
        q0=anchors['Quantity']['x0']-8; p1=anchors['Price']['x1']; t1=anchors['Total']['x1']
        for l in ls[idx+1:]:
            sm=SUMMARY.fullmatch(l.text)
            if sm:
                flush(); key=sm[1].rstrip(':').title(); value=decimal(sm[2])
                if key in doc.summary and doc.summary[key]!=value: doc.warnings.append('Conflicting '+key)
                doc.summary[key]=value; doc.summary_pages[key]=pn
                if key=='Grand Total': summary_seen=True
                if key=='Amount Due': break
                continue
            if re.match(r'^(\*\*4%|CUSTOMER IS RESPONSIBLE|Damage Disclaimer|Signature:|Created with Towbook)',l.text,re.I):
                flush(); break
            cells=[[],[],[],[]]
            for w in l.words:
                x=w['x0']; end=w['x1']
                col=0 if x<q0 and not (w['text'].startswith('$') and end>p1-15) else 1 if end<p1-22 else 2 if end<(p1+t1)/2 else 3
                cells[col].append(w['text'])
            desc,q,p,a=[' '.join(g) for g in cells]
            if any((q,p,a)):
                flush(); pending=(desc,[],decimal(q),decimal(p),decimal(a),pn)
                if not desc: doc.warnings.append('Numeric row without charge description.')
            elif desc and pending: pending[1].append(desc)
            elif desc: doc.warnings.append('Unassigned detail text; review.')
        flush()
    if not table_seen or not doc.items: doc.warnings.append('No recognized charge items.')
    known=sum((i.amount for i in doc.items if i.amount is not None),Decimal(0))
    complete=bool(doc.items) and all(i.amount is not None for i in doc.items)
    subtotal=doc.summary.get('Subtotal'); total=doc.summary.get('Grand Total')
    check_delta(doc,'Printed subtotal vs rows',subtotal,known if complete else None)
    check_delta(doc,'Grand total vs subtotal and adjustments',total,subtotal+sum((v for k,v in doc.summary.items() if k.casefold() in ('tax','taxes','sales tax') or k.casefold().endswith('% tax')),Decimal(0))-doc.summary.get('Discount',Decimal(0)) if subtotal is not None else None)
    if 'Amount Due' in doc.summary: check_delta(doc,'Amount due vs total less printed payments',doc.summary['Amount Due'],total-doc.summary.get('Payments',doc.summary.get('Payments/Credits',Decimal(0))) if total is not None else None)
    if towing and 'quote' in doc.notes.get('Complaint','').casefold():
        doc.warnings.append('Printed invoice contains quote language; confirm final billing status before comparison.')
    if doc.warnings or any(v is None or abs(v)>TOL for v in doc.checks.values()):
        for i in doc.items: i.comparison_eligible=False
    doc.warnings.append('Date/time requested is not an issue date. Service location is not necessarily a branch. Labor units are not printed; invoice is not proof of payment.' if not towing else 'Request, completion and print dates are not necessarily invoice issue dates. Tow origin/destination are not vendor branches. Units are retained only when explicit. Invoice is not proof of payment.')
    return doc
