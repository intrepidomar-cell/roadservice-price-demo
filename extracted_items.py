"""Expose only explicitly eligible normalized rows to historical comparisons."""
from dataclasses import asdict


def extract_candidates(invoice):
    return [asdict(item) for item in invoice.items if item.comparison_eligible]
