"""Decisiv operation-based estimates from Freightliner Northwest / Gordon.
Digital letter-size layout. No legacy reader, OCR, network, or invented prices.
"""
from decimal import Decimal
from hashlib import sha256
import re
from core.models import Invoice, LineItem, Operation
from core.pdf_utils import lines, decimal, field
from core.validation import check_delta, TOL

HEADING = re.compile(r'^(\d{1,3})\s+([A-Z][A-Z0-9 /&.,()\'\-]+?)(\s*(?:\[[^\]]+\]\s*)*)$')
SUMMARY = re.compile(r'^(Parts|Labor|HOOKUP|Shop Supplies|Taxes|Core|Total)\s+(\$[\d,]+\.\d{2})$', re.I)
SUMMARY_NAMES = {s.lower():s for s in ('Parts','Labor','HOOKUP','Shop Supplies','Taxes','Core','Total')}
NOTE = re.compile(r'^(Complaint|Cause|Correction)\s*:', re.I)
VENDOR = re.compile(r'^(Freightliner Northwest|Gordon Truck Centers)\s+-\s+(.+)$', re.M)
MONEY = re.compile(r'^\$[\d,]+\.\d{2}$')
ZERO = Decimal('0')


def clean(text):
    return re.sub(r'\(cid:\d+\)', '', text).replace('\u00ad','').strip()


def words_text(words):
    return clean(' '.join(w['text'] for w in words))


def page_lines(page):
    # Large diagonal watermark is not document content.
    filtered = page.filter(lambda o: o.get('object_type') != 'char' or o.get('size',0)<25)
    return lines(filtered)


def fields(row):
    # Numeric columns are right-aligned; their left edges move with digit count.
    w=row.words
    return (words_text([x for x in w if 130<=x['x0']<400]),
            words_text([x for x in w if 400<=x['x0']<465]),
            words_text([x for x in w if 465<=x['x0']<530]),
            words_text([x for x in w if x['x0']>=530]))


def split_part(row):
    # In coded rows the description starts at x=204 and code at x=136.
    # Do not interpret model numbers embedded in an uncoded description as a code.
    left=[w for w in row.words if 130<=w['x0']<202]
    right=[w for w in row.words if 202<=w['x0']<400]
    code=words_text(left)
    if right and abs(right[0]['x0']-204)<2 and re.fullmatch(r'[A-Z0-9][A-Z0-9 -]*',code) and any(c.isdigit() for c in code):
        return code,words_text(right)
    return '',fields(row)[0]


def append_continuation(item,row,page):
    # Continuations follow the numbered row, not the preceding part's number.
    if item.code:
        code=words_text([w for w in row.words if 130<=w['x0']<202])
        desc=words_text([w for w in row.words if 202<=w['x0']<400])
        if code: item.code+=' '+code
    else:
        desc=fields(row)[0]
    if desc: item.description+=' '+desc
    item.printed['Part Number']=item.code
    item.printed['Description']=item.description
    item.printed['End page']=page


def item_from_row(op,row,page,category):
    desc,qty,price,ext=fields(row)
    code=''
    if category=='Parts': code,desc=split_part(row)
    elif category=='Labor': desc='LABOR — '+op.title; code=op.code
    elif category=='Misc': desc=desc or 'Additional Charges'
    quantity=decimal(qty); rate=decimal(price); amount=decimal(ext)
    consistent=None if None in (quantity,rate,amount) else abs(quantity*rate-amount)<=TOL
    # Only explicitly priced, positive, non-warranty fee totals can match today's SQL.
    # Part UOM and labor operation identity need homologation before unit comparisons.
    eligible=category=='Misc' and amount is not None and amount>0 and not op.warranty
    return LineItem(description=desc,page=page,category=category,code=code,quantity=quantity,
        unit='',unit_price=rate,amount=amount,price_source='printed' if rate is not None else 'missing',
        comparison_eligible=eligible,amount_consistent=consistent,
        operation=f'{op.number}. {op.title}',printed={'Type':category,'Part Number':code if category=='Parts' else '',
        'Description':desc,'Quantity':quantity if quantity is not None else qty,'Price':rate,'Totals':amount,
        'Warranty':op.warranty,'End page':page})


