import unittest,tempfile,sys,json,shutil,struct,os
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import importer as m
class TestImporter(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();self.target=self.root/'dev_hdd0/home/00000001/savedata';self.target.mkdir(parents=True)
  self.closed=patch.object(m,'ensure_closed');self.closed.start()
 def tearDown(self):self.closed.stop();self.tmp.cleanup()
 def plan(self,ids=('e-online',)):return m.make_plan(self.target,ids)
 def old(self,name='E01'):
  p=self.target/(m.PREFIX+name);p.mkdir();(p/'USERDATA.BIN').write_bytes(b'original progress');(p/'nested').mkdir();(p/'nested/other').write_bytes(b'detail');return p
 def test_payload_slot_metadata(self):
  for item in m.read_catalog():
   b=(m.HERE/'saves'/item['id']/'PARAM.SFO').read_bytes();_,_,ks,ds,n=struct.unpack_from('<5I',b)
   fields={}
   for i in range(n):
    ko,fmt,l,cap,o=struct.unpack_from('<HHIII',b,20+i*16);fields[b[ks+ko:].split(b'\0')[0].decode()]=b[ds+o:ds+o+l].split(b'\0')[0]
   self.assertEqual(fields['SAVEDATA_DIRECTORY'].decode(),item['directory']);self.assertEqual(fields['SUB_TITLE'].decode(),item['title'])
 def test_all_import_restore_and_story_preserved(self):
  old=self.old();before=m.snapshot(old);story=self.target/'BLJS10050-STORY';story.mkdir();(story/'data').write_bytes(b'keep')
  rp=m.install(self.plan([x['id'] for x in m.read_catalog()]));self.assertEqual(len(list(self.target.glob(m.PREFIX+'*'))),4)
  for x in m.read_catalog():self.assertEqual(m.snapshot(self.target/x['directory']),x['hashes'])
  m.restore(rp);self.assertEqual(m.snapshot(old),before);self.assertEqual(len(list(self.target.glob(m.PREFIX+'*'))),1);self.assertEqual((story/'data').read_bytes(),b'keep')
 def test_single_only_and_repeat(self):
  m.install(self.plan());self.assertEqual(len(list(self.target.iterdir())),1);self.assertIsNone(m.install(self.plan()))
 def test_changed_since_preview(self):
  plan=self.plan();self.old()
  with self.assertRaises(m.ImportErrorSafe):m.install(plan)
  self.assertFalse((self.target.parent/'SuitenSaveBackups').exists())
 def test_restore_refuses_new_progress(self):
  rp=m.install(self.plan());p=self.target/(m.PREFIX+'E01')/'USERDATA.BIN';p.write_bytes(b'new progress')
  with self.assertRaises(m.ImportErrorSafe):m.restore(rp)
  self.assertEqual(p.read_bytes(),b'new progress')
 def test_corrupt_backup(self):
  self.old();rp=m.install(self.plan());(rp.parent/'before'/(m.PREFIX+'E01')/'USERDATA.BIN').write_bytes(b'bad')
  after=m.snapshot(self.target/(m.PREFIX+'E01'))
  with self.assertRaises(m.ImportErrorSafe):m.restore(rp)
  self.assertEqual(m.snapshot(self.target/(m.PREFIX+'E01')),after)
 def test_write_failure_rolls_back_all(self):
  a=self.old('E01');b=self.old('E00');before={p.name:m.snapshot(p) for p in self.target.iterdir()};replace=os.replace;failed=False
  def broken(src,dst):
   nonlocal failed
   if Path(src).parent.name=='new' and Path(src).name.endswith('E00') and not failed:
    failed=True;raise OSError('simulated disk error')
   return replace(src,dst)
  with patch.object(m.os,'replace',side_effect=broken):
   with self.assertRaises(OSError):m.install(self.plan(['e-online','e-all']))
  self.assertTrue(failed);self.assertEqual({p.name:m.snapshot(p) for p in self.target.iterdir()},before)
 def test_restore_failure_rolls_back(self):
  self.old();rp=m.install(self.plan(['e-online','e-all']));before={p.name:m.snapshot(p) for p in self.target.iterdir()};replace=os.replace;failed=False
  def broken(src,dst):
   nonlocal failed
   if Path(src).parent.name=='new' and not failed:
    failed=True;raise OSError('restore error')
   return replace(src,dst)
  with patch.object(m.os,'replace',side_effect=broken):
   with self.assertRaises(OSError):m.restore(rp)
  self.assertEqual({p.name:m.snapshot(p) for p in self.target.iterdir()},before)
 def test_ambiguous_users(self):
  (self.root/'dev_hdd0/home/00000002').mkdir();self.assertEqual(len(m.targets(self.root)),2)
 def test_game_path_rejected(self):
  p=self.root/'Game/PS3_GAME';p.mkdir(parents=True)
  with self.assertRaises(m.ImportErrorSafe):m.targets(p)
 def test_lock_protects(self):
  with m.lock(self.target):
   with self.assertRaises(m.ImportErrorSafe):m.install(self.plan())
 def test_space_preflight(self):
  with patch.object(m.shutil,'disk_usage',return_value=type('D',(),{'free':0})()):
   with self.assertRaises(m.ImportErrorSafe):m.install(self.plan())
  self.assertEqual(list(self.target.iterdir()),[])
 def test_symlink_refused(self):
  actual=self.root/'actual';actual.mkdir()
  try:(self.target/(m.PREFIX+'E01')).symlink_to(actual,target_is_directory=True)
  except OSError:self.skipTest('此环境无创建符号链接权限')
  with self.assertRaises(m.ImportErrorSafe):self.plan()
 def test_payload_corruption_refused(self):
  copy=self.root/'bundle';shutil.copytree(m.HERE,copy,ignore=shutil.ignore_patterns('__pycache__'))
  (copy/'saves/e-online/USERDATA.BIN').write_bytes(b'bad')
  with patch.object(m,'HERE',copy):
   with self.assertRaises(m.ImportErrorSafe):self.plan()
 def test_process_check_blocks(self):
  self.closed.stop()
  with patch.object(m.subprocess,'check_output',return_value=(b'"rpcs3.exe","123","Console"\n' if os.name=='nt' else b'/Applications/RPCS3.app/Contents/MacOS/rpcs3\n')):
   with self.assertRaises(m.ImportErrorSafe):m.ensure_closed()
  self.closed.start()
 def test_process_check_windows(self):
  self.closed.stop()
  with patch.object(m.os,'name','nt'),patch.object(m.subprocess,'check_output',return_value=b'"rpcs3.exe","123","Console","1","123 K"\n'):
   with self.assertRaises(m.ImportErrorSafe):m.ensure_closed()
  self.closed.start()
 def test_check_failure_closed(self):
  self.closed.stop()
  with patch.object(m.subprocess,'check_output',side_effect=OSError('access denied')):
   with self.assertRaises(m.ImportErrorSafe):m.ensure_closed()
  self.closed.start()
if __name__=='__main__':unittest.main(verbosity=2)
