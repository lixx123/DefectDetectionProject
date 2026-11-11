# Phase10 Revision 修订报告（提交前）

修复两个阻塞：历史结果缺少可验证原始灰度证据；未正式保存的staging结果可以创建人工审核会话。没有进入Phase11。

1. Controller历史加载通过配置的正式JsonResultRepository完整校验，签发运行期FormalResultBinding。检测返回的VM仍无正式身份；不能凭saved布尔值、目录名字或output/results字符串获得资格。
2. 保存成功后使用SaveRecord.result_dir对应的正式库重载，构建新VM并比对result_id和完整字典；原Defect/Candidate/任务语义不改。保存或重载失败时审核仍禁用。
3. 独立ReviewAccess/ReviewEligibility集中管理formal/integrity/policy/RAW状态。HumanReviewRepository.create和submit均有服务级硬门禁，直接调用也不能绕过临时结果限制；submit在事务锁内再次检查正式绑定与verified RAW。正式结果可创建PENDING会话和只读恢复，没有RAW不能提交五类结论。
4. 新增只读运行时RAW关联/解除。根据结果元数据验证普通文件、字节数、尺寸、RAW格式、big端序、16容器/12有效位和流式SHA256；后台worker执行。不同文件名相同内容允许，文件名相同内容不同拒绝。
5. 使用既有RawImageProvider解析与局部显示；Windows只读共享句柄阻止关联期间写入/截断/替换，代理锁保护crop与解除mmap的并发。错误/过期返回不污染新结果。
6. 重启只恢复会话，RAW始终需要重选；审核协议和正式包均不保存RAW路径。只有原RAW证据验证后才能启用保存结论。
7. 第五Tab改名“人工复核”，内部两页不变。空图/无效显示尺寸明确显示不可用，不再除零。
8. pytest临时目录由OS原子保留独立父目录、pytest只管理其子目录，残留不复用；保留自身诊断目录，不删除任何历史或用户目录。

schema1.0、AUTO、正式Repository、Golden、Phase9规则和hash冻结；83/49全量任务保留，真实审核记录0，实际算法执行0。提交前证据与最终提交后的受测回执分开；最终回执在ignored output/phase10_revision_final和Codex outputs/Phase10_Revision。
