"""Non-destructive cross-check: live Lab 10 extraction versus synthetic SQL seed.

Only compares Parts and Labor by category, code, normalized UOM, price, and
quantity. No inference of equivalence and no automatic database writes.
"""
from collections import Counter
from decimal import Decimal, InvalidOperation


def _decimal(value):
    try:
        return Decimal(str(value)).quantize(Decimal('0.01'))
    except (TypeError, ValueError, InvalidOperation):
        return None


def _key(category, code, uom, qty, price):
    return (str(category).strip().upper(), str(code).strip().upper(),
            str(uom).strip().upper(), _decimal(qty), _decimal(price))


def reconcile_extracted_with_sql(candidates, sql_lines):
    """Return #matches and unmatched source rows; no writes or deduplication."""
    found = Counter(
        _key(r.get('category'), r.get('item_code'), r.get('unit_of_measure'),
             r.get('quantity'), r.get('unit_price'))
        for r in sql_lines if r.get('category') in ('Parts', 'Labor')
    )
    total = sum(found.values())
    matches = 0
    unmatched_extracted = []
    for row in candidates:
        if row.get('category') not in ('Parts', 'Labor') or not row.get('code'):
            continue
        k = _key(row.get('category'), row.get('code'), row.get('unit'),
                 row.get('quantity'), row.get('unit_price'))
        if found[k]:
            matches += 1
            found[k] -= 1
        else:
            unmatched_extracted.append(row.get('row_id', '(unknown)'))
    return {'matches': matches, 'sql_total': total,
            'unmatched_sql': sum(found.values()),
            'unmatched_extracted': unmatched_extracted}
