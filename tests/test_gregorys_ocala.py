"""Synthetic-only regression tests, no private sample data."""
from decimal import Decimal
from reportlab.pdfgen import canvas
from core.invoice_router import read_invoice
from extracted_items import extract_candidates
from test_invoice_display import view, assert_three_sections


def test_gregorys_precision_groups(tmp_path,monkeypatch):
    p=tmp_path/'gregory.pdf';c=canvas.Canvas(str(p),pagesize=(612,792))
    def put(y,*cells):
        c.setFont('Helvetica',8)
        for x,t in cells:c.drawString(x,792-y,t)
    def header(y):put(y,(49,'Item'),(153,'Description'),(322,'Quantity'),(423,'Rate'),(530,'Amount'))
    put(50,(49,"GREGORY'S TRAILER AND"),(420,'Estimate'),(530,'TEST1'));put(65,(49,'TRUCK SERVICE'));header(300)
    put(320,(49,'Labor'),(153,'Test labor'),(322,'1.00000'),(423,'$80.00'),(530,'$80.00'))
    put(340,(49,'Parts'),(153,'Test part -'),(347,'1'),(423,'$1.235'),(530,'$1.24'))
    put(354,(153,'ABC-'));put(368,(153,'123'));c.showPage();header(40)
    put(70,(423,'Subtotal'),(530,'$81.24'))
    put(95,(153,'SHOP SUPPLIES'),(347,'1'),(423,'$10.00'),(530,'$10.00'))
    put(110,(153,'Shop Supplies'),(530,'$0.00'))
    put(150,(46,'Unit: TEST'),(361,'Labor'),(530,'$80.00'))
    put(165,(361,'Parts'),(530,'$1.24'));put(180,(361,'SHOP SUPPLIES'),(530,'$10.00'));put(195,(361,'Subtotal'),(530,'$91.24'))
    put(210,(361,'SC STATE & COUNTY (7% of'),(530,'$0.79'));put(225,(361,'$11.24)'));put(240,(361,'Total'),(530,'$92.03'));c.save()
    d=read_invoice(p);assert d.reader=='gregorys_v1' and d.document_type=='estimate'
    assert len(d.operations)==1 and d.operations[0].end_page==2
    assert len(d.items)==4 and d.items[1].unit_price==Decimal('1.235') and d.items[1].amount==Decimal('1.24')
    assert d.items[1].code_candidates==['ABC-123'] and d.items[3].amount==0 and d.items[3].unit_price is None
    assert all(v==0 for v in d.checks.values()) and not d.warnings
    events=view(monkeypatch,d);assert_three_sections(events)
    detail=[v for s,k,v in events if s==('Repair Details',) and k=='table'];assert len(detail)==2 and len(detail[1])==2


def make_ocala(p,final):
    c=canvas.Canvas(str(p),pagesize=(612,792))
    def put(x,y,t):c.setFont('Helvetica',8);c.drawString(x,792-y,t)
    def table(y,wide,rows):
        xs=[23,54,202,445,520,590] if wide else [23,54,590]
        labels=['QTY','ITEM','DESCRIPTION','UNIT PRICE','EXTD PRICE'] if wide else ['QTY','DESCRIPTION']
        for x in xs:c.line(x,792-y,x,792-y-18*(len(rows)+1))
        for n in range(len(rows)+2):c.line(xs[0],792-y-18*n,xs[-1],792-y-18*n)
        for n,r in enumerate([labels]+rows):
            for x,t in zip(xs,r):put(x+8,y+12+n*18,t)
    put(260,30,'OCALA FREIGHTLINER');put(200,210,'SERVICE INVOICE: TEST:01' if final else 'SERVICE ORDER: TEST');put(250,310,'Sold Operations')
    if not final:put(200,270,'NOT AN INVOICE')
    put(23,340,'JOB #1 A Test sold');put(23,360,'COMPLAINT TEST');table(380,True,[['1','TESTCODE','Test Part','50.00','50.00']]);c.showPage()
    put(250,50,'Sold Operations (Cont.)');table(70,True,[['','LABOR T99','TRUCK REPAIR LABOR GUIDE','','100.00']]);put(240,130,'Prepay: $0.00 Parts: $50.00 Labor: $100.00 Misc: $0.00 Sublet: $0.00 $150.00')
    put(250,165,'Rejected Operations');put(23,190,'JOB #2 B Test rejected');put(23,210,'COMPLAINT -DECLINED');table(230,False,[['2','Test rejected part'],['','TEST AVAIL @ 105']]);put(240,300,'Prepay: $0.00 Parts: $300.00 Labor: $0.00 Misc: $0.00 Sublet: $0.00 $300.00')
    put(498,490,'ESTIMATED');put(569,490,'BILLED')
    for n,(k,v) in enumerate([('LABOR','$100.00'),('PARTS','$50.00'),('MISC CHG','$0.00'),('SUBLET','$0.00'),('PREPAY','$0.00'),('SUBTOTAL','$150.00'),('SHOP SUPPLIES','$10.00'),('TAX','$5.00'),('TOTAL','$165.00')]):put(411,510+n*14,k);put(555,510+n*14,v)
    c.save()


def test_ocala_rejected_continuation(tmp_path,monkeypatch):
    p=tmp_path/'ocala.pdf';make_ocala(p,False);d=read_invoice(p)
    assert d.reader=='ocala_v1' and d.document_type=='estimate'
    assert len(d.operations)==2 and d.operations[0].end_page==2 and d.operations[0].total==150
    assert d.operations[1].notes['status']=='Rejected' and d.operations[1].total==300
    assert d.items[2].amount is None and d.items[3].category=='Unclassified'
    assert d.summary['TOTAL']==165 and d.summary['Billed — SUBTOTAL']==150
    assert d.checks['Billed total']==0 and d.checks['Job 2 item total'] is None
    assert not extract_candidates(d)
    events=view(monkeypatch,d);assert_three_sections(events)
    summary=next(v for s,k,v in events if s==('Economic Summary',) and k=='table')
    assert list(summary.columns)==['Concept','Estimated','Billed','Total / additional']
    assert not any('Page' in str(c) for s,k,v in events if k=='table' and s==('Repair Details',) for c in v.columns)


def test_ocala_final_rejection_not_comparable(tmp_path):
    p=tmp_path/'ocala.pdf';make_ocala(p,True);d=read_invoice(p)
    assert d.document_type=='invoice' and d.summary['TOTAL']==165
    assert not any(i.comparison_eligible for i in d.items if '[Rejected]' in i.operation)
