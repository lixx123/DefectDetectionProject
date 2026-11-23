"""Direct coverage of the official scripts_v3 H3 chain (2026-11-23 repair).

These tests import the chain modules themselves (scripts/h3_b151/scripts_v3),
not the legacy scripts.run_case03j4_fullscan stand-ins.
"""
from __future__ import annotations
import importlib.util,json,os,shutil,subprocess,sys,tempfile,unittest
from inspect import signature
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
CHAIN=ROOT/'scripts/h3_b151/scripts_v3'
for p in (str(ROOT),str(CHAIN)):
    while p in sys.path:sys.path.remove(p)
sys.path.insert(0,str(CHAIN));sys.path.insert(0,str(ROOT))
import stage_j4,stage_process,stage_refine,timings
from src.detection.case03g_joint_gate import JointGateConfig,decide_gate

DISABLE=65536.


def write_raster(directory:Path,ids:np.ndarray,name:str='ids.npy')->str:
    directory.mkdir(parents=True,exist_ok=True)
    path=directory/name
    np.save(path,ids)
    return str(path)


def spec_for(ids_path:str,bands:dict[int,tuple[float,float]]|None=None)->dict:
    bands=bands if bands is not None else {1:(10.,20.),2:(30.,40.)}
    return dict(bands=[dict(band_id=k,low_dn=v[0],high_dn=v[1]) for k,v in bands.items()],
                fallback=[DISABLE,DISABLE],pixel_band_ids=ids_path)


class ThresholdMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=Path(tempfile.mkdtemp(prefix='h3map_'))
        ids=np.zeros((6,8),np.uint8)
        ids[1:3,:]=1
        ids[3:5,2:6]=2
        cls.ids=ids
        cls.path=write_raster(cls.tmp,ids)
        cls.spec=spec_for(cls.path)

    def tearDown(self):
        stage_j4.clear_band_map_cache()

    def test_every_pixel_uses_its_own_band_threshold(self):
        lo,hi,applied=stage_j4.threshold_maps(self.spec,0,0,8,6)
        self.assertEqual(lo.shape,(6,8))
        self.assertTrue(np.all(lo[1:3]==10.)and np.all(hi[1:3]==20.))
        self.assertTrue(np.all(lo[3:5,2:6]==30.)and np.all(hi[3:5,2:6]==40.))
        outside=self.ids==0
        self.assertTrue(np.all(lo[outside]==DISABLE)and np.all(hi[outside]==DISABLE))
        self.assertTrue(np.all(hi>=lo))
        counts={int(a['band_id']):int(a['pixels']) for a in applied}
        self.assertEqual(counts,{1:16,2:8,0:24})
        self.assertEqual(sum(counts.values()),48)

    def test_subwindow_matches_full_window(self):
        lo,hi,_=stage_j4.threshold_maps(self.spec,2,1,6,5)
        full_lo,full_hi,_=stage_j4.threshold_maps(self.spec,0,0,8,6)
        self.assertEqual(lo.shape,(4,4))
        np.testing.assert_array_equal(lo,full_lo[1:5,2:6])
        np.testing.assert_array_equal(hi,full_hi[1:5,2:6])

    def test_window_outside_raster_is_rejected(self):
        for window in [(0,0,9,6),(0,0,8,7),(-1,0,8,6),(0,0,0,6)]:
            with self.subTest(window=window):
                with self.assertRaises(ValueError):
                    stage_j4.threshold_maps(self.spec,*window)

    def test_unknown_band_id_never_falls_back_to_a_fixed_threshold(self):
        other=np.zeros((4,4),np.uint8);other[1,1]=7
        path=write_raster(self.tmp/'unknown',other)
        with self.assertRaisesRegex(ValueError,'absent from the frozen spec'):
            stage_j4.threshold_maps(spec_for(path),0,0,4,4)

    def test_band_map_cache_lifecycle_is_per_run(self):
        import gc
        path=write_raster(self.tmp/'lifecycle',self.ids)
        spec=spec_for(path)
        stage_j4.threshold_maps(spec,0,0,8,6)
        self.assertTrue(stage_j4._BAND_MAP_CACHE)
        # The cached band raster is an mmap, so on Windows the file can only be
        # replaced after the per-run cache released it.
        stage_j4.clear_band_map_cache();gc.collect()
        np.save(path,np.full((6,8),2,np.uint8))
        lo,hi,applied=stage_j4.threshold_maps(spec,0,0,8,6)
        self.assertTrue(np.all(lo==30.))
        self.assertEqual(int(applied[1]['pixels']),48)

    def test_invalid_specs_fail_before_any_threshold_surface(self):
        duplicated=dict(band_id=1,low_dn=10.,high_dn=20.)
        cases=[
            ('missing fallback',lambda s:s.pop('fallback')),
            ('missing raster',lambda s:s.pop('pixel_band_ids')),
            ('no bands',lambda s:s.update(bands=[])),
            ('band field',lambda s:s['bands'][0].pop('high_dn')),
            ('duplicate band',lambda s:s.update(bands=[duplicated,dict(duplicated)])),
            ('nan low',lambda s:s['bands'][0].update(low_dn=float('nan'))),
            ('inf high',lambda s:s['bands'][1].update(high_dn=float('inf'))),
            ('low>=high',lambda s:s['bands'][0].update(low_dn=25.,high_dn=20.)),
            ('fixed fallback',lambda s:s.update(fallback=[170.,230.])),
            ('asymmetric fallback',lambda s:s.update(fallback=[DISABLE,1000.])),
            ('raster not on disk',lambda s:s.update(pixel_band_ids=str(self.tmp/'gone.npy'))),
        ]
        for label,mutate in cases:
            spec=json.loads(json.dumps(self.spec))
            mutate(spec)
            with self.subTest(label):
                with self.assertRaises(ValueError):
                    stage_j4.threshold_maps(spec,0,0,8,6)


class ThresholdContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp=Path(tempfile.mkdtemp(prefix='h3contract_'))
        self.path=write_raster(self.tmp,np.ones((300,300),np.uint8))

    def tearDown(self):
        stage_j4.clear_band_map_cache()

    def test_run_tile_default_is_b15_pixel_with_no_spec(self):
        parameters=signature(stage_j4.run_tile).parameters
        self.assertEqual(parameters['threshold_mode'].default,'b15_pixel')
        self.assertIsNone(parameters['perband_spec'].default)

    def test_run_tile_refuses_before_touching_input_arrays(self):
        # rawmem/fused/pcfg are None on purpose: reaching array work would raise
        # AttributeError instead of the contract ValueError.
        cases=[dict(threshold_mode='b15_pixel',perband_spec=None),
               dict(threshold_mode='fixed_170_230',perband_spec=spec_for(self.path)),
               dict(threshold_mode='adaptive',perband_spec=spec_for(self.path))]
        for kwargs in cases:
            with self.subTest(**kwargs):
                with self.assertRaises(ValueError):
                    stage_j4.run_tile(dict(tile_id='T000_000',core_xyxy=[0,0,256,256]),
                                      None,None,None,None,None,None,64,self.tmp,**kwargs)

    def test_no_fixed_scalar_route_reaches_refinement(self):
        raw=np.full((300,300),1000,np.uint16)
        response=np.zeros((300,300),np.uint16)
        response[10:20,10:20]=500
        refine,seed,f,g,h=stage_process.policies()
        with self.assertRaises(TypeError):
            stage_process.process_one(raw,response,170.,230.,refine,seed,f,g,h)

    def test_chain_modules_expose_no_hardcoded_threshold_token(self):
        for name in ['stage_j4.py','stage_process.py','stage_refine.py','detector.py']:
            text=(CHAIN/name).read_text(encoding='utf-8')
            for token in ('H170_230','fixed_170_230','h_low_threshold_dn'):
                self.assertNotIn(token,text,name)


class GateRenamingTests(unittest.TestCase):
    def test_source_rename_cannot_flip_gate_protection(self):
        labels=np.zeros((40,40),np.int32)
        labels[30:32,30:32]=1       # 4px, isolated, below protect area
        labels[2:4,2:9]=2           # 14px, far away, counts as support
        stats=np.array([[0,0,0,0,0],[4,30,30,2,2],[14,2,2,7,2]],np.int32)
        cfg=JointGateConfig()
        legacy=decide_gate(labels,stats,['suggest_hide','suggest_hide'],
                           [('H170_230',),('H170_230','closing61')],cfg)
        current=decide_gate(labels,stats,['suggest_hide','suggest_hide'],
                            [(stage_refine.H_SOURCE,),(stage_refine.H_SOURCE,'closing61')],cfg)
        self.assertEqual(legacy,current)
        self.assertEqual(current[0],['hide_suggestion','protected_review'])


