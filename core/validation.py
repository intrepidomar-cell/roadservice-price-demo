"""Common reconciliation without inventing missing values."""
from decimal import Decimal
TOL = Decimal('0.02')

def check_delta(invoice, name, expected, actual):
    delta = None if expected is None or actual is None else expected-actual
    invoice.checks[name] = delta
    if delta is not None and abs(delta)>TOL:
        invoice.warnings.append(f'{name}: difference ${delta:,.2f}; verify printed document.')
    return delta
