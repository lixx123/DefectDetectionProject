"""Build offline, point/box human target-review page for 9 clarified sample26 ROIs.

This is a static, no-network UI. A user clicks the *actual anomaly*, not the
preselected red component. It exports a CSV with global RAW (x,y), target kind,
color membership and optional boxes; exact H IDs require validated re-linking.
Source RAW/case02/case03 outputs and user's manual_review_template.xlsx remain
read-only.
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
from datetime import datetime
from pathlib import Path
import sys

import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"outputs/case03c/run_20261008_174000"
REVIEW_DIR=ROOT/"outputs/case03c_revision/run_20261009_reference_feature_review"
OUTROOT=ROOT/"outputs/case03c_manual_retarget"
TARGETS={
 18:("cyan","青色部分有暗异常：点选真正异常位置"),
 19:("cyan","青色部分有暗异常：点选真正异常位置"),
 21:("cyan","青色部分有暗异常：点选真正异常位置"),
 24:("yellow_and_cyan","黄色、青色均有异常：需要分别添加至少2条标记"),
 27:("cyan","青色部分有暗异常：点选真正异常位置"),
 31:("lower_left","左下角肉眼可见未完整提取暗区：拖框圈定"),
 39:("yellow","黄色高阈值区域有异常：点选黄色核心"),
 46:("lower_right","右下角肉眼可见未完整提取暗区：拖框圈定"),
 56:("left","左侧肉眼可见未完整提取暗区：拖框圈定"),
}
ROUGH={
 31:(20,133,151,217),
 46:(202,186,256,250),
 56:(30,40,130,133),
}


def normalize_raw(raw:np.ndarray)->np.ndarray:
    lo,hi=np.percentile(raw,[1.0,99.5])
    hi=max(float(hi),float(lo)+1.0)
    return np.uint8(np.rint(255*np.clip((raw.astype(np.float32)-lo)/(hi-lo),0,1)))


def save_rgb(path:Path,arr:np.ndarray):
    # OpenCV imwrite may silently fail when Windows paths contain Chinese.
    data=cv2.cvtColor(arr,cv2.COLOR_RGB2BGR) if arr.ndim==3 else arr
    ok,buffer=cv2.imencode(".png",data)
    if not ok:
        raise OSError(f"Failed encoding PNG: {path}")
    path.write_bytes(buffer.tobytes())
    if not path.is_file() or path.stat().st_size==0:
        raise OSError(f"Failed writing PNG: {path}")


def packbits_base64(mask:np.ndarray)->str:
    return base64.b64encode(np.packbits(mask.reshape(-1).astype(np.uint8),bitorder="little").tobytes()).decode("ascii")


def build_assets(out:Path)->list[dict]:
    image_dir=out/"assets"
    image_dir.mkdir(parents=True)
    manifest=[]
    for number,(provenance,hint) in TARGETS.items():
        path=next((REVIEW_DIR/"patches").glob(f"review_{number:03d}_reference_corrected.npz"))
        with np.load(path,allow_pickle=False) as d:
            raw=np.asarray(d["raw_dn"],dtype=np.uint16)
            response=np.asarray(d["response_dn"],dtype=np.uint16)
            s=np.asarray(d["S230"],dtype=bool)
            h=np.asarray(d["H170_230"],dtype=bool)
            selected=np.asarray(d["selected_candidate"],dtype=bool)
            origin=np.asarray(d["origin_xy"],dtype=np.int64)
        if raw.shape!=(256,256) or not np.all(s<=h) or not np.all(selected<=h):
            raise ValueError(f"invalid mask shape/containment for review_{number:03d}")
        scaled=normalize_raw(raw)
        # Overlay only changes display. Yellow=core, cyan=weak appended, red contour=old wrong target.
        image=np.repeat(scaled[...,None],3,axis=2).astype(np.float32)
        image[s]=image[s]*.18+np.array([255,220,45],dtype=np.float32)*.82
        image[h&~s]=image[h&~s]*.18+np.array([36,224,242],dtype=np.float32)*.82
        display=np.uint8(np.clip(np.rint(image),0,255))
        cnts,_=cv2.findContours((selected*255).astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(display,cnts,-1,(255,45,65),1)
        resp_cap=max(float(np.percentile(response,99.5)),1.)
        rsp8=np.uint8(np.rint(np.clip(response.astype(np.float32)/resp_cap,0,1)*255))
        color=cv2.cvtColor(cv2.applyColorMap(rsp8,cv2.COLORMAP_MAGMA),cv2.COLOR_BGR2RGB)
        prefix=f"review_{number:03d}"
        save_rgb(image_dir/(prefix+"_raw.png"),scaled)
        save_rgb(image_dir/(prefix+"_overlay.png"),display)
        save_rgb(image_dir/(prefix+"_response.png"),color)
        record={
            "review_id":prefix,"number":number,
            "hint":hint,"confirmed_visual_part":provenance,
            "origin_xy":[int(origin[0]),int(origin[1])],
            "old_red_selected_area_px":int(selected.sum()),
            "roi_mask_S230_area_px":int(s.sum()),
            "roi_mask_H170_area_px":int(h.sum()),
            "raw_image":f"assets/{prefix}_raw.png",
            "overlay_image":f"assets/{prefix}_overlay.png",
            "response_image":f"assets/{prefix}_response.png",
            "S_mask_base64":packbits_base64(s),
            "H_mask_base64":packbits_base64(h),
            "rough_box":ROUGH.get(number),
            "preliminary_label":"visual_detected_color_roi" if number not in ROUGH else "visual_undersegmented_roi",
        }
        manifest.append(record)
        print(prefix,"origin",record["origin_xy"],"S",record["roi_mask_S230_area_px"],"H",record["roi_mask_H170_area_px"],flush=True)
    return manifest


PAGE=r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Case03-C｜样品26｜9处人工目标复核</title>
<style>
:root{font-family:system-ui,-apple-system,"Microsoft YaHei",Arial,sans-serif;color:#223047;background:#f4f6fa;}
*{box-sizing:border-box}body{margin:0}header{background:#152b45;color:#fff;padding:18px 24px}
header h1{font-size:19px;font-weight:650;margin:0 0 8px}header p{margin:0;opacity:.85;font-size:13px;line-height:1.6}
.layout{display:grid;grid-template-columns:240px minmax(660px,1fr);gap:18px;max-width:1570px;margin:20px auto;padding:0 18px}
.panel{background:#fff;border:1px solid #e0e6ec;border-radius:12px;box-shadow:0 1px 5px #122b4410;padding:15px}
h2{font-size:16px;margin:3px 0 10px}h3{font-size:14px;margin:12px 0 8px}
.roilist{display:flex;flex-direction:column;gap:6px}
.roi-btn{border:1px solid #dde4eb;background:#fff;border-radius:8px;text-align:left;cursor:pointer;padding:10px 11px;color:#304053}
.roi-btn.active{border-color:#2462a3;background:#eaf3fb;font-weight:650}.roi-btn span{float:right;color:#6d7f94}
.roi-btn.reviewed span{color:#16784e}
.hint{padding:10px;background:#f1f5f9;border-radius:8px;font-size:13px;line-height:1.55}
.muted{color:#64748b;font-size:12px}.mainhead{display:flex;align-items:center;justify-content:space-between;gap:12px}
.vizrow{display:flex;flex-wrap:wrap;justify-content:center;gap:14px;margin-top:15px}
.viz{text-align:center;min-width:280px;flex:1}.viz-title{font-size:13px;font-weight:600;margin-bottom:6px}
canvas{display:block;width:100%;max-width:420px;aspect-ratio:1;border:1px solid #bac7d5;margin:auto;cursor:crosshair;image-rendering:pixelated;background:#090c12;touch-action:none}
.color-key{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;margin:10px 0;color:#475569}
.sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px}
.controls{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end;margin:12px 0}
.ctrl{display:flex;flex-direction:column;gap:4px;font-size:12px;font-weight:600}
select,input[type=text]{padding:9px;border:1px solid #c7d1dc;border-radius:7px;font-size:13px}
button.action{border:0;border-radius:8px;background:#1e578d;color:white;padding:10px 14px;cursor:pointer;font-weight:650}
button.secondary{background:#ebf1f7;color:#28455f}
button.danger{background:#fff2f1;color:#a02a2a}
.actions{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}
table{border-collapse:collapse;width:100%;font-size:12px}td,th{border-bottom:1px solid #e7edf3;text-align:left;padding:7px;line-height:1.45}
.note{padding:10px;background:#fff8e4;border:1px solid #efd59a;border-radius:8px;font-size:12px;line-height:1.5}
.status{font-size:13px;padding:8px 10px;border-radius:7px;background:#edf8f5;color:#175940;min-height:34px}
@media(max-width:900px){.layout{grid-template-columns:1fr}.vizrow{flex-direction:column}.viz{width:100%}}
</style>
</head>
<body>
<header>
<h1>样品26｜Case03-C 人工目标点选与框选</h1>
<p>本页离线运行，不上传图像或标注。请在原始RAW中标出<strong>实际异常目标</strong>，不要仅因为原图红色框选了某个候选，就把它标成疵病。<br>
阳性/正候选=人工确认选中目标具有暗点/划痕类异常形态；阴性/负候选=人工确认<strong>选中目标</strong>是噪点或伪影；「欠分割」=看得到异常但掩膜未完整覆盖。以上均不直接证明来源于滤光片。</p>
</header>
<div class="layout">
<aside class="panel">
 <h2>待复核的9张图</h2>
 <div id="roiList" class="roilist"></div>
 <h3>复核原则</h3>
 <p class="hint">18/19/21/27：点选青色异常。<br>24：黄色和青色<strong>分别标记</strong>（可多条）。<br>39：点选黄色异常。<br>31/46/56：在RAW上拖动矩形框住未完整检测的暗区。</p>
 <p class="muted">黄色=单阈值S230；青色=H170/230新增；旧红色轮廓=此前误选的目标，仅供参考。</p>
 <p class="note">标记完成后点击“导出CSV”。刷新前也可以“导出JSON备份”；重开页面后可通过“导入JSON”恢复。浏览器不自动把记录写回工程。</p>
</aside>
<main class="panel">
 <div class="mainhead"><h2 id="currentTitle">review_018</h2><div class="muted" id="coords"></div></div>
 <div class="hint" id="currentHint"></div>
 <div class="color-key">
 <span><span class="sw" style="background:#ffdc2d"></span>黄色=S230高阈值</span>
 <span><span class="sw" style="background:#24e0f2"></span>青色=H170新增</span>
 <span><span class="sw" style="background:#fc455e"></span>红色轮廓=旧选中目标</span>
 <span><span class="sw" style="background:#20a370"></span>绿色轮廓=你本次新增的人工标记</span>
 </div>
 <div class="vizrow">
   <div class="viz"><div class="viz-title">原始RAW（只做显示拉伸）</div><canvas id="raw" width="256" height="256"></canvas></div>
   <div class="viz"><div class="viz-title">S230 / H170/230 分割叠加</div><canvas id="overlay" width="256" height="256"></canvas></div>
   <div class="viz"><div class="viz-title">Black-Hat响应（仅显示）</div><canvas id="response" width="256" height="256"></canvas></div>
 </div>
 <div class="controls">
  <label class="ctrl">标注方式<select id="mode"><option value="point">点选（选择目标点）</option><option value="box">框选（拖拽包围异常）</option></select></label>
  <label class="ctrl">人工判断<select id="label">
    <option value="visual_dark_spot">正候选：可见暗点</option>
    <option value="visual_fine_line">正候选：可见细线/划痕</option>
    <option value="background_artifact">负候选：噪点/伪影</option>
    <option value="undersegmented_visible_anomaly">人工可见但分割不完整</option>
    <option value="uncertain">不确定</option>
   </select></label>
  <label class="ctrl" style="flex:1;min-width:190px">备注（可选）<input id="note" type="text" placeholder="如：中间青色点、左下弱暗斑"></label>
 </div>
 <div class="status" id="status">请选择目标。</div>
 <h3>当前图中的人工标记</h3>
 <div style="overflow:auto"><table><thead><tr><th>序号</th><th>判断</th><th>目标坐标（RAW）</th><th>点位归属</th><th>操作</th></tr></thead><tbody id="marks"></tbody></table></div>
 <div class="actions">
   <button class="action" id="exportCsv">导出CSV供候选关联</button>
   <button class="action secondary" id="exportJson">导出JSON备份</button>
   <label class="action secondary" style="cursor:pointer">导入JSON<input id="importJson" type="file" accept=".json,application/json" hidden></label>
   <button class="action secondary" id="previous">上一张</button>
   <button class="action secondary" id="next">下一张</button>
   <button class="action danger" id="clearRoi">清除当前图标记</button>
 </div>
 <p class="muted">坐标采用完整原始RAW图像的列x、行y（0起始）。点位显示S230、H170新增或阈值未命中；框选只代表人工异常范围，不自动当作逐像素真值。候选ID将在后续经全图连通域精确匹配后填写。</p>
</main>
</div>
<script id="review-data" type="application/json">__REVIEW_DATA__</script>
<script>
"use strict";
const dataset=JSON.parse(document.getElementById("review-data").textContent);
let active=0;
let marks=[];
const imgs={}, decoded={};
let drag=null;
const canvasIds=["raw","overlay","response"];
function roi(){return dataset.rois[active]}
function decodePacked(b64){
 const binary=atob(b64); const bytes=new Uint8Array(binary.length);
 for(let i=0;i<binary.length;i++)bytes[i]=binary.charCodeAt(i);
 return bytes;
}
function bitAt(bytes,x,y){const v=y*256+x;return ((bytes[v>>3]>>(v&7))&1)===1}
function maskKind(rec,x,y){
 const bs=decoded[rec.review_id];if(!bs)return "loading";
 if(bitAt(bs.s,x,y))return "S230_yellow";
 if(bitAt(bs.h,x,y))return "H170_only_cyan";
 return "no_segmented_pixel";
}
function loadImages(record){
 decoded[record.review_id]={s:decodePacked(record.S_mask_base64),h:decodePacked(record.H_mask_base64)};
 for(const name of canvasIds){
  const im=new Image();imgs[name]=im;im.src=record[name+"_image"];
  im.onload=()=>render();
  im.onerror=()=>setStatus("找不到图像资源："+im.src,true);
 }
}
function setStatus(msg,error=false){const el=document.getElementById("status");el.textContent=msg;el.style.background=error?"#fff2ec":"#edf8f5";el.style.color=error?"#a33426":"#175940"}
function point(event,can){
 const r=can.getBoundingClientRect();
 return [Math.max(0,Math.min(255,Math.floor((event.clientX-r.left)*256/r.width))),
         Math.max(0,Math.min(255,Math.floor((event.clientY-r.top)*256/r.height)))];
}
function annotationsForCurrent(){return marks.filter(m=>m.review_id===roi().review_id)}
function render(){
 const r=roi();
 for(const name of canvasIds){
  const can=document.getElementById(name);const ctx=can.getContext("2d");
  ctx.clearRect(0,0,256,256);
  if(imgs[name]&&imgs[name].complete&&imgs[name].naturalWidth)ctx.drawImage(imgs[name],0,0,256,256);
  else{ctx.fillStyle="#101621";ctx.fillRect(0,0,256,256)}
  ctx.lineWidth=1.5;ctx.strokeStyle="#18d779";ctx.fillStyle="#18d779";
  for(const m of annotationsForCurrent()){
   if(m.mode==="point"){
    ctx.beginPath();ctx.arc(m.local_x,m.local_y,5.5,0,Math.PI*2);ctx.stroke();
    ctx.beginPath();ctx.moveTo(m.local_x-10,m.local_y);ctx.lineTo(m.local_x+10,m.local_y);ctx.moveTo(m.local_x,m.local_y-10);ctx.lineTo(m.local_x,m.local_y+10);ctx.stroke();
   } else ctx.strokeRect(m.local_x0,m.local_y0,Math.max(1,m.local_x1-m.local_x0),Math.max(1,m.local_y1-m.local_y0));
  }
  if(drag&&drag.review_id===r.review_id&&drag.mode==="box"){
   ctx.strokeStyle="#39ef81";ctx.setLineDash([3,2]);
   ctx.strokeRect(Math.min(drag.x0,drag.x1),Math.min(drag.y0,drag.y1),Math.abs(drag.x0-drag.x1)+1,Math.abs(drag.y0-drag.y1)+1);
   ctx.setLineDash([]);
  }
 }
 renderMarkTable();
}
function choose(i){
 active=i;drag=null;
 const r=roi();document.getElementById("currentTitle").textContent=r.review_id+"｜样品26 / 第1帧";
 document.getElementById("currentHint").textContent="此前人工确认："+r.hint+"；旧红色选中区域"+r.old_red_selected_area_px+"px。本工具不自动把旧红色ID作为正候选。";
 document.getElementById("coords").textContent="RAW ROI原点 x="+r.origin_xy[0]+", y="+r.origin_xy[1];
 const suggested=r.rough_box?"box":"point";
 document.getElementById("mode").value=suggested;
 document.getElementById("label").value=r.rough_box?"undersegmented_visible_anomaly":"visual_dark_spot";
 document.getElementById("note").value="";
 document.getElementById("roiList").innerHTML=dataset.rois.map((rec,n)=>{
   const count=marks.filter(m=>m.review_id===rec.review_id).length;
   return '<button class="roi-btn '+(n===i?"active ":"")+(count?"reviewed":"")+'" data-index="'+n+'">'+rec.review_id+'<span>'+(count?count+"条":"待标")+'</span></button>';
 }).join("");
 for(const b of document.querySelectorAll(".roi-btn"))b.addEventListener("click",()=>choose(Number(b.dataset.index)));
 loadImages(r);render();
 setStatus("请选择RAW中的真正暗异常：青色/黄色可单击，未完整检出的较大暗区请拖动矩形。");
}
function addMark(record){
 const r=roi();
 record.review_id=r.review_id;record.source_sample=26;record.source_frame=1;
 record.annotation_id="manual_"+Date.now()+"_"+Math.floor(Math.random()*1e6);
 record.label=document.getElementById("label").value;
 record.note=document.getElementById("note").value;
 record.original_red_candidate_id=""; // explicitly not trusted target ID
 record.retargeted_full_H_candidate_id=""; // computed only after full-image crosscheck
 marks.push(record);
 choose(active);
 setStatus("已新增一条人工定位；你可以继续对同一张图标记其他异常。");
}
for(const name of canvasIds){
 const can=document.getElementById(name);
 can.addEventListener("pointerdown",ev=>{
  if(ev.button!==0)return;
  ev.preventDefault();can.setPointerCapture(ev.pointerId);
  const [x,y]=point(ev,can);
  drag={review_id:roi().review_id,mode:document.getElementById("mode").value,x0:x,y0:y,x1:x,y1:y};
  render();
 });
 can.addEventListener("pointermove",ev=>{
  if(!drag || drag.review_id!==roi().review_id)return;
  const [x,y]=point(ev,can);drag.x1=x;drag.y1=y;render();
 });
 can.addEventListener("pointerup",ev=>{
  if(!drag||drag.review_id!==roi().review_id)return;
  const [x,y]=point(ev,can);drag.x1=x;drag.y1=y;
  const r=roi();const mode=drag.mode;
  const label=document.getElementById("label").value;
  if(mode==="point"){
   const mark={mode,local_x:x,local_y:y,raw_global_x:r.origin_xy[0]+x,raw_global_y:r.origin_xy[1]+y,
       mask_membership_at_point:maskKind(r,x,y)};
   if(mark.mask_membership_at_point==="no_segmented_pixel"&&label!=="undersegmented_visible_anomaly"&&label!=="uncertain")
     setStatus("该点未达到现有分割阈值。若标记的是肉眼暗斑，请改为“人工可见但分割不完整”。",true);
   addMark(mark);
  }else{
   const x0=Math.min(drag.x0,drag.x1),x1=Math.max(drag.x0,drag.x1)+1;
   const y0=Math.min(drag.y0,drag.y1),y1=Math.max(drag.y0,drag.y1)+1;
   if(x1-x0<3||y1-y0<3){drag=null;setStatus("框选至少宽高3像素，请重新拖动。",true);render();return;}
   let sCount=0,hCount=0;
   const bs=decoded[r.review_id];
   for(let j=y0;j<y1;j++)for(let k=x0;k<x1;k++){if(bitAt(bs.s,k,j))sCount++;if(bitAt(bs.h,k,j))hCount++}
   addMark({mode,local_x0:x0,local_y0:y0,local_x1:x1,local_y1:y1,
    raw_global_x0:r.origin_xy[0]+x0,raw_global_y0:r.origin_xy[1]+y0,
    raw_global_x1:r.origin_xy[0]+x1,raw_global_y1:r.origin_xy[1]+y1,
    box_S230_pixel_count:sCount,box_H170_pixel_count:hCount,
    mask_membership_at_point:"region_annotation_not_per_pixel_GT"});
  }
  drag=null;render();
 });
}
function esc(s){return String(s).replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;")}
function renderMarkTable(){
 document.getElementById("marks").innerHTML=annotationsForCurrent().map((m,i)=>{
 const p=m.mode==="point"?("("+m.raw_global_x+","+m.raw_global_y+")"):
       ("["+m.raw_global_x0+","+m.raw_global_y0+" → "+m.raw_global_x1+","+m.raw_global_y1+"]");
 return "<tr><td>"+(i+1)+"</td><td>"+esc(m.label)+"</td><td>"+esc(p)+"</td><td>"+esc(m.mask_membership_at_point)+"</td><td><button class='action danger remove' data-id='"+esc(m.annotation_id)+"' style='padding:5px 8px'>删除</button></td></tr>";
 }).join("")||"<tr><td colspan='5' class='muted'>尚未标注此图。</td></tr>";
 for(const btn of document.querySelectorAll(".remove"))btn.addEventListener("click",()=>{
   marks=marks.filter(x=>x.annotation_id!==btn.dataset.id);choose(active);
 });
}
document.getElementById("previous").addEventListener("click",()=>choose((active-1+dataset.rois.length)%dataset.rois.length));
document.getElementById("next").addEventListener("click",()=>choose((active+1)%dataset.rois.length));
document.getElementById("clearRoi").addEventListener("click",()=>{
 if(!confirm("清除当前图片的全部人工标记？"))return;
 marks=marks.filter(m=>m.review_id!==roi().review_id);choose(active);
});
function exportFile(filename,text,mime){
 const blob=new Blob([text],{type:mime});
 const href=URL.createObjectURL(blob);
 const a=document.createElement("a");a.href=href;a.download=filename;
 document.body.appendChild(a);a.click();a.remove();
 setTimeout(()=>URL.revokeObjectURL(href),5000);
}
const fields=["annotation_id","review_id","source_sample","source_frame","label","mode","note",
"raw_global_x","raw_global_y","raw_global_x0","raw_global_y0","raw_global_x1","raw_global_y1",
"local_x","local_y","local_x0","local_y0","local_x1","local_y1",
"mask_membership_at_point","box_S230_pixel_count","box_H170_pixel_count",
"original_red_candidate_id","retargeted_full_H_candidate_id"];
function csvCell(value){let t=value==null?"":String(value);return '"'+t.replaceAll('"','""')+'"'}
document.getElementById("exportCsv").addEventListener("click",()=>{
 if(!marks.length){setStatus("尚无标注，请先点选或框选。",true);return;}
 const lines=[fields.map(csvCell).join(",")];
 for(const rec of marks)lines.push(fields.map(k=>csvCell(rec[k])).join(","));
 exportFile("case03c_sample26_user_retarget.csv","\ufeff"+lines.join("\r\n")+"\r\n","text/csv;charset=utf-8");
 setStatus("已导出CSV（通常在浏览器“下载”目录）。请把文件放入工程目录，再通知我关联候选ID。");
});
document.getElementById("exportJson").addEventListener("click",()=>{
 exportFile("case03c_sample26_user_retarget_backup.json",JSON.stringify({schema:1,source:"offline_case03c_retarget",annotations:marks},null,2),"application/json");
 setStatus("JSON备份已保存到浏览器下载目录。");
});
document.getElementById("importJson").addEventListener("change",async ev=>{
 const file=ev.target.files[0];if(!file)return;
 try{
   const d=JSON.parse(await file.text());
   if(!d||!Array.isArray(d.annotations)||d.schema!==1)throw Error("非本工具备份格式");
   const validIds=new Set(dataset.rois.map(r=>r.review_id));
   if(!d.annotations.every(a=>validIds.has(a.review_id)&&["point","box"].includes(a.mode)))throw Error("存在未知review_id或模式");
   marks=d.annotations;choose(active);setStatus("已导入"+marks.length+"条人工标注。");
 }catch(err){setStatus("导入失败："+err.message,true)}
 ev.target.value="";
});
choose(0);
</script>
</body></html>""";


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--run-id",default=None)
    args=parser.parse_args()
    out=OUTROOT/(args.run_id or datetime.now().strftime("run_%Y%m%d_%H%M%S"))
    if out.exists():raise FileExistsError(f"refuse overwrite existing review session: {out}")
    out.mkdir(parents=True)
    rois=build_assets(out)
    page=PAGE.replace("__REVIEW_DATA__",json.dumps({"rois":rois},ensure_ascii=False))
    (out/"index.html").write_text(page,encoding="utf-8")
    manifest=[]
    for row in rois:
        safe={k:v for k,v in row.items() if not k.endswith("_base64")}
        manifest.append(safe)
    (out/"roi_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    (out/"README.md").write_text(
        "# Case03-C 9处人工目标复核（离线）\n\n"
        "双击 index.html，在RAW或叠加图中点选黄色/青色异常，拖框31/46/56的未完整识别暗区。\n"
        "一张图可多次标注（如review_024黄与青分别标记），导出CSV和JSON备份；"
        "页面本身不自动写工程文件，不向网络上传任何数据。\n"
        "坐标为原始RAW(x,y)像素，ROI框为半开区间[x0,x1),[y0,y1)。"
        "标注导出后须做全图8连通域/候选ID核验，不能凭颜色猜候选ID。\n"
        "显示用图片从源NPZ生成，不更改任何原始RAW或旧结果。"
        "负候选=当前选中的背景伪影；正候选=当前选中存在人工视觉暗异常，物理来源未证实。\n",
        encoding="utf-8"
    )
    print("OUTPUT_REVIEW_PAGE",out/"index.html",flush=True)
    print("GENERATED_ROIS",len(rois),"ASSET_PNG",len(list((out/"assets").glob("*.png"))),flush=True)


if __name__=="__main__":
    sys.exit(main())
