# 运行时RAW安全关联

绑定全程只读，不调用Detector、不改正式DTO或存储协议。允许格式：input_format为RAW/raw，byte_order=big，container_bits=16，effective_bits=12；width/height为正整数且从当前input_info取得，尺寸不使用RawImageProvider默认值。文件字节数必须width×height×container_bits/8，缺SHA或格式不支持明确拒绝。

后台步骤：检查普通文件/尺寸→Windows共享读租约（禁写、禁删/替换）→记录文件identity→每次最多1MiB流式SHA256→核对input_info.sha256→再次核对identity→RawImageProvider(path,width,height)。绝不一次read_bytes读取200MB文件。失败清理lease/mmap，不改变session和记录。SHA大小写归一后比较，文件名不作为身份。

RawBinding仅在内存包含result/source digest/path/sha/dimensions/provider/lease/verified。每次crop及提交校验文件identity，RLock保证解除与局部读取不同时操作已释放mmap。Windows租约覆盖hash和整个mmap寿命；非Windows平台保留identity检查，不宣称提供同等强制文件锁。

用户选择文件→既有QThread worker→SHA256。验证期间保存禁用；epoch/result_id/raw_revision共同绑定返回，过期成功关闭provider，过期失败丢弃。失败替换会解除旧证据，复核页旧图立即清除。切结果和关闭释放mmap/lease；重启RAW状态无绑定。当前RAW在同结果正式保存重载时重新验证，通过后保留可用证据。

UI不显示完整路径，状态明确未关联/校验中/失败/已验证。局部图复用Candidate/DefectDetailVM和原坐标，标示“真实 RAW 像素 · SHA256 已校验”。测量bbox/面积/长度/mask均不改；候选青框和可选Final黄框维持原显示语义。

标准pytest/FAST/GOLDEN/RELEASE全部使用外部RAW阻断守卫，只读合成测试RAW。单独真实界面验收仅允许两份冻结RAW和output内合成RAW；无算法执行，真实submit方法直接禁止。验证报告只保存sample ID、hash和状态，不保存RAW绝对路径。
