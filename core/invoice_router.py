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
    'readers.gwm': (r'GWM Commercial Auto Glass', r'Invoice\s*#\s*\d+', r'Product/Service\s+Description\s+Qty\.\s+Unit Price\s+Total'),
    'readers.loves': (r'TOTAL TRUCK CARE', r'Love.s Travel Stops'),
    'readers.decisiv': (r'ESTIMATE VERSION\s+\d+', r'Complaint\s*:', r'Freightliner Northwest|Gordon Truck Centers'),
    'readers.fleetperform': (r'fleet\s*perform', r'Hrs\s*/\s*Qty'),
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
