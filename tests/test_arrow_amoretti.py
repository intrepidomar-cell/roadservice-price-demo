"""Synthetic fixtures for the two new vendor signatures."""
from decimal import Decimal
from core.invoice_router import read_invoice
from test_towbook_bj_tom_nehl import pdf_writer
from test_invoice_display import view, assert_three_sections


def test_arrow_two_vehicles(tmp_path,monkeypatch):
    f=tmp_path/'arrow.pdf';c,p=pdf_writer(f)
    p(28,(30,'Arrow Towing, Inc.'),(520,'Invoice'));p(43,(30,'Example remit address'),(530,'#TEST'))
    p(90,(30,'Invoice #'),(131,'TEST'))
    p(170,(29,'Year'),(56,'Make'),(177,'Model'),(231,'Color'),(270,'VIN'),(365,'Plate'),(435,'Odometer'),(500,'Unit Number'))
    p(187,(29,'2020'),(56,'Example'),(177,'Tractor'),(231,'Red'),(270,'TESTVIN1'),(365,'ABC'),(435,'100'),(500,'TEST01'))
    p(204,(29,'2021'),(56,'Example'),(177,'Trailer'),(231,'White'),(270,'TESTVIN2'),(365,'DEF'),(435,'-'),(500,'TEST02'))
    p(230,(33,'Charge Description'),(358,'Quantity'),(465,'Price'),(529,'Line Total'))
    p(250,(33,'Fuel Surcharge'),(358,'1'),(454,'$10.00'),(539,'$10.00'))
    p(270,(33,'Heavy Duty - Wrecker Tow'),(358,'1'),(454,'$20.00'),(539,'$20.00'))
    p(290,(33,'Heavy Duty - Shag Tow'),(358,'1'),(454,'$30.00'),(539,'$30.00'))
    p(330,(430,'Subtotal'),(539,'$60.00'));p(350,(430,'Grand Total'),(539,'$60.00'));p(370,(410,'Amount Due:'),(539,'$60.00'))
    p(770,(30,'Created with Towbook Management Software'));c.save()
    d=read_invoice(f)
    assert d.reader=='towbook_v1' and d.vendor=='Arrow Towing, Inc.'
    assert d.metadata['Vehicle Unit']=='TEST01' and d.metadata['Vehicle 2 Unit']=='TEST02' and d.metadata['Vehicle count']=='2'
    assert len(d.items)==3 and all(v==0 for v in d.checks.values())
    assert all(i.category=='Misc' and not i.comparison_eligible for i in d.items)
    assert 'Tax' not in d.summary
    assert_three_sections(view(monkeypatch,d))


def test_amoretti_precharge_summary(tmp_path,monkeypatch):
    f=tmp_path/'amoretti.pdf';c,p=pdf_writer(f)
    p(48,(45,'Amoretti Diesel Repair and'),(457,'Invoice:'),(539,'TEST'))
    p(63,(45,'Service'));p(78,(45,'Example address'));p(93,(45,'Example, UT 99999'))
    p(275,(45,'Item'),(100,'Description'),(426,'Quantity'),(495,'Rate'),(537,'Amount'))
    p(294,(45,'Complaint: Example repair'));p(312,(45,'Cause: Example'))
    p(346,(45,'Labor'),(100,'Correction:'),(429,'2.00000'),(484,'$50.00'),(539,'$100.00'))
    p(357,(100,'Example correction'));p(386,(481,'Subtotal'),(539,'$100.00'))
    p(412,(100,'Call out fee'),(442,'1.00'),(488,'$20.00'),(543,'$20.00'))
    p(429,(100,'milage'),(438,'10.00'),(493,'$1.00'),(543,'$10.00'))
    p(461,(45,'Unit: TEST VIN: TESTVIN'),(490,'Labor'),(539,'$100.00'))
    p(478,(458,'Shop Supplies'),(543,'$5.00'));p(496,(436,'Pre-Charge Subtotal'),(539,'$105.00'))
    p(514,(470,'Call out fee'),(543,'$20.00'));p(532,(487,'milage'),(543,'$10.00'))
    p(549,(493,'State'));p(555,(543,'$13.50'));p(561,(436,'(10% of $135.00)'))
    p(578,(490,'Total'),(539,'$148.50'));p(595,(457,'Payments & Credits'),(543,'$0.00'));p(612,(480,'Balance Due'),(539,'$148.50'))
    p(650,(45,'Any warranties on the parts and accessories'))
    c.showPage();c.setFont('Helvetica',9);p(45,(45,'Example legal terms'));c.save()
    d=read_invoice(f)
    assert d.reader=='amoretti_v1' and len(d.items)==4 and len(d.operations)==1
    assert d.operations[0].total==100 and d.summary['Total']==Decimal('148.50')
    assert d.items[-1].quantity is None and d.items[-1].unit_price is None
    assert d.items[2].unit=='MI' and all(v==0 for v in d.checks.values()) and not d.warnings
    events=view(monkeypatch,d);assert_three_sections(events)
    tables=[v for s,k,v in events if s==('Repair Details',) and k=='table']
    assert len(tables)==2 and tables[1]['Description'].tolist()==['Call out fee','milage']
