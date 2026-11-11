"""Phase 6 operator window. All expensive I/O and detection run in a worker."""
from pathlib import Path
from PySide6.QtCore import Qt, QSortFilterProxyModel, QItemSelectionModel, Slot
from PySide6.QtGui import QAction, QKeySequence, QStandardItemModel, QStandardItem, QFont, QFontDatabase
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QSplitter, QTableView, QToolBar, QComboBox, QProgressBar, QFileDialog, QMessageBox,
    QDialog, QDialogButtonBox, QAbstractItemView, QHeaderView, QScrollArea, QApplication, QTabWidget, QPushButton)
from ui.image_viewer import ImageViewer
from ui.runtime_errors import guarded_completion
from ui.models.defect_table_model import DefectTableModel
from ui.models.result_view_model import ImageCache, ViewMode, shown
from ui.controllers.inspection_controller import InspectionController
from ui.models.defect_filter_model import DefectFilterModel
from ui.models.selection_controller import SelectionController
from ui.widgets.defect_detail_page import DefectDetailPage
from ui.widgets.statistics_page import StatisticsPage
from ui.widgets.audit_page import AuditPage
from ui.widgets.review_admission_page import ReviewAdmissionPage
from ui.widgets.human_review_workspace import HumanReviewWorkspace

_font_loaded = False


