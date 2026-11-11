"""Consume historical RAW proposals by explicit safety state and pixel checks."""
from pathlib import Path
import numpy as np
import pandas as pd
from config import user_config as C

def select_proposals(frame,objects,lineage,negative_masks):
    from scripts import run_case03_unified_final_detector_26_1_2 as old
    from scripts.run_case03k8i_stage2_fullband_priority_contours import K8D,PRIOR
    proposals=[];audit=[]
    # Earlier K8I priority results were also absent from the v2 consumer.
    t=pd.read_csv(PRIOR/f'frame26_{frame}/all_NOT_PREVIOUSLY_PROCESSED_NOVEL_MEDLARGE_K8D_trials.csv')
    for r in t.to_dict('records'):
        label=int(r['B_label']);band=int(r['band_id'])
        p=PRIOR/f'frame26_{frame}/band{band:02d}/F{frame}_B{band}_C{label:05d}_NEW_RAW_trial_all_masks.npz'
        proposals.append((f'B:F{frame}:B{band:02d}:C{label:07d}',p,'K8I_K8D_review_outer','original_RAW_roi_xyxy',str(r.get('status',r.get('K8D_review_status','')))))
    t=pd.read_csv(old.II/f'frame26_{frame}/new_evidence_RAW_trial_results.csv')
    for r in t.to_dict('records'):
        proposals.append((r['source_UID'],Path(str(r['new_NPZ'])),'new_full_RAW_review_outer','RAW_roi_global_xyxy',str(r['stage2_review_status'])))
    for uid,p,mkey,bkey,status in proposals:
        row={'source_uid':uid,'prior_mask_path':str(p),'proposal_status':status,'accepted':False}
        matches=[i for i,z in enumerate(objects) if uid in z['sources']]
        if not status.startswith('STABLE_'):
            row['decision_reason']='RAW_PROPOSAL_NOT_STABLE';audit.append(row);continue
        if len(matches)!=1:
            row['decision_reason']='NO_UNIQUE_ALREADY_SELECTED_SOURCE_OR_APPROVAL_REQUIRED';audit.append(row);continue
        i=matches[0];before=objects[i]
        if before['user_approved']:
            row['decision_reason']='IMMUTABLE_HUMAN_CONFIRMED_MASK';audit.append(row);continue
        mask,box=old.unpack(p,mkey,bkey)
        candidate=old.item(mask,box,'B_STABLE_RAW_PROPOSAL',before['sources'],before['band'],False,'STABLE_RAW_PROPOSAL_CONSUMED_WITH_PIXEL_SAFETY',2)
        row.update(prior_area_px2=int(before['mask'].sum()),proposal_area_px2=int(mask.sum()))
        if old.global_intersection(candidate,before)!=int(before['mask'].sum()):
            row['decision_reason']='SOURCE_PIXEL_LOSS';audit.append(row);continue
        if mask.sum()>C.UNIFIED_FINAL['max_raw_growth_ratio']*before['mask'].sum():
            row['decision_reason']='GROWTH_LIMIT';audit.append(row);continue
        if any(old.global_intersection(candidate,z) for j,z in enumerate(objects) if j!=i) or any(old.global_intersection(candidate,z) for z in negative_masks):
            row['decision_reason']='OTHER_OBJECT_OR_USER_NEGATIVE_OVERLAP';audit.append(row);continue
        objects[i]=candidate
        row.update(accepted=True,decision_reason=candidate['reason']);audit.append(row)
    return objects,audit
