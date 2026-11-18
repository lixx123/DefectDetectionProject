"""J4真实RAW滤波上下文；判定窗口与数值算子的读取范围独立。"""
from __future__ import annotations
import cv2
import numpy as np
from src.detection.local_boundary_refinement import compute_local_residual


def filter_context(rawmem, decision_xyxy, guard, texture):
    """输出固定判定窗口内的Gaussian22/Closing61残差及DoG，单位DN。

    中值1 + uint16 Gaussian22半径88 + float32平滑半径4 = 93。
    Closing61为1+30+30+4=65，DoG为max(8,32)=32。
    仅真实图像边缘采用原OpenCV边界模式；内部窗边不能合成像素。
    MAD、CC、面积比例等仍由既有固定判定窗口计算，不宣称全帧CC等价。
    """
    if not isinstance(guard,int) or guard<93:
        raise ValueError('J4 external filter context must be >=93 pixels')
    if (texture.dog_large_sigma_px,texture.dog_small_sigma_px)!=(8.,2.):
        raise ValueError('Re-derive filter support before changing DoG sigma')
    l,t,r,b=map(int,decision_xyxy);H,W=rawmem.shape
    if not(0<=l<r<=W and 0<=t<b<=H):raise ValueError('invalid decision window')
    x0=max(0,l-guard);y0=max(0,t-guard);x1=min(W,r+guard);y1=min(H,b+guard)
    # 固定全局 SIMD 对齐，避免同一像素在不同宽度下进入不同尾部运算路径。
    x0=(x0//32)*32;x1=min(W,((x1+31)//32)*32)
    raw=np.asarray(rawmem[y0:y1,x0:x1],dtype=np.uint16)
    ys=slice(t-y0,b-y0);xs=slice(l-x0,r-x0)
    residuals={s:compute_local_residual(raw,s)[ys,xs].copy() for s in ('gaussian22','closing61')}
    f=raw.astype(np.float32)
    dog=(cv2.GaussianBlur(f,(0,0),8.)-cv2.GaussianBlur(f,(0,0),2.))[ys,xs].copy()
    return dict(residuals=residuals,dog=dog,read_xyxy=[x0,y0,x1,y1],raw_pixels=int(raw.size))
