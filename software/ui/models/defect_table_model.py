from PySide6.QtCore import QAbstractTableModel, Qt, QModelIndex
from .result_view_model import shown, ResultViewModel


class DefectTableModel(QAbstractTableModel):
    SortRole = Qt.ItemDataRole.UserRole + 1
    DefectIdRole = Qt.ItemDataRole.UserRole + 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.view_model = None

    def set_result(self, vm):
        self.beginResetModel()
        self.view_model = vm
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() or self.view_model is None else len(self.view_model.defects)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(ResultViewModel.columns)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return ResultViewModel.columns[section]
        return super().headerData(section, orientation, role)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or self.view_model is None:
            return None
        values = self.view_model.values(index.row())
        if role == Qt.ItemDataRole.DisplayRole:
            return shown(values[index.column()])
        if role == self.SortRole:
            return values[index.column()]
        if role == self.DefectIdRole:
            return values[0]
