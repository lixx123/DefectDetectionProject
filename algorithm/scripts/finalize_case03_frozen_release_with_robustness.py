"""Finalize frozen v2 release with independent all20 QA, unaltered PNGs and transparent scope."""
from pathlib import Path
import json,sys,shutil,hashlib
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from config import user_config as C
RELEASE=C.OUTPUT_ROOT/"CASE03_FROZEN_RELEASE_20261019_v2"
INITIAL=C.OUTPUT_ROOT/"CASE03_FROZEN_RELEASE_20261019"
ROBUST=C.OUTPUT_ROOT/"CASE03_FROZEN_ROBUSTNESS_20RAW_20261019_v3"
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for chunk in iter(lambda:f.read(8*1024*1024),b""):h.update(chunk)
 return h.hexdigest()
def main():
 m=json.loads((RELEASE/"FROZEN_PIPELINE_AND_FILES_SHA256.json").read_text(encoding="utf-8"))
 assert m["version"]=="CASE03_FROZEN_20261019_v2"
 assert len(m["registered_stages"])==26
 assert all(all(f["exists"] for f in step["source_files"]) for step in m["registered_stages"]), (
   "A frozen pipeline stage is missing code")
 assert len(m["immutable_exports"])==55
 assert all((RELEASE/x["release_path"]).exists() for x in m["immutable_exports"])
 a=json.loads((ROBUST/"independent_QA.json").read_text(encoding="utf-8"))
 assert a["pass_count"]==20 and a["fail_count"]==0
 assert a["bands_count_all_frames"]=={"4":20}
 src=INITIAL/"README_先看26两帧及完整固化流程.md"
 shutil.copy2(src,RELEASE/src.name)
 assert sha(src)==sha(RELEASE/src.name)
 arr=[]
 dest=RELEASE/"ROBUSTNESS_20RAW_K8A_B_C";dest.mkdir()
 names=[
 "20_RAW_RAW_WORKBAND_CONTACT_SHEET_5samples_x_4frames.png",
 "20_RAW_ALL_B_CONTACT_SHEET_5samples_x_4frames.png",
 "20_RAW_K8C_PROMISING_PENDING_CONTACT_SHEET_5samples_x_4frames.png",
 "20_RAW_K8C_MICRO_SUGGEST_HIDE_CONTACT_SHEET_5samples_x_4frames.png",
 "INDEPENDENT_20_FRAME_PIXEL_SOURCE_AUDIT.csv",
 "ROBUSTNESS_COUNT_OUTLIER_REVIEW_ONLY.csv",
 "ALL_20_INPUTS_STAGE_STATUS.csv",
 "summary.json","independent_QA.json"]
 for name in names:
  p=ROBUST/name
  assert p.is_file(),p
  z=dest/name
  if z.exists():raise FileExistsError(z)
  shutil.copy2(p,z)
  assert sha(p)==sha(z)
  arr.append({"destination":str(z.relative_to(RELEASE)), "SHA256":sha(z),
              "source":str(p),"bytes":p.stat().st_size})
 pd.DataFrame(arr).to_csv(dest/"COPY_SHA256_MANIFEST.csv",
                          encoding="utf-8-sig",index=False)
 df=pd.read_csv(ROBUST/"INDEPENDENT_20_FRAME_PIXEL_SOURCE_AUDIT.csv")
 matrix=df.pivot(index="sample_id",columns="frame_id",
                 values="B_candidate_source_objects")
 print("COUNT_MATRIX")
 print(matrix.to_string())
 half=df.groupby("sample_id").agg(
     frames=("frame_id","count"),B_sources=("B_candidate_source_objects","sum"),
     B_median=("B_candidate_source_objects","median"),
     micro_suggest_hide_not_deleted=("micro_suggest_hide_without_deletion","sum"),
     strong_raw_pending=("strong_dark_pending_candidates","sum"))
 half.to_csv(dest/"SAMPLE_LEVEL_5_PIECE_CANDIDATE_SUMMARY.csv",encoding="utf-8-sig")
 md=[
 "# Case03现有算法冻结基线——20张RAW鲁棒性实际测试",
 "",
 "**实际执行时间：2026-10-19。冻结版本v2，不修改原RAW、J5/K8A-I历史检测结果。**",
 "",
 "## 必须先区分两类结果",
 "",
 "- **26_1和26_2：** 原J4/J5完整整图检测、K8A/B/C候选和所选K8D/E轮廓、人工确认局部对象的全部现有历史结果打包至冻结发布目录。检查主图、全部复核层以及人工批准记录，不能只打开绿色稳定层。",
 "- **26～30号全部20张RAW：** 真正从每帧原RAW运行了K8A动态工作带、五尺度椭圆核BlackHat融合、固定A与分波段鲁棒B双阈值、K8C局部RAW/MAD/DoG噪声分级；每张都有独立B源像素和审核记录。**18张新帧尚未完成J4/J5受限Gaussian/Closing、G/H全图多窗融合和K8D/E全量候选轮廓修复/去重。此阶段绝不冒称整套流水线对20帧完全验收。**",
 "",
 "## 本轮独立实测数字",
 "",
 "| 指标 | 结果 |",
 "|---|---:|",
 f"| RAW 输入及文件大小校验 | {a['inputs_total']}张，全部11276×9200×2字节 |",
 f"| K8A/B/C流程PASS/FAIL | {a['pass_count']} / {a['fail_count']} |",
 f"| K8A逐帧自动工作带 | 20帧各4条 |",
 f"| B实验分支所有原始连通候选 | **{a['B_source_objects_all20_total']:,}** |",
 f"| B原始候选的最低/中位/最高 | **{a['B_source_objects_min']:,} / {a['B_source_objects_median']:,.1f} / {a['B_source_objects_max']:,}** |",
 f"| B源数量跨帧最大/最小比 | **{a['B_source_objects_max_min_ratio']:.2f}倍** |",
 f"| K8C仅建议隐藏的微候选，实际未删 | **{a['K8C_micro_suggest_hide_source_total_not_deleted']:,}** |",
 f"| K8C RAW暗度证据较强、尚待复核 | **{a['K8C_strong_raw_support_pending_total']:,}** |",
 "",
 "**以上均为检测源连通候选数，而非真实疵病数，也不能据此报告精确率/召回率。**",
 "",
 "## 每片4帧源B候选数（按样片/帧）",
 "",
 "| 样片 | 帧1 | 帧2 | 帧3 | 帧4 |",
 "|---|---:|---:|---:|---:|"]
 for idx,row in matrix.iterrows():
  md.append(f"| {int(idx)} | "+
         " | ".join(f"{int(row[k]):,}" for k in (1,2,3,4))+" |")
 md.extend([
 "",
 "## 鲁棒性结论（不隐藏的异常与局限）",
 "",
 "1. **输入形态与K8A定位：** 20帧都成功自动提取4条工作带，WORK和SHIELD全图掩膜逐帧生成；这个数据批次未出现5条带或不同结构滤光片，尚不能证明对其它结构普适。",
 "2. **重演26号基准：** 26_1、26_2工作带/原B掩膜按像素严格重合，K8C源分类数量与历史记录完全一致；原先在新通用脚本发现的整体/局部抽样相位问题已保留失败试验输出，正式v3按**全图一致8px网格**修复，不改阈值。",
 "3. **候选密度变化：** 后期29、30号样片每帧B微候选远多于26、27；这可能来自RAW背景细纹理、亮度/噪声和实际表面情况，需要再看原RAW/真实人工标签，而非擅自修改噪声门控。基于整个20帧分布的MAD数值未超过设置的2.0异常标记线，不代表无鲁棒性风险。",
 "4. **保留与去向：** 全部自适应B候选独立保存二值源mask、K8C类别和唯一UID，微点仅标Suggest-Hide而从未在原图掩膜删除；A固定分支独立保存，A/B不交集的像素显式计入各带统计，不假设B覆盖A。",
 "5. **未完成项明确隔离：** 第三方新RAW真值缺失；J4/J5/G/H/跨窗scratch恢复及K8D/K8E只在26前两帧有完整或抽样历史记录。其余18帧缺少这几步的自动端到端执行，后续必须逐帧跑并对比J5源面积守恒、跨波段边缘假检、同一疵病重复计量、阈值稳定性。",
 "6. **用户确认必须保持：** 第一帧B02与B04各一处完整暗斑、第二帧G006/G009两处保持已审核；绿色稳定框人工反馈非疵病但尚未自动逐源编号映射，须留待复核，不可静默改变候选数。",
 "",
 "## 打开文件",
 "",
 "- 首先进入冻结主目录的`26_1`、`26_2`文件夹查看中大主图、全部小点/待复核层及用户已确认结果。",
 "- 进入此报告所在`ROBUSTNESS_20RAW_K8A_B_C`文件夹，依次打开`20_RAW_RAW_WORKBAND_CONTACT_SHEET_5samples_x_4frames.png`、`20_RAW_ALL_B_CONTACT_SHEET_5samples_x_4frames.png`、`20_RAW_K8C_PROMISING_PENDING_CONTACT_SHEET_5samples_x_4frames.png`、`20_RAW_K8C_MICRO_SUGGEST_HIDE_CONTACT_SHEET_5samples_x_4frames.png`。",
 "- 20帧完整的逐源CSV和原分波段RAW掩膜位于`outputs/CASE03_FROZEN_ROBUSTNESS_20RAW_20261019_v3/{sample}_{frame}`，按需进一步检查1:8预览是否漏掉暗斑，不把低分辨率显示图当原面积。",
 "- `README_先看26两帧及完整固化流程.md`与`COMPLETE_PIPELINE_STAGE_REGISTRY.csv`记录所有26个方法阶段及是否已全部执行；`FROZEN_PIPELINE_AND_FILES_SHA256.json`记录源码及导出文件原样哈希，不允许静默忽略步骤。",
 "",
 "## 正式全流程鲁棒性下一阶段",
 "",
 "在运行新的各帧J4/J5 + G/H + K8D/E之前，**完整20帧生产级鲁棒性仍判PENDING**。不可将前段PASS当作真正检出率结论。"
 ])
 report=dest/"ALL20_ROBUSTNESS_FINAL_REPORT.md"
 if report.exists():raise FileExistsError(report)
 report.write_text("\n".join(md)+"\n",encoding="utf-8")
 print("FROZEN_RELEASE_V2_FINISHED",RELEASE,"QA_COUNT",a["B_source_objects_all20_total"],
       "ROBUSTNESS_COPIED",len(arr),"FILES",flush=True)
if __name__=="__main__":main()
