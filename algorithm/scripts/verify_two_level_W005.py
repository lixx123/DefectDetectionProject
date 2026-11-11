"""Separate NONWORK scratch diagnostic; not a production ROI exception."""
from pathlib import Path
import sys,json
from contextlib import redirect_stdout
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from config import user_config as C
from scripts import run_case03j4_fullscan as J4,run_case03j5_global_merge as J5
from scripts.run_two_level_unified import member_signatures
from scripts.run_unified_final_revision import write_json


def run(full,output):
    full=Path(full);out=Path(output);out.mkdir(exist_ok=False)
    # Fixed coordinates are solely a posterior diagnostic test, never seeds,
    # fitting data or an exception added to the production workband plan.
    task=[t for t in J4.tiles((C.RAW_HEIGHT,C.RAW_WIDTH)) if 3<=t['iy']<=5 and 10<=t['ix']<=13]
    saved=J4.OUTROOT,J5.OUTPUT_ROOT
    with (out/'execution.log').open('w',encoding='utf8') as log,redirect_stdout(log):
        try:
            J4.OUTROOT=out/'J4';J5.OUTPUT_ROOT=out/'J5'
            j4=J4.run('diagnostic',save_images=False,input_raw_file=C.DATA_ROOT/'26 (1).raw',
                input_fused_npy=full/'fused_blackhat.npy',scheduled_tile_ids=[t['tile_id'] for t in task])
            j5=J5.run('diagnostic',review_limit=0,input_J4_run=j4,input_raw_file=C.DATA_ROOT/'26 (1).raw')
        finally:J4.OUTROOT,J5.OUTPUT_ROOT=saved
    diff=0
    for t in task:
        p=t['tile_id']+'.npz'
        with np.load(j4/'tile_masks'/p) as a,np.load(full/'upstream_J4/fresh/tile_masks'/p) as b:
            diff+=sum(int(np.count_nonzero(a[k]!=b[k])) for k in a.files)
    oldsig=member_signatures(full/'upstream_J5/fresh');new=member_signatures(j5)
    oldid='DEFECT_07328';matches=[k for k,v in new.items() if v==oldsig[oldid]]
    assert len(matches)==1 and diff==0
    a=pd.read_csv(full/'upstream_J5/fresh/global_defects.csv').set_index('global_defect_id').loc[oldid]
    b=pd.read_csv(j5/'global_defects.csv').set_index('global_defect_id').loc[matches[0]]
    columns=['source_area_px2','source_max_feret_px','source_bbox_x_global','source_bbox_y_global','source_bbox_width_px','source_bbox_height_px']
    deltas={k:float(b[k])-float(a[k]) for k in columns};assert all(v==0 for v in deltas.values())
    result={'status':'PASS','scope':'SEPARATE_NONWORK_DIAGNOSTIC_NOT_PRODUCTION_ROI',
        'fresh_J4_tiles':len(task),'all_J4_array_different_pixels':diff,'historical_ID':oldid,
        'diagnostic_ID':matches[0],'measurement_deltas':deltas,'source_area_px2':int(b.source_area_px2),
        'member_set_exact':True,'final_WORK_image_inclusion_not_asserted':True,
        'BH_source':str(full/'fused_blackhat.npy'),'BH_reused_explicitly':True}
    write_json(out/'QA.json',result);print(result,flush=True)
    return result


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--full',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.full,a.output)
