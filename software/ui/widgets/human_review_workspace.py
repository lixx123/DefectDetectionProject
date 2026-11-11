"""Human review workspace. All result objects remain read-only."""
import json
import logging
from ui.runtime_errors import classify_error,guarded_completion
from pathlib import Path
from PySide6.QtCore import Qt,Signal,QAbstractTableModel,QEvent
from PySide6.QtGui import QColor,QPen
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QPushButton,QComboBox,
 QPlainTextEdit,QCheckBox,QTableView,QSplitter,QTabWidget,QFileDialog,QHeaderView,QAbstractItemView,QDialog,QDialogButtonBox)
from ui.image_viewer import ImageViewer
from ui.models.human_review import (HumanReviewRepository,ReviewContext,HumanReviewDecision,latest,summary,mismatch,task_status,query_tasks)
from ui.models.human_review.model import allowed_decisions
from ui.models.human_review.service import make_guard
from ui.models.human_review.evidence import ReviewAccess,validate_raw
from ui.models.defect_detail_view_model import DefectDetailViewModel,LocalView
from ui.models.candidate_detail_view_model import CandidateDetailViewModel
from ui.models.result_view_model import Overlay

LABELS={'CONFIRMED_DEFECT':'确认疵病','FALSE_POSITIVE':'误报','DUPLICATE_OF_EXISTING_DEFECT':'与现有疵病重复',
        'NEW_MISSED_DEFECT':'新增漏检（独立记录）','UNCERTAIN':'不确定'}

