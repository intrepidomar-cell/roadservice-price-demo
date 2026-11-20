# -*- coding: utf-8 -*-
"""Motor completo del Laboratorio 10 (L08 → L09 → L10).

Fuente: CR_England_Laboratorio_10_Multitablas_Jobs_y_Subtablas_WIG_Colab(2).ipynb
Celdas originales 10, 12 y 14; se conservaron sus funciones y su orden.
No hay OCR. NO se ejecutan celdas de Google Colab ni cargas desde /content.
Archivo generado para integración en Streamlit; no editar los parsers aquí.
"""



# ========= CELDA 10 DEL NOTEBOOK ORIGINAL =========
"""Motor C.R. England: tablas principales, subtotales por Task y resumen global."""
from pathlib import Path
import re
from dataclasses import dataclass
import pdfplumber
import pandas as pd

RE_NUM = re.compile(r'^\(?-?\$?\d[\d,]*(?:\.\d+)?\)?$')
RE_MONEY = re.compile(r'^\(?-?\$?\d[\d,]*\.\d{2}\)?$')
RE_TASK = re.compile(r'^(?:task|job|operation):?$', re.I)
RE_SUMMARY = re.compile(r'\b(?:subtotal|subtotals|totals|total|discount|tax|freight|payment|balance|surcharge\s+total|type\s+legend|special\s+charges)\b', re.I)


def norm(s):
    return re.sub(r'[^a-z0-9]+','',str(s or '').lower())

def text_of(words):
    return ' '.join(w['text'] for w in sorted(words, key=lambda w:(round(w['top']/4),w['x0']))).strip()

def close_words(words, y, left, right, tol=4.5):
    return [w for w in words if left <= w['x0'] < right and abs(w['top']-y)<=tol]

def is_num(text):
    return bool(RE_NUM.fullmatch(str(text).strip()))

def is_money(text):
    return bool(RE_MONEY.fullmatch(str(text).strip()))


def grouped_lines(words, tolerance=3.5):
    groups=[]
    for w in sorted(words,key=lambda w:(w['top'],w['x0'])):
        if groups and abs(groups[-1]['y']-w['top'])<=tolerance:
            groups[-1]['words'].append(w)
        else:
            groups.append({'y':w['top'],'words':[w]})
    return [{'y':g['y'],'words':sorted(g['words'],key=lambda w:w['x0'])} for g in groups]



# Encabezados originales: la salida NO decide columnas según si tienen valores.
def header_columns(header_words):
    """Reconstruye etiquetas impresas sobre la misma banda del encabezado.

    Cada elemento tiene nombre y coordenada x. La unión de palabras como
    'Ext Price' solo recompone un título, no interpreta importes.
    """
    ws=sorted(header_words,key=lambda w:w['x0'])
    out=[]; i=0
    while i<len(ws):
        tok=norm(ws[i]['text']); end=i+1
        if tok=='description' and i+3<len(ws) and [norm(w['text']) for w in ws[i+1:i+4]]==['','ref','number']:
            end=i+4
        elif tok in ('ext','position','list') and i+1<len(ws):
            nxt=norm(ws[i+1]['text'])
            if (tok,nxt) in {('ext','price'),('ext','amt'),('position','codes'),('list','price')}:
                end=i+2
        label=' '.join(w['text'] for w in ws[i:end])
        # No se descarta ningún encabezado por tener celdas vacías.
        out.append({'name':label,'x':ws[i]['x0']})
        i=end
    names={}
    for col in out:
        n=col['name']; names[n]=names.get(n,0)+1
        if names[n]>1:col['name']=f'{n} ({names[n]})'
    return out


def column_limits(columns, name, width=float('inf')):
    """Midpoints between printed heading anchors, not the next word's left edge.

    For nongridded PDFs. When a printed grid exists, we prefer the grid edges.
    """
    idx=next((i for i,c in enumerate(columns) if c['name']==name),None)
    if idx is None:return 0,0
    starts=[c['x'] for c in columns]
    left=(starts[idx-1]+starts[idx])/2 if idx else max(0,starts[0]-18)
    right=(starts[idx]+starts[idx+1])/2 if idx+1<len(starts) else width
    return left,right


def words_in_column(words,y,columns,name,tol=5, width=float('inf')):
    """Preserve sparse cells by using each header's own positional band."""
    left,right=column_limits(columns,name,width)
    return text_of([w for w in words if left<=w['x0']<right and abs(w['top']-y)<=tol])


def add_implicit_task_type(cols, uom_x):
    """En algunas tareas el tipo Part/Misc aparece sin título impreso.

    Se conserva en 'Tipo' y se documenta como columna inferida,
    sin sustituir ni borrar ningún encabezado existente.
    """
    if any(norm(c['name'])=='tipo' for c in cols):return cols,[]
    x=uom_x-60
    if not any(x-8<=c['x']<=x+8 for c in cols):
        return sorted([*cols,{'name':'Tipo','x':x}],key=lambda c:c['x']),['Tipo']
    return cols,[]


def find_task_headers(pages, task, next_task=None):
    """Lee encabezado real del bloque Task, incluso si inicia en otra página."""
    for pn in range(task['start_page'],len(pages)+1):
        if next_task and pn>next_task['start_page']:break
        for d in pages[pn-1]:
            if norm(d['text'])!='description' or d['x0']<100:continue
            if pn==task['start_page'] and d['top']<task['start_y']:continue
            if next_task and pn==next_task['start_page'] and d['top']>=next_task['start_y']:continue
            nearby=[w for w in pages[pn-1] if abs(w['top']-d['top'])<=7]
            if not any(norm(w['text'])=='quantity' for w in nearby):continue
            if not any(norm(w['text']) in ('ext','extprice','extamt') for w in nearby):continue
            cols=header_columns(nearby)
            if not any(norm(c['name'])=='descriptionrefnumber' for c in cols):
                # Si la impresión usa otros nombres, seguimos conservándolos.
                if not any(norm(c['name'])=='description' for c in cols):continue
            return cols
    return []

def make_table(task_info, records, columns, inferred=None):
    """Construye DataFrame con TODOS los encabezados, aunque no haya filas."""
    labels=['pagina']+[c['name'] for c in columns]
    # Un mismo PDF puede imprimir un título repetido; se le da sufijo (2) sin suprimirlo.
    df=pd.DataFrame(records,columns=labels).reset_index(drop=True)
    return {'id':str(task_info['task']),'titulo':task_info.get('title',''),
            'codigo':task_info.get('code',''),'inicio':task_info['start_page'],
            'fin':task_info['end_page'],'datos':df,
            'encabezados_pdf':[c['name'] for c in columns if c['name'] not in (inferred or [])],
            'columnas_inferidas':inferred or []}

# ESTRUCTURA 1: Secciones de tareas repetidas, con la tabla principal continuando en varias páginas.
def parse_por_tareas(pdf):
    tareas=[]; pages=[]
    for pn,page in enumerate(pdf.pages,1):
        words=page.extract_words(x_tolerance=1,y_tolerance=3,keep_blank_chars=False)
        pages.append(words)
        for w in words:
            if not RE_TASK.match(w['text']) or w['x0']>100: continue
            nums=[z for z in words if abs(z['top']-w['top'])<=3.5 and w['x1']<=z['x0']<=w['x0']+80 and z['text'].isdigit()]
            if not nums: continue
            index=int(min(nums,key=lambda z:z['x0'])['text'])
            # Captura texto de encabezado, no etiquetas de proveedor ni nombres de archivo.
            header_line=[z for z in words if abs(z['top']-w['top'])<=3.5]
            code=text_of([z for z in header_line if w['x0']+65 <= z['x0'] < w['x0']+145])
            title=text_of([z for z in header_line if w['x0']+145 <= z['x0'] < 470])
            tareas.append({'task':index,'code':code,'title':title,'start_page':pn,'start_y':w['top']})
    if not tareas:
        return []
    # Coordenadas de cantidad, precio, importe y tipo, para NO alterar
    # la identificación de filas que ya funcionaba en el Motor 02.
    cols=None
    for words in pages:
        for d in words:
            if norm(d['text'])!='description' or d['x0']<110:continue
            adj=[w for w in words if abs(w['top']-d['top'])<=8]
            def get(k):
                a=[w for w in adj if norm(w['text'])==norm(k)]
                return min(a,key=lambda z:abs(z['top']-d['top']))['x0'] if a else None
            q=get('quantity'); price=get('price'); ext=get('ext'); uom=get('u/m')
            if None not in (q,price,ext,uom):
                cols={'description':d['x0'],'tipo':uom-60,'uom':uom,
                      'quantity':q,'price':price,'ext':ext}
                break
        if cols:break
    if not cols:return []
    tables=[]
    for i,task in enumerate(tareas):
        nxt=tareas[i+1] if i+1<len(tareas) else None
        headers=find_task_headers(pages,task,nxt)
        if not headers:
            # Conservamos el esquema completo aun si el encabezado de esta
            # tarea fue cortado por un salto de página.
            headers=find_task_headers(pages,tareas[0],tareas[1] if len(tareas)>1 else None)
        headers,implicit=add_implicit_task_type(headers,cols['uom'])
        gathered=[]; stopped=False; last_page=task['start_page']
        end_page = nxt['start_page'] if nxt else len(pages)
        for pn in range(task['start_page'],end_page+1):
            if pn>len(pages): break
            words=pages[pn-1]
            lower=task['start_y']+5 if pn==task['start_page'] else 0
            upper=nxt['start_y'] if nxt and pn==nxt['start_page'] else float('inf')
            if upper<=lower:continue
            scoped=[w for w in words if lower<=w['top']<upper]
            subtotal_y=[w['top'] for w in scoped if norm(w['text']).startswith('subtotals') and w['x0']>250]
            if subtotal_y:
                scoped=[w for w in scoped if w['top']<min(subtotal_y)-4]
                stopped=True
            if not scoped:
                if stopped: break
                continue
            qitems=[w for w in scoped if cols['quantity']-6<=w['x0']<cols['quantity']+45 and is_money(w['text'])]
            for q in sorted(qitems,key=lambda w:w['top']):
                pri=[w for w in close_words(scoped,q['top'],cols['price']-25,cols['ext']-5,6) if is_money(w['text'])]
                ext=[w for w in close_words(scoped,q['top'],cols['ext']-6,1000,6) if is_money(w['text'])]
                if not pri or not ext: continue
                pr=min(pri,key=lambda w:abs(w['x0']-cols['price']))
                ex=min(ext,key=lambda w:abs(w['x0']-cols['ext']))
                typ=close_words(scoped,q['top'],cols['tipo']-4,cols['uom']-4,3.5)
                unit=close_words(scoped,q['top'],cols['uom']-4,cols['quantity']-6,6)
                gathered.append({'pagina':pn,'y':q['top'],'Cantidad':q['text'],'Precio':pr['text'],
                                 'Importe':ex['text'],'Tipo':text_of(typ),'U/M':text_of(unit),'_scope':scoped})
            last_page=pn
            if stopped:break
        # Mantener la descripción y agrupación multipágina del Motor 02,
        # pero emitir TODAS las columnas que declara el PDF.
        converted=[]
        for k,row in enumerate(gathered):
            same_pg=[r for r in gathered[k+1:] if r['pagina']==row['pagina']]
            next_y=same_pg[0]['y'] if same_pg else float('inf')
            desc_words=[w for w in row['_scope'] if cols['description']-6<=w['x0']<cols['tipo']-4
                        and row['y']-6<=w['top']<next_y-4]
            desc_words=[w for w in desc_words if norm(w['text']) not in ('description','number')]
            desc=text_of(desc_words)
            out={'pagina':row['pagina']}
            for h in headers:
                label=h['name']; role=norm(label)
                if role in ('descriptionrefnumber','description'):
                    out[label]=desc
                elif role=='quantity':out[label]=row['Cantidad']
                elif role=='price':out[label]=row['Precio']
                elif role in ('extprice','extamt','extension','amount'):out[label]=row['Importe']
                elif role in ('um','uom'):out[label]=row['U/M']
                elif role=='tipo':out[label]=row['Tipo']
                else:
                    out[label]=words_in_column(row['_scope'],row['y'],headers,label)
            converted.append(out)
        task['end_page']=last_page if stopped else end_page
        tables.append(make_table(task,converted,headers,implicit))
    return tables

# ESTRUCTURAS 2-4: Analizar columnas de acuerdo a su encabezado impreso, no al proveedor.
def detect_column_header(page):
    words=page.extract_words(x_tolerance=2,y_tolerance=3)
    for line in grouped_lines(words):
        row=line['words']; tokens=[norm(w['text']) for w in row]
        if 'description' not in tokens: continue
        d=next(w for w in row if norm(w['text'])=='description')
        def get(*names):
            return next((w['x0'] for w in row if norm(w['text']) in names),None)
        x={
            'description':d['x0'], 'item':get('item','type'),
            'code':get('laborpart'), 'line':get('line'),
            'uom':get('uom'), 'quantity':get('quantity','hrsqty'),
            'rate':get('rate','rateprice'), 'amount':get('amount','ext','extamt','extension'),
            'mechanic':get('mechanic'), 'list':get('list'),
            'product':get('product'),'labor':get('labor'),
        }
        if x['product'] is not None and x['labor'] is not None and x['amount'] is not None and x['quantity'] is not None:
            return {'tipo':'PRODUCTO_LABOR','y':line['y'],'x':x,'words':words,
                    'headers':header_columns(row)}
        if None not in (x['description'],x['quantity'],x['rate'],x['amount']):
            typ='CODIFICADA' if x['item'] is not None and (x['code'] is not None or x['uom'] is not None) else 'POR_CONCEPTO'
            return {'tipo':typ,'y':line['y'],'x':x,'words':words,
                    'headers':header_columns(row)}
    return None


def choose_right(words,y,a,b,need_money=False,tol=5):
    cand=[w for w in words if a-6<=w['x0']<b and abs(w['top']-y)<=tol and (is_money(w['text']) if need_money else is_num(w['text']))]
    return min(cand,key=lambda w:abs(w['x0']-a))['text'] if cand else ''


def clean_cell(value):
    """Preserve characters and values; normalize only PDF cell line wrapping."""
    return re.sub(r'\s+', ' ', '' if value is None else str(value)).strip()


def table_from_drawn_grid(page, header):
    """Use real vertical/horizontal cell borders on ruled tables.

    Returns None when there is no trustworthy grid (spatial fallback follows).
    This is a generic layout strategy, independent of any invoice/vendor.
    """
    if len(page.lines)+len(page.rect_edges)<10:
        return None
    try:
        found=page.find_tables(table_settings={
            'vertical_strategy':'lines', 'horizontal_strategy':'lines',
            'snap_tolerance':3, 'join_tolerance':3, 'intersection_tolerance':4,
            'text_x_tolerance':2,'text_y_tolerance':3})
    except Exception:
        return None
    for table in found:
        x0, top, x1, bottom=table.bbox
        if not (top-4<=header['y']<=bottom+4):continue
        extracted=table.extract(x_tolerance=2,y_tolerance=3)
        if not extracted or len(extracted)<2:continue
        # Find the printed header inside the table rather than assuming row zero.
        head_idx=None
        for j,row in enumerate(extracted[:4]):
            keys=[norm(clean_cell(v)) for v in row]
            if any(k=='description' or k.startswith('descriptionref') for k in keys) and \
               (any(k in ('extamt','extprice','extension','amount') for k in keys)):
                head_idx=j;break
        if head_idx is None:continue
        hdr=extracted[head_idx]
        names=[];seen={}
        for k,name in enumerate(hdr):
            raw=clean_cell(name) or f'Columna sin encabezado {k+1}'
            seen[raw]=seen.get(raw,0)+1
            names.append(raw if seen[raw]==1 else f'{raw} ({seen[raw]})')
        if len(names)<4:continue
        rows=[]; bounds=[]
        for j,line in enumerate(extracted[head_idx+1:],head_idx+1):
            vals=[clean_cell(v) for v in list(line)[:len(names)]]
            vals+=['']*(len(names)-len(vals))
            if not any(vals):continue
            # Conservar la lectura física completa y la ubicación de cada fila.
            rows.append(dict(zip(names,vals)))
            bounds.append(table.rows[j].bbox)
        return {'rows':rows,'names':names,'bbox':table.bbox,'bounds':bounds}
    return None



