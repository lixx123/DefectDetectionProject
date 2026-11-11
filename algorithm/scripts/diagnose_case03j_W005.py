from pathlib import Path
import numpy as np, cv2
root=Path(__file__).resolve().parents[1]
p=root/'outputs/case03i_annotation/run_20261010_frame1_frame2_pixel_grade_v1/region_masks/26_1_E2_W005_graded_masks.npz'
with np.load(p) as z:
 lab=z['local_region_labels_int32']
rect=(2944,1024,3200,1280)
raw=np.asarray(np.memmap(root.parent/'疵病实测数据/260624批次表观（5片）/26 (1).raw',mode='r',dtype='>u2',shape=(9200,11276))[1024:1280,2944:3200],dtype=np.uint16)
blur=cv2.GaussianBlur(raw.astype(np.float32),(0,0),8)-cv2.GaussianBlur(raw.astype(np.float32),(0,0),2)
n=lab.max()
for j in range(1,n+1):
 yy,xx=np.where(lab==j)
 pts=np.column_stack([xx,yy]).astype(float)
 if len(pts)>=2:
  cov=np.cov(pts.T); v,U=np.linalg.eigh(cov); v=v[::-1];ax=U[:,::-1][:,0]
  ang=float(np.rad2deg(np.arctan2(ax[1],ax[0]))%180); ratio=float(np.sqrt(max(1e-6,v[0])/max(1e-6,v[-1])))
 else:ang=0.;ratio=0.
 if len(pts)>=8:
  print(f'{j:02d} A={len(pts):4d} ratio={ratio:4.1f} angle={ang:5.1f} DoG={np.median(blur[yy,xx]):5.1f} x({xx.min():3d}-{xx.max():3d}) y({yy.min():3d}-{yy.max():3d})')
# gap sample at W005 main parts
pairs=[(7,16),(16,20),(15,16),(15,17),(16,17),(15,21),(8,10)]
for a,b in pairs:
 ya,xa=np.where(lab==a);yb,xb=np.where(lab==b)
 A=np.column_stack([xa,ya]);B=np.column_stack([xb,yb])
 dist=((A[:,None,:]-B[None,:,:])**2).sum(2)
 i,k=np.unravel_index(dist.argmin(),dist.shape)
 q0=A[i];q1=B[k];N=max(int(np.linalg.norm(q1-q0)*2),2)
 line=np.rint(np.linspace(q0,q1,N)).astype(int)
 print('PAIR',a,b,'gap',round(np.sqrt(dist[i,k]),2),'pts',q0,q1,
       'line DoG med',np.median(blur[line[:,1],line[:,0]]),
       'RAW mean',np.mean(raw[line[:,1],line[:,0]]))
