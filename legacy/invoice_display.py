"""Compact display for Laboratory 10 results.

Use as a view-only adapter: does not alter parser output, historical queries,
comparison candidates, or PDF originals. Numbered operation estimates display each description, detail table, and
Operation Total, followed by a single economic summary. Other formats retain
their Laboratory 10 tables in compact form.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from typing import Any

import pandas as pd
import streamlit as st

_MONEY = re.compile(r"[-+]?\$?\s*([\d,]+\.\d{2})")


def _amount(value: Any) -> Decimal | None:
    match = _MONEY.search(str(value or ""))
    if not match:
        return None
    try:
        return Decimal(match.group(1).replace(",", ""))
    except InvalidOperation:
        return None


def _money(value: Decimal | None) -> str:
    return f"${value:,.2f}" if value is not None else "—"


def _compact(df: Any) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame):
        return pd.DataFrame()
    # Streamlit displays null cells as blanks; preserving dtypes avoids
    # pandas 3.x downcasting warnings from replacing NaN with strings.
    return df.reset_index(drop=True).copy()


def _height(n: int, *, max_height: int = 720) -> int:
    # 35 px header + 35 px per row, avoiding the default 4-5 phantom rows.
    return min(max_height, max(72, 39 + max(n, 1) * 35))


def _dataframe(frame: pd.DataFrame, *, height: int | None = None) -> None:
    frame = _compact(frame)
    if frame.empty:
        st.caption("No extracted rows in this section.")
        return
    st.dataframe(frame, hide_index=True, use_container_width=True,
                 height=height or _height(len(frame)))


def _summary_map(result: dict) -> dict[str, Decimal]:
    raw = (result.get("resumen_final") or {}).get("datos")
    if not isinstance(raw, pd.DataFrame):
        return {}
    output = {}
    for _, row in raw.iterrows():
        key = str(row.get("Concepto", "")).strip().casefold()
        recognized = {"parts", "labor", "hookup", "shop supplies", "taxes", "core", "total"}
        # Some digital watermarks insert a stray letter in summary labels
        # (for example, EShop Supplies). Normalize only known concepts.
        if key not in recognized and key[:1] in "eatmis" and key[1:].strip() in recognized:
            key = key[1:].strip()
        value = _amount(row.get("Importe", ""))
        if key and value is not None:
            output[key] = value
    return output


def _operation_data(result: dict) -> list[dict]:
    """Existing numeric extraction is authoritative; metadata is optional."""
    metadata = {str(o.get("table_id", "")): o
                for o in (result.get("operaciones") or []) if isinstance(o, dict)}
    subtotals = {}
    for sub in result.get("subtablas") or []:
        if str(sub.get("tipo", "")) != "OPERATION_TOTAL":
            continue
        identifier = str(sub.get("id", ""))
        table_id = identifier.replace("operation-total-", "operation-", 1)
        df = _compact(sub.get("datos"))
        if not df.empty:
            subtotals[table_id] = _amount(df.iloc[0].get("Importe"))

    operations = []
    for table in result.get("tablas") or []:
        table_id = str(table.get("id", ""))
        if not table_id.startswith("operation-"):
            continue
        df = _compact(table.get("datos"))
        labor = Decimal("0")
        other = Decimal("0")
        parts = Decimal("0")
        for _, row in df.iterrows():
            val = _amount(row.get("Ext Amt", ""))
            if val is None:
                continue
            kind = str(row.get("Type", "")).upper()
            if kind == "L":
                labor += val
            elif kind == "P":
                parts += val
            else:
                other += val
        details = metadata.get(table_id, {})
        printed_parts_total = _amount(details.get("printed_parts_total"))
        parts_in_subtotal = max(parts, printed_parts_total or Decimal("0"))
        subtotal = subtotals.get(table_id)
        if subtotal is None:
            subtotal = labor + other + parts_in_subtotal
        operations.append({
            "id": table_id, "title": str(table.get("titulo") or "Operación"),
            "labor": labor, "other": other, "parts": parts_in_subtotal,
            "itemized_parts": parts,
            "subtotal": subtotal, "subtotal_is_printed": table_id in subtotals and subtotals[table_id] is not None,
            "difference": subtotal - labor - other - parts_in_subtotal,
            "details": details, "frame": df,
        })
    return operations


def _operation_table_with_total(operation: dict) -> pd.DataFrame:
    """Add the printed Operation Total to the operation's existing line-item table.

    This is display-only. The Lab 10 result, pricing candidates and original
    line items are not altered. If the printed total is missing, label the
    calculated sum clearly instead of presenting it as an extracted fact.
    """
    frame = _compact(operation["frame"])
    if frame.empty:
        frame = pd.DataFrame(columns=["Type", "Description", "Hrs/Qty",
                                      "UOM", "Rate/Price", "Ext Amt"])
    # Keep the operation's printed Parts subtotal directly next to its parts.
    # It is informational and NOT an additional charge or a second table.
    printed_parts = _amount(operation['details'].get('printed_parts_total'))
    if printed_parts is not None and any(str(t).upper() == 'P' for t in frame.get('Type', [])):
        part_row = {col: '' for col in frame.columns}
        part_row['Description'] = 'Parts Total (printed; not an additional charge)'
        part_row['Ext Amt'] = _money(printed_parts)
        frame = pd.concat([frame, pd.DataFrame([part_row])], ignore_index=True)
    total_label = ("Operation Total" if operation["subtotal_is_printed"]
                   else "Calculated subtotal (not printed)")
    total_row = {col: "" for col in frame.columns}
    total_row["Description"] = total_label
    total_row["Ext Amt"] = _money(operation["subtotal"])
    return pd.concat([frame, pd.DataFrame([total_row])], ignore_index=True)


def _show_operation_estimate(result: dict) -> None:
    """Operations with their descriptions and totals, then one final summary.

    Avoid the duplicated overview and separate subtotal tables for numbered
    operation estimates; keep the regular Lab 10 display for other formats.
    """
    operations = _operation_data(result)
    if not operations:
        st.warning("No operations detected.")
        return

    document = result.get('operation_document') or {}
    document_label = ' | '.join(str(v) for v in (
        document.get('shop'),
        ('Case ' + document['case_number']) if document.get('case_number') else '',
        document.get('estimate_version')) if v)
    if document_label:
        st.caption(document_label)
    st.markdown("**Operation details**")
    for operation in operations:
        # Each operation is a single coherent block: technical notes, one
        # line-item table and the operation total as its final row.
        st.markdown(f"**{operation['title']}**")
        if operation['details'].get('warranty'):
            st.caption('Warranty operation — use the printed extended charges, not reference rates.')
        details = operation["details"]
        for key, title in (("complaint", "Complaint"), ("cause", "Cause"),
                           ("correction", "Correction"),
                           ("parts_description", "Parts (printed description)")):
            value = str(details.get(key, "")).strip()
            if value:
                st.caption(f"{title}: {value}")

        frame = _operation_table_with_total(operation)
        _dataframe(frame)

        if not operation["subtotal_is_printed"]:
            st.warning("The PDF's Operation Total was not detected. "
                       "The displayed subtotal was calculated from extracted rows; "
                       "verify it against the original PDF.")
        if operation["parts"] > operation["itemized_parts"] + Decimal("0.02"):
            st.info("The operation has a printed Parts subtotal, but not all "
                    "parts have individual prices.")
        if operation["difference"] > Decimal("0.02"):
            st.warning(f"Operation Total includes {_money(operation['difference'])} "
                       "without an individually priced extracted line. "
                       "No unit prices or hours are inferred.")
        elif operation["difference"] < Decimal("-0.02"):
            st.warning("The extracted lines exceed the printed Operation Total. "
                       "Verify this operation against the original PDF.")

    # The sole monetary summary is shown last, as printed on the estimate.
    summary = _summary_map(result)
    if summary:
        operation_total = sum((o["subtotal"] for o in operations), Decimal("0"))
        if "total" in summary:
            # Operations already include their labor, priced parts and any
            # attached hookup. Do not count those charges twice.
            global_charges = sum((summary.get(k, Decimal("0"))
                                  for k in ("shop supplies", "taxes")), Decimal("0"))
            other_global = sum((amount for key, amount in summary.items()
                                if key not in {"parts", "labor", "hookup", "total",
                                               "shop supplies", "taxes", "core"}), Decimal("0"))
            direct = operation_total + global_charges + other_global
            with_core = direct + summary.get("core", Decimal("0"))
            if min(abs(direct - summary["total"]),
                   abs(with_core - summary["total"])) > Decimal("0.02"):
                st.warning("Extracted operation totals do not fully reconcile "
                           "to the printed estimate total. Verify the PDF.")

        rows = []
        labels = {"labor": "Labor", "parts": "Parts",
                  "hookup": "Computer Hookup", "shop supplies": "Shop Supplies",
                  "taxes": "Taxes", "core": "Core"}
        order = ("parts", "labor", "hookup", "shop supplies", "taxes", "core")
        for key in order:
            if key in summary:
                rows.append({"Concepto": labels[key], "Importe": _money(summary[key])})
        for key, val in summary.items():
            if key not in set(order) | {"total"}:
                rows.append({"Concepto": key.title(), "Importe": _money(val)})
        if "total" in summary:
            rows.append({"Concepto": "ESTIMATE TOTAL", "Importe": _money(summary["total"])})
        st.markdown("**Economic summary**")
        _dataframe(pd.DataFrame(rows))
    else:
        st.warning("No printed economic summary was detected. Verify the PDF.")


def _show_generic_l10(result: dict) -> None:
    tables = result.get("tablas") or []
    if not tables:
        st.warning("No main table detected in this PDF.")
    for i, table in enumerate(tables, 1):
        df = _compact(table.get("datos"))
        st.caption(f"Table {i} — {table.get('titulo') or 'Line items'}")
        _dataframe(df)
    summary = (result.get("resumen_final") or {}).get("datos")
    if isinstance(summary, pd.DataFrame) and not summary.empty:
        st.markdown("**Economic summary**")
        _dataframe(summary)
    extra = result.get("subtablas") or []
    charges = result.get("cargos_adicionales") or []
    if extra or charges:
        with st.expander("View subtotals and additional charges"):
            for i, table in enumerate(extra, 1):
                st.caption(f"Subtable {i} — {table.get('titulo') or ''}")
                _dataframe(table.get("datos"))
            for i, table in enumerate(charges, 1):
                st.caption(f"Additional charge {i}")
                _dataframe(table.get("datos"))


def show_invoice_tables(result: dict) -> None:
    """Public entrypoint. Safe to call wherever the old UI showed Lab10 tables."""
    if result.get("operation_fallback_used"):
        _show_operation_estimate(result)
    else:
        _show_generic_l10(result)
