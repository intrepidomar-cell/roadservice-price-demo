"""Atlantic Utility Trailer Sales direct service estimate/invoice, distinct from FleetPerform."""
import hashlib,re
from decimal import Decimal
from core.models import Invoice, Operation, LineItem
from core.pdf_utils import lines, decimal, field
from core.validation import check_delta,TOL


def read(pdf,path=None):
    first=pdf.pages[0].extract_text() or ''
    final=bool(re.search(r'SERVICE INVOICE:',first)) and not re.search(r'\bSERVICE ESTIMATE:',first)
    d=Invoice('atlantic_utility_v1','Atlantic Utility Trailer Sales','invoice' if final else 'estimate',pages=len(pdf.pages))
    if path:d.metadata['Source SHA-256']=hashlib.sha256(path.read_bytes()).hexdigest()
    d.metadata.update({'Shop city/state/ZIP':'Thorofare, NJ 08086','Billing format':'Direct','Document number':field(first,r'SERVICE (?:ESTIMATE|INVOICE):\s*(\S+)')})
    top_total=decimal(field(first,r'INVOICE TOTAL:\s*(\$[\d,.]+)'))
    op=None;active=False;note=None;pending=None;footer=False;state='Estimate'
    def crop(l,a,b):return ' '.join(w['text'] for w in l.words if a<=w['x0']<b)
    def flush():
        nonlocal pending
        if not pending:return
        (q,c,desc,p,a),pn,owner=pending;qty,price,amt=map(decimal,(q,p,a))
        cat='Labor' if c.startswith('LABOR ') else 'Parts' if c else 'Unclassified'
        d.items.append(LineItem(desc,pn,cat,code=c,quantity=qty,unit='HR' if cat=='Labor' and qty is not None and price is not None else '',unit_price=price,amount=amt,price_source='printed Unit Price' if price is not None else 'missing',amount_consistent=None if None in (qty,price,amt) else abs(qty*price-amt)<=TOL,operation=f'{owner.number}. {owner.title}',printed=dict(zip(('Qty','Item','Description','Unit Price','Extd Price'),(qty,c,desc,price,amt)))))
        pending=None
    for pn,p in enumerate(pdf.pages,1):
        ls=lines(p.filter(lambda o:o.get('object_type')!='char' or o.get('size',0)<20))
        for n,l in enumerate(ls):
            t=l.text
            if pn==1 and t.startswith('DATE INVOICE SALES TYPE') and n+1<len(ls):
                for k,a,b in [('Invoice Date',0,120),('Sales type',120,230),('Advisor',230,320),('Terms',320,390),('Customer reference',390,500),('Customer Unit #',500,560),('Dealer Unit ID',560,612)]:
                    v=crop(ls[n+1],a,b)
                    if v:d.metadata[k]=v
            if pn==1 and t.startswith('YEAR MAKE MODEL VIN') and n+1<len(ls):
                for k,a,b in [('Year',0,65),('Make',65,135),('Model',135,195),('VIN',195,290),('Odometer',290,355),('Reefer',355,430),('Reefer serial',430,520),('Engine hours',520,612)]:
                    v=crop(ls[n+1],a,b)
                    if v:d.metadata[k]=v
            if t.startswith('Statement of Disclaimer:'):flush();footer=True;active=False;note=None
            if footer:
                m=re.fullmatch(r'(LABOR|PARTS|PREPAY|MISC|SUBLET|SUBTOTAL|SHOP SUPPLIES|TAX|TOTAL)\s+(\$[\d,.]+)',crop(l,440,612))
                if m:d.summary[m[1]]=decimal(m[2]);d.summary_pages[m[1]]=pn
                continue
            m=re.fullmatch(r'(Sold|Estimate|Rejected) Operations(?: \(Cont\.\))?',t)
            if m:state=m[1];continue
            m=re.match(r'JOB #\s*(\d+)\s+(\S+)\s*-?\s*(.*)',t)
            if m:
                flush();op=Operation(int(m[1]),f'[{state}] {m[3].lstrip("- ")}',m[2],page=pn,end_page=pn,notes={'status':state});d.operations.append(op);active=False;note=None;continue
            if t=='QTY ITEM DESCRIPTION UNIT PRICE EXTD PRICE':active=op is not None;note=None;continue
            if not op:continue
            if t.startswith('Prepay:'):
                flush();active=False;note=None
                vals=re.findall(r'\$?\d[\d,]*(?:\.\d+)?',t)
                if len(vals)==6:
                    pre,parts,lab,misc,sub,total=map(decimal,vals);op.total=total;op.notes['economic breakdown']=t
                    check_delta(d,f'Job {op.number} subtotal',total,parts+lab+misc+sub-pre)
                continue
            if t.startswith('Page '):flush();active=False;note=None;continue
            m=re.match(r'^(COMPLAINT|CAUSE|CORRECTION)\s*(.*)',t)
            if m:flush();active=False;note=m[1].lower();op.notes[note]=m[2];continue
            if active:
                c=[crop(l,a,b) for a,b in [(20,57),(57,202),(202,440),(440,535),(535,612)]]
                if c[1] and c[2]:flush();pending=(c,pn,op);op.end_page=pn
                elif pending and c[2] and not any(c[:2]+c[3:]):pending[0][2]+=' '+c[2]
                else:d.warnings.append('Unrecognized Atlantic detail row; review.')
            elif note:op.notes[note]+=' '+t
        flush()
    for op in d.operations:
        its=[i for i in d.items if i.operation==f'{op.number}. {op.title}'];check_delta(d,f'Job {op.number} rows',op.total,sum((i.amount for i in its),Decimal(0)) if its and all(i.amount is not None for i in its) else None)
    s=d.summary
    keys=('LABOR','PARTS','MISC','SUBLET','PREPAY')
    check_delta(d,'Printed subtotal',s.get('SUBTOTAL'),sum(s[k] for k in keys[:4])-s['PREPAY'] if all(k in s for k in keys) else None)
    check_delta(d,'Printed total',s.get('TOTAL'),sum(s[k] for k in ('SUBTOTAL','SHOP SUPPLIES','TAX')) if all(k in s for k in ('SUBTOTAL','SHOP SUPPLIES','TAX')) else None)
    check_delta(d,'Header total vs summary',top_total,s.get('TOTAL'))
    return d
