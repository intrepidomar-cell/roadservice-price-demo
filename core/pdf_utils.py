"""Shared PDF primitives, not format-specific parsing rules."""
import re
from decimal import Decimal, InvalidOperation
from dataclasses import dataclass
import pdfplumber

@dataclass
class TextLine:
    top: float
    words: list
    @property
    def text(self):
        return ' '.join(w['text'] for w in self.words)


def lines(page):
    words = page.extract_words(x_tolerance=1, y_tolerance=2)
    return [TextLine(min(w['top'] for w in group), sorted(group,key=lambda w:w['x0']))
            for group in pdfplumber.utils.cluster_objects(words,'top',3)]


def decimal(value):
    if value is None: return None
    s = str(value).strip().replace('$','').replace(',','')
    if not s: return None
    if s.startswith('(') and s.endswith(')'): s = '-'+s[1:-1]
    if not re.fullmatch(r'[+-]?\d+(?:\.\d+)?',s): return None
    try: return Decimal(s)
    except InvalidOperation: return None


def field(text, pattern):
    m = re.search(pattern,text,re.I|re.M)
    return m.group(1).strip() if m else ''
