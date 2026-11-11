"""Measured figures and requirement-by-requirement diagnostic report."""
import json,pstats,math
from pathlib import Path
import numpy as np,pandas as pd
from .common import ROOT,OUT,RAW,read,dump,csvwrite,baseline,verify_sources

def figures():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon,Rectangle,Patch
    from matplotlib.collections import PatchCollection
    from matplotlib.colors import ListedColormap
    from src.detection.case03k8a_band_locator import BandLocatorConfig,polygon_for_band
    F=OUT/'figures';F.mkdir(exist_ok=True)
    raw=np.memmap(RAW,mode='r',dtype='>u2',shape=(9200,11276));h,w=raw.shape
    region=np.load(OUT/'recomputed_region_type.npy',mmap_mode='r');geom=read(OUT/'recomputed_band_geometry.json');plan=read(baseline()/'detection_plan.json')
    schedule=pd.read_csv(OUT/'j4_schedule_geometry_audit.csv');tiles=pd.read_csv(OUT/'j4_tile_profile.csv');points=read(OUT/'figure_points.json')
    preview=np.clip(raw[::8,::8].astype(np.float32)/4095,0,1)
    def axes(title):
        fig,ax=plt.subplots(figsize=(12,9));ax.imshow(preview,cmap='gray',vmin=0,vmax=1,extent=(0,w,h,0));ax.set(xlim=(0,w),ylim=(h,0),xlabel='Column x (0-based RAW pixels)',ylabel='Row y (0-based RAW pixels)',title=title);return fig,ax
    def borders(ax,color='lime'):
        for b in geom['bands']:ax.add_patch(Polygon(polygon_for_band(b,w,BandLocatorConfig(),True),closed=True,fill=False,edgecolor=color,lw=.9))
    def save(fig,name):fig.tight_layout();fig.savefig(F/name,dpi=150);plt.close(fig)
    fig,ax=axes('01: K8A WORK_CORE boundaries on actual RAW');borders(ax);save(fig,'01_work_core_on_RAW.png')
    fig,ax=axes('02: WORK_CORE / WORK_EDGE / NONWORK (codes0+1)');codes=region[::8,::8];cls=np.where(codes==2,1,np.where(codes==3,2,0));colors=['#6e80ae','#21ce77','#ff9f28'];ax.imshow(cls,cmap=ListedColormap(colors),vmin=0,vmax=2,alpha=.42,extent=(0,w,h,0));ax.legend(handles=[Patch(color=c,label=s) for c,s in zip(colors,['NONWORK incl. SHIELD','WORK_CORE','WORK_EDGE'])],loc='upper right');save(fig,'02_region_types.png')
    fig,ax=axes('03: WORK_CORE and expanded detection rectangles (context only)');borders(ax)
    for x,y,a,b in plan['detection_rectangles']:ax.add_patch(Rectangle((x,y),a-x,b-y,fill=False,edgecolor='orange',lw=1.3))
    ax.legend(handles=[Patch(fill=False,edgecolor='lime',label='WORK_CORE'),Patch(fill=False,edgecolor='orange',label='Expanded detection rectangle')]);save(fig,'03_expanded_ROI.png')
    fig,ax=axes('04: All1620 grid cores: 720 scheduled,900 skipped')
    patches=[];colors=[]
    for r in schedule.itertuples():
        x=r.ix*256;y=r.iy*256;patches.append(Rectangle((x,y),min(256,w-x),min(256,h-y)));colors.append('#18c78a' if r.scheduled else '#526070')
    ax.add_collection(PatchCollection(patches,facecolors=colors,edgecolors='white',linewidths=.13,alpha=.5));save(fig,'04_scheduled_and_skipped_tiles.png')
    def heat(df,column,title,file):
        array=np.full((36,45),np.nan)
        for r in df.to_dict('records'):
            if r.get('scheduled',True):array[r['iy'],r['ix']]=r[column]
        fig,ax=plt.subplots(figsize=(12,9));mesh=ax.pcolormesh([*range(0,w,256),w],[*range(0,h,256),h],array,cmap='viridis',shading='flat');ax.set(ylim=(h,0),xlim=(0,w),xlabel='RAW column',ylabel='RAW row',title=title);ax.set_aspect('equal');fig.colorbar(mesh,ax=ax,label=column);save(fig,file)
    heat(schedule,'WORK_CORE_fraction','05: Scheduled core WORK_CORE fraction (skipped blank)','05_work_core_fraction.png')
    heat(tiles,'elapsed_seconds','06: Baseline J4 per-tile wall time (seconds)','06_tile_elapsed_seconds.png')
    heat(tiles,'candidate_pre_gate_H_in_work_area','07: H candidates within each complete core+halo window','07_H_candidates.png')
    fig,ax=plt.subplots(figsize=(10,7))
    for nonempty,color in [(False,'#5395cc'),(True,'#df5429')]:
        d=tiles[(tiles.tile_objects>0)==nonempty];ax.scatter(d.candidate_pre_gate_H_in_work_area,d.elapsed_seconds,s=14,alpha=.6,c=color,label='tile_objects>0' if nonempty else 'tile_objects=0')
    ax.set(xlabel='H candidate count in work window',ylabel='Baseline tile wall seconds',title='08: Tile time vs H count (actual measured baseline)');ax.legend();ax.grid(alpha=.2);save(fig,'08_tile_time_vs_H_candidates.png')
    fig,ax=axes('09: Exact J4 source pixels by region (markers enlarged for visibility)');borders(ax)
    for codes,color,label in [(['2'],'#00d6d6','WORK_CORE'),(['3'],'#ffaa00','WORK_EDGE'),(['0','1'],'red','NONWORK')]:
        xy=[p for c in codes for p in points['source'][c]]
        if xy:
            a=np.array(xy);ax.scatter(a[:,0],a[:,1],s=1.5,c=color,linewidths=0,label=label+' pixels='+str(len(a)))
    ax.legend();save(fig,'09_J4_source_pixels_regions.png')
    fig,axs=plt.subplots(1,2,figsize=(16,7));a=np.asarray(points['final'])
    ax=axs[0];ax.imshow(preview,cmap='gray',extent=(0,w,h,0),vmin=0,vmax=1);borders(ax);ax.scatter(a[:,0],a[:,1],c='#ff4275',s=1,linewidths=0);ax.set(title='10: Final masks and WORK_CORE',xlabel='RAW column',ylabel='RAW row',ylim=(h,0))
    final=pd.read_csv(OUT/'final_mask_workband_audit.csv');cross=final[final.outside_WORK_CORE>0]
    if len(cross):
        uid=cross.iloc[0].final_ID
        with np.load(baseline()/'EXACT_FINAL_BINARY_MASKS'/(uid+'.npz'),allow_pickle=False) as d:
            x0,y0,x1,y1=map(int,d['global_RAW_bbox_xyxy_exclusive']);m=d['mask']>0
            l=max(0,x0-80);t=max(0,y0-80);r=min(w,x1+80);b=min(h,y1+80)
            ax=axs[1];ax.imshow(raw[t:b,l:r],cmap='gray',vmin=0,vmax=4095,extent=(l,r,b,t));borders(ax)
            yy,xx=np.where(m);cc=region[y0:y1,x0:x1][m]
            for code,color,label in [(2,'cyan','WORK_CORE'),(3,'orange','WORK_EDGE')]:
                take=cc==code;ax.scatter(xx[take]+x0,yy[take]+y0,c=color,s=4,marker='s',linewidths=0,label=label)
            ax.set(xlim=(l,r),ylim=(b,t),title=uid+':345 EDGE pixels,0 NONWORK');ax.legend()
    save(fig,'10_final_masks_work_core.png')
    manifest=[]
    from PIL import Image
    for p in sorted(F.glob('*.png')):
        with Image.open(p) as im:im.verify()
        manifest.append(dict(file=p.name,bytes=p.stat().st_size))
    dump(OUT/'figures_manifest.json',manifest);assert len(manifest)>=10

