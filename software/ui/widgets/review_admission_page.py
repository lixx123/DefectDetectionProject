"""Runtime-only admission workspace; evaluation, querying, and selected crops use workers."""
import json
from ui.runtime_errors import guarded_completion
from PySide6.QtCore import Qt,Signal,QModelIndex
from PySide6.QtGui import QColor,QPen
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QPushButton,QTableView,
    QPlainTextEdit,QSplitter,QAbstractItemView,QHeaderView,QGroupBox)
from ui.models.review_admission import ReviewAdmissionEngine,load_policy,ReviewBucket
from ui.models.review_admission.model import ReviewTask
from ui.models.review_admission.rules import REASON_DESCRIPTIONS
from ui.models.review_queue_view_model import ReviewQueueViewModel,ReviewQueueQuery,ReviewQueueTableModel,object_key,row_key,sources
from ui.models.defect_detail_view_model import DefectDetailViewModel
from ui.models.candidate_detail_view_model import CandidateDetailViewModel
from ui.image_viewer import ImageViewer


class ReviewAdmissionPage(QWidget):
    defect_requested=Signal(str)
    candidate_requested=Signal(object)
    def __init__(self,controller,parent=None):
        super().__init__(parent);self.controller=controller;self.result_vm=None;self.queue_vm=None
        self.active=False;self.epoch=0;self.query_revision=0;self.image_revision=0
        self.evaluate_pending=self.query_pending=self.image_pending=False
        self.selected_key=None;self.selected_row=None;self.local_vm=None;self.query=ReviewQueueQuery()
        self.sort_column=3;self.descending=False
        self._build()
        controller.completed.connect(self.completed)
        controller.busy_changed.connect(lambda busy:None if busy else self.pump())
        controller.error.connect(self.failed)

    def _build(self):
        layout=QVBoxLayout(self)
        self.heading=QLabel('人工复核准入 · 当前仅生成复核建议队列，尚未执行人工审核。')
        self.heading.setWordWrap(True);self.heading.setStyleSheet('font-size:17px;font-weight:600');layout.addWidget(self.heading)
        self.policy=QLabel('Review Admission Policy: v1 · 待加载');self.policy.setWordWrap(True);layout.addWidget(self.policy)
        self.summary=QLabel('暂无检测结果');self.summary.setStyleSheet('font-size:16px;font-weight:600');self.summary.setWordWrap(True);layout.addWidget(self.summary)
        cards=QHBoxLayout();self.cards={}
        for bucket in ReviewBucket:
            group=QGroupBox(bucket.value);gl=QVBoxLayout(group);label=QLabel('Defect 0 · Candidate 0');gl.addWidget(label);cards.addWidget(group);self.cards[bucket]=label
        layout.addLayout(cards)
        self.warning=QLabel('');self.warning.setWordWrap(True);self.warning.setStyleSheet('color:#b91c1c;font-weight:600');layout.addWidget(self.warning)
        filters=QHBoxLayout();self.view=QComboBox();self.view.addItem('人工工作队列（ReviewTask）','TASKS')
        for b in ReviewBucket:self.view.addItem(b.value+' 对象',b.value)
        filters.addWidget(QLabel('查看'));filters.addWidget(self.view);self.view.currentIndexChanged.connect(self.request_query)
        self.filters={}
        for name,label in [('kind','对象类型'),('priority','优先级'),('reason','原因'),('band','Band'),('source','Source')]:
            combo=QComboBox();combo.addItem('全部',None);combo.setMaximumWidth(220)
            self.filters[name]=combo;filters.addWidget(QLabel(label));filters.addWidget(combo)
            combo.currentIndexChanged.connect(self.request_query)
        clear=QPushButton('清除筛选');clear.clicked.connect(self.clear_filters);filters.addWidget(clear);filters.addStretch();layout.addLayout(filters)
        split=QSplitter(Qt.Orientation.Horizontal)
        left=QWidget();ll=QVBoxLayout(left);ll.setContentsMargins(0,0,0,0)
        self.model=ReviewQueueTableModel(self);self.table=QTableView();self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.setAlternatingRowColors(True);self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for i,width in enumerate((50,95,190,80,280,110,100,65,100,170)):self.table.setColumnWidth(i,width)
        self.table.setSortingEnabled(True);self.table.horizontalHeader().setSortIndicator(3,Qt.SortOrder.AscendingOrder)
        self.table.selectionModel().currentRowChanged.connect(self.row_selected);ll.addWidget(self.table,1)
        paging=QHBoxLayout();self.previous=QPushButton('上一页');self.next=QPushButton('下一页');self.page_status=QLabel()
        self.previous.clicked.connect(lambda:self.change_page(-1));self.next.clicked.connect(lambda:self.change_page(1))
        paging.addWidget(self.previous);paging.addWidget(self.next);paging.addWidget(self.page_status,1);ll.addLayout(paging);split.addWidget(left)
        right=QWidget();rl=QVBoxLayout(right);rl.setContentsMargins(4,0,0,0)
        self.position=QLabel('请选择一个任务或派生对象');self.position.setWordWrap(True);rl.addWidget(self.position)
        self.jump=QPushButton('跳转原始详情');self.jump.setEnabled(False);self.jump.clicked.connect(self.jump_selected);rl.addWidget(self.jump)
        self.image_status=QLabel('局部图只在当前选中对象时加载');self.image_status.setWordWrap(True);rl.addWidget(self.image_status)
        self.viewer=ImageViewer();self.viewer.setMinimumSize(300,190);rl.addWidget(self.viewer,2)
        self.details=QPlainTextEdit();self.details.setReadOnly(True);rl.addWidget(self.details,3)
        rl.addWidget(QLabel('优先级是复核紧急度，不等同于尺寸等级或严重度。'))
        split.addWidget(right);split.setSizes([1130,500]);split.setStretchFactor(0,3);split.setStretchFactor(1,1)
        layout.addWidget(split,1);self.model.sort_requested.connect(self.sort);self.refresh_page()

    def set_result(self,result_vm):
        self.epoch+=1;self.query_revision+=1;self.image_revision+=1;self.result_vm=result_vm;self.queue_vm=None
        self.evaluate_pending=result_vm is not None;self.query_pending=self.image_pending=False
        self.selected_key=self.selected_row=self.local_vm=None;self.model.set_rows(())
        self.viewer.clear();self.details.clear();self.position.setText('请选择一个任务或派生对象');self.jump.setEnabled(False)
        self.heading.setText('人工复核准入 · 当前仅生成复核建议队列，尚未执行人工审核。' + (f' · {result_vm.result.input_info.file_name}' if result_vm else ''))
        self.summary.setText('在后台生成只读准入建议…' if result_vm else '暂无检测结果')
        self.warning.setText('');self.policy.setText('Review Admission Policy: v1 · 待加载');self.image_status.setText('局部图只在当前选中对象时加载')
        for label in self.cards.values():label.setText('Defect 0 · Candidate 0')
        self.view.blockSignals(True);self.view.setCurrentIndex(0);self.view.blockSignals(False)
        for combo in self.filters.values():combo.blockSignals(True);combo.clear();combo.addItem('全部',None);combo.blockSignals(False)
        self.refresh_page();self.pump()

    def set_active(self,active):
        self.active=active
        if not active:self.image_revision+=1
        elif self.local_vm:self.image_pending=True
        self.pump()

    def pump(self):
        if not self.active or self.controller.busy or self.result_vm is None:return
        epoch=self.epoch
        if self.evaluate_pending:
            self.evaluate_pending=False;result=self.result_vm.result
            def evaluate():
                config=load_policy();admission=ReviewAdmissionEngine().evaluate(result,config)
                return epoch,ReviewQueueViewModel(admission,result.audit_log.candidates)
            self.controller.submit('admission_result',evaluate);return
        if self.query_pending and self.queue_vm:
            self.query_pending=False;q=self.query;vm=self.queue_vm;revision=self.query_revision
            self.controller.submit('admission_query',lambda:(epoch,revision,vm.query(q)));return
        if self.image_pending and self.local_vm:
            self.image_pending=False;request=self.image_key();vm=self.local_vm
            raw=getattr(self.window(),'raw',None);mode=2 if object_key(self.selected_row).kind=='DEFECT' else 1
            self.image_status.setText('正在加载当前对象局部资源…')
            self.controller.submit('admission_frame',lambda:(request,vm.local_view(mode,raw)))

    @guarded_completion
    def completed(self,kind,payload):
        if kind=='admission_result':
            epoch,vm=payload
            if epoch!=self.epoch:return
            self.queue_vm=vm;self.populate();self.request_query()
        elif kind=='admission_query':
            epoch,revision,rows=payload
            if epoch!=self.epoch or revision!=self.query_revision:return
            self.model.set_rows(rows)
            if self.selected_key is not None and not any(row_key(row)==self.selected_key for row in rows):self.clear_selection()
            self.restore_selection();self.refresh_page()
        elif kind=='admission_frame':
            request,local=payload
            if request!=self.image_key() or not self.active:return
            self.viewer.set_frame(local.frame,fit=True);self.viewer.set_overlays(local.overlays)
            if 'Candidate' in self.viewer.overlays:
                pen=QPen(QColor('#22d3ee'),2);pen.setCosmetic(True);self.viewer.overlays['Candidate'].setPen(pen)
            self.image_status.setText(f'{local.source} · 原图坐标原点 {local.origin}' + (' · '+local.frame.message if local.frame.message else ''))

    def populate(self):
        a=self.queue_vm.admission;s=a.summary
        self.policy.setText(f'Review Admission Policy: v1 · {a.policy_id} / {a.policy_version} · SHA256 {a.policy_hash}')
        ratio=s['audit_review_to_manual_task_compression_ratio'];ratio_text=f'{ratio:.2f} : 1' if ratio is not None else '—（无人工任务）'
        self.summary.setText(f'Audit REVIEW 候选：{s["audit_review_count"]:,}    真正人工待复核任务：{s["manual_review_task_count"]:,}    压缩比：{ratio_text}\nDefect 任务 {s["manual_review_defect_tasks"]} · Candidate 任务 {s["manual_review_candidate_tasks"]}（含一致性任务 {s["candidate_consistency_tasks"]}）· 建议目标 ≤ {s["preferred_max"]}：{"达标" if s["preferred_max_met"] else "TARGET_NOT_MET，全部保留"}')
        for bucket,label in self.cards.items():
            counts=s['bucket_counts'][bucket];label.setText(f'Defect {counts["DEFECT"]:,} · Candidate {counts["CANDIDATE"]:,}')
        self.warning.setText('\n'.join(a.warnings))
        values=dict(kind={'DEFECT','CANDIDATE'},priority={'HIGH','MEDIUM','LOW'},reason=set(),band=set(),source=set())
        for row in a.decisions:
            values['reason'].update(row.reasons);values['band'].add(row.evidence['band'] or '—');values['source'].update(sources(row))
        for name,combo in self.filters.items():
            combo.blockSignals(True);combo.clear();combo.addItem('全部',None)
            for v in (('HIGH','MEDIUM','LOW') if name=='priority' else sorted(values[name])):combo.addItem(v,v)
            combo.blockSignals(False)

    def request_query(self,*args):
        self.query_revision+=1
        self.query=ReviewQueueQuery(view=self.view.currentData(),**{name:combo.currentData() for name,combo in self.filters.items()},sort_column=self.sort_column,descending=self.descending)
        self.query_pending=self.queue_vm is not None;self.table.setEnabled(False);self.refresh_page();self.pump()

    def clear_filters(self):
        for combo in self.filters.values():combo.blockSignals(True);combo.setCurrentIndex(0);combo.blockSignals(False)
        self.request_query()

    def sort(self,column,descending):
        self.sort_column=column;self.descending=descending
        h=self.table.horizontalHeader();h.blockSignals(True);h.setSortIndicator(column,Qt.SortOrder.DescendingOrder if descending else Qt.SortOrder.AscendingOrder);h.blockSignals(False)
        self.request_query()

    def refresh_page(self):
        m=self.model;self.page_status.setText(f'第 {m.page+1 if m.pages else 0} / {m.pages} 页 · 当前匹配 {len(m.rows):,} · 每页 {m.page_size}')
        self.previous.setEnabled(m.page>0 and not self.query_pending);self.next.setEnabled(m.page+1<m.pages and not self.query_pending);self.table.setEnabled(not self.query_pending)

    def change_page(self,step):
        self.model.set_rows(self.model.rows,self.model.page+step);self.restore_selection();self.refresh_page()

    def restore_selection(self):
        self.table.selectionModel().blockSignals(True);self.table.clearSelection();self.table.setCurrentIndex(QModelIndex())
        for i in range(self.model.rowCount()):
            if row_key(self.model.row(i))==self.selected_key:
                index=self.model.index(i,0);self.table.setCurrentIndex(index);self.table.selectRow(i);self.table.scrollTo(index);break
        self.table.selectionModel().blockSignals(False)

    def row_selected(self,current,previous):
        if current.isValid():self.select_row(self.model.row(current.row()))

    def clear_selection(self):
        self.image_revision+=1;self.image_pending=False
        self.selected_key=self.selected_row=self.local_vm=None
        self.viewer.clear();self.details.clear();self.position.setText('请选择一个任务或派生对象')
        self.jump.setEnabled(False);self.image_status.setText('局部图只在当前选中对象时加载')

    def select_row(self,row):
        self.image_revision+=1;self.image_pending=False;self.selected_row=row;self.selected_key=row_key(row)
        k=object_key(row);self.viewer.clear();self.local_vm=None
        self.position.setText(f'{k.kind} · {k.object_id}' + (f' · Source {k.candidate_source}' if k.kind=='CANDIDATE' else ''))
        self.jump.setText('跳转疵病详情' if k.kind=='DEFECT' else '跳转检测过程 / 审计');self.jump.setEnabled(True)
        self.details.setPlainText(json.dumps(dict(primary_object=dict(kind=k.kind,defect_id=k.defect_id,candidate_source=k.candidate_source,candidate_id=k.candidate_id),
            task_kind=row.task_kind if isinstance(row,ReviewTask) else 'BUCKET_DECISION',priority=row.priority,
            bucket='MANUAL_REVIEW' if isinstance(row,ReviewTask) else row.bucket,reasons=row.reasons,
            reason_explanations={reason:REASON_DESCRIPTIONS.get(reason,reason) for reason in row.reasons},evidence=dict(row.evidence),
            related_candidates=row.related_candidates if isinstance(row,ReviewTask) else ()),ensure_ascii=False,indent=2))
        if k.kind=='DEFECT' and k.defect_id in self.result_vm.by_id:self.local_vm=DefectDetailViewModel(self.result_vm,k.defect_id)
        elif k.kind=='CANDIDATE':
            candidate=self.queue_vm.candidates.get((k.candidate_source,k.candidate_id))
            if candidate is not None:self.local_vm=CandidateDetailViewModel(self.result_vm,candidate)
        if self.local_vm:self.image_pending=True;self.pump()
        else:self.image_status.setText('对象无法唯一解析或局部资源不可用')

    def image_key(self):return self.epoch,self.selected_key,self.image_revision

    def jump_selected(self):
        if self.selected_row is None:return
        k=object_key(self.selected_row)
        if k.kind=='DEFECT':self.defect_requested.emit(k.defect_id)
        else:self.candidate_requested.emit((k.candidate_source,k.candidate_id))

    def failed(self,message):
        if self.active:self.image_status.setText(message)
