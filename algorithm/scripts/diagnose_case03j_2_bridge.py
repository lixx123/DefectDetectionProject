from pathlib import Path
import cv2,numpy as np,pandas as pd,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.detection.case03j_fragment_association import _component_geometry,_nearest_pair,_bridge_support,AssociationConfig
root=Path(__file__).resolve().parents[1]
p=root/'outputs/case03i_annotation/run_20261010_frame1_frame2_pixel_grade_v1'
with np.load(p/'region_masks/26_1_E2_W005_graded_masks.npz') as z: lab=z['local_region_labels_int32'];r=z['roi_global_xyxy']
rs=pd.read_csv(p/'all_candidate_size_grades.csv')
records=rs[(rs.window_id=='E2_W005')&(rs.frame=='26_1')].to_dict('records')
for x in records:x.update(_global_x0=int(r[0]),_global_y0=int(r[1]))
raw=np.asarray(np.memmap(root.parent/'疵病实测数据/260624批次表观（5片）/26 (1).raw',dtype='>u2',mode='r',shape=(9200,11276))[r[1]:r[3],r[0]:r[2]],np.uint16)
f=raw.astype(np.float32);dog=cv2.GaussianBlur(f,(0,0),8)-cv2.GaussianBlur(f,(0,0),2)
cfg=AssociationConfig()
g=_component_geometry(lab,records,dog,cfg)
for a,b in [(16,17),(15,17),(16,19),(15,16),(7,16)]:
 gap,q0,q1=_nearest_pair(g[a]['boundary'],g[b]['boundary'])
 v=q1-q0
 print('pair',a,b,'gap',round(gap,3),'p',q0,q1,'v',v,'dog',_bridge_support(dog,q0,q1,lab,cfg))
for j in [7,12,15,16,17,19,20]:
 q=g[j]
 print('object',j,'area',q['area'],'length',q['length'],'axis',q['axis'],'aspect',q['aspect'])
