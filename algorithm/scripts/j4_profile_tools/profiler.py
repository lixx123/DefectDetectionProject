"""Temporary, restored wrappers; exclusive wall timing plus true cProfile."""
import sys,time,cProfile,pstats,io,functools
from contextlib import ExitStack
from collections import defaultdict
from unittest.mock import patch
import numpy as np,cv2,pandas as pd
from .common import OUT,RAW,baseline,read,dump,csvwrite,verify_sources

class Timer:
    def __init__(self):self.stack=[];self.rows=defaultdict(lambda:[0.,0.,0]);self.tile=None;self.tile_calls=defaultdict(lambda:defaultdict(int))
    def wrap(self,fn,label):
        @functools.wraps(fn)
        def call(*args,**kwargs):
            category=label(args,kwargs,sys._getframe(1)) if callable(label) else label
            if category is None:return fn(*args,**kwargs)
            start=time.perf_counter();entry=[category,start,0.];self.stack.append(entry)
            if self.tile:self.tile_calls[self.tile][category]+=1
            try:return fn(*args,**kwargs)
            finally:
                dt=time.perf_counter()-start;self.stack.pop();row=self.rows[category];row[0]+=dt-entry[2];row[1]+=dt;row[2]+=1
                if self.stack:self.stack[-1][2]+=dt
        return call

def aliases(stack,fn,wrapped):
    # The production code imports several functions by name; instrument all loaded
    # aliases of this exact object, without changing its implementation/arguments.
    for name,mod in list(sys.modules.items()):
        if mod is None or not name.startswith(('scripts.','src.')):continue
        for key,value in list(vars(mod).items()):
            if value is fn:stack.enter_context(patch.object(mod,key,wrapped))

