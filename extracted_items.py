"""Vista orientativa de partidas a partir de las tablas originales del Laboratorio 10.

No altera ni reescribe los datos de extracción. No garantiza equivalencia de partes,
ni asigna valores por omisión cuando falta evidencia.
"""

import re
from decimal import Decimal, InvalidOperation

import pandas as pd


def _simplify(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _field(row, *, exact=(), contains=()):
    """Obtiene una celda por el encabezado impreso (nunca por posición arbitraria)."""
    cols = {str(k): _simplify(k) for k in row}
    for key, normal in cols.items():
        if normal in exact and pd.notna(row[key]) and str(row[key]).strip():
            return str(row[key]).strip()
    for key, normal in cols.items():
        if any(t in normal for t in contains) and pd.notna(row[key]) and str(row[key]).strip():
            return str(row[key]).strip()
    return ""


def money(v):
    s = str(v or "").strip().replace(",", "").replace("$", "")
    if not s or s in {"—", "-"}:
        return None
    negative = s.startswith("(") and s.endswith(")")
    if negative:
        s = s[1:-1]
    try:
        d = Decimal(s)
        if not d.is_finite():
            return None
        return -d if negative else d
    except InvalidOperation:
        return None


def extract_candidates(result):
    """Produce candidatos a comparar preservando los valores crudos originales.

    Solo se extraen tarifas de columnas de precio explícitas, o se calcula el
    unitario cuando aparecen cantidad y total claramente impresos. Un candidato
    incompleto se muestra pero NO es comparable automáticamente.
    """
    candidates = []
    sections = result.get("partidas_seccionadas_l09")
    section_by_row = {}
    if isinstance(sections, pd.DataFrame) and not sections.empty:
        for _, r in sections.iterrows():
            try:
                section_by_row[(str(r.get("tabla_id")), int(r.get("fila")))] = str(r.get("Seccion", ""))
            except (TypeError, ValueError):
                continue

    for tab in result.get("tablas", []):
        df = tab.get("datos")
        if not isinstance(df, pd.DataFrame) or df.empty:
            continue
        table_id = str(tab.get("id", ""))
        for position, (_, rowdata) in enumerate(df.iterrows(), start=1):
            row = rowdata.to_dict()
            desc = _field(row, exact=("descripcion", "description", "itemdescription", "concepto", "laborperformedpartsusedforrepairs"), contains=("description", "descripcion"))
            code = _field(row, exact=("partnumber", "partno", "part", "itemnumber", "itemno", "refnumber", "sku", "code"), contains=("partnumber", "itemnumber", "refnumber"))
            qty_text = _field(row, exact=("qty", "quantity", "hours", "laborhours", "salesqty", "qtyhours", "labortimepartsqty"))
            unit = _field(row, exact=("uom", "um", "unitofmeasure", "unit", "units", "measure"))
            rate_text = _field(row, exact=("unitprice", "unitrate", "rate", "price"))
            total_text = _field(row, exact=("amount", "totalcost", "total", "totals", "extendedprice", "extprice", "extdprice", "extension", "extamount", "extamt"))
            qty = money(qty_text)
            unit_price = money(rate_text)
            total = money(total_text)
            price_source = "printed" if unit_price is not None else "missing"
            if unit_price is None and qty is not None and qty > 0 and total is not None:
                unit_price = total / qty
                price_source = "derived_from_total_and_quantity"
            section = section_by_row.get((table_id, position), "")
            classify_text = " ".join([section, desc]).lower()
            if re.search(r"\blabor\b|\blabour\b", classify_text):
                category = "Labor"
            elif re.search(r"\bpart(s)?\b", classify_text):
                category = "Parts"
            elif re.search(r"\bmisc\b", classify_text):
                category = "Misc"
            else:
                category = "Unclassified"
            if not desc:
                desc = str(tab.get("titulo") or "Partida sin descripción reconocida")
            candidates.append({
                "row_id": f"{table_id}:{position}",
                "table": table_id, "job": str(tab.get("titulo") or ""),
                "description": desc, "code": code.strip(), "category": category,
                "quantity": qty, "unit": unit.strip().upper(), "unit_price": unit_price,
                "amount": total, "price_source": price_source,
                "raw_row": row,
            })
    return candidates