class TimingTests(unittest.TestCase):
    def setUp(self):
        timings.clear()

    def tearDown(self):
        timings.clear()

    def test_real_chain_function_is_timed_once_per_defining_module(self):
        response=np.zeros((64,64),np.float32)
        response[10:20,10:20]=30.
        response[30:36,30:36]=80.
        low=np.full(response.shape,20.);high=np.full(response.shape,50.)
        from src.detection import case03t_adaptive_hysteresis as adaptive
        original=adaptive.hysteresis_window
        self.assertIs(stage_process.hysteresis_window,original)
        with timings.instrument():
            self.assertIs(stage_process.hysteresis_window,adaptive.hysteresis_window,
                          'aliases must share one wrapper')
            self.assertIsNot(adaptive.hysteresis_window,original)
            adaptive.hysteresis_window(response,low,high)
            stage_process.hysteresis_window(response,low,high)
            with self.assertRaises(RuntimeError):
                with timings.instrument():
                    pass
        rows={(r['defining_module'],r['function']):r for r in timings.rows('s','A1','M')}
        key=('src.detection.case03t_adaptive_hysteresis','hysteresis_window')
        self.assertIn(key,rows)
        self.assertEqual(rows[key]['calls'],2)
        self.assertGreater(rows[key]['inclusive_seconds'],0.)
        self.assertEqual(len(rows),1,'no fabricated zero-call rows')
        self.assertFalse(timings.STACK)
        self.assertIs(adaptive.hysteresis_window,original)
        self.assertIs(stage_process.hysteresis_window,original)
        self.assertFalse(timings.STATS['active'])

    def test_nested_inclusive_and_exclusive(self):
        from src.detection import case03i_size_grade as grade
        mask=np.zeros((40,40),bool);mask[5:15,5:25]=True
        with timings.instrument():
            # Call through the module attribute: a name bound before wrapping
            # would bypass the wrapper.
            grade.extract_regions(mask,grade.SizeGradeConfig(),'T000_000',(0,0,40,40))
        self.assertFalse(timings.STACK)
        rows={(r['defining_module'],r['function']):r for r in timings.rows('s','A1','M')}
        outer=rows[('src.detection.case03i_size_grade','extract_regions')]
        inner=rows[('src.detection.case03i_size_grade','max_feret_centers_px')]
        self.assertEqual(outer['calls'],1)
        self.assertGreater(inner['calls'],0)
        self.assertGreaterEqual(outer['inclusive_seconds'],inner['inclusive_seconds'])
        self.assertAlmostEqual(inner['exclusive_seconds'],inner['inclusive_seconds'],
                               delta=1e-9,msg='a leaf has no child time to subtract')
        self.assertLess(outer['exclusive_seconds'],outer['inclusive_seconds'],
                        'nested child time must leave the outer exclusive row')

    def test_functions_restore_after_an_exception(self):
        from src.detection import case03i_size_grade as grade
        original=grade.extract_regions
        with self.assertRaises(ValueError):
            with timings.instrument():
                grade.extract_regions(np.zeros((8,8),bool),grade.SizeGradeConfig(),'T0',(0,0,40,40))
        self.assertIs(grade.extract_regions,original)
        self.assertFalse(timings.STATS['active'])
        self.assertFalse(timings.STACK)

    def test_prefix_lookalike_directory_is_not_instrumented(self):
        decoy=CHAIN.parent/(CHAIN.name+'_lookalike')
        shutil.rmtree(decoy,ignore_errors=True)
        decoy.mkdir()
        try:
            module_file=decoy/'decoy_module.py'
            module_file.write_text('def hysteresis_window(a,b,c):\n    return "decoy"\n',encoding='utf-8')
            spec=importlib.util.spec_from_file_location('decoy_module',module_file)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            original=module.hysteresis_window
            with timings.instrument():
                self.assertIs(module.hysteresis_window,original,
                              'sibling directories sharing a path prefix must stay untouched')
        finally:
            shutil.rmtree(decoy,ignore_errors=True)

    def test_overhead_probe_leaves_no_statistics(self):
        per=timings.measure_overhead(calls=500)
        self.assertGreater(per,0.)
        self.assertEqual(timings.STATS['wrapped_calls'],0)
        self.assertEqual(list(timings.DATA),[])

    def test_rows_declare_unmeasurable_dimensions(self):
        timings.DATA[('m','f')]['calls']=1
        row=timings.rows('s','A1','M')[0]
        self.assertEqual(row['function_allocated_memory'],'NOT_VERIFIABLE')
        self.assertEqual(row['physical_disk_IO'],'NOT_VERIFIABLE')

    def test_stack_leftover_is_measured_not_assumed(self):
        with timings.instrument():
            pass
        self.assertEqual(timings.stats()['stack_leftover'],0)
        timings.clear()
        with timings.instrument():
            timings.STACK.append([0.])
        self.assertEqual(timings.stats()['stack_leftover'],1,
                         'a stale entry must surface in the audit, not be reported as zero')
        self.assertFalse(timings.STACK,'the stale entry is still cleared on exit')


