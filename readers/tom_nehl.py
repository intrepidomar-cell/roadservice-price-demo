"""Tom Nehl Fleet Boost Customer Review: task details and printed financial totals."""
import hashlib,re
from decimal import Decimal
from core.models import Invoice,LineItem,Operation
from core.pdf_utils import lines,decimal
from core.validation import check_delta,TOL

# Exact embedded Lake City header image fingerprint, verified against the visible logo.
LAKE_CITY_HEADER='905e8daf09635ff187c798577cde5325637d8961644ca16981145c22ea589b90'
SUMMARY=re.compile(r'(Total Parts|Total Core Chg|Total Core Ret|Total EHC|Total Labor|Total Miscellaneous|Total Shop Supplies|Invoice Subtotal|Total Tax|Invoiced Total):\s*([\-$\d,.]+)$')

def read(pdf,path=None):
    d=Invoice('tom_nehl_v1',vendor='Tom Nehl Truck Company',document_type='estimate',pages=len(pdf.pages))
    if path: d.metadata['Source SHA-256']=hashlib.sha256(path.read_bytes()).hexdigest()
    if any(hashlib.sha256(i['stream'].get_data()).hexdigest()==LAKE_CITY_HEADER for i in pdf.pages[0].images):
        d.metadata.update({'Shop':'Tom Nehl Lake City, Inc.','Vendor location':'Lake City, FL'})
    d.metadata['Printed document type']='Customer Review / Estimated'
    op=None; table=False; pending=None; labor_by_task={}; header_total=None; note_mode=None
    for pn,page in enumerate(pdf.pages,1):
        # Large watermark glyphs overlap the digital text; discard only those glyphs.
        p=page.filter(lambda obj: obj.get('object_type')!='char' or not (obj.get('size',0)>40 and 'BoldItalic' in obj.get('fontname','')))
        ls=lines(p)
        for idx,l in enumerate(ls):
            t=l.text
            for key in ('Date / Time','Repair Order','Customer','Branch','Invoice Total'):
                if t.startswith(key+':'):
                    v=t.split(':',1)[1].strip()
                    if key=='Invoice Total': header_total=decimal(v)
                    else: d.metadata[key]=v
            if t.startswith('Customer P/O Created By') and idx+1<len(ls):
                vals=ls[idx+1].text.split();
                if vals: d.metadata['Customer PO']=vals[0]
                if len(vals)>1: d.metadata['Created by']=vals[1]
            if t.startswith('REF #'): d.metadata['Reference #']=t.split(':',1)[-1].strip().removeprefix('REF # ').strip()
            if t.startswith('Unit Number:'):
                m=re.match(r'Unit Number:\s*(.*?)\s+Model Year:\s*(.*?)\s+Make/Model:\s*(.*)',t)
                if m: d.metadata.update({'Unit number':m[1],'Model year':m[2],'Make/Model':m[3]})
            if t.startswith('Type:') and 'VIN:' in t:
                m=re.search(r'Type:\s*(.*?)\s+VIN:\s*(.*?)\s+Meter:\s*(.*)',t)
                if m:d.metadata.update({'Vehicle type':m[1],'VIN':m[2],'Meter':m[3]})
            sm=SUMMARY.search(t)
            if sm:
                d.summary[sm[1]]=decimal(sm[2]);d.summary_pages[sm[1]]=pn;table=False;pending=None;continue
            m=re.match(r'Task:\s*(\d+)\s+(.*?)\s+Department:\s*(.*)',t)
            if m:
                title=' '.join(w['text'] for w in l.words if 155<=w['x0']<450) or m[2]
                code=' '.join(w['text'] for w in l.words if 65<=w['x0']<155)
                op=Operation(int(m[1]),title,code=code,page=pn,notes={'Department':m[3],'total label':'Task Total'});d.operations.append(op);table=False;pending=None;note_mode=None;continue
            if op is None: continue
            m=re.fullmatch(r'Task\s+(\d+)\s+Subtotals:\s+Parts:\s+([\-$\d,.]+)',t)
            if m:
                op.parts_total=decimal(m[2]);table=False;pending=None;continue
            m=re.fullmatch(r'Labor:\s+([\-$\d,.]+)',t)
            if m and op.parts_total is not None and op.total is None:
                labor_by_task[op.number]=decimal(m[1]);continue
            m=re.fullmatch(r'Task\s+(\d+)\s+Totals:\s+([\-$\d,.]+)',t)
            if m:
                op.total=decimal(m[2]);op.end_page=pn;table=False;pending=None;continue
            if t.startswith('Supp. Part Description / Ref Number'):
                table=True;pending=None;note_mode=None;continue
            if t.startswith('Complaint:') or t.startswith('Correction:'):
                note_mode=t.split(':',1)[0].casefold();op.notes[note_mode]=t.split(':',1)[1].strip();continue
            if not table and note_mode and op.total is None:
                op.notes[note_mode]+=' '+t;continue
            if not table: continue
            cells=[' '.join(w['text'] for w in l.words if a<=w['x0']<b) for a,b in [(0,65),(65,205),(205,330),(330,390),(390,425),(425,490),(490,560),(560,612)]]
            supplier,code,desc,kind,unit,q,r,a=cells
            qty,rate,amount=map(decimal,(q,r,a))
            if amount is not None and supplier and code and desc:
                consistent=None if qty is None or rate is None else abs(qty*rate-amount)<=TOL
                if consistent is not True:d.warnings.append('Missing or inconsistent task row amount.')
                pending=LineItem(desc,pn,'Parts',code=code,quantity=qty,unit=unit,unit_price=rate,amount=amount,price_source='printed Price',amount_consistent=consistent,operation=f'{op.number}. {op.title}',printed={'Supp.':supplier,'Part':code,'Description':desc,'Type':kind,'U/M':unit,'Quantity':qty,'Price':rate,'Ext Price':amount,'Details':''})
                d.items.append(pending)
            elif pending is not None and not any((qty,rate,amount)):
                pending.printed['Details']=' '.join(filter(None,[pending.printed['Details'],t]))
            else:d.warnings.append('Unassigned task detail; review.')
    for op in d.operations:
        subset=[i for i in d.items if i.operation==f'{op.number}. {op.title}']
        check_delta(d,f'Task {op.number} parts vs rows',op.parts_total,sum((i.amount for i in subset if i.amount is not None),Decimal(0)))
        labor=labor_by_task.get(op.number)
        check_delta(d,f'Task {op.number} total vs parts and labor',op.total,op.parts_total+labor if op.parts_total is not None and labor is not None else None)
        if labor is not None:
            d.items.append(LineItem('Labor subtotal (no individual rate printed)',op.end_page,'Labor',amount=labor,operation=f'{op.number}. {op.title}',printed={'Description':'Labor subtotal (no individual rate printed)','Ext Price':labor}))
    def s(k):return d.summary.get(k)
    def add(keys):return sum((s(k) for k in keys),Decimal(0)) if all(s(k) is not None for k in keys) else None
    check_delta(d,'Parts summary vs tasks',s('Total Parts'),sum((op.parts_total for op in d.operations if op.parts_total is not None),Decimal(0)) if d.operations and all(op.parts_total is not None for op in d.operations) else None)
    check_delta(d,'Labor summary vs tasks',s('Total Labor'),sum(labor_by_task.values(),Decimal(0)) if len(labor_by_task)==len(d.operations) else None)
    keys=('Total Parts','Total Core Chg','Total Core Ret','Total EHC','Total Labor','Total Miscellaneous','Total Shop Supplies')
    check_delta(d,'Invoice subtotal vs summary',s('Invoice Subtotal'),add(keys))
    check_delta(d,'Invoiced total vs subtotal and tax',s('Invoiced Total'),add(('Invoice Subtotal','Total Tax')))
    check_delta(d,'Header total vs summary',header_total,s('Invoiced Total'))
    d.warnings.append('Customer Review is not a final invoice; labor subtotals do not establish hours or rates. Freight is included in printed parts subtotal. No automatic comparison candidates for this estimate.')
    return d
