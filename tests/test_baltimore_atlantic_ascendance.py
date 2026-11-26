"""Synthetic examples of new formats; no actual business records."""
from decimal import Decimal
from core.invoice_router import read_invoice
from test_towbook_bj_tom_nehl import pdf_writer,towbook
from test_invoice_display import view,assert_three_sections


def test_bains_shared_towbook(tmp_path):
    f=tmp_path/'bains.pdf';towbook(f,'Bains Towing & Recovery, LLC.')
    d=read_invoice(f)
    assert d.reader=='towbook_v1' and d.vendor=='Bains Towing & Recovery, LLC.'
    assert all(v==0 for v in d.checks.values()) and not any(i.comparison_eligible for i in d.items)


def test_baltimore_repeated_job_header(tmp_path,monkeypatch):
    f=tmp_path/'baltimore.pdf';c,p=pdf_writer(f)
    p(40,(320,'BALTIMORE FREIGHTLINER'));p(100,(280,'Service Order'));p(130,(500,'RO: TEST1'))
    p(170,(51,'FREIGHTLINER WARRANTY SERVICE'));p(220,(280,'Sold Operations'))
    p(240,(25,'Job#1'),(65,'ASR'),(155,'Example repair'))
    p(260,(25,'Condition'),(90,'Example complaint'))
    p(300,(41,'Qty'),(70,'Item'),(178,'Description'),(485,'Price'),(558,'Extended'))
    p(320,(46,'1'),(68,'001F/TEST1'),(178,'Example part'))
    c.showPage();c.setFont('Helvetica',9);p(40,(280,'Service Order'));p(60,(250,'Sold Operations (Cont.)'))
    p(80,(25,'Job#1'),(65,'ASR'),(155,'Example repair'));p(100,(25,'Condition'),(90,'Example complaint'))
    p(140,(41,'Qty'),(70,'Item'),(178,'Description'),(485,'Price'),(558,'Extended'))
    p(160,(46,'1'),(68,'001F/TEST2'),(178,'Second part'))
    p(560,(22,'I hereby authorize example terms'));c.save()
    d=read_invoice(f);assert d.reader=='baltimore_v1' and len(d.operations)==1 and len(d.items)==2
    assert d.operations[0].end_page==2 and d.operations[0].warranty and not d.summary
    assert all(i.amount is None for i in d.items)


def test_atlantic_direct(tmp_path,monkeypatch):
    f=tmp_path/'atlantic.pdf';c,p=pdf_writer(f)
    p(40,(430,'WWW.ATLANTICUTILITY.COM'));p(180,(220,'SERVICE ESTIMATE: TEST1'),(430,'INVOICE TOTAL: $110.00'))
    p(220,(250,'Estimate Operations'));p(240,(28,'JOB #1 T12 - Example'))
    p(265,(21,'COMPLAINT'),(98,'Example complaint'))
    p(300,(35,'QTY'),(62,'ITEM'),(206,'DESCRIPTION'),(479,'UNIT PRICE'),(559,'EXTD PRICE'))
    p(320,(37,'2'),(62,'LABOR TEST'),(205,'LABOR'),(483,'50.00'),(566,'100.00'))
    p(345,(220,'Prepay: 0.00 Parts: $0.00 Labor: $100.00 Misc: $0 Sublet: $0 $100.00'))
    p(500,(23,'Statement of Disclaimer:'))
    for n,(k,v) in enumerate([('LABOR',100),('PARTS',0),('PREPAY',0),('MISC',0),('SUBLET',0),('SUBTOTAL',100),('SHOP SUPPLIES',5),('TAX',5),('TOTAL',110)]):p(515+n*18,(446,k),(556,f'${v:.2f}'))
    c.save();d=read_invoice(f);assert d.reader=='atlantic_utility_v1' and d.document_type=='estimate'
    assert len(d.items)==1 and d.items[0].amount==100 and d.summary['TOTAL']==110
    assert all(v==0 for v in d.checks.values());assert_three_sections(view(monkeypatch,d))


def test_ascendance_status_and_summary(tmp_path,monkeypatch):
    f=tmp_path/'ascendance.pdf';c,p=pdf_writer(f)
    p(40,(230,'Ascendance Trucks Eastern Iowa,'));p(55,(230,'LLC'));p(80,(425,'SERVICE ORDER: TEST1'))
    p(130,(27,'JOB# 1 Example repair'),(523,'CUSTOMER PAY'))
    p(155,(24,'COMPLAINT:'),(106,'Example'))
    p(190,(26,'STATUS'),(89,'QTY'),(119,'ITEM'),(260,'DESCRIPTION'),(474,'UNIT PRICE'),(542,'EXTD PRICE'))
    p(210,(24,'ESTIMATE'),(89,'2'),(119,'353N/TEST'),(260,'Example part'),(485,'10.00'),(570,'20.00'))
    p(240,(57,'SOLD'),(105,'Prepay: 0.00'),(184,'Parts: 0.00'),(255,'Labor: 0.00'),(325,'Misc: 0.00'),(396,'Sublet: 0.00'),(544,'Subtotal: 0.00'))
    p(265,(48,'ESTIMATE'),(184,'Parts: 20.00'),(255,'Labor: 0.00'),(325,'Misc: 0.00'),(396,'Sublet: 0.00'),(544,'Subtotal: 20.00'))
    p(320,(20,'TERMS OF SALE'),(436,'Approved:'))
    for n,(k,v) in enumerate([('Labor',0),('Parts',0),('Misc',0),('Sublet',0),('PrePay',0),('Subtotal',0),('Shop Supplies',0),('Misc Supplies',0),('Taxes',0),('Total',0)]):p(340+n*16,(438,k+':'),(563,f'${v:.2f}'))
    p(515,(436,'Additional Estimates:'))
    for n,(k,v) in enumerate([('Labor',0),('Parts',20),('Misc',0),('Sublet',0),('Subtotal',20),('Shop Supplies',0),('Misc Supplies',0),('Taxes',0),('Est Total',20),('Total w Est',20)]):p(535+n*16,(438,k+':'),(563,f'${v:.2f}'))
    c.save();d=read_invoice(f)
    assert d.reader=='ascendance_v1' and len(d.items)==1 and d.items[0].printed['Status']=='ESTIMATE'
    assert d.summary['Approved — Total']==0 and d.summary['Additional Estimates — Est Total']==20
    assert all(v==0 for v in d.checks.values()) and not d.items[0].comparison_eligible
    assert_three_sections(view(monkeypatch,d))


def test_atlantic_fleetperform_identity(tmp_path):
    from test_fleet_readers import make_fp
    f=tmp_path/'atlantic_fp.pdf';make_fp(f,True,vendor='ATLANTIC UTILITY TRLR SLS')
    d=read_invoice(f)
    assert d.reader=='fleetperform_v1' and d.vendor=='Atlantic Utility Trailer Sales'
    assert d.metadata['Billing format']=='FleetPerform' and d.document_type=='estimate'
    assert len(d.items)==4 and all(v==0 for v in d.checks.values())
    assert not any(i.comparison_eligible for i in d.items)