CHILD=r'''
import sys,json,tempfile
from pathlib import Path
import numpy as np, cv2
ROOT=Path(sys.argv[1]);CHAIN=ROOT/'scripts/h3_b151/scripts_v3'
sys.path.insert(0,str(CHAIN));sys.path.insert(0,str(ROOT))
import stage_j4
from src.visualization import case03j_object_boxes as boxes
loaded=[name for name,module in list(sys.modules.items())
        if 'run_case03g' in name or 'run_case03g' in str(getattr(module,'__file__',''))]
sys.path.insert(0,str(ROOT/'scripts'))
from run_case03g_joint_noise_refinement import gray as legacy_gray
rng=np.random.default_rng(7)
cases=[rng.integers(0,4096,(64,64)).astype(np.uint16),
       np.full((32,32),7,np.uint16),
       np.broadcast_to(np.arange(16,dtype=np.uint16),(16,16)).copy()]
same=all(np.array_equal(legacy_gray(a),stage_j4.gray(a))
         and np.array_equal(legacy_gray(a),boxes.gray(a)) for a in cases)
raw=cases[0].copy();stage_j4.gray(raw)
untouched=bool(np.array_equal(raw,cases[0]))
tmp=Path(tempfile.mkdtemp())/'疵病检测 中文'/'子目录'
image=cv2.cvtColor(np.zeros((4,4),np.uint8),cv2.COLOR_GRAY2BGR)
stage_j4.save_png(tmp/'small.png',image)
written=(tmp/'small.png')
ok=written.is_file() and written.stat().st_size<1000
decoded=cv2.imdecode(np.frombuffer(written.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
roundtrip=decoded is not None and decoded.shape==(4,4,3)
print(json.dumps(dict(loaded=loaded,display_identical=bool(same),raw_untouched=untouched,
                      unicode_small_png=bool(ok),roundtrip=bool(roundtrip))))
'''


class IsolationAndDisplayTests(unittest.TestCase):
    def test_child_process_report(self):
        env=dict(os.environ,PYTHONIOENCODING='utf-8')
        probe=ROOT/'.h3_chain_isolation_probe.py'
        probe.write_text(CHILD,encoding='utf-8')
        try:
            result=subprocess.run([sys.executable,'-B',str(probe),str(ROOT)],
                                  capture_output=True,text=True,env=env,cwd=str(ROOT),timeout=600)
        finally:
            probe.unlink(missing_ok=True)
        self.assertEqual(result.returncode,0,result.stderr[-2000:])
        report=json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(report['loaded'],[],
                         'importing the production chain must not load the manual-review script')
        self.assertTrue(report['display_identical'],'display stretch must match the original helper')
        self.assertTrue(report['raw_untouched'],'display helper must not modify RAW')
        self.assertTrue(report['unicode_small_png'],'small PNG on a Unicode path must be written')
        self.assertTrue(report['roundtrip'])



class TimerIdentityTests(unittest.TestCase):
    def test_distinct_same_named_functions_restore_independently(self):
        import types
        from unittest.mock import patch
        first=lambda:1
        second=lambda:2
        first.__name__=second.__name__='extract_regions'
        first.__module__=second.__module__='same_module'
        module=types.ModuleType('identity_probe')
        module.first=first
        module.second=second
        key=('same_module','extract_regions')
        timings.clear()
        with patch.object(timings,'targets',return_value={(module,'first'):key,(module,'second'):key}):
            with timings.instrument():
                self.assertEqual(module.first(),1)
                self.assertEqual(module.second(),2)
        self.assertIs(module.first,first)
        self.assertIs(module.second,second)

if __name__=='__main__':
    unittest.main(verbosity=2)
