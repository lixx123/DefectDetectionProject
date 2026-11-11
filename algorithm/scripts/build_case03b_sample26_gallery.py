"""Case03-B样品26：已保存的全分辨率S/H掩膜的局部人工复核图册。

只读Case02 uint16融合响应、原始12bit RAW及Case03-B无损packbits掩膜，
在新目录生成原始RAW/单阈值/双阈值对照。不会在ROI内重新进行滞后连通计算，
因而不会遗漏来自ROI外部的连通高阈值种子。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from config import user_config

matplotlib.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False
ALL_COLORS = {
    "core": np.array([255, 217, 39], dtype=np.float32),        # 黄：S230
    "added170": np.array([0, 222, 239], dtype=np.float32),    # 青：H170新增
    "added150": np.array([239, 45, 155], dtype=np.float32),   # 洋红：H150再新增
}
SOURCE_KEYS = {
    "s230": "fused_S_TL230_TH230.npz",
    "h170": "fused_H_TL170_TH230.npz",
    "h150": "fused_H_TL150_TH230.npz",
}

def bounds_for_roi(x: int, y: int, n: int, shape: tuple[int, int]) -> tuple[int, int, int, int]:
    """原始像素坐标范围；靠边时移动窗口而非截小窗口。"""
    h, w = shape
    if n <= 0 or n > min(h, w):
        raise ValueError("ROI size invalid")
    x0 = max(0, min(w-n, x-n//2))
    y0 = max(0, min(h-n, y-n//2))
    return x0, y0, x0+n, y0+n

def read_packed_bits(path: Path, expected_shape: tuple[int, int]) -> tuple[np.ndarray, str]:
    """只将packbits字节读入RAM；不在内存创建一亿像素bool全图。"""
    with np.load(path, allow_pickle=False) as data:
        packed = np.asarray(data["mask_packed"], dtype=np.uint8)
        shape = tuple(int(v) for v in data["mask_shape"])
        order = str(np.asarray(data["bitorder"]).item())
    if shape != expected_shape or order not in ("little", "big"):
        raise ValueError(f"mask shape/order invalid: {path} {shape} {order}")
    expected_bytes = (shape[0] * shape[1] + 7) // 8
    if packed.size != expected_bytes:
        raise ValueError(f"mask packed size invalid: {path}")
    return packed, order

def packed_roi(packed: np.ndarray, bitorder: str, shape: tuple[int, int],
               bounds: tuple[int,int,int,int]) -> np.ndarray:
    """按原始展平索引直接截取packbits，严格保留full-image hysteresis语义。"""
    x0,y0,x1,y1 = bounds
    h,w = shape
    if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h):
        raise ValueError("ROI bounds invalid")
    rows = np.arange(y0,y1,dtype=np.int64)[:,None]
    cols = np.arange(x0,x1,dtype=np.int64)[None,:]
    linear = rows * w + cols
    byte_values = packed[linear >> 3]
    offset = linear & 7
    shift = offset if bitorder=="little" else 7-offset
    return ((byte_values >> shift) & 1).astype(np.bool_)

def normalize_dn(raw: np.ndarray) -> tuple[np.ndarray, tuple[float,float]]:
    """仅做显示用线性拉伸；不改变原始DN数据。"""
    low, high = np.percentile(raw, [1.0, 99.5])
    high = max(float(high),float(low)+1.0)
    img = np.clip((raw.astype(np.float32)-low)/(high-low),0,1)
    return img,(float(low),float(high))

def make_overlay(base_gray: np.ndarray, s:np.ndarray, h170:np.ndarray, h150:np.ndarray) -> np.ndarray:
    """黄=高阈值核心；青=170新增；洋红=150再新增，互斥染色。"""
    if not (s.shape==h170.shape==h150.shape==base_gray.shape):
        raise ValueError("overlay dimensions mismatch")
    if not (np.all(~s|h170) and np.all(~h170|h150)):
        raise ValueError("H masks must contain S and be nested")
    img = np.repeat((np.clip(base_gray,0,1)*255).astype(np.float32)[...,None],3,axis=2)
    for key, mask in (("core",s),("added170",h170 & ~s),("added150",h150 & ~h170)):
        img[mask] = img[mask]*0.22 + ALL_COLORS[key]*0.78
    return np.clip(np.rint(img),0,255).astype(np.uint8)

def components_in_patch(mask: np.ndarray) -> int:
    """仅用于ROI连通片段统计：ROI边界切断部分全图组件，不是全图候选数。"""
    _, count = ndimage.label(mask, structure=np.ones((3,3),dtype=np.uint8))
    return int(count)

def stats_for_roi(label: str, category: str, x: int, y: int, size: int,
                  bounds: tuple[int,int,int,int], raw:np.ndarray, response:np.ndarray,
                  s:np.ndarray, h170:np.ndarray, h150:np.ndarray) -> dict:
    total = int(s.size)
    n_s,n_170,n_150 = (int(np.count_nonzero(z)) for z in (s,h170,h150))
    if not (n_s<=n_170<=n_150 and np.all(~s|h170) and np.all(~h170|h150)):
        raise AssertionError(f"mask containment failed at {label}")
    return {
        "label":label, "category":category,"candidate_not_truth":True,
        "x":x,"y":y,"patch_size":size,"x0":bounds[0],"y0":bounds[1],"x1":bounds[2],"y1":bounds[3],
        "total_pixels":total,"S230_pixels":n_s,"H170_230_pixels":n_170,"H150_230_pixels":n_150,
        "H170_added_pixels":n_170-n_s,"H150_additional_pixels":n_150-n_170,
        "S230_pct":round(n_s/total*100,5),
        "H170_pct":round(n_170/total*100,5),
        "H150_pct":round(n_150/total*100,5),
        "S230_roi_fragments":components_in_patch(s),
        "H170_roi_fragments":components_in_patch(h170),
        "H150_roi_fragments":components_in_patch(h150),
        "raw_min_dn":int(raw.min()),"raw_max_dn":int(raw.max()),
        "raw_median_dn":float(np.median(raw)),
        "response_max_dn":int(response.max()),
        "response_p99_dn":float(np.percentile(response,99)),
        "response_p99_9_dn":float(np.percentile(response,99.9)),
    }

def image_panel(ax, img:np.ndarray, caption:str, gray:bool=False):
    if gray: ax.imshow(img,cmap="gray",vmin=0,vmax=1,interpolation="nearest")
    else: ax.imshow(img,interpolation="nearest")
    ax.set_title(caption,fontsize=10)
    ax.set_xticks([]);ax.set_yticks([])

def save_comparison(path:Path,row:dict,raw_show:np.ndarray,response:np.ndarray,
                    s:np.ndarray,h170:np.ndarray,h150:np.ndarray,overlay:np.ndarray,
                    raw_range:tuple[float,float]):
    fig, axes=plt.subplots(2,3,figsize=(13.3,9),dpi=145)
    cap=max(1.0,float(np.percentile(response,99.5)))
    bh=np.clip(response.astype(np.float32)/cap,0,1)
    image_panel(axes[0,0],raw_show,f"原始RAW显示 (P1={raw_range[0]:.0f} / P99.5={raw_range[1]:.0f} DN)",True)
    image_panel(axes[0,1],bh,f"融合Black-Hat响应 (显示上限{cap:.1f} DN)",True)
    image_panel(axes[0,2],s.astype(np.float32),f"单阈值 S230 ｜{row['S230_pixels']}像素",True)
    image_panel(axes[1,0],h170.astype(np.float32),
                f"双阈值 H170/230 ｜{row['H170_230_pixels']}像素（+{row['H170_added_pixels']}）",True)
    image_panel(axes[1,1],h150.astype(np.float32),
                f"双阈值 H150/230 ｜{row['H150_230_pixels']}像素（再+{row['H150_additional_pixels']}）",True)
    image_panel(axes[1,2],overlay,"RAW叠加｜黄:S230 青:H170新增 洋红:H150再新增")
    fig.suptitle(
        f"样品26 | {row['label']} | 中心({row['x']},{row['y']}) | {row['patch_size']}px\n"
        "使用Case03-B全图保存掩膜裁剪；不在ROI重新生长；全部候选未人工确认为疵病",
        fontsize=12)
    fig.tight_layout(rect=(0,0,1,0.925))
    fig.savefig(path,bbox_inches="tight")
    plt.close(fig)

def save_contact_sheet(path:Path,items:list[dict],title:str):
    """每行原始RAW/S230/H170/三色叠加，无密集编号。"""
    fig,axes=plt.subplots(len(items),4,figsize=(12.8,max(3.4,2.55*len(items))),
                           dpi=140,squeeze=False)
    for ri,item in enumerate(items):
        for ci,(im,lab) in enumerate(zip((item["raw"],item["s"].astype(np.float32),
                              item["h170"].astype(np.float32),item["overlay"]),
                             ("原始RAW","固定230 DN","双阈值170/230","三色增量叠加"))):
            image_panel(axes[ri,ci],im,
                        (item["row"]["label"]+" | "+lab if ci==0 else lab),
                        gray=(ci<3))
        axes[ri,3].set_xlabel(
            f"单={item['row']['S230_pixels']} / H170={item['row']['H170_230_pixels']}"
            f" / H150={item['row']['H150_230_pixels']}",fontsize=8)
    fig.suptitle(title+"\n黄=S230  青=H170新增  洋红=H150再新增；原始像素裁剪且无真值标签",fontsize=12)
    fig.tight_layout(rect=(0,0,1,0.965))
    fig.savefig(path,bbox_inches="tight")
    plt.close(fig)

def file_manifest(path:Path)->dict:
    st=path.stat()
    return {"path":str(path),"size_bytes":st.st_size,"mtime_ns":st.st_mtime_ns}

def main():
    parser=argparse.ArgumentParser(description="Case03-B sample26 fixed/hysteresis localized review gallery")
    parser.add_argument("--output-run-id",default=None)
    args=parser.parse_args()
    g=user_config
    sample=int(g.CASE03B_GALLERY_SAMPLE_ID)
    frame=int(g.CASE03B_GALLERY_FRAME_ID)
    if sample!=26 or frame!=1: raise ValueError("This review gallery is explicitly scoped to sample26/frame1")
    source=ROOT/g.CASE03B_GALLERY_SOURCE_RUN
    case02=ROOT/g.CASE03B_INPUT_RUN
    stem=f"sample_{sample}_frame_{frame}"
    response_path=case02/"samples"/stem/"responses"/"blackhat_fused.npz"
    mask_dir=source/"masks"/stem
    if not response_path.is_file():raise FileNotFoundError(response_path)
    raw_path=g.DATA_ROOT/"26 (1).raw"
    if not raw_path.is_file():raise FileNotFoundError(raw_path)
    h,w=int(g.RAW_HEIGHT),int(g.RAW_WIDTH)
    shape=(h,w)
    if raw_path.stat().st_size!=h*w*2:raise ValueError("RAW byte size mismatch")
    th=g.CASE03B_GALLERY_THRESHOLDS
    if tuple(int(th[z]) for z in ("single_high_dn","hysteresis_low_1_dn","hysteresis_low_2_dn"))!=(230,170,150):
        raise ValueError("Gallery expects exact existing Case03B masks S230 H170/230 H150/230")
    sources=[raw_path,response_path]+[mask_dir/f for f in SOURCE_KEYS.values()]
    before=[file_manifest(p) for p in sources]
    folder=g.OUTPUT_ROOT/"case03b_gallery"
    folder.mkdir(exist_ok=True)
    run_id=args.output_run_id or datetime.now().strftime("run_%Y%m%d_%H%M%S")
    run=folder/run_id
    suffix=1
    while run.exists():
        run=folder/f"{run_id}_{suffix:02d}"
        suffix+=1
    (run/"figures").mkdir(parents=True)
    (run/"patches").mkdir(parents=True)
    with np.load(response_path,allow_pickle=False) as data:
        response=np.asarray(data["fused_response_dn"])
    if response.dtype!=np.uint16 or response.shape!=shape:
        raise ValueError("Unexpected response type or shape")
    raw=np.memmap(raw_path,dtype=">u2",mode="r",shape=shape)
    packed={name:read_packed_bits(mask_dir/f,shape) for name,f in SOURCE_KEYS.items()}
    rows=[]
    contact=[]
    for i,roi in enumerate(g.CASE03B_GALLERY_ROIS,1):
        label=str(roi["label"])
        x,y,size=(int(roi[k]) for k in ("x","y","size_px"))
        b=bounds_for_roi(x,y,size,shape)
        x0,y0,x1,y1=b
        raw_patch=np.asarray(raw[y0:y1,x0:x1],dtype=np.uint16)
        rsp_patch=np.array(response[y0:y1,x0:x1],copy=True)
        mask={name:packed_roi(bits,order,shape,b) for name,(bits,order) in packed.items()}
        s,h170,h150=(mask[key] for key in ("s230","h170","h150"))
        row=stats_for_roi(label,roi["category"],x,y,size,b,raw_patch,rsp_patch,s,h170,h150)
        display,rng=normalize_dn(raw_patch)
        overlay=make_overlay(display,s,h170,h150)
        npz_path=run/"patches"/f"{i:02d}_{label}_{size}px.npz"
        np.savez_compressed(npz_path,raw_dn=raw_patch,fused_response_dn=rsp_patch,
                            S230=s,H170_230=h170,H150_230=h150,
                            added_H170=np.logical_and(h170,~s),
                            added_H150=np.logical_and(h150,~h170),
                            origin_xy=np.array([x0,y0],dtype=np.int64),
                            candidate_not_truth=np.array(True))
        figpath=run/"figures"/f"{i:02d}_{label}_{size}px_compare.png"
        save_comparison(figpath,row,display,rsp_patch,s,h170,h150,overlay,rng)
        row["compare_figure"]=str(figpath.relative_to(run))
        row["patch_npz"]=str(npz_path.relative_to(run))
        rows.append(row)
        contact.append({"row":row,"raw":display,"s":s,"h170":h170,"overlay":overlay})
        print(f"{i:02d} {label:33s} S={row['S230_pixels']:6d} H170={row['H170_230_pixels']:6d}"
              f" H150={row['H150_230_pixels']:6d} peak={row['response_max_dn']:4d}",flush=True)
    # 按人工观察类别分页，避免高分辨率原图一次铺满屏幕。
    for idx in range(0,len(contact),5):
        part=idx//5+1
        save_contact_sheet(run/"figures"/f"contact_sheet_part{part:02d}.png",
                           contact[idx:idx+5],
                           f"Case03-B样品26 单阈值/双阈值原分辨率对照 第{part}页")
    with (run/"roi_statistics.csv").open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
    after=[file_manifest(p) for p in sources]
    all_ok=bool(before==after)
    snapshot={
        "gallery_version":"1.0",
        "source_run":str(source),"case02_response":str(response_path),
        "sample":sample,"frame":frame,"shape":[h,w],
        "roi_parameters":g.CASE03B_GALLERY_ROIS,
        "thresholds_dn":th,"source_manifest_before":before,"source_manifest_after":after,
        "sources_unchanged":all_ok,
        "all_masks_nested":True,"roi_count":len(rows),
        "comparison_note":"ROI从完整Case03B全图掩膜精确裁剪；不在ROI重新执行H；ROI片段数不是全图候选数量；人工真值尚未核验。",
    }
    (run/"config_snapshot.json").write_text(json.dumps(snapshot,indent=2,ensure_ascii=False),encoding="utf-8")
    report=[
        "# Case03-B样品26：固定阈值与双阈值局部对照图册",
        "",
        f"- 源运行：`{source}`（只读）",
        f"- 响应来源：`{response_path}`；原始12bit大端RAW：`{raw_path}`",
        "- 检测输入单位：uint16 Black-Hat DN，非8bit预览。",
        "- 单阈值S230：R>=230；H170/230：Seed>=230且低阈值支持R>=170；H150/230同理。",
        "- 所有ROI均从**已完成全图连通重建的保存掩膜**截取，不在ROI重新生长，避免ROI外强种子影响被遗漏。",
        "- 六面板：RAW、融合响应、S230、H170/230、H150/230、三色差异叠加。黄=高阈值核心，青=H170新增，洋红=H150再次新增。",
        "- PNG为显示；对应NPZ含原始RAW DN、融合DN和三种无损布尔掩膜，可逐像素复核。",
        "- 所有位置皆为candidate_not_truth，'line_like'仅表示细长响应或可见结构，不能直接当作真实划痕。",
        "- 对照区域边界会切断连通片段，因此ROI碎片数不是原始全图连通域数量。",
        "- 禁止把H增加的像素数直接等同为新增真疵病，也不得把背景区域候选判定为必然噪声。",
        "",
        "## ROI复核统计",
        "",
        "| 位置 | S230 | H170/230 | H150/230 | H170新增 | H150再增 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        report.append(f"| {r['label']} | {r['S230_pixels']} | {r['H170_230_pixels']} | {r['H150_230_pixels']} | {r['H170_added_pixels']} | {r['H150_additional_pixels']} |")
    report+=["","## 阶段验收",
        f"- 图册页数：{(len(rows)+4)//5}；逐ROI六面板图片：{len(rows)}；逐ROI可复核NPZ：{len(rows)}。",
        f"- 全图掩膜包含关系逐ROI检查：PASS。",
        f"- 原始输入及既有运行文件数量、大小、修改时间不变：{'PASS' if all_ok else 'FAIL'}。",
        "- 真实弱点、划痕人工真值、不同阈值的真正漏检情况：PENDING USER。",
        "- 未修改Case03-B算法及检测结果，不执行后续阶段。",
    ]
    (run/"gallery_report.md").write_text("\n".join(report)+"\n",encoding="utf-8")
    (run/"acceptance.md").write_text(
        "# 样品26局部对照图册验收\n\n"
        f"- 生成文件：{len(rows)}个ROI图 + {(len(rows)+4)//5}张联系图 + {len(rows)}个无损局部NPZ\n"
        "- 三掩膜逻辑包含：PASS\n"
        f"- 只读输入保护：{'PASS' if all_ok else 'FAIL'}\n"
        "- 检出性能人工验收：PENDING USER\n"
        "- Case04/Case05：未执行\n",encoding="utf-8")
    print("OUTPUT_GALLERY",run,flush=True)
    print("INTEGRITY",all_ok,flush=True)
    return 0 if all_ok else 1

if __name__=="__main__":
    raise SystemExit(main())
