"""真正调用受控原J4/J5；正式运行不读历史对象/GT，不落盘SMALL明细。"""
import math
import sys
sys.dont_write_bytecode=True
import guard
guard.activate('detector')
from common import *
from collections import defaultdict
from dataclasses import asdict
import memory_store as store
from fast_state import STATE
import timings
import stage_j4 as J4,stage_j5 as J5,stage_process
def init(inp,mode):
 pp=read(ROOT/'config/postprocess.json');STATE.mode=mode;STATE.early=mode=='MEDIUM_LARGE_FAST';STATE.ids=np.load(inp['ids'],mmap_mode='r');STATE.counts.clear()
 STATE.params={'medium_area':pp['grade']['medium_area_min_px2'],'medium_length':pp['grade']['medium_length_min_px'],'J1_gap':pp['association']['max_gap_px'],'J2_gap':pp['display_bridge']['context_max_gap_px'],'J5_gap':pp['J5']['gap_max_px'],'bridge_corridor_radius':max(4,pp['display_bridge']['bridge_half_width_px'])}
 refine,seed,f,g,h=J4.policies()
 STATE.params['micro_cluster_exit_proof_enabled']=seed.min_h_pixels_for_refinement<=min(pp['association']['min_piece_area_px'],pp['display_bridge']['piece_min_area_px'],pp['J5']['min_piece_area_px'],5)
 assert seed.min_h_pixels_for_refinement<=min(f.protect_large_area_px,g.protect_support_area_min_px,h.medium_min_area_px)
 return pp,(refine,seed,f,g,h),J4.SizeGradeConfig(**pp['grade']),J4.AssociationConfig(**pp['association']),J4.ContinuousConfig(**pp['display_bridge'])
def j5(plan,raw,pp,policy):
 rows={o['object_id']:o for rr in store.ROWS.values() for o in rr};by=defaultdict(dict)
 for uid,row in rows.items():by[row['tile_id']][int(row['local_object_index'])]=uid
 config=J5.J5Config(**pp['J5']);config.validate();edges,seams,proposed=J5.candidate_seam_edges(plan,rows,by,store.load,raw,config)
 uf=J5.UnionFind(list(rows))
 for e in edges:
  if e['accepted']:uf.join(e['a_id'],e['b_id'])
 groups=defaultdict(list)
 for key in rows:groups[uf.find(key)].append(key)
 moments,hulls=J5.moments_and_hulls(plan,store.load,by,groups)
 objects,mapping,meta=J5.reconcile(rows,edges,moments,hulls,J4.SizeGradeConfig(**pp['grade']),output_policy=policy)
 return objects,mapping,rows,{'seams':seams,'proposals':proposed,**meta}