# LABORATORIO 07: interpretacion de bloques sobre una rejilla ya extraida.
# No se cambian las reglas de deteccion de familias ni el motor POR_TAREAS.
# Siempre se conserva la cuadricula fisica original en filas_pdf_originales.
def _resumen_coords_en_pagina(page, pn, resumen):
    """Limite superior del resumen global confirmado por parse_resumen_final()."""
    if resumen is None or resumen['pagina']!=pn:
        return None
    _,anchored=_summary_anchors_and_rows(page,pn)
    expected=[(str(r['Concepto']),str(r['Importe']))
              for _,r in resumen['datos'].iterrows()]
    used=set(); ys=[]
    for concept,amount in expected:
        for idx,row in enumerate(anchored):
            if idx not in used and row['Concepto']==concept and row['Importe']==amount:
                ys.append(row['y']);used.add(idx);break
    return min(ys) if ys else None


def _informacion_paralela_al_resumen(page, pn, resumen, start_y):
    """Texto a la izquierda del resumen, no fusionado con sus filas contables."""
    if start_y is None or resumen is None or resumen['pagina']!=pn:
        return []
    _,anchored=_summary_anchors_and_rows(page,pn)
    closes=[r['y'] for r in anchored
            if r['Concepto']==resumen['cierre'] and
            r['Importe']==str(resumen['datos'].iloc[-1]['Importe'])]
    end_y=max(closes) if closes else start_y+110
    words=page.extract_words(x_tolerance=1,y_tolerance=3,keep_blank_chars=False)
    left=[w for w in words if start_y-8<=w['top']<=end_y+8
          and w['x1']<page.width*.52]
    return [{'pagina':pn,'Texto':text_of(line['words'])}
            for line in grouped_lines(left,tolerance=3.5)
            if text_of(line['words'])]


def interpretar_bloques_de_celdas(page, pn, header, grid, resumen_final):
    """Separa partidas, subtotal local, cargo, contexto y resumen global.

    Usa solo encabezados, contenido impreso, posicion y secuencia de bloques.
    Si una fila no es clasificable, se conserva para inspeccion, no se descarta.
    La rejilla completa tambien se devuelve intacta como evidencia.
    """
    original=pd.DataFrame([{'pagina':pn,**r} for r in grid['rows']],
                          columns=['pagina']+grid['names'])
    encabezados=[h['name'] for h in header['headers']]
    amount_cols=[k for k in grid['names'] if norm(k) in ('amount','extamt','extprice','extension')]
    if not amount_cols:
        return None
    amount_col=amount_cols[-1]
    quantity_cols=[k for k in grid['names'] if norm(k) in ('quantity','hrsqty')]
    rate_cols=[k for k in grid['names'] if norm(k) in ('rate','rateprice')]
    desc_cols=[k for k in grid['names'] if norm(k) in ('description','descriptionrefnumber')]
    item_cols=[k for k in grid['names'] if norm(k) in ('item','type')]

    resumen_y=_resumen_coords_en_pagina(page,pn,resumen_final)
    # Activar la nueva interpretacion SOLO con evidencia positiva de una
    # tabla de detalle seguida de un subtotal local independiente.
    # Otras cuadriculas se leen exactamente como en Laboratorio 06.
    seen_detail=False; local_closure=False
    for raw,bbox in zip(grid['rows'],grid['bounds']):
        if resumen_y is not None and bbox[1]>=resumen_y-9:
            break
        amount=str(raw.get(amount_col,'')).strip()
        labels=[str(v).strip() for k,v in raw.items()
                if k!=amount_col and str(v).strip()]
        q=' '.join(str(raw.get(c,'')) for c in quantity_cols).strip()
        rate=' '.join(str(raw.get(c,'')) for c in rate_cols).strip()
        if (is_money(amount) and len(labels)==1 and
            norm(labels[0]) in ('subtotal','subtotals','total','totals')
            and not is_num(q) and not is_num(rate) and seen_detail):
            local_closure=True
            break
        if (is_money(amount) and (any(str(raw.get(c,'')).strip() for c in desc_cols+item_cols))
                and (is_num(q) or is_num(rate))):
            seen_detail=True
    if not local_closure:
        return None
    # Resultados separados; una sola fila Subtotal tambien es una subtabla.
    principales=[]; subtablas=[]; cargos=[]; contexto=[]; sin_clasificar=[]
    hubo_subtotal=False
    for raw,bbox in zip(grid['rows'],grid['bounds']):
        y0=bbox[1]
        # La zona derecha puede contener un resumen aun si comparte fila fisica
        # con datos del vehiculo a la izquierda. Sus filas ya las lee el resumen.
        if resumen_y is not None and y0>=resumen_y-9:
            continue
        amount=raw.get(amount_col,'').strip()
        q=' '.join(raw.get(c,'') for c in quantity_cols).strip()
        rate=' '.join(raw.get(c,'') for c in rate_cols).strip()
        desc=' '.join(raw.get(c,'') for c in desc_cols).strip()
        item=' '.join(raw.get(c,'') for c in item_cols).strip()
        other=[v.strip() for k,v in raw.items() if k!=amount_col and v.strip()]
        text=' '.join(other).strip()
        # Unicamente una etiqueta de cierre, sin cantidad/tarifa de partida.
        # Primero se distingue del subtotal general usando su posicion.
        local_subtotal=(is_money(amount) and not is_num(q)
                        and not is_num(rate)
                        and len(other)==1 and norm(other[0]) in ('subtotal','subtotals','total','totals'))
        if local_subtotal:
            subtablas.append({'pagina':pn,'Concepto':other[0],'Importe':amount})
            hubo_subtotal=True
        elif is_money(amount) and hubo_subtotal and desc and not is_num(q) and not is_num(rate):
            # Cargos impresos tras el cierre del detalle y antes del resumen.
            # No se interpretan como nueva partida ni se suman.
            cargos.append({'pagina':pn,'Concepto':text,'Importe':amount})
        elif is_money(amount) and (desc or item) and not hubo_subtotal:
            principales.append({'pagina':pn,**raw})
        elif amount:
            sin_clasificar.append({'pagina':pn,'Texto':text,'Importe':amount,
                                   'Motivo':'Importe fuera de estructura confiable'})
        elif text:
            token=norm(text.split(':',1)[0]) if ':' in text else ''
            etiqueta=(token.upper() if token in ('concern','cause','correction','complaint',
                                                'reason','status') else 'CONTEXTO')
            # Continuaciones de descripcion conservadas separadas y unidas
            # logicamente cuando la geometria ofrece suficiente evidencia.
            if not item and desc and principales and not hubo_subtotal and etiqueta=='CONTEXTO':
                principales[-1][desc_cols[0]]=(str(principales[-1].get(desc_cols[0],'')).strip()+' '+desc).strip()
                etiqueta='CONTINUACION'
            contexto.append({'pagina':pn,'Tipo':etiqueta,'Texto':text})

    # Se mantienen TODOS los encabezados impresos, incluyendo los vacios.
    # Las columnas de rejilla sin rotulo solo pasan a la vista principal si
    # contienen datos de alguna partida; las otras siguen en evidencia física.
    inferred=[k for k in grid['names'] if k not in encabezados
              and any(str(r.get(k,'')).strip() for r in principales)]
    cols=list(dict.fromkeys(encabezados+inferred))
    df=pd.DataFrame([{'pagina':r['pagina'],**{k:r.get(k,'') for k in cols}}
                     for r in principales],columns=['pagina']+cols)
    return {
        'principal':df,'encabezados_pdf':encabezados,
        'columnas_inferidas':inferred,'filas_pdf_originales':original,
        'subtotales':subtablas,'cargos':cargos,'contexto':contexto,
        'sin_clasificar':sin_clasificar,
        'informacion_auxiliar':_informacion_paralela_al_resumen(page,pn,resumen_final,resumen_y)
    }

def parse_spatial_table(page, pn, header, limit=None):
    """Devuelve filas de la tabla principal, sin leer un subtotal como nueva partida."""
    typ=header['tipo']; x=header['x']; words=header['words']; y0=header['y']+8
    y1=min(page.height,limit) if limit is not None else page.height
    groups=grouped_lines([w for w in words if y0<w['top']<y1],tolerance=3.5)
    amount=x['amount']; candidates=[]
    for g in groups:
        # La columna final (Amount, Ext Amt o Extension) contiene una sola cifra por partida.
        am=[w for w in g['words'] if amount-17<=w['x0']<=page.width+5 and is_money(w['text'])]
        if not am:continue
        at=min(am,key=lambda w:abs(w['x0']-amount))
        if abs(at['x0']-amount)>65: continue
        earlier=[w for w in g['words'] if w['x0']<amount-20]
        combined=text_of(earlier)
        if typ=='CODIFICADA':
            # Without a printed grid, real item types occupy the Type column.
            # 'L: Labor' belongs to the type legend, not an invoice line.
            typ_words=[w['text'].strip() for w in g['words']
                       if x['item']-12<=w['x0']<((x['item']+x['line'])/2 if x['line'] is not None else x['description'])]
            if not any(re.fullmatch(r'[A-Za-z]{1,3}',v) for v in typ_words):continue
        if RE_SUMMARY.search(combined) and (typ!='CODIFICADA' or not any(
               re.fullmatch(r'[A-Za-z]{1,3}',w['text'])
               for w in g['words'] if x['item'] is not None and x['item']-12<=w['x0']<x['item']+22)):
            continue
        if re.search(r'\b(?:page\s+\d+\s+of|license plate|vin|unit number)\b',combined,re.I):continue
        candidates.append((g['y'],at,earlier))
    rows=[]
    for i,(y,amt,earlier) in enumerate(candidates):
        next_y=candidates[i+1][0] if i+1<len(candidates) else page.height
        # El nombre del concepto se obtiene de las bandas de texto ubicadas entre columnas.
        numeric_break=min([v for v in [x['quantity'],x['uom'],x['rate'],x['product']] if v is not None],default=amount)
        # En PRODUCTO_LABOR la descripción termina antes de mechanic/uom.
        if typ=='PRODUCTO_LABOR':
            desc_right=min([v for v in (x['mechanic'],x['uom']) if v is not None],default=numeric_break)-3
        else:
            desc_right=min([v for v in (x['uom'],x['quantity']) if v is not None],default=numeric_break)-6
        left=column_limits(header['headers'],'Description')[0]
        inline=[w for w in earlier if left<=w['x0']<desc_right]
        desc=text_of(inline)
        # Continuaciones que aparecen bajo la misma partida.
        if i+1<len(candidates):
            interval=[w for w in words if y+4<w['top']<next_y-5 and left<=w['x0']<desc_right]
            lines=[line for line in grouped_lines(interval) if line['y']<next_y-5]
            tail=' '.join(text_of(line['words']) for line in lines)
            # Un bloque colocado inmediatamente encima de la cantidad sin descripción
            # pertenece a la siguiente partida, no se pega por error a la anterior.
            next_inline=[w for w in candidates[i+1][2] if left<=w['x0']<desc_right]
            if tail and (desc or next_inline) and not (typ=='PRODUCTO_LABOR' and not next_inline):
                desc=(desc+' '+tail).strip()
        if not desc and i>0:
            py=candidates[i-1][0]
            pref=[w for w in words if py+5<w['top']<y-3 and left<=w['x0']<desc_right]
            desc=text_of(pref)
        item_left=x['item']-4 if x['item'] is not None else -1
        item_right=(x['line'] or x['code'] or x['description'])-3 if x['item'] is not None else -1
        label=text_of(close_words(earlier,y,item_left,item_right)) if x['item'] is not None else ''
        label_value=label
        code_right=x['description']-4
        code_left=x['code']-4 if x['code'] is not None else -1
        code=text_of(close_words(earlier,y,code_left,code_right)) if x['code'] is not None else ''
        q=choose_right(words,y,x['quantity'],x['rate'] if typ!='PRODUCTO_LABOR' else (x['list'] or x['product']),False) if x['quantity'] is not None else ''
        rate=choose_right(words,y,x['rate'],x['amount'],False) if x['rate'] is not None else ''
        uom=text_of(close_words(earlier,y,x['uom']-4,x['quantity']-3)) if x['uom'] is not None else ''
        if typ=='PRODUCTO_LABOR':
            rate=choose_right(words,y,x['list'],x['product'],False) if x['list'] is not None else ''
            product=choose_right(words,y,x['product'],x['labor'],False)
            labor=choose_right(words,y,x['labor'],x['amount'],False)
        else: product=labor=''
        # Validación semántica: no confundir un resumen lateral con una fila.
        if not (desc or label or code):continue
        if not q and not rate and not product and not labor and not desc:
            continue
        # Mostrar nombres ORIGINALES del encabezado, no un subconjunto
        # normalizado. Las columnas sin datos también se incluyen.
        data={'pagina':pn}
        for col in header['headers']:
            label=col['name']; key=norm(label)
            if key in ('description','descriptionrefnumber'):
                value=desc
            elif key in ('quantity','hrsqty'):
                value=q
            elif key in ('extamt','extprice','amount','extension'):
                value=amt['text']
            elif key in ('rate','rateprice'):
                value=rate
            elif key in ('um','uom'):
                value=uom
            elif key in ('item','type'):
                value=label_value
            elif key=='laborpart':
                value=words_in_column(header['words'],y,header['headers'],label)
            elif key=='listprice':
                value=rate if typ=='PRODUCTO_LABOR' else words_in_column(header['words'],y,header['headers'],label)
            elif key=='product' and typ=='PRODUCTO_LABOR':value=product
            elif key=='labor' and typ=='PRODUCTO_LABOR':value=labor
            else:
                value=words_in_column(header['words'],y,header['headers'],label)
            data[label]=value
        rows.append(data)
    return rows