def metadata(doc, rows):
    text='\n'.join(clean(r.text) for r in rows)
    m=VENDOR.search(text)
    if m:
        doc.vendor=m[1];doc.metadata.update(shop=m[0],location=m[2])
    patterns={'case_number':r'Case Number:\s*(\S+)', 'repair_order':r'Repair Order Number:\s*(\S+)',
        'purchase_order':r'Purchase Order Number:\s*(\S+)', 'estimate_version':r'ESTIMATE VERSION\s+(\d+)',
        'updated_at':r'Updated at:\s*([^\n]+)', 'case_date':r'Case Date\s*([^\n]+)',
        'service_advisor':r'Service Advisor:\s*(.*?)\s*-\s*Case Date', 'etr':r'ETR:\s*([^\n]+)',
        'unit_number':r'Unit Number:\s*(\S+)', 'asset':r'Asset:\s*(.*?)(?:\s+Engine Hours:|$)',
        'serial_number':r'Serial Number:\s*(\S+)', 'vin':r'VIN:\s*(\S+)',
        'engine':r'Engine:\s*(.*?)(?:\s+In Service:|$)', 'engine_hours':r'Engine Hours:\s*(\S+)',
        'odometer':r'Odometer:\s*([^\n]+)', 'warranty_start':r'Warranty Start:\s*([^\n]+)',
        'in_service':r'In Service:\s*([^\n]+)', 'customer_number':r'Customer Number:\s*(\S+)'}
    doc.metadata.update({k:v for k,p in patterns.items() if (v:=field(text,p))})


def read(pdf,path):
    doc=Invoice('decisiv_estimate_v2',document_type='estimate',pages=len(pdf.pages))
    doc.metadata['source_sha256']=sha256(path.read_bytes()).hexdigest()
    op=None; state=''; note_key=None; last_part=None; final=False; notes=[]; notes_active=False
    for page_number,page in enumerate(pdf.pages,1):
        rows=page_lines(page)
        if page_number==1: metadata(doc,rows)
        if abs(page.width-612)>2 or abs(page.height-792)>2:
            doc.warnings.append(f'Page {page_number}: unsupported page dimensions; extraction withheld.')
            doc.items.clear();doc.operations.clear();doc.summary.clear();return doc
        body=[r for r in rows if (280 if page_number==1 else 160)<=r.top<750]
        for idx,row in enumerate(body):
            text=clean(row.text)
            if not text: continue
            if text.startswith('EXCLUSION OF WARRANTIES') or text.startswith('TERMS:'):
                notes_active=False; break
            if text.startswith('Notes:'):
                notes_active=True;final=True;continue
            if notes_active:
                notes.append(text);continue
            if final: continue
            summary=SUMMARY.fullmatch(text)
            if summary and (op is None or op.total is not None):
                key=SUMMARY_NAMES[summary[1].lower()]
                if key in doc.summary: doc.warnings.append(f'Duplicate summary key: {key}.')
                doc.summary[key]=decimal(summary[2]);doc.summary_pages[key]=page_number
                if key=='Total': final=True
                continue
            match=HEADING.fullmatch(text)
            if match and idx+1<len(body) and clean(body[idx+1].text).startswith('Complaint:'):
                number,title,suffix=match.groups(); tags=re.findall(r'\[([^\]]+)\]',suffix or '')
                op=Operation(int(number),title.strip(),next((t for t in tags if re.fullmatch(r'[\d-]+',t)),''),
                    'WARRANTY' in tags,page_number,page_number)
                doc.operations.append(op);state='';note_key=None;last_part=None;continue
            if op is None or op.total is not None: continue
            op.end_page=page_number
            if text.startswith('Quantity Price Totals'):
                state='table';note_key=None;continue
            if text.startswith('Operation Total:'):
                op.total=decimal(fields(row)[3]);state='';note_key=None;continue
            if text.startswith('Parts Total'):
                op.parts_total=decimal(fields(row)[3]);state='table';last_part=None;continue
            if text.startswith('Labor:'):
                doc.items.append(item_from_row(op,row,page_number,'Labor'));state='table';note_key=None;continue
            if text.startswith('Additional Charges:'):
                doc.items.append(item_from_row(op,row,page_number,'Misc'));state='table';note_key=None;continue
            if text.startswith('Parts:'):
                state='parts';note_key=None;last_part=None
                if not fields(row)[0]: continue
            if state=='parts':
                desc,qty,rate,ext=fields(row)
                if decimal(qty) is not None or MONEY.fullmatch(rate) or MONEY.fullmatch(ext):
                    last_part=item_from_row(op,row,page_number,'Parts');doc.items.append(last_part)
                elif last_part is not None: append_continuation(last_part,row,page_number)
                else: doc.warnings.append(f'Operation {op.number}: unassigned part text on page {page_number}.')
                continue
            label=NOTE.match(text)
            # Nested uppercase labels in a technician narrative remain narrative.
            if label and row.words[0]['x0']<100:
                note_key=label[1].lower();op.notes[note_key]=text[label.end():].strip();state='note'
            elif state=='note' and note_key: op.notes[note_key]+=' '+text
    if notes: doc.notes['Case notes']='\n'.join(notes)
    reconcile(doc)
    return doc


