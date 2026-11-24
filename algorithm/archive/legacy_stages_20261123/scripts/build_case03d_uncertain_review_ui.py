"""Create 100-case offline human-review set FROM UNCERTAIN CANDIDATES ONLY.

Selection strata are engineered to diversify uncertain examples, not random
unbiased precision/recall sampling. Excludes already-reviewed H candidate IDs.
No user labels are manufactured and no original outputs are changed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.thresholding import load_packed_mask
from scripts.run_case03d_autodetect import (
    DATA_RAW,HNPZ,SNPZ,CORRECTED,tile_for
)

SOURCE=ROOT/"outputs/case03d_autodetect/run_20261009_autodetect_final"
OUT=SOURCE/"uncertain_manual_review_batch01"


def diverse_batch(rows:pd.DataFrame,k_per_group:int=20):
    already=pd.read_csv(CORRECTED,dtype=str,keep_default_na=False)
    ids=set(already["candidate_id"])
    frame=rows[~rows["candidate_id"].isin(ids)].copy()
    frame=frame.sort_values(["peak_response_dn","area_px","candidate_id"],
                             ascending=[False,False,True],kind="mergesort")
    if not frame["triage_status"].eq("uncertain_review").all():
        raise AssertionError("uncertain-only batch required")
    aspect=frame["bbox_w"].to_numpy()/frame["bbox_h"].to_numpy()
    row_length=np.maximum(frame["bbox_w"].to_numpy(),frame["bbox_h"].to_numpy())
    linearity=pd.to_numeric(frame["linearity_proxy"],errors="coerce").fillna(0).to_numpy()
    choices=[
        ("micro_high_response",frame["area_px"].le(3)&frame["peak_response_dn"].ge(275)),
        ("interior_spotlike",frame["area_px"].ge(8)&pd.Series(
            (aspect>=.55)&(aspect<=1.9),index=frame.index)&
            (~frame["near_band_transition"])),
        ("elongated_line_like",pd.Series((linearity>=.75)&(row_length>=8)&
             ((aspect>=2)|(aspect<=.5)),index=frame.index)),
        ("band_transition_context",frame["near_band_transition"]),
        ("other_uncertain",pd.Series(np.ones(len(frame),bool),index=frame.index))
    ]
    selected=set()
    out=[]
    for label,mask in choices:
        sub=frame[mask&~frame["candidate_id"].isin(selected)].copy()
        if len(sub)<k_per_group:
            raise ValueError(f"not enough examples for {label}: {len(sub)}")
        # Coverage across response range, not only strongest examples.
        points=np.unique(np.rint(np.linspace(0,len(sub)-1,k_per_group)).astype(int))
        if len(points)!=k_per_group:
            raise AssertionError("sampling points were not unique")
        for r in sub.iloc[points].to_dict("records"):
            r["review_group"]=label
            out.append(r)
            selected.add(r["candidate_id"])
    if len(out)!=5*k_per_group or len(selected)!=len(out):
        raise AssertionError("batch lost or duplicated candidate")
    return pd.DataFrame(out)


WEBPAGE=r"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Case03-D｜自动判别不确定区域人工复核</title>
<style>
*{box-sizing:border-box}
body{font-family:"Microsoft YaHei",system-ui,Arial,sans-serif;background:#f2f5f8;color:#22344a;margin:0}
header{background:#173251;color:white;padding:19px 26px}header h1{margin:0 0 8px;font-size:22px}
header p{margin:0;font-size:13px;line-height:1.7;color:#d3e1ee}
.wrap{max-width:1240px;margin:18px auto;padding:0 15px;display:grid;grid-template-columns:248px 1fr;gap:16px}
.panel{background:white;border-radius:12px;border:1px solid #dce3eb;padding:17px;box-shadow:0 1px 5px #142c3910}
h2{font-size:16px;margin:0 0 10px}h3{font-size:13px;margin:17px 0 9px}
.muted{font-size:12px;color:#607087;line-height:1.6}
input,select,textarea{font:inherit;border:1px solid #bbc9d9;border-radius:7px;padding:8px}
button{border:0;background:#1d5f9c;color:white;border-radius:8px;padding:10px 13px;cursor:pointer;font:inherit}
button.secondary{background:#eaf0f6;color:#1b476a}button.warn{background:#fff3e0;color:#794900}
button.good{background:#147d65}button.negative{background:#b1573b}
button:focus-visible{outline:3px solid #76ace6}
button.active{box-shadow:0 0 0 3px #8bd3b8 inset}
#img{display:block;width:100%;max-width:980px;object-fit:contain;border:1px solid #ccd6e1;background:#121820;image-rendering:pixelated}
.toolbar{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin:14px 0}
.pill{display:inline-block;padding:5px 9px;background:#edf2f7;border-radius:6px;font-size:12px}
.selection{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}
#status{background:#e8f7f1;color:#164c39;padding:9px;border-radius:7px;font-size:13px}
.field{display:flex;gap:7px;flex-direction:column;font-size:13px;margin:9px 0}
#caseList{height:600px;overflow:auto;display:flex;flex-direction:column;gap:4px}
.case{border:1px solid #dce3ee;background:white;color:#26394c;text-align:left;padding:9px;display:block;width:100%}
.case.selected{background:#e9f5fb;border-color:#4383bf}
.case.reviewed:after{content:"✓";float:right;color:#137855}
.info{font-size:13px;line-height:1.75}
.info b{font-weight:600}
@media(max-width:870px){.wrap{grid-template-columns:1fr}#caseList{height:220px}.panel{padding:12px}}
</style></head>
<body><header><h1>Case03-D｜只复核自动判别的不确定候选</h1>
<p>本批100个候选从6,685个不确定区域分层挑选，用于查找点状、细线、低响应和过渡背景的误判规律。图片/标签均保留本地，不上传云端。</p></header>
<div class="wrap">
<aside class="panel">
<h2>样品26第1帧｜待复核100处</h2>
<div class="muted" id="progress"></div>
<label class="field">选择类别<select id="groupFilter">
<option value="">全部5类</option><option>micro_high_response</option>
<option>interior_spotlike</option><option>elongated_line_like</option>
<option>band_transition_context</option><option>other_uncertain</option>
</select></label>
<div id="caseList"></div>
</aside>
<main class="panel">
<h2 id="title"></h2>
<p class="muted">每张图依次显示：左边原始RAW；中间所有S230黄色/H170新增青色响应；右边当前候选的<strong>精确8连通区域（绿色）</strong>及红色外接框。三个视图均使用实际原始RAW坐标。</p>
<img id="img" alt="RAW、全部S/H掩膜、指定候选精确轮廓">
<div class="info" id="features"></div>
<h3>人工判断：仅判断当前绿色候选本身</h3>
<div class="selection">
<button class="good" data-label="confirmed_dark_spot">暗点异常</button>
<button class="good" data-label="confirmed_fine_line">细线/划痕异常</button>
<button class="negative" data-label="background_artifact">背景伪影/噪声</button>
<button class="secondary" data-label="uncertain">无法确定</button>
<button class="warn" data-label="">清除标注</button>
</div>
<label class="field">备注（可选）<textarea rows="2" id="note" placeholder="如：亮暗过渡、设备标记、疑似弱暗点；不确定请记录原因"></textarea></label>
<div class="toolbar">
<button class="secondary" id="prev">上一处</button><button class="secondary" id="next">下一处</button>
<button class="secondary" id="exportBackup">导出JSON备份</button>
<button class="secondary" id="importBackupBtn">导入JSON备份</button>
<input id="importBackup" type="file" accept=".json" hidden>
<button id="exportCsv">导出人工复核CSV</button>
</div>
<div id="status">请先查看原RAW与精确连通域，再给出判断。未判断的条目不会被当作负样本。</div>
<p class="muted">标注只保存在当前打开的页面中。请定期导出JSON备份；完成后点击导出CSV，并将文件保存到工程或告诉ChatGPT路径。本阶段的人工视觉异常标签仍不能证明异常一定来自滤光片表面。</p>
</main></div>
<script id="manifest" type="application/json">__DATA__</script>
<script>
"use strict";
const DATA=JSON.parse(document.getElementById("manifest").textContent);
let current=0,marks={},noteCache={};
const byId={};DATA.forEach((v,i)=>byId[v.candidate_id]=i);
function el(k){return document.getElementById(k)}
function esc(s){return String(s).replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;")}
function renderList(){
 const filter=el("groupFilter").value;
 const count=Object.values(marks).filter(x=>x.manual_label).length;
 el("progress").textContent="已复核 "+count+" / "+DATA.length+"；未复核的不自动作为噪声";
 el("caseList").innerHTML="";
 DATA.forEach((r,i)=>{
  if(filter && filter!==r.review_group)return;
  const b=document.createElement("button");
  b.className="case"+(current===i?" selected":"")+(marks[r.candidate_id]&&marks[r.candidate_id].manual_label?" reviewed":"");
  b.textContent=String(i+1).padStart(3,"0")+" | "+r.review_group+" | "+r.candidate_id.replace("H_sample26_","");
  b.onclick=()=>choose(i);el("caseList").appendChild(b);
 });
}
function choose(i){
 if(DATA[current])noteCache[DATA[current].candidate_id]=el("note").value;
 current=(i+DATA.length)%DATA.length;
 const r=DATA[current];
 el("title").textContent=String(current+1)+"/"+DATA.length+"  "+r.candidate_id;
 el("img").src=r.image_rel;
 el("features").innerHTML="<p>区域类型："+esc(r.review_group)+"　算法状态：<b>不确定，需人工复核</b><br>"+
   "面积："+r.area_px+" px　Black-Hat峰值："+r.peak_response_dn+" DN<br>"+
   "完整RAW中心位置：(x="+r.centroid_x+", y="+r.centroid_y+")<br>"+
   "外接框：[x="+r.bbox_x+", y="+r.bbox_y+", w="+r.bbox_w+", h="+r.bbox_h+"]</p>";
 el("note").value=noteCache[r.candidate_id]||"";
 for(const b of document.querySelectorAll("[data-label]"))b.classList.toggle("active",
     !!marks[r.candidate_id]&&marks[r.candidate_id].manual_label===b.dataset.label);
 renderList();
 el("status").textContent=marks[r.candidate_id]?
     "当前已有人工标签："+marks[r.candidate_id].manual_label:"此候选尚无人工判断。";
}
function label(tag){
 const r=DATA[current];noteCache[r.candidate_id]=el("note").value;
 if(!tag){delete marks[r.candidate_id];}
 else{marks[r.candidate_id]={candidate_id:r.candidate_id,manual_label:tag,
       review_status:"reviewed",source_case:"case03d_r2_sample26_uncertain",
       selection_group:r.review_group,note:el("note").value,
       source_image:r.image_rel};}
 choose(current);
}
for(const b of document.querySelectorAll("[data-label]"))b.onclick=()=>label(b.dataset.label);
el("prev").onclick=()=>choose(current-1);
el("next").onclick=()=>choose(current+1);
el("groupFilter").onchange=renderList;
el("note").oninput=()=>{noteCache[DATA[current].candidate_id]=el("note").value;
  if(marks[DATA[current].candidate_id])marks[DATA[current].candidate_id].note=el("note").value;};
function download(name,data,type){
 const blob=new Blob([data],{type:type});
 const href=URL.createObjectURL(blob);
 const a=document.createElement("a");a.href=href;a.download=name;
 document.body.appendChild(a);a.click();a.remove();
 setTimeout(()=>URL.revokeObjectURL(href),5000);
}
el("exportBackup").onclick=()=>{
 download("case03d_uncertain_review_backup.json",
  JSON.stringify({schema:1,source:"case03d_r2_uncertain_batch01",
  marks:Object.values(marks),noteCache:noteCache},null,2),"application/json");
 el("status").textContent="JSON备份已导出到浏览器下载目录。";
};
el("importBackupBtn").onclick=()=>el("importBackup").click();
el("importBackup").onchange=async ev=>{
 const f=ev.target.files[0];if(!f)return;
 try{
   const j=JSON.parse(await f.text());
   if(j.schema!==1||j.source!=="case03d_r2_uncertain_batch01")throw Error("不是本工具的备份");
   if(!Array.isArray(j.marks)||j.marks.some(x=>!byId.hasOwnProperty(x.candidate_id)))throw Error("存在未知ID");
   marks={};for(const r of j.marks)marks[r.candidate_id]=r;
   noteCache=j.noteCache||{};choose(current);
   el("status").textContent="成功恢复 "+Object.keys(marks).length+" 个记录。";
 }catch(err){el("status").textContent="备份导入失败："+err.message}
 ev.target.value="";
};
el("exportCsv").onclick=()=>{
 const rows=DATA.filter(x=>marks[x.candidate_id]).map(x=>marks[x.candidate_id]);
 if(!rows.length){el("status").textContent="还没有人工标签，先选一个候选。";return;}
 const fields=["candidate_id","manual_label","review_status","source_case","selection_group","note","source_image"];
 function cell(x){return '"'+String(x??"").replaceAll('"','""')+'"';}
 const lines=[fields.map(cell).join(",")];
 for(const r of rows)lines.push(fields.map(k=>cell(r[k])).join(","));
 download("case03d_uncertain_review_batch01.csv","\ufeff"+lines.join("\r\n")+"\r\n","text/csv;charset=utf-8");
 el("status").textContent="已导出 "+rows.length+" 个人工复核标签；未选择的条目不在CSV中。";
};
choose(0);
</script></body></html>""";


