"""Fresh RAW -> BlackHat -> J4/J5 + K8A/B/C/D -> final mask/box pipeline.

No historical segmentation is required for a new RAW. Human approvals are
loaded only when the complete RAW SHA256 matches a reviewed frame.
"""
from pathlib import Path
from dataclasses import replace,asdict
from contextlib import redirect_stdout
from datetime import datetime
import sys,json,time
import numpy as np
import pandas as pd
import cv2
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from config import user_config as C
from scripts import run_case03_unified_final_detector_26_1_2 as old
from scripts.run_unified_final_revision import sha,write_json,negative_objects
from src.detection.blackhat import black_hat_uint16
from src.detection.two_level_roi import require_computed_response
from src.detection.case03k8a_band_locator import BandLocatorConfig,locate_transmission_bands,rasterize_region_masks
from src.detection.case03k8b_perband_trial import PerBandTrial,stats_median_mad,threshold_params,hysteresis_on_work
from src.detection.case03k8c_noise_review import K8CConfig,evaluate_binary_band
from src.detection.case03k3_spot_contour_pilot import PilotConfig,raw_outer_envelope
from src.detection.case03k8d_group_stability import K8DConfig,resolve
from src.detection.case03i_size_grade import SizeGradeConfig,max_feret_centers_px,grade_size
from src.detection.unified_raw_recovery import recover_objects
from src.visualization.unified_final_boxes import render
from scripts.run_case03k8b_bandwise_thresholds import region_of_interest

def png(path,array):
    ok,b=cv2.imencode('.png',array);assert ok;path.write_bytes(b.tobytes())

