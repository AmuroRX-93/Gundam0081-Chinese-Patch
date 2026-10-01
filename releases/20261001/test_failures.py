import tempfile,sys,gzip,json,hashlib
from pathlib import Path
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parent));import engine
out=[]
with tempfile.TemporaryDirectory() as d:
 r=Path(d);b=r/'payload.gz'
 with gzip.open(b,'wb') as f:f.write(b'new content')
 before=hashlib.sha256(b'old content').hexdigest();after=hashlib.sha256(b'new content').hexdigest()
 item=dict(size=11,after=after,variants={before:dict(blob='payload.gz',blob_sha256=engine.sha(b),segments=[['add',0,11]])})
 paths=[r/'one',r/'two'];[p.write_bytes(b'old content') for p in paths];targets=[(p,item) for p in paths];j=r/'journal.json'
 real=engine.os.rename;count=[0]
 def fail(a,b):
  count[0]+=1
  if count[0]==3:raise OSError('simulated second-file commit failure')
  return real(a,b)
 with mock.patch.object(engine.os,'rename',side_effect=fail):
  try:engine.update(targets,r,j);raise AssertionError('failure not triggered')
  except OSError:pass
 assert all(p.read_bytes()==b'old content' for p in paths);out.append('second_file_commit_failure_restores_all')
 # Simulate process exit after first target was renamed away.
 state=json.loads(j.read_text());state['status']='committing';engine.save(j,state)
 p=paths[0];p.rename(state['entries'][0]['backup']);Path(state['entries'][0]['temp']).write_bytes(b'new content')
 engine.restore(j);assert all(p.read_bytes()==b'old content' for p in paths);out.append('interrupted_commit_journal_recovery')
 engine.update(targets,r,j);paths[0].write_bytes(b'later user edit')
 try:engine.restore(j);raise AssertionError('must refuse later edit')
 except ValueError:pass
 assert paths[0].read_bytes()==b'later user edit';out.append('restore_refuses_later_modifications')
 # Fresh journal for preflight and corruption failures.
 r2=r/'next';r2.mkdir();p=r2/'one';p.write_bytes(b'old content')
 with mock.patch.object(engine.shutil,'disk_usage',return_value=type('Space',(),{'free':0})()):
  try:engine.update([(p,item)],r,r2/'journal.json');raise AssertionError('must fail')
  except ValueError:pass
 assert not (r2/'journal.json').exists();out.append('insufficient_space_before_write')
 b.write_bytes(b'corrupted')
 try:engine.iso(p,r2/'result',item,r);raise AssertionError('must fail')
 except ValueError:pass
 assert p.read_bytes()==b'old content' and not (r2/'result.partial').exists();out.append('corrupted_payload_no_output_or_source_change')
Path(__file__).with_name('failure-test-results.json').write_text(json.dumps(out,indent=2));print(out)
