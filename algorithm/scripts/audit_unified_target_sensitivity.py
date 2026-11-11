"""Development sensitivity evidence, not an independent accuracy estimate."""
from pathlib import Path
import sys,json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import run_case03_unified_final_detector_26_1_2 as old
from scripts.run_unified_final_revision import K8A,read_png,write_json
from src.detection.unified_raw_recovery import recover_objects

def main():
    dest=ROOT/'outputs/UNIFIED_REVIEW_20261019_v1/TARGET_SENSITIVITY'
    dest.mkdir(exist_ok=False)
    rows=pd.read_csv(old.I/'frame26_1/end_to_end_candidate_lineage.csv',low_memory=False)
    objects=[v for v in old.build_b(1,rows)[0] if v['band']==2 and not v['user_approved']]
    raw=np.memmap(old.C.DATA_ROOT/'26 (1).raw',mode='r',dtype='>u2',shape=(9200,11276))
    ids=read_png(K8A/'frame26_1/band_id_fullres.png');results=[]
    for scale in (12.,16.,20.):
        for sigma in (2.75,3.,3.25):
            cfg=dict(old.C.UNIFIED_FINAL,recovery_line_background_sigma_px=scale,recovery_sigma_multiplier=sigma)
            final,audit=recover_objects(objects,raw,ids,config=cfg)
            record={'background_sigma_px':scale,'noise_multiplier':sigma,'objects':len(final),
                    'area':sum(int(z['mask'].sum()) for z in final),'accepted':audit[0]['accepted'],'reason':audit[0]['reason']}
            results.append(record)
    pd.DataFrame(results).to_csv(dest/'parameter_sensitivity.csv',index=False,encoding='utf-8-sig')
    write_json(dest/'interpretation.json',{'development_target_only':True,'parameters_in_main_unchanged':True,
                 'all_variants_single_object':all(r['objects']==1 for r in results),'not_true_boundary_accuracy':True})
    print(pd.DataFrame(results).to_string(index=False))

if __name__=='__main__':main()
