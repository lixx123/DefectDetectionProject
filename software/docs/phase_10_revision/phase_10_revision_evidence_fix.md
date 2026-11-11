# Phase10 Revision Evidence Fix

原问题：09_26_1_83_pending.png 错误地与 06_raw_mismatch.png 内容重复。旧 QA 脚本拍摄 RAW_MISMATCH 后没有恢复正确关联，导致同一画面被保存两次。

本次从真实 26_1 正式 Repository 结果重新打开界面，关联正确 RAW，通过 SHA256、尺寸、RAW/big/16容器/12有效位验证，再选择真实 Candidate 显示局部灰度图。独立机器读取正式结果、任务和隔离 PENDING 会话，核对 26_1=36 Defect/83 Tasks/83 PENDING，26_2=35/49/49；两组 records/labels 均为0。像素值逐点与原始 DN 的既有 LUT 换算核对。

未修改任何检测算法、正式结果、任务集合或真实人工审核数据；Detector 和真实 submit 在 QA 中被禁止调用。生产 output/reviews 不存在，本次未创建；完整正式 Repository 文件哈希前后相同。06/10 保留原证据，09 为真实窗口重新渲染，绝非复制或重命名。

- old_09_screenshot_sha256: `05679f3aa14a541000fc04747d94d259bc83715292173900d3fd7575cfa8c238`
- 09_screenshot_sha256: `9f38db6c61221f61373593f3897b5424092fed7a93f3c6f232cf99beb3c19ed8`
- 06_screenshot_sha256: `05679f3aa14a541000fc04747d94d259bc83715292173900d3fd7575cfa8c238`
- 10_screenshot_sha256: `702e5f576f7638f988f7bb717d2b0ee96bf0d089669ee756cae467c1e0308abc`

RAW 路径仅在运行时环境变量中读取；正式包、隔离审核 JSON/CSV及交付文件复核不含完整 RAW 路径。对 RAW 的报告仅记录 sample_id、sha256 和验证状态。

本文件是提交前证据记录。最终同一干净 HEAD 的 focused/full pytest、FAST、GOLDEN、RELEASE、smoke、pip check 回执在交付目录 verification/test report/manifest；最终提交号只写入仓库外回执，避免再次提交形成未测试 HEAD。停止于 Phase10 Revision，Phase11_started=false。
