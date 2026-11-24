"""Synthetic regression fixtures generated in a temp directory, no customer data."""
import sys
from decimal import Decimal
from reportlab.pdfgen import canvas
from core.invoice_router import read_invoice
from extracted_items import extract_candidates


def make_loves(path, zero=False):
    c=canvas.Canvas(str(path),pagesize=(612,792))
    def line(y,text,x=20):
        c.setFont('Helvetica',8); c.drawString(x,792-y,text)
    def header():
        line(60,'TOTAL TRUCK CARE'); line(100,"Love's Travel Stops & Country Stores, Inc.")
        line(125,'9999 Example, TX TRUCKCARE');line(125,'WORK ORDER # : 9999999999',400)
    header();line(350,'COMPLAINT :');line(362,'Synthetic complaint, for tests only.')
    c.showPage();header()
    for x,t in zip((19,145,245,271,325,395,474,554),('DESCRIPTION','MECHANIC','UOM','QUANTITY','LIST PRICE','PRODUCT','LABOR','EXTENSION')):line(230,t,x)
    def row(y,desc,mechanic='',qty='',lp='',prod='',labor='',ext='',uom='EA'):
        for x,t in zip((21,147,252,291,335,404,472,565),(desc,mechanic,uom,qty,lp,prod,labor,ext)):
            if t:line(y,t,x)
    if zero:
        row(250,'TIRE REPLACEMENT',qty='1.00',lp='0.00',prod='0.00',labor='0.00',ext='0.00')
        row(270,'TEST123 CASING',qty='1',uom='')
        vals=['0.00']*8
    else:
        row(250,'SRT LABOR','Test Mechanic','1.00','100.00','0.00','80.00','80.00')
        row(275,'Synthetic part ABC123',qty='2.00',lp='5.00',prod='5.00',labor='0.00',ext='10.00')
        line(285,'XYZ456',21);row(310,'Shop Supplies',ext='4.00',uom='')
        vals=['10.00','100.00','0.00','4.00','20.00','0.00','6.00','100.00']
    for n,(k,v) in enumerate(zip(('Parts','Labor','Tires','Fees','Customer Discount*','Site Discount','Tax','Total'),vals)):
        y=410+n*16;line(y,k,460);line(y+(3.5 if n==0 else 0),v,532)
    line(570,'SERVICE COMMENTS: Synthetic repair comment.');line(590,'********This is an Estimate********')
    c.save()


def test_loves_discount(tmp_path):
    f=tmp_path/'sample.pdf';make_loves(f);d=read_invoice(f)
    assert d.reader=='loves_total_truck_care_v1' and d.document_type=='estimate'
    assert len(d.items)==3 and d.summary['Total']==Decimal('100.00')
    assert d.items[0].printed['List Price']==Decimal('100.00')
    assert d.items[0].printed['Labor']==Decimal('80.00')
    assert d.items[1].description=='Synthetic part ABC123 XYZ456'
    assert d.items[1].code_candidates==['ABC123','XYZ456']
    assert d.items[2].quantity is None and d.items[2].amount==Decimal('4.00')
    assert all(v==0 for v in d.checks.values())
    assert [c['description'] for c in extract_candidates(d)]==['Shop Supplies']
    assert 'Synthetic complaint' in d.notes['Complaint'] and 'Synthetic repair' in d.notes['Service comments']


def test_loves_sparse_and_zero(tmp_path):
    f=tmp_path/'sample.pdf';make_loves(f,True);d=read_invoice(f)
    assert len(d.items)==2 and d.items[0].amount==0 and d.items[1].amount is None
    assert d.items[1].quantity==1 and d.items[1].unit==''
    assert d.summary['Total']==0 and not extract_candidates(d)


def test_unknown_no_fallback(tmp_path):
    f=tmp_path/'unknown.pdf';c=canvas.Canvas(str(f));c.drawString(20,700,'Unknown invoice format');c.save()
    d=read_invoice(f);assert d.reader=='unsupported' and not d.items


def make_decisiv(path, sparse=False):
    c=canvas.Canvas(str(path),pagesize=(612,792)); c.setFont('Helvetica',8)
    def put(y, *cells):
        for x,t in cells: c.drawString(x,792-y,t)
    put(36,(328,'ESTIMATE VERSION 1')); put(65,(136,'Gordon Truck Centers - Example WA'))
    put(112,(136,'Case Number: 12345678')); put(125,(136,'Repair Order Number: TEST123'))
    put(300,(44,'1 CHECK AND ADVISE')); put(320,(44,'Complaint:'),(136,'Synthetic test'))
    put(340,(420,'Quantity'),(490,'Price'),(550,'Totals'))
    put(360,(44,'Labor:'),(440,'2'),(480,'$50.00'),(540,'$100.00'))
    put(380,(44,'Parts:'),(136,'ABC123'),(204,'Synthetic sensor'),(440,'1.0'),*(() if sparse else ((480,'$20.00'),(540,'$25.00'))))
    put(390,(136,'456'),(204,'extended description'))
    if not sparse: put(410,(136,'Parts Total'),(540,'$25.00'))
    put(430,(44,'Operation Total:'),(540,'$125.00'))
    for n,(k,v) in enumerate([('Parts','$20.00'),('Labor','$100.00'),('Shop Supplies','$10.00'),('Taxes','$0.00'),('Core','$5.00'),('Total','$135.00')]):
        put(470+n*16,(470,k),(540,v))
    c.save()


def test_decisiv_direct(tmp_path):
    f=tmp_path/'decisiv.pdf';make_decisiv(f);d=read_invoice(f)
    assert d.reader=='decisiv_estimate_v2' and d.summary['Total']==135
    assert d.legacy_result is None and len(d.operations)==1
    assert d.operations[0].total==125 and d.operations[0].parts_total==25
    assert d.items[1].code=='ABC123 456' and d.items[1].description=='Synthetic sensor extended description'
    assert d.items[1].unit_price==20 and d.items[1].amount==25 and d.items[1].amount_consistent is False
    assert all(v==0 for v in d.checks.values())
    assert [i['description'] for i in extract_candidates(d)]==['SHOP SUPPLIES']


def test_decisiv_missing_price(tmp_path):
    f=tmp_path/'decisiv.pdf';make_decisiv(f,True);d=read_invoice(f)
    assert d.items[1].quantity==1 and d.items[1].amount is None and d.items[1].unit_price is None
    assert d.checks['Operation 1 total'] is None and d.checks['Printed economic summary']==0


def test_fleetperform_compat(tmp_path):
    f=tmp_path/'fleet.pdf';c=canvas.Canvas(str(f),pagesize=(612,792));c.setFont('Helvetica',8)
    c.drawString(20,750,'FleetPerform Synthetic Demo')
    for x,t in zip((20,50,110,260,310,365,490),('Type','Labor/Part','Description','Hrs/Qty','UOM','Rate/Price','Ext Amt')):c.drawString(x,700,t)
    for x,t in zip((20,50,110,260,310,365,490),('P','TEST123','Synthetic part','2.00','EA','5.00','10.00')):c.drawString(x,680,t)
    c.save();d=read_invoice(f)
    assert d.reader=='fleetperform_v1'
    assert d.items and any(i.amount==10 for i in d.items)
