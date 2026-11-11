# 人工复核工作区

维持五个顶层Tab；第五页保留名称“人工复核准入”，内部“复核队列 / 准入统计”。原Phase9准入统计、四bucket、旧跳转继续可用；规则与policy字节不变。默认队列仅ReviewTask，不把全量Audit REVIEW变人工工作量。

顶部总数/已处理/PENDING/UNCERTAIN/完成率/算法最终疵病数独立显示；当前审核者为显式输入。左侧QAbstractTableModel虚拟行，无逐候选Widget。支持状态/对象/优先级/原因/source/decision组合筛选，全局priority/status/area/ID/reason排序；默认HIGH→MEDIUM→LOW，同级Defect先，再稳定key。不会Top-N截断。

右侧始终显示task ID/kind/object/source/priority/reasons，原始evidence和完整revision历史。五类结论按对象动态限制；初始不预选，重复目标初始不选。空间候选ID单独展示，可查看对应最终Defect；target列表空间关联在先、全部有效最终对象在后，排除自身。

复用ImageViewer、RawImageProvider.crop、DefectDetailViewModel、CandidateDetailViewModel；候选40/120/300像素多尺度邻域可选，既有调用默认40不变。青色Candidate初始框、黄色可选附近Final框；缺初始几何不借最终bbox，缺原图显示明确标注的中性底图，不生成假原图。外扩只为显示，不改测量。

保存并下一个：显式选结论/target、必要确认后，捕获epoch+session+taskkey+expected_revision，worker再次检查选中身份；保存期间禁用表格和表单，成功耐久落盘后才跳首个PENDING。图像返回以epoch/taskkey/image_revision三重比对，旧帧丢弃；切结果/隐藏页使旧请求失效。保存出错保留表单并显示原因，不假报成功。

表格/图像聚焦时1–5按固定五decision顺序选择，Defect不允许4；Enter提交。输入框内数字不拦截。DUP/NEW额外确认仍必须通过。

“人工审核统计”显示五结论与kind/priority/reason/source/Band拆分，包括空间关联、边界、尺寸风险、promising专项（零命中也保留计数）。这些统计与原36/35算法疵病数分离；CSV/JSON按钮导出独立审核最小数据。

截图为1800×1100离屏Qt实窗抓图；已检查真实PENDING、合成duplicate、历史revision和mismatch界面。真实图不自动人工标注，合成截图明确标记Synthetic。
