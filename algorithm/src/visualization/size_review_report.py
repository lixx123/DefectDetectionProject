"""尺寸分流导出：保留全部检测对象，不改变Mask与测量。"""
import csv
import html
import json
import time
from dataclasses import asdict
from pathlib import Path
from src.detection.size_review import Settings, classify

def partition_rows(rows,bands,settings,enabled=True):
    start=time.perf_counter()
    tags=classify(rows,bands,settings) if enabled else [dict(original_id=r['new_id'],review_status='NORMAL_CANDIDATE',reason='DISABLED') for r in rows]
    all_rows=[dict(r,**{'size_'+k:v for k,v in tag.items() if k!='original_id'}) for r,tag in zip(rows,tags)]
    normal=[r for r in all_rows if r['size_review_status']=='NORMAL_CANDIDATE']
    review=[r for r in all_rows if r['size_review_status']=='SIZE_REVIEW']
    elapsed=time.perf_counter()-start
    assert len(normal)+len(review)==len(rows)
    return all_rows,normal,review,dict(enabled=enabled,settings=asdict(settings),total=len(rows),normal=len(normal),review=len(review),classification_seconds=elapsed,mask_policy='UNCHANGED_ALL_OBJECTS_RETAINED',ratio_scope='source bbox projected conservative envelope, not exact rotated mask')

def write_reports(folder,rows,bands,settings,gray,enabled=True):
    """Reuse the export's gray preview and preprocessing geometry; no RAW reread."""
    from PIL import Image,ImageDraw,ImageFont
    folder=Path(folder);start=time.perf_counter()
    all_rows,normal,review,receipt=partition_rows(rows,bands,settings,enabled)
    fields=list(dict.fromkeys(k for r in all_rows for k in r)) or ['new_id','size_review_status','size_reason']
    for name,data in [('SIZE_ALL_CANDIDATES.csv',all_rows),('SIZE_NORMAL_CANDIDATES.csv',normal),('SIZE_REVIEW_CANDIDATES.csv',review)]:
        with (folder/name).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fields);w.writeheader();w.writerows(data)
    images=[]
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',22)
    for name,data,color,title in [('SIZE_NORMAL.png',normal,'cyan','正常尺寸候选'),('SIZE_REVIEW.png',review,'orange','超限待复核：不是已确认误报')]:
        im=Image.fromarray(gray).convert('RGB');d=ImageDraw.Draw(im)
        for row in data:
            x,y,X,Y=json.loads(row['bbox_xyxy_exclusive']);d.rectangle((x//4,y//4,(X-1)//4,(Y-1)//4),outline=color)
        page=Image.new('RGB',(im.width,im.height+80),'white');page.paste(im,(0,80));d=ImageDraw.Draw(page)
        d.text((8,8),f'{title} {len(data)}；总候选{len(rows)}，待复核{len(review)}',font=font,fill='black')
        d.text((8,42),'全部源Mask保留；不能仅凭正常尺寸图作无疵病判断。',font=font,fill='black');page.save(folder/name);images.append(name)
    body=f'<meta charset="utf-8"><title>尺寸待复核</title><h1>总候选 {len(rows)} · 正常尺寸 {len(normal)} · 待复核 {len(review)}</h1><p>尺寸只是复核触发条件，不是真假判定。未删除对象或像素；必须同时检查待复核列表。</p>'
    body+='<p><a href="MEDIUM_LARGE_RAW_BOXES_AUTO_CANDIDATE.png">全部原候选图</a> · <a href="SIZE_ALL_CANDIDATES.csv">全部候选表</a> · <a href="SIZE_REVIEW_CANDIDATES.csv">待复核表</a></p>'
    for name in images:body+=f'<a href="{name}"><img src="{name}" style="max-width:100%"></a>'
    body+='<h2>待复核对象</h2><table border="1"><tr><th>ID</th><th>谱段</th><th>长度比例</th><th>厚度比例</th><th>原因</th><th>原Mask</th></tr>'
    for r in review:
        body+='<tr>'+''.join(f'<td>{html.escape(str(r.get(k,"")))}</td>' for k in ['new_id','band_id','size_length_ratio','size_thickness_ratio','size_reason'])+f'<td><a href="{html.escape(r["mask_path"].replace(chr(92),"/"))}">NPZ</a></td></tr>'
    body+='</table>'
    (folder/'SIZE_REVIEW.html').write_text(body,encoding='utf-8')
    receipt['report_total_seconds']=time.perf_counter()-start
    (folder/'size_review_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    return receipt
