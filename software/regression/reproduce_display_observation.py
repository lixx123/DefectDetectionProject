"""Explicit real-RAW display acceptance, independent of pytest and release gates.

Run with --raw-path; input discovery and machine-specific fallbacks are forbidden.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]


def build_parser():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-path',type=Path,required=True,help='Explicit source RAW; no fallback or disk search')
    parser.add_argument('--repository',type=Path,default=ROOT/'output/phase4_validation/repository')
    parser.add_argument('--result-id',default='8a363da8-7a3b-4c77-84cf-d13a375c3b15')
    parser.add_argument('--output-dir',type=Path)
    return parser


def stream_sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def observe(raw_path,repository,result_id,output_dir):
    # Imported lazily so --help / missing arguments need no Qt or data access.
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    import time
    from unittest.mock import patch
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from infrastructure.repositories import JsonResultRepository
    from ui.controllers.inspection_controller import InspectionController
    from ui.main_window import MainWindow
    from ui.models.result_view_model import ResultViewModel, ViewMode
    from ui.raw_image_provider import RawImageProvider
    from regression.golden import no_engine_execution
    from regression.comparator import digest

    raw_path=Path(raw_path); out=Path(output_dir)
    out.mkdir(parents=True,exist_ok=False)
    report=dict(status='FAIL',raw_path_source='CLI_ARGUMENT',sha256_streaming=True,
                algorithm_executions=0,human_acceptance='PENDING',
                no_disk_discovery=True,raw_unchanged=False,result_unchanged=False)
    try:
        with no_engine_execution(), patch('core.detector.Detector.inspect',side_effect=AssertionError('Detector forbidden in display acceptance')):
            repo=JsonResultRepository(repository)
            result=repo.load(result_id)
            report['expected_sha256']=result.input_info.sha256
            report['raw_sha256']=stream_sha256(raw_path)
            report['sha256_match']=report['raw_sha256']==report['expected_sha256']
            if not report['sha256_match']:
                raise ValueError('RAW SHA256 does not match the frozen result')
            original=digest(result.to_dict())
            app=QApplication.instance() or QApplication([])
            controller=InspectionController(repo)
            window=MainWindow(controller); window.show()
            def wait():
                end=time.monotonic()+120
                while controller.busy and time.monotonic()<end:
                    app.processEvents(); time.sleep(.005)
                if controller.busy: raise RuntimeError('Display worker did not finish')
                app.processEvents()
            try:
                window.raw=RawImageProvider(raw_path,result.input_info.width_px,result.input_info.height_px)
                window.raw_path=raw_path
                vm=ResultViewModel(result,repo.root/result_id)
                window.display_result(vm)
                defect=min(result.defects,key=lambda d:d.geometry.area_px)
                index=window.proxy.mapFromSource(window.table_model.index(vm.by_id[defect.identity.defect_id],0))
                window.table.setCurrentIndex(index); window.table.selectRow(index.row())
                window.viewer.actual_size(); window.viewer.zoom_by(10)
                window.viewer.select_defect(defect.identity.defect_id,center=True)
                window.viewer.show_ids(True)
                app.processEvents(); window.viewer._refresh_raw_detail()
                item=window.viewer.detail_item
                assert item is not None and window.viewer.mask_items
                assert item.zValue()<window.viewer.mask_items[0].zValue()<10
                x,y=int(item.pos().x()),int(item.pos().y())
                dn=window.raw.dn(x,y)
                assert item.pixmap().toImage().pixelColor(0,0).red()==int(dn*255/4095)
                assert window.grab().save(str(out/'03_final_zoom_raw_detail.png'))
                b=defect.geometry.bbox
                report.update(selected_defect=dict(id=defect.identity.defect_id,
                    measurement_bbox=[b.x0,b.y0,b.x1,b.y1],area_px=defect.geometry.area_px),
                    zoom=window.viewer.zoom,DN=dn,DN_coordinate=[x,y],
                    detail_item_count=sum(i.zValue()==-9 for i in window.viewer.scene().items()),
                    z_order=dict(thumbnail=-10,raw_detail=-9,mask=-8,bbox=10,selected_bbox=15,label=20))
                window.mask_action.setChecked(False); wait()
                window.viewer._refresh_raw_detail()
                assert not window.viewer.mask_items and window.viewer.detail_item is not None
                QTest.mouseMove(window.viewer.viewport(),window.viewer.mapFromScene(defect.geometry.center.x,defect.geometry.center.y))
                app.processEvents()
                assert window.grab().save(str(out/'07_raw_detail_mask_off.png'))
                report['raw_pointer_text']=window.pointer.text()
                report['result_unchanged']=digest(result.to_dict())==original
                report['raw_unchanged']=stream_sha256(raw_path)==report['raw_sha256']
                assert report['result_unchanged'] and report['raw_unchanged']
                report['status']='PASS'
            finally:
                wait()
                window.close()
    except Exception as exc:
        report['error']=f'{type(exc).__name__}: {exc}'
    (out/'display_observation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report


def main(argv=None):
    args=build_parser().parse_args(argv)
    output=args.output_dir or ROOT/'output/display_observation'/(
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'_'+uuid4().hex[:8])
    report=observe(args.raw_path,args.repository,args.result_id,output)
    print(json.dumps(dict(status=report['status'],output_dir=str(output),
        sha256_match=report.get('sha256_match',False),algorithm_executions=0),ensure_ascii=False))
    return 0 if report['status']=='PASS' else 1


if __name__=='__main__':
    raise SystemExit(main())
