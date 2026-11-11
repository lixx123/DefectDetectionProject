from PySide6.QtCore import QSortFilterProxyModel, Signal


class DefectFilterModel(QSortFilterProxyModel):
    filters_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.grade = self.band = self.defect_type = None

    def set_filters(self, grade=None, band=None, defect_type=None):
        self.grade, self.band, self.defect_type = grade, band, defect_type
        self.beginFilterChange()
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)
        self.filters_changed.emit()

    def filterAcceptsRow(self, row, parent):
        vm = self.sourceModel().view_model
        if vm is None:
            return False
        d = vm.defects[row]
        return ((self.grade is None or str(d.classification.size_grade)==self.grade)
            and (self.band is None or (d.location.band_id or 'UNKNOWN')==self.band)
            and (self.defect_type is None or (d.classification.defect_type or 'UNKNOWN')==self.defect_type))

    def lessThan(self, left, right):
        role = self.sortRole()
        a, b = left.data(role), right.data(role)
        if a is None or b is None:
            return a is None and b is not None
        if left.column()==2:
            order={'SMALL':0,'MEDIUM':1,'LARGE':2,'UNKNOWN':3}
            return order.get(str(a),4)<order.get(str(b),4)
        if left.column()==9:
            try: return float(a)<float(b)
            except (ValueError,TypeError): pass
        return super().lessThan(left,right)
