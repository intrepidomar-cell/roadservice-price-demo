"""Love's / Speedco Total Truck Care, eight-column digital work-order layout.
Preserves printed zeros, sparse rows, discounts, comments and original UOM.
No inferred hourly units, part codes, prices, or payment status.
"""
import re
from decimal import Decimal
from core.models import Invoice, LineItem
from core.pdf_utils import lines, decimal, field
from core.validation import check_delta, TOL

COLUMNS = ('Description','Mechanic','UOM','Quantity','List Price','Product','Labor','Extension')
HEADER = 'DESCRIPTION MECHANIC UOM QUANTITY LIST PRICE PRODUCT LABOR EXTENSION'
SUMMARY = ('Parts','Labor','Tires','Fees','Customer Discount','Site Discount','Tax','Total')


def matches(text):
    return 'TOTAL TRUCK CARE' in text.upper() and bool(re.search(r"Love.s Travel Stops",text,re.I))


def _cells(line, width):
    # The printed numeric columns are right-aligned; use their right edges.
    # Description/mechanic are left-aligned. Quantity-only tire components
    # can extend past the mechanic heading, so preserve their entire wording.
    bounds = [140,240,269,315,380,450,520,612]
    words=[[] for _ in bounds]
    for w in line.words:
        x=w['x0']*612/width
        k=next((i for i,b in enumerate(bounds) if x<b),7)
        words[k].append(w['text'])
    out=dict(zip(COLUMNS,(' '.join(w) for w in words)))
    if out['Quantity'] and not any(out[k] for k in ('UOM','List Price','Product','Labor','Extension')):
        out['Description']=' '.join(filter(None,[out['Description'],out['Mechanic']]))
        out['Mechanic']=''
    return out


def _append(previous, cells):
    for key in ('Description','Mechanic'):
        if cells[key]: previous[key]=' '.join(filter(None,[previous[key],cells[key]]))


def _summary_start(line,width):
    return line.words[0]['x0']/width>.70 and bool(re.match(r'^(Parts|Labor|Tires|Fees|Customer Discount|Site Discount|Tax|Total)\b',line.text,re.I))


def _summary(page_lines,width):
    result={}
    for i,line in enumerate(page_lines):
        if not _summary_start(line,width): continue
        m=re.match(r'^(Parts|Labor|Tires|Fees|Customer Discount\*?|Site Discount|Tax|Total)\s*(.*)$',line.text,re.I)
        if not m: continue
        key=next(k for k in SUMMARY if k.lower()==m[1].rstrip('*').lower())
        value=decimal(m[2])
        if value is None and i+1<len(page_lines):
            nxt=page_lines[i+1]
            if nxt.top-line.top<8 and nxt.words[0]['x0']/width>.80:
                value=decimal(nxt.text)
        if value is not None: result[key]=value
    return result


def _row(cells,page):
    desc=cells['Description']; q=decimal(cells['Quantity']); ext=decimal(cells['Extension']); product=decimal(cells['Product']); labor=decimal(cells['Labor']); lp=decimal(cells['List Price'])
    upper=desc.upper()
    if re.search(r'SUPPLIES|SURCHARGE|\bFEE\b|TIRE DISPOSAL',upper): category='Misc'
    elif 'LABOR' in upper: category='Labor'
    elif product is not None and product>0: category='Parts'
    elif 'TIRE' in upper or 'CASING' in upper or 'VANTAGE' in upper: category='Tires'
    elif 'VALVE STEM' in upper: category='Parts'
    else: category='Unclassified'
    # Misc total is comparable only as an explicitly printed positive charge.
    # List price is NOT necessarily the billed rate; don't match parts/labor
    # without independently established codes and comparable UOM semantics.
    consistent=None
    if q is not None and product is not None and labor is not None and ext is not None:
        consistent=abs(q*(product+labor)-ext)<=TOL
    # Tokens embedded in the Description are candidate identifiers, not
    # authoritative part numbers: the form has no dedicated part-number field.
    codes=[]
    if category in ('Parts','Tires'):
        for token in desc.split():
            if re.fullmatch(r'[A-Za-z0-9.-]{5,}',token) and re.search(r'\d',token) and not re.fullmatch(r'\d+(?:\.\d+)?',token):
                codes.append(token)
            elif re.fullmatch(r'\d{7,}',token): codes.append(token)
    printed_price=product if category=='Parts' and product is not None and product>0 else None
    return LineItem(desc,page,category,quantity=q,unit=cells['UOM'],amount=ext,
        unit_price=printed_price,price_source='printed Product column' if printed_price is not None else 'missing',code_candidates=codes,
        comparison_eligible=category=='Misc' and ext is not None and ext>0 and consistent is not False,
        amount_consistent=consistent,printed={**cells,'List Price':lp,'Product':product,'Labor':labor,'Quantity':q,'Extension':ext})