def profile():
    from scripts import run_case03j4_fullscan as j4
    from scripts import run_case03t_threeway_comparison as three
    from src.detection import case03t_hseeded_variable as hs
    from src.detection import case03e2_bounded_rescue as rescue
    from src.detection import case03i_size_grade as grade
    from src.detection import case03j_continuous_contour as continuous
    b=baseline();plan=read(b/'detection_plan.json');old=read(b/'upstream_J4/fresh/config_snapshot.json')
    timer=Timer();stats=cProfile.Profile();original_tile=j4.run_tile
    events=[]
    def tile(*args,**kwargs):
        tile_id=args[0]['tile_id'];timer.tile=tile_id;start=time.perf_counter()
        try:return original_tile(*args,**kwargs)
        finally:events.append(dict(tile_id=tile_id,wall=time.perf_counter()-start));timer.tile=None
    def residual_label(args,kw,frame):return 'Gaussian22' if args[1]=='gaussian22' else 'Closing61'
    def cc_label(args,kw,frame):
        if frame.f_code.co_name=='detect_window_H_seeded':
            source=frame.f_locals.get('source');return source+'_threshold_CC' if source in ('gaussian22','closing61') else 'H170_230_CC'
        if frame.f_code.co_name in ('hysteresis_window','process_one','_H_component_catalog'):return 'H170_230_CC'
        return None # Other CC remains charged to its semantic parent.
    def blur_label(args,kw,frame):
        if frame.f_code.co_name=='process_one':return 'DoG_H'
        return None
    def array_label(args,kw,frame):
        return 'Tile_RAW_response_read' if frame.f_code.co_name=='run_tile' and frame.f_code.co_filename.endswith('run_case03j4_fullscan.py') else None
    with ExitStack() as stack:
        targets=[(j4.process_one,'Process_other'),(three.hysteresis_window,'H170_230_CC'),
            (three.detect_window_H_seeded,'H_seeded_other'),(hs.compute_local_residual,residual_label),
            (hs._robust_thresholds,lambda a,k,f:f.f_locals.get('source','unknown')+'_threshold_CC'),
            (hs._refinement_by_H_seed,'H_seeded_other'),(rescue.rescue_bounded_H_extension,'H_seeded_bounded_fallback'),
            (three.local_raw_statistics,'F'),(three.classify_candidate,'F'),(three.decide_gate,'G'),(three.build_joint_maps,'G'),(three.extend_gate,'DoG_H'),
            (j4.extract_regions,'extract_regions'),(j4.associate_fragments,'J1'),(j4.reconstruct_continuous_visual,'J2'),(j4.measure_visual_bbox,'bbox_Feret'),
            (j4.require_computed_response,'Tile_RAW_response_read'),(j4.json_save,'CSV_JSON_write'),(j4.render_full_preview,'full_preview')]
        # Feret is nested in region/association/reconstruction; exclusive timing avoids double counting.
        for name in ['max_feret_centers_px','max_feret','max_feret_px','maximum_feret','max_hull_distance','full_diameter']:
            for mod in [grade,continuous,hs]:
                if hasattr(mod,name):targets.append((getattr(mod,name),'bbox_Feret'))
        seen=set()
        for fn,label in targets:
            if id(fn) in seen:continue
            seen.add(id(fn));aliases(stack,fn,timer.wrap(fn,label))
        stack.enter_context(patch.object(j4,'run_tile',tile))
        stack.enter_context(patch.object(np,'asarray',timer.wrap(np.asarray,array_label)))
        stack.enter_context(patch.object(cv2,'connectedComponentsWithStats',timer.wrap(cv2.connectedComponentsWithStats,cc_label)))
        stack.enter_context(patch.object(cv2,'GaussianBlur',timer.wrap(cv2.GaussianBlur,blur_label)))
        stack.enter_context(patch.object(np,'savez_compressed',timer.wrap(np.savez_compressed,'NPZ_write')))
        stack.enter_context(patch.object(pd.DataFrame,'to_csv',timer.wrap(pd.DataFrame.to_csv,'CSV_JSON_write')))
        stack.enter_context(patch.object(j4,'OUTROOT',OUT/'profile_replay'))
        start=time.perf_counter()
        try:
            dest=stats.runcall(j4.run,'fresh',halo=old['overlap_for_internal_context'],save_images=False,input_raw_file=RAW,input_fused_npy=b/'fused_blackhat.npy',frame_label=old.get('frame_label','26_1'),scheduled_tile_ids=[t['tile_id'] for t in plan['tiles']],response_coverage=old.get('input_fused_coverage','FULL_FRAME'))
        finally:
            wall=time.perf_counter()-start;stats.dump_stats(str(OUT/'j4_profile.pstats'))
    for key,order in [('cumulative','cumulative'),('tottime','tottime')]:
        stream=io.StringIO();pstats.Stats(stats,stream=stream).sort_stats(order).print_stats(100)
        (OUT/('j4_profile_'+key+'_top100.txt')).write_text(stream.getvalue(),encoding='utf-8')
    stream=io.StringIO();pstats.Stats(stats,stream=stream).sort_stats('cumulative').print_callers(100)
    (OUT/'j4_profile_callers.txt').write_text(stream.getvalue(),encoding='utf-8')
    rows=[dict(stage=k,seconds=v[0],J4_fraction=v[0]/wall,calls=v[2],mean_ms=1000*v[0]/v[2],inclusive_seconds=v[1]) for k,v in timer.rows.items()]
    charged=sum(r['seconds'] for r in rows);rows.append(dict(stage='Other_run_and_wrapper_overhead',seconds=wall-charged,J4_fraction=(wall-charged)/wall,calls=1,mean_ms=1000*(wall-charged),inclusive_seconds=wall-charged))
    rows.sort(key=lambda r:-r['seconds']);csvwrite(OUT/'j4_semantic_timing.csv',rows)
    dump(OUT/'j4_semantic_timing_summary.json',dict(profile_wall_seconds=wall,baseline_wall_seconds=read(OUT/'PROFILE_BASELINE_RUN.json')['J4_seconds'],exclusive_sum_seconds=sum(r['seconds'] for r in rows),sum_error_seconds=wall-sum(r['seconds'] for r in rows),rows=rows,method='Nested wrappers subtract child inclusive time. mean_ms uses exclusive time. Other contains unwrapped run orchestration and measurement overhead. cProfile adds overhead; baseline seconds are not rescaled.',tile_calls=timer.tile_calls,tile_wall=events))
    # Exact equality of EVERY saved NPZ array, not compressed archive byte equality.
    mismatches=[];pixels=0;objects_old=read(b/'upstream_J4/fresh/run_status.json')['candidate_j4_local_objects'];new=read(dest/'run_status.json')
    for f in sorted((b/'upstream_J4/fresh/tile_masks').glob('*.npz')):
        with np.load(f,allow_pickle=False) as x,np.load(dest/'tile_masks'/f.name,allow_pickle=False) as y:
            if set(x.files)!=set(y.files):mismatches.append(f.name+':keys');continue
            for key in x.files:
                if not np.array_equal(x[key],y[key]):mismatches.append(f.name+':'+key)
            pixels+=int(x['source_detected_uint8'].sum())
    eq=dict(scope='J4-only replay: no J5/final recomputation',algorithm_parameters_changed=False,J4_source_masks_pixel_equal=not mismatches,J4_all_npz_arrays_pixel_equal=not mismatches,J4_tiles=len(events),J4_baseline_tiles=len(plan['tiles']),J4_source_pixel_count=pixels,J4_object_count_equal=objects_old==new['candidate_j4_local_objects'],J4_object_count=objects_old,mismatches=mismatches,final_masks_pixel_equal='NOT_RECOMPUTED_READ_ONLY_BASELINE',final_object_count_equal='NOT_RECOMPUTED_READ_ONLY_BASELINE')
    dump(OUT/'profiling_result_equivalence.json',eq)
    assert not mismatches and eq['J4_object_count_equal'] and len(events)==len(plan['tiles'])
    verify_sources();print('J4_PROFILE_AND_PIXEL_EQUIVALENCE_PASS',wall,flush=True)
