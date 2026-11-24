"""Temporary compatibility reader for the known FleetPerform layout.
Uses existing L10 extraction ONLY after explicit FleetPerform identification.
Replace with a dedicated parser after regression fixtures are available.
"""
import re
from core.legacy_adapter import adapt


def matches(text):
    return bool(re.search(r'fleet\s*perform',text,re.I)) and bool(re.search(r'Hrs\s*/\s*Qty',text,re.I))


def read(pdf,path):
    from legacy.invoice_reader_l10 import leer_invoice
    result=leer_invoice(path)
    doc=adapt(result,'fleetperform_compat_l10', 'FleetPerform',len(pdf.pages))
    if not doc.items: doc.warnings.append('FleetPerform layout recognized, but no detail rows were extracted.')
    doc.warnings.append('Transitional compatibility reader; dedicated extraction pending regression samples.')
    return doc
