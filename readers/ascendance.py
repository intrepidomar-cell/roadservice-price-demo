"""Ascendance Davenport: line status and payer, separate approved and additional estimates."""
import re,hashlib
from decimal import Decimal
from core.models import Invoice,LineItem,Operation
from core.pdf_utils import lines,decimal,field
from core.validation import check_delta,TOL


def read(pdf,path=None):
    d=Invoice('ascendance_v1','Ascendance Trucks Eastern Iowa, LLC','service_order',pages=len(pdf.pages))
    if path:d.metadata['Source SHA-256']=hashlib.sha256(path.read_bytes()).hexdigest()
    first=pdf.pages[0].extract_text() or ''
    d.metadata.update({'Shop city/state/ZIP':'Davenport, IA 52806','Service Order':field(first,r'SERVICE ORDER:[ \t]*(\S+)'),'Document status':'Service Order; approved and additional estimates separate'})
    op=None;active=False;note=None;pending=None;footer=False;group='';totals={}
    def crop(l,a,b):return ' '.join(w['text'] for w in l.words if a<=w['x0']<b)
    def flush():
        nonlocal pending
        if pending is None:return
        (status,q,c,desc,p,a),pn,owner=pending;qty,price,amt=map(decimal,(q,p,a))
        cat='Labor' if c.startswith('LABOR ') else 'Misc' if c=='COM' else 'Parts' if re.match(r'\d{3}[A-Z]/',c) else 'Unclassified'
        d.items.append(LineItem(desc,pn,cat,code=c,quantity=qty,unit_price=price,amount=amt,price_source='printed Unit Price' if price is not None else 'missing',amount_consistent=None if None in (qty,price,amt) else abs(qty*price-amt)<=TOL,operation=f'{owner.number}. {owner.title}',printed=dict(zip(('Status','Qty','Item','Description','Unit Price','Extd Price'),(status,qty,c,desc,price,amt)))))
        pending=None
    for pn,p in enumerate(pdf.pages,1):
        ls=lines(p);active=False;note=None
        for n,l in enumerate(ls):
            t=l.text
            if pn==1 and t.startswith('DATE ARRIVED DATE ARRIVED DATE INVOICE') and n+1<len(ls):
                for k,a,b in [('Date arrived',0,120),('Date invoice',120,215),('Sales type',215,305),('Advisor',305,400),('Terms',400,465),('Customer PO',465,612)]:
                    v=crop(ls[n+1],a,b)
                    if v:d.metadata[k]=v
            if pn==1 and t.startswith('YEAR MAKE MODEL VIN') and n+1<len(ls):
                for k,a,b in [('Year',0,55),('Make',55,155),('Model',155,235),('VIN',235,355),('Unit #',355,440),('In Service',440,515),('Odometer',515,612)]:
                    v=crop(ls[n+1],a,b)
                    if v:d.metadata[k]=v
            if t.startswith('TERMS OF SALE'):flush();footer=True;active=False;note=None
            if footer:
                right=crop(l,430,612)
                if right in ('Approved:','Additional Estimates:'):group=right[:-1];continue
                m=re.fullmatch(r'(Labor|Parts|Misc|Sublet|PrePay|Subtotal|Shop Supplies|Misc Supplies|Taxes|Total|Est Total|Total w Est):\s+(\$[\d,.]+)',right,re.I)
                if m and group:
                    k=m[1] if m[1]=='Total w Est' else group+' — '+m[1]
                    d.summary[k]=decimal(m[2]);d.summary_pages[k]=pn
                continue
            m=re.match(r'^JOB#\s*(\d+)\s+(.*?)\s+(CUSTOMER PAY|WARRANTY)$',t,re.I)
            if m:
                flush();op=Operation(int(m[1]),m[2],warranty=m[3]=='WARRANTY',page=pn,end_page=pn,notes={'payer':m[3]});d.operations.append(op);active=False;note=None;continue
            if t=='STATUS QTY ITEM DESCRIPTION UNIT PRICE EXTD PRICE':active=op is not None;note=None;continue
            if not op:continue
            if re.match(r'^(Effective May|Page \d|SERVICE ORDER:|ESTIMATE:)',t):flush();active=False;note=None;continue
            if t.startswith('CLAIM NUMBER#'):note=None;continue
            m=re.match(r'^(COMPLAINT|CAUSE|CORRECTION):\s*(.*)',t)
            if m:flush();active=False;note=m[1].lower();op.notes[note]=m[2];continue
            if re.match(r'^(SOLD|ESTIMATE|REJECTED)\s+(?:Prepay:|Parts:)',t):
                flush();active=False;note=None
                status=t.split()[0];vals={k:decimal(v) for k,v in re.findall(r'(Prepay|Parts|Labor|Misc|Sublet|Subtotal):\s*(\$?[\d,.]+)',t)}
                if all(k in vals for k in ('Parts','Labor','Misc','Sublet','Subtotal')):
                    totals[op.number,status]=vals['Subtotal'];op.notes[status+' subtotal']=str(vals['Subtotal']);op.notes['economic breakdown']=op.notes.get('economic breakdown','')+(' | ' if 'economic breakdown' in op.notes else '')+t
                    check_delta(d,f'Job {op.number} {status} subtotal',vals['Subtotal'],sum(vals[k] for k in ('Parts','Labor','Misc','Sublet'))-vals.get('Prepay',Decimal(0)))
                    if status=='SOLD':op.total=vals['Subtotal'];op.notes['total label']='Sold subtotal'
                continue
            if active:
                c=[crop(l,a,b) for a,b in [(20,80),(80,115),(115,255),(255,460),(460,535),(535,612)]]
                if c[0] in ('SOLD','ESTIMATE','REJECTED') and c[2]:flush();pending=(c,pn,op);op.end_page=pn
                elif pending and c[3] and not any(c[:3]+c[4:]):pending[0][3]+=' '+c[3]
                else:d.warnings.append('Unrecognized Ascendance detail row; review.')
            elif note:op.notes[note]+=' '+t
        flush()
    for (num,status),total in totals.items():
        its=[i for i in d.items if i.operation.startswith(f'{num}. ') and i.printed['Status']==status]
        check_delta(d,f'Job {num} {status} rows',total,sum((i.amount for i in its),Decimal(0)) if all(i.amount is not None for i in its) else None)
    for status,g,end in [('SOLD','Approved','Total'),('ESTIMATE','Additional Estimates','Est Total')]:
        s={k.split(' — ',1)[1]:v for k,v in d.summary.items() if k.startswith(g+' — ')}
        if not s:continue
        check_delta(d,g+' job subtotals',s.get('Subtotal'),sum((v for (n,st),v in totals.items() if st==status),Decimal(0)))
        keys=('Subtotal','Shop Supplies','Misc Supplies','Taxes')
        check_delta(d,g+' total',s.get(end),sum(s[k] for k in keys) if all(k in s for k in keys) else None)
        if all(k in s for k in ('Labor','Parts','Misc','Sublet')):check_delta(d,g+' printed components',s.get('Subtotal'),sum(s[k] for k in ('Labor','Parts','Misc','Sublet'))-s.get('PrePay',Decimal(0)))
    if 'Total w Est' in d.summary:check_delta(d,'Total with estimate',d.summary['Total w Est'],d.summary['Approved — Total']+d.summary['Additional Estimates — Est Total'] if 'Approved — Total' in d.summary and 'Additional Estimates — Est Total' in d.summary else None)
    if any(i.amount is None for i in d.items):d.warnings.append('Unpriced warranty rows are missing, not zero; no row-level amount inferred.')
    return d