def parse_tabla_columnas(pdf, resumen_final=None):
    all_tables=[]; current=None; strategy=None
    bloques={'subtablas':[],'cargos_adicionales':[],
             'contexto_tablas':[],'informacion_auxiliar':[],'sin_clasificar':[]}
    for pn,page in enumerate(pdf.pages,1):
        head=detect_column_header(page)
        if head:
            # Un encabezado reiterado en la siguiente página puede continuar la misma tabla.
            same=current is not None and head['tipo']==strategy and pn==current['fin']+1
            if not same:
                current={'id':str(len(all_tables)+1),'titulo':'Tabla principal',
                         'codigo':'','inicio':pn,'fin':pn,
                         'datos':pd.DataFrame(columns=['pagina']+[h['name'] for h in head['headers']]),
                         'encabezados_pdf':[h['name'] for h in head['headers']],
                         'columnas_inferidas':[]}
                all_tables.append(current)
            strategy=head['tipo']
        elif current is None: continue
        else:
            # En una continuación sin encabezado, emplear los mismos límites de columnas,
            # pero no inventar datos si la página solo tiene totales / texto administrativo.
            head={'tipo':strategy,'y':0,'x':last_header['x'],
                  'words':page.extract_words(x_tolerance=2,y_tolerance=3),
                  'headers':last_header['headers']}
        last_header=head
        # First, retain exact cell/column geometry when the PDF draws a grid.
        # When there is no grid, continue with the established spatial parser.
        grid=table_from_drawn_grid(page,head) if detect_column_header(page) else None
        interpretacion=(interpretar_bloques_de_celdas(page,pn,head,grid,resumen_final)
                        if grid is not None else None)
        if interpretacion is not None:
            # Los datos originales siguen disponibles para auditoria.
            raw=interpretacion['filas_pdf_originales']
            old_raw=current.get('filas_pdf_originales')
            current['filas_pdf_originales']=(pd.concat([old_raw,raw],ignore_index=True)
                                              if old_raw is not None else raw)
            pdf_cols=list(dict.fromkeys(current.get('encabezados_pdf',[])+
                                         interpretacion['encabezados_pdf']))
            current['encabezados_pdf']=pdf_cols
            inferred=list(dict.fromkeys(current.get('columnas_inferidas',[])+
                                         interpretacion['columnas_inferidas']))
            current['columnas_inferidas']=inferred
            current['metodo_lectura']='CELDAS_PDF_INTERPRETADAS'
            current['datos']=current['datos'].reindex(columns=['pagina']+pdf_cols+inferred)
            found=interpretacion['principal'].to_dict('records')
            if interpretacion['subtotales']:
                sub=interpretacion['subtotales']
                bloques['subtablas'].append({
                    'task_id':current['id'],'tabla_id':current['id'],'pagina':pn,
                    'datos':pd.DataFrame(sub,columns=['pagina','Concepto','Importe']),
                    'completa':True,'origen':'SUBTOTAL_IMPLICITO','tipo':'IMPLICITA'})
            if interpretacion['cargos']:
                bloques['cargos_adicionales'].append({
                    'tabla_id':current['id'],'pagina':pn,
                    'datos':pd.DataFrame(interpretacion['cargos'],
                                         columns=['pagina','Concepto','Importe'])})
            if interpretacion['contexto']:
                bloques['contexto_tablas'].append({
                    'tabla_id':current['id'],'pagina':pn,
                    'datos':pd.DataFrame(interpretacion['contexto'],
                                         columns=['pagina','Tipo','Texto'])})
            bloques['informacion_auxiliar'].extend(interpretacion['informacion_auxiliar'])
            bloques['sin_clasificar'].extend(interpretacion['sin_clasificar'])
        elif grid is not None:
            # Respaldo: si faltan criterios para separar bloques, conservar
            # el comportamiento de Laboratorio 06 y todas las celdas.
            found=[{'pagina':pn,**r} for r in grid['rows']]
            pdf_cols=list(dict.fromkeys(current.get('encabezados_pdf',[])+grid['names']))
            current['encabezados_pdf']=pdf_cols
            current['metodo_lectura']='CELDAS_PDF'
            current['datos']=current['datos'].reindex(columns=['pagina']+pdf_cols)
        else:
            found=parse_spatial_table(page,pn,head)
            # Una pagina vacia de continuacion no reemplaza el metodo real.
            if found or head['y']>0:
                current['metodo_lectura']='COORDENADAS'
        if found:
            current['fin']=pn
            current['datos']=pd.concat([current['datos'],pd.DataFrame(found)],ignore_index=True)
        elif current is not None and head['y']>0:
            current['fin']=pn
    return all_tables, strategy, bloques



# CAPA ADICIONAL: subtablas economicas asociadas a cada Task.
# El extractor solo utiliza marcas estructurales y posicion de palabras;
# no depende de nombres de archivo, talleres, clientes ni importes esperados.
# IMPORTANTE: no se insertan estas cifras como nuevas filas de la tabla principal.
def _task_marker(line_words, kinds):
    """Ubica secuencias Task <n> Subtotals/Totals dentro de un renglon."""
    ws=sorted(line_words,key=lambda w:w['x0'])
    for i in range(len(ws)-2):
        a,b,c=ws[i:i+3]
        if norm(a['text']) in ('task','job','operation') and b['text'].isdigit() and norm(c['text']) in kinds:
            return {'task':str(int(b['text'])),'start':i,'end':i+3,'words':ws,
                    'left':a['x0'],'right':c['x1']}
    return None


def _amount_on_line(line_words, minimum_x):
    """Lee el importe tal como esta impreso; conserva ceros y negativos en parentesis."""
    candidates=[w for w in line_words if w['x0']>=minimum_x and is_money(w['text'])]
    return max(candidates,key=lambda w:w['x1']) if candidates else None


def parse_subtablas_por_tarea(pdf, tablas_principales):
    """Extrae subtablas Task N Subtotals...Task N Totals.

    Las tablas principales son la referencia para asociar numeros de Task,
    pero sus DataFrames no se tocan. El esquema de salida es independiente:
    cada Task tiene a lo sumo una subtabla por marcador encontrado.
    Si no hay marcador (p. ej. una Task Deferred), no se inventa subtabla.
    """
    valid_ids={str(t['id']) for t in tablas_principales}
    blocks=[]; avisos=[]
    for pn,page in enumerate(pdf.pages,1):
        ws=page.extract_words(x_tolerance=1,y_tolerance=3,keep_blank_chars=False)
        lines=grouped_lines(ws,tolerance=3.5)
        for i,line in enumerate(lines):
            marker=_task_marker(line['words'],{'subtotals','subtotal'})
            if marker is None:continue
            tid=marker['task']
            if tid not in valid_ids:
                avisos.append(f'Pagina {pn}: subtotal de Task {tid} sin tabla principal reconocida.')
                continue
            # Obtener la primera etiqueta justo despues de "Subtotals:".
            first_label=[w for w in marker['words'][marker['end']:] if not is_money(w['text'])]
            first_x=min((w['x0'] for w in first_label),default=marker['right']+10)
            label_min=max(marker['left']+10,first_x-70)
            records=[]; complete=False
            for j in range(i,min(i+25,len(lines))):
                current=lines[j]
                if current['y']-line['y']>210:break
                cur_words=sorted(current['words'],key=lambda w:w['x0'])
                if j>i and _task_marker(cur_words,{'subtotals','subtotal'}):break
                if j>i:
                    # Inicio de otra tarea (encabezado a la izquierda).
                    if any(norm(w['text']) in ('task','job','operation') and w['x0']<110
                           and any(z['text'].isdigit() and 0<=z['x0']-w['x1']<=80
                                   for z in cur_words) for w in cur_words):break
                end_marker=_task_marker(cur_words,{'total','totals'})
                amount=_amount_on_line(cur_words,max(marker['left']+60,label_min+35))
                if j==i:
                    label_words=[w for w in cur_words if w['x0']>marker['right']+3 and
                                 (amount is None or w['x1']<amount['x0']-1)]
                elif end_marker:
                    label_words=cur_words[end_marker['start']:end_marker['end']]
                else:
                    label_words=[w for w in cur_words if label_min<=w['x0'] and
                                 (amount is None or w['x1']<amount['x0']-1)]
                label=' '.join(w['text'] for w in label_words).strip()
                if amount is not None and label:
                    records.append({'pagina':pn,'Concepto':label,'Importe':amount['text']})
                if end_marker:
                    if end_marker['task']==tid:
                        complete=True
                    else:
                        avisos.append(f'Pagina {pn}: total de Task {end_marker["task"]} no coincide con subtotal de Task {tid}.')
                    break
            if not records:
                avisos.append(f'Pagina {pn}: marcador de subtotales Task {tid} sin filas legibles.')
            if not complete:
                avisos.append(f'Pagina {pn}: subtotales de Task {tid} sin cierre Task {tid} Totals verificable.')
            blocks.append({'task_id':tid,'pagina':pn,
                           'datos':pd.DataFrame(records,columns=['pagina','Concepto','Importe']),
                           'completa':complete,'origen':'SUBTOTALES_DE_TASK'})
    # Si una Task tuviera dos bloques reales, mantenerlos, no fusionarlos silenciosamente.
    counts={}
    for b in blocks:counts[b['task_id']]=counts.get(b['task_id'],0)+1
    for tid,count in counts.items():
        if count>1:avisos.append(f'Task {tid} presenta {count} bloques de subtotales; revisar sin fusionar automaticamente.')
    return blocks,avisos

# CAPA ADICIONAL: resumen economico GLOBAL impreso al final del documento.
# No es una subtabla de Task. Se conserva independientemente de las partidas,
# de la cantidad de tablas principales y de sus subtotales internos.
# Se reconoce por geometria y las etiquetas impresas, nunca por nombres de proveedor.

def _summary_label_for_amount(words, money, page_width):
    """Selecciona SOLO el texto de la columna conceptual del resumen.

    No adjunta la leyenda Type Legend a la izquierda ni Payment Method.
    Usa tolerancia vertical porque en PDF la cifra y su etiqueta pueden tener
    un offset de varios puntos (p.ej. 'Labor' y '$242.40').
    """
    left=page_width*0.52
    candidates=[w for w in words if left<=w['x0'] and w['x1']<=money['x0']-2
                and abs(w['top']-money['top'])<=7.5]
    return text_of(candidates)


def _is_final_total_label(label):
    """Cierre del documento, no 'Task N Totals' ni 'Subtotal' de una tabla."""
    cleaned=re.sub(r'\s+', ' ', str(label or '')).strip().lower().rstrip(':')
    compact=norm(cleaned)
    return compact in {
        'invoicedtotal','invoicetotal','estimatetotal',
        'total','grandtotal','finaltotal','totaldue',
        'balancedue','amountdue','amountpayable','totalamount',
        'totalinvoice','totalestimate','nettotal'
    }


def _summary_anchors_and_rows(page, pn):
    """Detecta renglones concepto + importe en el area derecha del PDF.

    Una cifra sin etiqueta NO se descarta de la factura: solo no se asigna
    automaticamente al bloque de resumen. No se inventan importes.
    """
    words=page.extract_words(x_tolerance=1,y_tolerance=3,keep_blank_chars=False)
    monetary=[w for w in words if w['x1']>=page.width*.88 and is_money(w['text'])]
    rows=[]
    for money in monetary:
        label=_summary_label_for_amount(words,money,page.width)
        if not label or not re.search('[A-Za-z]',label):continue
        # Evitar copias de un importe ya reconocido en la misma linea.
        if any(abs(r['y']-money['top'])<2 and abs(r['x1']-money['x1'])<6 for r in rows):continue
        rows.append({'pagina':pn,'y':money['top'],'x1':money['x1'],
                     'Concepto':label,'Importe':money['text']})
    rows.sort(key=lambda r:r['y'])
    return words,rows


def _additional_summary_label_lines(words,rows,start_y,end_y,page_width):
    """Adjunta un renglon envuelto como 'SURCHARGE:' a su concepto anterior."""
    if not rows:return rows
    lines=grouped_lines([w for w in words if start_y-2<=w['top']<=end_y+2],tolerance=2.4)
    for line in lines:
        y=line['y']
        if any(abs(y-r['y'])<=7.5 for r in rows):continue
        # Solo se consideran continuaciones a la derecha y SIN importe.
        right=[w for w in line['words'] if w['x0']>=page_width*.52
               and w['x1']<page_width*.84 and not is_money(w['text'])]
        if not right:continue
        continuation=text_of(right)
        if not re.search('[A-Za-z]',continuation):continue
        predecessors=[r for r in rows if 2<y-r['y']<19]
        if not predecessors:continue
        preceding=max(predecessors,key=lambda r:r['y'])
        following=[r for r in rows if r['y']>preceding['y']]
        if following and y>=min(following,key=lambda r:r['y'])['y']-3:continue
        # Un renglon suelto pegado a una fila con importe no se convierte en
        # un nuevo concepto: queda como continuacion exacta del concepto anterior.
        preceding['Concepto']=(preceding['Concepto']+' '+continuation).strip()
    return rows


def parse_resumen_final(pdf):
    """Extrae el resumen global, nunca lo suma a las tablas de detalle.

    Detecta un cierre como 'Invoiced Total', 'Estimate Total' o 'Total'
    acompanado por varias filas economicas alineadas a la derecha.
    Devuelve un solo bloque con sus palabras originales y pagina de origen,
    o None si el bloque no se reconoce con confianza.
    """
    options=[]
    for pn,page in enumerate(pdf.pages,1):
        words,rows=_summary_anchors_and_rows(page,pn)
        for idx,closing in enumerate(rows):
            if not _is_final_total_label(closing['Concepto']):continue
            # Un encabezado 'Totals' delimita la tabla final aunque la Task
            # anterior este muy cerca y comparta la alineacion de precios.
            titles=[]
            for line in grouped_lines(words,tolerance=3.5):
                if closing['y']-270<=line['y']<closing['y']:
                    right=[w for w in line['words'] if w['x0']>=page.width*.5]
                    txt=text_of(right)
                    if norm(txt) in ('totals','summary','summaryofcharges'):
                        titles.append((line['y'],txt))
            title_cutoff,title=(max(titles,key=lambda z:z[0]) if titles else (-float('inf'),''))
            # Se exige un bloque de varias filas (una cifra sola en la cabecera
            # 'Invoice Total' NO es una tabla de resumen).
            selected=[closing]
            last_y=closing['y']
            for previous in reversed(rows[:idx]):
                diff=last_y-previous['y']
                if previous['y']<=title_cutoff+2:break
                # Un resumen puede separar el TOTAL mediante una linea o espacio.
                # Un corte mayor a ~55 pt separa regiones distintas del PDF.
                if diff>55:break
                # Un concepto suele estar a la izquierda del valor en la misma
                # alineacion, pero no se exige que empiece con 'Total'.
                selected.append(previous)
                last_y=previous['y']
            selected=list(reversed(selected))
            if len(selected)<3:continue
            # La lista debe tener al menos dos etiquetas contables mas el total.
            # Evitar confundir una ultima fila de tabla con un resumen.
            if not any(re.search(r'\b(?:parts?|labor|misc|charges?|tax|freight|subtotal|discount|surcharge|exempt|fees?)\b',
                                 r['Concepto'],re.I) for r in selected[:-1]):continue
            # Si en la misma pagina hay varios 'Total', privilegiar el ultimo
            # grupo que cierra el documento, no un subtotal de seccion.
            selected=[dict(row) for row in selected]
            selected=_additional_summary_label_lines(words,selected,selected[0]['y'],closing['y'],page.width)
            rank=(pn, closing['y'],len(selected))
            options.append((rank,{'pagina':pn,'titulo':title,
                'datos':pd.DataFrame([{'pagina':r['pagina'],
                                      'Concepto':r['Concepto'],
                                      'Importe':r['Importe']} for r in selected],
                                      columns=['pagina','Concepto','Importe']),
                'cierre':closing['Concepto'],
                'origen':'RESUMEN_GENERAL_IMPRESO'}))
    return max(options,key=lambda z:z[0])[1] if options else None


