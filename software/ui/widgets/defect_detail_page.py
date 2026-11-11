from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QComboBox,QLabel,
    QSplitter,QScrollArea,QGroupBox,QFormLayout,QGridLayout,QPlainTextEdit)
from ui.image_viewer import ImageViewer
from ui.models.defect_detail_view_model import DefectDetailViewModel, text
from ui.models.result_view_model import shown


class DefectDetailPage(QWidget):
    navigate=Signal(int)
    image_requested=Signal()
    def __init__(self,parent=None):
        super().__init__(parent);self.detail_vm=None;self.origin=(0,0);self.raw=None
        layout=QVBoxLayout(self);bar=QHBoxLayout()
        self.previous=QPushButton('上一条');self.next=QPushButton('下一条')
        self.previous.clicked.connect(lambda:self.navigate.emit(-1));self.next.clicked.connect(lambda:self.navigate.emit(1))
        bar.addWidget(self.previous);bar.addWidget(self.next)
        self.position=QLabel('请选择一个检测结果和疵病');bar.addWidget(self.position,1)
        self.mode=QComboBox();self.mode.addItems(['原始灰度','原始灰度 + bbox','原始灰度 + final mask + bbox'])
        self.mode.setCurrentIndex(2);self.mode.currentIndexChanged.connect(lambda _:self.image_requested.emit());bar.addWidget(self.mode)
        layout.addLayout(bar)
        split=QSplitter(Qt.Orientation.Horizontal)
        left=QWidget();ll=QVBoxLayout(left)
        self.image_status=QLabel('局部图 · 测量 bbox 外扩40 px，仅用于显示');self.image_status.setWordWrap(True);ll.addWidget(self.image_status)
        self.viewer=ImageViewer();ll.addWidget(self.viewer,1)
        self.coordinate=QLabel('X：—  Y：—  DN：—');ll.addWidget(self.coordinate)
        split.addWidget(left)
        self.fields_widget=QWidget();self.field_layout=QGridLayout(self.fields_widget);self.field_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(self.fields_widget);scroll.setMinimumWidth(620)
        split.addWidget(scroll);split.setSizes([850,750]);layout.addWidget(split,1)
        self.calibration=QLabel('');self.calibration.setWordWrap(True);layout.addWidget(self.calibration)
        self.fields={};self.group_boxes=[]
        self.viewer.pointer_changed.connect(self._pointer)
        self.clear()

    def clear(self,message='请选择一个检测结果和疵病'):
        self.detail_vm=None;self.raw=None;self.origin=(0,0);self.viewer.clear()
        self.position.setText(message);self.previous.setEnabled(False);self.next.setEnabled(False)
        self.image_status.setText('局部图不可用');self.coordinate.setText('X：—  Y：—  DN：—');self.calibration.clear()
        self._clear_fields()

    def _clear_fields(self):
        while self.field_layout.count():
            item=self.field_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self.fields={};self.group_boxes=[]

    def select(self,result_vm,defect_id,position,total,raw=None):
        self.detail_vm=DefectDetailViewModel(result_vm,defect_id);self.raw=raw;self.viewer.clear();self._clear_fields()
        self.position.setText(f'{position+1} / {total} · {defect_id}')
        self.previous.setEnabled(position>0);self.next.setEnabled(position+1<total)
        for i,(group,rows) in enumerate(self.detail_vm.groups().items()):
            box=QGroupBox(group);form=QFormLayout(box);self.group_boxes.append(box)
            for key,value in rows:
                if key=='merge history' and value is not None:
                    editor=QPlainTextEdit(text(value));editor.setReadOnly(True);editor.setMinimumHeight(90);editor.setMaximumHeight(150)
                    form.addRow(key,editor);self.fields[key]=editor
                    continue
                label=QLabel(text(value));label.setWordWrap(True);label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                if 'μm' in key:label.setToolTip('依据本次结果的空间尺度换算；不使用当前全局设置重算')
                if 'Feret' in key:label.setToolTip('最终疵病 mask 的最大 Feret 直径（像素中心定义）')
                if '面积' in key:label.setToolTip('最终疵病 mask 前景像素数；不是显示框面积')
                form.addRow(key,label);self.fields[key]=label
            self.field_layout.addWidget(box,i//2,i%2,1,2 if i==4 else 1)
        c=result_vm.result.calibration_info
        note=('本次空间尺度无效，物理量不可用' if not c.valid else
              '按配置尺度换算，非独立计量标定' if not c.metrologically_calibrated else '本次结果已记录计量标定信息')
        self.calibration.setText(result_vm.calibration_text.replace('\n',' · ')+' · '+note)
        self.image_status.setText('局部图待加载 · 测量 bbox 外扩40 px，仅用于显示')

    def apply_local(self,local):
        self.origin=local.origin;self.viewer.set_frame(local.frame,fit=True);self.viewer.set_overlays(local.overlays)
        self.image_status.setText(local.source+(' · '+local.frame.message if local.frame.message else '')+' · 原始坐标局部')

    def _pointer(self,x,y,dn,zoom):
        if x is None or y is None:
            self.coordinate.setText('X：—  Y：—  DN：—');return
        x+=self.origin[0];y+=self.origin[1]
        value=self.raw.dn(x,y) if self.raw else None
        self.coordinate.setText(f'X：{x}  Y：{y}  DN：{shown(value)}  Zoom：{zoom*100:.1f}%')
