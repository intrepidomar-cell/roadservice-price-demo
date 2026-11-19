"""Cálculos puros del prototipo. No contienen acceso a datos ni credenciales."""

from decimal import Decimal
from statistics import median


def summarize_prices(proposed_unit_price: str, historical_unit_prices: list) -> dict:
    """Compara una cotización con precios unitarios previamente homologados.

    La equivalencia de código, categoría, moneda y unidad debe verificarse en SQL.
    """
    if not historical_unit_prices:
        raise ValueError("Se necesita al menos una observación histórica")

    proposed = Decimal(str(proposed_unit_price))
    observed = [Decimal(str(price)) for price in historical_unit_prices]
    if proposed < 0 or any(price < 0 for price in observed):
        raise ValueError("Los precios no pueden ser negativos")

    baseline = median(observed)
    diff = proposed - baseline
    percent = (diff / baseline) * Decimal("100") if baseline != 0 else None
    return {
        "count": len(observed),
        "minimum": min(observed),
        "maximum": max(observed),
        "average": sum(observed) / len(observed),
        "median": baseline,
        "proposed": proposed,
        "difference": diff,
        "percent": percent,
    }
