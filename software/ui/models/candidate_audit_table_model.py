"""Virtual current-page table: domain records remain in the shared audit index."""
import math
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, Signal, QObject
from PySide6.QtGui import QColor
from .audit_view_model import key
from .result_view_model import shown


class CandidateSelectionController(QObject):
    changed = Signal(object)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.candidate_key = None
    def set(self, candidate_key):
        if self.candidate_key != candidate_key:
            self.candidate_key = candidate_key
            self.changed.emit(candidate_key)


class CandidateAuditTableModel(QAbstractTableModel):
    KeyRole = int(Qt.ItemDataRole.UserRole) + 1
    sort_requested = Signal(int, bool)
    headers = ('序号','Candidate ID','Source','Stage','Disposition','Filter Reason',
               'Merged Into','Final Defect ID','初始面积 px²','初始 Feret px')
    def __init__(self, parent=None):
        super().__init__(parent)
        self.audit = None
        self.indexes = ()
        self.page = 0
        self.page_size = 500
    @property
    def pages(self):
        return math.ceil(len(self.indexes)/self.page_size)
    def set_query(self, audit, indexes, page=0):
        self.beginResetModel()
        self.audit, self.indexes = audit, indexes
        self.page = min(max(0,page),max(0,self.pages-1))
        self.endResetModel()
    def set_page(self, page):
        self.set_query(self.audit,self.indexes,page)
    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else max(0,min(self.page_size,len(self.indexes)-self.page*self.page_size))
    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.headers)
    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role==Qt.ItemDataRole.DisplayRole and orientation==Qt.Orientation.Horizontal:
            return self.headers[section]
    def candidate(self, row):
        return self.audit.records[self.indexes[self.page*self.page_size+row]]
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0<=index.row()<self.rowCount(): return None
        c = self.candidate(index.row())
        if role==self.KeyRole: return key(c)
        if role==Qt.ItemDataRole.ForegroundRole and index.column()==4:
            return QColor(dict(RETAINED='#15803d',FILTERED='#64748b',MERGED='#2563eb',REVIEW='#b45309',PENDING='#9333ea')[str(c.disposition)])
        if role in (Qt.ItemDataRole.DisplayRole,Qt.ItemDataRole.ToolTipRole):
            g=c.initial_geometry
            fields=(self.page*self.page_size+index.row()+1,c.candidate_id,c.source,c.current_stage,c.disposition,
                    c.filter_reason,c.merged_into,c.final_defect_id,g.area_px if g else None,g.length_px if g else None)
            return shown(fields[index.column()])
    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        self.sort_requested.emit(column,order==Qt.SortOrder.DescendingOrder)