def reconcile(doc):
    for op in doc.operations:
        items=[i for i in doc.items if i.operation==f'{op.number}. {op.title}']
        parts=[i for i in items if i.category=='Parts']
        known=sum((i.amount for i in items if i.amount is not None),ZERO)
        known_parts=sum((i.amount for i in parts if i.amount is not None),ZERO)
        missing=any(i.amount is None for i in parts)
        if op.parts_total is not None:
            if missing:
                doc.warnings.append(f'Operation {op.number}: some part prices are not printed; only printed Parts Total is used for reconciliation.')
            else: check_delta(doc,f'Operation {op.number} parts',op.parts_total,known_parts)
            known+=op.parts_total-known_parts
        elif missing:
            doc.warnings.append(f'Operation {op.number}: part amounts and Parts Total not printed; itemized reconciliation unavailable.')
        other_missing=any(i.amount is None for i in items if i.category!='Parts')
        check_delta(doc,f'Operation {op.number} total',op.total,None if other_missing or (missing and op.parts_total is None) else known)
        for i in items:
            if i.amount_consistent is False:
                doc.warnings.append(f'Operation {op.number}: {i.description} printed quantity × price differs from extended amount; values preserved.')
    total=doc.summary.get('Total')
    check_delta(doc,'Printed economic summary',total,sum((v for k,v in doc.summary.items() if k!='Total'),ZERO) if total is not None else None)
    op_sum=sum((o.total for o in doc.operations if o.total is not None),ZERO)
    check_delta(doc,'Operations + shop supplies + taxes',total,op_sum+doc.summary.get('Shop Supplies',ZERO)+doc.summary.get('Taxes',ZERO) if doc.operations and all(o.total is not None for o in doc.operations) else None)
    labor=[i for i in doc.items if i.category=='Labor']
    if 'Labor' in doc.summary:
        check_delta(doc,'Printed labor vs line amounts',doc.summary['Labor'],sum((i.amount for i in labor),ZERO) if labor and all(i.amount is not None for i in labor) else None)
    # Core is already included in operation totals in this layout; never count twice.
    if 'Core' in doc.summary: doc.warnings.append('Core is a separate printed summary component; do not allocate it to a part or add it again to operation totals.')
    fee=doc.summary.get('Shop Supplies')
    if fee is not None:
        doc.items.append(LineItem('SHOP SUPPLIES',doc.summary_pages['Shop Supplies'],'Misc',amount=fee,
            comparison_eligible=fee>0,price_source='printed',operation='',printed={'Description':'SHOP SUPPLIES','Totals':fee}))
    if not doc.operations or total is None or any(o.total is None for o in doc.operations) or any(v is not None and abs(v)>TOL for v in doc.checks.values()):
        for i in doc.items: i.comparison_eligible=False
        doc.warnings.append('Document reconciliation failed or is incomplete: comparison disabled.')
    doc.warnings.append('Estimate only. Part UOM and labor comparison identity require homologation; no inferred unit prices or paid charges.')
