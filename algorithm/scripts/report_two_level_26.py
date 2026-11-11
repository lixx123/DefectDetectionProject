"""Build a delivery index only from completed fresh runs and independent QA."""
from pathlib import Path
import sys,json,shutil,xml.etree.ElementTree as ET
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from config import user_config as C
from scripts.run_unified_final_revision import write_json,sha


def run():
    root=C.OUTPUT_ROOT/'K8A_TWO_LEVEL_20261020_v1'
    rows=json.loads((root/'completed_benchmarks.json').read_text(encoding='utf8'))
    assert len(rows)==6
    records=[];qas=[]
    for r in rows:
        out=Path(r['output']);q=json.loads((out/'independent_QA/QA.json').read_text(encoding='utf8'))
        assert q['status']=='PASS';qas.append(q)
        full=next(x for x in rows if x['frame']==r['frame'] and x['mode']=='full')
        visits=r['blackhat_input_pixels_with_repeats']+r['J4_RAW_window_pixels_with_repeats']
        basevis=full['blackhat_input_pixels_with_repeats']+full['J4_RAW_window_pixels_with_repeats']
        records.append({'frame':r['frame'],'mode':r['mode'],'actual_tiles':r['actual_fresh_J4_tiles'],
            'skipped_tiles':r['skipped_tiles'],'tile_reduction_pct':100*r['skipped_tiles']/r['full_tiles'],
            'BH_input_pixels_with_repeats':r['blackhat_input_pixels_with_repeats'],
            'BH_output_pixels':r['blackhat_output_pixels'],'J4_RAW_pixels_with_repeats':r['J4_RAW_window_pixels_with_repeats'],
            'high_cost_RAW_visits':visits,'high_cost_RAW_visit_reduction_pct':100*(1-visits/basevis),
            'BH_seconds':r['blackhat_seconds'],'J4_seconds':r['J4_seconds'],'J5_seconds':r['J5_seconds'],
            'total_seconds':r['elapsed_seconds'],'runtime_reduction_pct':100*(1-r['elapsed_seconds']/full['elapsed_seconds']),
            'peak_working_set_MiB':r['peak_working_set_bytes']/2**20 if r['peak_working_set_bytes'] else None,
            'fresh_source_rows':r['source_count'],'final_objects':r['objects'],'final_area_px2':r['area'],'output':str(out)})
    pd.DataFrame(records).to_csv(root/'PERFORMANCE_SIX_FRESH_RUNS.csv',index=False,encoding='utf-8-sig')
    delivery=root/'FINAL_RESULTS';delivery.mkdir(exist_ok=False)
    archive=[]
    for frame in (1,2):
        out=Path(next(r['output'] for r in rows if r['frame']==frame and r['mode']=='roi-bh'))
        target=delivery/f'26_{frame}';target.mkdir()
        for file in ('00_FINAL_DEFECTS_ONLY_fullframe_1to4.png','FINAL_DEFECTS_AND_MEASUREMENTS.csv',
                     'ALL_HISTORICAL_SOURCE_DISPOSITIONS_NO_DROP.csv','acceptance.json'):
            shutil.copy2(out/file,target/file)
        for file in ('BEFORE_AFTER_FINAL_RECTANGLES.png','ALL_FINAL_OBJECT_MEASUREMENT_DIFF.csv','QA.json'):
            shutil.copy2(out/'independent_QA'/file,target/file)
        archive.append({'frame':frame,'complete_run':str(out),'final_image':str(target/'00_FINAL_DEFECTS_ONLY_fullframe_1to4.png'),
                        'SHA256':sha(target/'00_FINAL_DEFECTS_ONLY_fullframe_1to4.png')})
    write_json(root/'DELIVERY_INDEX.json',archive)
    tests=ET.parse(root/'pytest_final.xml').getroot()
    suites=list(tests.iter('testsuite'));n=sum(int(s.attrib['tests']) for s in suites)
    assert all(int(s.attrib.get('failures',0))==0 and int(s.attrib.get('errors',0))==0 for s in suites)
    lines=['# K8A两级检测架构：26双帧验收报告','',
        '## 核心结论','',
        '实测只减少高成本计算，没有改变这两帧工作区内的检测结果。六次新流程实际重算并通过独立QA；不得外推成其他样品零漏检保证。',
        '采用方案B（--roi-mode roi-bh）；方案A（roi-j4）与全幅对照（full）保留。默认旧命令仍兼容；只有显式选择roi-mode才启用新调度。','',
        '## 修改前证据','',
        '详见CODE_REVIEW_BEFORE_IMPLEMENTATION.md和source_baseline_SHA256.json。旧330项测试通过；新增ROI测试在实现前因接口缺失失败，随后通过。',
        '原问题是BH先全幅计算、J4/J5强制全幅网格、顺序J5编号不能跨调度比较；不是阈值过严或显示问题。未调低170/230、未修改筛噪、关联门限或RAW恢复规则。','',
        '## 新执行链路','',
        'RAW QC → RAW K8A → 可信性检查 → 安全ROI/全幅回退 → BH真实上下文 → 原J4完整窗口 → J5 → 原K8补充/RAW恢复/精确并集 → mask测量 → 矩形标注 → 独立QA。','',
        'ROI为WORK+EDGE外包几何，加12px review、93px算法安全范围，再保守外包到原256网格完整core作为合法source区。部分相交tile不裁WORK、不零填充。保留原J4 64px处理窗口，不改变窗口统计/连通操作。',
        '93px = max(BH闭运算30, Gaussian22的88+median1+后平滑4=93, Closing61两步60+1+4=65, F12, G8, H DoG32, J1/J2 53, J4 64, K8D128半窗64, Unified背景72)。BH在所有消费窗口之外另读32px RAW。参数在config/user_config.py:TWO_LEVEL_ROI。',
        '93不是对全局连通域的数学有界性证明；等价性依靠保留原完整局部计算窗口，加全对象成员集与源像素回归验证。','',
        '## 真实性能（串行独立进程，未用旧缓存冒充）','',
        '|帧|模式|实际tile|BH秒|J4秒|总秒|峰值工作集MiB|最终对象|',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    for r in records:
        lines.append(f"|26_{r['frame']}|{r['mode']}|{r['actual_tiles']}|{r['BH_seconds']:.2f}|{r['J4_seconds']:.2f}|{r['total_seconds']:.2f}|{r['peak_working_set_MiB']:.1f}|{r['final_objects']}|")
    lines+=['','完整处理像素/内存/候选/减幅见PERFORMANCE_SIX_FRESH_RUNS.csv。像素访问量含重叠，BH多核执行另存kernel_pixel_evaluations；不把它称作唯一RAW像素。RAW QC仍读取全帧、渲染仍使用整图，峰值内存不保证同步下降。每模式单次测量，缓存/系统负载有影响，不作统计显著性承诺。','',
        '## 逐像素与逐对象验收','',
        '每组independent_QA目录包含所有执行tile、旧J5完整成员/面积/Feret/bbox对照、全部最终对象差异表。BH完整消费窗口差异0、J4源与桥接/标签差异0，WORK/EDGE J5成员集和尺寸不变，最终全分辨率二值差异0。',
        '两帧最终36/35对象；四处批准mask逐像素保持297/398/348/370px²；F1_FINAL_0029保持3469px²，Feret189.97368px。负例与最终mask交集0。矩形1显示像素、ID/A/L，标签碰撞0，无外轮廓或mask填充。面积来自真实mask像素，长度来自像素中心最大Feret，不是显示框大小。',
        'W005位于NONWORK，不会被ROI生产扫描。W005_NONWORK_DIAGNOSTIC真实重算12个原网格tile及J5，明确复用本轮新全幅BH；成员集、7689px²面积、Feret和bbox全部不变。这是独立回归，不是向生产ROI偷加人工坐标，也不是宣称ROI覆盖全帧。',
        '40702条历史来源原始CSV字节SHA256不变，完整审计保留。每条明确FRESH_REPRODUCED或HISTORICAL_PRESERVED_NOT_RESCANNED_OR_ROI_BOUNDARY_CHANGED；历史未扫描不能称本轮新检出或阴性。当前新J5顺序ID另存，按精确J4成员集合建立历史别名，不改新J5数据。','',
        '## 失败保护与限制','',
        '无band、异常数量、边界拟合/几何不可信、空/异常面积或定位异常自动FULL_FRAME_FALLBACK，实际跑全幅BH/J4/J5。无法可信分带时不编造K8B结果，保留J5全候选、已知人工审核，状态要求人工几何复核；不能输出“生产验收通过”。合成无band真实全流程测试覆盖此分支。',
        '仅26双帧回归。没有独立全图真值，不能声称召回率/精确率或物理轮廓完全准确；像面像素面积非物面标定。基于K8A的可信性门控不能保证发现所有错误定位；外部新样本仍需要对照和人工复核。',
        '原上一批20张实际18成功，30-1_000/30-4_000的J2断连失败保留，本任务未处理或推广另外18张。','',
        '## 测试与实际命令','',f'完整pytest：{n}项，失败0，错误0。原始结果pytest_final.log / pytest_final.xml。',
        '```powershell']
    for r in rows:
        lines.append(f'.\\.venv\\Scripts\\python.exe main.py --case unified-final --input "{C.DATA_ROOT}/26 ({r["frame"]}).raw" --roi-mode {r["mode"]} --run-id {Path(r["output"]).name}')
    lines+=['```','','QA命令：python scripts/verify_two_level_unified.py --output NEW_RUN --frame 1（或2）；禁止覆盖已有QA目录。',
        '统一交付图：FINAL_RESULTS/26_1和26_2；完整运行目录、图片SHA256见DELIVERY_INDEX.json。所有历史结果、RAW、用户标注保持原位。','',
        '## 修改文件','',
        '- main.py：显式roi-mode入口，旧命令兼容。',
        '- config/user_config.py：集中调度、安全范围和可信性参数。',
        '- src/detection/two_level_roi.py：可信性、合法core计划、真实halo BH。',
        '- scripts/run_case03j4_fullscan.py：原网格选择与完整性校验、空结果合法表头。',
        '- scripts/run_case03j5_global_merge.py：稀疏合法计划校验、空结果与准确覆盖状态。',
        '- scripts/run_unified_raw_input.py：空J5/空输出处理，不改非空检测语义。',
        '- scripts/run_two_level_unified.py：新调度管线、历史别名与全来源审计、计时和内存。',
        '- scripts/verify_two_level_unified.py、verify_two_level_W005.py：独立像素与W005回归。',
        '- scripts/benchmark_two_level_26.py、report_two_level_26.py：串行真实对照与交付汇总。',
        '- tests/test_two_level_roi.py、tests/test_two_level_real_regression.py：新单测/合成fallback/真实结果门禁。','',
        '完成本轮后停止，等待人工验收；不自动推广其余18帧。']
    (root/'K8A_TWO_LEVEL_ACCEPTANCE_REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    write_json(root/'FINAL_ACCEPTANCE.json',{'status':'ENGINEERING_QA_PASS_PENDING_HUMAN_ACCEPTANCE','fresh_runs':6,
        'pytest_tests':n,'historical_sources_preserved':40702,'only_frames':[1,2],'selected_mode':'roi-bh','qas':qas})
    print(root/'K8A_TWO_LEVEL_ACCEPTANCE_REPORT.md')


if __name__=='__main__':run()