def main():
    if OUT.exists():
        raise FileExistsError(f"do not overwrite a human annotation batch: {OUT}")
    OUT.mkdir()
    image_dir=OUT/"assets"
    image_dir.mkdir()
    data=pd.read_csv(SOURCE/"uncertain_review_full.csv",low_memory=False)
    rows=diverse_batch(data,20)
    S=load_packed_mask(SNPZ)
    H=load_packed_mask(HNPZ)
    raw=np.memmap(DATA_RAW,mode="r",dtype=">u2",shape=H.shape)
    manifest=[]
    for i,r in enumerate(rows.to_dict("records")):
        tile=tile_for(r,raw,H,S,size=160)
        name=f"{i+1:03d}_{r['candidate_id']}.jpg"
        ok,encoded=cv2.imencode(".jpg",tile,[cv2.IMWRITE_JPEG_QUALITY,80])
        if not ok:raise IOError(name)
        (image_dir/name).write_bytes(encoded.tobytes())
        rec={
            "candidate_id":r["candidate_id"],"review_group":r["review_group"],
            "image_rel":"assets/"+name,"area_px":int(r["area_px"]),
            "peak_response_dn":int(r["peak_response_dn"]),
            "centroid_x":float(r["centroid_x"]),"centroid_y":float(r["centroid_y"]),
            "bbox_x":int(r["bbox_x"]),"bbox_y":int(r["bbox_y"]),
            "bbox_w":int(r["bbox_w"]),"bbox_h":int(r["bbox_h"]),
        }
        manifest.append(rec)
    page=WEBPAGE.replace("__DATA__",json.dumps(manifest,ensure_ascii=False))
    (OUT/"index.html").write_text(page,encoding="utf-8")
    pd.DataFrame(manifest).to_csv(OUT/"review_batch_100_manifest.csv",
                                  index=False,encoding="utf-8-sig")
    (OUT/"README.md").write_text(
        "# Case03-D-R2 不确定候选人工复核100例（离线）\n\n"
        "双击index.html，查看当前候选的原RAW、S/H综合掩膜和绿色的精确H连通域。\n"
        "人工可标暗点、线状异常、背景伪影或不确定；无需每项都标注。"
        "只导出已复核的CSV；刷新网页前保存JSON备份，所有数据仅在本机。\n"
        "每组20条，总计100条：高响应单像素、内部点状、延长线状、亮暗过渡和其他不确定。\n"
        "本次抽样用于改善算法开发，不是可用于无偏估计全图准确率的随机验证集。\n"
        "人工标注仍只是影像异常，不证明一定源自滤光片表面。\n",
        encoding="utf-8")
    print("REVIEW_UI_READY",OUT/"index.html")
    print("REVIEW_BATCH_COUNT",len(manifest),"GROUPS",rows["review_group"].value_counts().to_dict())
    print("REVIEW_ASSET_COUNT",len(list(image_dir.glob("*.jpg"))))


if __name__=="__main__":
    main()
