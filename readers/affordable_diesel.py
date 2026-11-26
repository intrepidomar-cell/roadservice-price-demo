"""Affordable Diesel digital activity invoice with nested bundle components."""
import hashlib,re
from decimal import Decimal
from core.models import Invoice,LineItem,Operation
from core.pdf_utils import lines,decimal,field
from core.validation import check_delta,TOL
HEADER='ACTIVITY QTY RATE AMOUNT'
def read(pdf,path=None):
    doc=Invoice('affordable_diesel_v1',vendor='Affordable Diesel Repair, Inc.',document_type='invoice',pages=len(pdf.pages))
    if path is not None:doc.metadata['Source SHA-256']=hashlib.sha256(path.read_bytes()).hexdigest()
    text=pdf.pages[0].extract_text() or ''
    for key,pat in [('Invoice #',r'INVOICE #\s*(\S+)'),('Date',r'(?<!DUE )\bDATE\s+(\d+/\d+/\d+)'),('Due date',r'DUE DATE\s+(\d+/\d+/\d+)'),('PO #',r'^(RS-\S+)'),('Unit #',r'Truck#\s*(\S+)'),('Reference #',r'Ref#[ \t]+([A-Z0-9-]+)'),('Terms',r'TERMS\s+([^\n]+)')]:
        val=field(text,pat)
        if val:doc.metadata[key]=val
    doc.metadata['Vendor address']=field(text,r'^Affordable Diesel Repair, Inc\.\s*\n([^\n]+\n[^\n]+)').replace('\n',', ')
    seen=False; finished=False; pending=None; parent=None; component_values=[]; components=[]
    def flush():
        nonlocal pending,parent
        if pending is None:return
        desc,q,p,a,pn,indent,details=pending;qty,rate,amount=map(decimal,(q,p,a.rstrip('T') if a else a))
        if desc.startswith('***WORK'):
            # Explicit narrative headings, not economic services even when printed as zero.
            doc.notes['Complaint' if 'TO BE DONE' in desc else 'Service comments']=' '.join(details)
        elif indent and amount is None and parent is not None and qty is not None and rate is not None:
            # Child has no extended amount printed; display the original values but never add it to billed charges.
            item=LineItem(desc,pn,'Labor' if desc.upper()=='LABOR RATE' else 'Misc' if desc.lower()=='fuel surcharge' else 'Unclassified',quantity=qty,unit_price=rate,price_source='printed component Rate',printed={'Activity':desc,'Details':' '.join(details),'Qty':qty,'Rate':rate,'Amount':None,'Role':'Included component — not an additional charge'},operation=parent)
            doc.items.append(item);components.append(item);component_values.append(qty*rate)
        else:
            category='Misc' if 'call out' in desc.lower() or 'surcharge' in desc.lower() else 'Unclassified'
            consistent=None if None in (qty,rate,amount) else abs(qty*rate-amount)<=TOL
            parent=f'{len(doc.operations)+1}. {desc}'
            op=Operation(len(doc.operations)+1,desc,page=pn,end_page=pn,total=amount,notes={'total label':'Activity total'});doc.operations.append(op)
            doc.items.append(LineItem(desc,pn,category,quantity=qty,unit_price=rate,amount=amount,price_source='printed Rate' if rate is not None else 'missing',amount_consistent=consistent,operation=parent,printed={'Activity':desc,'Details':' '.join(details),'Qty':qty,'Rate':rate,'Amount':amount,'Role':'Billed activity'}))
            if amount is None or consistent is False:doc.warnings.append('Incomplete or inconsistent billed activity.')
        pending=None
    for pn,page in enumerate(pdf.pages,1):
        for l in lines(page):
            t=l.text
            if t==HEADER:seen=True;continue
            # Summary is right aligned, including a line with unrelated notes at left.
            right=' '.join(w['text'] for w in l.words if w['x0']>=page.width*.50)
            sm=re.fullmatch(r'(SUBTOTAL|TAX|TOTAL|BALANCE DUE|PAYMENTS|DISCOUNT)\s+(\$?[\d,.]+)',right,re.I)
            if sm:
                flush();finished=True;doc.summary[sm[1].title()]=decimal(sm[2]);doc.summary_pages[sm[1].title()]=pn;continue
            if not seen or finished or t.startswith('We appreciate'):continue
            cells=['']*4
            for w in l.words:
                x=w['x0']*612/page.width;j=0 if x<290 else 1 if x<400 else 2 if x<505 else 3
                cells[j]+=(' ' if cells[j] else '')+w['text']
            desc,q,p,a=cells
            if desc and any(cells[1:]):
                flush();pending=(*cells,pn,l.words[0]['x0']*612/page.width>65,[])
            elif desc and pending:pending[-1].append(desc)
        flush();seen=False
    billed=[i for i in doc.items if i.printed.get('Role')=='Billed activity']
    check_delta(doc,'Subtotal vs billed activities',doc.summary.get('Subtotal'),sum((i.amount for i in billed),Decimal(0)) if billed and all(i.amount is not None for i in billed) else None)
    if len(billed)==1 and components:check_delta(doc,'Printed bundle vs component quantity × rate',billed[0].amount,sum(component_values,Decimal(0)))
    sub=doc.summary.get('Subtotal');tax=doc.summary.get('Tax')
    check_delta(doc,'Total vs subtotal plus tax',doc.summary.get('Total'),sub+tax if sub is not None and tax is not None else None)
    if components:doc.warnings.append('Included components have no printed extended price; do not count them again or compare the bundle as a standalone service rate.')
    doc.warnings.append('Invoice is not proof of payment. Component units and billing channel not inferred.')
    return doc
