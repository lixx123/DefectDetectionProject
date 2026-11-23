import numpy as np
import pytest
from src.detection.edge_attached_spots import split_parent, EdgeSpotSettings


def fixture(spot=True, mirror=False, dx=0):
    y,x=np.mgrid[:256,:1024]
    raw=np.where(y<128,1000,100).astype(np.uint16)
    source=(y>=126)&(y<=128)
    disk=(x-(400+dx))**2+(y-114)**2<=12**2
    if spot:
        raw[disk]=450;source|=disk
    band=dict(core_x_min=0,core_x_max_exclusive=1024,top_line_y_at_x0=20.,bottom_line_y_at_x0=128.,
              top_line_slope_y_per_x=0.,bottom_line_slope_y_per_x=0.)
    if mirror:
        raw=raw[::-1].copy();source=source[::-1].copy()
        band.update(top_line_y_at_x0=127.,bottom_line_y_at_x0=235.)
    return raw,source,band


@pytest.mark.parametrize('mirror,dx',[(False,0),(True,0),(False,150)])
def test_source_partition_and_location_equivariance(mirror,dx):
    raw,source,band=fixture(mirror=mirror,dx=dx);original=source.copy()
    children,remainder,_=split_parent(raw,source,[0,0,1024,256],band)
    assert len(children)==1
    union=remainder.copy()
    for c in children:
        x,y,X,Y=c['bbox'];assert not (union[y:Y,x:X]&c['mask']).any()
        union[y:Y,x:X]|=c['mask'];assert x<=400+dx<X
    assert np.array_equal(union,source) and np.array_equal(source,original)


def test_pure_edge_does_not_make_spot():
    raw,source,band=fixture(spot=False)
    children,remainder,_=split_parent(raw,source,[0,0,1024,256],band)
    assert not children and np.array_equal(remainder,source)


def test_long_anomaly_is_preserved_for_review():
    raw,source,band=fixture(spot=False)
    raw[104:120,300:500]=400;source[104:120,300:500]=True
    children,remainder,_=split_parent(raw,source,[0,0,1024,256],band)
    assert not children and np.array_equal(remainder,source)


def test_unknown_geometry_preserves_source():
    raw,source,_=fixture()
    children,remainder,audit=split_parent(raw,source,[0,0,1024,256],None)
    assert not children and np.array_equal(remainder,source)
    assert audit['reason']=='UNKNOWN_GEOMETRY'


def test_invalid_settings_fail_explicitly():
    with pytest.raises(ValueError):EdgeSpotSettings(high_sigma=1,low_sigma=2).validate()


def test_two_separate_spots_are_not_merged():
    raw,source,band=fixture();y,x=np.indices(raw.shape)
    other=(x-600)**2+(y-114)**2<=12**2
    raw[other]=450;source|=other
    children,remainder,_=split_parent(raw,source,[0,0,1024,256],band)
    assert len(children)==2
    assert sorted(c['bbox'][0] for c in children)==[388,588]
    assert sum(c['area_px'] for c in children)+int(remainder.sum())==int(source.sum())


def test_clipped_spot_stays_in_review():
    raw,source,band=fixture(dx=-395)
    children,remainder,_=split_parent(raw,source,[0,0,1024,256],band)
    assert not children and np.array_equal(remainder,source)


def test_no_review_objects_skip_raw_and_mask_io(tmp_path):
    from src.visualization.edge_spot_report import write_edge_spots
    from src.detection.size_review import Settings
    _,_,band=fixture()
    row=dict(new_id='normal',band_id=1,source_bbox_width_px=10,source_bbox_height_px=10)
    class Unreadable:
        def __getitem__(self,key):raise AssertionError('RAW accessed on no-review route')
    result=write_edge_spots(tmp_path,[row],{1:band},Unreadable(),None,Settings(),EdgeSpotSettings())
    assert result['skipped'] and result['children']==0
    assert [p.name for p in tmp_path.iterdir()]==['edge_spot_receipt.json']


def test_half_pixel_geometry_does_not_drop_alternate_rows():
    raw,source,band=fixture()
    band['top_line_y_at_x0']+=.5;band['bottom_line_y_at_x0']+=.5
    children,_,_=split_parent(raw,source,[0,0,1024,256],band)
    assert len(children)==1
    assert children[0]['area_px']>400
