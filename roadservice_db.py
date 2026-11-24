"""Parameterized read-only historical queries."""
import psycopg
from psycopg.rows import dict_row

def query(database_url: str, sql: str, args=()):
    with psycopg.connect(
        database_url, sslmode="require", connect_timeout=10, prepare_threshold=None
    ) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, args)
            return cur.fetchall()


def shops(database_url: str):
    return query(database_url, """
        SELECT s.shop_id, s.shop_code, s.shop_name, s.city, s.state_code,
               v.vendor_id, v.vendor_name
        FROM roadservice_demo.shops s
        JOIN roadservice_demo.vendors v ON v.vendor_id = s.vendor_id
        ORDER BY v.vendor_name, s.city, s.state_code
    """)


def shops_with_prices_for_item(database_url: str, item: dict):
    """Return only vendor locations with validated historical matches for this item.

    The WHERE rules mirror historical_prices() so selecting a vendor/location
    never leads to an empty result just because the shop has no comparable item.
    """
    import re
    category = item.get('category')
    if category not in ('Parts', 'Labor', 'Misc'):
        return []
    sql = """
        SELECT s.shop_id, s.shop_code, s.shop_name, s.city, s.state_code,
               v.vendor_id, v.vendor_name, COUNT(*)::integer AS match_count
        FROM roadservice_demo.line_items li
        JOIN roadservice_demo.documents d ON d.document_id = li.document_id
        JOIN roadservice_demo.shops s ON s.shop_id = d.shop_id
        JOIN roadservice_demo.vendors v ON v.vendor_id = s.vendor_id
        WHERE d.document_type = 'invoice'
          AND d.validation_status = 'validated'
          AND d.currency_code = 'USD'
          AND li.category = %s
    """
    args = [category]
    if category == 'Misc':
        normalized = re.sub(r'[^A-Z0-9]', '', (item.get('description') or '').upper())
        if not normalized or item.get('amount') is None:
            return []
        sql += """
          AND li.line_amount > 0
          AND UPPER(REGEXP_REPLACE(li.description_original, '[^A-Za-z0-9]', '', 'g')) = %s
        """
        args.append(normalized)
    else:
        code = (item.get('code') or '').strip().upper()
        unit = (item.get('unit') or '').strip().upper()
        if not code or not unit or item.get('unit_price') is None:
            return []
        sql += """
          AND li.unit_price > 0
          AND UPPER(TRIM(li.item_code)) = %s
          AND UPPER(TRIM(li.unit_of_measure)) = %s
        """
        args.extend([code, unit])
    sql += """
        GROUP BY s.shop_id, s.shop_code, s.shop_name, s.city, s.state_code,
                 v.vendor_id, v.vendor_name
        ORDER BY v.vendor_name, s.city, s.state_code
    """
    return query(database_url, sql, tuple(args))


def historical_prices(database_url: str, vendor_id: int, selected_shop_ids: list[int], item: dict):
    """Find same-vendor historical invoice lines matching a particular parsed item.

    Parts and Labor require exact code and UOM. Misc charge rows (e.g. SHOP SUPPLIES)
    lack a code in the source PDF; use exact normalized category+description and
    compare printed line amounts. No fuzzy matching or cross-vendor fallback.
    """
    if not selected_shop_ids or not item.get('category') in ('Parts', 'Labor', 'Misc'):
        return []
    common = """
        SELECT d.document_id, d.document_number, d.issued_on,
               d.original_pdf_url, d.original_file_sha256,
               s.shop_id, s.shop_name, s.city, s.state_code,
               v.vendor_name, li.category, li.item_code,
               li.description_original, li.quantity, li.unit_of_measure,
               li.unit_price, li.line_amount, li.line_number
        FROM roadservice_demo.line_items li
        JOIN roadservice_demo.documents d ON d.document_id = li.document_id
        JOIN roadservice_demo.shops s ON s.shop_id = d.shop_id
        JOIN roadservice_demo.vendors v ON v.vendor_id = s.vendor_id
        WHERE v.vendor_id = %s
          AND s.shop_id = ANY(%s::bigint[])
          AND d.document_type = 'invoice'
          AND d.validation_status = 'validated'
          AND d.currency_code = 'USD'
          AND li.category = %s
    """
    args = [vendor_id, selected_shop_ids, item['category']]
    if item['category'] == 'Misc':
        # The PDF typically has no part code for fees. Avoid invented codes.
        # Exact normalised-description matching, not a substring fuzzy match.
        import re
        description = re.sub(r'[^A-Z0-9]', '', (item.get('description') or '').upper())
        if not description or item.get('amount') is None:
            return []
        common += """
          AND li.line_amount > 0
          AND UPPER(REGEXP_REPLACE(li.description_original, '[^A-Za-z0-9]', '', 'g')) = %s
        """
        args.append(description)
        common += ' ORDER BY li.line_amount DESC, d.issued_on DESC, d.document_number DESC'
    else:
        code, unit = (item.get('code') or '').strip().upper(), (item.get('unit') or '').strip().upper()
        if not code or not unit or item.get('unit_price') is None:
            return []
        common += """
          AND li.unit_price > 0
          AND UPPER(TRIM(li.item_code)) = %s
          AND UPPER(TRIM(li.unit_of_measure)) = %s
        """
        args.extend((code, unit))
        common += ' ORDER BY li.unit_price DESC, d.issued_on DESC, d.document_number DESC'
    return query(database_url, common, tuple(args))
