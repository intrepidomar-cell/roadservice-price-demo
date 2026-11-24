"""UI contract tests without a Streamlit server or access to Supabase."""
import importlib.util
import sys
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from types import ModuleType

import pandas as pd
from core.models import Invoice, LineItem, Operation
from extracted_items import extract_candidates


class RecordingUI(ModuleType):
    def __init__(self):
        super().__init__('streamlit')
        self.events = []
        self.scope = []

    def record(self, kind, value=None):
        self.events.append((tuple(self.scope), kind, value))

    @contextmanager
    def expander(self, label, expanded=False):
        self.record('expander', (label, expanded)); self.scope.append(label)
        yield
        self.scope.pop()

    @contextmanager
    def container(self, border=False):
        self.record('container', border); self.scope.append('card')
        yield
        self.scope.pop()

    def dataframe(self, value, **kwargs): self.record('table', value.copy())
    def markdown(self, value): self.record('markdown', value)
    def text(self, value): self.record('text', value)
    def caption(self, value): self.record('caption', value)
    def write(self, value): self.record('write', value)
    def warning(self, value): self.record('warning', value)
    def divider(self): self.record('divider')


def view(monkeypatch, doc):
    fake = RecordingUI()
    monkeypatch.setitem(sys.modules, 'streamlit', fake)
    spec = importlib.util.spec_from_file_location('test_view', Path(__file__).resolve().parents[1] / 'invoice_display.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    module.show_invoice_tables(doc)
    return fake.events


def assert_three_sections(events):
    assert [(k,v) for scope,k,v in events if not scope] == [
        ('expander', ('Document Information', False)),
        ('expander', ('Repair Details', True)), ('expander', ('Economic Summary', True))]
    assert not any(k=='container' for _,k,_ in events)
    assert not any(k=='markdown' and v in ('**Service comments**','**Case notes**','**Reconciliation**') for _,k,v in events)


def test_loves_compact_view(monkeypatch):
    item=LineItem('Shop Supplies', 1, 'Misc', amount=Decimal('7.15'), comparison_eligible=True, printed={'Description':'Shop Supplies','Extension':Decimal('7.15')})
    doc=Invoice('loves', items=[item], summary={'Total':Decimal('7.15')}, notes={'Complaint':'Synthetic complaint','Service comments':'Do not render'}, checks={'Total':Decimal(0)}, warnings=['Synthetic warning'])
    before=extract_candidates(doc)
    events=view(monkeypatch, doc); assert_three_sections(events)
    assert [v for _,k,v in events if k=='text']==['Synthetic complaint']
    assert next(i for i,(_,k,v) in enumerate(events) if k=='text') < next(i for i,(s,k,v) in enumerate(events) if k=='table' and s==('Repair Details',))
    assert any(s==('Document Information',) and k=='write' and v=='Synthetic warning' for s,k,v in events)
    assert before==extract_candidates(doc)


def test_decisiv_totals_inside_operation(monkeypatch):
    op=Operation(1,'TEST',page=1,end_page=2,total=Decimal('15'),parts_total=Decimal('5'),notes={'complaint':'Synthetic complaint'})
    items=[LineItem(name,1,category,amount=amount,operation='1. TEST',printed={'Description':name,'Totals':amount}) for name,category,amount in [('Labor','Labor',Decimal('8')),('Part','Parts',None),('Hookup','Misc',Decimal('2'))]]
    items.append(LineItem('SHOP SUPPLIES',2,'Misc',amount=Decimal(3),printed={'Description':'SHOP SUPPLIES','Totals':Decimal(3)}))
    doc=Invoice('decisiv',items=items,operations=[op],summary={'Shop Supplies':Decimal(3),'Total':Decimal(18)},notes={'Case notes':'Do not render'})
    events=view(monkeypatch,doc); assert_three_sections(events)
    detail, summary=[v for s,k,v in events if s in (('Repair Details',), ('Economic Summary',)) and k=='table']
    assert detail['Description'].tolist()==['Labor','Part','Parts Total','Hookup','Operation Total']
    assert detail['Totals'].tolist()==['8','','5','2','15']
    assert len(doc.items)==4 and summary['Concept'].tolist()==['Shop Supplies','Total']


def test_legacy_subtable_order(monkeypatch):
    result={'tablas':[{'id':'1','titulo':'Task 1','datos':pd.DataFrame({'Description':['A']})},{'id':'2','titulo':'Task 2','datos':pd.DataFrame({'Description':['B']})}], 'subtablas':[{'task_id':'1','datos':pd.DataFrame({'Concepto':['Subtotal 1']})}], 'resumen_final':{'datos':pd.DataFrame({'Concepto':['Total']})}}
    doc=Invoice('legacy',legacy_result=result)
    events=view(monkeypatch,doc); assert_three_sections(events)
    frames=[v for s,k,v in events if s in (('Repair Details',), ('Economic Summary',)) and k=='table']
    assert [f.iloc[0,0] for f in frames]==['A','Subtotal 1','B','Total']


def test_gwm_compact_view(monkeypatch):
    doc=Invoice('gwm', items=[LineItem('Glass',1,printed={'Product/Service':'Glass','Total':Decimal(100)})],summary={'Total':Decimal(100)})
    events=view(monkeypatch,doc); assert_three_sections(events)
    assert len([v for s,k,v in events if s in (('Repair Details',), ('Economic Summary',)) and k=='table'])==2


def test_no_summary_has_only_two_expanders(monkeypatch):
    doc=Invoice('gwm', items=[LineItem('Glass',1,printed={'Product/Service':'Glass','Total':Decimal(100)})])
    events=view(monkeypatch,doc)
    assert [(k,v) for scope,k,v in events if not scope] == [
        ('expander', ('Document Information', False)), ('expander', ('Repair Details', True))]
    assert not any('Economic Summary' in scope for scope,_,_ in events)
    assert any(scope==('Repair Details',) and kind=='table' for scope,kind,_ in events)


def test_legacy_empty_summary_has_only_two_expanders(monkeypatch):
    doc=Invoice('legacy', legacy_result={'tablas':[{'id':'1','datos':pd.DataFrame({'Description':['A']})}], 'resumen_final':{'datos':pd.DataFrame()}})
    events=view(monkeypatch,doc)
    assert [(k,v) for scope,k,v in events if not scope] == [
        ('expander', ('Document Information', False)), ('expander', ('Repair Details', True))]


def test_hide_page_columns_keep_provenance(monkeypatch):
    for reader in ('loves', 'gwm', 'decisiv'):
        item=LineItem('Part', 2, category='Parts', amount=Decimal('5'), operation='1. TEST',
                      printed={'Page':2,'Description':'Part','Totals':Decimal('5'),'End page':3})
        ops=[Operation(1,'TEST',code='123',page=2,end_page=3,total=Decimal('5'))] if reader=='decisiv' else []
        doc=Invoice(reader,items=[item],operations=ops,summary={'Total':Decimal('5')},pages=3)
        before=extract_candidates(doc)
        events=view(monkeypatch,doc); assert_three_sections(events)
        frames=[v for s,k,v in events if s==('Repair Details',) and k=='table']
        assert frames[0].columns.tolist()==['Description','Totals']
        assert not any(k=='caption' and str(v).startswith('Pages ') for _,k,v in events)
        assert item.page==2 and item.printed['End page']==3 and before==extract_candidates(doc)
        if ops: assert ops[0].end_page==3 and frames[0]['Description'].tolist()==['Part','Operation Total']


def test_legacy_page_columns_hidden(monkeypatch):
    main=pd.DataFrame({'pagina':[1,2],'Description':['A','B']})
    sub=pd.DataFrame({'Page':[2],'Concepto':['Subtotal']})
    summary=pd.DataFrame({'Página':[2],'Concepto':['Total']})
    result={'tablas':[{'id':'1','datos':main}], 'subtablas':[{'task_id':'1','datos':sub}],
            'resumen_final':{'datos':summary}}
    events=view(monkeypatch,Invoice('legacy',legacy_result=result))
    frames=[v for s,k,v in events if s in (('Repair Details',),('Economic Summary',)) and k=='table']
    assert [f.columns.tolist() for f in frames]==[['Description'],['Concepto'],['Concepto']]
    assert main['pagina'].tolist()==[1,2] and sub['Page'].tolist()==[2] and summary['Página'].tolist()==[2]
