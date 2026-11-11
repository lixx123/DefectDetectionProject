"""Graphics scene in original image pixels; overlays are independent items."""
from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QTimer
from PySide6.QtGui import QPen, QColor, QPixmap, QPainter
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsRectItem, QGraphicsSimpleTextItem


class DefectItem(QGraphicsRectItem):
    def __init__(self, overlay, callback):
        x0, y0, x1, y1 = overlay.display_bbox
        super().__init__(QRectF(x0, y0, x1 - x0, y1 - y0))
        self.measurement_bbox = overlay.measurement_bbox
        self.defect_id = overlay.defect_id
        self.callback = callback
        self.color = {'SMALL': '#38bdf8', 'MEDIUM': '#fbbf24', 'LARGE': '#fb7185'}.get(overlay.grade, '#e2e8f0')
        self.setZValue(10)
        self.setToolTip(self.defect_id)
        self.highlight(False)

    def highlight(self, active):
        pen = QPen(QColor('#ffffff' if active else self.color), 3 if active else 1.6)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setZValue(15 if active else 10)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.callback(self.defect_id)
            event.accept()
        else:
            super().mousePressEvent(event)


class ImageViewer(QGraphicsView):
    defect_selected = Signal(str)
    pointer_changed = Signal(object, object, object, float)
    zoom_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setBackgroundBrush(QColor('#101721'))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setMouseTracking(True)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.overlays, self.id_labels = {}, {}
        self.band_labels = []
        self.mask_items = []
        self.selected_id = None
        self.boxes_visible, self.ids_visible = True, False
        self.raw_provider = None
        self.task_controller=None
        self._raw_detail_revision=0
        self._raw_detail_pending=False
        self._pending_pointer=None
        self.base_item = None
        self.image_rect = QRectF()
        self.detail_item = None
        self.detail_enabled = False
        self._detail_timer = QTimer(self)
        self._detail_timer.setSingleShot(True)
        self._detail_timer.timeout.connect(self._refresh_raw_detail)

    @property
    def zoom(self):
        return self.transform().m11()

    def clear(self):
        self._raw_detail_revision+=1;self._raw_detail_pending=False;self._pending_pointer=None
        self._detail_timer.stop()
        self.scene().clear()
        self.overlays.clear()
        self.id_labels.clear()
        self.band_labels.clear()
        self.mask_items.clear()
        self.selected_id = None
        self.base_item = None
        self.detail_item = None
        self.detail_enabled = False
        self.raw_provider = None
        self.image_rect = QRectF()
        self.resetTransform()
        self.scene().setSceneRect(QRectF())
        self.zoom_changed.emit(self.zoom)

    def set_frame(self, frame, *, fit=False):
        self._raw_detail_revision+=1;self._raw_detail_pending=False;self._pending_pointer=None
        if frame.image.isNull() or frame.image.width()<=0 or frame.image.height()<=0 or frame.width<=0 or frame.height<=0:
            self.clear()
            self.scene().addSimpleText('图像不可用：空图或无效尺寸').setBrush(QColor('#ffffff'))
            return
        if self.detail_item is not None:
            self.scene().removeItem(self.detail_item)
            self.detail_item = None
        if self.base_item is not None:
            self.scene().removeItem(self.base_item)
        for item in self.band_labels:
            self.scene().removeItem(item)
        self.band_labels.clear()
        for item in self.mask_items:
            self.scene().removeItem(item)
        self.mask_items.clear()
        self.base_item = self.scene().addPixmap(QPixmap.fromImage(frame.image))
        from PySide6.QtGui import QTransform
        transform = QTransform.fromScale(frame.width / frame.image.width(), frame.height / frame.image.height())
        self.base_item.setTransform(transform)
        self.base_item.setZValue(-10)
        for layer in frame.layers:
            item = self.scene().addPixmap(QPixmap.fromImage(layer))
            item.setTransform(transform)
            item.setZValue(-8)
            self.mask_items.append(item)
        self.image_rect = QRectF(0, 0, frame.width, frame.height)
        self.scene().setSceneRect(self.image_rect)
        for text, x, y in frame.labels:
            item = self.scene().addSimpleText(text)
            item.setBrush(QColor('#ffffff'))
            item.setFlag(QGraphicsSimpleTextItem.GraphicsItemFlag.ItemIgnoresTransformations)
            item.setPos(x, y)
            item.setZValue(20)
            self.band_labels.append(item)
        if fit:
            self.fit()

    def set_overlays(self, overlays):
        for item in (*self.overlays.values(), *self.id_labels.values()):
            self.scene().removeItem(item)
        self.overlays.clear()
        self.id_labels.clear()
        self.selected_id = None
        for overlay in overlays:
            item = DefectItem(overlay, self._clicked)
            self.scene().addItem(item)
            self.overlays[overlay.defect_id] = item
            label = self.scene().addSimpleText(overlay.defect_id)
            label.setBrush(QColor(item.color))
            label.setPos(overlay.display_bbox[0], overlay.display_bbox[1])
            label.setFlag(QGraphicsSimpleTextItem.GraphicsItemFlag.ItemIgnoresTransformations)
            label.setZValue(20)
            label.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.id_labels[overlay.defect_id] = label
        self.show_boxes(self.boxes_visible)
        self.show_ids(self.ids_visible)

    def _clicked(self, defect_id):
        self.select_defect(defect_id)
        self.defect_selected.emit(defect_id)

    def select_defect(self, defect_id, *, center=False):
        if defect_id not in self.overlays:
            return
        self.selected_id = defect_id
        for key, item in self.overlays.items():
            item.highlight(key == defect_id)
        if center:
            item = self.overlays[defect_id]
            # At most 1:1 when navigating from fit; preserve an existing closer view.
            if self.zoom < 0.7:
                self.resetTransform()
                self.scale(0.7, 0.7)
            x0, y0, x1, y1 = item.measurement_bbox
            self.centerOn((x0+x1)/2, (y0+y1)/2)
            self.zoom_changed.emit(self.zoom)
            self._detail_timer.start(30)

    def show_boxes(self, visible):
        self.boxes_visible = visible
        for item in self.overlays.values():
            item.setVisible(visible)

    def show_ids(self, visible):
        self.ids_visible = visible
        for item in self.id_labels.values():
            item.setVisible(visible)

    def fit(self):
        if not self.image_rect.isEmpty():
            self.fitInView(self.image_rect, Qt.AspectRatioMode.KeepAspectRatio)
            self.zoom_changed.emit(self.zoom)
            self._detail_timer.start(30)

    def actual_size(self):
        self.resetTransform()
        self.zoom_changed.emit(self.zoom)
        self._detail_timer.start(30)

    def zoom_by(self, factor, anchor=None):
        target = min(32., max(0.01, self.zoom * factor))
        anchor = anchor or self.viewport().rect().center()
        before = self.mapToScene(anchor)
        self.scale(target / self.zoom, target / self.zoom)
        delta = self.mapToScene(anchor) - before
        self.translate(delta.x(), delta.y())
        self.zoom_changed.emit(self.zoom)
        self._detail_timer.start(30)

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        if hasattr(self, '_detail_timer'):
            self._detail_timer.start(40)

    def set_task_controller(self,controller):
        if self.task_controller is controller:return
        if self.task_controller is not None:raise ValueError('viewer controller already assigned')
        self.task_controller=controller
        controller.completed.connect(self._raw_detail_ready)
        controller.busy_changed.connect(self._raw_detail_idle)

    def _raw_detail_idle(self,busy):
        if not busy and self._raw_detail_pending:self._refresh_raw_detail()
        if not busy and not self.task_controller.busy and self._pending_pointer:
            provider,x,y=self._pending_pointer;self._pending_pointer=None
            if provider is self.raw_provider:
                try:dn=provider.dn(x,y)
                except Exception as exc:
                    dn=None;self.task_controller.report_exception(exc,operation='viewer_detail')
                self.pointer_changed.emit(x,y,dn,self.zoom)

    def _raw_detail_ready(self,kind,value):
        if kind!='viewer_detail':return
        key,image,x,y=value
        if key!=(id(self),self._raw_detail_revision,id(self.raw_provider)):return
        try:
            if self.detail_item is not None:self.scene().removeItem(self.detail_item)
            self.detail_item=self.scene().addPixmap(QPixmap.fromImage(image))
            self.detail_item.setPos(x,y);self.detail_item.setZValue(-9)
        except Exception as exc:
            if self.task_controller:self.task_controller.report_exception(exc,operation='viewer_detail')
            else:raise

    def _refresh_raw_detail(self):
        self._raw_detail_revision+=1
        if self.detail_item is not None:
            self.scene().removeItem(self.detail_item);self.detail_item=None
        if not self.detail_enabled or self.raw_provider is None or self.zoom<0.7:
            self._raw_detail_pending=False;return
        rect=self.mapToScene(self.viewport().rect()).boundingRect().intersected(self.image_rect)
        import math
        x0,y0=max(0,math.floor(rect.left())),max(0,math.floor(rect.top()))
        x1=min(self.raw_provider.width,math.ceil(rect.right()));y1=min(self.raw_provider.height,math.ceil(rect.bottom()))
        if x1<=x0 or y1<=y0 or (x1-x0)*(y1-y0)>4_000_000:return
        raw=self.raw_provider;key=(id(self),self._raw_detail_revision,id(raw))
        if self.task_controller is None:
            # Standalone display API compatibility. App windows attach a controller.
            self._raw_detail_ready('viewer_detail',(key,raw.crop(x0,y0,x1,y1),x0,y0));return
        if self.task_controller.busy:self._raw_detail_pending=True;return
        self._raw_detail_pending=False
        self.task_controller.submit('viewer_detail',lambda:(key,raw.crop(x0,y0,x1,y1),x0,y0))

    def wheelEvent(self, event):
        self.zoom_by(1.25 if event.angleDelta().y() > 0 else 0.8, event.position().toPoint())
        event.accept()

    def mouseMoveEvent(self, event):
        point = self.mapToScene(event.position().toPoint())
        x, y = int(point.x() // 1), int(point.y() // 1)
        if self.image_rect.contains(QPointF(x, y)) and x < self.image_rect.width() and y < self.image_rect.height():
            self._pending_pointer=(self.raw_provider,x,y) if self.raw_provider and self.task_controller and self.task_controller.busy else None
            # A leased RAW crop owns the same lock: never wait for it in GUI.
            try:dn = self.raw_provider.dn(x, y) if self.raw_provider and not (self.task_controller and self.task_controller.busy) else None
            except Exception as exc:
                dn=None
                if self.task_controller:self.task_controller.report_exception(exc,operation='viewer_detail')
                else:raise
            self.pointer_changed.emit(x, y, dn, self.zoom)
        else:
            self._pending_pointer=None
            self.pointer_changed.emit(None, None, None, self.zoom)
        super().mouseMoveEvent(event)
