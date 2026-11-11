"""Read-only audit workbench. Index/query and selected-image jobs use the shared worker."""
import json
from ui.runtime_errors import guarded_completion
from PySide6.QtCore import Qt, Signal, QTimer, QAbstractTableModel, QModelIndex
from PySide6.QtGui import QPen, QColor
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QLineEdit,
    QTableView,QSplitter,QTabWidget,QScrollArea,QFormLayout,QPlainTextEdit,QAbstractItemView,QHeaderView)
from ui.models.audit_view_model import AuditViewModel,AuditQuery,key
from ui.models.candidate_audit_table_model import CandidateAuditTableModel,CandidateSelectionController
from ui.models.candidate_detail_view_model import CandidateDetailViewModel
from ui.models.result_view_model import shown
from ui.image_viewer import ImageViewer
from .statistics_page import CountChart
from domain.serialization import to_dict


class EventTableModel(QAbstractTableModel):
    def __init__(self,parent=None):
        super().__init__(parent);self.events=()
    def set_events(self,events):
        self.beginResetModel();self.events=events;self.endResetModel()
    def rowCount(self,parent=QModelIndex()):return 0 if parent.isValid() else len(self.events)
    def columnCount(self,parent=QModelIndex()):return 0 if parent.isValid() else 5
    def headerData(self,section,orientation,role=Qt.ItemDataRole.DisplayRole):
        if orientation==Qt.Orientation.Horizontal and role==Qt.ItemDataRole.DisplayRole:
            return ('序号','时间（若提供）','Stage','Type','Message')[section]
    def data(self,index,role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role!=Qt.ItemDataRole.DisplayRole:return None
        event=self.events[index.row()]
        if index.column()==0:return str(index.row()+1)
        keys=(('time','timestamp','started_at'),('stage',),('type','event_type','name'),('message','reason'))[index.column()-1]
        return shown(next((event[k] for k in keys if k in event),None))


class AuditPage(QWidget):
    final_requested=Signal(str)
    def __init__(self,controller,parent=None):
        super().__init__(parent)
        self.controller=controller;self.result_vm=None;self.audit=None;self.active=False
        self.epoch=0;self.query_revision=0;self.image_revision=0
        self.index_pending=self.query_pending=self.image_pending=False
        self.query=AuditQuery();self.selection=CandidateSelectionController(self);self.detail_vm=None
        self.sort_column=1;self.descending=False;self.final_filter=None;self.current_final=None
        self.reveal_key=None;self.pending_focus=None
        self._build()
        self.controller.completed.connect(self.completed)
        self.controller.busy_changed.connect(lambda busy:None if busy else self.pump())
        self.selection.changed.connect(self.select_candidate)
        self.controller.error.connect(self.failed)

    def _build(self):
        layout=QVBoxLayout(self)
        self.heading=QLabel('检测过程 / 候选审计 · 只读展示，不提供人工审核或结果修改')
        self.heading.setStyleSheet('font-size:16px;font-weight:600');self.heading.setWordWrap(True);layout.addWidget(self.heading)
        self.execution=QLabel('暂无检测结果');self.execution.setWordWrap(True);layout.addWidget(self.execution)
        self.summary=QLabel('来源候选 — · 审计记录 0 · 审计链完整：否');layout.addWidget(self.summary)
        self.warning=QLabel('');self.warning.setWordWrap(True);self.warning.setStyleSheet('color:#b91c1c;font-weight:600');layout.addWidget(self.warning)
        self.sections=QTabWidget()
        candidates=QWidget();cl=QVBoxLayout(candidates);cl.setContentsMargins(0,4,0,0)
        row=QHBoxLayout();self.filters={}
        for name,label in [('disposition','Disposition'),('reason','Filter Reason'),('source','Source'),('stage','Stage'),('linked','关联')]:
            combo=QComboBox();combo.setMinimumWidth(85);combo.addItem('全部',None)
            row.addWidget(QLabel(label));row.addWidget(combo);self.filters[name]=combo
            combo.currentIndexChanged.connect(self.request_query)
        self.search=QLineEdit();self.search.setPlaceholderText('搜索 Candidate ID（忽略大小写）');self.search.setMinimumWidth(175)
        row.addWidget(self.search,1)
        self.debounce=QTimer(self);self.debounce.setSingleShot(True);self.debounce.setInterval(200)
        self.search.textChanged.connect(lambda:self.debounce.start());self.debounce.timeout.connect(self.request_query)
        reset=QPushButton('清除筛选');reset.clicked.connect(self.clear_filters);row.addWidget(reset);cl.addLayout(row)
        reverse=QHBoxLayout();self.reverse=QPushButton('只看当前最终疵病来源候选');self.reverse.clicked.connect(self.reverse_current)
        self.lineage=QLabel('请先选择最终疵病');self.lineage.setWordWrap(True)
        reverse.addWidget(self.reverse);reverse.addWidget(self.lineage,1);cl.addLayout(reverse)
        split=QSplitter(Qt.Orientation.Horizontal)
        left=QWidget();ll=QVBoxLayout(left);ll.setContentsMargins(0,0,0,0)
        self.model=CandidateAuditTableModel(self);self.table=QTableView();self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True);self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide();self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for col,width in enumerate((52,210,85,150,100,150,140,140,110,110)):self.table.setColumnWidth(col,width)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSortIndicator(1,Qt.SortOrder.AscendingOrder)
        self.table.selectionModel().currentRowChanged.connect(self.row_selected)
        ll.addWidget(self.table,1)
        paging=QHBoxLayout();self.previous=QPushButton('上一页');self.next=QPushButton('下一页')
        self.previous.clicked.connect(lambda:self.change_page(-1));self.next.clicked.connect(lambda:self.change_page(1))
        self.size=QComboBox();self.size.addItems(['200','500','1000']);self.size.setCurrentText('500');self.size.currentTextChanged.connect(self.page_size_changed)
        self.page_status=QLabel();paging.addWidget(self.previous);paging.addWidget(self.next);paging.addWidget(QLabel('每页'));paging.addWidget(self.size);paging.addWidget(self.page_status,1)
        ll.addLayout(paging);split.addWidget(left)
        right=QWidget();rl=QVBoxLayout(right);rl.setContentsMargins(4,0,0,0)
        self.position=QLabel('请选择候选');self.position.setWordWrap(True);rl.addWidget(self.position)
        actions=QHBoxLayout();self.jump_final=QPushButton('跳转到最终疵病');self.jump_merged=QPushButton('跳转合并目标')
        self.jump_final.clicked.connect(self.to_final);self.jump_merged.clicked.connect(self.to_merged)
        actions.addWidget(self.jump_final);actions.addWidget(self.jump_merged);rl.addLayout(actions)
        self.detail_warning=QLabel();self.detail_warning.setWordWrap(True);self.detail_warning.setStyleSheet('color:#b91c1c');rl.addWidget(self.detail_warning)
        self.mode=QComboBox();self.mode.addItems(['原始灰度','灰度 + 候选初始框','灰度 + 候选初始框 + 关联最终框']);self.mode.setCurrentIndex(1)
        self.mode.currentIndexChanged.connect(self.request_image);rl.addWidget(self.mode)
        self.image_status=QLabel('局部图按需加载');self.image_status.setWordWrap(True);rl.addWidget(self.image_status)
        self.legend=QLabel('青色实线：候选显示框（可放大） · 红色虚线：关联最终测量框')
        self.legend.setWordWrap(True);rl.addWidget(self.legend)
        self.viewer=ImageViewer();self.viewer.setMinimumSize(290,160);rl.addWidget(self.viewer,2)
        fields_widget=QWidget();form=QFormLayout(fields_widget);self.fields={}
        names=('candidate_id','source','current_stage','disposition','filter_reason','filter_message','merged_into','final_defect_id',
               'bbox（初始测量）','center','area_px','area_um2','length_px','length_um','width_px','width_um','equivalent_diameter_px','equivalent_diameter_um')
        for name in names:
            label=QLabel('—');label.setWordWrap(True);label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow(name,label);self.fields[name]=label
        self.extensions=QPlainTextEdit();self.extensions.setReadOnly(True);self.extensions.setMaximumHeight(110)
        form.addRow('原始 extensions',self.extensions)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(fields_widget);rl.addWidget(scroll,3)
        split.addWidget(right);split.setSizes([1120,480]);split.setStretchFactor(0,3);split.setStretchFactor(1,1)
        cl.addWidget(split,1);self.sections.addTab(candidates,'候选表 / 详情')
        stats=QWidget();sl=QVBoxLayout(stats);sl.addWidget(QLabel('候选最终去向 · 全量审计记录统计（不是阶段流水线，不受筛选或分页影响）'))
        charts=QHBoxLayout();self.charts={}
        for name,title in [('disposition','CandidateDisposition 数量'),('reason','仅 FILTERED 的 FilterReason 数量')]:
            box=QWidget();bl=QVBoxLayout(box);bl.addWidget(QLabel(title));chart=CountChart();self.charts[name]=chart;bl.addWidget(chart);charts.addWidget(box)
        sl.addLayout(charts,1);self.counts=QPlainTextEdit();self.counts.setReadOnly(True);sl.addWidget(self.counts,1)
        self.sections.addTab(stats,'全量去向统计')
        self.execution_detail=QPlainTextEdit();self.execution_detail.setReadOnly(True);self.sections.addTab(self.execution_detail,'运行 Attempts / QA')
        events=QWidget();el=QVBoxLayout(events);self.event_status=QLabel('暂无事件');el.addWidget(self.event_status)
        self.event_model=EventTableModel(self);self.event_table=QTableView();self.event_table.setModel(self.event_model)
        self.event_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.event_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.event_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.event_json=QPlainTextEdit();self.event_json.setReadOnly(True)
        self.event_table.selectionModel().currentRowChanged.connect(self.show_event)
        el.addWidget(self.event_table,1);el.addWidget(self.event_json,1);self.sections.addTab(events,'审计事件')
        layout.addWidget(self.sections,1);self.model.sort_requested.connect(self.sort);self.refresh_page()
        self.select_candidate(None)

    def set_result(self, result_vm):
        self.epoch+=1;self.query_revision+=1;self.image_revision+=1
        self.result_vm=result_vm;self.audit=None;self.index_pending=result_vm is not None
        self.query_pending=self.image_pending=False;self.final_filter=None;self.current_final=None
        self.reveal_key=None;self.pending_focus=None
        self.heading.setText('检测过程 / 候选审计 · 只读展示，不提供人工审核或结果修改' + (f' · {result_vm.result.input_info.file_name}' if result_vm else ''))
        self.selection.set(None);self.select_candidate(None);self.model.set_query(None,())
        self.clear_filters();self.refresh_page();self.warning.setText('');self.lineage.setText('请先选择最终疵病')
        self.execution.setText('暂无检测结果' if result_vm is None else '正在准备只读审计索引…')
        self.summary.setText('审计记录 0' if result_vm is None else '索引在审计页活动时由后台构建')
        self.execution_detail.clear();self.counts.clear();self.event_model.set_events(());self.event_json.clear();self.event_status.setText('暂无事件')
        for chart in self.charts.values():chart.set_rows([])
        self.pump()

    def set_active(self, active):
        self.active=active
        if not active:self.image_revision+=1
        else:
            if self.detail_vm:self.image_pending=True
            self.pump()

    def pump(self):
        if not self.active or self.controller.busy or self.result_vm is None:return
        epoch=self.epoch
        if self.index_pending:
            result=self.result_vm.result;self.index_pending=False
            self.controller.submit('audit_index',lambda:(epoch,AuditViewModel(result)));return
        if self.query_pending and self.audit is not None:
            audit=self.audit;q=self.query;revision=self.query_revision;self.query_pending=False
            self.controller.submit('audit_query',lambda:(epoch,revision,audit.query(q)));return
        if self.image_pending and self.detail_vm is not None:
            request=self.image_key();detail=self.detail_vm;mode=self.mode.currentIndex();raw=self.raw_provider()
            self.image_pending=False;self.image_status.setText('正在加载当前候选局部资源…')
            self.controller.submit('candidate_frame',lambda:(request,detail.local_view(mode,raw)))

    def raw_provider(self):
        return getattr(self.window(),'raw',None)

    @guarded_completion
    def completed(self, kind, payload):
        if kind=='audit_index':
            epoch,audit=payload
            if epoch!=self.epoch:return
            self.audit=audit;self.populate();self.request_query()
            if self.pending_focus is not None:self.focus_candidate(self.pending_focus)
        elif kind=='audit_query':
            epoch,revision,indexes=payload
            if epoch!=self.epoch or revision!=self.query_revision:return
            self.model.set_query(self.audit,indexes)
            if self.reveal_key is not None:
                row=self.audit.by_key.get(self.reveal_key)
                if row in indexes:self.model.set_page(indexes.index(row)//self.model.page_size)
                self.reveal_key=None
            self.restore_selection();self.refresh_page()
            if self.detail_vm:self.image_pending=True
        elif kind=='candidate_frame':
            request,local=payload
            if request!=self.image_key() or not self.active:return
            self.apply_local(local)

    def populate(self):
        a=self.audit;r=a.result;e=r.execution_info;s=a.summary()
        attempts=' → '.join(f'{i+1}. {x.mode} [{x.status}; QA {x.qa_status}; {shown(x.reason)}]' for i,x in enumerate(e.attempts)) or '无实际 attempt 记录'
        self.execution.setText(f'请求：{e.requested_mode} · 实际尝试：{attempts}\n最终：{shown(e.final_mode)} · 回退：{"是" if e.fallback_used else "否"} · 原因：{shown(e.fallback_reason)} · 状态：{e.status} · QA：{e.qa_status}')
        self.execution_detail.setPlainText(json.dumps(to_dict(e),ensure_ascii=False,indent=2))
        self.summary.setText(f'来源声明：{shown(s["source_candidate_count"])} · 实际审计记录：{s["candidate_count"]:,} · 审计链完整：{"是" if s["lineage_complete"] else "否"} · 最终疵病：{s["final_defect_count"]} · 关联：{s["linked_to_final_count"]} · 未关联：{s["unlinked_count"]}')
        critical=[]
        if not r.audit_log.lineage_complete:
            critical.append('来源候选审计链不完整，本结果不应被视为完整正式审计记录。')
        if r.audit_log.source_candidate_count!=len(a.records):
            critical.append('来源候选声明数量与实际审计记录数不一致')
        prominent=critical+[issue for issue in a.issues if issue not in critical][:max(0,3-len(critical))]
        self.warning.setText('\n'.join(prominent) + (f'\n共 {len(a.issues)} 项问题，详见全量去向统计。' if len(a.issues)>3 else ''))
        for name,values in [('disposition',a.dispositions),('reason',{str(x):n for x,n in a.reasons.items() if x is not None}),('source',a.sources),('stage',{x or '—':n for x,n in a.stages.items()}),('linked',{'已关联':True,'未关联':False})]:
            combo=self.filters[name];combo.blockSignals(True);combo.clear();combo.addItem('全部',None)
            for label in sorted(values):combo.addItem(label,values[label] if name=='linked' else label)
            combo.blockSignals(False)
        self.charts['disposition'].set_rows([dict(label=k,count=v) for k,v in a.dispositions.items()])
        self.charts['reason'].set_rows([dict(label=k,count=v) for k,v in s['filter_reason_counts'].items()])
        self.counts.setPlainText(json.dumps(s,ensure_ascii=False,indent=2))
        self.event_model.set_events(r.audit_log.events);self.event_status.setText(f'{len(r.audit_log.events)} 条既有事件' if r.audit_log.events else '暂无事件')
        self.update_final(self.current_final)

    def request_query(self,*args):
        self.query_revision+=1;self.image_revision+=1
        self.query=AuditQuery(**{name:combo.currentData() for name,combo in self.filters.items()},
            search=self.search.text(),final_id=self.final_filter,sort_column=self.sort_column,descending=self.descending)
        self.query_pending=self.audit is not None
        # Do not allow selecting old rows while a new query is outstanding.
        self.table.setEnabled(False);self.refresh_page();self.pump()

    def sort(self,column,descending):
        self.sort_column=column;self.descending=descending
        header=self.table.horizontalHeader();header.blockSignals(True)
        header.setSortIndicator(column,Qt.SortOrder.DescendingOrder if descending else Qt.SortOrder.AscendingOrder)
        header.blockSignals(False);self.request_query()

    def clear_filters(self):
        self.debounce.stop();self.final_filter=None
        for combo in self.filters.values():combo.blockSignals(True);combo.setCurrentIndex(0);combo.blockSignals(False)
        self.search.blockSignals(True);self.search.clear();self.search.blockSignals(False)
        self.request_query()

    def change_page(self,step):
        self.model.set_page(self.model.page+step);self.restore_selection();self.refresh_page()

    def page_size_changed(self,text):
        self.model.page_size=int(text);self.model.set_page(0);self.restore_selection();self.refresh_page()

    def refresh_page(self):
        m=self.model;total=len(self.audit.records) if self.audit else 0
        self.page_status.setText(f'第 {m.page+1 if m.pages else 0} / {m.pages} 页 · 筛选 {len(m.indexes):,} / 全部 {total:,}')
        self.previous.setEnabled(m.page>0 and not self.query_pending);self.next.setEnabled(m.page+1<m.pages and not self.query_pending)
        self.table.setEnabled(not self.query_pending)
        self.reverse.setEnabled(self.current_final is not None and self.audit is not None)

    def row_selected(self,current,previous):
        if current.isValid():self.selection.set(current.data(self.model.KeyRole))

    def restore_selection(self):
        self.table.selectionModel().blockSignals(True)
        self.table.clearSelection();self.table.setCurrentIndex(QModelIndex())
        for row in range(self.model.rowCount()):
            if key(self.model.candidate(row))==self.selection.candidate_key:
                self.table.setCurrentIndex(self.model.index(row,0));self.table.selectRow(row);break
        self.table.selectionModel().blockSignals(False)

    def select_candidate(self,candidate_key):
        self.image_revision+=1;self.image_pending=False;self.viewer.clear()
        c=self.audit.candidate(candidate_key) if self.audit and candidate_key else None
        self.detail_vm=CandidateDetailViewModel(self.result_vm,c) if c else None
        self.position.setText(f'{c.source} / {c.candidate_id}' if c else '请选择候选')
        for name,label in self.fields.items():label.setText(shown(self.detail_vm.fields()[name]) if c else '—')
        self.extensions.setPlainText(json.dumps(c.extensions,ensure_ascii=False,indent=2) if c else '')
        valid=c is not None and c.final_defect_id in self.audit.final_ids
        target=self.audit.merged_target(c) if c else None
        self.jump_final.setEnabled(valid);self.jump_merged.setEnabled(target is not None)
        self.mode.model().item(2).setEnabled(valid)
        if not valid and self.mode.currentIndex()==2:self.mode.setCurrentIndex(1)
        warnings=[]
        if c and c.final_defect_id and not valid:warnings.append('一致性警告：最终疵病不存在')
        if c and c.merged_into and target is None:warnings.append('目标候选无法唯一解析')
        if c and str(c.disposition)=='FILTERED' and c.filter_reason is None:warnings.append('协议异常：FILTERED 缺少 FilterReason')
        self.detail_warning.setText('\n'.join(warnings))
        self.image_status.setText('局部图按需加载' if c else '请选择候选')
        self.request_image()

    def request_image(self,*args):
        self.image_revision+=1;self.image_pending=self.detail_vm is not None;self.pump()

    def image_key(self):
        return self.epoch,self.selection.candidate_key,self.mode.currentIndex(),self.image_revision

    def apply_local(self,local):
        self.viewer.set_frame(local.frame,fit=True);self.viewer.set_overlays(local.overlays)
        for name,color,style in [('Candidate','#22d3ee',Qt.PenStyle.SolidLine),('Final','#fb7185',Qt.PenStyle.DashLine)]:
            if name in self.viewer.overlays:
                pen=QPen(QColor(color),2,style);pen.setCosmetic(True);self.viewer.overlays[name].setPen(pen)
        self.image_status.setText(f'{local.source} · 原图坐标原点 {local.origin}' + (' · '+local.frame.message if local.frame.message else ''))

    def focus_candidate(self,candidate_key):
        self.pending_focus=candidate_key
        if self.audit is None:return
        self.pending_focus=None;self.reveal_key=candidate_key
        self.clear_filters()
        if self.selection.candidate_key==candidate_key:self.select_candidate(candidate_key)
        else:self.selection.set(candidate_key)

    def to_final(self):
        c=self.audit.candidate(self.selection.candidate_key) if self.audit else None
        if c and c.final_defect_id in self.audit.final_ids:self.final_requested.emit(c.final_defect_id)

    def to_merged(self):
        c=self.audit.candidate(self.selection.candidate_key) if self.audit else None
        target=self.audit.merged_target(c) if c else None
        if target:
            self.reveal_key=target;self.clear_filters();self.selection.set(target)

    def update_final(self,fid):
        self.current_final=fid
        d=self.result_vm.defects[self.result_vm.by_id[fid]] if self.result_vm and fid in self.result_vm.by_id else None
        if d:
            candidates=self.audit.candidates_for_final_defect(fid) if self.audit else ()
            issues=self.audit.reverse_issues.get(fid,[]) if self.audit else []
            self.lineage.setText(f'当前最终疵病 {fid} · 来源候选 {len(candidates)} · 已存 candidate_ids：{", ".join(d.detection.candidate_ids) or "—"}' + (' · '+'；'.join(issues) if issues else ''))
        else:self.lineage.setText('请先在检测页或疵病详情选择最终疵病')
        self.refresh_page()

    def reverse_current(self):
        if self.current_final is None:return
        fid=self.current_final;self.clear_filters();self.final_filter=fid;self.request_query()

    def show_event(self,current,previous):
        if current.isValid():self.event_json.setPlainText(json.dumps(self.event_model.events[current.row()],ensure_ascii=False,indent=2))

    def failed(self,message):
        if self.active:self.image_status.setText(message)