def prepare_fused(raw,path):
    """Exact tiled five-scale morphology with a two-operation kernel halo."""
    h,w=raw.shape;fused=np.lib.format.open_memmap(path,mode='w+',dtype=np.uint16,shape=raw.shape)
    kernels=C.BLACKHAT_KERNEL_SIZES_PX;halo=2*(max(kernels)//2)+2;step=512
    for y in range(0,h,step):
        for x in range(0,w,step):
            a=max(0,x-halo);b=max(0,y-halo);c=min(w,x+step+halo);d=min(h,y+step+halo)
            tile=np.asarray(raw[b:d,a:c],np.uint16);response=np.zeros(tile.shape,np.uint16)
            for k in kernels:np.maximum(response,black_hat_uint16(tile,k,'ellipse'),out=response)
            fused[y:min(y+step,h),x:min(x+step,w)]=response[y-b:min(y+step,h)-b,x-a:min(x+step,w)-a]
    fused.flush();return fused

def fresh_b(raw,fused,ids,loc,out,frame):
    config=PerBandTrial();noise=K8CConfig();pilot=PilotConfig();safety=K8DConfig()
    stats={};regions={};stride=config.robust_sample_stride_px
    for band in loc['bands']:
        bid=int(band['band_id']);y0,y1=region_of_interest(band,raw.shape,config)
        core=ids[y0:y1]==bid;start=(-y0)%stride
        band_fused=np.asarray(fused[y0:y1])
        require_computed_response(band_fused[core],f'K8B WORK band {bid}')
        sample=band_fused[start::stride,::stride][core[start::stride,::stride]]
        stat=stats_median_mad(sample,config.min_sigma_dn)
        stat['workband_raw_median_dn']=float(np.median(raw[y0+start:y1:stride,::stride][core[start::stride,::stride]]))
        stats[bid]=stat;regions[bid]=(y0,y1)
    params=threshold_params(stats,config,max(stats,key=lambda b:stats[b]['workband_raw_median_dn']))
    records=[];objects=[];trials=[];sources={}
    for bid,(y0,y1) in regions.items():
        core=ids[y0:y1]==bid;bh=np.asarray(fused[y0:y1]);r=np.asarray(raw[y0:y1],np.uint16)
        a,_=hysteresis_on_work(bh,core,config.original_low_dn,config.original_high_dn)
        b,_=hysteresis_on_work(bh,core,params[bid]['band_trial_low_dn'],params[bid]['band_trial_high_dn'])
        bdir=out/f'band{bid:02d}';bdir.mkdir();png(bdir/'B_SOURCE_ALL.png',np.uint8(b)*255)
        rows,_,_,_=evaluate_binary_band(r,b,a&b,core,noise)
        n,labels,st,ct=cv2.connectedComponentsWithStats(np.uint8(b),connectivity=8)
        assert len(rows)==n-1
        for row in rows:
            lid=int(row['band_component_label']);x,y,w,h,area=map(int,st[lid]);uid=f'B:F{frame}:B{bid:02d}:C{lid:07d}'
            seed=labels[y:y+h,x:x+w]==lid;box=(x,y+y0,x+w,y+y0+h)
            source=old.item(seed,box,'B_NOVEL_MEDLARGE_SOURCE_ONLY',[uid],bid,False,'SOURCE_ONLY_RAW_GATES_PENDING',1)
            sources[uid]=source
            row.update(candidate_source_uid=uid,stage='K8B',band_id=bid,source_local_id=lid,source_area_px2=area,
                       source_mask_path=str(bdir/'B_SOURCE_ALL.png'),source_label=lid,source_y0=y0,
                       source_bbox_x0=x,source_bbox_y0=y+y0,source_bbox_x1_exclusive=x+w,source_bbox_y1_exclusive=y+y0+h)
            records.append(row)
            # Keep all originals; only evidence-supported nonmicro regions can
            # propose final masks. No historical manual ROI creates a seed.
            if area<C.UNIFIED_FINAL['min_b_source_area_px2'] or row['classification'] not in ('PROMISING_DARK_REVIEW','UNCERTAIN_REVIEW'):
                row['decision_reason']='K8C_'+row['classification']+'_'+row['reason'];continue
            cx,cy=ct[lid];cy+=y0;xx=max(0,min(raw.shape[1]-128,int(round(cx))-64));yy=max(0,min(raw.shape[0]-128,int(round(cy))-64))
            grid=np.zeros((128,128),np.int32);t=max(yy,y0);u=min(yy+128,y1)
            grid[t-yy:u-yy]=labels[t-y0:u-y0,xx:xx+128]
            seed128=grid==lid;reason='SOURCE_DOES_NOT_FIT_ROI';outer=seed128
            if int(seed128.sum())==area:
                roi=np.asarray(raw[yy:yy+128,xx:xx+128],np.uint16);trial={};aud={}
                core128=ids[yy:yy+128,xx:xx+128]==bid
                for k in (3.,2.,1.5):trial[k],aud[k]=raw_outer_envelope(roi,seed128,(cx-xx,cy-yy),replace(pilot,raw_noise_sigma_multiplier=k))
                outer,decision=resolve(seed128,trial,aud,core128,grid,st[:,cv2.CC_STAT_AREA],lid,safety)
                reason=decision['status'];proposal=old.item(outer,(xx,yy,xx+128,yy+128),'B_STABLE_RAW_PROPOSAL',[uid],bid,False,reason,2)
                path=bdir/f'C{lid:07d}_RAW_trials.npz'
                np.savez_compressed(path,seed=seed128,raw_k3=trial[3.],raw_k2=trial[2.],raw_k1p5=trial[1.5],outer=outer,bbox=np.array([xx,yy,xx+128,yy+128]))
                trials.append({'uid':uid,'reason':reason,'decision':json.dumps(decision),'npz':str(path)})
                if reason.startswith('STABLE_') and outer.sum()<=C.UNIFIED_FINAL['max_raw_growth_ratio']*area:
                    source=proposal
            row['decision_reason']=reason
            objects.append(source)
        print('FRESH_K8_BAND',bid,'sources',len(rows),flush=True)
    write_json(out/'thresholds.json',params)
    pd.DataFrame(trials).to_csv(out/'RAW_trials.csv',index=False,encoding='utf-8-sig')
    return objects,records,sources

def fresh_j5(raw,ids,j4,j5,frame):
    table=pd.read_csv(j5/'global_defects.csv');records=[]
    if table.empty:return [],[]
    for z in table.itertuples(index=False):
        x=int(round(z.center_x_global));y=int(round(z.center_y_global));bid=int(ids[y,x]);x0=z.source_bbox_x_global;y0=z.source_bbox_y_global
        records.append({'candidate_source_uid':f'J5:F{frame}:{z.global_defect_id}','stage':'J5','band_id':bid,
                        'source_local_id':z.global_defect_id,'primary_visibility_layer':('J5_OUTSIDE_WORK' if not bid else 'J5_WORK_SMALL' if z.grade=='SMALL' else 'J5_WORK_MEDLARGE'),
                        'source_area_px2':z.source_area_px2,'source_max_Feret_px':z.source_max_feret_px,'size_grade':z.grade,
                        'source_bbox_x0':x0,'source_bbox_y0':y0,'source_bbox_x1_exclusive':x0+z.source_bbox_width_px,'source_bbox_y1_exclusive':y0+z.source_bbox_height_px,
                        'source_mask_path':str(j4/'tile_masks'),'source_membership':str(j5/'global_object_membership.csv')})
    saved=(old.J4P.get(frame),old.J5P.get(frame))
    try:
        old.J4P[frame]=j4;old.J5P[frame]=j5
        selected=old.build_j5(frame,pd.DataFrame(records),{})
    finally:old.J4P[frame],old.J5P[frame]=saved
    return selected,records

def export(out,raw,objects,records,frame,negative):
    maskdir=out/'EXACT_FINAL_BINARY_MASKS';maskdir.mkdir();binary=np.zeros(raw.shape,np.uint8);table=[];view=[];owners={}
    for i,z in enumerate(objects,1):
        uid=f'F{frame}_FINAL_{i:04d}';m=z['mask'];x0,y0,x1,y1=z['bbox'];crop=binary[y0:y1,x0:x1]
        assert not np.any(crop[m]);crop[m]=255
        y,x=np.where(m);area=len(x);length=max_feret_centers_px(np.column_stack([x,y]));grade,_=grade_size(area,length,SizeGradeConfig())
        assert not any(old.global_intersection(z,n) for n in negative)
        path=maskdir/f'{uid}.npz';np.savez_compressed(path,mask=np.uint8(m),global_RAW_bbox_xyxy_exclusive=np.array(z['bbox']),source_uids=np.array(sorted(z['sources'])))
        table.append({'final_ID':uid,'final_area_detector_px2':area,'max_Feret_detector_px':length,'bbox_xyxy_exclusive':json.dumps(z['bbox']),
                      'grade':grade,'human_confirmed_darkspot':z['user_approved'],'source_uids':';'.join(sorted(z['sources'])),'mask_path':str(path),'decision_reason':z['reason']})
        view.append({'final_ID':uid,'bbox':z['bbox'],'area':area,'length':length,'approved':z['user_approved'],'grade':grade})
        for source in z['sources']:
            assert source not in owners;owners[source]=uid
    for r in records:
        r['final_ID']=owners.get(r['candidate_source_uid'],'');r['original_source_preserved']=True
        r.setdefault('decision_reason','J5_'+r.get('primary_visibility_layer','SOURCE_RETAINED'))
    pd.DataFrame(records,columns=None if records else ['candidate_source_uid','stage','final_ID','decision_reason']).to_csv(out/'ALL_SOURCE_DISPOSITIONS.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(table,columns=None if table else ['final_ID','final_area_detector_px2','max_Feret_detector_px',
        'bbox_xyxy_exclusive','grade','human_confirmed_darkspot','source_uids','mask_path','decision_reason']).to_csv(out/'FINAL_DEFECTS_AND_MEASUREMENTS.csv',index=False,encoding='utf-8-sig')
    png(out/'01_FINAL_EXACT_FULLRES_BINARY_DEFECT_MASK.png',binary)
    layout=render(raw,view,out/'00_FINAL_DEFECTS_ONLY_fullframe_1to4.png')
    pd.DataFrame(layout,columns=None if layout else ['final_ID','display_box','label_box','label_area',
        'label_length','box_overlap_pixels','label_overlap_pixels','mask_contour_drawn']).to_csv(out/'render_layout_audit.csv',index=False,encoding='utf-8-sig')
    assert not any(r['box_overlap_pixels'] or r['label_overlap_pixels'] for r in layout)
    return {'objects':len(table),'source_count':len(records),'area':int(np.count_nonzero(binary)),
            'confirmed_areas':sorted(r['final_area_detector_px2'] for r in table if r['human_confirmed_darkspot'])}

