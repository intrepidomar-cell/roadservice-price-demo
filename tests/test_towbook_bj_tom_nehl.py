"""Synthetic digital layouts; no actual company invoices or identifiers."""
from decimal import Decimal
from reportlab.pdfgen import canvas
from core.invoice_router import read_invoice
from extracted_items import extract_candidates
from test_invoice_display import view, assert_three_sections


def pdf_writer(path):
    c=canvas.Canvas(str(path),pagesize=(612,792));c.setFont('Helvetica',9)
    def put(y,*cells):
        for x,t in cells:c.drawString(x,792-y,t)
    return c,put


def towbook(path,vendor,tax_label='Taxes',quote=False):
    c,p=pdf_writer(path)
    p(28,(30,vendor),(520,'Invoice'));p(43,(30,'Example address'),(530,'#TEST'))
    p(90,(30,'Invoice #'),(131,'TEST'));p(112,(30,'Tow Reason'),(131,'Tow'),(306,'Tow From'),(370,'Example origin'))
    p(130,(306,'Tow To'),(370,'Example destination'))
    if quote:p(170,(30,'Notes'),(110,'Customer requesting quote'))
    p(200,(33,'Charge Description'),(358,'Quantity'),(465,'Price'),(529,'Line Total'))
    p(220,(33,'Tow (Hourly)'),(358,'1.5'),(454,'$20.00'),(539,'$30.00'))
    p(240,(33,'Mileage - HD'),(358,'10'),(454,'$2.00'),(539,'$20.00'))
    p(260,(33,'Fuel Surcharge'),(358,'1'),(454,'$5.00'),(539,'$5.00'))
    p(290,(430,'Subtotal'),(539,'$55.00'));p(310,(410,tax_label),(539,'$3.00'))
    p(330,(430,'Grand Total'),(539,'$58.00'));p(350,(410,'Amount Due:'),(539,'$58.00'))
    p(770,(30,'Created with Towbook Management Software'));c.save()


def test_shared_towbook(tmp_path):
    for vendor in ("Candido's Towing & Repair",'B&W Wrecker Service',"Stauffer's Road Solutions"):
        path=tmp_path/'tow.pdf';towbook(path,vendor,'Example - 6% Tax');d=read_invoice(path)
        assert d.reader=='towbook_v1' and d.vendor==vendor and len(d.items)==3
        assert all(v==0 for v in d.checks.values())
        assert d.items[0].unit=='HR' and d.items[1].unit=='MI'
        assert not d.items[1].comparison_eligible
        assert len(extract_candidates(d))==1
    towbook(path,"Candido's Towing & Repair",quote=True);assert not extract_candidates(read_invoice(path))


def test_bj_groups_and_missing_quantity(tmp_path,monkeypatch):
    path=tmp_path/'bj.pdf';c,p=pdf_writer(path)
    p(40,(180,'B.J. Trailer & Truck Repair'));p(75,(458,'DATE'),(513,'INVOICE #'));p(95,(445,'01/01/2025'),(522,'12345'))
    p(276,(175,'DESCRIPTION'),(389,'HRS/QTY'),(448,'RATE/PRICE'),(523,'AMOUNT'))
    p(300,(38,'Synthetic repair'),(400,'2'),(479,'10.00'),(537,'20.00'))
    p(320,(38,'LABOR TOTAL'),(537,'20.00'));p(340,(38,'Part A'),(479,'40.00'),(537,'40.00'))
    p(360,(38,'PARTS TOTAL'),(537,'40.00'));p(380,(38,'Sales Tax'),(479,'10%'),(537,'4.00'))
    p(690,(38,'Thank you for your business.'));p(710,(525,'$64.00'),(38,'NOT RESPONSIBLE'));c.save()
    d=read_invoice(path);assert d.reader=='bj_trailer_v1' and len(d.items)==2
    assert d.items[1].quantity is None and all(v==0 for v in d.checks.values())
    assert d.metadata['Sales tax rate']=='10%' and not extract_candidates(d)
    assert_three_sections(view(monkeypatch,d))


def test_tom_nehl_task_aggregate(tmp_path,monkeypatch):
    path=tmp_path/'tom.pdf';c,p=pdf_writer(path)
    p(20,(400,'*** Customer Review ***'));p(60,(400,'Invoice Total: $50.00'));p(90,(400,'Fleet Boost'))
    p(150,(18,'Task: 1'),(70,'TEST'),(168,'Synthetic repair'),(456,'Department: Service'))
    p(170,(30,'Complaint: Synthetic complaint'))
    p(190,(19,'Supp.'),(70,'Part'),(211,'Description / Ref Number'),(396,'U/M'),(432,'Quantity'),(529,'Price'),(565,'Ext Price'))
    p(205,(19,'FTL'),(70,'TEST123'),(211,'Synthetic part'),(336,'Part'),(396,'EA'),(443,'1.00'),(516,'20.00'),(565,'20.00'))
    p(220,(70,'Synthetic detail'))
    p(240,(364,'Task 1 Subtotals:'),(478,'Parts:'),(550,'$20.00'))
    p(255,(476,'Labor:'),(550,'$25.00'));p(270,(451,'Task 1 Totals:'),(550,'$45.00'))
    c.showPage();c.setFont('Helvetica',9)
    for i,(label,value) in enumerate([('Total Parts','20.00'),('Total Core Chg','0.00'),('Total Core Ret','0.00'),('Total EHC','0.00'),('Total Labor','25.00'),('Total Miscellaneous','0.00'),('Total Shop Supplies','5.00'),('Invoice Subtotal','50.00'),('Total Tax','0.00'),('Invoiced Total','50.00')]):p(300+i*15,(400,label+':'),(550,'$'+value))
    p(600,(20,'TOM NEHL TRUCK COMPANY'));c.save()
    d=read_invoice(path);assert d.reader=='tom_nehl_v1' and d.document_type=='estimate'
    assert len(d.items)==2 and d.items[1].unit_price is None and d.items[1].quantity is None
    assert d.items[0].printed['Details']=='Synthetic detail' and not extract_candidates(d)
    assert all(v==0 for v in d.checks.values());assert_three_sections(view(monkeypatch,d))
