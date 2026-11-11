"""Current-result statistics with native Qt tables and two small bar charts."""
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QRectF
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QGroupBox,QGridLayout,
    QTabWidget,QTableView,QHeaderView)
from ui.models.statistics_view_model import StatisticsViewModel
from ui.models.result_view_model import shown


class AggregateTableModel(QAbstractTableModel):
    columns=(('label','分组'),('count','数量'),('percentage','占比 %'),('area_px','面积 px²'),
             ('area_um2','面积 μm²'),('max_area_px','最大面积 px²'),('max_feret_px','最大 Feret px'))
    def __init__(self,parent=None):
        super().__init__(parent); self.rows=[]
    def set_rows(self,rows):
        self.beginResetModel(); self.rows=rows; self.endResetModel()
    def rowCount(self,parent=QModelIndex()): return 0 if parent.isValid() else len(self.rows)
    def columnCount(self,parent=QModelIndex()): return 0 if parent.isValid() else len(self.columns)
    def headerData(self,section,orientation,role=Qt.ItemDataRole.DisplayRole):
        if role==Qt.ItemDataRole.DisplayRole and orientation==Qt.Orientation.Horizontal:return self.columns[section][1]
    def data(self,index,role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():return None
        value=self.rows[index.row()][self.columns[index.column()][0]]
        if role==Qt.ItemDataRole.DisplayRole:
            return f'{value:,.2f}' if isinstance(value,float) else shown(value)
        if role==Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter) if index.column()==0 else int(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)


class CountChart(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent); self.rows=[]; self.setMinimumHeight(210)
    def set_rows(self,rows):self.rows=rows;self.update()
    def paintEvent(self,event):
        painter=QPainter(self);painter.fillRect(self.rect(),QColor('white'))
        if not self.rows or not any(r['count'] for r in self.rows):
            painter.setPen(QColor('#64748b'));painter.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'暂无疵病');return
        maximum=max(r['count'] for r in self.rows)
        width=max(1,(self.width()-80)/len(self.rows)); baseline=self.height()-35
        painter.setPen(QColor('#64748b'));painter.drawText(8,25,f'数量 · 0–{maximum}')
        for i,row in enumerate(self.rows):
            height=(self.height()-80)*row['count']/maximum
            x=55+i*width
            painter.fillRect(QRectF(x+width*.18,baseline-height,width*.64,height),QColor('#4c8de8'))
            painter.setPen(QColor('#17263a'))
            painter.drawText(QRectF(x,baseline-height-25,width,22),Qt.AlignmentFlag.AlignCenter,str(row['count']))
            painter.drawText(QRectF(x,baseline+5,width,25),Qt.AlignmentFlag.AlignCenter,row['label'])


class StatisticsPage(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.view_model=None
        layout=QVBoxLayout(self)
        self.heading=QLabel('当前结果 · 全量最终疵病统计（不受检测页筛选影响）');self.heading.setStyleSheet('font-size:18px;font-weight:600;padding:10px;')
        self.heading.setWordWrap(True);layout.addWidget(self.heading)
        self.status=QLabel('暂无检测结果');self.status.setWordWrap(True);layout.addWidget(self.status)
        cards=QGridLayout();self.cards={}
        labels={'total_defects':'疵病总数','total_area_px':'总面积 px²','total_area_um2':'总面积 μm²',
                'defect_area_ratio':'疵病 / WORK 面积占比','max_area_px':'最大面积 px²','max_feret_px':'最大 Feret px'}
        for i,(key,label) in enumerate(labels.items()):
            box=QGroupBox(label);bl=QVBoxLayout(box);value=QLabel('—');value.setStyleSheet('font-size:23px;font-weight:600;')
            bl.addWidget(value);cards.addWidget(box,0,i);self.cards[key]=value
        layout.addLayout(cards)
        self.scope=QLabel('面积占比仅使用结果中可信 WORK 像素数作为分母');layout.addWidget(self.scope)
        self.groups=QTabWidget();self.models={};self.charts={}
        for key,label in [('size','尺寸等级'),('band','Band'),('type','类型'),('roi','ROI')]:
            widget=QWidget();wl=QVBoxLayout(widget)
            if key in ('size','band'):
                chart=CountChart();self.charts[key]=chart;wl.addWidget(chart)
            model=AggregateTableModel(self);table=QTableView();table.setModel(model)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            table.setAlternatingRowColors(True);table.verticalHeader().hide();self.models[key]=model
            wl.addWidget(table,1);self.groups.addTab(widget,label)
        layout.addWidget(self.groups,1)

    def set_result(self,result):
        self.view_model=StatisticsViewModel(result) if result else None
        if result is None:
            self.heading.setText('当前结果 · 全量最终疵病统计（不受检测页筛选影响）')
            self.status.setText('暂无检测结果')
            for card in self.cards.values():card.setText('—')
            for model in self.models.values():model.set_rows([])
            for chart in self.charts.values():chart.set_rows([])
            self.scope.setText('面积占比仅使用结果中可信 WORK 像素数作为分母')
            return
        vm=self.view_model
        self.heading.setText('统计分析 · '+(result.input_info.file_name or '未命名结果')+'\n全量最终疵病（不受检测页筛选影响）')
        if vm.errors:
            self.status.setText('一致性校验未通过：'+'；'.join(vm.errors));self.status.setStyleSheet('color:#b42318;')
        else:
            self.status.setText('统计一致性校验通过'+(' · '+'；'.join(vm.warnings) if vm.warnings else ''))
            self.status.setStyleSheet('color:#16734b;')
        summary=vm.summary()
        for key,card in self.cards.items():
            value=summary[key]
            card.setText('—' if value is None else f'{value*100:.4f}%' if key=='defect_area_ratio' else
                         f'{value:,.2f}' if isinstance(value,float) else str(value))
        self.scope.setText('全量存储统计；WORK 面积：'+shown(summary['work_area_px'])+' px² · 图表/分组仅来自最终 Defect[]')
        for key,rows in [('size',vm.by_size_grade()),('band',vm.by_band()),('type',vm.by_type()),('roi',vm.by_roi())]:
            self.models[key].set_rows(rows)
            if key in self.charts:self.charts[key].set_rows(rows if vm.defects else [])
