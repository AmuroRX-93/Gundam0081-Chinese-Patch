"""Synthetic, asset-free transaction tests; python3 upgrade/test_upgrade.py."""
import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import install_upgrade as u


def sfo_bytes(values):
    keys=bytearray();data=bytearray();entries=bytearray()
    for k,v in values.items():
        b=v.encode()+b'\0';entries.extend(struct.pack('<HHIII',len(keys),0x204,len(b),len(b),len(data)))
        keys.extend(k.encode()+b'\0');data.extend(b)
    return b'\0PSF'+struct.pack('<IIII',0x101,20+len(entries),20+len(entries)+len(keys),len(values))+entries+keys+data


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.g=self.root/'中文 game';self.d=self.root/'data'
        self.update=self.d/'dev_hdd0/game/BLJS10050'
        self.arb=self.g/'PS3_GAME/USRDIR/game.arb';self.arb.parent.mkdir(parents=True)
        (self.g/'PS3_GAME/PARAM.SFO').write_bytes(sfo_bytes(dict(TITLE_ID='BLJS10050')))
        self.update.mkdir(parents=True);(self.update/'PARAM.SFO').write_bytes(sfo_bytes(dict(TITLE_ID='BLJS10050',APP_VER='01.02')))
        self.name='game/language/test.xmb'
        h=bytearray(2048);h[:6]=b'BfPk\xfe\xff';struct.pack_into('>HH',h,6,1,1)
        rec=17+len(self.name);struct.pack_into('>IIIHH',h,16,0,3,0,rec,len(self.name));h[33:33+len(self.name)]=self.name.encode()
        self.original=bytes(h)+b'old'+bytes(13)+b'KEEP LOWFX'
        self.arb.write_bytes(self.original)
        self.file=self.update/'USRDIR/patch/a.sdat';self.file.parent.mkdir(parents=True);self.file.write_bytes(b'old update')
        self.man=dict(release=u.VERSION,title_id='BLJS10050',members=[self.item(self.name,b'old',b'new!',0)],files=[self.item('USRDIR/patch/a.sdat',b'old update',b'new update+',1)])
    def item(self,path,a,b,i):
        blob=str(i)+'.bin';(self.root/blob).write_bytes(b)
        return dict(path=path,before=u.digest(a),after=u.digest(b),old_size=len(a),new_size=len(b),blob=blob,blob_sha256=u.digest(b),segments=[['add',0,len(b)]])
    def plan(self): return u.plan(self.g,self.d,self.man,self.root)
    def install(self): return u.install(self.g,self.plan())
    def assert_restored(self):
        self.assertEqual(self.arb.read_bytes(),self.original);self.assertEqual(self.file.read_bytes(),b'old update')
    def test_roundtrip_repeat_cache_lowfx(self):
        cache=self.update/'USRDIR/cache/game.arb';cache.parent.mkdir();cache.write_bytes(self.original)
        self.install();self.assertEqual(self.plan(),[]);self.assertTrue(self.arb.read_bytes().endswith(b'KEEP LOWFX'))
        u.restore(self.g);self.assert_restored();self.assertEqual(cache.read_bytes(),self.original)
    def test_unknown_no_writes(self):
        self.file.write_bytes(b'unknown')
        with self.assertRaises(ValueError):self.plan()
        self.assertEqual(self.arb.read_bytes(),self.original);self.assertFalse((self.g/u.JOURNAL).exists())
    def test_missing_payload_no_writes(self):
        (self.root/'1.bin').unlink()
        with self.assertRaises(FileNotFoundError):self.plan()
        self.assert_restored()
    def test_corrupt_payload(self):
        (self.root/'0.bin').write_bytes(b'bad')
        with self.assertRaises(ValueError):self.plan()
    def test_mixed_versions(self):
        self.file.write_bytes(b'new update+')
        with self.assertRaisesRegex(ValueError,'混合'):self.plan()
    def test_wrong_title_and_update(self):
        (self.update/'PARAM.SFO').write_bytes(sfo_bytes(dict(TITLE_ID='BLJS10050',APP_VER='01.01')))
        with self.assertRaises(ValueError):self.plan()
    def test_read_only(self):
        self.arb.chmod(0o444)
        try:
            with self.assertRaises(PermissionError):self.install()
        finally:self.arb.chmod(0o644)
        self.assert_restored()
    def test_space(self):
        with patch.object(u.shutil,'disk_usage',return_value=type('D',(),{'free':0})()):
            with self.assertRaises(ValueError):self.install()
        self.assert_restored()
    def test_interrupted_partial_write_restore(self):
        real=u.write_op;count=[0]
        def fail(op,value):
            count[0]+=1
            if count[0]==3:
                with Path(op['path']).open('r+b') as f:f.write(value[:4])
                raise OSError('simulated power loss')
            real(op,value)
        with patch.object(u,'write_op',side_effect=fail):
            with self.assertRaises(OSError):self.install()
        u.restore(self.g);self.assert_restored()
    def test_interrupted_partial_append_restore(self):
        self.man['files'][0]=self.item('USRDIR/patch/a.sdat',b'old update',b'new update plus append',1)
        real=u.write_op
        def fail(op,value):
            if op['whole']:
                with Path(op['path']).open('r+b') as f:f.write(value[:15])
                raise OSError('partial extension')
            real(op,value)
        with patch.object(u,'write_op',side_effect=fail):
            with self.assertRaises(OSError):self.install()
        u.restore(self.g);self.assert_restored()
    def test_restore_refuses_later_edits(self):
        self.install();self.file.write_bytes(b'new player changes')
        before=self.arb.read_bytes()
        with self.assertRaises(ValueError):u.restore(self.g)
        self.assertEqual(before,self.arb.read_bytes())
    def test_restore_checks_backups(self):
        self.install();(self.g/u.JOURNAL/'0000-before.bin').write_bytes(b'bad')
        with self.assertRaises(ValueError):u.restore(self.g)
        self.assertEqual(self.plan(),[])
    def test_manifest_escape(self):
        self.man['members'][0]['blob']='../escape'
        with self.assertRaises(ValueError):self.plan()
    def test_missing_update_and_optional_cache(self):
        self.assertTrue(self.plan());self.file.unlink()
        with self.assertRaises(FileNotFoundError):self.plan()
    def test_preparation_failure(self):
        with patch.object(u,'write_sync',side_effect=OSError('disk failed')):
            with self.assertRaises(OSError):self.install()
        self.assertFalse((self.g/u.JOURNAL).exists());self.assert_restored()
    def test_restore_interrupt(self):
        self.install();real=u.write_op;count=[0]
        def fail(op,value):
            count[0]+=1
            if count[0]==2:
                with Path(op['path']).open('r+b') as f:f.seek(op['offset']);f.write(value[:2])
                raise OSError('interrupt restore')
            real(op,value)
        with patch.object(u,'write_op',side_effect=fail):
            with self.assertRaises(OSError):u.restore(self.g)
        u.restore(self.g);self.assert_restored()

if __name__=='__main__':unittest.main()
