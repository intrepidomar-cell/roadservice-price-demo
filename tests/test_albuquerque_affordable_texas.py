"""Synthetic regression fixtures; no corporate documents or identifiers."""
from decimal import Decimal
from core.invoice_router import read_invoice
from test_towbook_bj_tom_nehl import pdf_writer, towbook
from test_invoice_display import view


def test_albuquerque_warranty_and_absent_summary(tmp_path,monkeypatch):
    f=tmp_path/'abq.pdf';c,p=pdf_writer(f)
    p(25,(24,'Albuquerque Freightliner'));p(42,(24,'Example address'));p(55,(24,'Example city'))
    p(100,(470,'SERVICE ORDER:'),(549,'TEST01'));p(120,(480,'ESTIMATE:'),(550,'TEST02'))
    p(200,(24,'JOB# 2 Example repair'),(547,'WARRANTY'))
    p(225,(21,'COMPLAINT:'),(77,'Example complaint'))
    p(250,(26,'STATUS'),(78,'QTY'),(120,'ITEM'),(262,'DESCRIPTION'),(493,'UNIT PRICE'),(560,'EXTD PRICE'))
    p(270,(24,'SOLD'),(77,'1'),(118,'EXAMPLE-1'),(260,'Example part'))
    p(290,(24,'SOLD'),(118,'LABOR TEST'),(260,'Example labor'))
    c.save();d=read_invoice(f)
    assert d.reader=='albuquerque_v1' and len(d.items)==2 and d.operations[0].warranty
    assert d.document_type=='estimate' and not d.summary and all(i.amount is None and not i.comparison_eligible for i in d.items)
    assert d.items[1].quantity is None


def test_affordable_bundle_not_double_counted(tmp_path):
    f=tmp_path/'adr.pdf';c,p=pdf_writer(f)
    p(30,(177,'Affordable Diesel Repair, Inc.'));p(50,(177,'Example address'));p(70,(177,'AR US'))
    p(100,(403,'INVOICE #'),(467,'TEST1'))
    p(150,(50,'ACTIVITY'),(308,'QTY'),(428,'RATE'),(515,'AMOUNT'))
    p(170,(50,'***WORK TO BE DONE***'),(324,'1'),(434,'0.00'),(532,'0.00T'));p(185,(50,'Example problem'))
    p(210,(50,'Jump Start Call Out'),(324,'1'),(420,'50.00'),(526,'50.00'))
    p(230,(76,'LABOR RATE'),(307,'2'),(420,'20.00'))
    p(250,(76,'Fuel Surcharge'),(324,'1'),(427,'10.00'))
    p(280,(50,'***WORK COMPLETED***'),(324,'1'),(434,'0.00'),(532,'0.00T'));p(295,(50,'Example correction'))
    p(700,(312,'SUBTOTAL'),(530,'50.00'));p(730,(312,'TAX'),(530,'5.00'))
    c.showPage();c.setFont('Helvetica',9);p(40,(312,'TOTAL'),(530,'55.00'));p(60,(312,'BALANCE DUE'),(530,'$55.00'));c.save()
    d=read_invoice(f);assert d.reader=='affordable_diesel_v1' and len(d.items)==3
    assert [i.amount for i in d.items]==[Decimal('50'),None,None]
    assert all(v==0 for v in d.checks.values()) and d.summary['Total']==55
    assert d.notes['Complaint']=='Example problem' and not any(i.comparison_eligible for i in d.items)


def test_a1_towbook_identity(tmp_path):
    f=tmp_path/'a1.pdf';towbook(f,'A1 Wrecker & Diesel Services LLC','Standard Tax Rate - 10.5% Tax')
    d=read_invoice(f);assert d.vendor=='A1 Wrecker & Diesel Services LLC' and d.reader=='towbook_v1'
    assert all(v==0 for v in d.checks.values()) and not any(i.comparison_eligible for i in d.items)
    towbook(f,'A-1 SERVICE CENTER');assert read_invoice(f).reader=='unsupported'


def test_mobile_tax_marker_and_inline_tax(tmp_path):
    f=tmp_path/'mobile.pdf';c,p=pdf_writer(f)
    p(40,(156,'A Mobile Maintenance'),(501,'Invoice'));p(110,(364,'Invoice #'),(490,'TEST-01'))
    p(310,(43,'Quantity'),(101,'Item Code'),(277,'Description'),(449,'Price Each'),(522,'Amount'))
    p(350,(78,'1'),(89,'SERVICE CALL'),(161,'Service Location : Example'),(470,'100.00'),(541,'100.00T'))
    p(400,(541,'100.00'));p(430,(161,'BILL TO CUSTOMER: Example'));p(450,(161,'Sales Tax- Example'),(466,'6.50%'),(545,'6.50'))
    p(610,(390,'Subtotal'),(536,'$100.00'));p(640,(390,'Total'),(536,'$106.50'));p(670,(390,'Payments/Credits'),(536,'$0.00'));p(695,(390,'Balance Due'),(536,'$106.50'));c.save()
    d=read_invoice(f);assert len(d.items)==1 and d.items[0].amount==100 and d.items[0].printed['Taxable marker']=='T'
    assert d.summary['Sales Tax']==Decimal('6.50') and all(v==0 for v in d.checks.values())


def test_texas_towing_amount_only(tmp_path):
    f=tmp_path/'texas.pdf';c,p=pdf_writer(f)
    p(32,(127,'TEXAS TOWING WRECKER SERVICE INC.'));p(46,(127,'Example address'));p(60,(127,'Example city'));p(80,(390,'INVOICE: TEST1'));p(100,(469,'TOW INVOICE'))
    p(350,(39,'TOW CHARGE DESCRIPTION'),(430,'QTY'),(480,'RATE'),(530,'AMOUNT'))
    p(370,(34,'JUMP CALL OUT FEE'),(420,'1.00'),(470,'$50.00'),(545,'$50.00'))
    p(390,(34,'FUEL SURCHARGE'),(545,'$10.00'));p(420,(38,'INVOICE TOTAL'),(545,'$60.00'));p(440,(38,'PAYMENTS & CREDITS'));p(460,(38,'BALANCE'),(545,'$60.00'));c.save()
    d=read_invoice(f);assert len(d.items)==2 and d.summary['Invoice Total']==60 and all(v==0 for v in d.checks.values())
    assert d.items[1].quantity is None and d.items[1].unit_price is None and d.items[1].amount==10 and 'Payments & Credits' not in d.summary


def test_mobile_repeated_header_continuation(tmp_path):
    f=tmp_path/'mobile2.pdf';c,p=pdf_writer(f)
    def header():p(310,(43,'Quantity'),(101,'Item Code'),(277,'Description'),(449,'Price Each'),(522,'Amount'))
    p(40,(156,'A Mobile Maintenance'),(501,'Invoice'));p(110,(364,'Invoice #'),(490,'TEST-02'));header()
    p(350,(78,'1'),(89,'SERVICE CALL'),(161,'Service Location : Example'),(470,'20.00'),(541,'20.00'))
    c.showPage();c.setFont('Helvetica',9);header()
    p(350,(78,'2'),(89,'PART'),(161,'Example product'),(470,'15.00'),(541,'30.00'))
    p(400,(541,'50.00'));p(610,(390,'Subtotal'),(536,'$50.00'));p(640,(390,'Total'),(536,'$50.00'));p(670,(390,'Payments/Credits'),(536,'$0.00'));p(695,(390,'Balance Due'),(536,'$50.00'));c.save()
    d=read_invoice(f);assert len(d.items)==2 and [i.page for i in d.items]==[1,2] and all(v==0 for v in d.checks.values())
