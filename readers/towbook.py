"""Explicitly recognized Towbook vendors sharing the Battleground layout."""
import re
from readers.battleground_wrecker import read as read_layout
from core.models import Invoice

VENDORS=("Candido's Towing & Repair", 'B&W Wrecker Service', "Stauffer's Road Solutions", "A1 Wrecker & Diesel Services LLC")

def read(pdf,path=None):
    text=pdf.pages[0].extract_text() or ''
    matches=[v for v in VENDORS if re.search(re.escape(v),text,re.I)]
    if len(matches)!=1:
        return Invoice('unsupported',pages=len(pdf.pages),warnings=['Towbook vendor ambiguous.'])
    return read_layout(pdf,path,vendor=matches[0],reader='towbook_v1')
