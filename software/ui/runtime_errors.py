"""UI-only adaptation; domain/repository exceptions and wire schemas stay frozen."""
from dataclasses import dataclass
from functools import wraps
import re

MESSAGES={
 'LEDGER_UPDATE_FAILED':('Excel 台账更新失败。','正式结果保留；关闭 Excel/WPS，检查权限后重试同步/重建。'),
 'INPUT_VALIDATION_FAILED':('输入数据未通过检查。','当前结果不变；检查输入后重试。'),
 'RAW_READ_FAILED':('无法读取 RAW。','当前结果保留；检查文件存在且可读后重试。'),
 'RAW_SIZE_MISMATCH':('RAW 尺寸不匹配。','原结果不变；请选择符合尺寸的文件。'),
 'RAW_UNSUPPORTED_FORMAT':('RAW 格式不受支持。','无法提交审核；请使用 RAW/big/16容器/12有效位文件。'),
 'RAW_MISMATCH':('RAW 与正式结果身份不匹配。','旧证据已失效；请重新关联正确 RAW，当前不能提交。'),
 'RAW_UNAVAILABLE':('RAW 证据不可用。','当前不能提交；检查文件可读后重新关联。'),
 'CONFIG_ERROR':('检测配置无效。','未产生正式结果；检查配置后重试。'),
 'ROI_DETECTION_FAILED':('工作区定位失败。','未产生正式结果；请检查输入及配置。'),
 'DETECTION_FAILED':('检测执行失败。','未保存正式结果；检查输入后可重新检测。'),
 'RESULT_LOAD_FAILED':('历史结果加载失败。','新结果未加载；检查结果包后重试。'),
 'RESULT_INTEGRITY_FAILED':('正式结果完整性校验失败。','拒绝加载或审核；请恢复完整原始结果包。'),
 'RESULT_SAVE_FAILED':('正式结果保存失败。','当前临时结果未获得正式审核权限；检查空间和权限后重试。'),
 'VIEW_RESOURCE_FAILED':('视图资源读取失败。','算法结果不变；检查资源后重新切换视图。'),
 'REVIEW_SESSION_FAILED':('人工复核会话读取或创建失败。','未提交结论；检查审核目录后重试。'),
 'REVIEW_SUBMIT_FAILED':('人工复核保存失败。','当前任务未标为已处理；重新加载记录后重试。'),
 'REVIEW_CONFLICT':('人工复核记录发生冲突。','本次未追加结论；重新加载审核记录后重试。'),
 'POLICY_MISMATCH':('审核策略不匹配。','历史记录只读；使用一致策略后重新加载。'),
 'TEMPORARY_RESULT':('当前是临时检测结果。','无法创建正式审核会话；先保存正式结果。'),
 'EXPORT_FAILED':('导出失败。','正式结果与审核记录不变；检查目标位置后重试。'),
 'UNEXPECTED_ERROR':('操作失败，详细信息已写入日志。','请检查运行日志后重试；当前不会自动提交结论。')}

@dataclass(frozen=True)
class UiFailure:
    code:str
    user_message:str
    operation:str
    retryable:bool=True

def classify_error(exc,operation):
    from infrastructure.repositories.errors import PackageIntegrityError
    from ui.models.human_review import ReviewConflict
    text=str(exc);code=None
    for token in ['RAW_SIZE_MISMATCH','RAW_UNSUPPORTED_FORMAT','RAW_MISMATCH','RAW_UNAVAILABLE','POLICY_MISMATCH','TEMPORARY_RESULT','CONFIG_ERROR','ROI_DETECTION_FAILED']:
        if text.startswith(token):code=token;break
    if code is None and isinstance(exc,PackageIntegrityError):code='RESULT_INTEGRITY_FAILED'
    if code is None and operation=='detect' and (type(exc) is ValueError or type(exc).__name__=='ConfigurationError'):code='CONFIG_ERROR'
    if code is None and type(exc).__name__=='InputValidationError':code='RAW_READ_FAILED'
    if code is None and text.startswith('RESULT_MISMATCH'):code='RESULT_INTEGRITY_FAILED'
    if code is None and isinstance(exc,ReviewConflict):code='REVIEW_CONFLICT'
    if code is None and (text.startswith('RAW 大小') or text.startswith('RAW_INVALID_DIMENSIONS')):code='RAW_SIZE_MISMATCH'
    if code is None:
        code={'open_raw':'RAW_READ_FAILED','raw':'RAW_READ_FAILED','human_raw':'RAW_UNAVAILABLE','detect':'DETECTION_FAILED','load_history':'RESULT_LOAD_FAILED','history':'RESULT_LOAD_FAILED','save':'RESULT_SAVE_FAILED','saved':'RESULT_SAVE_FAILED','view':'VIEW_RESOURCE_FAILED','frame':'VIEW_RESOURCE_FAILED','detail_frame':'VIEW_RESOURCE_FAILED','viewer_detail':'VIEW_RESOURCE_FAILED','candidate_frame':'VIEW_RESOURCE_FAILED','admission_frame':'VIEW_RESOURCE_FAILED','human_image':'VIEW_RESOURCE_FAILED','human_session':'REVIEW_SESSION_FAILED','human_save':'REVIEW_SUBMIT_FAILED','human_export':'EXPORT_FAILED','ledger':'LEDGER_UPDATE_FAILED'}.get(operation,'UNEXPECTED_ERROR')
    if code=='UNEXPECTED_ERROR' and type(exc) is ValueError:code='INPUT_VALIDATION_FAILED'
    what,next_step=MESSAGES[code]
    # Keep safe legacy validation text (not technical exceptions) compatible with
    # existing UI callers, without paths, multiline tracebacks or secret details.
    validation=''
    if type(exc) is ValueError and code=='INPUT_VALIDATION_FAILED':
        safe=re.sub(r'[A-Za-z]:[\\/][^\s]+','[文件]',text.splitlines()[0] if text else '')[:120]
        validation=(' '+safe) if safe and 'Traceback' not in safe else ''
    return UiFailure(code,f'{code}：{what}{validation} {next_step} 详情见运行日志。',operation,code not in ('POLICY_MISMATCH','TEMPORARY_RESULT'))

def guarded_completion(method):
    @wraps(method)
    def receive(self,*args,**kwargs):
        try:return method(self,*args,**kwargs)
        except Exception as exc:self.controller.report_exception(exc,operation=getattr(self.controller,'operation','ui_callback'))
    return receive