def leer_invoice(pdf_file):
    """PDF de cualquier nombre -> tablas principales, subtablas Task y resumen final.
    No calcula cifras, no duplica partidas ni exporta archivos.
    """
    pdf_file=Path(pdf_file)
    if pdf_file.suffix.lower()!='.pdf':
        raise ValueError('Selecciona un archivo PDF.')
    with pdfplumber.open(pdf_file) as pdf:
        if not pdf.pages:
            return {'parser':'NO RECONOCIDO','tablas':[],'subtablas':[],'resumen_final':None,'avisos':['PDF sin páginas.']}
        if sum(len(p.chars) for p in pdf.pages)<20:
            return {'archivo':pdf_file.name,'parser':'REQUIERE OCR','tablas':[],'subtablas':[],'resumen_final':None,
                    'avisos':['El PDF no contiene texto digital suficiente.']}
        resumen_final=parse_resumen_final(pdf)
        tables=parse_por_tareas(pdf)
        bloques={'subtablas':[],'cargos_adicionales':[],
                 'contexto_tablas':[],'informacion_auxiliar':[],'sin_clasificar':[]}
        if tables:
            kind='POR_TAREAS'
            subtablas,avisos_subtablas=parse_subtablas_por_tarea(pdf,tables)
        else:
            tables,kind,bloques=parse_tabla_columnas(pdf,resumen_final)
            subtablas,avisos_subtablas=bloques['subtablas'],[]
        kind=kind if tables else 'NO RECONOCIDO'
        alerts=[] if tables else ['No se encontró una estructura de tablas principales compatible; revisar el PDF.']
        alerts.extend(avisos_subtablas)
        if bloques['sin_clasificar']:
            alerts.append(f"{len(bloques['sin_clasificar'])} renglon(es) con importe sin clasificar; revisar evidencia.")
        return {'archivo':pdf_file.name,'parser':kind,'paginas':len(pdf.pages),
                'tablas':tables,'subtablas':subtablas,'resumen_final':resumen_final,'avisos':alerts,
                'cargos_adicionales':bloques['cargos_adicionales'],
                'contexto_tablas':bloques['contexto_tablas'],
                'informacion_auxiliar':pd.DataFrame(bloques['informacion_auxiliar'],columns=['pagina','Texto']),
                'sin_clasificar':pd.DataFrame(bloques['sin_clasificar'],
                                             columns=['pagina','Texto','Importe','Motivo']),
                'n_partidas':sum(len(t['datos']) for t in tables)}


# -----------------------------------------------------------------------------
# LABORATORIO 08 — ampliación general para encabezados y columnas variantes
# Se incorpora SIN modificar los lectores estables del Laboratorio 07.
# No hay listas de proveedores, nombres de invoice ni patrones por filename.
# -----------------------------------------------------------------------------
_L08_leer_invoice_base = leer_invoice

L08_AMOUNT_RE = re.compile(r'^\(?-?\$?\d[\d,]*(?:\.\d{2})\)?[Tt]?$')
L08_NUMBER_RE = re.compile(r'^\(?-?\$?\d[\d,]*(?:\.\d+)?\)?[Tt]?$')
L08_STOP_RE = re.compile(r'^(?:terms(?:\s+and\s+conditions)?\s*:|i\s+understand\s+that|notice\s*:|\*{2,}\s*note|customer\s+signature|approvedby|please\s+tell\s+us|please\s+remove\s+your|subject\s+to\s+the\s+terms|it\s+is\s+agreed)',re.I)
L08_CLOSE_RE = re.compile(r'\b(?:sub[\s-]*total|totals?|tax|netorder|sales\s*tax|invoice\s*total|amount\s*due|charged\s+to)\b',re.I)
L08_SECTION_RE = re.compile(r'^(?:labor\s+description|misc(?:ellaneous)?\s+charges\s+description|parts\s*/\s*sr\s+no\s+description)\b',re.I)


def l08_is_amount(value):
    return bool(L08_AMOUNT_RE.fullmatch(str(value or '').strip()))


def l08_is_number(value):
    return bool(L08_NUMBER_RE.fullmatch(str(value or '').strip()))


def l08_header_patterns(line, prior_lines):
    """Encabezados según semántica/posición; se conservan etiquetas impresas.

    La salida es un conjunto de anclas para reconstruir filas sin borrar columnas
    de datos vacías. No identifica al proveedor ni usa el nombre del archivo.
    """
    ws=line['words']; tokens=[norm(w['text']) for w in ws]
    has_desc='description' in tokens
    has_prose=('labor' in tokens and any(t.startswith('performed') for t in tokens)
               and 'repairs' in tokens)
    has_end=any(t in ('amount','extended','extamt','amttx','total','extprice') for t in tokens)
    has_amount_pair=('ext' in tokens and 'amttx' in tokens)
    if not ((has_desc or has_prose) and (has_end or has_amount_pair)):
        return None
    if len(ws)>22 or len(ws)<3:return None

    anchors=[]
    if has_prose and not has_desc:
        # Ejemplo abstracto: encabezado descriptivo extenso y cantidad compuesta.
        # Rate puede estar en una segunda banda física, justo encima del resto.
        qnext=next((w for w in ws if norm(w['text']) in ('qty','quantity')),None)
        end=next((w for w in ws if norm(w['text'])=='amount'),None)
        if qnext is None or end is None:return None
        second_start=next((w['x0'] for w in ws[1:] if norm(w['text'])=='labor'),qnext['x0']-65)
        desc_ws=[w for w in ws if w['x0']<second_start-2]
        qty_ws=[w for w in ws if second_start<=w['x0']<=qnext['x1']]
        if not desc_ws:return None
        anchors=[{'name':text_of(desc_ws),'x':desc_ws[0]['x0'],'role':'descripcion'},
                 {'name':text_of(qty_ws),'x':qnext['x0'],'role':'cantidad'}]
        prior=[w for l in prior_lines[-3:] if 0<line['y']-l['y']<28 for w in l['words']
               if norm(w['text']) in ('rate','price')]
        if prior:
            near=min(prior,key=lambda w:abs(w['x0']-(end['x0']-36)))
            anchors.append({'name':near['text'],'x':near['x0'],'role':'tarifa'})
        anchors.append({'name':end['text'],'x':end['x0'],'role':'importe'})
    else:
        i=0
        while i<len(ws):
            w=ws[i];t=norm(w['text']);n=1;role=None
            if t=='unit' and i+1<len(ws) and norm(ws[i+1]['text'])=='price':
                n=2;role='tarifa'
            elif t=='ext' and i+1<len(ws) and norm(ws[i+1]['text']) in ('amttx','amt','amount','price'):
                n=2;role='importe'
            elif t=='partssr' and i+1<len(ws) and norm(ws[i+1]['text'])=='no':
                n=2;role='item'
            elif t in ('description',):role='descripcion'
            elif t in ('quantity','qty','order','ship','hrsqty'):role='cantidad' if t in ('quantity','qty','hrsqty') else 'otro'
            elif t in ('amount','extended','total','amttx','extamt','extprice'):role='importe'
            elif t in ('rate','price','unitprice'):role='tarifa'
            elif t in ('item','itemid','no','partssr','type'):role='item'
            elif t in ('bo','uom','core','tax','d','ship','order'):role='otro'
            else:
                # Ornamentos de separación no crean columnas artificiales.
                if re.fullmatch(r'[-*_/]+',w['text']):
                    i+=1;continue
                role='otro'
            anchors.append({'name':text_of(ws[i:i+n]),'x':w['x0'],'role':role})
            i+=n
    anchors=sorted(anchors,key=lambda a:a['x'])
    if sum(a['role']=='descripcion' for a in anchors)!=1:return None
    if sum(a['role']=='importe' for a in anchors)!=1:return None
    if len(anchors)<3:return None
    return {'y':line['y'],'anchors':anchors,'signature':tuple((a['name'],a['role']) for a in anchors)}


def l08_find_headers(page):
    lines=grouped_lines(page.extract_words(x_tolerance=2,y_tolerance=3),tolerance=2.8)
    matches=[]
    for idx,line in enumerate(lines):
        header=l08_header_patterns(line,lines[max(0,idx-3):idx])
        if header:
            header['pagina_lineas']=lines
            matches.append(header)
    return matches,lines


def l08_economic_closure(words):
    """Distingue un cierre de sección de una partida sin usar el importe."""
    txt=text_of(words)
    compact=norm(txt)
    if not txt:return False
    if re.search(r'^(?:\*+\s*)?(?:sub[\s-]*total|total\s+(?:parts?|labor|misc|svc|shop)|invoice\s+total|sales\s*tax|total\s+excl\.|netorder|charged\s+to|estimated\s+total)\b',txt,re.I):return True
    if re.search(r'\bsub[\s-]*total\b',txt,re.I):return True
    if re.search(r'\*{2}\s*TOTAL\b',txt,re.I):return True
    if re.search(r'^Total\s+(?:Excl|Incl|before|after)\b',txt,re.I):return True
    if re.search(r'^Total\s+[-$\d]',txt,re.I):return True
    return False


def l08_assign_words(line_words,anchors):
    """Asignación espacial de palabras por anclas, conservando encabezados exactos."""
    ordered=sorted(anchors,key=lambda a:a['x'])
    out={a['name']:[] for a in ordered}
    # A diferencia de los midpoints, el inicio de la columna siguiente evita
    # partir descripciones extensas (títulos muy largos con valores a la derecha).
    for w in line_words:
        candidates=[i for i,a in enumerate(ordered) if w['x0']>=a['x']-10]
        idx=max(candidates,default=0)
        out[ordered[idx]['name']].append(w)
    return {name:text_of(words) for name,words in out.items()}


def l08_job_before(lines,y,old=None):
    """Identificador impreso de bloque; admite Job#3, Job 3 y Task 3."""
    cur=old
    for line in lines:
        if line['y']>=y:break
        s=text_of(line['words'])
        m=re.search(r'\b(?:job|task|operation)\s*#?\s*(\d{1,4})\b',s,re.I)
        if m and line['words'][0]['x0'] < 130:
            cur=f'{m.group(0)}'
    return cur


def l08_parse_table_segment(page,pn,header,lines,ymax):
    """Filas + subtotales detectados en una banda tabular.

    Las cifras sin descripción/identificador se preservan como dudosas, no
    se transforman automáticamente en partidas de detalle.
    """
    anchors=header['anchors']; names=[a['name'] for a in anchors]
    item=next((a['name'] for a in anchors if a['role']=='item'),None)
    desc=next(a['name'] for a in anchors if a['role']=='descripcion')
    amount=next(a['name'] for a in anchors if a['role']=='importe')
    price=next((a['name'] for a in anchors if a['role']=='tarifa'),None)
    qty=next((a['name'] for a in anchors if a['role']=='cantidad'),None)
    amt_x=next(a['x'] for a in anchors if a['role']=='importe')
    desc_x=next(a['x'] for a in anchors if a['role']=='descripcion')
    rows=[]; raw_blocks=[]; unknown=[]; section=''
    previous_y=None
    for l in lines:
        y=l['y']
        if y<=header['y']+3 or y>=ymax:continue
        words=l['words']; s=text_of(words)
        if not s:continue
        if L08_STOP_RE.search(s):break
        if re.search(r'^(?:(?:job|task|operation)\s*#\s*\d{1,3}|(?:job|task|operation)\s+\d{1,3})\b',s,re.I):break
        if re.search(r'^\s*(?:estimate\s+operations|continued\s+on\s+next\s+page)',s,re.I):continue
        if L08_SECTION_RE.match(s):
            section=s;previous_y=None;continue
        # Títulos de secciones no son continuación del detalle anterior.
        if (rows and rows[-1].get(amount,'')=='' and previous_y is not None
            and 0<y-previous_y<=17 and len(words)==1
            and item is not None and words[0]['x0']<desc_x-10):
            rows[-1][item]=(rows[-1].get(item,'')+' '+s).strip()
            previous_y=y;continue
        if (not any(l08_is_number(w['text']) for w in words) and
            len(words)<=5 and s.upper()==s and
            any(w['x0']<desc_x-5 for w in words) and
            not re.match(r'^[A-Z0-9-]{1,12}\s+[A-Z0-9-]{1,12}$',s)):
            section=s;previous_y=None;continue
        if l08_economic_closure(words):
            raw_blocks.append({'pagina':pn,'y':round(y,1),'Texto':s,'Tipo':'CIERRE_O_RESUMEN'})
            previous_y=None
            # Cierres múltiples de Job y total general cierran el detalle físico.
            if ((re.search(r'^Total\s+Labor\b',s,re.I) and
                 sum(l08_is_number(w['text']) for w in words)>=3) or
                re.search(r'^Total\s+Excl\.',s,re.I)):
                break
            continue
        # Valores en columna de importe que cumplan el patrón numérico real
        money=[w for w in words if w['x0']>=amt_x-16 and l08_is_amount(w['text'])]
        # El texto del detalle no puede ser un bloque contable en otra posición.
        cells=l08_assign_words(words,anchors)
        valor=cells[amount]
        value_ok=any(w['text']==valor for w in money) if money else False
        if not value_ok and money:
            # Con varios tokens en la misma celda de importe: conservar sin inventar.
            value_ok=bool(l08_is_amount(valor))
        has_item=bool(item and cells[item] and re.search(r'[A-Za-z0-9]',cells[item]))
        has_desc=bool(cells[desc] and re.search('[A-Za-z]',cells[desc]))
        rate_val=cells[price] if price else ''
        qty_val=cells[qty] if qty else ''
        has_num=bool(rate_val or qty_val)
        # Una fila de detalle exige importe, o un item identificable junto con
        # una descripción aunque no se haya impreso su monto.
        if value_ok and (has_desc or has_item):
            rows.append({'pagina':pn,**cells,'_y':y,'_seccion':section})
            previous_y=y
            continue
        if (not money and has_item and has_desc and not L08_CLOSE_RE.search(s)
                and item is not None and
                len(cells[item])<=22 and len(cells[item].split())<=2
                and not re.search(r'^(?:please|customer|payment|approved|survey)',cells[item],re.I)):
            rows.append({'pagina':pn,**cells,'_y':y,'_seccion':section})
            previous_y=y
            continue
        # Continuación de texto multilinea. Solo asociar si la distancia vertical
        # es pequeña y el bloque no es un cierre ni cambia de sección.
        if rows and previous_y is not None and 0<y-previous_y<=17 and not money and not L08_CLOSE_RE.search(s):
            last=rows[-1]
            dw=[w for w in words if (desc_x-12)<=w['x0']<amt_x-50]
            iw=[w for w in words if item is not None and w['x0']<desc_x-12]
            if dw or iw:
                if dw or (iw and not rows[-1].get(amount,'')):
                    d=text_of(words) if (iw and not rows[-1].get(amount,'')) else text_of(dw)
                    last[desc]=(' '.join([last.get(desc,''),d])).strip()
                if iw and not dw and item is not None and rows[-1].get(amount,''):
                    last[item]=(' '.join([last.get(item,''),text_of(iw)])).strip()
                previous_y=y
                continue
        if money:
            unknown.append({'pagina':pn,'y':round(y,1),'Texto':s,
                            'Motivo':'Importe con estructura de fila no concluyente'})
        previous_y=y
    for r in rows:
        r.pop('_y',None)
    sections=[str(r.get('_seccion','')) for r in rows]
    cols=['pagina']+names
    df=pd.DataFrame([{k:r.get(k,'') for k in cols} for r in rows],columns=cols)
    return df,raw_blocks,unknown,sections


