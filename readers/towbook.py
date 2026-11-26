"""Explicitly recognized Towbook vendors sharing the Battleground layout."""
import re
from readers.battleground_wrecker import read as read_layout
from core.models import Invoice
from core.pdf_utils import lines

VENDORS=("Candido's Towing & Repair", 'B&W Wrecker Service', "Stauffer's Road Solutions", "A1 Wrecker & Diesel Services LLC", "Arrow Towing, Inc.", "Bains Towing & Recovery, LLC.")

def read(pdf,path=None):
    text=pdf.pages[0].extract_text() or ''
    matches=[v for v in VENDORS if re.search(re.escape(v),text,re.I)]
    if len(matches)!=1:
        return Invoice('unsupported',pages=len(pdf.pages),warnings=['Towbook vendor ambiguous.'])
    doc=read_layout(pdf,path,vendor=matches[0],reader='towbook_v1')
    if matches[0]=='Arrow Towing, Inc.':
        _arrow_metadata(pdf.pages[0],doc)
    if matches[0]=="Bains Towing & Recovery, LLC.":
        m=re.search(r"Service Location\s+([^\n]+)",text,re.I)
        if m: doc.metadata["Service location"]=m[1].strip()
        for item in doc.items:
            if item.description.casefold() in {"call out", "fuel surcharge"}:
                item.category="Misc"; item.unit="EA" if item.quantity==1 else ""
            item.comparison_eligible=False
    return doc


def _arrow_metadata(page,doc):
    # Identical economic grid; only Arrow's multi-vehicle header is adapted.
    ls=lines(page)
    idx=next((n for n,l in enumerate(ls) if l.text.startswith('Year Make Model Color VIN Plate')),None)
    if idx is not None:
        anchors=[(w['text'],w['x0']) for w in ls[idx].words if w['text'] in ('Year','Make','Model','Color','VIN','Plate','Odometer','Unit')]
        count=0
        for l in ls[idx+1:]:
            if l.text.startswith('Charge Description'): break
            if not re.match(r'^\d{4}\s',l.text): continue
            count+=1
            if count==1: continue  # first vehicle already retained
            for j,(k,x) in enumerate(anchors):
                end=anchors[j+1][1]-2 if j+1<len(anchors) else page.width
                val=' '.join(w['text'] for w in l.words if x-2<=w['x0']<end)
                if val: doc.metadata[f'Vehicle {count} {k}']=val
        if count: doc.metadata['Vehicle count']=str(count)
        if count>1: doc.warnings.append('Multiple vehicles on one invoice; charges are not allocated by vehicle.')
    for item in doc.items:
        if item.description.casefold() in {'heavy duty - wrecker tow','heavy duty - shag tow'}:
            item.category='Misc'  # no hourly/mileage rate basis printed
        item.comparison_eligible=False
