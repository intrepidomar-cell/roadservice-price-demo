"""Recognize a known layout before importing/executing its specialized reader.
Signatures are cheap text checks; no parser trials and no automatic fallback.
"""
import re
from importlib import import_module
from pathlib import Path
import pdfplumber
from core.models import Invoice

# Format identification is centralized and independent of extraction.
# Add one signature and module path when a new layout is validated.
SIGNATURES = {
    'readers.baltimore': (r'BALTIMORE FREIGHTLINER', r'Service Order', r'Qty\s+Item\s+Description\s+Price\s+Extended'),
    'readers.atlantic_utility': (r'ATLANTICUTILITY\.COM', r'SERVICE (?:ESTIMATE|INVOICE):', r'QTY\s+ITEM\s+DESCRIPTION\s+UNIT PRICE\s+EXTD PRICE'),
    'readers.ascendance': (r'Ascendance Trucks Eastern Iowa,', r'SERVICE ORDER:', r'STATUS\s+QTY\s+ITEM\s+DESCRIPTION\s+UNIT PRICE\s+EXTD PRICE'),
    'readers.amoretti': (r'Amoretti Diesel Repair and Service|Amoretti Diesel Repair and\s+(?:Invoice:.*\n\s*)?Service', r'Invoice:\s*\S+', r'Item\s+Description\s+Quantity\s+Rate\s+Amount', r'Complaint:'),
    'readers.albuquerque': (r'Albuquerque Freightliner', r'SERVICE ORDER:', r'STATUS\s+QTY\s+ITEM\s+DESCRIPTION\s+UNIT PRICE\s+EXTD PRICE'),
    'readers.affordable_diesel': (r'Affordable Diesel Repair, Inc\.', r'INVOICE #', r'ACTIVITY\s+QTY\s+RATE\s+AMOUNT'),
    'readers.texas_towing': (r'TEXAS TOWING WRECKER SERVICE INC\.', r'TOW INVOICE', r'TOW CHARGE DESCRIPTION\s+QTY\s+RATE\s+AMOUNT'),
    'readers.towbook': (r"Candido.s Towing & Repair|B&W Wrecker Service|Stauffer.s Road Solutions|A1 Wrecker & Diesel Services LLC|Arrow Towing, Inc\.|Bains Towing & Recovery, LLC\.", r'Invoice\s*#', r'Charge Descrip(?:ti|\x00)on\s+Quan(?:ti|\x00)ty\s+Price\s+Line Total', r'Towbook Management Software'),
    'readers.bj_trailer': (r'B\.J\. Trailer & Truck Repair', r'DESCRIPTION\s+HRS/QTY\s+RATE/PRICE\s+AMOUNT'),
    'readers.tom_nehl': (r'Customer Review|Invoice Total:', r'Fleet Boost', r'TOM NEHL TRUCK COMPANY', r'Task:\s*\d+'),
    'readers.gregorys': (r"GREGORY.S TRAILER AND", r"TRUCK SERVICE", r"Item\s+Description\s+Quantity\s+Rate\s+Amount"),
    'readers.ocala': (r"OCALA FREIGHTLINER", r"SERVICE (?:ORDER|INVOICE):", r"Sold Operations|Estimate Operations|Rejected Operations"),
    'readers.a_mobile_maintenance': (r'A Mobile Maintenance', r'Invoice\s*#', r'Quantity\s+Item Code\s+Description\s+Price Each\s+Amount'),
    'readers.battleground_wrecker': (r'Battleground Wrecker', r'Invoice\s*#', r'Charge Description\s+Quantity\s+Price\s+Line Total'),
    'readers.gwm': (r'GWM Commercial Auto Glass', r'Invoice\s*#\s*\d+', r'Product/Service\s+Description\s+Qty\.\s+Unit Price\s+Total'),
    'readers.loves': (r'TOTAL TRUCK CARE', r'Love.s Travel Stops'),
    'readers.decisiv': (r'ESTIMATE VERSION\s+\d+', r'Complaint\s*:', r'Freightliner Northwest|Gordon Truck Centers'),
    'readers.fleet_repair_solutions': (r'Fleet Repair Solutions\s*-', r'Item\s+Description\s+Quantity\s+Rate\s+Amount', r'Concern:'),
    'readers.fleetperform': (r'Hrs\s*/\s*Qty', r'Labor/Part', r'(?:fleet\s*perform|FLEET REPAIR SOLNS-|Position Codes\s+UOM)'),
}
MAX_PDF_BYTES=15*1024*1024
MAX_PAGES=25


def read_invoice(path):
    path=Path(path)
    if path.stat().st_size>MAX_PDF_BYTES: raise ValueError('PDF exceeds 15 MB.')
    with path.open('rb') as f:
        if f.read(5)!=b'%PDF-': raise ValueError('Invalid PDF header.')
    with pdfplumber.open(path) as pdf:
        if not pdf.pages: raise ValueError('Empty PDF.')
        if len(pdf.pages)>MAX_PAGES: raise ValueError('PDF exceeds 25 pages.')
        # Only inspect two pages for signatures. No full extraction until matched.
        text='\n'.join(p.extract_text() or '' for p in pdf.pages[:2])
        candidates=[module for module,patterns in SIGNATURES.items() if all(re.search(p,text,re.I) for p in patterns)]
        if len(candidates)!=1:
            warning='Ambiguous format; no reader executed.' if candidates else 'Unsupported format or no digital text; no reader executed.'
            return Invoice('unsupported',pages=len(pdf.pages),warnings=[warning])
        return import_module(candidates[0]).read(pdf,path)
