"""Shared result contract. None means not printed or not confidently extracted."""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

@dataclass
class LineItem:
    description: str
    page: int | None = None
    category: str = 'Unclassified'
    code: str = ''
    quantity: Decimal | None = None
    unit: str = ''
    unit_price: Decimal | None = None
    amount: Decimal | None = None
    price_source: str = 'missing'
    comparison_eligible: bool = False
    amount_consistent: bool | None = None
    printed: dict[str, Any] = field(default_factory=dict)
    operation: str = ''
    code_candidates: list[str] = field(default_factory=list)

@dataclass
class Operation:
    number: int
    title: str
    code: str = ''
    warranty: bool = False
    page: int | None = None
    end_page: int | None = None
    total: Decimal | None = None
    parts_total: Decimal | None = None
    notes: dict[str, str] = field(default_factory=dict)

@dataclass
class Invoice:
    reader: str
    vendor: str = ''
    document_type: str = 'unknown'
    metadata: dict[str, str] = field(default_factory=dict)
    items: list[LineItem] = field(default_factory=list)
    summary: dict[str, Decimal] = field(default_factory=dict)
    notes: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    pages: int = 0
    checks: dict[str, Decimal | None] = field(default_factory=dict)
    legacy_result: dict | None = None
    operations: list[Operation] = field(default_factory=list)
    summary_pages: dict[str, int] = field(default_factory=dict)
