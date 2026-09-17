import unittest,tempfile,json,hashlib,sys
from pathlib import Path
from unittest.mock import patch
import install_patch as app
H=lambda b:hashlib.sha256(b).hexdigest()
class InstallerTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.game=self.root/'game';self.data=self.root/'rpcs3';(self.game/'PS3_GAME/USRDIR').mkdir(parents=True);(self.game/'PS3_GAME/PARAM.SFO').write_bytes(b'fixture');self.update=self.data/'dev_hdd0/game/BLJS10050';(self.update/'USRDIR/patch').mkdir(parents=True);(self.update/'USRDIR/cache').mkdir();self.old=b'original bytes';self.new=b'Chinese data';self.rows=[]
  for scope,rel,root in [('game','PS3_GAME/USRDIR/game.arb',self.game),('update','USRDIR/patch/patch0100_arb.sdat',self.update)]:
   (root/rel).write_bytes(self.old);name=scope+'.bin';(self.root/name).write_bytes(self.new);self.rows.append(dict(scope=scope,path=rel,source_bytes=len(self.old),source_sha256=H(self.old),target_bytes=len(self.new),target_sha256=H(self.new),blob=name,blob_sha256=H(self.new),segments=[dict(type='add',offset=0,size=len(self.new))]))
  (self.update/'USRDIR/cache/game.arb').write_bytes(self.old);(self.root/'manifest.json').write_text(json.dumps(dict(format=1,title_id='BLJS10050',release='fixture',patches=self.rows)))
 def run_app(self,*extra):
  with patch.object(app,'ROOT',self.root),patch.object(sys,'argv',['install_patch.py','--game',str(self.game),'--rpcs3',str(self.data),*extra]):app.main()
 def test_install_and_restore_including_cache(self):
  self.run_app();self.assertEqual((self.update/'USRDIR/cache/game.arb').read_bytes(),self.new);self.run_app('--restore');self.assertEqual((self.game/'PS3_GAME/USRDIR/game.arb').read_bytes(),self.old);self.assertEqual((self.update/'USRDIR/cache/game.arb').read_bytes(),self.old)
 def test_second_install_is_idempotent(self):
  self.run_app();before=(self.game/'.suiten-cn-install.json').read_bytes();self.run_app();self.assertEqual((self.game/'.suiten-cn-install.json').read_bytes(),before)
 def test_wrong_source_no_writes(self):
  (self.update/self.rows[1]['path']).write_bytes(b'wrong')
  with self.assertRaises(ValueError):self.run_app()
  self.assertEqual((self.game/self.rows[0]['path']).read_bytes(),self.old)
 def test_corrupt_payload_no_writes(self):
  (self.root/'game.bin').write_bytes(b'corrupt')
  with self.assertRaises(ValueError):self.run_app()
  self.assertEqual((self.game/self.rows[0]['path']).read_bytes(),self.old)
 def test_missing_update_no_writes(self):
  (self.update/self.rows[1]['path']).unlink()
  with self.assertRaises(ValueError):self.run_app()
  self.assertEqual((self.game/self.rows[0]['path']).read_bytes(),self.old)
 def test_restore_refuses_changed_backup(self):
  self.run_app();j=json.loads((self.game/'.suiten-cn-install.json').read_text());Path(j['files'][0]['backup']).write_bytes(b'bad')
  with self.assertRaises(ValueError):self.run_app('--restore')
  self.assertEqual((self.game/self.rows[0]['path']).read_bytes(),self.new)
 def test_commit_failure_rolls_back(self):
  original=app.os.replace
  def fail(src,dst):
   if str(src).endswith('.partial') and Path(dst).name=='patch0100_arb.sdat':raise OSError('simulated rename failure')
   return original(src,dst)
  with patch.object(app.os,'replace',side_effect=fail),self.assertRaises(OSError):self.run_app()
  self.assertEqual((self.game/self.rows[0]['path']).read_bytes(),self.old);self.assertEqual((self.update/self.rows[1]['path']).read_bytes(),self.old)
 def test_rebuild_rejects_truncated_source(self):
  with self.assertRaises(ValueError):app.rebuild(self.root/'game.bin',self.root/'game.bin',[dict(type='copy',offset=100,size=5)],self.root/'test.out',5,'invalid')
if __name__=='__main__':unittest.main()
