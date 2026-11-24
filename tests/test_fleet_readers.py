"""Synthetic-only fixtures: no actual invoice identifiers or corporate data."""
from decimal import Decimal
from reportlab.pdfgen import canvas
import pytest
from core.invoice_router import read_invoice
from readers.fleetperform import HEADER
from test_invoice_display import view, assert_three_sections


def make_fp(path, repeat):
    c=canvas.Canvas(str(path),pagesize=(595,842))
    xs=[25,50,76,150,325,397,435,475,520,570]
    def put(x,y,t):
        c.setFont('Helvetica',7); c.drawString(x,842-y,t)
    def table(rows, y):
        h=22
        for x in xs: c.line(x,842-y,x,842-y-h*len(rows))
        for i in range(len(rows)+1): c.line(xs[0],842-y-i*h,xs[-1],842-y-i*h)
        for i,row in enumerate(rows):
            for x,t in zip(xs,row): put(x+2,y+i*h+13,t)
    put(25,30,'FleetPerform Synthetic Demo'); put(400,45,'Estimate # : TEST1');put(400,60,'Approve Date :')
    table([HEADER,['L','','123-456-789','Test labor','','3 (Units)','2.00','85.00','$510.00'],['P','','ABC123','Test part','','EA','2','5.00','$10.00']],180)
    c.showPage()
    table(([HEADER] if repeat else [])+[['P','','ABC456','Test other part','','EA','1','20.00','$20.00'],['M','','','SHOP SUPPLIES','','','1','10.00','$10.00']],40)
    for i,(label,v) in enumerate([('Total Parts','$30.00'),('Total Labor','$510.00'),('Special Charges','$10.00'),('Freight','$0.00'),('Tax','$0.00'),('Estimate Total','$550.00')]): put(375,180+i*15,label+' : '+v)
    c.save()

@pytest.mark.parametrize('repeat',[False,True])
def test_fleetperform_continuation(tmp_path,repeat,monkeypatch):
    p=tmp_path/'fp.pdf';make_fp(p,repeat);d=read_invoice(p)
    assert d.reader=='fleetperform_v1' and d.legacy_result is None
    assert len(d.items)==4 and [i.page for i in d.items]==[1,1,2,2]
    assert d.items[0].quantity==6 and d.items[0].printed['Hrs/Qty']==2 and d.items[0].printed['UOM']=='3 (Units)'
    assert d.items[0].unit_price==85 and d.items[0].amount==510
    assert 'Approve Date' not in d.metadata
    assert d.summary['Estimate Total']==550 and all(v==0 for v in d.checks.values())
    assert not d.warnings
    events=view(monkeypatch,d);assert_three_sections(events)
    detail=[v for s,k,v in events if s==('Repair Details',) and k=='table']
    assert len(detail)==1 and len(detail[0])==4


def test_direct_cross_page_core(tmp_path,monkeypatch):
    p=tmp_path/'direct.pdf';c=canvas.Canvas(str(p),pagesize=(612,792))
    def put(y,*cells):
        c.setFont('Helvetica',8)
        for x,t in cells:c.drawString(x,792-y,t)
    put(50,(51,'Fleet Repair Solutions - Test'),(415,'Estimate'),(484,'TEST-1'))
    put(100,(51,'Example, TX 99999'));put(300,(51,'Item'),(106,'Description'),(420,'Quantity'),(489,'Rate'),(531,'Amount'))
    put(320,(51,'Concern: Test repair'));put(340,(51,'Cause: Test Type: 03 - TEST'))
    put(360,(51,'Labor'),(106,'Recommended Correction:'),(423,'1.50000'),(478,'$100.00'),(533,'$150.00'))
    put(372,(106,'Travel / 123-456-789 / Test labor'))
    put(390,(51,'Parts'),(106,'Battery'),(447,'1'),(478,'$50.00'),(533,'$50.00'))
    c.showPage()
    put(40,(51,'Parts'),(106,'Inherent Core'),(447,'1'),(478,'$10.00'),(533,'$10.00'))
    put(60,(51,'Parts'),(106,'Dirty Core'),(447,'-1'),(478,'$5.00'),(533,'-$5.00'))
    put(80,(475,'Subtotal'),(533,'$205.00'))
    put(100,(106,'Shop Supplies'),(533,'$10.00'))
    put(130,(48,'Unit: TEST'),(480,'Labor'),(533,'$150.00'))
    put(150,(480,'Parts'),(533,'$55.00'));put(170,(475,'Subtotal'),(533,'$215.00'))
    put(190,(415,'PA Exempt (0% of $0.00)'),(541,'$0.00'));put(210,(480,'Total'),(533,'$215.00'));c.save()
    d=read_invoice(p)
    assert d.reader=='fleet_repair_solutions_v1' and d.legacy_result is None
    assert len(d.operations)==1 and d.operations[0].end_page==2 and d.operations[0].total==205
    assert len(d.items)==5 and d.items[3].quantity==-1 and d.items[3].amount==-5
    assert d.items[0].code=='123-456-789' and d.items[0].printed['Description'].startswith('Recommended Correction:')
    assert all(v==0 for v in d.checks.values()) and d.summary['Total']==215 and not d.warnings
    events=view(monkeypatch,d);assert_three_sections(events)
    detail=[v for s,k,v in events if s==('Repair Details',) and k=='table']
    assert len(detail)==2 and detail[0].iloc[-1]['Description']=='Operation Total' and detail[1].iloc[0]['Description']=='Shop Supplies'