def l08_parse_flexible_columns(pdf):
    tables=[]; blocks=[]; unknown=[]
    # Marcadores Job/Task de todo el documento, incluso antes de un salto de página.
    markers=[]
    for pnum,p in enumerate(pdf.pages,1):
        for line in grouped_lines(p.extract_words(x_tolerance=2,y_tolerance=3)):
            ss=text_of(line['words'])
            match=re.search(r'^(?:job|task|operation)\s*#?\s*(\d{1,4})\b',ss,re.I)
            if match and line['words'][0]['x0']<140:
                markers.append((pnum,line['y'],match.group(0)))
    previous=None
    for pn,page in enumerate(pdf.pages,1):
        heads,lines=l08_find_headers(page)
        for j,head in enumerate(heads):
            # Mantener el identificador lógico de Job aunque haya salto de página.
            carry_job=next((m[2] for m in reversed(markers)
                            if (m[0],m[1])<(pn,head['y'])),None)
            top_limit=heads[j+1]['y']-4 if j+1<len(heads) else page.height
            df,detail_blocks,uncertain,sections=l08_parse_table_segment(page,pn,head,lines,top_limit)
            unknown.extend(uncertain)
            if not len(df):
                # Una cabecera impresa sin partidas sigue siendo una tabla válida.
                pass
            sig=head['signature']
            compatible=(previous is not None and previous['signature']==sig
                        and previous['job']==carry_job and pn==previous['lastpage']+1)
            if compatible:
                target=previous['table'];target['datos']=pd.concat([target['datos'],df],ignore_index=True)
                target['fin']=pn
                target['secciones_inferidas'].extend(sections)
                previous['lastpage']=pn
            else:
                tab={'id':str(len(tables)+1),'titulo':carry_job or 'Tabla principal',
                     'codigo':'','inicio':pn,'fin':pn,'datos':df,
                     'encabezados_pdf':[a['name'] for a in head['anchors']],
                     'columnas_inferidas':[], 'metodo_lectura':'COLUMNAS_FLEXIBLES_L08',
                     'secciones_inferidas':sections}
                tables.append(tab)
                previous={'table':tab,'signature':sig,'lastpage':pn,'job':carry_job}
            table_id=previous['table']['id']
            blocks.extend([{**b,'tabla_id':table_id} for b in detail_blocks])
    return tables,blocks,unknown


def l08_local_subtotals(pdf, blocks):
    """Detecta subtablas explícitas con distintas orientaciones de concepto/importe.

    Solo usa renglones de cierre detectados por el lector flexible. No computa
    montos faltantes ni asume que todo cierre es un subtotal de reparación.
    """
    rows=[]
    for b in blocks:
        p=pdf.pages[int(b['pagina'])-1]
        lines=grouped_lines(p.extract_words(x_tolerance=2,y_tolerance=3),tolerance=2.8)
        line=min(lines,key=lambda line:abs(line['y']-b['y']))
        ws=sorted(line['words'],key=lambda w:w['x0'])
        if not ws or abs(line['y']-b['y'])>3:continue
        txt=' '.join(w['text'] for w in ws)
        # Caso de categorías sucesivas: Total Labor 1,837.50 Total Parts 0.00 Total 1,837.50.
        if re.search(r'\bTotal\s+Labor\b',txt,re.I) and sum(l08_is_amount(w['text']) for w in ws)>=2:
            i=0
            while i<len(ws):
                if norm(ws[i]['text'])!='total':i+=1;continue
                j=i+1
                while j<len(ws) and not l08_is_amount(ws[j]['text']):j+=1
                if j<len(ws):
                    label=' '.join(w['text'] for w in ws[i:j])
                    rows.append({'tabla_id':b['tabla_id'],'pagina':b['pagina'],
                                 'Concepto':label,'Importe':ws[j]['text']})
                    i=j+1
                else:i+=1
            continue
        # Caso de pares importe/etiqueta horizontales: 49.16 PARTS ... 623.23 SUB TOTAL.
        if ('subtotal' in norm(txt) or 'subtotal' in norm(b['Texto'])) and sum(l08_is_amount(w['text']) for w in ws)>=3:
            i=0
            while i<len(ws):
                if not l08_is_amount(ws[i]['text']):i+=1;continue
                amount=ws[i]['text'];j=i+1
                while j<len(ws) and not l08_is_amount(ws[j]['text']):j+=1
                label=' '.join(w['text'] for w in ws[i+1:j]).strip()
                if label and re.search('[A-Za-z]',label):
                    rows.append({'tabla_id':b['tabla_id'],'pagina':b['pagina'],
                                 'Concepto':label,'Importe':amount})
                i=j
            continue
        # Cierre singular: Sub-Total for Labor 712.64, ** TOTAL PARTS SHOP 295.39.
        last=next((w for w in reversed(ws) if l08_is_amount(w['text'])),None)
        if last is None:continue
        labels=[w for w in ws if w['x0']<last['x0'] and not l08_is_amount(w['text'])]
        label=' '.join(w['text'] for w in labels).strip()
        if not re.search(r'(?:sub[ -]?total|\*{2}\s*total|^total\s+(?:labor|parts))',label,re.I):
            continue
        rows.append({'tabla_id':b['tabla_id'],'pagina':b['pagina'],
                     'Concepto':label,'Importe':last['text']})
    grouped={}
    for r in rows:
        grouped.setdefault(r['tabla_id'],[]).append(r)
    return [{'task_id':tid,'tabla_id':tid,'pagina':rr[0]['pagina'],
             'datos':pd.DataFrame([{k:r[k] for k in ('pagina','Concepto','Importe')} for r in rr]),
             'completa':False,'origen':'SUBTOTALES_FLEXIBLES_L08','tipo':'IMPRESA'}
            for tid,rr in grouped.items()]



def l08_summary_from_compact_layout(pdf):
    """Resúmenes breves (2+ filas) en el área derecha de la última página.

    Es un respaldo para formatos cuyos totales no forman un bloque grande.
    Los valores se copian literalmente; se exigen etiquetas económicas.
    """
    if not pdf.pages:return None
    pn=len(pdf.pages);page=pdf.pages[-1]
    words=page.extract_words(x_tolerance=1,y_tolerance=3,keep_blank_chars=False)
    lines=grouped_lines(words,tolerance=3.5)
    candidates=[]
    for money in words:
        if not(l08_is_amount(money['text']) and money['x0']>=page.width*.78
               and money['top']>=page.height*.58):continue
        near=[w for w in words if page.width*.61<=w['x0']<money['x0']-3
              and abs(w['top']-money['top'])<=6.6 and not l08_is_number(w['text'])]
        label=' '.join(w['text'] for w in sorted(near,key=lambda w:w['x0'])).strip()
        if not label:
            # Algunas facturas imprimen la etiqueta encima del importe.
            preceding=[l for l in lines if 0<money['top']-l['y']<=38]
            for l in sorted(preceding,key=lambda l:-l['y']):
                ws=[w for w in l['words'] if page.width*.61<=w['x0']<money['x0']-3]
                possibility=' '.join(w['text'] for w in ws).strip()
                if re.search(r'(?:estimated|grand|invoice)?\s*total',possibility,re.I):
                    label=possibility;break
        label=re.sub(r'\s+',' ',label).strip()
        if not re.match(r'^(?:\*+\s*)?(?:sub[\s-]*total|total|sales\s*tax|tax|estimated\s*total|netorder|salestax|charged\s+to|invoice\s*total|grand\s*total)\b',label,re.I):
            continue
        candidates.append({'pagina':pn,'y':money['top'],'Concepto':label,'Importe':money['text']})
    if len(candidates)<2:return None
    candidates=sorted(candidates,key=lambda r:r['y'])
    closing=[(idx,r) for idx,r in enumerate(candidates) if re.search(
        r'^(?:\*+\s*)?(?:total\s*\*{0,2}\s*$|estimated\s*total|invoice\s*total|grand\s*total|charged\s+to)',r['Concepto'],re.I)]
    if not closing:return None
    j,end=closing[-1]
    block=[r for r in candidates[:j+1] if end['y']-r['y']<=115]
    if len(block)<2:return None
    return {'pagina':pn,'titulo':'','datos':pd.DataFrame(
        [{k:r[k] for k in ('pagina','Concepto','Importe')} for r in block]),
        'cierre':end['Concepto'],'origen':'RESUMEN_COMPACTO_L08'}


def l08_reparar_etiquetas_resumen(pdf, resumen):
    """Cuando la etiqueta del resumen incorpora texto legal lateral, acotar
    las palabras a la banda derecha. Mantener evidencia original de Laboratorio 07.
    """
    if resumen is None:return resumen,None
    df=resumen['datos']
    if not any(len(str(v).split())>=6 for v in df['Concepto']):return resumen,None
    pn=resumen['pagina'];p=pdf.pages[pn-1]
    words,anchors=_summary_anchors_and_rows(p,pn)
    source=[];used=set()
    for _,r in df.iterrows():
        line=next(((i,a) for i,a in enumerate(anchors) if i not in used
                   and str(a['Importe'])==str(r['Importe'])),None)
        if line is None:return resumen,None
        i,a=line;used.add(i)
        monetary=next((w for w in words if str(w['text'])==str(r['Importe'])
                       and abs(w['top']-a['y'])<2 and w['x1']>p.width*.88),None)
        if monetary is None:return resumen,None
        lbl=[w for w in words if p.width*.67<=w['x0']<monetary['x0']-2
             and abs(w['top']-monetary['top'])<=7.5]
        text=' '.join(w['text'] for w in sorted(lbl,key=lambda w:w['x0'])).strip()
        if not text or len(text.split())>5:return resumen,None
        source.append({'pagina':pn,'Concepto':text,'Importe':str(r['Importe'])})
    if len(source)!=len(df):return resumen,None
    old=resumen
    new={**resumen,'datos':pd.DataFrame(source,columns=['pagina','Concepto','Importe']),
         'origen':'RESUMEN_ORIGINAL_BANDA_CORREGIDA_L08'}
    return new,old

def leer_invoice(pdf_file):
    """Motor 08: LAB 07 intacto + estrategia flexible solo como recuperación.

    La estrategia adicional se usa únicamente si el Laboratorio 07 no encuentra
    ninguna tabla principal. El estado de OCR nunca se fuerza a una lectura.
    """
    result=_L08_leer_invoice_base(pdf_file)
    result['estrategia_l08']='LABORATORIO_07'
    result['cierres_detectados_l08']=pd.DataFrame(columns=['pagina','y','Texto','Tipo'])
    result['filas_dudosas_l08']=pd.DataFrame(columns=['pagina','y','Texto','Motivo'])
    result['evidencia_lineas_l08']=pd.DataFrame(columns=['pagina','y','Texto'])
    if result['parser']=='REQUIERE OCR' or result['tablas']:
        return result
    with pdfplumber.open(pdf_file) as pdf:
        tables,blocks,uncertain=l08_parse_flexible_columns(pdf)
        local_subtables=l08_local_subtotals(pdf,blocks)
        # Resguardo íntegro del texto físico digital: no perder notas ni renglones.
        result['evidencia_lineas_l08']=pd.DataFrame([
            {'pagina':pn,'y':round(g['y'],2),'Texto':text_of(g['words'])}
            for pn,page in enumerate(pdf.pages,1)
            for g in grouped_lines(page.extract_words(x_tolerance=2,y_tolerance=3))
        ],columns=['pagina','y','Texto'])
        if result.get('resumen_final') is None:
            result['resumen_final']=l08_summary_from_compact_layout(pdf)
        else:
            corrected,original=l08_reparar_etiquetas_resumen(pdf,result['resumen_final'])
            result['resumen_final']=corrected
            if original is not None:
                result['resumen_original_l07_evidencia']=original
    if tables:
        result['tablas']=tables
        result['n_partidas']=sum(len(t['datos']) for t in tables)
        result['subtablas']=local_subtables
        result['parser']='COLUMNAS_FLEXIBLES'
        result['estrategia_l08']='RECONOCIMIENTO_FLEXIBLE'
        result['avisos']=[a for a in result['avisos'] if 'No se encontró una estructura' not in a]
        result['avisos'].append('La lectura flexible requiere validación de partidas y bloques económicos; no implica lectura completa del invoice.')
        if uncertain:
            result['avisos'].append(f'{len(uncertain)} fila(s) con importe pendientes de revisión.')
        result['cierres_detectados_l08']=pd.DataFrame(blocks,columns=['pagina','y','Texto','Tipo'])
        result['filas_dudosas_l08']=pd.DataFrame(uncertain,columns=['pagina','y','Texto','Motivo'])
    return result



# ========= CELDA 12 DEL NOTEBOOK ORIGINAL =========
# =============================================================================
# LABORATORIO 09 - Lectura modular de secciones y subtablas (SOLO PDF DIGITAL)
# Se añade sobre el motor 08; no se modifica ninguna de las funciones anteriores.
# No contiene condiciones por nombre de archivo ni por proveedor.
# =============================================================================
_L09_leer_invoice_base = leer_invoice

L09_JOB_LINE = re.compile(r'^Job\s+\d{3,}\b', re.I)
L09_BLOCK_MARK = re.compile(r'^(?:job|task|operation)\s*#?\s*(\d{1,4})\b',re.I)
L09_CONTEXT_MARK = re.compile(r'^(condition|complaint|concern|cause|correction|recommended correction|work description|request cmnts|repair cmnts)\s*:?(?:\s|$)',re.I)


def l09_section_role(line):
    """Categoriza títulos cortos de sección usando vocabulario/forma, no marca.

    Devuelve None para conceptos sin un papel inequívoco (ej. DRY NITROGEN),
    permitiendo unir esos conceptos con un importe impreso en la siguiente línea.
    """
    s=re.sub(r'\s+',' ',str(line or '')).strip()
    if not s or len(s.split())>7 or any(l08_is_amount(tok) for tok in s.split()):
        return None
    ns=norm(s)
    if re.match(r'^(?:comments?|remarks?|service\s+note|repair\s+comments?|cust(?:omer)?\s+complaint)\b',s,re.I):
        return 'NOTAS'
    if L09_JOB_LINE.match(s):
        return None
    if re.search(r'\b(?:part(?:s)?|material(?:s)?)\b',s,re.I) and (s.upper()==s or re.search(r'\bDescription\b',s,re.I)):
        return 'PARTS'
    if re.search(r'\b(?:labor|lab(?:our)?|svc\s+sh\s+lab)\b',s,re.I) and (s.upper()==s or re.search(r'\bDescription\b',s,re.I)):
        return 'LABOR'
    if re.search(r'\b(?:misc(?:ellaneous)?\s+charges?|enviro(?:nmental)?\s*/?\s*shop)\b',s,re.I) and (s.upper()==s or re.search(r'\bDescription\b',s,re.I)):
        return 'CARGOS'
    return None


def l09_header_for_table(page, table, pn):
    heads,lines=l08_find_headers(page)
    sig=tuple(table.get('encabezados_pdf', []))
    matched=[h for h in heads if tuple(a['name'] for a in h['anchors'])==sig]
    return (matched[0] if matched else None), lines