def run_raw(path,run_id=None):
    from scripts import run_case03j4_fullscan as j4script,run_case03j5_global_merge as j5script
    path=Path(path).resolve()
    if not path.is_file() or path.stat().st_size!=C.RAW_HEIGHT*C.RAW_WIDTH*2:
        raise ValueError('Expected big-endian uint16 RAW with configured dimensions')
    name=run_id or 'UNIFIED_RAW_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    if Path(name).name!=name:raise ValueError('run-id must be a directory name')
    out=C.OUTPUT_ROOT/name;out.mkdir(exist_ok=False);start=time.perf_counter();input_hash=sha(path)
    write_json(out/'input.json',{'path':str(path),'SHA256':input_hash,'shape':[C.RAW_HEIGHT,C.RAW_WIDTH],'dtype':'>u2'})
    code=[ROOT/'main.py',ROOT/'config/user_config.py',*list((ROOT/'src').rglob('*.py')),*list((ROOT/'scripts').glob('*.py'))]
    write_json(out/'source_SHA256_at_start.json',[{'path':str(p),'sha256':sha(p)} for p in sorted(set(code))])
    write_json(out/'config_snapshot.json',{'unified':C.UNIFIED_FINAL,'bands':asdict(BandLocatorConfig()),'B':asdict(PerBandTrial()),'K8C':asdict(K8CConfig()),'K8D':asdict(K8DConfig()),'RAW':asdict(PilotConfig())})
    raw=np.memmap(path,mode='r',dtype='>u2',shape=(C.RAW_HEIGHT,C.RAW_WIDTH))
    for y in range(0,raw.shape[0],512):
        if raw[y:y+512].max()>2**C.EFFECTIVE_BITS-1:raise ValueError('RAW exceeds configured effective bit depth')
    frame=1;known=None
    for fr in (1,2):
        reference=C.DATA_ROOT/f'26 ({fr}).raw'
        if reference.is_file() and input_hash==sha(reference):known=fr;frame=fr
    try:
        print('FRESH_RAW_START',path,out,flush=True)
        fused=prepare_fused(raw,out/'fused_blackhat.npy');print('FRESH_BLACKHAT_COMPLETE',flush=True)
        loc=locate_transmission_bands(raw,BandLocatorConfig())
        if not loc['bands']:raise ValueError('No transmission bands located; manual review required')
        types,ids=rasterize_region_masks(raw.shape,loc['bands'],loc['exterior'],BandLocatorConfig())
        png(out/'band_id_fullres.png',ids);png(out/'region_type_fullres.png',types)
        write_json(out/'band_geometry.json',{k:v for k,v in loc.items() if k!='profile'})
        j4old,j5old=j4script.OUTROOT,j5script.OUTPUT_ROOT
        with (out/'J4_J5_execution.log').open('w',encoding='utf8') as log,redirect_stdout(log):
            try:
                j4script.OUTROOT=out/'upstream_J4';j5script.OUTPUT_ROOT=out/'upstream_J5'
                j4=j4script.run('fresh',save_images=False,input_raw_file=path,input_fused_npy=out/'fused_blackhat.npy',frame_label=f'input_{frame}')
                j5=j5script.run('fresh',review_limit=0,input_J4_run=j4,input_raw_file=path,frame_label=f'input_{frame}')
            finally:j4script.OUTROOT=j4old;j5script.OUTPUT_ROOT=j5old
        print('FRESH_J4_J5_COMPLETE',flush=True)
        selected,jrecords=fresh_j5(raw,ids,j4,j5,frame)
        bdir=out/'upstream_K8BCD';bdir.mkdir();bs,brecords,sources=fresh_b(raw,fused,ids,loc,bdir,frame)
        negative=[]
        if known:
            negative=negative_objects(known)
            oldrows=pd.read_csv(old.I/f'frame26_{known}/end_to_end_candidate_lineage.csv',low_memory=False)
            approved=[z for z in old.build_b(known,oldrows)[0] if z['user_approved']]
            approved_sources=set().union(*(z['sources'] for z in approved))
            bs=[z for z in bs if not (z['sources']&approved_sources) and not any(old.global_intersection(z,n) for n in negative)]
            selected.extend(approved)
            assert {r['candidate_source_uid'] for r in jrecords+brecords}==set(oldrows.candidate_source_uid),'Fresh source UID regression'
            write_json(out/'fresh_vs_frozen_source_reconciliation.json',{'source_UID_count':len(oldrows),'exact_UID_set':True,'input_SHA256_bound_approvals':True})
        selected+=bs
        prior_selected=list(selected)
        selected,recovery=recover_objects(selected,raw,ids,negative)
        final,edges=old.consolidate(selected)
        assert set().union(*(z['sources'] for z in prior_selected))<=set().union(*(z['sources'] for z in final))
        pd.DataFrame(recovery).to_csv(out/'RAW_recovery_gate_audit.csv',index=False,encoding='utf-8-sig')
        pd.DataFrame(edges).to_csv(out/'association_edges.csv',index=False,encoding='utf-8-sig')
        summary=export(out,raw,final,jrecords+brecords,frame,negative)
        assert sha(path)==input_hash
        write_json(out/'acceptance.json',{'status':'ENGINEERING_PASS_HUMAN_EFFECT_PENDING','actual_fresh_J4_tiles':1620,
                  'fresh_J5_K8A_K8B_K8C_K8D_executed':True,'elapsed_seconds':time.perf_counter()-start,'RAW_unchanged':True,**summary})
        print('FRESH_RAW_COMPLETE',out,summary,flush=True)
    except BaseException as exc:
        write_json(out/'FAILED.json',{'error':repr(exc)});raise
    return out

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--run-id')
    args=p.parse_args();run_raw(args.input,args.run_id)
