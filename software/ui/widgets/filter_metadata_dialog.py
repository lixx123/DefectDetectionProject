"""Explicit operator identity for a filter, independent from RAW/sample/result IDs."""
from PySide6.QtWidgets import QDialog,QFormLayout,QLineEdit,QLabel,QDialogButtonBox
from ui.models.defect_ledger import validate_filter_id

class FilterMetadataDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent);self.setWindowTitle('保存正式结果');self.resize(480,190)
        layout=QFormLayout(self);self.filter_id=QLineEdit();self.notes=QLineEdit();self.notes.setMaxLength(2000)
        layout.addRow('滤光片编号 Filter_ID：',self.filter_id);layout.addRow('备注（可选）：',self.notes)
        self.error=QLabel();self.error.setWordWrap(True);layout.addRow(self.error)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('保存');buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addRow(buttons)

    def accept(self):
        try:validate_filter_id(self.filter_id.text())
        except ValueError as exc:self.error.setText(str(exc));return
        super().accept()

    @classmethod
    def get_metadata(cls,parent=None):
        dialog=cls(parent)
        return (dialog.filter_id.text(),dialog.notes.text()) if dialog.exec()==QDialog.DialogCode.Accepted else None
