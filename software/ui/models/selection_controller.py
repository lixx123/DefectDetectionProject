from PySide6.QtCore import QObject, Signal


class SelectionController(QObject):
    changed=Signal(object)
    def __init__(self,parent=None):
        super().__init__(parent);self.defect_id=None
    def set(self,defect_id):
        if self.defect_id!=defect_id:
            self.defect_id=defect_id;self.changed.emit(defect_id)
