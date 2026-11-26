"""Albuquerque Freightliner digital service order / estimate, including warranty."""
import hashlib,re
from core.models import Invoice,LineItem,Operation
from core.pdf_utils import lines,decimal,field
from core.validation import TOL,check_delta
from decimal import Decimal

HEADER='STATUS QTY ITEM DESCRIPTION UNIT PRICE EXTD PRICE'
def read(pdf,path=None):
    doc=Invoice('albuquerque_v1',vendor='Albuquerque Freightliner',document_type='estimate',pages=len(pdf.pages))
    if path is not None: doc.metadata['Source SHA-256']=hashlib.sha256(path.read_bytes()).hexdigest()
    text=pdf.pages[0].extract_text() or ''
    for key,pat in [('Service Order',r'SERVICE ORDER:\s*(\S+)'),('Estimate',r'ESTIMATE:\s*(\S+)'),('Tag Number',r'TAG NUMBER:\s*([^\n]+)'),('Date arrived',r'^(\d+/\d+/\d+\s+\d+:\d+:\d+[AP]M)')]:
        v=field(text,pat)
        if v: doc.metadata[key]=v
    doc.metadata['Vendor address']=field(text,r'^Albuquerque Freightliner\s*\n([^\n]+\n[^\n]+)').replace('\n',', ')
    op=None; state=''; pending=None; active=False
    def flush():
        nonlocal pending
        if pending is None:return
        cells,pn,owner=pending
        status,q,code,desc,p,a=cells; qty,price,amount=map(decimal,(q,p,a))
        category='Labor' if code.upper().startswith('LABOR ') else 'Parts' if code else 'Unclassified'
        consistent=None if None in (qty,price,amount) else abs(qty*price-amount)<=TOL
        doc.items.append(LineItem(desc,pn,category,code=code,quantity=qty,unit_price=price,amount=amount,price_source='printed Unit Price' if price is not None else 'missing',amount_consistent=consistent,operation=f'{owner.number}. {owner.title}',printed=dict(zip(('Status','Qty','Item','Description','Unit Price','Extd Price'),(status,qty,code,desc,price,amount)))))
        pending=None
    for pn,page in enumerate(pdf.pages,1):
        ls=lines(page)
        for n,l in enumerate(ls):
            t=l.text
            if pn==1 and t.startswith('YEAR MAKE MODEL VIN') and n+1<len(ls):
                values=ls[n+1].words
                for key,lo,hi in [('Year',0,45),('Make',45,110),('Model',110,180),('VIN',180,275),('Unit #',275,355),('Engine hours',355,420),('In service',420,470),('Component serial',470,545),('Odometer',545,612)]:
                    v=' '.join(w['text'] for w in values if lo<=w['x0']*612/page.width<hi)
                    if v: doc.metadata[key]=v
            m=re.match(r'^JOB#\s*(\d+)\s+(.*)$',t,re.I)
            if m:
                flush(); title=re.sub(r'\s+WARRANTY$','',m[2],flags=re.I);op=Operation(int(m[1]),title,warranty=bool(re.search(r'\bWARRANTY$',m[2],re.I)),page=pn,end_page=pn);doc.operations.append(op);state='';active=False;continue
            if t==HEADER: active=op is not None;state='';continue
            if re.match(r'^(Page \d|Thank you|TERMS AND CONDITIONS|Albuquerque Freightliner|SERVICE ORDER:|ESTIMATE:)',t,re.I):
                flush();active=False;state='';continue
            if op is None:continue
            m=re.match(r'^(COMPLAINT|CAUSE|CORRECTION):\s*(.*)$',t,re.I)
            if m:flush();state=m[1].lower();op.notes[state]=m[2];active=False;continue
            if active:
                cells=['']*6
                for w in l.words:
                    x=w['x0']*612/page.width
                    j=0 if x<65 else 1 if x<110 else 2 if x<250 else 3 if x<480 else 4 if x<545 else 5
                    cells[j]+=(' ' if cells[j] else '')+w['text']
                if cells[0] and cells[2]:flush();pending=(cells,pn,op);op.end_page=pn
                elif pending and cells[3] and not any(cells[:3]+cells[4:]):pending[0][3]+=' '+cells[3]
                else:doc.warnings.append('Unrecognized operation detail; review.')
            elif state:op.notes[state]+=' '+t
        flush()
    if not doc.items:doc.warnings.append('No recognized items.')
    if any(i.amount is None for i in doc.items):doc.warnings.append('Warranty / other unpriced lines: missing amounts are not zero. No spend total inferred.')
    if not doc.summary:doc.warnings.append('No printed economic summary in the recognized layout; monetary reconciliation unavailable.')
    # Estimates and warranty rows never eligible automatically.
    return doc
