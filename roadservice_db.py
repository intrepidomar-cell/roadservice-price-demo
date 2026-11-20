"""Consultas de solo lectura al dataset ficticio; siempre se filtra por shop_id."""

import psycopg
from psycopg.rows import dict_row


def query(database_url: str, sql: str, args=()):
    # La URL se recibe del servidor Streamlit Secrets, nunca del navegador.
    with psycopg.connect(database_url, sslmode="require", connect_timeout=10, prepare_threshold=None) as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(sql, args)
            return cursor.fetchall()


def shops(database_url):
    return query(database_url, """
        SELECT s.shop_id, s.shop_code, s.shop_name, s.city, s.state_code,
               v.vendor_name
        FROM roadservice_demo.shops s
        JOIN roadservice_demo.vendors v ON v.vendor_id = s.vendor_id
        ORDER BY v.vendor_name, s.city, s.state_code
    """)


def catalog(database_url, shop_id: int):
    return query(database_url, """
        SELECT li.category, li.item_code, li.unit_of_measure,
               MIN(li.description_original) AS description,
               COUNT(*) AS observations
        FROM roadservice_demo.line_items li
        JOIN roadservice_demo.documents d ON d.document_id = li.document_id
        WHERE d.shop_id = %s
          AND d.document_type = 'invoice'
          AND d.validation_status = 'validated'
          AND d.currency_code = 'USD'
          AND li.category IN ('Parts', 'Labor', 'Misc')
        GROUP BY li.category, li.item_code, li.unit_of_measure
        ORDER BY li.category, li.item_code, li.unit_of_measure
    """, (shop_id,))


def history(database_url, shop_id: int, category: str, code: str, unit: str):
    return query(database_url, """
        SELECT d.issued_on AS invoice_date, d.document_number AS invoice_number,
               v.vendor_name, s.shop_name, s.city, s.state_code,
               li.category, li.item_code, li.description_original,
               li.quantity, li.unit_of_measure, li.unit_price,
               li.line_amount, li.task_job_label
        FROM roadservice_demo.line_items li
        JOIN roadservice_demo.documents d ON d.document_id = li.document_id
        JOIN roadservice_demo.shops s ON s.shop_id = d.shop_id
        JOIN roadservice_demo.vendors v ON v.vendor_id = s.vendor_id
        WHERE d.shop_id = %s
          AND d.document_type = 'invoice'
          AND d.validation_status = 'validated'
          AND d.currency_code = 'USD'
          AND li.category = %s
          AND li.item_code = %s
          AND li.unit_of_measure = %s
        ORDER BY d.issued_on DESC, d.document_number, li.line_item_id
    """, (shop_id, category, code, unit))
