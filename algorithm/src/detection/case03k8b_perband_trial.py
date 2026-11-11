"""Case03-K8-B read-only, label-free, work-band-specific threshold comparison.

INPUT: original RAW, unmodified full-frame fused BlackHat, K8-A *approved*
WORK_CORE masks. Branches:
 A FIXED: per-band WORK segmentation with original 170/230 hysteresis.
 B ADAPT: calibrate the 170/230 sigma-scores from the work band with
   strongest median RAW illumination in that frame; transfer these scores
   to each individual band's robust fused-BH (median+1.4826*MAD).
Exact same BlackHat kernel and source data; never fill mask before morphology.
Results are seed hypotheses, NOT fully classified J5 defects.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np,cv2


@dataclass(frozen=True)
class PerBandTrial:
    original_low_dn:float=170.0
    original_high_dn:float=230.0
    robust_sample_stride_px:int=8
    blackhat_halo_px:int=32
    min_sigma_dn:float=2.0
    absolute_low_floor_dn:float=25.0
    absolute_high_floor_dn:float=35.0
    min_high_low_gap_dn:float=8.0
    minimum_hysteresis_connected_area_px:int=1
    # This trial DOES NOT claim all candidates are true physical defects.


def stats_median_mad(arr:np.ndarray,minimum_sigma:float)->dict:
    vals=np.asarray(arr,np.float64).reshape(-1)
    if len(vals)<100:raise ValueError("Not enough work band pixels")
    median=float(np.median(vals))
    sig=max(minimum_sigma,float(1.4826*np.median(np.abs(vals-median))))
    return {
      "blackhat_background_median_dn":round(median,5),
      "blackhat_background_MADsigma_dn":round(sig,5),
      "count":int(len(vals)),
      "blackhat_p90_dn":round(float(np.percentile(vals,90)),4),
      "blackhat_p99_dn":round(float(np.percentile(vals,99)),4),
      "blackhat_p999_dn":round(float(np.percentile(vals,99.9)),4)
    }


def threshold_params(perband_stats:dict[int,dict],
                     detector:PerBandTrial,reference_id:int)->dict[int,dict]:
    if reference_id not in perband_stats:raise ValueError("Missing reference workband")
    src=perband_stats[reference_id]
    z_low=(detector.original_low_dn-src["blackhat_background_median_dn"])/src["blackhat_background_MADsigma_dn"]
    z_high=(detector.original_high_dn-src["blackhat_background_median_dn"])/src["blackhat_background_MADsigma_dn"]
    if z_low<=0 or z_high<=z_low:
        raise ValueError("Invalid anchor sigma scores; reject trial")
    result={}
    for i,stats in sorted(perband_stats.items()):
        median=stats["blackhat_background_median_dn"]
        sigma=stats["blackhat_background_MADsigma_dn"]
        if i==reference_id:
            low=detector.original_low_dn
            high=detector.original_high_dn
        else:
            low=max(detector.absolute_low_floor_dn,median+z_low*sigma)
            high=max(detector.absolute_high_floor_dn,median+z_high*sigma,
                     low+detector.min_high_low_gap_dn)
        result[i]={
          **stats,
          "reference_id":reference_id,
          "reference_z_low":round(z_low,7),
          "reference_z_high":round(z_high,7),
          "fixed_low_dn":detector.original_low_dn,
          "fixed_high_dn":detector.original_high_dn,
          "band_trial_low_dn":round(float(low),4),
          "band_trial_high_dn":round(float(high),4),
          "threshold_method":"ANCHOR_ROBUST_Z_TRANSFER_NOT_APPROVED_FOR_PRODUCTION",
          "no_human_label_used":True,
        }
    return result


def hysteresis_on_work(response:np.ndarray,work:np.ndarray,
                       low:float,high:float,
                       minimum_area:int=1)->tuple[np.ndarray,dict]:
    """Single WORK band core mask. Connected low objects must have high pixel.

    WARNING: this is a transparent H170/230 detection comparison only, not
    full production G/H/J4/J5 refinement or object joining.
    """
    if response.shape!=work.shape or response.ndim!=2:
        raise ValueError("Array shape mismatch")
    if response.dtype!=np.uint16:raise ValueError("BlackHat expects uint16")
    if work.dtype!=np.bool_:raise ValueError("work core must be bool")
    if low<=0 or high<=low or minimum_area<1:raise ValueError("bad thresholds")
    lowpix=(response>=low)&work
    highpix=(response>=high)&work
    n,lab,stats,centroids=cv2.connectedComponentsWithStats(
        lowpix.astype(np.uint8),connectivity=8,ltype=cv2.CV_32S)
    seed_ids=np.unique(lab[highpix])
    seed_ids=seed_ids[seed_ids>0]
    accept=np.zeros(n,bool)
    accept[seed_ids]=True
    if minimum_area>1:
        accept[stats[:,cv2.CC_STAT_AREA]<minimum_area]=False
    accept[0]=False
    out=accept[lab]
    assert not np.any(out&~work)
    assert not np.any(out&~lowpix)
    if n==1:areas=np.zeros(0,int)
    else:areas=stats[1:,cv2.CC_STAT_AREA]
    selected_ids=np.flatnonzero(accept)
    return out,{
      "low_threshold_px":int(np.count_nonzero(lowpix)),
      "high_seed_pixels":int(np.count_nonzero(highpix)),
      "low_connected_components":int(n-1),
      "seeded_components_all_sizes":int(len(seed_ids)),
      "hysteresis_candidate_components":int(len(selected_ids)),
      "hysteresis_candidate_pixels":int(out.sum()),
      "hysteresis_candidate_ge3":int(np.count_nonzero(stats[selected_ids,cv2.CC_STAT_AREA]>=3)),
      "hysteresis_candidate_ge10":int(np.count_nonzero(stats[selected_ids,cv2.CC_STAT_AREA]>=10)),
      "hysteresis_candidate_ge40":int(np.count_nonzero(stats[selected_ids,cv2.CC_STAT_AREA]>=40)),
      "largest_candidate_area_px2":int(np.max(stats[selected_ids,cv2.CC_STAT_AREA])) if len(selected_ids) else 0,
      "max_original_response_in_mask":int(response[work].max()) if work.any() else 0,
      "not_j5_verified_true_defect":True
    }