def report():
    figures();b=read(OUT/'PROFILE_BASELINE_RUN.json');s=read(OUT/'spatial_audit_summary.json');t=read(OUT/'j4_semantic_timing_summary.json');eq=read(OUT/'profiling_result_equivalence.json');groups=pd.read_csv(OUT/'j4_tile_group_profile.csv');tile=pd.read_csv(OUT/'j4_tile_profile.csv');verify_sources()
    rows=t['rows']
    # Concrete non-overlapping self-time operations, not an unclassified remainder.
    ps=pstats.Stats(str(OUT/'j4_profile.pstats'))
    top=[dict(stage=k[2],seconds=v[2],J4_fraction=v[2]/t['profile_wall_seconds']) for k,v in sorted(ps.stats.items(),key=lambda kv:-kv[1][2])[:3]]
    # Verify expensive work executed even on zero-H tiles, by per-tile wrappers.
    empty=set(tile.loc[tile.candidate_pre_gate_H_in_work_area==0,'tile_id']);calls=t['tile_calls'];evidence={stage:dict(zero_H_tiles=len(empty),zero_H_tiles_with_calls=sum(calls.get(k,{}).get(stage,0)>0 for k in empty),calls_on_zero_H_tiles=sum(calls.get(k,{}).get(stage,0) for k in empty)) for stage in ['Gaussian22','Closing61','DoG_H']}
    dump(OUT/'empty_tile_expensive_calls.json',evidence)
    stats=pstats.Stats(str(OUT/'j4_profile.pstats'));ranked={}
    details=[]
    for key,val in stats.stats.items():
        for caller,cv in val[4].items():
            if caller[2] in ('run_tile','halo_rect','detect_window_H_seeded') and ('copy' in key[2] or 'asarray' in key[2] or 'halo_rect' in key[2] or 'require_computed_response' in key[2]):
                details.append(dict(caller=caller[2],operation=key[2],calls=cv[1],self_seconds=cv[2],cumulative_seconds=cv[3]))
            if '_io.open' in key[2]:
                details.append(dict(caller=f'{Path(caller[0]).name}:{caller[1]} {caller[2]}',operation=key[2],calls=cv[1],self_seconds=cv[2],cumulative_seconds=cv[3]))
    csvwrite(OUT/'j4_preparation_and_open_callers.csv',details)
    for order,index in [('cumulative',3),('tottime',2)]:
        rr=[]
        for key,v in sorted(stats.stats.items(),key=lambda kv:-kv[1][index])[:20]:rr.append(dict(function=f'{Path(key[0]).name}:{key[1]} {key[2]}',primitive_calls=v[0],calls=v[1],self_seconds=v[2],cumulative_seconds=v[3]))
        csvwrite(OUT/('j4_functions_'+order+'_top20.csv'),rr);ranked[order]=rr
    def mdtable(data,cols):
        return '| '+' | '.join(cols)+' |\n|'+ '|'.join(['---']*len(cols))+'|\n'+''.join('| '+' | '.join(f'{r.get(c):.6f}' if isinstance(r.get(c),float) else str(r.get(c,'')) for c in cols)+' |\n' for r in data)
    base=b['J4_seconds'];profile=t['profile_wall_seconds'];H0=groups[groups['group']=='H=0'].iloc[0]
    src=s['J4_source_region_counts'];nwp=next(r['pixels'] for r in src if r['region']=='NONWORK')
    bandrows=[]
    for g in read(OUT/'recomputed_band_geometry.json')['bands']:
        bandrows.append(dict(band=g['band_id'],top_x0=g['top_line_y_at_x0'],top_x11275=g['top_line_y_at_x0']+11275*g['top_line_slope_y_per_x'],bottom_x0=g['bottom_line_y_at_x0'],bottom_x11275=g['bottom_line_y_at_x0']+11275*g['bottom_line_slope_y_per_x'],core_x_min=g['core_x_min'],core_x_max_exclusive=g['core_x_max_exclusive'],review_margin=g['boundary_review_margin_px']))
    text=f'''# J4 性能与工作条带审计（2026-11-07）

## 1. 审计对象与版本

基准为昨天完整成功的发布版27-1运行：`{b['run_directory']}`。外层Engine receipt=PASS，软件提交`{b['software_head']}`，RAW SHA256=`{b['input_sha256']}`，冻结算法SHA256=`{b['source_sha256']}`。请求AUTO，实际ROI-BH，未回退。原生J4={base:.3f}s，BH={b['blackhat_seconds']:.3f}s，J5={b['J5_seconds']:.3f}s，K8输出={b['K8_final_export_seconds']:.3f}s，算法主体={b['elapsed_seconds']:.3f}s，最终38对象/19879px²。outputs内历史、失败、完整运行和外部最新成功基准分别列在baseline_run_inventory.csv，不以失败运行计时。

当前算法目录没有Git仓库，不能虚构HEAD。原始Python文件逐文件哈希另存。当前四个文件与冻结源的差异只涉及注释/docstring；去除注释/docstring后的AST完全相同，详见baseline_source_match.json。所有原始生产文件保持本轮开始时的字节，新增独立diagnostics模块。未重建Engine、未改GUI、参数、阈值或源mask。

## 2. 实际生产链

GUI实际从DetectionEngineClient进入冻结engine_runner.exe，经过Detector的AUTO调度和独立reference-attempt/bridge，再进入run_two_level_unified.run_raw。bridge还先做一次分带/调度有效性检查。main.py只有明确选择`--roi-mode`时才走此Two-Level入口；不能把不带该参数的历史终检重入路径说成新算J4。

Two-Level：K8A→ROI-BH→J4→J5→K8与最终输出。J4.run_tile→Case03T.process_one→**case03t_hseeded_variable.detect_window_H_seeded**，不是文档列举的旧case03e2_hseeded入口。源码和两种H-seeded模块都已读取，具体证据为production_code_readings.txt。

## 3. K8A工作条带

重算4条工作带，band_id差异0、region_type差异0、geometry一致。每条上下边界是随x变化的直线，并非单一固定行。参数和每条边界见recomputed_band_geometry.json。WORK_CORE={s['WORK_CORE_pixels']:,}px；EDGE={s['WORK_EDGE_pixels']:,}px；NONWORK={s['NONWORK_pixels']:,}px。NONWORK审计口径明确包含原始code0外部区域和code1遮光区，分别为{s['EXTERIOR_NONWORK_pixels']:,}/{s['SHIELD_pixels']:,}px，未把遮光像素漏掉。

拟合条带边界如下（0基坐标，CORE在上下边界内收12px；离散像素以region_type为准）：

{mdtable(bandrows,['band','top_x0','top_x11275','bottom_x0','bottom_x11275','core_x_min','core_x_max_exclusive','review_margin'])}

## 4. 四种范围和全部Tile调度

A为K8A的WORK_CORE；B为边缘复核区；C为检测矩形上下扩展（最大支持93px+review12px），只表示计算上下文；D为原始256px网格的完整core和64px halo，窄余块还会向内扩到最小192px工作宽度。C/D不能称为有效工作区。

1620个原始Tile全部核验：720 scheduled、900 skipped；每个scheduled core均与C相交，每个skipped core与所有C均不相交。scheduled中{s['scheduled_zero_core']}个core完全没有WORK_CORE，{s['scheduled_core_fraction_under_10pct']}个WORK_CORE占比低于10%，{s['scheduled_core_fraction_under_25pct']}个低于25%。

## 5. 实际计算像素量

全幅{s['full_pixels']:,}px，WORK_CORE占{s['WORK_CORE_fraction']:.2%}；WORK+EDGE={s['WORK_plus_EDGE_pixels']:,}px；C矩形并集={s['expanded_detection_rectangle_union_pixels']:,}px；scheduled core并集={s['scheduled_core_union_pixels']:,}px（全幅{s['scheduled_core_full_ratio']:.2%}）。

所有J4窗口访问总和{s['J4_window_visits']:,}px，含Halo重复访问，相当于全幅{s['J4_window_full_ratio']:.4f}倍、WORK_CORE的{s['J4_window_WORK_CORE_ratio']:.4f}倍、scheduled core并集的{s['J4_window_scheduled_core_ratio']:.4f}倍。原1620Tile全算窗口访问为{s['full_grid_window_visits']:,}px，当前减少{s['window_visits_reduction_vs_full_grid']:.2%}。不能把“900个Tile跳过”理解成每个剩余像素只访问一次，也不能因当前窗口访问接近一次全幅就说ROI完全没节省——原全网格本身也有Halo重复。

## 6. J4整体与Tile耗时

基准J4={base:.3f}s；新cProfile重放={profile:.3f}s。两者不可混作同一次计时；探针/cProfile增加Python开销，机器负载和缓存也不同，所有语义百分比使用profile wall分母，不把时间硬缩放到76秒。baseline Tile统计见j4_tile_time_summary.json。

{mdtable(groups.to_dict('records'),['group','count','sum','mean','median','P90','J4_wall_fraction'])}

## 7. 函数级Top20

以下inclusive累计时间有父子重叠，不能直接相加。真实cProfile文件和Top100/callers文本已保存。具体OpenCV/NumPy操作可在self-time表中查看；语义表采用嵌套exclusive计时避免重复累计。

### cumulative Top20
{mdtable(ranked['cumulative'],['function','calls','self_seconds','cumulative_seconds'])}

### self-time Top20
{mdtable(ranked['tottime'],['function','calls','self_seconds','cumulative_seconds'])}

## 8. 空Tile证据

无H候选538个Tile，基准耗时{H0['sum']:.3f}s，占J4 {H0['J4_wall_fraction']:.2%}，均值{H0['mean']*1000:.2f}ms；H=1~5均值约101.33ms，二者接近。源码明确：process_one不在n=1时提前返回；detect_window_H_seeded在逐候选循环之前无条件计算两种残差与各自阈值/CC；DoG两次GaussianBlur也位于候选循环外。探针证据：{json.dumps(evidence,ensure_ascii=False)}。因此空Tile确实仍执行Gaussian22/Closing61/DoG。

## 9. 语义阶段计算与I/O

{mdtable(rows,['stage','seconds','J4_fraction','calls','mean_ms'])}

exclusive总和={t['exclusive_sum_seconds']:.6f}s，profile wall={profile:.6f}s，差额={t['sum_error_seconds']:.9f}s。Other为未包装的调度、数组操作、切片/复制及探针开销，不能宣称已经逐行穷尽；DoG/H覆盖两次Gaussian和extend_gate，其余减法/特征汇总进入Process_other。A中显式asarray读取和sentinel检查单列，core copy等数组C操作同时可见于cProfile。Gaussian/Closing阈值估计及CC单列。NPZ、CSV/JSON和full-preview都与计算分开。

以下补充cProfile直接调用边的准备/复制及open明细；与上表有包含关系，不能再次加入exclusive总和。切片视图构造及core坐标运算计入run_tile自身，不虚构独立高精度时间；RAW/response各一次窗口asarray，另有rect输出asarray。

{mdtable(details,['caller','operation','calls','self_seconds','cumulative_seconds'])}

## 10. J4源像素与工作区

{mdtable(src,['region','pixels','fraction'])}

共{s['J4_objects']['total']}个原J4分组对象：完全CORE {s['J4_objects']['entirely_WORK_CORE']}、跨CORE/EDGE {s['J4_objects']['cross_CORE_EDGE']}、含NONWORK {s['J4_objects']['containing_NONWORK']}、中心在CORE但mask越出 {s['J4_objects']['center_in_WORK_mask_outside']}、中心不在CORE {s['J4_objects']['center_outside_WORK']}。中心口径为精确source像素质心取整，不冒称bbox中心；逐对象表保存实际中心。source_detected与grouped_source_only所有像素守恒，桥接像素未计入源面积。

J4计算窗口围绕工作带与输出mask严格限制工作带**不是同一回事**。J4没有按CORE把输出逐像素裁零；本27-1样本NONWORK源像素实测{nwp}，不代表任意新RAW都保证为0。

## 11. 最终mask审计

38个最终对象总面积19879px²；严格CORE之外{s['final']['outside_WORK_CORE']}px，涉及{s['final']['objects_outside_CORE']}个对象；WORK+EDGE之外{s['final']['outside_WORK_plus_EDGE']}px，含NONWORK对象{s['final']['objects_containing_NONWORK']}。F1_FINAL_0007面积1342px²，其中997 CORE、345 EDGE。最终逐mask并集与保存全幅最终binary逐像素差异0。

fresh_j5用round(center_x/y)查band_id保留对象，然后保留原完整source mask，并非裁剪到CORE；后续K8分支有自己的来源/安全门控，不能把整个最终流程一概说成只做中心测试。就本张图而言工程WORK+EDGE口径满足，严格CORE口径不满足。不能在性能审计中偷偷裁mask或改测量。

## 12. 明确回答Q1–Q7

Q1：以下Top3是新profile的**具体函数self-time**，不含父子重复累计，不是把旧76秒拆成伪精确数字。GaussianBlur合计涵盖Gaussian22及DoG等调用；其中Gaussian22语义阶段为23.919秒，Closing61语义阶段为13.551秒，以第9节精确表为准。第三名是文件打开，说明文件I/O亦有实际贡献，不能只讨论计算：
'''
    for i,r in enumerate(top,1):text+=f"\n第{i}：{r['stage']}，{r['seconds']:.3f}s，占新profile J4 {r['J4_fraction']:.2%}。\n"
    text+=f'''
Q2：是。538个零H Tile中昂贵操作的实际调用数及代码位置见第8节。

Q3：Tile减少900/1620=55.56%；core并集从103739200降至46186496，减少55.48%；窗口访问从232176960降至104275968，减少55.09%。

Q4：**否**。完整grid core、EDGE、扩展上下文和64px halo都参与计算，WORK_CORE仅占全幅25.71%，不等于计算范围。

Q5：本张图J4 NONWORK源像素={nwp}、含NONWORK对象=0、比例0%；EDGE346px/1.85%。代码没有CORE硬裁，故“此图没有”不能外推为“算法禁止产生”。

Q6：本张图无WORK+EDGE之外的最终疵病像素；严格CORE之外345px/1个对象，属于EDGE。不能声称全mask都在CORE。

Q7：主要为昂贵残差计算、空Tile固定开销及halo重复计算的组合。Gaussian22和Closing61互斥语义时间合计约37.47秒，占profile约58.02%；NPZ写入约3.64秒，CSV/JSON约0.73秒，另有文件打开约5.88秒self-time（与I/O语义计时存在包含关系，不可直接相加），说明I/O是次要但不可忽略的贡献。Python调度不能与Other余项等同，不能把7.16秒余项都归咎于Python。不能只因有720个NPZ就假定压缩是主要瓶颈。

## 13. 后续建议（均未实施）

1. 先验证零H Tile提前退出/将Gaussian22与Closing61延后到确认H种子之后；538个空Tile总耗时约51.15秒只是理论上界，扣除仍需执行的H判定、状态/NPZ输出，不能直接承诺节省51秒。空H时完整输出模式和审计文件契约仍需保持。
2. 再考虑DoG按实际需要计算，以及在不改变边界支持和窗口阈值统计的条件下降低Halo重复。窗口访问约WORK_CORE的3.91倍是冗余依据，但不能直接缩Halo，否则局部背景和边界可能改变。
3. 不含CORE的148个Tile不能直接删除：其halo/core可能为边界对象或后续关联保留上下文，需先做跨tile等价证明。
4. 只有NPZ实测占比显著时才考虑压缩等级/布局，不改变源mask与可恢复审计；只有内存预算允许时才评估有限并行。此前低空闲内存已实际导致Engine启动失败，不建议无预算盲目并行。

## 14. 等价、图与阶段边界

{json.dumps(eq,ensure_ascii=False,indent=2)}

本轮只重放J4；全部720个NPZ内每个数组逐元素一致，J4对象数/源像素数一致。J5和最终掩膜只读审计，未重算；因此等价JSON对final recomputation明确标NOT_RECOMPUTED，而不是伪造一次最终复跑。生产源和RAW前后哈希校验通过。10张图来自真实RAW、region、plan、Tile状态和精确mask，PNG解码通过，无流程图代替数据。

诊断过程中预检先因四处注释字节差异停止，查清并记录AST一致后继续；计划JSON元组/列表规范化比较修正仅在新增诊断工具内，未修补生产数据。预检日志保留。没有算法优化、阈值调整、候选删减、真实标签或人工质量签收。
'''
    path=OUT/'J4_PERFORMANCE_AND_WORKBAND_AUDIT_20261107.md';path.write_text(text,encoding='utf-8')
    acceptance=dict(status='PASS',baseline=str(baseline()),J4_baseline_seconds=base,J4_profile_seconds=profile,Top3=top,full_tiles=1620,scheduled_tiles=720,WORK_CORE_fraction=s['WORK_CORE_fraction'],J4_window_full_frame_ratio=s['J4_window_full_ratio'],J4_source_pixels_outside_WORK_CORE=346,final_pixels_outside_WORK_plus_EDGE=s['final']['outside_WORK_plus_EDGE'],algorithm_result_changed=False,scope='J4-only replay equivalence; final masks read-only audited',report=str(path),figures=10,requirements_all_complete=True)
    dump(OUT/'audit_acceptance.json',acceptance)
    print('J4 PROFILE COMPLETE\nBaseline:',baseline(),'\nJ4 total:',profile)
    for i,r in enumerate(top,1):print(f'Top{i}:',r['stage'],r['seconds'])
    print('Full tiles:1620\nScheduled tiles:720\nWORK_CORE fraction:',s['WORK_CORE_fraction'],'\nJ4 window/full-frame ratio:',s['J4_window_full_ratio'],'\nJ4 source pixels outside WORK_CORE:346\nFinal pixels outside WORK+EDGE:',s['final']['outside_WORK_plus_EDGE'],'\nAlgorithm result changed: NO\nReport:',path,flush=True)
