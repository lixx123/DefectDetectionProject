"""Primary child candidates plus disjoint review remainders; originals retained."""
import csv
import json
import time
import html
from pathlib import Path
from dataclasses import asdict
import numpy as np
from src.detection.size_review import classify
from src.detection.edge_attached_spots import split_parent
from src.detection.case03i_size_grade import max_feret_centers_px


def write_edge_spots(folder, rows, bands, raw, gray, size_settings, settings):
    start=time.perf_counter();folder=Path(folder)
    tags=classify(rows,bands,size_settings)
    parents=[r for r,t in zip(rows,tags) if t['review_status']=='SIZE_REVIEW']
    receipt=dict(settings=asdict(settings),parents=len(parents),children=0,algorithm_seconds=0.,
                 original_policy='UNCHANGED',partition_policy='CHILDREN_PLUS_REMAINDER_EQUALS_PARENT',
                 measurement_scope='SOURCE_SUBSET_NOT_PHYSICAL_OUTER_BOUNDARY')
    # No new RAW processing or duplicate reports when nothing needs splitting.
    if not parents:
        receipt.update(primary_count=len(rows),review_count=0,total_seconds=time.perf_counter()-start,skipped=True)
        (folder/'edge_spot_receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
        return receipt
    from PIL import Image,ImageDraw,ImageFont
    import cv2
    maskdir=folder/'EDGE_PARTITION_MASKS';maskdir.mkdir()
    primary=[dict(id=r['new_id'],parent_id='',bbox=json.loads(r['bbox_xyxy_exclusive']),
                  area_px=int(r['baseline_source_area_px2']),feret_px=float(r['baseline_Feret_px']),
                  grade=r['grade'],band_id=int(r['band_id']),mask_path=r['mask_path'],status='ORIGINAL_NORMAL')
             for r,t in zip(rows,tags) if t['review_status']=='NORMAL_CANDIDATE']
    remainders=[];partitions=[];details=[]
    for row in parents:
        oid=row['new_id'];bbox=json.loads(row['bbox_xyxy_exclusive'])
        with np.load(folder/row['mask_path']) as z:source=z['mask'].astype(bool)
        children,remaining,audit=split_parent(raw,source,bbox,bands.get(int(row['band_id'])),settings)
        receipt['algorithm_seconds']+=audit['seconds']
        child_area=0
        for i,c in enumerate(children,1):
            cid=f'{oid}_SPOT_{i:03d}';path=maskdir/(cid+'.npz')
            np.savez_compressed(path,mask=c['mask'],bbox=c['bbox'])
            record={k:v for k,v in c.items() if k!='mask'}
            record.update(id=cid,parent_id=oid,band_id=int(row['band_id']),mask_path=str(path.relative_to(folder)))
            primary.append(record);details.append((record,c['mask'],source,bbox));child_area+=c['area_px']
        if remaining.any():
            yy,xx=np.nonzero(remaining);ax,ay,bx,by=int(xx.min()),int(yy.min()),int(xx.max())+1,int(yy.max())+1
            rb=[bbox[0]+ax,bbox[1]+ay,bbox[0]+bx,bbox[1]+by];rid=oid+'_REMAINDER';path=maskdir/(rid+'.npz')
            np.savez_compressed(path,mask=remaining[ay:by,ax:bx],bbox=rb)
            remainders.append(dict(id=rid,parent_id=oid,bbox=rb,area_px=int(remaining.sum()),
                                   feret_px=max_feret_centers_px(np.c_[xx,yy]),band_id=int(row['band_id']),
                                   status='UNRESOLVED_REVIEW',mask_path=str(path.relative_to(folder))))
        assert child_area+int(remaining.sum())==int(source.sum())
        partitions.append(dict(parent_id=oid,parent_area=int(source.sum()),child_area=child_area,
                               remaining_area=int(remaining.sum()),audit=audit))
    receipt.update(children=len(details),primary_count=len(primary),review_count=len(remainders))
    for name,data in [('EDGE_PRIMARY_CANDIDATES.csv',primary),('EDGE_REVIEW_REMAINDERS.csv',remainders)]:
        fields=list(dict.fromkeys(k for row in data for k in row)) or ['id']
        with (folder/name).open('w',newline='',encoding='utf-8-sig') as f:
            writer=csv.DictWriter(f,fields);writer.writeheader();writer.writerows(data)
    (folder/'edge_partition_audit.json').write_text(json.dumps(partitions,indent=2),encoding='utf-8')
    unresolved=[dict(parent_id=p['parent_id'],**q) for p in partitions for q in p['audit'].get('proposals',[])
                if q['reason']!='SPLIT_CHILD' and q.get('seed_source_pixels',0)>=settings.min_seed_source_px]
    with (folder/'EDGE_UNRESOLVED_PROPOSALS.csv').open('w',newline='',encoding='utf-8-sig') as f:
        fields=list(dict.fromkeys(k for q in unresolved for k in q)) or ['parent_id','proposal_bbox','reason']
        writer=csv.DictWriter(f,fields);writer.writeheader();writer.writerows(unresolved)
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',20)
    im=Image.fromarray(gray).convert('RGB');draw=ImageDraw.Draw(im)
    for row in primary:
        x,y,X,Y=row['bbox'];draw.rectangle((x//4,y//4,(X-1)//4,(Y-1)//4),outline='lime' if row['parent_id'] else 'cyan',width=2 if row['parent_id'] else 1)
    page=Image.new('RGB',(im.width,im.height+80),'white');page.paste(im,(0,80));d=ImageDraw.Draw(page)
    d.text((8,8),f'主候选 {len(primary)}：原正常 {len(primary)-len(details)}，边缘暗斑子对象 {len(details)}；待复核残余 {len(remainders)}',font=font,fill='black')
    d.text((8,42),'绿框为自动分离候选；原始对象保留，残余不能当作无疵病。',font=font,fill='black');page.save(folder/'EDGE_PRIMARY.png')
    # Compact before/after sheet; per-crop stretch is identical across columns.
    sheet=Image.new('RGB',(768,max(1,len(details))*300),'white');d=ImageDraw.Draw(sheet)
    for index,(row,mask,source,pbox) in enumerate(details):
        ax,ay,bx,by=row['bbox'];cx=(ax+bx)//2;cy=(ay+by)//2;rad=max(64,(max(bx-ax,by-ay)+32)//2)
        x=max(0,cx-rad);y=max(0,cy-rad);X=min(raw.shape[1],cx+rad);Y=min(raw.shape[0],cy+rad)
        ar=np.asarray(raw[y:Y,x:X],np.float32);lo,hi=np.percentile(ar,[1,99]);rgb=cv2.cvtColor(np.uint8(np.clip((ar-lo)/max(hi-lo,1)*255,0,255)),cv2.COLOR_GRAY2RGB)
        old=np.zeros(ar.shape,np.uint8);l,t,r,b=max(x,pbox[0]),max(y,pbox[1]),min(X,pbox[2]),min(Y,pbox[3])
        if l<r and t<b:old[t-y:b-y,l-x:r-x]=source[t-pbox[1]:b-pbox[1],l-pbox[0]:r-pbox[0]]
        new=np.zeros(ar.shape,np.uint8);new[ay-y:by-y,ax-x:bx-x]=mask
        for col,m in enumerate([None,old,new]):
            vis=rgb.copy()
            if m is not None:
                co,_=cv2.findContours(m,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE);cv2.drawContours(vis,co,-1,(255,80,0) if col==1 else (0,240,40),1)
            sheet.paste(Image.fromarray(vis).resize((256,256)),(col*256,index*300+44))
        d.text((5,index*300+2),row['id']+f"  A={row['area_px']}px² L={row['feret_px']:.2f}px",font=font,fill='black')
        for col,label in enumerate(['原始RAW','原大对象源轮廓','分离后独立候选']):d.text((col*256+5,index*300+23),label,font=font,fill='black')
    sheet.save(folder/'EDGE_SPOT_DETAILS.png')
    unresolved_html='<h2>未自动分离的局部提议（均保留于残余）</h2><p>坐标为RAW像素，右下不含；不能把未分离理解为无疵病。</p><table border="1"><tr><th>父对象</th><th>局部范围</th><th>原因</th></tr>'
    for q in unresolved:
        unresolved_html+='<tr>'+''.join('<td>'+html.escape(str(q[k]))+'</td>' for k in ['parent_id','proposal_bbox','reason'])+'</tr>'
    unresolved_html+='</table><p><a href="edge_partition_audit.json">完整逐提议审计</a></p>'
    (folder/'EDGE_REVIEW.html').write_text('<meta charset="utf-8"><h1>边缘暗斑分离（自动候选，待人工验收）</h1>'
        +f'<p>主候选 {len(primary)}，残余待复核 {len(remainders)}。原父对象不应与子对象重复计数。</p>'
        +'<p><a href="EDGE_PRIMARY_CANDIDATES.csv">主候选表</a> · <a href="EDGE_REVIEW_REMAINDERS.csv">残余表</a> · <a href="SIZE_REVIEW.html">原始全部待复核对象</a></p>'
        +'<img src="EDGE_PRIMARY.png" style="max-width:100%"><img src="EDGE_SPOT_DETAILS.png" style="max-width:100%">'+unresolved_html,encoding='utf-8')
    receipt['total_seconds']=time.perf_counter()-start
    (folder/'edge_spot_receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    return receipt