def export(inp,a,folder,objects,mapping,localrows):
 # 所有映射与精确Mask均来自本次实际原J4/J5内存结果。
 import cv2
 from PIL import Image,ImageDraw,ImageFont
 rows=[];maskdir=folder/'MEDIUM_LARGE_FINAL_EXACT_MASKS';maskdir.mkdir(parents=True,exist_ok=True);ids=STATE.ids
 frozen={int(b['band_id']):(float(b['low_dn']),float(b['high_dn'])) for b in inp['specs'][a]}
 for o in objects:
  assert o['grade']!='SMALL';gid=o['global_defect_id'];x=int(o['display_bbox_x_global']);y=int(o['display_bbox_y_global']);xx=x+int(o['display_bbox_width_px']);yy=y+int(o['display_bbox_height_px']);mask=np.zeros((yy-y,xx-x),bool);bridge=mask.copy();members=[]
  for uid in sorted(k for k,v in mapping.items() if v==gid):
   loc=localrows[uid];tile=loc['tile_id'];index=int(loc['local_object_index']);data=store.all_data(tile);tx,ty,te,tb=map(int,data['core_xyxy']);m=data['grouped_source_only_i32']==index;br=data['inferred_bridge_i32']==index;ix,iy,ie,ib=max(x,tx),max(y,ty),min(xx,te),min(yy,tb)
   mask[iy-y:ib-y,ix-x:ie-x]|=m[iy-ty:ib-ty,ix-tx:ie-tx];bridge[iy-y:ib-y,ix-x:ie-x]|=br[iy-ty:ib-ty,ix-tx:ie-tx]
   members.append({'tile_id':tile,'source_sha256':hashlib.sha256(m.tobytes()).hexdigest(),'source_area':int(m.sum()),'region_members_count':int(loc['member_count'])})
  bridge&=~mask;assert int(mask.sum())==o['source_area_px2'];valid=ids[y:yy,x:xx]>0;em=mask&valid;bid=ids[y:yy,x:xx][mask];v=bid[bid>0];band=int(np.bincount(v).argmax()) if len(v) else 0
  p=maskdir/(gid+'.npz');np.savez_compressed(p,mask=mask,inferred_bridge=bridge,global_RAW_bbox_xyxy_exclusive=np.array([x,y,xx,yy]));members.sort(key=lambda q:(q['tile_id'],q['source_sha256']))
  rows.append({**o,'new_id':gid,'sample_id':inp['sample_id'],'strategy':a,'status':'AUTO_CANDIDATE','band_id':band,'threshold_mode':'b15_pixel','threshold_strategy':'H3_P95_P99_9_PER_BAND','threshold_low_dn':frozen[band][0] if band in frozen else None,'threshold_high_dn':frozen[band][1] if band in frozen else None,'bbox_xyxy_exclusive':json.dumps([x,y,xx,yy]),'source_area_scope':'FULL_BASELINE_SOURCE_FOR_EXACT_REGRESSION','baseline_source_area_px2':int(mask.sum()),'baseline_Feret_px':o['source_max_feret_px'],'EVAL_source_area_px2':int(em.sum()),'outside_EVAL_source_pixels':int((mask&~valid).sum()),'EVAL_Feret_px':_feret(em),'measurement_scope_status':'UNRESOLVED_DUAL_SCOPE' if (mask&~valid).any() else 'EVAL_EQUALS_BASELINE','mask_path':str(p.relative_to(folder)),'mask_sha256':sha(p),'association_source_members':json.dumps(members),'detector_pixel_pitch_um':read(ROOT/'config/run_config.json')['physical_pixel_pitch_detector_plane_um']})
 csvout(str((folder/'MEDIUM_LARGE_FINAL_OBJECTS.csv').relative_to(OUT)),rows)
 raw=np.memmap(inp['raw'],dtype='>u2',mode='r',shape=(9200,11276));r=np.asarray(raw[::4,::4],np.float32);lo,hi=np.percentile(r,[1,99.5]);gray=np.uint8(np.clip((r-lo)/max(hi-lo,1)*255,0,255));im=Image.fromarray(gray).convert('RGB');d=ImageDraw.Draw(im)
 for o in rows:
  x,y,xx,yy=json.loads(o['bbox_xyxy_exclusive']);color=(255,75,30) if o['grade']=='LARGE' else (255,200,20);d.rectangle((x//4,y//4,(xx-1)//4,(yy-1)//4),outline=color)
  d.text((min(x//4,im.width-180),max(0,y//4-12)),o['new_id']+' A'+str(o['baseline_source_area_px2'])+' L'+str(o['baseline_Feret_px']),fill=color)
 page=Image.new('RGB',(im.width,im.height+64),'white');page.paste(im,(0,64));draw=ImageDraw.Draw(page);draw.text((15,6),inp['sample_id']+' '+a+' MEDIUM_LARGE_FAST | AUTO_CANDIDATE',fill='black',font=ImageFont.truetype(r'C:\Windows\Fonts\arial.ttf',24));draw.text((15,36),'full baseline source dimensions; EVAL-only metrics separately; no SMALL final output',fill='black',font=ImageFont.truetype(r'C:\Windows\Fonts\arial.ttf',18));page.save(folder/'MEDIUM_LARGE_RAW_BOXES_AUTO_CANDIDATE.png')
 # 仅中大对象contact sheet，不画Mask，不创建小对象图。
 cellw,cellh=240,210;sheet=Image.new('RGB',(cellw*6,cellh*max(1,math.ceil(len(rows)/6))),'white');dd=ImageDraw.Draw(sheet)
 for k,o in enumerate(rows):
  x,y,xx,yy=json.loads(o['bbox_xyxy_exclusive']);rx,ry,re,rb=max(0,x-16),max(0,y-16),min(11276,xx+16),min(9200,yy+16);ar=np.asarray(raw[ry:rb,rx:re],np.float32);g=np.uint8(np.clip((ar-lo)/max(hi-lo,1)*255,0,255));thumb=Image.fromarray(g).convert('RGB');z=ImageDraw.Draw(thumb);z.rectangle((x-rx,y-ry,xx-1-rx,yy-1-ry),outline='red',width=1);thumb.thumbnail((230,170));px=(k%6)*cellw;py=(k//6)*cellh;sheet.paste(thumb,(px,py+35));dd.text((px+4,py+2),o['new_id']+' '+o['grade'],fill='black');dd.text((px+4,py+16),'A'+str(o['baseline_source_area_px2'])+' L'+str(o['baseline_Feret_px'])+'px',fill='black')
 sheet.save(folder/'MEDIUM_LARGE_CONTACT_SHEET_AUTO_CANDIDATE.png')
 # 后处理仅分流展示，原总表、Mask、计量与检测调用保持不变。
 from config import user_config as cfg
 from src.detection.size_review import Settings
 from src.visualization.size_review_report import write_reports
 settings=Settings(cfg.H3_SIZE_REVIEW_LENGTH_RATIO,cfg.H3_SIZE_REVIEW_THICKNESS_RATIO)
 bands={int(b['band_id']):b for b in inp.get('size_review_bands',[])}
 receipt=write_reports(folder,rows,bands,settings,gray,enabled=cfg.H3_SIZE_REVIEW_ENABLED)
 logging.info('Size review: total=%d normal=%d review=%d classify=%.6fs',receipt['total'],receipt['normal'],receipt['review'],receipt['classification_seconds'])
 if cfg.H3_SIZE_REVIEW_ENABLED and cfg.H3_EDGE_SPOTS_ENABLED:
  from src.detection.edge_attached_spots import EdgeSpotSettings
  from src.visualization.edge_spot_report import write_edge_spots
  edge_receipt=write_edge_spots(folder,rows,bands,raw,gray,settings,EdgeSpotSettings(**cfg.H3_EDGE_SPOTS))
  logging.info('Edge spots: children=%d total=%.3fs',edge_receipt['children'],edge_receipt['total_seconds'])
 return rows
def _feret(m):
 import cv2
 y,x=np.nonzero(m)
 if not len(x):return 0.
 if len(x)==1:return 1.
 pts=cv2.convexHull(np.c_[x,y].astype(np.float32).reshape(-1,1,2)).reshape(-1,2).astype(float);return max(1.,max(float(((pts[i:i+128,None]-pts[None])**2).sum(2).max()) for i in range(0,len(pts),128)))**.5
def one(inp,a,mode,plan,qa=False):
 pp,policies,grade,j1,j2=init(inp,mode);s=inp['sample_id'];folder=OUT/(f'qa_full_reference/RULE_V3/{s}/{a}/{mode}' if qa else f'runs/FAST_V3/{s}/{a}');folder.mkdir(parents=True,exist_ok=False);store.reset('QA' if qa else 'FAST',folder);timings.clear();J4.clear_band_map_cache()
 raw=np.memmap(inp['raw'],dtype='>u2',mode='r',shape=(9200,11276));response=np.load(inp['response'],mmap_mode='r');spec={'bands':inp['specs'][a],'fallback':[65536.,65536.],'pixel_band_ids':inp['ids']};statuses=[];allstart=time.perf_counter()
 # 仪表开销在无包裹状态下实测，随后按实测次数折算本次运行成本。
 overhead_seconds_per_call=timings.measure_overhead()
 with timings.instrument():
  tic=time.perf_counter()
  for k,tile in enumerate(plan):
   status=J4.run_tile(tile,raw,response,policies,grade,j1,j2,64,folder,image_enabled=False,frame_label=s,threshold_mode='b15_pixel',perband_spec=spec);statuses.append(status)
   if k%100==0:logging.info('%s %s %s J4 %d/%d',s,a,mode,k,len(plan))
  t4=time.perf_counter()-tic;tic=time.perf_counter();objects,mapping,loc,meta=j5(plan,raw,pp,'LEGACY_FULL' if qa else 'MEDIUM_LARGE_ONLY');t5=time.perf_counter()-tic
 # QA可存完整中间结果；正式FAST只输出中大与必要血缘。
 if qa:
  csvout(str((folder/'J5_QA_OBJECTS.csv').relative_to(OUT)),objects);dump(str((folder/'J5_QA_MAPPING.json').relative_to(OUT)),mapping)
 else:
  te=time.perf_counter();export(inp,a,folder,objects,mapping,loc);exporttime=time.perf_counter()-te
 total=time.perf_counter()-allstart
 counters=dict(STATE.counts);counters.update(final_MEDIUM=sum(o['grade']=='MEDIUM' for o in objects),final_LARGE=sum(o['grade']=='LARGE' for o in objects),SMALL_final_rows=0 if not qa else sum(o['grade']=='SMALL' for o in objects),J5_SMALL_final_gate_rejected=meta['small_final_gate_rejected'],J4_initial_H_components=sum(st['candidate_pre_gate_H_in_work_area'] for st in statuses),J4_nonempty_tiles=sum(not st['early_exit_empty_H'] for st in statuses))
 stats={'sample_id':s,'strategy':a,'mode':mode,'J4_total':t4,'J5_total':t5,'J4_J5_total':t4+t5,'export_seconds':'NOT_APPLICABLE' if qa else exporttime,'total_runtime':total,'tiles':len(plan),'peak_memory_scope':'process lifetime, not stage-specific peak','memory':memory(),'disk_hardware_IO':'NOT_VERIFIABLE','cache':'shared frozen memmaps; G0 hash read warms input cache; no parallel experiment workers','function_timers_scope':'per-function inclusive/exclusive wrapper timers; inclusive nests, so never sum inclusive rows to get a stage total','instrumentation':dict(timings.stats(),wrapper_overhead_seconds_per_call_measured=overhead_seconds_per_call,estimated_wrapper_overhead_seconds=overhead_seconds_per_call*timings.stats()['total_wrapped_calls'],empty_table_means='no matching src/scripts_v3 function was executed under instrument()'),'source_sha256':{name:sha(Path(__file__).resolve().parent/name) for name in ['stage_j4.py','stage_process.py','stage_refine.py','early_rules.py','memory_store.py','stage_j5.py','timings.py','detector.py']},'legacy_baseline_timing_caveat':'B15 has a different full audit/sys-profile/I-O burden; whole-run speedup is observed pipeline change, not pure P1 effect'}
 dump(str((folder/'execution_times.json').relative_to(OUT)),stats);dump(str((folder/'candidate_stats.json').relative_to(OUT)),counters);dump(str((folder/'frozen_run_config.json').relative_to(OUT)),{'postprocess':pp,'threshold_spec':spec,'input_response_sha256':inp['response_sha256'],'early_exit':STATE.early,'early_exit_proof_parameters':dict(STATE.params),'output_policy':'LEGACY_FULL_QA' if qa else 'MEDIUM_LARGE_ONLY','halo':64,'external_filter_context':93})
 costs=timings.rows(s,a,mode);csvout(str((folder/'function_times.csv').relative_to(OUT)),costs)
 if qa:csvout(str((folder/'tile_counters.csv').relative_to(OUT)),statuses)
 files=[p for p in folder.rglob('*') if p.is_file()];stats.update(persisted_files=len(files),file_bytes_written=sum(p.stat().st_size for p in files));dump(str((folder/'execution_times.json').relative_to(OUT)),stats)
 logging.info('Actual %s %s %s DONE J4 %.3f J5 %.3f total %.3f; counts %s',s,a,mode,t4,t5,total,counters)
 return stats,counters,costs
