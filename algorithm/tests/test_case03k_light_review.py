"""K0 sampling + split-view invariants (no manual ground truth claimed)."""
from pathlib import Path
import numpy as np,pandas as pd
from scripts.prepare_case03k_light_review import area_stratum,choose_small,STRATA
from scripts.export_case03j5_split_views import draw_base


def test_area_strata_cover_every_possible_green_area():
    assert [area_stratum(k) for k in (1,2,3,4,7,8,39)]==[
      STRATA[0],STRATA[1],STRATA[1],STRATA[2],STRATA[2],STRATA[3],STRATA[3]]


def test_seeded_small_selection_no_duplicates_and_geometry():
    rng=np.random.default_rng(20261012)
    # 4 very separated candidate regions per area stratum.
    entries=[]
    for group,area in enumerate((1,2,4,8)):
        for i in range(8):
            entries.append({
                "grade":"SMALL","source_area_px2":area,
                "center_x_global":400+i*180+group*22,
                "center_y_global":400+group*180+i*180,
                "global_defect_id":f"D_{group}_{i}"
            })
    result=choose_small(pd.DataFrame(entries),rng,n_per=4)
    assert len(result)==16
    assert result.global_defect_id.is_unique
    assert result.groupby("area_group").size().to_dict()==dict.fromkeys(STRATA,4)


def test_split_views_same_raw_geometry():
    raw=np.full((40,60),2100,dtype=np.uint16)
    raw[5,4]=1600
    base={
      "grade":["SMALL","MEDIUM","LARGE"],
      "display_bbox_x_global":[4,14,31],
      "display_bbox_y_global":[5,7,17],
      "display_bbox_xmax_inclusive":[4,22,43],
      "display_bbox_ymax_inclusive":[5,15,32],
    }
    df=pd.DataFrame(base)
    a=draw_base(raw,df,frozenset(("SMALL",)),"SMALL")
    b=draw_base(raw,df,frozenset(("MEDIUM","LARGE")),"MAIN")
    assert a.shape==b.shape
    assert a.ndim==3
    assert np.array_equal(a[90,0],b[90,0])  # unmarked origin
