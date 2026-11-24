"""Twenty RAW K8D/E review contact sheet. All RAWs, no truth claim."""
from pathlib import Path
import sys,json,cv2,numpy as np,pandas as pd
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from config import user_config as C
from scripts.run_case03_frozen_K8DE_priority_all20 import OUT as DE
from scripts.run_case03frozen_all20_robustness import inputs
VAL=C.OUTPUT_ROOT/"CASE03_FROZEN_20RAW_VALIDATION_20261019_v1"
HIST=C.OUTPUT_ROOT/"case03k8i_stage2_RAW_review_and_association/run_20261017_twoframes_priority_evidence_v1"
FONT="C:/Windows/Fonts/msyh.ttc"
def read(p):
 im=cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
 if im is None:raise IOError(p)
 return im
def main():
 qa=json.loads((DE/"independent_QA.json").read_text(encoding="utf-8"))
 assert qa["raw_inputs_pass"]==20
 s=json.loads((VAL/"summary.json").read_text(encoding="utf-8"))
 assert s["K8DE_priority_20_frames_pass"] and len(s["frame_statuses"])==20
 W,H=680,550
 sheet=Image.new("RGB",(W*4,H*5),(23,25,27))
 draw=ImageDraw.Draw(sheet)
 title=ImageFont.truetype(FONT,16)
 sub=ImageFont.truetype(FONT,12)
 rows=[]
 for i,info in enumerate(inputs()):
  uid=info["uid"]
  k=json.loads((DE/uid/"status.json").read_text(encoding="utf-8"))
  assert k["status"]=="PASS"
  p=(HIST/f"frame26_{info['frame_id']}"/
      "02_NEW_RAW_GROUPS_ALL_review_1to4.png") if uid in ("26_1","26_2") else (
      DE/uid/"K8DE_ALL_PRIORITY_REVIEW_1to8.png")
  view=read(p)
  scale=min((W-20)/view.shape[1],(H-90)/view.shape[0])
  w=int(view.shape[1]*scale);h=int(view.shape[0]*scale)
  pic=Image.fromarray(cv2.cvtColor(
      cv2.resize(view,(w,h),interpolation=cv2.INTER_AREA),
      cv2.COLOR_BGR2RGB))
  x=(i%4)*W;y=(i//4)*H
  sheet.paste(pic,(x+(W-w)//2,y+77))
  draw.text((x+8,y+8),f"{uid}: B={k['B_all_source_count']:,}",
            font=title,fill=(241,241,241))
  draw.text((x+8,y+38),
            f"RAW trials={k['new_raw_trials']}  OR review={k['review_group_count']}",
            font=sub,fill=(221,224,228))
  js=next(z for z in s["frame_statuses"] if z["uid"]==uid)
  rows.append({"uid":uid,
   "B_candidate_source_records":k["B_all_source_count"],
   "K8D_priority_RAW_trials":k["new_raw_trials"],
   "K8E_exact_OR_review_groups":k["review_group_count"],
   "J4_whole_frame":js["J4_status"],
   "J5_cross_tile":js["J5_status"],
   "K8D_micro_trial_scope":"NOT_ALL_MICRO",
   "J5_B_crosschannel_dedup":"NOT_DONE",
   "groundtruth":"NOT_AVAILABLE"})
 name="20_RAW_K8DE_PRIORITY_CONTOURS_5_SAMPLES_X_4_FRAMES.png"
 output=VAL/name
 if output.exists():raise FileExistsError(output)
 sheet.save(output,optimize=True)
 pd.DataFrame(rows).to_csv(VAL/"TWENTY_RAW_K8DE_J4J5_COMPARISON.csv",
                          encoding="utf-8-sig",index=False)
 report=[
 "# Case03完整流水线固化与20张RAW算法阶段验证",
 "",
 "20张RAW的K8A/B/C分支实测通过，K8D多级RAW外围与K8E精确掩膜并集高优先级复核流程也在20张RAW上实测通过。",
 "",
 f"总原始B候选来源：{qa['all_original_B_source_labels_audited']:,}；K8D RAW试验：{qa['all_trial_counts']:,}；K8E外围关联复核组：{qa['new_pixel_groups_sum']:,}。这些不等于已确认真实疵病。",
 "",
 f"目前完成J4/J5跨块拼接的帧数：{s['J4_J5_full_frame_pass']}/20，仍未完成{s['J4_J5_frames_not_yet_complete']}帧。J4完整算法包括固定H、E2受限Gaussian/Closing、F/G/H噪声门控、DoG划痕保护及J1/J2方向性分段关联；K8A/B/C或者单独的K8D/E不能替代。",
 "",
 "保留四处历史人工确认：第一帧Band02 398px²和Band04 297px²各一处；第二帧G006 348px²和G009 370px²各一处。其余新RAW组全部仍待审核；用户提出的8个绿色误检框尚待准确源UID映射，未自动删除。",
 "",
 "20张K8D/E RAW复核位置总览图："+name,
 "每帧逐来源B和实验掩膜位于CASE03_FROZEN_K8DE_PRIORITY_ALL20_20261019_v1文件夹。",
 "全部26个流程阶段×20帧的实际执行记录：CURRENT_26_ALGORITHM_STAGES_X_20_RAW_SCOPE_LEDGER.csv（本目录）。",
 "当前J4/J5进度：ALL20_MAIN_PIPELINE_EXECUTION_STATUS.csv（本目录），该表为执行中的快照，最终以对应帧run_status.json与summary.json为准。",
 "20帧前段工作区及候选总览在CASE03_FROZEN_RELEASE_20261019_v2/ROBUSTNESS_20RAW_K8A_B_C下。",
 "",
 "未完成：J4/J5其它帧、J5与K8B物理疵病级精确去重、统一真值复核、倍率标定及误检漏检量化。不得将已运行的候选试验当作完整的生产鲁棒性验收。"
 ]
 (VAL/"CURRENT_IMPLEMENTATION_AND_ROBUSTNESS_REPORT.md").write_text(
    "\n".join(report)+"\n",encoding="utf-8")
 print("K8DE_20_RAW_CONTACT_SHEET_PASS",output.stat().st_size,
       "bytes","rows",len(rows),flush=True)
if __name__=="__main__":main()
