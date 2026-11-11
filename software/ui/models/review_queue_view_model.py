"""Virtual review rows and global filtering/sorting. No image or repository I/O."""
from dataclasses import dataclass
from PySide6.QtCore import Qt,QAbstractTableModel,QModelIndex,Signal
from PySide6.QtGui import QColor
from .review_admission.model import ReviewTask,ReviewBucket,ReviewPriority
from .result_view_model import shown


@dataclass(frozen=True)
class ReviewQueueQuery:
    view: str='TASKS'
    kind: str | None=None
    priority: str | None=None
    reason: str | None=None
    band: str | None=None
    source: str | None=None
    sort_column: int=3
    descending: bool=False


def object_key(row):return row.primary_object if isinstance(row,ReviewTask) else row.object_key
def row_key(row):return row.task_key if isinstance(row,ReviewTask) else row.object_key.token
def sources(row):
    source=row.evidence['source']
    return (source,) if isinstance(source,str) else (source or ())


class ReviewQueueViewModel:
    def __init__(self,admission,candidates=()):
        self.admission=admission
        self.tasks=admission.tasks
        self.by_key={row_key(row):row for row in self.tasks}
        self.by_key.update({row_key(row):row for row in admission.decisions})
        self.buckets={bucket:tuple(d for d in admission.decisions if d.bucket==bucket) for bucket in ReviewBucket}
        self.candidates={}
        for c in candidates:
            k=(c.source,c.candidate_id)
            self.candidates[k]=None if k in self.candidates else c

    def query(self,q):
        rows=self.tasks if q.view=='TASKS' else self.buckets[q.view]
        filtered=[]
        for row in rows:
            k=object_key(row)
            if q.kind is not None and k.kind!=q.kind:continue
            if q.priority is not None and row.priority!=q.priority:continue
            if q.reason is not None and q.reason not in row.reasons:continue
            if q.band is not None and (row.evidence['band'] or '—')!=q.band:continue
            if q.source is not None and q.source not in sources(row):continue
            filtered.append(row)
        rank={ReviewPriority.HIGH:0,ReviewPriority.MEDIUM:1,ReviewPriority.LOW:2}
        def order(row):
            k=object_key(row);e=row.evidence
            v=(None,k.kind,k.object_id,rank.get(row.priority,3),','.join(row.reasons),e['area_px'],e['feret_px'],e['band'],','.join(sources(row)),e['final_defect_id'])[q.sort_column]
            return (v is None,v if v is not None else '',k)
        filtered.sort(key=order,reverse=q.descending)
        return tuple(filtered)


class ReviewQueueTableModel(QAbstractTableModel):
    KeyRole=int(Qt.ItemDataRole.UserRole)+1
    sort_requested=Signal(int,bool)
    headers=('序号','对象类型','ID','优先级','准入原因','面积 px²','Feret px','Band','Source','关联最终 Defect')
    def __init__(self,parent=None):
        super().__init__(parent);self.rows=();self.page=0;self.page_size=500
    @property
    def pages(self):return (len(self.rows)+self.page_size-1)//self.page_size
    def set_rows(self,rows,page=0):
        self.beginResetModel();self.rows=rows;self.page=min(max(0,page),max(0,self.pages-1));self.endResetModel()
    def row(self,index):return self.rows[self.page*self.page_size+index]
    def rowCount(self,parent=QModelIndex()):return 0 if parent.isValid() else max(0,min(self.page_size,len(self.rows)-self.page*self.page_size))
    def columnCount(self,parent=QModelIndex()):return 0 if parent.isValid() else len(self.headers)
    def headerData(self,section,orientation,role=Qt.ItemDataRole.DisplayRole):
        if orientation==Qt.Orientation.Horizontal and role==Qt.ItemDataRole.DisplayRole:return self.headers[section]
    def data(self,index,role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row()>=self.rowCount():return None
        row=self.row(index.row());k=object_key(row);e=row.evidence
        if role==self.KeyRole:return row_key(row)
        if role==Qt.ItemDataRole.ForegroundRole and index.column()==3:
            return QColor({'HIGH':'#b91c1c','MEDIUM':'#b45309','LOW':'#64748b'}.get(row.priority,'#64748b'))
        if role in (Qt.ItemDataRole.DisplayRole,Qt.ItemDataRole.ToolTipRole):
            return shown((self.page*self.page_size+index.row()+1,k.kind,k.object_id,row.priority,', '.join(row.reasons),e['area_px'],e['feret_px'],e['band'],', '.join(sources(row)),e['final_defect_id'])[index.column()])
    def sort(self,column,order=Qt.SortOrder.AscendingOrder):self.sort_requested.emit(column,order==Qt.SortOrder.DescendingOrder)