def l09_rebuild_contaminated_table(pdf, table):
    """Relee solamente una tabla donde L08 fusionó notas/tareas con una partida.

    Regla general: cantidad, tarifa y monto siguen su ancla de impresión;
    'Job 01234' y las notas son unidades lógicas distintas de la última
    partida, aun si están muy cerca. Las celdas no impresas quedan en blanco.
    """
    all_rows=[]; sections=[]; notes=[]; joins=[]; unknown=[]
    for pn in range(table['inicio'],table['fin']+1):
        page=pdf.pages[pn-1]
        head, lines=l09_header_for_table(page,table,pn)
        if head is None:
            unknown.append({'pagina':pn,'y':None,'Texto':'',
                            'Motivo':'No se localizaron encabezados para reconstruir la tabla'})
            continue
        anchors=head['anchors']; names=[a['name'] for a in anchors]
        item=next((a['name'] for a in anchors if a['role']=='item'),None)
        desc=next(a['name'] for a in anchors if a['role']=='descripcion')
        amount=next(a['name'] for a in anchors if a['role']=='importe')
        ax=next(a['x'] for a in anchors if a['role']=='importe')
        dx=next(a['x'] for a in anchors if a['role']=='descripcion')
        active='SIN_SECCION_EXPLICITA'; recent=None; pending=None; row_y=None
        for l in lines:
            y=l['y']; ws=l['words']; s=text_of(ws)
            if y<=head['y']+3:continue
            if L08_STOP_RE.search(s):break
            if re.match(r'^(?:(?:job|task|operation)\s*#\s*\d+|(?:job|task|operation)\s+\d+)\b',s,re.I) and ws[0]['x0']<110:break
            # Cambios explícitos de sección; notas tras COMMENTS no son partidas.
            role=l09_section_role(s)
            if role:
                active=role;pending=None;recent=None
                sections.append({'tabla_id':table['id'],'pagina':pn,'y':round(y,2),
                                 'Texto':s,'Tipo':'SECCION_'+role})
                continue
            if l08_economic_closure(ws):
                recent=None;pending=None
                # Si terminó una categoría, no adscribir importes posteriores
                # automáticamente a la sección precedente.
                active='SIN_SECCION_EXPLICITA'
                continue
            if active=='NOTAS':
                notes.append({'tabla_id':table['id'],'pagina':pn,'y':round(y,2),
                              'Seccion':'NOTAS','Texto':s,'Tipo':'COMENTARIO'})
                continue
            if L09_JOB_LINE.match(s):
                notes.append({'tabla_id':table['id'],'pagina':pn,'y':round(y,2),
                              'Seccion':active if active!='SIN_SECCION_EXPLICITA' else 'LABOR',
                              'Texto':s,'Tipo':'DESCRIPCION_DE_TRABAJO'})
                recent=None;pending=None
                continue
            # Los candidatos de importe deben aparecer en la banda de Amount.
            money=[w for w in ws if w['x0']>=ax-16 and l08_is_amount(w['text'])]
            cells=l08_assign_words(ws, anchors)
            val=cells.get(amount,'')
            has_money=bool(money and l08_is_amount(val))
            has_item=bool(item and cells.get(item,''))
            has_desc=bool(cells.get(desc,''))
            # Una partida puede carecer de item y de descripción en la MISMA línea:
            # el descriptor puede estar inmediatamente arriba.
            if has_money and not has_desc and pending and 0<y-pending['y']<=15:
                cells[desc]=pending['Texto']
                has_desc=True
            if has_money and (has_desc or has_item):
                if pending and str(cells[desc]).strip()==pending['Texto'] and 0<y-pending['y']<=15:
                    joins.append({'tabla_id':table['id'],'pagina':pn,'y':round(y,2),
                                  'Texto':pending['Texto'],'Importe':val,
                                  'Regla':'DESCRIPCION_EN_RENGLON_ANTERIOR'})
                if not cells[desc]:
                    unknown.append({'pagina':pn,'y':round(y,2),'Texto':s,
                                    'Motivo':'Importe sin descripción asociable'})
                else:
                    all_rows.append({'pagina':pn,**cells})
                    sec=(active if active!='SIN_SECCION_EXPLICITA' else
                         ('CARGOS' if pending and 0<y-pending['y']<=15 else active))
                    sections.append({'tabla_id':table['id'],'pagina':pn,'y':round(y,2),
                                     'Texto':cells[desc],'Tipo':'PARTIDA','Seccion':sec,
                                     'IndiceFila':len(all_rows)-1})
                    recent=len(all_rows)-1;row_y=y
                pending=None
                continue
            if not has_money and has_item and has_desc and item is not None and len(cells[item].split())<=2:
                all_rows.append({'pagina':pn,**cells})
                sections.append({'tabla_id':table['id'],'pagina':pn,'y':round(y,2),
                                 'Texto':cells[desc],'Tipo':'PARTIDA','Seccion':active,
                                 'IndiceFila':len(all_rows)-1})
                recent=len(all_rows)-1;row_y=y;pending=None
                continue
            # Continuación SOLO del renglón físico anterior, y sin cambiar sección.
            if recent is not None and row_y is not None and 0<y-row_y<=16 and not has_money:
                text_part=[w for w in ws if dx-10<=w['x0']<ax-25]
                if text_part and len(ws)<=9 and not L09_CONTEXT_MARK.match(s):
                    all_rows[recent][desc]=(all_rows[recent][desc]+' '+text_of(text_part)).strip()
                    row_y=y;continue
            # Descriptor independiente inmediatamente antes de importe sin nombre.
            if not money and len(ws)<=6 and re.search('[A-Za-z]',s) and not L09_CONTEXT_MARK.match(s):
                pending={'y':y,'Texto':s}
            elif has_money:
                unknown.append({'pagina':pn,'y':round(y,2),'Texto':s,
                                'Motivo':'Importe no asociado a partida'})
            recent=None;row_y=None
    if not all_rows:return None,sections,notes,joins,unknown
    cols=['pagina']+table['encabezados_pdf']
    df=pd.DataFrame([{col:row.get(col,'') for col in cols} for row in all_rows],columns=cols)
    return df,sections,notes,joins,unknown


def l09_find_line_of_row(lines, row, item_columns, amount_columns, minimum_y):
    """Obtiene la línea de origen de una fila sin usar el nombre del proveedor."""
    row_items=[str(row.get(c,'')).strip() for c in item_columns if str(row.get(c,'')).strip()]
    row_amounts=[str(row.get(c,'')).strip() for c in amount_columns if str(row.get(c,'')).strip()]
    for l in lines:
        if l['y'] < minimum_y-2:continue
        txt=text_of(l['words'])
        tokens=[w['text'] for w in l['words']]
        if row_amounts and not any(a in tokens for a in row_amounts):continue
        if row_items and not any(i in tokens for i in row_items):continue
        if row_items or row_amounts:
            return l['y']
    return None


def l09_sections_for_existing_tables(pdf, tables):
    """Enriquece cada fila con su sección; no reemplaza la tabla principal."""
    out=[]; evidence=[]
    for table in tables:
        if 'datos' not in table:continue
        df=table['datos']
        if not len(df):continue
        pieces=[]
        for pn in range(table.get('inicio',1),table.get('fin',1)+1):
            p=pdf.pages[pn-1];head,lines=l09_header_for_table(p,table,pn)
            if head is None:continue
            start=head['y']; roles=[]; default_section=('PARTS' if any(
                re.search(r'parts?', a['name'], re.I) and a['role']=='item'
                for a in head['anchors']) else 'SIN_SECCION_EXPLICITA')
            for l in lines:
                if l['y']<=start:continue
                role=l09_section_role(text_of(l['words']))
                if role:
                    roles.append((l['y'],role))
                    evidence.append({'tabla_id':table['id'],'pagina':pn,'y':round(l['y'],2),
                                     'Texto':text_of(l['words']),'Tipo':'SECCION_'+role})
            amount_cols=[a['name'] for a in head['anchors'] if a['role']=='importe']
            item_cols=[a['name'] for a in head['anchors'] if a['role']=='item']
            # Si no hay item, usar descripción + importe para anclar.
            for ri,r in df[df['pagina']==pn].iterrows():
                y=l09_find_line_of_row(lines,r,item_cols,amount_cols,start)
                role=next((role for yy,role in reversed(roles) if y is not None and yy<y),default_section)
                # Si la fila antecede inmediatamente a un subtotal de categoría,
                # éste puede identificar su sección aun sin título separado.
                if role=='SIN_SECCION_EXPLICITA' and y is not None:
                    closing=next((l for l in lines if y<l['y']<=y+24 and
                                  re.search(r'Sub[ -]?Total\s+for\s+(Labor|Misc|Parts)',text_of(l['words']),re.I)),None)
                    if closing:
                        m=re.search(r'Sub[ -]?Total\s+for\s+(Labor|Misc|Parts)',text_of(closing['words']),re.I)
                        role='CARGOS' if m.group(1).lower()=='misc' else m.group(1).upper()
                out.append({'tabla_id':table['id'],'fila':int(ri)+1,'pagina':pn,
                            'Seccion':role,'Origen':'ENCABEZADO_O_CIERRE' if role!='SIN_SECCION_EXPLICITA' else 'NO_IDENTIFICADO'})
    return out,evidence


def l09_job_context(pdf):
    """Extrae Condition/Cause/Correction y similares asociadas al Job/Task cercano.

    No normaliza ni resume el texto: conserva las palabras impresas y permite
    bloques sin valor. Los saltos de página no reinician el Job activo.
    """
    events=[]; job=None; field=None; parts=[]; start=None; marker_found=False
    def flush():
        nonlocal field,parts,start
        if field is not None and job is not None:
            events.append({'Bloque':job,'Campo':field,'Texto':' '.join(parts).strip(),
                           'pagina':start[0],'y':round(start[1],2)})
        field=None;parts=[];start=None
    for pn,page in enumerate(pdf.pages,1):
        lines=grouped_lines(page.extract_words(x_tolerance=2,y_tolerance=3),tolerance=2.8)
        for l in lines:
            s=text_of(l['words']);ws=l['words'];yy=l['y']
            m=L09_BLOCK_MARK.match(s)
            if m and ws[0]['x0']<145:
                flush();job=m.group(0);marker_found=True;continue
            if not marker_found:continue
            m=L09_CONTEXT_MARK.match(s)
            if m and ws[0]['x0']<145:
                flush();field=m.group(1).title();parts=[s[m.end():].strip()];start=(pn,yy)
                continue
            # Ninguna descripción de contexto puede absorber cabeceras de tabla,
            # cierres económicos ni pies de página.
            if field is not None:
                if (l08_header_patterns(l,[]) is not None or l08_economic_closure(ws)
                    or L08_STOP_RE.search(s) or re.match(r'^(?:Estimate\s+Operations|Page\s+\d+|JeId:)',s,re.I)):
                    flush();continue
                if (12<=min(w['x0'] for w in ws)<=page.width*.33 and
                    not any(l08_is_amount(w['text']) for w in ws) and
                    len(s)<250 and yy-start[1]<=95):
                    parts.append(s)
                elif yy-start[1]>95:
                    flush()
    flush()
    return pd.DataFrame(events,columns=['Bloque','Campo','Texto','pagina','y'])


def l09_summary_unpriced_labels(pdf, summary):
    """Preserva etiquetas impresas SIN monto cuando caen dentro del resumen.

    Añade un renglón literal vacío; nunca calcula impuestos o diferencias.
    """
    if summary is None or len(summary.get('datos',[]))<2:return summary,[]
    pn=summary['pagina'];p=pdf.pages[pn-1];df=summary['datos']
    if 'Concepto' not in df or 'Importe' not in df:return summary,[]
    lines=grouped_lines(p.extract_words(x_tolerance=2,y_tolerance=3),tolerance=2.8)
    anchors=[]
    for l in lines:
        w=[x for x in l['words'] if l08_is_amount(x['text']) and x['x0']>p.width*.74]
        if any(x['text'] in set(df['Importe'].astype(str)) for x in w):anchors.append((l['y'],min(x['x0'] for x in w)))
    if len(anchors)<2:return summary,[]
    ymin=min(y for y,x in anchors);ymax=max(y for y,x in anchors)
    additional=[]
    for l in lines:
        if not ymin<l['y']<ymax:continue
        right=[w for w in l['words'] if w['x0']>=p.width*.62]
        if not right:continue
        label=text_of(right)
        if not re.fullmatch(r'(?:sales\s+)?tax(?:es)?\s*:?',label,re.I):continue
        if any(l08_is_amount(w['text']) for w in right):continue
        if any(norm(c)==norm(label) for c in df['Concepto']):continue
        additional.append({'pagina':pn,'Concepto':label,'Importe':'','_y':l['y']})
    if not additional:return summary,[]
    # Insertar de acuerdo a su posición (sin reemplazar el resumen 08).
    data=df.to_dict('records')
    located=[]
    remaining=list(anchors)
    for item in data:
        amt=str(item.get('Importe',''))
        pair=next((j for j,(y,x) in enumerate(remaining) if
                   any(w['text']==amt for l in lines if abs(l['y']-y)<1 for w in l['words'])),None)
        y=remaining.pop(pair)[0] if pair is not None else 1e5
        located.append((y,item))
    for x in additional:located.append((x['_y'],{k:x[k] for k in ('pagina','Concepto','Importe')}))
    located.sort(key=lambda v:v[0])
    updated={**summary,'datos':pd.DataFrame([v for _,v in located],columns=df.columns),
             'origen':summary.get('origen','')+'+ETIQUETAS_SIN_IMPORTE_L09'}
    return updated,[{k:x[k] for k in ('pagina','Concepto','Importe')} for x in additional]


def l09_orientation(pdf, sub):
    """Clasifica orientación geométrica de pares concepto/importe impresos."""
    if len(sub['datos'])<=1:return 'UNA_FILA'
    pn=sub.get('pagina') or sub['datos']['pagina'].iat[0]
    p=pdf.pages[int(pn)-1]
    lines=grouped_lines(p.extract_words(x_tolerance=2,y_tolerance=3),tolerance=2.8)
    amounts=[str(x) for x in sub['datos']['Importe']]
    populated=[l for l in lines if sum(w['text'] in amounts for w in l['words'])>=2]
    return 'HORIZONTAL' if populated else 'VERTICAL'




def l09_append_records(original, new_records):
    """Adjunta datos conservando columnas aun con registros vacíos (sin warnings)."""
    if not new_records:
        return original
    if original.empty:
        return pd.DataFrame(new_records)
    return pd.concat([original,pd.DataFrame(new_records)],ignore_index=True)


