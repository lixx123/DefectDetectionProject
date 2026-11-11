# ImageViewer 设计

QGraphicsView/QGraphicsScene 的 scene 坐标始终为原始像素；缩略图 QPixmap 用变换映射至原宽高，1:1 是一个 scene pixel 对应一个视口像素。滚轮围绕鼠标位置缩放，范围 0.01–32；滚动条/拖拽约束于 image rect。适应窗口、1、+、- 可用。

RawImageProvider 只读 big-endian uint16 memmap，默认 11276×9200，按文件字节数校验；DN 直接索引映射数据。显示 LUT 为固定有效 12-bit 的 0–4095 → 0–255，不修改原文件。缩略图最长边约 2800。原图接近 1:1 时解码可见局部原始像素，最多 400 万像素，40ms 防抖；不会在鼠标移动时复制全图。仅当前局部保留，没有多份全尺寸 RGB。

疵病框读取 Defect.geometry.bbox（exclusive），使用独立 QGraphicsRectItem；编号使用忽略缩放的文字项。框与编号可分别隐藏。没有扩大或重算 measurement bbox。最终 mask 使用独立透明 QPixmap 层，可开关，不烧入底图。

ROI/Band 显示只对引用的 PNG 掩膜作缩略显示着色，不从像素识别 Band、不从 mask 反算 bbox、不读取 CSV。Band 标签位置来自 BandInfo.bbox，数量来自 band_list；WORK/NONWORK/REVIEW 标签和缺资源提示明确显示。几何无效状态原样呈现，不将失败几何标为有效。

QImageReader 顺序解码大灰度 PNG，分配上限 512MiB；显示层只保留缩略尺寸。ImageCache 只保留当前帧，切换/clear 释放 QImage、mask、items、选择、详情和 RAW 映射。历史无原图时不提供虚假的高分辨率灰度细节。

所有资源先做包内路径约束和引用 SHA 校验；历史加载先通过 Repository.full verify。鼠标越界显示 —；preview 不提供原始 DN。
