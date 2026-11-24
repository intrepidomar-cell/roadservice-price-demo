"""Bridge for the previously implemented readers during migration.
New readers must return Invoice directly, without depending on this module.
"""
from core.models import Invoice, LineItem
from core.pdf_utils import decimal
from legacy.extracted_items import extract_candidates


def adapt(result, reader, vendor, pages, document_type='unknown'):
    doc=Invoice(reader,vendor,document_type,pages=pages,legacy_result=result)
    doc.warnings=list(result.get('avisos') or [])
    doc.metadata={k:str(v) for k,v in (result.get('operation_document') or {}).items() if v}
    for c in extract_candidates(result):
        p=c.get('unit_price'); a=c.get('amount'); cat=c['category']
        eligible=(cat=='Misc' and a is not None and a>0) or (cat in ('Parts','Labor') and p is not None and p>0 and bool(c['code'] and c['unit']) and c.get('price_source')=='printed' and c.get('amount_consistent') is True and a is not None and a>0)
        raw=c['raw_row']; pg=raw.get('pagina')
        try: pg=int(pg) if pg is not None else None
        except (ValueError,TypeError): pg=None
        doc.items.append(LineItem(c['description'],pg,cat,c['code'],c['quantity'],c['unit'],p if c.get('price_source')=='printed' else None,a,c['price_source'],eligible,c.get('amount_consistent'),raw,c['job']))
    summary=(result.get('resumen_final') or {}).get('datos')
    if summary is not None:
        for _,row in summary.iterrows():
            v=decimal(row.get('Importe'))
            if v is not None: doc.summary[str(row.get('Concepto'))]=v
    return doc