class HumanTaskTableModel(QAbstractTableModel):
    columns=('状态','优先级','对象','来源','ID','准入原因','人工结论')
    def __init__(self,parent=None):super().__init__(parent);self.rows=[];self.records={};self.stale=None
    def rowCount(self,parent=None):return len(self.rows)
    def columnCount(self,parent=None):return len(self.columns)
    def headerData(self,section,orientation,role=Qt.ItemDataRole.DisplayRole):
        if role==Qt.ItemDataRole.DisplayRole and orientation==Qt.Orientation.Horizontal:return self.columns[section]
    def data(self,index,role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role!=Qt.ItemDataRole.DisplayRole:return None
        t=self.rows[index.row()];r=self.records.get(t['task_key'],{})
        return (task_status(t,self.records,self.stale),t['priority'],t['object_kind'],t['source'],t['object_id'],
                ', '.join(t['reasons']),r.get('decision','—'))[index.column()]
    def set_rows(self,rows,records,stale):
        self.beginResetModel();self.rows=rows;self.records=records;self.stale=stale;self.endResetModel()


class HumanReviewPage(QWidget):
    defect_requested=Signal(str)
    candidate_requested=Signal(object)
    def __init__(self,controller,admission_page,parent=None,repository=None):
        super().__init__(parent);self.controller=controller;self.admission_page=admission_page
        self.repository=repository or HumanReviewRepository(controller.runtime_root.parent/'reviews')
        self.result_vm=None;self.admission=None;self.tasks=[];self.context=None;self.state=None;self.stale=None
        self.access=ReviewAccess();self.raw_revision=0;self.raw_verifying=False;self.raw_error=None
        self.epoch=0;self.image_revision=0;self.selected_task_key=None;self.form_task_key=None
        self.image_pending=False;self.restore_pending=False;self.active=False;self.own_job=None;self.guard=None
        self._build();controller.completed.connect(self.completed);controller.busy_changed.connect(self.busy_changed);controller.error.connect(self.failed)

    def _build(self):
        layout=QVBoxLayout(self)
        self.notice=QLabel('人工复核执行 · 原算法结果永久保留；人工结论独立保存。这里只是准入任务，不是完整GT。')
        self.notice.setWordWrap(True);layout.addWidget(self.notice)
        evidence_bar=QHBoxLayout();self.evidence_status=QLabel('原始 RAW：未关联')
        self.evidence_status.setWordWrap(True);evidence_bar.addWidget(self.evidence_status,1)
        self.attach=QPushButton('关联原始 RAW');self.attach.clicked.connect(self.choose_raw);evidence_bar.addWidget(self.attach)
        self.detach=QPushButton('解除 RAW 关联');self.detach.clicked.connect(self.detach_raw);evidence_bar.addWidget(self.detach)
        layout.addLayout(evidence_bar)
        self.progress=QLabel('暂无结果 · PENDING 0');layout.addWidget(self.progress)
        bar=QHBoxLayout();bar.addWidget(QLabel('当前审核者（必填）'))
        self.reviewer=QLineEdit();self.reviewer.setPlaceholderText('由审核者明确填写，不自动读取系统账户');bar.addWidget(self.reviewer,1)
        self.start=QPushButton('创建 / 恢复会话');self.start.clicked.connect(lambda:self.open_session(False));bar.addWidget(self.start)
        self.new=QPushButton('新建独立会话');self.new.clicked.connect(lambda:self.open_session(True));bar.addWidget(self.new)
        self.new_ack=QCheckBox('确认另建会话，保留旧记录');bar.addWidget(self.new_ack);layout.addLayout(bar)
        filters=QHBoxLayout();self.filters={}
        for name,label in [('status','状态'),('object_kind','对象'),('priority','优先级'),('reason','原因'),('source','来源'),('decision','结论')]:
            combo=QComboBox();combo.addItem(label+'：全部',None);combo.setMaximumWidth(190)
            combo.currentIndexChanged.connect(self.refresh);self.filters[name]=combo;filters.addWidget(combo)
        self.sort=QComboBox()
        for text,key in [('优先级（同级Defect先）','priority'),('状态','status'),('面积','area'),('ID','id'),('原因','reason')]:self.sort.addItem(text,key)
        self.sort.currentIndexChanged.connect(self.refresh);filters.addWidget(self.sort)
        self.stats=QPushButton('人工审核统计');self.stats.clicked.connect(self.show_statistics);filters.addWidget(self.stats)
        self.descending=QCheckBox('降序');self.descending.toggled.connect(self.refresh);filters.addWidget(self.descending);layout.addLayout(filters)
        split=QSplitter(Qt.Orientation.Horizontal);self.table=QTableView();self.model=HumanTaskTableModel(self)
        self.table.setModel(self.model);self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.selectionModel().currentRowChanged.connect(self.select_index);split.addWidget(self.table)
        right=QWidget();rl=QVBoxLayout(right);self.identity=QLabel('请选择任务');self.identity.setWordWrap(True);rl.addWidget(self.identity)
        imagebar=QHBoxLayout();self.margin=QComboBox()
        for text,m in [('小邻域 40px',40),('中邻域 120px',120),('大邻域 300px',300)]:self.margin.addItem(text,m)
        self.margin.currentIndexChanged.connect(self.request_image);imagebar.addWidget(self.margin)
        self.nearby=QCheckBox('显示附近最终bbox（黄色）');self.nearby.setChecked(True);self.nearby.toggled.connect(self.request_image);imagebar.addWidget(self.nearby)
        self.jump=QPushButton('查看原对象');self.jump.clicked.connect(self.jump_selected);imagebar.addWidget(self.jump);rl.addLayout(imagebar)
        self.viewer=ImageViewer();self.viewer.setMinimumHeight(140);rl.addWidget(self.viewer,1)
        self.image_status=QLabel('局部图尚未加载');self.image_status.setWordWrap(True);rl.addWidget(self.image_status)
        self.spatial=QComboBox();self.spatial.addItem('spatial_final_ids：无',None)
        spatialbar=QHBoxLayout();spatialbar.addWidget(self.spatial,1);button=QPushButton('跳转空间关联Defect');button.clicked.connect(lambda:self.jump_final(self.spatial.currentData()));spatialbar.addWidget(button);rl.addLayout(spatialbar)
        self.detail=QPlainTextEdit();self.detail.setReadOnly(True);self.detail.setMaximumHeight(110);rl.addWidget(self.detail)
        self.decision=QComboBox();self.decision.currentIndexChanged.connect(self.update_controls);rl.addWidget(self.decision)
        targetbar=QHBoxLayout();targetbar.addWidget(QLabel('重复目标（必须显式选择）'));self.target=QComboBox();targetbar.addWidget(self.target,1)
        button=QPushButton('查看目标');button.clicked.connect(lambda:self.jump_final(self.target.currentData()));targetbar.addWidget(button);rl.addLayout(targetbar)
        self.special=QCheckBox('我已核对重复目标 / 确认新增漏检语义（不会生成正式Defect）');rl.addWidget(self.special)
        self.other=QCheckBox('已阅读另一审核者结论，确认以新revision追加');rl.addWidget(self.other)
        self.comment=QPlainTextEdit();self.comment.setPlaceholderText('审核备注（可空）');self.comment.setMaximumHeight(60);rl.addWidget(self.comment)
        actions=QHBoxLayout();self.save=QPushButton('保存并下一个');self.save.clicked.connect(self.save_next);actions.addWidget(self.save)
        self.reload=QPushButton('重新加载审核记录');self.reload.clicked.connect(lambda:self.open_session(False));actions.addWidget(self.reload)
        for fmt in ('csv','json'):
            b=QPushButton('导出 '+fmt.upper());b.clicked.connect(lambda checked=False,f=fmt:self.export(f));actions.addWidget(b)
        rl.addLayout(actions);self.message=QLabel('尚未执行人工审核');self.message.setWordWrap(True);rl.addWidget(self.message)
        split.addWidget(right);split.setSizes([700,850]);layout.addWidget(split,1)
        self.table.installEventFilter(self);self.viewer.installEventFilter(self);self.update_controls()

    def set_result(self,vm):
        self.epoch+=1;self.detach_raw(refresh=False);self.result_vm=vm;self.access=vm.review_access if vm else ReviewAccess();self.admission=None;self.tasks=[];self.context=self.state=None;self.stale=None
        self.selected_task_key=self.form_task_key=None;self.guard=None;self.image_pending=False;self.restore_pending=False
        self.viewer.clear();self.identity.setText('请选择任务');self.detail.clear();self.comment.clear();self.message.setText('尚未执行人工审核')
        self.refresh()

    def set_active(self,active):
        self.active=active
        if not active:self.image_revision+=1
        self.pump()

    def bind_admission(self):
        queue=self.admission_page.queue_vm
        if not queue or self.result_vm is None:return
        self.admission=queue.admission
        # Only frozen task projections, no all-candidate widgets or geometry copies.
        from ui.models.human_review.model import snapshot_task
        self.tasks=[snapshot_task(t,self.result_vm.result,queue.candidates) for t in self.admission.tasks]
        self.populate_filters();self.refresh()
        pointer=self.repository.root/self.result_vm.result.result_id/'active.json'
        self.restore_pending=pointer.is_file() and self.access.eligibility().formal_result;self.pump()

    def populate_filters(self):
        options={'status':['PENDING','REVIEWED','UNCERTAIN','STALE'],'object_kind':['DEFECT','CANDIDATE'],
                 'priority':['HIGH','MEDIUM','LOW'],'decision':[d.value for d in HumanReviewDecision],
                 'reason':sorted({r for t in self.tasks for r in t['reasons']}),'source':sorted({t['source'] for t in self.tasks if t['source']})}
        for key,combo in self.filters.items():
            combo.blockSignals(True)
            while combo.count()>1:combo.removeItem(1)
            for value in options[key]:combo.addItem(value,value)
            combo.setCurrentIndex(0);combo.blockSignals(False)

    def refresh(self,*args):
        records=latest(self.state) if self.state else {}
        selected=self.selected_task_key
        tasks=self.state['tasks'] if self.state else self.tasks
        rows=query_tasks(tasks,records,stale=self.stale,filters={k:c.currentData() for k,c in self.filters.items()},
                         sort=self.sort.currentData(),descending=self.descending.isChecked())
        self.model.set_rows(rows,records,self.stale)
        total=len(tasks);completed=0;uncertain=0
        if self.state:
            s=summary(self.state,self.stale);completed=s['completed'];uncertain=s['uncertain']
        self.progress.setText(f'总任务 {total} · 已处理 {completed} · PENDING {total-completed} · 不确定 {uncertain} · {(100*completed/total if total else 0):.1f}% · 原算法最终疵病 {len(self.result_vm.defects) if self.result_vm else 0}'
                              +(f' · {self.stale}：历史记录只读' if self.stale else '')
                              +(f' · 全部已处理，但仍有 {uncertain} 条不确定' if total and completed==total and uncertain else ''))
        self.selected_task_key=self.form_task_key=None
        index=next((i for i,t in enumerate(rows) if t['task_key']==selected),None)
        if index is None:index=next((i for i,t in enumerate(rows) if task_status(t,records,self.stale)=='PENDING'),0 if rows else None)
        if index is not None:self.table.setCurrentIndex(self.model.index(index,0));self.table.selectRow(index)
        else:self.viewer.clear();self.identity.setText('当前筛选无任务');self.detail.clear()
        self.update_controls()

    def select_index(self,index,*args):
        self.image_revision+=1;self.viewer.clear();self.image_pending=False
        if not index.isValid() or index.row()>=len(self.model.rows):return
        t=self.model.rows[index.row()];self.selected_task_key=self.form_task_key=t['task_key']
        self.identity.setText(f"任务 {t['task_key']}\n{t['task_kind']} · {t['object_kind']} · {t['source']} / {t['object_id']}\n{t['priority']} · {', '.join(t['reasons'])}")
        records=latest(self.state) if self.state else {};history=[r for r in self.state['records'] if r['review_task_key']==t['task_key']] if self.state else []
        self.detail.setPlainText(json.dumps(dict(task=t,revision_history=history),ensure_ascii=False,indent=2))
        previous=records.get(t['task_key']);self.comment.setPlainText(previous.get('comment') or '' if previous else '')
        self.decision.blockSignals(True);self.decision.clear();self.decision.addItem('请选择人工结论（不预选）',None)
        for d in allowed_decisions(t['object_kind']):self.decision.addItem(d.value+' · '+LABELS[d.value],d.value)
        if previous:self.decision.setCurrentIndex(self.decision.findData(previous['decision']))
        self.decision.blockSignals(False);self.special.setChecked(False);self.other.setChecked(False)
        self.other.setVisible(bool(previous));self.other.setText('已有审核者 '+previous['reviewer']+'，确认以新revision追加' if previous else '另一审核者确认')
        spatial=t['evidence'].get('spatial_final_ids',[]) or []
        self.spatial.clear();self.spatial.addItem('spatial_final_ids：'+('无' if not spatial else '请选择查看'),None)
        for fid in spatial:self.spatial.addItem(str(fid),fid)
        self.target.clear();self.target.addItem('请选择现有Defect（不自动关联）',None)
        final_ids=[d.identity.defect_id for d in self.result_vm.defects]
        for fid in dict.fromkeys([*spatial,*final_ids]):
            if fid in final_ids and not (t['object_kind']=='DEFECT' and fid==t['object_id']):self.target.addItem(('空间关联 · ' if fid in spatial else '')+fid,fid)
        if previous and previous['target_defect_id']:self.target.setCurrentIndex(self.target.findData(previous['target_defect_id']))
        self.message.setText(('历史结论：'+previous['decision']+' · '+previous['reviewer']+' · revision '+str(previous['revision'])) if previous else 'PENDING · 尚未审核')
        self.update_controls();self.request_image()

    def update_controls(self,*args):
        busy=self.controller.busy
        eligibility=self.access.eligibility(self.context,self.stale)
        valid=self.state is not None and eligibility.can_submit_review and not self.raw_verifying and self.selected_task_key is not None
        self.evidence_status.setText(('结果状态：正式 Repository 结果' if eligibility.formal_result else '结果状态：临时检测结果')+' · '+('正在校验 RAW…' if self.raw_verifying else ('原始 RAW：已验证 · SHA256匹配' if eligibility.raw_verified else ('RAW 校验失败 · '+self.raw_error if self.raw_error else '原始 RAW：未关联')))+'\n'+eligibility.reason)
        self.attach.setEnabled(eligibility.formal_result and not busy);self.detach.setEnabled(eligibility.raw_verified and not busy)
        self.save.setEnabled(valid and not busy);self.start.setEnabled(self.admission is not None and eligibility.can_create_session and not busy)
        self.new.setEnabled(self.admission is not None and eligibility.can_create_session and not busy);self.table.setEnabled(not (self.own_job=='human_save' and busy))
        self.decision.setEnabled(valid and not busy);self.target.setEnabled(valid and not busy and self.decision.currentData()=='DUPLICATE_OF_EXISTING_DEFECT')
        self.jump.setEnabled(self.selected_task_key is not None)
        for widget in (self.reviewer,self.comment,self.special,self.other):widget.setEnabled(not (self.own_job=='human_save' and busy))

    def open_session(self,new_session=False):
        if self.controller.busy or not self.result_vm or not self.admission:return
        if not self.access.eligibility(self.context,self.stale).can_create_session:
            self.message.setText(self.access.eligibility(self.context,self.stale).reason);return
        name=self.reviewer.text().strip()
        if not name:self.message.setText('请明确填写当前审核者');return
        if new_session and not self.new_ack.isChecked():self.message.setText('请勾选另建会话确认，旧会话全部保留');return
        vm,admission,epoch=self.result_vm,self.admission,self.epoch
        def operation():
            context=ReviewContext.from_result(vm.result,admission,vm.review_access);guard=make_guard(vm.package_dir,context,vm.result);guard()
            state=self.repository.create(context,name,new_session=new_session)
            return epoch,context,state,guard
        self.own_job='human_session';self.controller.submit(self.own_job,operation)

    def busy_changed(self,busy):
        self.update_controls()
        if not busy:self.pump()

    def pump(self):
        if not self.active or self.controller.busy:return
        if self.restore_pending and self.result_vm and self.admission and self.access.eligibility().formal_result:
            self.restore_pending=False;vm,admission,epoch=self.result_vm,self.admission,self.epoch
            def restore():
                context=ReviewContext.from_result(vm.result,admission,vm.review_access);state=self.repository.load(context.result_id)
                return epoch,context,state,make_guard(vm.package_dir,context,vm.result)
            self.own_job='human_session';self.controller.submit(self.own_job,restore);return
        if self.image_pending and self.selected_task_key:
            self.image_pending=False;t=self.current_task();vm=self.result_vm;key=(self.epoch,self.selected_task_key,self.image_revision)
            raw=self.access.raw if self.access.eligibility(self.context,self.stale).raw_verified else None;margin=self.margin.currentData();show=self.nearby.isChecked()
            candidate=self.admission_page.queue_vm.candidates.get((t['source'],t['object_id'])) if t['object_kind']=='CANDIDATE' else None
            def image():
                if t['object_kind']=='DEFECT':model=DefectDetailViewModel(vm,t['object_id'])
                else:
                    c=candidate
                    model=CandidateDetailViewModel(vm,c) if c else None
                local=model.local_view(2,raw,margin=margin) if model else CandidateDetailViewModel.empty('无唯一候选，保留一致性任务')
                overlays=list(local.overlays)
                if show and t['object_kind']=='CANDIDATE':
                    x,y=local.origin
                    for fid in t['evidence'].get('spatial_final_ids',[]) or []:
                        if fid in vm.by_id:
                            b=vm.defects[vm.by_id[fid]].geometry.bbox
                            if b:overlays.append(Overlay('Final:'+fid,(b.x0-x,b.y0-y,b.x1-x,b.y1-y),(b.x0-x,b.y0-y,b.x1-x,b.y1-y),'UNKNOWN'))
                return key,LocalView(local.frame,tuple(overlays),local.origin,local.source)
            self.own_job='human_image';self.controller.submit(self.own_job,image)

    def current_task(self):
        return next((t for t in (self.state['tasks'] if self.state else self.tasks) if t['task_key']==self.selected_task_key),None)

    def request_image(self,*args):
        if self.stale:
            self.image_revision+=1;self.image_pending=False;self.viewer.clear();self.image_status.setText('历史会话与当前上下文不匹配，局部图暂停，历史证据仍可读');return
        self.image_revision+=1;self.image_pending=self.selected_task_key is not None;self.viewer.clear();self.pump()

    def save_next(self):
        if self.controller.busy or not self.state or self.stale:return
        if self.raw_verifying or not self.access.eligibility(self.context,self.stale).can_submit_review:
            self.message.setText(self.access.eligibility(self.context,self.stale).reason);return
        key=self.form_task_key
        if not key or key!=self.selected_task_key:self.message.setText('任务身份已变化，请重新选择');return
        if self.decision.currentData() is None:self.message.setText('请选择人工结论');return
        context,session,epoch=self.context,self.state['session_id'],self.epoch
        previous=latest(self.state).get(key);expected=previous['revision'] if previous else 0
        selected=self.selected_task_key
        args=dict(selected_task_key=selected,expected_revision=expected,target_defect_id=self.target.currentData() if self.decision.currentData()=='DUPLICATE_OF_EXISTING_DEFECT' else None,
                  comment=self.comment.toPlainText() or None,acknowledge_previous_reviewer=self.other.isChecked(),acknowledge_special=self.special.isChecked(),guard=self.guard)
        decision,name=self.decision.currentData(),self.reviewer.text()
        def operation():
            if self.epoch!=epoch or self.selected_task_key!=key:raise ValueError('selected task identity changed')
            return epoch,key,self.repository.submit(context,session,key,decision,name,**args)
        self.own_job='human_save';self.controller.submit(self.own_job,operation)

    @guarded_completion
    def completed(self,kind,value):
        if kind=='human_raw':
            epoch,result_id,revision,binding,error=value
            if epoch!=self.epoch or revision!=self.raw_revision or not self.result_vm or result_id!=self.result_vm.result.result_id:
                if binding:binding.clear()
                return
            self.raw_verifying=False
            if error:self.raw_error=error;self.message.setText(error);self.update_controls();return
            self.install_raw(binding);return
        if kind=='admission_result':self.bind_admission();return
        if kind=='human_session':
            epoch,context,state,guard=value
            if epoch!=self.epoch:return
            self.selected_task_key=None;self.context,self.state,self.guard=context,state,guard;self.stale=mismatch(state,context) if state else None
            self.new_ack.setChecked(False);self.refresh();self.message.setText((self.stale+' · 历史会话只读') if self.stale else '会话已恢复；从首个PENDING继续。提交时使用当前明确填写的审核者。')
        elif kind=='human_save':
            epoch,key,state=value
            if epoch!=self.epoch:return
            self.state=state;self.selected_task_key=None;self.refresh();self.message.setText('已原子保存 · 全部revision保留')
        elif kind=='human_image':
            key,local=value
            if not self.active or key!=(self.epoch,self.selected_task_key,self.image_revision):return
            self.viewer.set_frame(local.frame,fit=True);self.viewer.set_overlays(local.overlays)
            for name,item in self.viewer.overlays.items():
                pen=QPen(QColor('#00d5ef' if name=='Candidate' else '#ffd34d'));pen.setWidthF(1.5);pen.setCosmetic(True);item.setPen(pen)
            self.image_status.setText(('真实 RAW 像素 · SHA256 已校验' if self.access.eligibility(self.context,self.stale).raw_verified and 'RAW' in local.source else local.source)+' · 仅显示裁剪/外扩，不改测量')
        elif kind=='human_export':self.message.setText('人工审核最小导出完成（独立于正式结果包）')

    def failed(self,message):
        if self.own_job and self.own_job.startswith('human_') and getattr(self.controller,'_kind',None)==self.own_job:
            if self.own_job=='human_raw':self.raw_verifying=False;self.raw_error=message
            if 'POLICY_MISMATCH' in message:self.stale='POLICY_MISMATCH'
            elif 'RESULT_MISMATCH' in message or 'RESULT_INTEGRITY_FAILED' in message:self.stale='RESULT_MISMATCH'
            self.message.setText(message);self.update_controls()

    def choose_raw(self):
        if self.controller.busy or not self.access.eligibility().formal_result:return
        path,_=QFileDialog.getOpenFileName(self,'关联原始 RAW（只读，必须匹配SHA256）','','RAW (*.raw);;所有文件 (*)')
        if path:self.attach_raw(path)

    def attach_raw(self,path):
        if self.controller.busy or not self.result_vm or not self.access.eligibility().formal_result:return False
        # Rejecting a replacement must never leave an older verified evidence active.
        self.detach_raw(refresh=False);self.raw_revision+=1;revision=self.raw_revision
        epoch,result_id,result=self.epoch,self.result_vm.result.result_id,self.result_vm.result
        self.raw_verifying=True;self.own_job='human_raw'
        def operation():
            try:return epoch,result_id,revision,validate_raw(path,result),None
            except Exception as exc:
                failure=classify_error(exc,'human_raw')
                self.controller.application_log.event(logging.ERROR,'human_raw',failure.code,'RAW证据校验失败',exc=exc,result_id=result_id,operation_id=self.controller.operation_id)
                return epoch,result_id,revision,None,failure.user_message
        return self.controller.submit(self.own_job,operation)

    def install_raw(self,binding):
        formal=self.access.formal_binding
        if not formal or (binding.result_id,binding.source_digest)!=(formal.result_id,formal.source_digest):
            binding.clear();return
        self.raw_error=None;self.access.raw=binding
        window=self.window()
        if hasattr(window,'raw'):
            if window.raw is not None and window.raw is not binding:window.raw.clear()
            window.raw=binding;window.viewer.raw_provider=binding
        self.raw_verifying=False;self.update_controls();self.request_image()

    def detach_raw(self,checked=False,*,refresh=True):
        self.raw_revision+=1;self.raw_verifying=False;self.raw_error=None
        self.viewer.clear();self.image_pending=False
        self.image_status.setText('RAW 未关联 · 仅可查看任务证据，不可提交人工结论')
        previous=self.access.raw
        self.access.raw=None
        if previous:
            window=self.window()
            if getattr(window,'raw',None) is previous:
                window.raw=None;window.viewer.raw_provider=None
                if hasattr(window,'detail_page'):window.detail_page.raw=None
            previous.clear()
        self.image_revision+=1
        if refresh:self.update_controls();self.request_image()

    def jump_final(self,fid):
        if self.result_vm and fid in self.result_vm.by_id:self.defect_requested.emit(fid)

    def jump_selected(self):
        t=self.current_task()
        if not t:return
        if t['object_kind']=='DEFECT':self.defect_requested.emit(t['object_id'])
        else:self.candidate_requested.emit((t['source'],t['object_id']))

    def export(self,format):
        if self.controller.busy or not self.state:return
        path,_=QFileDialog.getSaveFileName(self,'导出独立人工审核记录','human_review.'+format,format.upper()+' (*.'+format+')')
        if path:
            state=self.state;self.own_job='human_export';self.controller.submit(self.own_job,lambda:self.repository.export(state,path,format))

    def show_statistics(self):
        dialog=QDialog(self);dialog.setWindowTitle('人工审核统计 · 不改变原算法疵病统计');dialog.resize(1000,720)
        layout=QVBoxLayout(dialog)
        label=QLabel('仅反映准入任务的人工处理情况，不代表整体准确率 / 召回率。UNCERTAIN计入已处理并单独统计。')
        label.setWordWrap(True);layout.addWidget(label)
        view=QPlainTextEdit();view.setReadOnly(True)
        value=summary(self.state,self.stale) if self.state else {'pending':len(self.tasks),'records':0,'message':'尚未创建人工会话'}
        view.setPlainText(json.dumps(value,ensure_ascii=False,indent=2));layout.addWidget(view)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons);dialog.exec()

    def eventFilter(self,obj,event):
        if event.type() in (QEvent.Type.ShortcutOverride,QEvent.Type.KeyPress) and self.active and not self.controller.busy:
            key=event.key()
            if Qt.Key.Key_1<=key<=Qt.Key.Key_5 or key in (Qt.Key.Key_Return,Qt.Key.Key_Enter):
                event.accept()
                if event.type()==QEvent.Type.KeyPress:
                    if key in (Qt.Key.Key_Return,Qt.Key.Key_Enter):self.save_next()
                    else:
                        value=list(HumanReviewDecision)[key-Qt.Key.Key_1].value;index=self.decision.findData(value)
                        if index>=0:self.decision.setCurrentIndex(index)
                return True
        return super().eventFilter(obj,event)


class HumanReviewWorkspace(QTabWidget):
    def __init__(self,controller,admission_page,parent=None):
        super().__init__(parent);self.review_page=HumanReviewPage(controller,admission_page);self.active=False
        self.addTab(self.review_page,'复核队列');self.addTab(admission_page,'准入统计')
        self.currentChanged.connect(lambda _:self.review_page.set_active(self.active and self.currentIndex()==0))
    def set_active(self,active):self.active=active;self.review_page.set_active(active and self.currentIndex()==0)
