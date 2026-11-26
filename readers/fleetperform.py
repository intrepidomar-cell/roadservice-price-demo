"""FleetPerform digital grid reader. One ordered list across all detail pages."""
import re
import hashlib
from decimal import Decimal
from core.models import Invoice, LineItem
from core.pdf_utils import lines, decimal
from core.validation import check_delta,TOL

HEADER=['Type','Line','Labor/Part','Description','Position Codes','UOM','Hrs/Qty','Rate/Price','Ext Amt']
SUMMARY=re.compile(r'(Total Parts|Total Labor|Special Charges|Freight|Tax|Estimate Total|Invoice Total)\s*:?\s*(\$[\d,]+\.\d{2})$',re.I)
TYPE={'L':'Labor','P':'Parts','M':'Misc'}

def read(pdf,path=None):
    doc=Invoice('fleetperform_v1','FleetPerform','estimate',pages=len(pdf.pages))
    if path is not None: doc.metadata['Source SHA-256']=hashlib.sha256(path.read_bytes()).hexdigest()
    doc.metadata['Billing format']='FleetPerform'
    first=pdf.pages[0].extract_text() or ''
    if re.search(r'FLEET REPAIR SOLNS',first,re.I):
        doc.vendor='Fleet Repair Solutions'
        doc.metadata['Printed vendor']='FLEET REPAIR SOLNS-'
        m=re.search(r'^([A-Z ]+ [A-Z]{2},\s*\d{5}(?:-\d{4})?)\s+(?:PO|Reference|Phone)',first,re.M)
        if m: doc.metadata['Shop city/state/ZIP']=m[1]
    if re.search(r'ATLANTIC UTILITY TRLR SLS',first,re.I):
        doc.vendor='Atlantic Utility Trailer Sales'
        doc.metadata['Printed vendor']='ATLANTIC UTILITY TRLR SLS'
        m=re.search(r'^([A-Z ]+ [A-Z]{2},\s*\d{5}(?:-\d{4})?)\s+(?:PO|Reference|Phone)',first,re.M)
        if m: doc.metadata['Shop city/state/ZIP']=m[1]
    if 'Estimate (Invoiced)' in first: doc.metadata['Document status']='Invoiced (estimate copy; not proof of payment)'
    else: doc.metadata['Document status']='Estimate'
    for label in ('Estimate #','Submit Date','Approve Date','PO #','Reference #','Vendor Inv #','Dealer Inv #','Unit Number','VIN','Make/Model'):
        m=re.search(re.escape(label)+r'[ \t]*:[ \t]*([^\n]*)',first)
        if m and m[1].strip(): doc.metadata[label]=m[1].strip()
    seen=False; summary_started=False; grid_widths=None
    def clean(x): return ' '.join((x or '').split())
    def row(c,pn):
        c=list(map(clean,c)); typ,ln,code,desc,pos,uom,q,rate,ext=c
        if typ not in TYPE:
            doc.warnings.append(f'Unrecognized FleetPerform row type on page {pn}.'); return
        category=TYPE[typ]; qty,price,amount=map(decimal,(q,rate,ext)); normalized=qty; unit=uom.upper(); multiplier=1
        if category=='Labor':
            unit='HR'; m=re.fullmatch(r'(\d+)\s*\(Units?\)',uom,re.I)
            if m: multiplier=int(m[1]); normalized=qty*multiplier if qty is not None else None
            elif uom.upper() not in ('HR','HRS','HOUR','HOURS'): unit=''
        consistent=None if None in (normalized,price,amount) else abs(normalized*price-amount)<=TOL
        generic=bool(re.fullmatch(r'G-\d+|0+(?:-0+)+',code,re.I))
        eligible=bool(consistent is True and normalized>0 and price>0 and amount>0 and ((category in ('Parts','Labor') and code and unit and not generic) or (category=='Misc' and qty==1 and desc.upper() in ('SHOP SUPPLIES','WELD SUPPLIES','DOT INSPECTION'))))
        doc.items.append(LineItem(desc,pn,category,code=code,quantity=normalized,unit=unit,unit_price=price,amount=amount,price_source='printed Rate/Price' if price is not None else 'missing',comparison_eligible=eligible,amount_consistent=consistent,printed=dict(zip(HEADER,[typ,ln,code,desc,pos,uom,qty,price,amount]))))
        if consistent is not True: doc.warnings.append('Incomplete or inconsistent FleetPerform line arithmetic; review.')
    for pn,page in enumerate(pdf.pages,1):
        for table in page.find_tables():
            data=table.extract(); rows=[list(map(clean,r)) for r in data]
            if not rows: continue
            has_header=rows[0]==HEADER
            if has_header:
                if summary_started: doc.warnings.append('Detail table after summary; review.')
                seen=True
                grid_widths=[(c[0]/page.width,c[2]/page.width) for c in table.rows[0].cells if c is not None]
                detail_rows=rows[1:]
            elif seen and not summary_started and len(rows[0])==len(HEADER) and all(len(r)==len(HEADER) for r in rows) and rows[0][0] in TYPE:
                coords=[(c[0]/page.width,c[2]/page.width) for c in table.rows[0].cells if c is not None]
                if grid_widths is None or len(coords)!=len(grid_widths) or any(abs(a-c)>.015 or abs(b-d)>.015 for (a,b),(c,d) in zip(coords,grid_widths)):
                    doc.warnings.append(f'Unconfirmed continuation grid on page {pn}; review.'); continue
                detail_rows=rows
            else: continue
            for r in detail_rows:
                if r==HEADER: continue
                if len(r)!=9: doc.warnings.append('Unexpected column count in FleetPerform table.'); continue
                row(r,pn)
        for l in lines(page):
            m=SUMMARY.search(l.text)
            if m:
                summary_started=True; key=m[1].title(); doc.summary[key]=decimal(m[2]); doc.summary_pages[key]=pn
        # Known synthetic/demo text-only format has no ruled grid. Explicit column headers required.
        if not seen and pn==1 and re.search(r'fleet\s*perform',first,re.I):
            ls=lines(page); header=next((l for l in ls if l.text.startswith('Type Labor/Part Description Hrs/Qty UOM Rate/Price Ext Amt')),None)
            if header:
                seen=True
                bounds=[w['x0']-2 for w in header.words if w['text']!='Amt']+[page.width+1]
                for l in ls:
                    if l.top<=header.top: continue
                    cells=[' '.join(w['text'] for w in l.words if a<=w['x0']<b) for a,b in zip(bounds,bounds[1:])]
                    if len(cells)==7 and cells[0] in TYPE:
                        typ,code,desc,q,uom,rate,amt=cells; row([typ,'',code,desc,'',uom,q,rate,amt],pn)
    if not doc.items: doc.warnings.append('No recognized FleetPerform rows.')
    for cat,key in [('Parts','Total Parts'),('Labor','Total Labor'),('Misc','Special Charges')]:
        items=[i for i in doc.items if i.category==cat]
        check_delta(doc,key+' vs rows',doc.summary.get(key),sum((i.amount for i in items),Decimal(0)) if all(i.amount is not None for i in items) else None)
    keys=('Total Parts','Total Labor','Special Charges','Freight','Tax')
    check_delta(doc,'Printed economic summary',doc.summary.get('Estimate Total',doc.summary.get('Invoice Total')),sum((doc.summary[k] for k in keys),Decimal(0)) if all(k in doc.summary for k in keys) else None)
    if doc.warnings or any(v is None or abs(v)>TOL for v in doc.checks.values()):
        for i in doc.items: i.comparison_eligible=False
    if doc.vendor=="Atlantic Utility Trailer Sales":
        for i in doc.items: i.comparison_eligible=False
    return doc