class HistoryDialog(QDialog):
    def __init__(self, summaries, parent=None):
        super().__init__(parent)
        self.setWindowTitle('加载历史正式结果')
        self.resize(1100, 520)
        self.summaries, self.result_id = summaries, None
        layout = QVBoxLayout(self)
        self.table = QTableView()
        model = QStandardItemModel(self)
        model.setHorizontalHeaderLabels(['时间', '文件名', '样本', '疵病数', '总面积 px²', '最终模式', '回退', 'Filter_ID'])
        for s in summaries:
            model.appendRow([QStandardItem(shown(v)) for v in (s.saved_at, s.file_name,
                s.sample_id, s.defect_count, s.total_area_px, s.final_mode, '是' if s.fallback_used else '否',getattr(s,'filter_id',None))])
        self.table.setModel(model)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.doubleClicked.connect(self._choose)
        layout.addWidget(self.table)
        layout.addWidget(QLabel('双击一行加载。' if summaries else '尚无正式结果。'))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _choose(self, index):
        self.result_id = self.summaries[index.row()].result_id
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self, controller=None):
        super().__init__()
        # The offscreen Qt platform may not discover Windows' CJK fallback fonts.
        font_path = Path('C:/Windows/Fonts/msyh.ttc')
        global _font_loaded
        if not _font_loaded and font_path.is_file():
            QFontDatabase.addApplicationFont(str(font_path))
            _font_loaded = True
        if _font_loaded:
            self.setFont(QFont('Microsoft YaHei', 10))
        self.setWindowTitle('滤光片表面疵病自动检测与分析软件 V1.0.0')
        QApplication.instance().setApplicationName('滤光片表面疵病自动检测与分析软件')
        self.resize(1680, 1000)
        self.controller = controller or InspectionController(parent=self)
        self.view_model = None
        self.raw = None
        self.raw_path = None
        self.saved = False
        self.cache = ImageCache()
        self.selection = SelectionController(self)
        self._detail_revision = 0
        self._detail_pending = False
        self.controller.busy_changed.connect(self._busy)
        self.controller.completed.connect(self._completed)
        self.controller.error.connect(self._error)
        self._build()
        self.controller.status_changed.connect(self.statusBar().showMessage)
        self.selection.changed.connect(self._selection_changed)
        self._actions()
        self._refresh_actions()
        if self.controller.packaged_engine:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0,self.controller.check_engine)

    def _build(self):
        self.setStyleSheet('''
            QMainWindow, QDialog { background: #f3f6fa; color: #17263a; }
            QToolBar { background: white; spacing: 9px; padding: 9px; border-bottom: 1px solid #dce3ed; }
            QToolButton { padding: 7px 10px; } QToolButton:hover { background: #e4efff; }
            QTableView { background: white; alternate-background-color: #f3f7fc; gridline-color: #e5ebf3; }
            QHeaderView::section { background: #eaf0f8; padding: 7px; border: 0; }
            QLabel { padding: 4px; } QStatusBar { background: #e5edf7; }
        ''')
        center = QWidget()
        layout = QVBoxLayout(center)
        layout.setContentsMargins(12, 10, 12, 8)
        self.summary = QLabel('打开 RAW 开始自动检测，或加载正式历史结果')
        self.summary.setStyleSheet('font-size: 17px; font-weight: 600; padding: 10px;')
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.engine_label=QLabel(self.controller.engine_status)
        self.engine_label.setWordWrap(True)
        layout.addWidget(self.engine_label)
        self.result_engine_label=QLabel('')
        layout.addWidget(self.result_engine_label)
        filters=QHBoxLayout()
        self.filter_grade=QComboBox();self.filter_band=QComboBox();self.filter_type=QComboBox()
        for name,combo in [('尺寸等级',self.filter_grade),('Band',self.filter_band),('类型',self.filter_type)]:
            filters.addWidget(QLabel(name));combo.addItem('全部',None);filters.addWidget(combo)
            combo.currentIndexChanged.connect(self._filter_changed)
        reset=QPushButton('清除筛选');reset.clicked.connect(self.clear_filters);filters.addWidget(reset)
        self.filter_count=QLabel('显示 0 / 0 个最终疵病');filters.addWidget(self.filter_count,1)
        layout.addLayout(filters)
        vertical = QSplitter(Qt.Orientation.Vertical)
        top = QSplitter(Qt.Orientation.Horizontal)
        sidebar = QWidget()
        sidebar.setMaximumWidth(280)
        sl = QVBoxLayout(sidebar)
        title = QLabel('当前任务')
        title.setStyleSheet('font-size: 15px; font-weight: bold;')
        sl.addWidget(title)
        self.file_info = QLabel('尚未打开 RAW')
        self.file_info.setWordWrap(True)
        sl.addWidget(self.file_info)
        self.calibration = QLabel('尺度：—\n来源：—')
        sl.addWidget(self.calibration)
        self.bands = QLabel('Band 信息将在结果加载后显示')
        self.bands.setWordWrap(True)
        band_scroll = QScrollArea()
        band_scroll.setWidgetResizable(True)
        band_scroll.setWidget(self.bands)
        sl.addWidget(band_scroll, 1)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setTextVisible(False)
        sl.addWidget(self.progress)
        top.addWidget(sidebar)
        middle = QWidget()
        ml = QVBoxLayout(middle)
        ml.setContentsMargins(0, 0, 0, 0)
        self.resource_status = QLabel('图像区域 · F 适应窗口 · 1 原始像素比例 · 滚轮缩放 · 拖拽平移')
        self.resource_status.setWordWrap(True)
        ml.addWidget(self.resource_status)
        self.viewer = ImageViewer()
        self.viewer.set_task_controller(self.controller)
        self.viewer.setMinimumSize(500, 300)
        ml.addWidget(self.viewer, 1)
        top.addWidget(middle)
        self.detail = QLabel('当前疵病\n\n点击疵病框或表格行查看详情')
        self.detail.setWordWrap(True)
        self.detail.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        detail_scroll = QScrollArea()
        detail_scroll.setWidgetResizable(True)
        detail_scroll.setWidget(self.detail)
        detail_scroll.setMinimumWidth(230)
        top.addWidget(detail_scroll)
        top.setSizes([240, 1130, 270])
        top.setStretchFactor(1, 1)
        vertical.addWidget(top)
        self.table_model = DefectTableModel(self)
        self.proxy = DefectFilterModel(self)
        self.proxy.setSourceModel(self.table_model)
        self.proxy.setSortRole(DefectTableModel.SortRole)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        vertical.addWidget(self.table)
        vertical.setSizes([680, 225])
        vertical.setStretchFactor(0, 1)
        layout.addWidget(vertical, 1)
        self.tabs=QTabWidget()
        self.tabs.addTab(center,'检测')
        self.detail_page=DefectDetailPage()
        self.statistics_page=StatisticsPage()
        self.tabs.addTab(self.detail_page,'疵病详情')
        self.tabs.addTab(self.statistics_page,'统计分析')
        self.audit_page=AuditPage(self.controller)
        self.tabs.addTab(self.audit_page,'检测过程 / 审计')
        self.audit_page.final_requested.connect(self._audit_to_final)
        self.admission_page=ReviewAdmissionPage(self.controller)
        self.review_workspace=HumanReviewWorkspace(self.controller,self.admission_page)
        self.human_review_page=self.review_workspace.review_page
        self.tabs.addTab(self.review_workspace,'人工复核')
        self.human_review_page.defect_requested.connect(self._audit_to_final)
        self.human_review_page.candidate_requested.connect(self._admission_to_candidate)
        self.admission_page.defect_requested.connect(self._audit_to_final)
        self.admission_page.candidate_requested.connect(self._admission_to_candidate)
        self.selection.changed.connect(self.audit_page.update_final)
        self.setCentralWidget(self.tabs)
        self.tabs.currentChanged.connect(self._tab_changed)
        self.detail_page.navigate.connect(self._navigate_defect)
        self.detail_page.image_requested.connect(self._queue_detail_image)
        self.proxy.filters_changed.connect(self._sync_filtered_overlays)
        self.proxy.layoutChanged.connect(self._update_navigation)
        self.pointer = QLabel('X：—  Y：—  DN：—  Zoom：—')
        self.activity=QProgressBar();self.activity.setRange(0,0);self.activity.setTextVisible(False);self.activity.setMaximumWidth(130);self.activity.hide()
        self.statusBar().addPermanentWidget(self.activity)
        self.statusBar().addPermanentWidget(self.pointer)
        self.statusBar().showMessage('就绪 · 自动检测')
        self.viewer.pointer_changed.connect(self._pointer)
        self._last_pointer = (None, None, None)
        self.viewer.zoom_changed.connect(lambda zoom: self._pointer(*self._last_pointer, zoom))
        self.viewer.defect_selected.connect(self._viewer_selected)
        self.table.selectionModel().currentRowChanged.connect(self._table_selected)

    def _actions(self):
        bar = QToolBar('主工具栏', self)
        bar.setMovable(False)
        self.addToolBar(bar)
        file_menu, detection_menu, view_menu, help_menu = [self.menuBar().addMenu(n) for n in ('文件', '检测', '视图', '帮助')]

        def action(text, callback, menu, shortcut=None, check=None, toolbar=True):
            a = QAction(text, self)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            if check is not None:
                a.setCheckable(True)
                a.setChecked(check)
                a.toggled.connect(callback)
            else:
                a.triggered.connect(callback)
            menu.addAction(a)
            if toolbar:
                bar.addAction(a)
            return a

        self.open_action = action('打开 RAW', self._choose_raw, file_menu, 'Ctrl+O')
        self.history_action = action('历史结果', self.controller.history, file_menu)
        self.save_action = action('保存正式结果', self._save, file_menu, 'Ctrl+S')
        self.open_ledger_action = action('打开检测台账',self._open_ledger,file_menu,toolbar=False)
        self.sync_ledger_action = action('同步/重建检测台账',lambda:self.controller.sync_ledger(),file_menu,toolbar=False)
        action('退出', self.close, file_menu, toolbar=False)
        bar.addSeparator()
        self.start_action = action('开始检测', self._detect, detection_menu)
        self.redetect_action = action('重新检测', self._detect, detection_menu, toolbar=False)
        bar.addSeparator()
        self.view_selector = QComboBox()
        self.view_selector.addItems([v.value for v in ViewMode])
        self.view_selector.setCurrentText(ViewMode.FINAL)
        self.view_selector.currentTextChanged.connect(self._switch_view)
        bar.addWidget(self.view_selector)
        for mode in ViewMode:
            action(mode.value, lambda checked=False, m=mode: self.view_selector.setCurrentText(m), view_menu, toolbar=False)
        action('适应窗口', self.viewer.fit, view_menu, 'F')
        action('1:1', self.viewer.actual_size, view_menu, '1')
        action('放大', lambda: self.viewer.zoom_by(1.25), view_menu, '+')
        action('缩小', lambda: self.viewer.zoom_by(0.8), view_menu, '-')
        self.box_action = action('疵病框', self.viewer.show_boxes, view_menu, check=True)
        self.id_action = action('编号', self.viewer.show_ids, view_menu, check=False)
        self.mask_action = action('最终 mask', lambda _: self._switch_view(self.view_selector.currentText()), view_menu, check=True)
        action('关于', lambda: QMessageBox.information(self, '关于', '滤光片表面疵病自动检测与分析软件 V1.0.0\nschema 1.0\n'+self.controller.engine_status), help_menu, toolbar=False)

    def _refresh_actions(self):
        self.engine_label.setText(self.controller.engine_status)
        busy = self.controller.busy
        self.open_action.setEnabled(not busy)
        self.history_action.setEnabled(not busy)
        self.sync_ledger_action.setEnabled(not busy)
        self.start_action.setEnabled(not busy and self.raw_path is not None and self.controller.engine_ready)
        self.redetect_action.setEnabled(not busy and self.raw_path is not None and self.controller.engine_ready)
        self.save_action.setEnabled(not busy and self.view_model is not None and not self.saved)
        self.view_selector.setEnabled(not busy)
        self.mask_action.setEnabled(not busy)

    def _busy(self, busy):
        self.activity.setVisible(busy)
        self.progress.setRange(0, 0 if busy else 1)
        self.progress.setVisible(busy)
        self._refresh_actions()
        self._update_navigation()
        if not busy:self._try_detail_image()

    def clear_result(self, *, keep_raw=False):
        self.result_engine_label.clear()
        self._detail_revision+=1;self._detail_pending=False
        self.selection.set(None)
        self.detail_page.clear()
        self.statistics_page.set_result(None)
        self.audit_page.set_result(None)
        self.admission_page.set_result(None)
        self.human_review_page.set_result(None)
        self.viewer.clear()
        self.table.clearSelection()
        self.table_model.set_result(None)
        self.cache.clear()
        self.view_model = None
        self.clear_filters()
        self.saved = False
        self.detail.setText('当前疵病\n\n点击疵病框或表格行查看详情')
        self.calibration.setText('尺度：—\n来源：—')
        self.bands.setText('Band 信息将在结果加载后显示')
        self.summary.setText('打开 RAW 开始自动检测，或加载正式历史结果')
        self.resource_status.setText('图像区域')
        self._pointer(None, None, None, 1)
        if not keep_raw:
            if self.raw:
                self.raw.clear()
            self.raw = self.raw_path = None
            self.file_info.setText('尚未打开 RAW')

    def _choose_raw(self):
        path, _ = QFileDialog.getOpenFileName(self, '打开 RAW', '', 'RAW (*.raw);;所有文件 (*)')
        if path:
            self.open_raw(path)

    def open_raw(self, path):
        if self.controller.busy:
            return
        self.statusBar().showMessage('正在读取 RAW…')
        self.controller.open_raw(path)

    def _detect(self):
        if self.raw_path and not self.controller.busy and self.controller.engine_ready:
            self.clear_result(keep_raw=True)
            self.statusBar().showMessage('正在执行自动检测…')
            self.controller.detect(self.raw_path, self.raw)

    def _request_filter_metadata(self):
        from ui.widgets.filter_metadata_dialog import FilterMetadataDialog
        return FilterMetadataDialog.get_metadata(self)

    def _open_ledger(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        path=self.controller.repository.root.parent/'defect_ledger.xlsx'
        if not path.exists():
            QMessageBox.information(self,'检测台账','尚无台账，请先保存正式结果或同步/重建检测台账。');return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            QMessageBox.information(self,'检测台账','未找到可打开 XLSX 的默认程序。台账位于：'+str(path))

    def _save(self):
        if self.view_model and not self.saved and not self.controller.busy:
            from ui.models.defect_ledger import filter_metadata
            metadata=filter_metadata(self.view_model.result)
            if not metadata.get('filter_id'):
                value=self._request_filter_metadata()
                if value is None:return
                metadata={'filter_id':value[0],'notes':value[1]}
            self.statusBar().showMessage('正在保存正式结果…')
            self.controller.save(self.view_model,self.raw,filter_id=metadata['filter_id'],notes=metadata.get('notes',''))

    def load_history(self, result_id):
        if not self.controller.busy:
            self.clear_result()
            self.statusBar().showMessage('正在校验并加载历史结果…')
            self.controller.load_history(result_id)

    def display_result(self, vm, frame=None, *, saved=True):
        previous_id=self.view_model.result.result_id if self.view_model else None
        if previous_id is not None and previous_id!=vm.result.result_id and self.raw:
            self.raw.clear();self.raw=self.raw_path=None
        self._detail_revision+=1;self._detail_pending=False
        self.selection.set(None)
        self.detail_page.clear('暂无疵病' if not vm.defects else '请选择一个检测结果和疵病')
        self.viewer.clear()
        self.cache.clear()
        self.view_model, self.saved = vm, saved
        engine=vm.result.algorithm_info.extensions.get('engine')
        result_engine=('本结果引擎：'+engine['engine_id']+' v'+engine['engine_version']) if engine else '本结果：历史记录未保存 Engine Package 元数据'
        self.result_engine_label.setText(result_engine)
        self.table_model.set_result(vm)
        self._populate_filters()
        self.statistics_page.set_result(vm.result)
        self.audit_page.set_result(vm)
        self.admission_page.set_result(vm)
        self.human_review_page.set_result(vm)
        self.detail.setText('当前疵病\n\n点击疵病框或表格行查看详情')
        self.summary.setText(vm.summary)
        self.calibration.setText(vm.calibration_text)
        self.bands.setText(vm.bands_text)
        self.file_info.setText(f'{vm.result.input_info.file_name}\n结果：{vm.result.result_id}\n' + ('正式历史结果' if saved else '临时结果 · 尚未正式保存'))
        self.view_selector.blockSignals(True)
        self.view_selector.setCurrentText(ViewMode.FINAL)
        self.view_selector.blockSignals(False)
        frame = frame or vm.frame(ViewMode.FINAL, self.raw)
        self._apply_frame(frame, fit=True)
        self.viewer.set_overlays(vm.overlays)
        self.viewer.raw_provider = self.raw
        self._sync_filtered_overlays()
        self._refresh_actions()
        self.statusBar().showMessage(vm.summary.replace('\n',' | '))

    def _apply_frame(self, frame, fit=False):
        self.cache.clear()
        self.cache.key = self.view_selector.currentText()
        self.cache.frame = frame
        self.viewer.set_frame(frame, fit=fit)
        self.viewer.detail_enabled = self.view_selector.currentText() in (ViewMode.ORIGINAL, ViewMode.FINAL)
        self.viewer._detail_timer.start(30)
        self.resource_status.setText(frame.message or self.view_selector.currentText())

    @Slot(str, object)
    @guarded_completion
    def _completed(self, kind, value):
        if kind == 'raw':
            from ui.models.result_view_model import DisplayFrame
            new_raw, image = value
            self.clear_result()
            self.raw = new_raw
            self.raw_path = self.raw.path
            self.view_selector.blockSignals(True)
            self.view_selector.setCurrentText(ViewMode.ORIGINAL)
            self.view_selector.blockSignals(False)
            self.viewer.raw_provider = self.raw
            self.viewer.detail_enabled = True
            self.viewer.set_frame(DisplayFrame(image, self.raw.width, self.raw.height), fit=True)
            self.file_info.setText(f'{self.raw_path.name}\n{self.raw_path.stat().st_size:,} 字节\n{self.raw_path}')
            self.summary.setText('RAW 已就绪 · 点击“开始检测”' if self.controller.engine_ready else 'RAW 可浏览 · 检测引擎不可用')
            self.statusBar().showMessage(('RAW 已打开 · 显示 LUT：0–4095 DN → 8-bit') if self.controller.engine_ready else self.controller.engine_status)
        elif kind == 'result':
            vm, frame, saved = value
            self.display_result(vm, frame, saved=saved)
            self.statusBar().showMessage(vm.summary.replace('\n', ' | '))
        elif kind == 'frame':
            self._apply_frame(value)
            self.statusBar().showMessage('视图已就绪 · ' + self.view_selector.currentText())
        elif kind == 'detail_frame':
            key,local=value
            if key==self._detail_key():
                self.detail_page.apply_local(local)
        elif kind == 'saved':
            # Replace the staging VM with a verified reload of the formal package.
            self.display_result(value.vm,value.frame,saved=True)
            if value.raw_binding:self.human_review_page.install_raw(value.raw_binding)
            warning='；'+'；'.join(value.record.warnings) if value.record.warnings else ''
            from ui.models.defect_ledger import filter_metadata
            metadata=filter_metadata(value.vm.result)
            self.statusBar().showMessage('已保存正式结果：'+value.record.result_id+' · Filter_ID: '+str(metadata.get('filter_id','—'))+' · '+(value.ledger_warning or '台账已更新')+warning+value.raw_warning)
        elif kind == 'ledger':
            self.statusBar().showMessage(f'台账已同步/重建：{value["summary_rows"]} 条结果，{value["detail_rows"]} 条 Large/Medium 疵病')
        elif kind == 'history':
            # Defer dialog until the worker lifecycle has finished.
            from PySide6.QtCore import QTimer
            def choose():
                if self.controller.busy:
                    QTimer.singleShot(20, choose)
                    return
                dialog = HistoryDialog(value, self)
                if dialog.exec() and dialog.result_id:
                    self.load_history(dialog.result_id)
            QTimer.singleShot(0, choose)

    def _switch_view(self, text):
        if self.view_model and not self.controller.busy:
            self.statusBar().showMessage('正在加载视图资源…')
            self.controller.view(self.view_model, ViewMode(text), self.raw, self.mask_action.isChecked())
        elif self.raw and not self.controller.busy:
            from ui.models.result_view_model import DisplayFrame
            raw=self.raw
            self.controller.submit('frame',lambda:DisplayFrame(raw.thumbnail(),raw.width,raw.height),operation_name='view')

    def _table_selected(self, current, previous):
        if current.isValid() and self.view_model:
            source = self.proxy.mapToSource(current)
            defect_id = self.table_model.data(source, DefectTableModel.DefectIdRole)
            self.selection.set(defect_id)

    def _viewer_selected(self, defect_id):
        if self.view_model and defect_id in self.view_model.by_id:
            index = self.proxy.mapFromSource(self.table_model.index(self.view_model.by_id[defect_id], 0))
            if not index.isValid():return
            self.table.setCurrentIndex(index)
            self.table.selectRow(index.row())
            self.table.scrollTo(index)
            self.selection.set(defect_id)

    def _selection_changed(self,defect_id):
        self._detail_revision+=1;self._detail_pending=False
        if self.view_model is None or defect_id is None:
            self.viewer.selected_id=None
            for item in self.viewer.overlays.values():item.highlight(False)
            self.detail.setText('当前疵病\n\n点击疵病框或表格行查看详情')
            message='暂无疵病' if self.view_model and not self.view_model.defects else '请选择一个检测结果和疵病'
            self.detail_page.clear(message)
            return
        self.viewer.select_defect(defect_id,center=True)
        self.detail.setText(self.view_model.detail(defect_id))
        self.detail_page.select(self.view_model,defect_id,self._visible_ids().index(defect_id),self.proxy.rowCount(),self.raw)
        self._update_navigation()
        self._queue_detail_image()

    def _visible_ids(self):
        return [self.proxy.index(i,0).data(DefectTableModel.DefectIdRole) for i in range(self.proxy.rowCount())]

    def _populate_filters(self):
        vm=self.view_model
        grades=list(dict.fromkeys(str(d.classification.size_grade) for d in vm.defects))
        bands=list(dict.fromkeys([b.band_id for b in vm.result.roi_info.band_list]+[d.location.band_id or 'UNKNOWN' for d in vm.defects]))
        types=list(dict.fromkeys(d.classification.defect_type or 'UNKNOWN' for d in vm.defects))
        for combo,values in [(self.filter_grade,grades),(self.filter_band,bands),(self.filter_type,types)]:
            combo.blockSignals(True);combo.clear();combo.addItem('全部',None)
            for value in values:combo.addItem('未分类' if combo is self.filter_type and value=='UNKNOWN' else value,value)
            combo.blockSignals(False)
        self.clear_filters()

    def _filter_changed(self,*args):
        if hasattr(self,'proxy'):
            self.proxy.set_filters(self.filter_grade.currentData(),self.filter_band.currentData(),self.filter_type.currentData())

    def clear_filters(self):
        for combo in (self.filter_grade,self.filter_band,self.filter_type):
            combo.blockSignals(True);combo.setCurrentIndex(0);combo.blockSignals(False)
        self._filter_changed()

    def _sync_filtered_overlays(self):
        vm=self.view_model
        ids=self._visible_ids() if vm else []
        if vm:
            visible=set(ids)
            self.viewer.set_overlays([o for o in vm.overlays if o.defect_id in visible])
            if self.selection.defect_id not in visible:
                self.table.clearSelection();self.table.setCurrentIndex(self.proxy.index(-1,-1));self.selection.set(None)
            elif self.selection.defect_id:
                self.viewer.select_defect(self.selection.defect_id)
        self.filter_count.setText(f'显示 {len(ids)} / {len(vm.defects) if vm else 0} 个最终疵病')
        self._update_navigation()

    def _update_navigation(self,*args):
        if not hasattr(self,'detail_page'):return
        ids=self._visible_ids();selected=self.selection.defect_id
        if selected not in ids:
            self.detail_page.previous.setEnabled(False);self.detail_page.next.setEnabled(False);return
        row=ids.index(selected)
        self.detail_page.position.setText(f'{row+1} / {len(ids)} · {selected}')
        self.detail_page.previous.setEnabled(not self.controller.busy and row>0)
        self.detail_page.next.setEnabled(not self.controller.busy and row+1<len(ids))

    def _navigate_defect(self,step):
        ids=self._visible_ids()
        if self.controller.busy or self.selection.defect_id not in ids:return
        row=ids.index(self.selection.defect_id)+step
        if 0<=row<len(ids):
            index=self.proxy.index(row,0);self.table.setCurrentIndex(index);self.table.selectRow(row)

    def _audit_to_final(self,defect_id):
        if self.view_model is None or defect_id not in self.view_model.by_id:return
        visible=self._visible_ids()
        if defect_id not in visible:
            self.clear_filters()
            self.statusBar().showMessage('为显示关联最终疵病，已清除检测页显示筛选')
        self._viewer_selected(defect_id)
        self.tabs.setCurrentIndex(1)

    def _admission_to_candidate(self,candidate_key):
        self.audit_page.focus_candidate(candidate_key)
        self.tabs.setCurrentIndex(3)

    def _tab_changed(self,index):
        self.audit_page.set_active(index==3)
        self.admission_page.set_active(index==4)
        self.review_workspace.set_active(index==4)
        if index==1:self._queue_detail_image()

    def _detail_key(self):
        return (self.view_model.result.result_id if self.view_model else None,self.selection.defect_id,
                self.detail_page.mode.currentIndex(),self._detail_revision)

    def _queue_detail_image(self,*args):
        self._detail_revision+=1
        self._detail_pending=self.selection.defect_id is not None and self.view_model is not None
        self._try_detail_image()

    def _try_detail_image(self):
        if not self._detail_pending or self.controller.busy or self.tabs.currentIndex()!=1:return
        detail_vm=self.detail_page.detail_vm
        if detail_vm is None:return
        key=self._detail_key();mode=self.detail_page.mode.currentIndex();raw=self.raw
        self._detail_pending=False
        self.detail_page.image_status.setText('正在加载局部显示资源…')
        self.controller.submit('detail_frame',lambda:(key,detail_vm.local_view(mode,raw)))

    def _pointer(self, x, y, dn, zoom):
        self._last_pointer = (x, y, dn)
        self.pointer.setText(f'X：{shown(x)}  Y：{shown(y)}  DN：{shown(dn)}  Zoom：{zoom * 100:.1f}%')

    def _error(self, message):
        self.statusBar().showMessage(message)
        self.resource_status.setText(message)
        self.progress.setVisible(self.controller.busy)
        if self.tabs.currentIndex()==1:self.detail_page.image_status.setText(message)

    def closeEvent(self, event):
        if self.controller.busy:
            self.statusBar().showMessage('任务正在运行，暂不允许关闭；完成后可安全退出')
            event.ignore()
            return
        self.clear_result()
        self.controller.close()
        event.accept()
