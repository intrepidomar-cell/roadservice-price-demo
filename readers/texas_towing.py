"""Texas Towing Wrecker Service digital invoices."""
import hashlib,re
from decimal import Decimal
from core.models import Invoice,LineItem
from core.pdf_utils import lines,decimal,field
from core.validation import check_delta,TOL
HEADER='TOW CHARGE DESCRIPTION QTY RATE AMOUNT'
def read(pdf,path=None):
    doc=Invoice('texas_towing_v1',vendor='Texas Towing Wrecker Service Inc.',document_type='invoice',pages=len(pdf.pages))
    if path is not None:doc.metadata['Source SHA-256']=hashlib.sha256(path.read_bytes()).hexdigest()
    text=pdf.pages[0].extract_text() or ''
    doc.metadata['Invoice #']=field(text,r'INVOICE:\s*(\S+)')
    doc.metadata['Vendor address']=field(text,r'^TEXAS TOWING WRECKER SERVICE INC\.[^\n]*\n(?:INVOICE:[^\n]*\n)?([^\n]+\n[^\n]+)').replace('\n',', ')
    doc.metadata['Date']=field(text,r'\b([A-Z]{3} \d{1,2}, \d{4})\b')
    doc.metadata['TDLR']=field(text,r'^TDLR\s+(\S+)')
    pending=None;seen=False;finished=False
    def flush():
        nonlocal pending
        if not pending:return
        desc,q,p,a,pn=pending;qty,rate,amount=map(decimal,(q,p,a))
        category='Labor' if desc.startswith('LABOR ') else 'Misc' if desc.startswith('JUMP ') or desc=='FUEL SURCHARGE' else 'Unclassified'
        consistent=None if None in (qty,rate,amount) else abs(qty*rate-amount)<=TOL
        doc.items.append(LineItem(desc,pn,category,quantity=qty,unit='HR' if category=='Labor' and 'MIN WAIT TIME' in desc else 'EA' if desc.startswith('JUMP ') and qty==1 else '',unit_price=rate,amount=amount,price_source='printed Rate' if rate is not None else 'missing',amount_consistent=consistent,printed={'Tow Charge Description':desc,'Qty':qty,'Rate':rate,'Amount':amount}))
        if amount is None or consistent is False:doc.warnings.append('Incomplete or inconsistent charge.')
        pending=None
    for pn,page in enumerate(pdf.pages,1):
        ls=lines(page)
        for n,l in enumerate(ls):
            t=l.text
            if pn==1 and t=='NOTES' and n+1<len(ls):doc.notes['Complaint']=ls[n+1].text
            if pn==1 and t=='YEAR COLOR MAKE / MODEL VIN / SERIAL NUMBER UNIT' and n+1<len(ls):
                for key,lo,hi in [('Year',0,80),('Color',80,150),('Make/model',150,310),('VIN',310,490),('Unit #',490,595)]:doc.metadata[key]=' '.join(w['text'] for w in ls[n+1].words if lo<=w['x0']*595/page.width<hi)
            if pn==1 and t=='PICK UP: DROP OFF OR STORED:':
                for key,lo,hi in [('Pickup',0,290),('Drop off',290,595)]:doc.metadata[key]=' '.join(w['text'] for r in ls[n+1:n+3] for w in r.words if lo<=w['x0']*595/page.width<hi)
            if t==HEADER:seen=True;continue
            m=re.fullmatch(r'(INVOICE TOTAL|PAYMENTS & CREDITS|BALANCE)\s*(\$[\d,.]+)?',t)
            if m:
                flush();finished=True
                if m[2]:doc.summary[m[1].title()]=decimal(m[2]);doc.summary_pages[m[1].title()]=pn
                continue
            if not seen or finished:continue
            if t.startswith(('Page ','CUSTOMER SIGNATURE')):flush();continue
            cells=['']*4
            for w in l.words:
                x=w['x0']*595/page.width;j=0 if x<390 else 1 if x<445 else 2 if x<510 else 3
                cells[j]+=(' ' if cells[j] else '')+w['text']
            if any(cells[1:]):flush();pending=(*cells,pn)
            elif cells[0] and pending:pending=(pending[0]+' '+cells[0],*pending[1:])
        flush();seen=False
    check_delta(doc,'Invoice total vs charges',doc.summary.get('Invoice Total'),sum((i.amount for i in doc.items),Decimal(0)) if doc.items and all(i.amount is not None for i in doc.items) else None)
    if 'Payments & Credits' in doc.summary and 'Invoice Total' in doc.summary:check_delta(doc,'Balance vs total less credits',doc.summary.get('Balance'),doc.summary['Invoice Total']-doc.summary['Payments & Credits'])
    doc.warnings.append('Unprinted quantity, rate and payment amounts remain blank. Vendor identity must be matched separately; invoice is not proof of payment.')
    return doc
