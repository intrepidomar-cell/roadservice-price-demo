"""Synthetic GWM fixtures: no corporate invoice data."""
from decimal import Decimal
from reportlab.pdfgen import canvas
from core.invoice_router import read_invoice
from extracted_items import extract_candidates


def make_gwm(path, mismatch=False, sparse=False):
    c=canvas.Canvas(str(path),pagesize=(612,792)); c.setFont('Helvetica',8)
    def put(y,*cells):
        for x,t in cells: c.drawString(x,792-y,t)
    put(55,(120,'GWM Commercial Auto Glass'))
    put(135,(346,'Invoice #99999'))
    put(160,(346,'Issued'),(510,'Jan 04, 2025'))
    put(180,(346,'Due'),(510,'Feb 04, 2025'))
    put(330,(346,'Total'),(525,'$100.00'))
    put(375,(36,'TEST - 2020 EXAMPLE TRUCK - 999999 - Example, TX'))
    put(400,*zip((41,171,413,450,548),('Product/Service','Description','Qty.','Unit Price','Total')))
    put(420,(41,'Jan 03, 2025'))
    put(440,*zip((41,171,426,461,533),('SRI Remove & Install','Install example','1','$20.00','$20.00*')))
    put(465,*zip((41,171,426,461,533),('CR England DW9999','Synthetic glass','2','$15.00' if not sparse else '', '$30.00*')))
    put(475,(171,'wrapped description'))
    put(500,*zip((41,171,426,461,533),('CR England DW9998','Synthetic glass B','1','$40.00','$40.00*')))
    put(525,(41,'Jan 04, 2025'))
    put(545,*zip((41,171,426,461,533),('Other service','Not classified','1','$5.00','$5.00*')))
    put(570,*zip((41,171,426,461,533),('Other product','Not classified','1','$5.00','$5.00*')))
    put(650,(381,'Total'),(536,'$101.00' if mismatch else '$100.00'))
    put(660,(36,'* Non-taxable')); c.save()


def test_gwm_many_rows(tmp_path):
    p=tmp_path/'fixture.pdf';make_gwm(p);d=read_invoice(p)
    assert d.reader=='gwm_commercial_auto_glass_v1' and d.document_type=='invoice'
    assert d.summary['Total']==100 and all(v==0 for v in d.checks.values())
    assert len(d.items)==5 and len(extract_candidates(d))==3
    assert d.items[0].category=='Labor' and d.items[0].unit=='EA'
    assert d.items[1].code=='CR England DW9999' and d.items[1].quantity==2
    assert d.items[1].description=='Synthetic glass wrapped description'
    assert d.items[1].amount==30 and d.items[1].unit_price==15
    assert d.items[-1].printed['Service date']=='2025-01-04'
    assert d.items[0].printed['Tax status']=='Non-taxable'
    assert d.metadata['Service location']=='Example, TX'


def test_gwm_mismatch_blocks_comparison(tmp_path):
    p=tmp_path/'fixture.pdf';make_gwm(p,mismatch=True);d=read_invoice(p)
    assert len(d.items)==5 and not extract_candidates(d)
    assert d.checks['Header total vs printed final total']==Decimal('-1.00')


def test_gwm_missing_price(tmp_path):
    p=tmp_path/'fixture.pdf';make_gwm(p,sparse=True);d=read_invoice(p)
    assert len(d.items)==5 and d.items[1].unit_price is None
    assert d.items[1].amount==30 and not extract_candidates(d)


def test_gwm_large_amount(tmp_path):
    p=tmp_path/'large.pdf';c=canvas.Canvas(str(p),pagesize=(612,792));c.setFont('Helvetica',8)
    def put(y,x,t): c.drawString(x,792-y,t)
    put(55,120,'GWM Commercial Auto Glass');put(135,346,'Invoice #99998')
    put(330,346,'Total');c.drawRightString(572,792-330,'$123,456.78')
    for x,t in zip((41,171,413,450,548),('Product/Service','Description','Qty.','Unit Price','Total')):put(400,x,t)
    put(440,41,'CR England DW9997');put(440,171,'Synthetic glass')
    for x,t in [(430,'1'),(486,'$123,456.78'),(566,'$123,456.78')]:c.drawRightString(x,792-440,t)
    put(650,381,'Total');c.drawRightString(572,792-650,'$123,456.78');c.save()
    d=read_invoice(p);assert len(d.items)==1 and d.items[0].amount==Decimal('123456.78')
    assert d.items[0].unit_price==d.items[0].amount and len(extract_candidates(d))==1
