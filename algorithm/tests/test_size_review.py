import unittest,copy
from src.detection.size_review import classify,Settings,attach

class SizeReviewTests(unittest.TestCase):
    def setUp(self):
        self.band={1:dict(core_x_min=0,core_x_max_exclusive=1000,top_line_y_at_x0=0,bottom_line_y_at_x0=100,top_line_slope_y_per_x=0,bottom_line_slope_y_per_x=0)}
    def row(self,w,h):return dict(new_id='test',band_id=1,source_bbox_width_px=w,source_bbox_height_px=h,mask_path='unchanged.npz')
    def test_threshold_boundary(self):
        self.assertEqual(classify([self.row(249,10)],self.band)[0]['review_status'],'NORMAL_CANDIDATE')
        self.assertEqual(classify([self.row(250,10)],self.band)[0]['review_status'],'SIZE_REVIEW')
        self.assertEqual(classify([self.row(10,80)],self.band)[0]['review_status'],'SIZE_REVIEW')
    def test_unknown_is_review(self):
        self.assertEqual(classify([self.row(10,10)],{})[0]['reason'],'UNKNOWN_BAND_GEOMETRY')
    def test_preserves_input_and_all_rows(self):
        rows=[self.row(10,10),self.row(900,90)];original=copy.deepcopy(rows)
        result=attach(rows,self.band)
        self.assertEqual(rows,original);self.assertEqual(len(result),len(rows))
        for a,b in zip(rows,result):
            for k,v in a.items():self.assertEqual(b[k],v)
    def test_invalid_setting(self):
        with self.assertRaises(ValueError):classify([],{},Settings(0,.8))
    def test_slope_sign_symmetry(self):
        bands=copy.deepcopy(self.band);bands[1]['top_line_slope_y_per_x']=.05;bands[1]['bottom_line_slope_y_per_x']=.05
        a=classify([self.row(200,30)],bands)[0]
        bands[1]['top_line_slope_y_per_x']=-.05;bands[1]['bottom_line_slope_y_per_x']=-.05
        b=classify([self.row(200,30)],bands)[0]
        self.assertEqual(a['length_ratio'],b['length_ratio']);self.assertEqual(a['thickness_ratio'],b['thickness_ratio'])
if __name__=='__main__':unittest.main()