def read(pdf,path=None):
    doc=Invoice('loves_total_truck_care_v1',vendor="Love's / Speedco",pages=len(pdf.pages))
    texts=[p.extract_text(x_tolerance=1,y_tolerance=2) or '' for p in pdf.pages]
    first=texts[0]; full='\n'.join(texts)
    doc.document_type='estimate' if re.search(r'This is an Estimate',full,re.I) else 'unknown'
    shop= re.search(r'^\s*(\d{4})\s+([^\n]+?,\s*[A-Z]{2})\s+(TRUCKCARE|SPEEDCO)\b',first,re.M|re.I)
    if shop: doc.metadata.update({'Shop code':shop[1],'Location':shop[2],'Shop brand':shop[3]})
    for k,pat in {'Work order':r'WORK ORDER\s*#\s*:\s*(\d+)', 'Work order date':r'WORK ORDER DATE\s*:\s*(\d+/\d+/\d+)', 'Close date':r'CLOSE DATE\s*:[ \t]*(\d+/\d+/\d+)', 'Service type':r'SERVICE TYPE\s*:[ \t]*([^\n]+)', 'Account':r'ACCOUNT\s*#\s*:\s*(\d+)'}.items():
        v=field(first,pat)
        if v: doc.metadata[k]=v
    # Read each vehicle / authorization cell by the actual form's column positions.
    first_lines=lines(pdf.pages[0]); scale=612/pdf.pages[0].width
    groups=[('TRACTOR #',('Tractor number','VIN','Year','Make','Mileage','Plate / state','Engine'),(88,194,258,329,399,488,612)),
            ('TRAILER #',('Trailer number','Trailer VIN','Trailer year','Trailer make','Hubometer','Trailer plate / state','Reefer number'),(88,194,258,329,399,488,612)),
            ('APU# / HOURS',('APU / hours','Additional unit','Start time','End time','Driver name','Driver contact'),(100,210,300,390,485,612)),
            ('Authorization #',('Authorization number','Authorization name','Pay type','PO number','PO issued by','DR number'),(100,210,340,410,510,612))]
    for marker,names,bounds in groups:
        idx=next((n for n,l in enumerate(first_lines) if marker.lower() in l.text.lower()),None)
        if idx is None or idx+1>=len(first_lines): continue
        line=first_lines[idx+1]
        if not 7<line.top-first_lines[idx].top<24: continue
        cells=[[] for _ in names]
        for w in line.words:
            col=next((n for n,b in enumerate(bounds) if w['x0']*scale<b),len(names)-1)
            cells[col].append(w['text'])
        doc.metadata.update({k:' '.join(v) for k,v in zip(names,cells) if v})
    for pn,(page,text) in enumerate(zip(pdf.pages,texts),1):
        ls=lines(page); start=next((i for i,l in enumerate(ls) if l.text.upper()==HEADER),None)
        if start is not None:
            raw=[]
            for l in ls[start+1:]:
                if _summary_start(l,page.width) or re.match(r'^Unit\s*:',l.text,re.I):
                    if re.match(r'^Unit\s*:',l.text,re.I): doc.notes['Tire details']=l.text
                    break
                c=_cells(l,page.width)
                if any(c[k] for k in COLUMNS[2:]):
                    raw.append(c)
                elif raw and (c['Description'] or c['Mechanic']):
                    _append(raw[-1],c)
                elif c['Description'] or c['Mechanic']:
                    doc.warnings.append(f'Page {pn}: text before first detail row requires review.')
            doc.items.extend(_row(c,pn) for c in raw)
        summ=_summary(ls,page.width)
        for k,v in summ.items():
            if k in doc.summary and doc.summary[k]!=v: doc.warnings.append(f'Conflicting summary value: {k}.')
            doc.summary[k]=v
        complaint=re.search(r'^COMPLAINT\s*:\s*\n?(.*?)(?=\nDESCRIPTION MECHANIC|\nSERVICE COMMENTS:|\nWARRANTY NOTICE|\Z)',text,re.M|re.S|re.I)
        if complaint and complaint[1].strip(): doc.notes['Complaint']=complaint[1].strip()
        comments=re.search(r'SERVICE COMMENTS\s*:\s*(.*?)(?=\n\*+This is an Estimate|\nDriver Signature|\nWARRANTY NOTICE|\Z)',text,re.S|re.I)
        if comments: doc.notes['Service comments']=comments[1].strip()
        location=field(text,r'Service Location:\s*([+-]?\d+\.\d+,\s*[+-]?\d+\.\d+)')
        if location: doc.metadata['Service location']=location
    if not doc.items: doc.warnings.append('Eight-column detail table not found. No alternate parser executed.')
    missing=[k for k in SUMMARY if k not in doc.summary]
    if missing: doc.warnings.append('Missing summary fields: '+', '.join(missing))
    else:
        s=doc.summary; expected=s['Parts']+s['Labor']+s['Tires']+s['Fees']-s['Customer Discount']-s['Site Discount']+s['Tax']
        check_delta(doc,'Printed summary reconciliation',s['Total'],expected)
        # Extension already reflects some discounts; do not deduct twice.
        # Some fees (e.g. Fuel Surcharge) are printed in Labor AND Fees.
        known=sum((i.amount for i in doc.items if i.amount is not None),Decimal(0))
        check_delta(doc,'Printed total vs known extensions + tax',s['Total'],known+s['Tax'])
    sparse=sum(i.amount is None for i in doc.items)
    if sparse: doc.warnings.append(f'{sparse} detail row(s) without printed extension; preserved as missing, not zero.')
    if not doc.summary or any(v is None or abs(v)>TOL for v in doc.checks.values()) or missing:
        for item in doc.items: item.comparison_eligible=False
    if doc.items and all(i.amount in (None,Decimal(0)) for i in doc.items): doc.warnings.append('No positive printed charges; zero is not evidence of a free repair or a paid invoice.')
    if doc.document_type=='estimate': doc.warnings.append('Estimate only; not evidence of payment.')
    for i in doc.items:
        if i.amount_consistent is False: doc.warnings.append(f'Page {i.page}: {i.description}: quantity × printed Product/Labor differs from Extension.')
    # Explicitly show list-vs-extended differences for the document reviewer.
    return doc
