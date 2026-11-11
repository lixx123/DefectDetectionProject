"""Exploratory K8-A row profile. No mask, no thresholds altered."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np,cv2
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks
from config import user_config as c
from scripts.run_case03g_joint_noise_refinement import save_png
o=c.OUTPUT_ROOT/"case03k8a_band_locator_exploration_v1"
o.mkdir(exist_ok=True)
for frame in (1,2):
    r=np.memmap(c.DATA_ROOT/f"26 ({frame}).raw",mode="r",dtype=">u2",shape=(c.RAW_HEIGHT,c.RAW_WIDTH))
    crop=np.asarray(r[::4,int(c.RAW_WIDTH*.12):int(c.RAW_WIDTH*.88):12],dtype=np.float32)
    med=np.median(crop,axis=1)
    q10=np.percentile(crop,10,axis=1)
    q90=np.percentile(crop,90,axis=1)
    mean=np.mean(crop,axis=1)
    smooth=gaussian_filter1d(med,17)
    mx=float(np.max(smooth));mn=float(np.min(smooth))
    peaks,_=find_peaks(smooth,prominence=150,distance=90)
    troughs,_=find_peaks(-smooth,prominence=150,distance=90)
    print("FRAME",frame,"raw med min max",round(mn),round(mx),"median",float(np.median(smooth)))
    print("PEAKS_MEDIAN",[(int(x*4),round(float(smooth[x]))) for x in peaks])
    print("TROUGHS_MEDIAN",[(int(x*4),round(float(smooth[x]))) for x in troughs])
    print("SAMPLES EACH 100 pixels",[(int(x*4),int(smooth[x]),int(q10[x]),int(q90[x])) for x in range(0,len(smooth),25)])
    w=1750;h=1200
    canvas=np.full((h,w,3),28,np.uint8)
    # panel top = resized frame, lower y indexed
    raw8=np.asarray(r[::8,::8],dtype=np.float32)
    lo,hi=np.percentile(raw8,[1,99.5]);g=np.uint8(np.clip((raw8-lo)/max(1,hi-lo)*255,0,255))
    thumb=cv2.cvtColor(cv2.resize(g,(1550,720),interpolation=cv2.INTER_AREA),cv2.COLOR_GRAY2BGR)
    canvas[45:765,175:1725]=thumb
    cv2.putText(canvas,f"FRAME 26({frame}): RAW preview with row profile", (20,27),cv2.FONT_HERSHEY_SIMPLEX,.65,(230,230,230),1)
    # x-axis is raw vertical index, choose horizontal plot below
    plotx0=175;ploty0=800;plotw=1550;ploth=340
    for p,name,col in [(med,"median",(210,210,210)),(q10,"p10",(45,185,255)),(q90,"p90",(120,235,105))]:
        pv=gaussian_filter1d(p,17)
        maxdn=max(float(np.max(q90)),1.)
        pts=np.asarray([[plotx0+int(x/len(pv)*(plotw-1)),ploty0+ploth-int(min(float(v)/maxdn,1)*(ploth-20))-10] for x,v in enumerate(pv)],np.int32)
        cv2.polylines(canvas,[pts],False,col,2,cv2.LINE_AA)
    for x in peaks:
        xx=plotx0+int(x/len(med)*plotw)
        cv2.line(canvas,(xx,ploty0),(xx,ploty0+ploth),(80,80,80),1)
        cv2.putText(canvas,str(round(x*4)),(xx,ploty0+15),cv2.FONT_HERSHEY_SIMPLEX,.42,(238,238,238),1)
    dest=o/f"frame26_{frame}_profile_and_raw.png"
    save_png(dest,canvas)
    print("PROFILEREF",dest)
