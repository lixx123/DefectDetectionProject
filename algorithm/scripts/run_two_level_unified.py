"""Opt-in two-level scheduling; unchanged J4/J5 and final detection semantics."""
from pathlib import Path
from dataclasses import asdict
from contextlib import redirect_stdout
from datetime import datetime
import sys,time,json,shutil,ctypes
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as C
from scripts import run_unified_raw_input as base
from scripts import run_case03j4_fullscan as J4, run_case03j5_global_merge as J5
from src.detection.two_level_roi import build_plan,compute_fused


def peak_memory_bytes():
    if sys.platform!='win32':return None
    class Counters(ctypes.Structure):
        _fields_=[('cb',ctypes.c_ulong),('PageFaultCount',ctypes.c_ulong)]+[(n,ctypes.c_size_t) for n in
            ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
             'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]
    c=Counters();c.cb=ctypes.sizeof(c)
    get=ctypes.windll.kernel32.GetCurrentProcess;get.restype=ctypes.c_void_p
    f=ctypes.windll.psapi.GetProcessMemoryInfo
    f.argtypes=[ctypes.c_void_p,ctypes.POINTER(Counters),ctypes.c_ulong]
    if not f(get(),ctypes.byref(c),c.cb):return None
    return int(c.PeakWorkingSetSize)


def member_signatures(path):
    m=pd.read_csv(path/'global_object_membership.csv')
    return {str(k):frozenset(g.J4_local_object_id.astype(str)) for k,g in m.groupby('global_defect_id',sort=False)}


def reconcile_history(frame,j5,records,selected,out,types):
    """Alias exact member sets, never infer identity from sequence numbers."""
    oldpath=base.old.J5P[frame]
    oldsig=member_signatures(oldpath);newsig=member_signatures(j5)
    reverse={v:k for k,v in oldsig.items()};mapping={k:reverse[v] for k,v in newsig.items() if v in reverse}
    original=pd.read_csv(oldpath/'global_defects.csv');required=set()
    for z in original.itertuples(index=False):
        x,y=int(z.source_bbox_x_global),int(z.source_bbox_y_global)
        w,h=int(z.source_bbox_width_px),int(z.source_bbox_height_px)
        if np.any((types[y:y+h,x:x+w]==2)|(types[y:y+h,x:x+w]==3)):required.add(str(z.global_defect_id))
    missing=required-set(mapping.values())
    base.write_json(out/'WORK_EDGE_membership_regression.json',{'required_objects':len(required),
        'missing_or_changed_membership':sorted(missing),'exact_match_count':len(mapping),
        'identity_basis':'EXACT_J4_LOCAL_MEMBER_SET_NOT_SEQUENTIAL_ID'})
    if missing:raise AssertionError('WORK/EDGE membership changed: '+str(sorted(missing)))
    audit=[];uidmap={}
    for r in records:
        current=r['source_local_id'];oldid=mapping.get(current)
        uid=r['candidate_source_uid']
        newuid=f'J5:F{frame}:{oldid}' if oldid else f'CURRENT_J5:F{frame}:{current}'
        uidmap[uid]=newuid;r['candidate_source_uid']=newuid
        r['historical_global_defect_id']=oldid or ''
        r['execution_disposition']='FRESH_EXACT_HISTORICAL_MEMBERS' if oldid else 'FRESH_PARTIAL_ROI_OBJECT'
        audit.append({'current_id':current,'historical_id':oldid or '', 'exact_member_set':bool(oldid)})
    for z in selected:z['sources']={uidmap[u] for u in z['sources']}
    pd.DataFrame(audit).to_csv(out/'J5_current_to_historical_identity.csv',index=False,encoding='utf-8-sig')
    return records,selected


def run_raw(path,run_id=None,mode=None):
    mode=mode or C.TWO_LEVEL_ROI['default_mode']
    if mode not in ('full','roi-j4','roi-bh'):raise ValueError('invalid mode')
    path=Path(path).resolve()
    if not path.is_file() or path.stat().st_size!=C.RAW_HEIGHT*C.RAW_WIDTH*2:raise ValueError('Configured RAW format/byte count required')
    name=run_id or 'TWO_LEVEL_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    if Path(name).name!=name:raise ValueError('run-id must be one directory name')
    out=C.OUTPUT_ROOT/name;out.mkdir(exist_ok=False)
    start=time.perf_counter();times={};input_hash=base.sha(path)
    base.write_json(out/'input.json',{'path':str(path),'SHA256':input_hash,'shape':[C.RAW_HEIGHT,C.RAW_WIDTH],'dtype':'>u2'})
    code=[ROOT/'main.py',ROOT/'config/user_config.py',*list((ROOT/'src').rglob('*.py')),*list((ROOT/'scripts').glob('*.py'))]
    base.write_json(out/'source_SHA256_at_start.json',[{'path':str(p),'sha256':base.sha(p)} for p in sorted(set(code))])
    raw=np.memmap(path,mode='r',dtype='>u2',shape=(C.RAW_HEIGHT,C.RAW_WIDTH))
    try:
        for y in range(0,raw.shape[0],512):
            if raw[y:y+512].max()>2**C.EFFECTIVE_BITS-1:raise ValueError('RAW exceeds bit depth')
        times['QC_seconds']=time.perf_counter()-start
        frame=1;known=None
        for f in (1,2):
            ref=C.DATA_ROOT/f'26 ({f}).raw'
            if ref.is_file() and input_hash==base.sha(ref):known=f;frame=f
        t=time.perf_counter()
        try:
            loc=base.locate_transmission_bands(raw,base.BandLocatorConfig())
            plan=build_plan(raw.shape,loc,force_full=mode=='full')
        except (ValueError,RuntimeError,TypeError,KeyError) as exc:
            loc={'bands':[],'status':'MANUAL_REVIEW_NO_BANDS','locator_exception':repr(exc)}
            plan=build_plan(raw.shape,loc,force_full=mode=='full')
            plan['fallback_reasons'].append('K8A_EXCEPTION: '+repr(exc))
        trusted=not plan['fallback_reasons']
        if trusted:
            types,ids=base.rasterize_region_masks(raw.shape,loc['bands'],loc['exterior'],base.BandLocatorConfig())
        else:
            # Unknown geometry is NOT a negative WORK mask. Full J5 is retained
            # for review; no fabricated K8B thresholds or approved empty result.
            types=np.zeros(raw.shape,np.uint8);ids=np.zeros(raw.shape,np.uint8)
        base.png(out/'region_type_fullres.png',types);base.png(out/'band_id_fullres.png',ids)
        base.write_json(out/'band_geometry.json',{k:v for k,v in loc.items() if k!='profile'})
        base.write_json(out/'detection_plan.json',plan)
        snapshot={'requested_mode':mode,'roi_mode':plan['roi_mode'],'fallback_reasons':plan['fallback_reasons'],
                  'two_level':C.TWO_LEVEL_ROI,'unified':C.UNIFIED_FINAL,'locator':asdict(base.BandLocatorConfig()),
                  'B':asdict(base.PerBandTrial()),'K8C':asdict(base.K8CConfig()),'K8D':asdict(base.K8DConfig()),'RAW':asdict(base.PilotConfig())}
        base.write_json(out/'config_snapshot.json',snapshot)
        times['K8A_plan_seconds']=time.perf_counter()-t
        print('TWO_LEVEL_PLAN',frame,mode,plan['roi_mode'],len(plan['tiles']),plan['fallback_reasons'],flush=True)
        fused,bhm=compute_fused(raw,out/'fused_blackhat.npy',plan['response_rectangles'] if mode=='roi-bh' and trusted else None)
        print('TWO_LEVEL_BH_COMPLETE',bhm,flush=True)
        saved=(J4.OUTROOT,J5.OUTPUT_ROOT);t=time.perf_counter()
        with (out/'J4_J5_execution.log').open('w',encoding='utf8') as log,redirect_stdout(log):
            try:
                J4.OUTROOT=out/'upstream_J4';J5.OUTPUT_ROOT=out/'upstream_J5'
                j4=J4.run('fresh',halo=C.CASE03J4_HALO_PX,save_images=False,input_raw_file=path,
                    input_fused_npy=out/'fused_blackhat.npy',frame_label=f'input_{frame}',
                    scheduled_tile_ids=[z['tile_id'] for z in plan['tiles']],
                    response_coverage='SCHEDULED_CONTEXT_ONLY' if mode=='roi-bh' and trusted else 'FULL_FRAME')
                times['J4_seconds']=time.perf_counter()-t;t=time.perf_counter()
                j5=J5.run('fresh',review_limit=0,input_J4_run=j4,input_raw_file=path,frame_label=f'input_{frame}')
                times['J5_seconds']=time.perf_counter()-t
            finally:J4.OUTROOT,J5.OUTPUT_ROOT=saved
        print('TWO_LEVEL_J4_J5_COMPLETE',frame,mode,flush=True);t=time.perf_counter()
        selected,jrecords=base.fresh_j5(raw,ids if trusted else np.ones(raw.shape,np.uint8),j4,j5,frame)
        if not trusted:
            for r in jrecords:
                r['band_id']=0;r['primary_visibility_layer']='GEOMETRY_UNKNOWN_FULL_FRAME_REVIEW'
            for z in selected:z['band']=0
        if known:jrecords,selected=reconcile_history(frame,j5,jrecords,selected,out,types)
        bdir=out/'upstream_K8BCD';bdir.mkdir()
        bs,brecords,_=base.fresh_b(raw,fused,ids,loc,bdir,frame) if trusted else ([],[],{})
        negative=[];historical=None
        if known:
            negative=base.negative_objects(known)
            history=base.old.I/f'frame26_{known}/end_to_end_candidate_lineage.csv'
            historical=pd.read_csv(history,low_memory=False)
            shutil.copy2(history,out/'HISTORICAL_ALL_SOURCE_LINEAGE_UNCHANGED.csv')
            base.write_json(out/'historical_archive_manifest.json',{'source':str(history),'SHA256':base.sha(history),
                'semantics':'HISTORICAL_ARCHIVE_NOT_FRESH_COMPUTATION','source_J4':str(base.old.J4P[frame]),'source_J5':str(base.old.J5P[frame])})
            approved=[z for z in base.old.build_b(known,historical)[0] if z['user_approved']]
            aps=set().union(*(z['sources'] for z in approved))
            bs=[z for z in bs if not z['sources']&aps and not any(base.old.global_intersection(z,n) for n in negative)]
            selected.extend(approved)
            if trusted:
                assert {r['candidate_source_uid'] for r in brecords}==set(historical[historical.stage=='K8B'].candidate_source_uid)
        selected+=bs;prior=list(selected)
        selected,recovery=base.recover_objects(selected,raw,ids,negative)
        final,edges=base.old.consolidate(selected)
        assert set().union(*(z['sources'] for z in prior))<=set().union(*(z['sources'] for z in final))
        pd.DataFrame(recovery).to_csv(out/'RAW_recovery_gate_audit.csv',index=False,encoding='utf-8-sig')
        pd.DataFrame(edges).to_csv(out/'association_edges.csv',index=False,encoding='utf-8-sig')
        summary=base.export(out,raw,final,jrecords+brecords,frame,negative)
        if historical is not None:
            fresh=pd.read_csv(out/'ALL_SOURCE_DISPOSITIONS.csv');lookup=fresh.set_index('candidate_source_uid')
            audit=historical.copy();audit['execution_disposition']=[
                'FRESH_REPRODUCED' if u in lookup.index else 'HISTORICAL_PRESERVED_NOT_RESCANNED_OR_ROI_BOUNDARY_CHANGED'
                for u in audit.candidate_source_uid]
            ownership={u:f'F{frame}_FINAL_{i:04d}' for i,z in enumerate(final,1) for u in z['sources']}
            audit['current_final_ID']=[ownership.get(u,'') for u in audit.candidate_source_uid]
            audit.to_csv(out/'ALL_HISTORICAL_SOURCE_DISPOSITIONS_NO_DROP.csv',index=False,encoding='utf-8-sig')
        times['K8_final_export_seconds']=time.perf_counter()-t
        assert base.sha(path)==input_hash
        status=json.loads((j4/'run_status.json').read_text(encoding='utf8'))
        result={'status':'ENGINEERING_OUTPUT_PENDING_INDEPENDENT_QA' if trusted else 'FULL_FRAME_FALLBACK_MANUAL_GEOMETRY_REVIEW_REQUIRED',
            'requested_mode':mode,'roi_mode':plan['roi_mode'],'fallback_reasons':plan['fallback_reasons'],
            'full_tiles':plan['full_tiles'],'planned_tiles':len(plan['tiles']),'actual_fresh_J4_tiles':status['completed_tiles'],
            'skipped_tiles':plan['skipped_tiles'],'legal_source_pixels':plan['legal_source_pixels'],
            'J4_RAW_window_pixels_with_repeats':plan['J4_RAW_window_pixels_with_repeats'],
            'RAW_frame_pixels':int(raw.size),
            'high_cost_RAW_pixel_visits_BH_plus_J4':bhm['blackhat_input_pixels_with_repeats']+plan['J4_RAW_window_pixels_with_repeats'],
            'peak_working_set_bytes':peak_memory_bytes(),'RAW_unchanged':True,
            'elapsed_seconds':time.perf_counter()-start,'K8B_executed':trusted,**bhm,**times,**summary}
        base.write_json(out/'acceptance.json',result);print('TWO_LEVEL_COMPLETE',str(out),result,flush=True)
        return out
    except BaseException as exc:
        base.write_json(out/'FAILED.json',{'error':repr(exc),'elapsed_seconds':time.perf_counter()-start});raise


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--input',required=True,type=Path);p.add_argument('--run-id')
    p.add_argument('--mode',choices=['full','roi-j4','roi-bh'],default=None)
    a=p.parse_args();run_raw(a.input,a.run_id,a.mode)
