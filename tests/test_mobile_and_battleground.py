"""Synthetic fixtures, no company records or actual invoice identifiers."""
from decimal import Decimal
from reportlab.pdfgen import canvas
from core.invoice_router import read_invoice
from extracted_items import extract_candidates


def mobile_fixture(path, mismatch=False):
    c=canvas.Canvas(str(path),pagesize=(612,792)); c.setFont('Helvetica',9)
    def put(y,*cells):
        for x,t in cells: c.drawString(x,792-y,t)
    put(40,(156,'A Mobile Maintenance'),(501,'Invoice'))
    put(110,(364,'Invoice #'),(490,'TEST-01'))
    put(130,(373,'Date'),(490,'01/01/2025'))
    put(310,(43,'Quantity'),(101,'Item Code'),(277,'Description'),(449,'Price Each'),(522,'Amount'))
    put(330,(161,'Synthetic complaint'))
    rows=[('1','SERVICE CALL','Service Location : Example, TX','20.00','20.00'),
          ('1.5','LABOR REG H...','Total Drive Time','10.00','15.00'),
          ('2','LABOR REG H...','Total Repair Labor','10.00','20.00'),
          ('1','FUEL SURCHA...','FUEL SURCHARGE FEE','0.00','0.00'),
          ('2','PART EXAMPLE','Synthetic part','5.00','10.00'),
          ('1','SHOP SUPPLY...','SHOP SUPPLY FEE','5.00','5.00')]
    for n,row in enumerate(rows): put(350+n*22,*zip((70,89,161,470,541),row))
    put(475,(161,'wrapped description'))
    put(500,(541,'70.00'))
    put(610,(390,'Subtotal'),(536,'$70.00'))
    put(640,(390,'Total'),(536,'$71.00' if mismatch else '$70.00'))
    put(670,(390,'Payments/Credits'),(536,'$0.00'))
    put(695,(390,'Balance Due'),(536,'$70.00'))
    c.save()


def battleground_fixture(path, mismatch=False, extra_page=True):
    c=canvas.Canvas(str(path),pagesize=(612,792));c.setFont('Helvetica',9)
    def put(y,*cells):
        for x,t in cells: c.drawString(x,792-y,t)
    put(28,(26,'Battleground Wrecker'),(517,'Invoice'))
    put(43,(26,'Example address'),(533,'#12345'))
    put(191,(30,'Invoice #'),(131,'12345'))
    put(218,(30,'Reason'),(131,'Shop'))
    put(238,(306,'Service'),(371,'Example, TX'))
    put(245,(306,'Location'))
    put(275,(28,'Notes'),(109,'Synthetic PM'))
    put(341,(33,'Charge Description'),(358,'Quantity'),(465,'Price'),(529,'Line Total'))
    rows=[('Filter (Oil)','1','20.00','20.00','TEST123 example oil filter'),
          ('Filter (Fuel)','1','30.00','30.00','TEST456 example fuel filter'),
          ('Filter (Fuel)','1','40.00','40.00','TEST789 other fuel filter'),
          ('Oil (QUART)','2.5','4.00','10.00','2.5 QTS synthetic oil'),
          ('PM TRACTOR','3','10.00','30.00',''),
          ('Shop Fee','1','5.00','5.00',''),
          ('Inspection Supplies','1','0.00','0.00','')]
    for n,(d,q,p,a,detail) in enumerate(rows):
        y=360+n*28;put(y,(33,d),(358,q),(454,'$'+p),(539,'$'+a))
        if detail: put(y+11,(39,detail))
    put(580,(450,'Subtotal'),(539,'$135.00'))
    put(600,(427,'Grand Total'),(539,'$136.00' if mismatch else '$135.00'))
    put(620,(410,'Amount Due:'),(539,'$135.00'))
    put(645,(26,'**4% Transaction Fee for Credit Cards and Fleet Checks **'))
    if extra_page:
        c.showPage();c.setFont('Helvetica',9);put(100,(26,'Signature:'));put(120,(26,'________'));put(730,(26,'Created with Towbook Management Software'))
    c.save()


def test_mobile_variable_length(tmp_path):
    p=tmp_path/'a.pdf';mobile_fixture(p);d=read_invoice(p)
    assert d.reader=='a_mobile_maintenance_v1' and len(d.items)==6
    assert d.summary['Total']==70 and all(v==0 for v in d.checks.values())
    assert d.items[1].description=='Total Drive Time' and d.items[2].description=='Total Repair Labor'
    assert d.items[1].printed['Item Code']=='LABOR REG H...' and not d.items[1].comparison_eligible
    assert d.items[3].amount==0 and not d.items[3].comparison_eligible
    assert d.items[5].printed['Description'].endswith('wrapped description')
    assert len(extract_candidates(d))==1 # wrapped unrecognized fee is not inferred


def test_mobile_mismatch(tmp_path):
    p=tmp_path/'a.pdf';mobile_fixture(p,True);d=read_invoice(p)
    assert not extract_candidates(d) and any(abs(v)>Decimal('.02') for v in d.checks.values() if v is not None)


def test_battleground_signature_page_and_parts(tmp_path):
    p=tmp_path/'b.pdf';battleground_fixture(p);d=read_invoice(p)
    assert d.reader=='battleground_wrecker_v1' and len(d.items)==7 and d.pages==2
    assert d.summary['Grand Total']==135 and all(v==0 for v in d.checks.values())
    assert [i.code for i in d.items[:3]]==['TEST123','TEST456','TEST789']
    assert d.items[3].unit=='QT' and d.items[3].quantity==Decimal('2.5')
    assert d.items[4].unit=='' and not d.items[4].comparison_eligible
    assert d.items[-1].amount==0 and len(extract_candidates(d))==4


def test_battleground_mismatch(tmp_path):
    p=tmp_path/'b.pdf';battleground_fixture(p,True);d=read_invoice(p)
    assert not extract_candidates(d)