def leer_invoice(pdf_file):
    """Motor 09: extensiones modulares e inspeccionables del Motor 08.

    Sin detección de proveedor, sin OCR, sin cifras sintéticas y sin CSV.
    """
    result=_L09_leer_invoice_base(pdf_file)
    result['estrategia_l09']='MOTOR_08_SIN_CAMBIOS'
    result['secciones_l09']=pd.DataFrame(columns=['tabla_id','pagina','y','Texto','Tipo','Seccion','IndiceFila'])
    result['partidas_seccionadas_l09']=pd.DataFrame(columns=['tabla_id','fila','pagina','Seccion','Origen'])
    result['trabajos_descriptivos_l09']=pd.DataFrame(columns=['tabla_id','pagina','y','Seccion','Texto','Tipo'])
    result['vinculos_l09']=pd.DataFrame(columns=['tabla_id','pagina','y','Texto','Importe','Regla'])
    result['contexto_por_bloque_l09']=pd.DataFrame(columns=['Bloque','Campo','Texto','pagina','y'])
    result['pendientes_l09']=pd.DataFrame(columns=['pagina','y','Texto','Motivo'])
    if result.get('parser')=='REQUIERE OCR':
        result['avisos'].append('Laboratorio 09 sin OCR: documento escaneado excluido.')
        return result
    with pdfplumber.open(pdf_file) as pdf:
        tables=result.get('tablas',[])
        if result.get('parser')=='COLUMNAS_FLEXIBLES':
            for tab in tables:
                if not len(tab['datos']):continue
                contaminated=any(re.search(r'\bJob\s+\d{3,}', ' '.join(map(str,row.values())),re.I)
                                 for row in tab['datos'].to_dict('records'))
                if contaminated:
                    newdf,sec,notes,joins,unknown=l09_rebuild_contaminated_table(pdf,tab)
                    if newdf is not None and len(newdf)>=len(tab['datos']):
                        tab['datos_originales_l08']=tab['datos'].copy()
                        tab['datos']=newdf
                        tab['metodo_lectura']='SECCIONES_Y_RENGLONES_L09'
                        result['estrategia_l09']='RECONSTRUCCION_POR_SECCIONES'
                        result['secciones_l09']=l09_append_records(result['secciones_l09'],sec)
                        result['trabajos_descriptivos_l09']=l09_append_records(result['trabajos_descriptivos_l09'],notes)
                        result['vinculos_l09']=l09_append_records(result['vinculos_l09'],joins)
                        result['pendientes_l09']=l09_append_records(result['pendientes_l09'],unknown)
                        result['filas_dudosas_l08']=pd.DataFrame(unknown,columns=['pagina','y','Texto','Motivo'])
            parts,sections=l09_sections_for_existing_tables(pdf,tables)
            # Para las reconstruidas, utilizar etiquetas por origen físico.
            for t in tables:
                if t.get('metodo_lectura')!='SECCIONES_Y_RENGLONES_L09':continue
                parts=[p for p in parts if p['tabla_id']!=t['id']]
                rebuilt=result['secciones_l09']
                if 'Tipo' in rebuilt and 'IndiceFila' in rebuilt:
                    for _,r in rebuilt[(rebuilt['tabla_id']==t['id']) & (rebuilt['Tipo']=='PARTIDA')].iterrows():
                        parts.append({'tabla_id':t['id'],'fila':int(r['IndiceFila'])+1,
                                      'pagina':int(r['pagina']),'Seccion':r['Seccion'],
                                      'Origen':'SECCION_EXPLICITA_L09'})
            if sections:
                result['secciones_l09']=l09_append_records(result['secciones_l09'],sections)
            result['partidas_seccionadas_l09']=pd.DataFrame(parts,columns=['tabla_id','fila','pagina','Seccion','Origen'])
        result['contexto_por_bloque_l09']=l09_job_context(pdf)
        result['resumen_final'],labels=l09_summary_unpriced_labels(pdf,result.get('resumen_final'))
        result['etiquetas_sin_importe_l09']=pd.DataFrame(labels,columns=['pagina','Concepto','Importe'])
        for subt in result.get('subtablas',[]):
            subt['orientacion_l09']=l09_orientation(pdf,subt)
        result['n_partidas']=sum(len(t['datos']) for t in tables)
        # El resultado contiene métricas de revisión, no un porcentaje ficticio de precisión.
        result['diagnostico_l09']={
            'tablas':len(tables),'partidas_detectadas':result['n_partidas'],
            'subtablas':len(result.get('subtablas',[])),
            'renglones_pendientes':len(set(
                (str(x.get('pagina')),str(x.get('y')),str(x.get('Texto')))
                for x in result['pendientes_l09'].to_dict('records') +
                         result.get('filas_dudosas_l08',pd.DataFrame()).to_dict('records'))),
            'trabajos_sin_importe':len(result['trabajos_descriptivos_l09']),
            'contextos_asociados':len(result['contexto_por_bloque_l09']),
            'resumen_identificado':result.get('resumen_final') is not None,
        }
        if result['estrategia_l09']!='MOTOR_08_SIN_CAMBIOS':
            result['avisos'].append('Se reconstruyó una tabla con renglones mezclados; L08 se conserva como evidencia.')
    return result



# ========= CELDA 14 DEL NOTEBOOK ORIGINAL =========
# =============================================================================
# LABORATORIO 10 — motores de bloques multipágina y cierres por operación
# Extensión del Laboratorio 09. Exclusivamente PDFs digitales; no hay OCR.
# Ningún criterio utiliza nombres de archivos ni proveedores.
# =============================================================================
_L10_leer_invoice_base = leer_invoice

L10_OPERATION = re.compile(r'^\s*(\d{1,3})\s+([A-Z])\.\s+(.+\[[\w-]+\])\s*$', re.I)
L10_JOB = re.compile(r'^\s*(?:JOB\s*#?\s*(\d{1,4})|Task:\s*(\d{1,4}))\b', re.I)
L10_MONEY = re.compile(r'^\(?-?\$?\d[\d,]*\.\d{2}\)?[Tt]?$')
L10_AMOUNT_TOKENS = re.compile(r'^(?:\$?-?\d[\d,]*\.\d{2}|\(-?\$?\d[\d,]*\.\d{2}\))$')
L10_IS_CLOSURE = re.compile(r'^(?:Job\s+(?:Summary|Total)|Job\s+Subtotal|Operation Total|Estimate Summary|Totals?\s*:\s*|Invoice Total|Sub-?total|\*?TOTAL\s+(?:LABOR|PARTS))',re.I)
L10_CONTEXT = re.compile(r'^(?:Complaint|Cause|Correction|Condition|Customer\s+Complaint|Service Note|Repair Comments|Terms|Notes)\s*:',re.I)


def l10_lines(pdf):
    out=[]
    for pn,page in enumerate(pdf.pages,1):
        for line in grouped_lines(page.extract_words(x_tolerance=2,y_tolerance=3),tolerance=2.8):
            out.append({'pn':pn,'y':line['y'],'w':line['words'],'s':text_of(line['words']),'width':page.width})
    return out


def l10_amount_word(w):
    return bool(L10_AMOUNT_TOKENS.fullmatch(w['text'].replace(' ','').replace('−','-')))


def l10_col_defs(l):
    """Detecta encabezados impresos por conceptos y geometría, no por marca.

    'Description + Total Cost', 'Item Description + Extension',
    'QTY ITEM DESCRIPTION UNIT PRICE EXTD PRICE' y similares.
    Preserva literalmente los encabezados, incluso si luego quedan vacíos.
    """
    ws=l['w']; toks=[norm(w['text']) for w in ws]
    text=l['s']
    if len(ws)<3 or len(ws)>20:return None
    if not re.search(r'\b(?:description|descrip|ref\s+number)\b',text,re.I):return None
    if not re.search(r'\b(?:amount|total\s+cost|totals?|ext(?:d|ended)?\s*(?:price|amt)|extension|extended\s*price)\b',text,re.I):return None
    cols=[];i=0
    def role_of(label):
        n=norm(label)
        if n in {'description','descriptionrefnumber','itemdescription','laborperformedpartsusedforrepairs'}:return 'description'
        if n in {'totalcost','extdprice','extprice','extendedprice','extension','amount','extamt','totals'}:return 'amount'
        if n in {'unitprice','unitrate','rate','price'}:return 'rate'
        if n in {'qty','qtyhours','quantity','salesqty','laborhours','labortimepartsqty'}:return 'quantity'
        if n in {'item','itemnumber','itemdescriptioncode','part','partno','partnumber','parts','supp','no'}:return 'item'
        return 'other'
    pairs={
        ('total','cost'),('core','charge'),('part','#'),('part','no'),('unit','price'),
        ('extd','price'),('ext','price'),('ext','amt'),('item','description'),
        ('item','number'),('description','ref'),('sales','qty'),('unit','rate'),
        ('core','price'),('labor','time'),('labortime','parts'),('labor','performed'),
        ('extended','price'),('parts','qty'),('supp.','part')
    }
    while i<len(ws):
        k=1
        if i+1<len(ws) and ((toks[i],toks[i+1]) in pairs or (toks[i] in ('part','item') and ws[i+1]['text']=='#')) and ws[i+1]['x0']-ws[i]['x1']<22:k=2
        if i+3<len(ws) and toks[i:i+4]==['description','','ref','number']:k=4
        elif i+2<len(ws) and toks[i:i+3]==['description','ref','number']:k=3
        label=' '.join(w['text'] for w in ws[i:i+k]);role=role_of(label)
        cols.append({'name':label,'role':role,'x':ws[i]['x0']})
        i+=k
    # Some headers print two adjacent Price columns, the rightmost is Extended Price
    if sum(c['role']=='amount' for c in cols)==0:
        last=cols[-1]
        if norm(last['name'])=='price' and any(c['role']=='rate' for c in cols[:-1]): last['role']='amount'
    if sum(c['role']=='amount' for c in cols)!=1:return None
    if not any(c['role']=='description' for c in cols):return None
    # Remove duplicated semantically incomplete chunks? NO: original headers retained.
    counts={}
    for c in cols:
        base=c['name'];counts[base]=counts.get(base,0)+1
        if counts[base]>1:c['name']=f'{base} ({counts[base]})'
    if len(cols)<3:return None
    return cols



def l10_stacked_header(block, idx):
    """Encabezado de dos alturas: 'Extended' encima de la columna 'Price'.

    No se inventa un nombre: ambas palabras deben existir en el PDF y
    sus coordenadas deben estar alineadas con el precio final.
    """
    l=block[idx]
    if not (re.search(r'\bDescription\b',l['s'],re.I)
            and re.search(r'\bQuantity\b',l['s'],re.I)
            and re.search(r'\bPrice\b',l['s'],re.I)):return None
    left=[x for x in block[max(0,idx-2):idx] if x['pn']==l['pn'] and 0<l['y']-x['y']<15]
    right=[x for x in block[idx+1:idx+3] if x['pn']==l['pn'] and 0<x['y']-l['y']<11]
    ex=next((w for a in left for w in a['w'] if norm(w['text'])=='extended'),None)
    pr=next((w for a in right for w in a['w'] if norm(w['text'])=='price' and w['x0']>l['width']*.76),None)
    if not ex or not pr or abs(ex['x0']-pr['x0'])>36:return None
    ws=l['w'];base=[];i=0
    while i<len(ws):
        w=ws[i];tok=norm(w['text']);step=1
        if tok=='description' and i+3<len(ws) and [norm(x['text']) for x in ws[i:i+4]]==['description','','ref','number']:
            name='Description / Ref Number';step=4;role='description'
        elif tok=='description' and i+2<len(ws) and [norm(x['text']) for x in ws[i:i+3]]==['description','ref','number']:
            name='Description Ref Number';step=3;role='description'
        else:
            name=w['text'];role={'quantity':'quantity','price':'rate','part':'item'}.get(tok,'other')
        base.append({'name':name,'x':w['x0'],'role':role});i+=step
    base.append({'name':'Extended Price','x':ex['x0'],'role':'amount'})
    return base


def l10_headers_with_stack(block):
    out=[]
    for i,l in enumerate(block):
        c=l10_col_defs(l)
        if c is None:c=l10_stacked_header(block,i)
        if c:out.append((i,c))
    return out

def l10_fields(ws, cols):
    out={c['name']:'' for c in cols}
    for j,c in enumerate(cols):
        # Midpoints tolerate right-aligned numeric cells whose printed value
        # begins to the left of the column heading (common for currency).
        left=(cols[j-1]['x']+c['x'])/2 if j else max(0,c['x']-16)
        if c['role']=='item':left=max(0,c['x']-5)
        right=(c['x']+cols[j+1]['x'])/2 if j+1<len(cols) else 1e9
        if c['role'] in ('description','item') and j+1<len(cols):
            right=cols[j+1]['x']-5
        out[c['name']]=text_of([w for w in ws if left<=w['x0']<right])
    return out


def l10_first_amount(cols):
    return next((c for c in cols if c['role']=='amount'),None)


def l10_is_detail(l,cols):
    if L10_CONTEXT.match(l['s']) or L10_IS_CLOSURE.match(l['s']):return False
    a=l10_first_amount(cols)
    if a is None:return False
    v=[w for w in l['w'] if w['x0']>=a['x']-25 and l10_amount_word(w)]
    if not v:return False
    # Numeric evidence near the terminal monetary column + textual description or an item code.
    description=next((c for c in cols if c['role']=='description'),None)
    desc=([w for w in l['w'] if description and description['x']-12<=w['x0']<a['x']-20 and
           re.search('[A-Za-z]',w['text'])] if description else [])
    left=[w for w in l['w'] if w['x0']<a['x']-24 and re.search('[A-Za-z]',w['text'])]
    return bool(desc or left)


def l10_make(id,title,first,cols):
    return {'id':str(id),'titulo':title,'codigo':'','inicio':first,'fin':first,
        'datos':pd.DataFrame(columns=['pagina']+[c['name'] for c in cols]),
        'encabezados_pdf':[c['name'] for c in cols], 'columnas_inferidas':[],
        'metodo_lectura':'BLOQUES_MULTITABLA_L10'}


def l10_standard_row(l,cols):
    d=l10_fields(l['w'],cols)
    # Only preserve printed cells; no computed amounts
    return {'pagina':l['pn'],**d}


def l10_block_subtable(table,lines,reason,orientation='VERTICAL'):
    records=[]
    for l in lines:
        # Accept label + amount on the line only; preserve literal number.
        amounts=[w for w in l['w'] if l10_amount_word(w)]
        if not amounts:continue
        last=amounts[-1]
        label=text_of([w for w in l['w'] if w['x1']<last['x0']-2])
        if not label or len(label)>100:continue
        records.append({'pagina':l['pn'],'Concepto':label,'Importe':last['text']})
    if not records:return None
    return {'task_id':table['id'],'tabla_id':table['id'],
            'pagina':records[0]['pagina'],'datos':pd.DataFrame(records,columns=['pagina','Concepto','Importe']),
            'tipo':'BLOQUE_ECONOMICO_L10','origen':reason,'completa':True,
            'orientacion_l09':orientation}


def l10_parse_operations(lines):
    heads=[(i,L10_OPERATION.match(l['s'])) for i,l in enumerate(lines) if L10_OPERATION.match(l['s']) and l['w'][0]['x0']<90]
    if len(heads)<2:return None
    op_closings=sum(bool(re.match(r'^Operation Total\s*:',l['s'],re.I)) for l in lines)
    if op_closings<len(heads)-1:return None
    tables=[];subs=[];pending=[]
    for pos,(start,match) in enumerate(heads):
        end=heads[pos+1][0] if pos+1<len(heads) else len(lines)
        block=lines[start:end];title=block[0]['s']
        header_idx=next((i for i,l in enumerate(block) if re.search(r'\bQuantity\b.*\bPrice\b.*\bTotals\b',l['s'],re.I)),None)
        if header_idx is None:continue
        header=block[header_idx]
        # Source header has no printed 'Item' column; add 'Concepto' explicitly inferred.
        raw=header['w'];printed=['Quantity','Price','Core Price','Totals']
        colxs=[next((w['x0'] for w in raw if norm(w['text'])==norm(n.split()[0])),None) for n in printed]
        if any(x is None for x in colxs):continue
        cols=[{'name':s,'x':x,'role':r} for s,x,r in zip(printed,colxs,['quantity','rate','other','amount'])]
        columns=['Concepto']+printed
        rows=[];closing=[]
        for l in block[header_idx+1:]:
            if re.match(r'^Operation Total\s*:',l['s'],re.I):closing.append(l);break
            a=[w for w in l['w'] if w['x0']>=colxs[-1]-18 and l10_amount_word(w)]
            label=text_of([w for w in l['w'] if w['x0']<colxs[0]-40])
            if not a or not re.search(r'\b(?:Labor|Parts?|Misc|Service|Sublet)\s*:',label,re.I):continue
            def token(start,end):return text_of([w for w in l['w'] if start-22<=w['x0']<end-12])
            rows.append({'pagina':l['pn'],'Concepto':label,'Quantity':token(colxs[0],colxs[1]),
                         'Price':token(colxs[1],colxs[2]),'Core Price':token(colxs[2],colxs[3]),
                         'Totals':a[-1]['text']})
        if not closing:continue
        t={'id':str(match.group(1)),'titulo':title,'codigo':'','inicio':block[0]['pn'],
            'fin':closing[0]['pn'],'datos':pd.DataFrame(rows,columns=['pagina']+columns),
            'encabezados_pdf':printed,'columnas_inferidas':['Concepto'],
            'metodo_lectura':'OPERACIONES_L10'}
        tables.append(t)
        s=l10_block_subtable(t,closing,'OPERATION_TOTAL_L10','UNA_FILA')
        if s:subs.append(s)
    return (tables,subs,[],[]) if len(tables)>=2 else None



