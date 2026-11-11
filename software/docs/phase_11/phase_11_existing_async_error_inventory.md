# Phase11 现有异步与异常机制盘点

基线 ff4e7dafd31e098341716a6379a8c5cfca38c3fc，修改前 HEAD 匹配且 Git clean。

| 操作 | 原有执行位置 | 异常传播与用户提示 | 风险 |
|---|---|---|---|
| RAW 打开/thumbnail | InspectionController + InspectionWorker/QThread | failed(str)→MainWindow状态栏和资源提示 | 打开前clear_result导致失败也丢掉旧VM；thumbnail失败可能未清mmap |
| detect | service→staging.save/load→VM.frame，QThread | runtime/gui_errors.log记录traceback，error信号提示 | 没有稳定事件码；日志创建或写失败可能压住error信号 |
| history/load_history | QThread，FormalResultAuthority完整校验 | error→状态栏 | 未统一完整性分类 |
| save + reload | QThread，正式库原子保存后完整reload | error；成功才替换VM | RAW重新验证失败仅warning字符串，无统一日志 |
| view/detail_frame | QThread加载/哈希/局部图 | error；缺资源可能返回降级frame.message | 降级有状态但没有运行日志 |
| 缩放/平移RAW裁剪 | ImageViewer定时器GUI线程，最大4M像素 | 直接crop，无错误适配 | 可能阻塞事件循环，异常未分类 |
| 人工session/save/export | 共享controller互斥QThread，Repository原子写及revision冲突保护 | worker.failed；页面own_job判断 | epoch等过期保护已有；不能改业务协议 |
| human_raw | QThread，大文件流式SHA256、格式/租约验证 | 操作内部捕获异常作为带epoch/result_id/raw_revision的完成payload | 异常在内部被转换，丢失traceback；必须保留过期payload处置语义 |
| audit/admission索引、查询、局部图 | 共享QThread；epoch/query_revision/image_revision | error→页面与主状态栏 | worker没有可查询终态；回调异常不进worker日志 |
| pointer DN | GUI线程单像素读取 | 原来直接读取 | 保持单像素，重裁剪须后台化 |

原有busy互斥、completed/error信号、线程finished后busy=False、忙时阻止关闭已存在；沿用并测试，不重建线程框架。原有application、infrastructure、human_review模型中的正式保存/审核写入是原子发布和锁保护，Phase11不改这些冻结语义。regression已有Golden、765文件算法保护、schema/AUTO与绝对路径扫描；tests已有665条，其中Phase10/9专项186条。

算法audit_log负责对象追溯、独立运行日志负责软件生命周期、human review负责人工判断；三者保持分离。