def l10_close_records(l):
    """Printed label/amount pairs in vertical or horizontal economic closings.

    Never reuse a preceding label for an unlabelled amount on the right.
    """
    ws=l['w']; amounts=[(i,w) for i,w in enumerate(ws) if l10_amount_word(w)]
    if not amounts:return [],[]
    records=[];unresolved=[]
    if len(amounts)==1:
        i,w=amounts[0]
        label=text_of(ws[:i]).strip()
        if re.search(r'\bTask\s+\d+\s+Subtotals\b',label,re.I) and re.search(r'\b(?:Parts|Labor|Misc|Tax|Other)\s*:',label,re.I):
            m=re.search(r'\b(?:Parts|Labor|Misc|Tax|Other)\s*:',label,re.I)
            label=label[m.start():]
        if label: records.append({'pagina':l['pn'],'Concepto':label,'Importe':w['text']})
        else:unresolved.append({'pagina':l['pn'],'y':l['y'],'Texto':l['s'],'Motivo':'Importe de cierre sin etiqueta'})
        return records,unresolved
    # Multiple concepts on one physical row. Only labels ending in ':' are safe.
    used_labels=[]
    for i,w in amounts:
        prev=[u for u in ws[:i] if not l10_amount_word(u)]
        label=next((u['text'] for u in reversed(prev) if u['text'].endswith(':') and
                    not any(u is other for other in used_labels)),None)
        if label:
            pair_x=next((u for u in reversed(prev) if u['text']==label),None)
            if pair_x is not None and 0<w['x0']-pair_x['x1']<130:
                used_labels.append(pair_x)
                records.append({'pagina':l['pn'],'Concepto':label,'Importe':w['text']})
                continue
        unresolved.append({'pagina':l['pn'],'y':l['y'],'Texto':l['s'],
                           'Motivo':f'Importe sin etiqueta inequívoca: {w["text"]}'})
    return records,unresolved

def l10_parse_marked_jobs(lines):
    """Task / Job explícitos; conserva bloques vacíos y continuaciones de página."""
    markers=[]
    for i,l in enumerate(lines):
        m=L10_JOB.match(l['s'])
        if m and l['w'][0]['x0']<120 and not re.match(r'^Job\s+(?:Summary|Total|Subtotal)',l['s'],re.I):
            markers.append((i,m.group(1) or m.group(2),l['s']))
    if not markers:return None
    tables=[];subs=[];contexts=[];pending=[]
    for pos,(start,ident,title) in enumerate(markers):
        end=markers[pos+1][0] if pos+1<len(markers) else len(lines)
        block=lines[start:end]
        headers=l10_headers_with_stack(block)
        cols=headers[0][1] if headers else []
        # Some tasks have no explicit line items; keep their printed header if present.
        if not cols:
            # avoid creating invented columns: reuse only a verified header elsewhere in the PDF
            candidates=[c for i,c in l10_headers_with_stack(lines)]
            cols=candidates[0] if candidates else []
        if not cols:continue
        table=l10_make(ident,title,block[0]['pn'],cols)
        rows=[];closure_lines=[];header_active=False;in_closure=False
        for li,l in enumerate(block[1:],1):
            h=l10_col_defs(l) or l10_stacked_header(block,li)
            if h:
                header_active=True;in_closure=False;continue
            # A closing block can span several subsequent physical lines,
            # even if only the first one prints 'Task N Subtotals'.
            is_close=bool(re.search(r'\b(?:Task\s+\d+\s+Subtotals|Job\s+Subtotal|Operation Total|(?:LABOR|PARTS?|MISC|COUPON|SHIP|EPA|SHOP|MACH|MACHINE|ACCRUED|CANCEL(?:LATION)?)\b.{0,30}SUBTOTAL)\b',l['s'],re.I))
            is_horizontal=bool(re.match(r'^\s*(?:Parts|Labor|Other|Sublet)\s*:',l['s'],re.I) and sum(l10_amount_word(w) for w in l['w'])>=2)
            is_following=bool(in_closure and re.match(r'^\s*(?:Parts|Labor|Misc(?:ellaneous)?|Tax|Other|Sublet|Freight|Shop\s+Supplies)\s*:',l['s'],re.I) and any(l10_amount_word(w) for w in l['w']))
            if is_close or is_horizontal or is_following:
                closure_lines.append(l);header_active=False;in_closure=True;continue
            if in_closure and not is_following and (l['s'].strip().startswith('** See') or re.search(r'^\s*(?:Job|Task):',l['s'],re.I)):
                in_closure=False
            if not header_active or not l10_is_detail(l,cols):continue
            row=l10_standard_row(l,cols)
            # Avoid taking many repeated, non-detail lines (footer, preview, etc.)
            rows.append(row)
            table['fin']=max(table['fin'],l['pn'])
        table['datos']=pd.DataFrame(rows,columns=['pagina']+[c['name'] for c in cols])
        # Block existence covers even zero-detail jobs across pages.
        table['fin']=max(table['fin'],block[0]['pn'])
        tables.append(table)
        # Economic closure can be horizontal (several pairs) or vertical.
        sub_records=[]
        for l in closure_lines:
            rec,und=l10_close_records(l)
            sub_records.extend(rec);pending.extend(und)
        if sub_records:
            df=pd.DataFrame(sub_records,columns=['pagina','Concepto','Importe']).drop_duplicates()
            subs.append({'task_id':table['id'],'tabla_id':table['id'],'pagina':block[0]['pn'],
                         'datos':df,'completa':True,'tipo':'CIERRE_JOB_L10','origen':'MARCADORES_JOB',
                         'orientacion_l09':'HORIZONTAL' if any(sum(l10_amount_word(w) for w in l['w'])>=2 for l in closure_lines) else 'VERTICAL'})
    return (tables,subs,contexts,pending) if tables and (len(tables)>=2 or subs) else None


def l10_parse_summarized_headers(lines):
    """Tabla repetida + cierre Job Summary: puede continuar entre páginas."""
    headers=[]
    for i,l in enumerate(lines):
        if re.search(r'\bDescription\b.*\b(?:QTY/Hours|Quantity|Qty)\b.*\b(?:Total Cost|Amount)\b',l['s'],re.I):
            cols=l10_col_defs(l)
            if cols:headers.append((i,cols))
    job_sums=[i for i,l in enumerate(lines) if re.match(r'^Job Summary\b',l['s'],re.I) and l['w'][0]['x0']<150]
    if len(headers)<2 or len(job_sums)<2:return None
    tables=[];subs=[];pending=[];contexts=[]
    consumed_until=-1;active=None;rows=[];col_last=None
    # Read headers and associated job-summary end markers, grouping repeated headers
    for j,(idx,cols) in enumerate(headers):
        if idx<=consumed_until:continue
        # First closing after this header, before the next new job-summary.
        close=next((v for v in job_sums if v>idx),None)
        if close is None:break
        sub_end=next((q for q in range(close+1,len(lines)) if re.match(r'^Job Total\s*:',lines[q]['s'],re.I)),None)
        if sub_end is None:continue
        start_l=lines[idx];ended=lines[sub_end]
        # Use nearest preceding complaint/title heading in same page.
        preceding=[l for l in lines[max(0,idx-14):idx] if l['pn']==start_l['pn'] and
                   l['w'][0]['x0']<start_l['width']*.35 and not L10_CONTEXT.match(l['s']) and
                   not l10_col_defs(l) and len(l['s'])<90 and re.search('[A-Za-z]',l['s'])]
        title=(preceding[-1]['s'] if preceding else f'Bloque de reparación {len(tables)+1}')
        t=l10_make(str(len(tables)+1),title,start_l['pn'],cols)
        rows=[];row_lines=[]
        for l in lines[idx+1:close]:
            if l10_col_defs(l):continue
            if not l10_is_detail(l,cols):continue
            rows.append(l10_standard_row(l,cols));row_lines.append(l)
        # Preserve narrow item-code fragments printed just above/below a row.
        # A fragment is associated only if it lies inside the printed item column
        # and no other row is comparably close. All fragments remain verbatim.
        itemcol=next((c for c in cols if c['role']=='item'),None)
        qtycol=next((c for c in cols if c['role']=='quantity'),None)
        if itemcol and qtycol and rows:
            for frag in lines[idx+1:close]:
                if frag in row_lines or l10_col_defs(frag):continue
                ws=frag['w']
                if len(ws)>3 or any(l10_amount_word(w) for w in ws):continue
                if not all(itemcol['x']-5<=w['x0']<qtycol['x']-10 for w in ws):continue
                if not any(re.search(r'[A-Za-z0-9]',w['text']) for w in ws):continue
                dist=[(abs(frag['y']-rl['y']),k) for k,rl in enumerate(row_lines) if frag['pn']==rl['pn']]
                if not dist:continue
                dist.sort()
                if dist[0][0]>9 or (len(dist)>1 and abs(dist[1][0]-dist[0][0])<1):continue
                k=dist[0][1];name=itemcol['name'];value=text_of(ws)
                old=rows[k].get(name,'')
                rows[k][name]=(value+' '+old).strip() if frag['y']<row_lines[k]['y'] else (old+' '+value).strip()
        t['datos']=pd.DataFrame(rows,columns=['pagina']+[c['name'] for c in cols])
        t['fin']=ended['pn'];tables.append(t)
        sublines=lines[close+1:sub_end+1]
        # Three horizontal clusters in each line, with close preceding amount.
        records=[]
        for l in sublines:
            ws=l['w']
            for k,w in enumerate(ws):
                if not l10_amount_word(w):continue
                prev=[v for v in ws[:k] if v['x1']<w['x0']]
                if not prev:continue
                bound=max((i for i,a in enumerate(prev) if a['text'].endswith(':')),default=-1)
                if bound>=0:
                    lab=prev[bound]['text']
                elif re.search(r'\bJob\s+Total',l['s'],re.I):lab='Job Total:'
                else:continue
                if re.search('[A-Za-z]',lab):
                    records.append({'pagina':l['pn'],'Concepto':lab,'Importe':w['text']})
        if records:
            subs.append({'task_id':t['id'],'tabla_id':t['id'],'pagina':lines[close]['pn'],
                         'datos':pd.DataFrame(records,columns=['pagina','Concepto','Importe']),
                         'tipo':'SUBTABLA_HORIZONTAL_L10','origen':'JOB_SUMMARY_L10','completa':True,
                         'orientacion_l09':'HORIZONTAL'})
        consumed_until=sub_end
    return (tables,subs,contexts,pending) if len(tables)>=2 else None


def l10_find_best_candidate(lines):
    # Only one explicit strategy per document; choose confidence from actual structure.
    for tag,parser in [('OPERACIONES_CON_TOTAL',l10_parse_operations),
                       ('JOBS_CON_SUMARIO',l10_parse_summarized_headers),
                       ('JOBS_O_TASKS_EXPLICITOS',l10_parse_marked_jobs)]:
        v=parser(lines)
        if v:
            tabs,sub,context,unknown=v
            if (len(tabs)>=2 and (sub or sum(len(t['datos']) for t in tabs)>=2)) or (len(tabs)==1 and len(sub)>=1 and tag=='JOBS_O_TASKS_EXPLICITOS'):
                return tag,v
    return None,None


def l10_score(tables,subs):
    return (len(tables),sum(len(t['datos']) for t in tables),len(subs))


def leer_invoice(pdf_file):
    """Laboratorio 10: lectura de múltiples tipos de Jobs y Tasks, sin OCR.

    Se conserva íntegra la salida del Laboratorio 09 si no existe una mejora
    suficientemente respaldada; los datos previos se guardan para auditoría.
    """
    base=_L10_leer_invoice_base(pdf_file)
    base['estrategia_l10']='MOTOR_09_SIN_CAMBIOS'
    base['comparacion_l10']={'base':l10_score(base.get('tablas',[]),base.get('subtablas',[]))}
    base['evidencia_l10']=pd.DataFrame(columns=['pagina','y','Texto'])
    base['pendientes_l10']=pd.DataFrame(columns=['pagina','y','Texto','Motivo'])
    if base.get('parser')=='REQUIERE OCR':return base
    with pdfplumber.open(pdf_file) as pdf:
        lines=l10_lines(pdf)
        strategy,candidate=l10_find_best_candidate(lines)
    if not candidate:
        base['avisos'].append('L10: no se encontró una nueva estrategia estructural verificable; se conserva L09.')
        return base
    tables,sub,context,unknown=candidate
    old=l10_score(base.get('tablas',[]),base.get('subtablas',[]));new=l10_score(tables,sub)
    # Never discard already recognized detail due to a lower-scoring candidate.
    # A previously missing multi-job structure can be promoted if more sections
    # and no fewer economic lines were recovered.
    promote=((old[0]==0 and new[0]>=1 and (new[1]>0 or new[2]>0)) or
             (base.get('parser')=='COLUMNAS_FLEXIBLES' and new[0]>=old[0]
              and new[1]>old[1] and new[2]>=old[2]))
    base['comparacion_l10'].update({'candidato':new,'parser_candidato':strategy,'promovido':promote})
    if not promote:
        base['avisos'].append('L10: candidato detectado, pero no superó la lectura existente; se mantiene L09.')
        return base
    base['tablas_originales_l09']=[{**t,'datos':t['datos'].copy()} for t in base['tablas']]
    base['subtablas_originales_l09']=[{**s,'datos':s['datos'].copy()} for s in base['subtablas']]
    base['tablas']=tables
    base['subtablas']=sub
    base['parser']='MULTITABLAS_ESTRUCTURALES_L10'
    base['n_partidas']=sum(len(t['datos']) for t in tables)
    base['estrategia_l10']=strategy
    base['evidencia_l10']=pd.DataFrame([{'pagina':l['pn'],'y':round(l['y'],2),'Texto':l['s']} for l in lines],columns=['pagina','y','Texto'])
    base['pendientes_l10']=pd.DataFrame(unknown,columns=['pagina','y','Texto','Motivo'])
    if unknown:
        base['avisos'].append(f'L10: {len(unknown)} importe(s) o línea(s) de cierre pendientes de interpretación; revisar evidencia.')
    base['avisos']=[a for a in base['avisos'] if 'No se encontró una estructura' not in a]
    base['avisos'].append('L10: interpretación nueva con evidencia original; comprobar manualmente filas, páginas y cierres. No equivale a precisión 100%.')
    return base

