"""Hash-pinned streaming patches. No network; Python standard library."""
import gzip, hashlib, json, os, shutil
from pathlib import Path

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()

def save(p,value):
 p=Path(p);tmp=p.with_suffix('.tmp')
 with tmp.open('w',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
 os.replace(tmp,p)

def safe(root,name):
 root=Path(root).resolve();p=(root/name).resolve()
 if root not in p.parents:raise ValueError('路径越界')
 return p

def select(src,item):
 h=sha(src)
 if h==item['after']:return None
 if h not in item['variants']:raise ValueError('版本不匹配，未写入：'+str(src)+' SHA256='+h)
 return item['variants'][h]

def reconstruct(src,dst,item,recipe,root):
 blob=safe(root,recipe['blob'])
 if sha(blob)!=recipe['blob_sha256']:raise ValueError('补丁文件损坏')
 try:
  with Path(src).open('rb') as old,gzip.open(blob,'rb') as payload,Path(dst).open('xb') as out:
   for kind,offset,length in recipe['segments']:
    stream=old if kind=='copy' else payload
    if kind=='copy':stream.seek(offset)
    elif kind!='add':raise ValueError('非法差分指令')
    left=length
    while left:
     b=stream.read(min(left,8*1024*1024))
     if not b:raise ValueError('补丁数据截断')
     out.write(b);left-=len(b)
   out.flush();os.fsync(out.fileno())
  if Path(dst).stat().st_size!=item['size'] or sha(dst)!=item['after']:raise ValueError('生成文件校验失败')
 except BaseException:
  Path(dst).unlink(missing_ok=True);raise

def iso(src,out,item,root,check=False):
 src=Path(src).resolve();out=Path(out).resolve();recipe=select(src,item)
 if recipe is None:return '输入已经是最新版，无需生成'
 if out.exists() or out==src:raise ValueError('输出已经存在，请另选文件名；不会覆盖原ISO')
 if check:return '基线匹配，可以生成新ISO'
 if shutil.disk_usage(out.parent).free<item['size']+64*1024*1024:raise ValueError('空间不足')
 tmp=out.with_name(out.name+'.partial')
 if tmp.exists():raise ValueError('存在未完成的.partial，请先核查并另选输出名')
 reconstruct(src,tmp,item,recipe,root)
 # Link is atomic and refuses an output created concurrently. Never overwrite.
 try:os.link(tmp,out)
 finally:tmp.unlink(missing_ok=True)
 return '新版ISO已生成，原ISO保留：'+str(out)

def restore(journal):
 journal=Path(journal);data=json.loads(journal.read_text(encoding="utf-8"))
 if data.get('status')=='restored':return '已经恢复'
 for e in data['entries']:
  p=Path(e['path']);backup=Path(e['backup'])
  if backup.exists():
   if sha(backup)!=e['before']:raise ValueError('备份校验失败')
   if p.exists() and sha(p) not in (e['before'],e['after']):raise ValueError('目标后来被修改，停止恢复：'+str(p))
  elif not p.exists() or sha(p)!=e['before']:raise ValueError('原文件/备份缺失，停止恢复')
 for e in reversed(data['entries']):
  p=Path(e['path']);backup=Path(e['backup']);tmp=Path(e['temp'])
  if backup.exists():os.replace(backup,p)
  tmp.unlink(missing_ok=True)
 data['status']='restored';save(journal,data)
 return '已恢复升级前资源'

def update(targets,root,journal,check=False):
 journal=Path(journal)
 if journal.exists():
  state=json.loads(journal.read_text(encoding="utf-8"))
  if state['status'] not in ('complete','restored'):raise ValueError('发现未完成事务，先执行恢复')
  if state['status']=='complete':
   if all(Path(e['path']).exists() and sha(e['path'])==e['after'] for e in state['entries']):return '本次升级已完成'
   raise ValueError('已安装资源之后发生变化，请先核对或恢复')
 plans=[]
 for src,item in targets:
  src=Path(src).resolve();recipe=select(src,item)
  if recipe is not None:plans.append((src,item,recipe))
 if not plans:return '全部目标已是最新版'
 if len(plans)!=len(targets):raise ValueError('发现新旧混合版本，未写入；请先恢复未完成升级')
 if check:return '全部基线匹配，可以升级'
 needs={}
 for src,item,recipe in plans:
  dev=src.stat().st_dev;needs.setdefault(dev,[src.parent,0])[1]+=item['size']
 for parent,size in needs.values():
  if shutil.disk_usage(parent).free<size+64*1024*1024:raise ValueError('空间不足：'+str(parent))
 entries=[]
 for i,(src,item,recipe) in enumerate(plans):
  tmp=src.with_name(src.name+'.cn-20261001.partial');bak=src.with_name(src.name+'.before-cn-20261001')
  if tmp.exists() or bak.exists():raise ValueError('临时文件或备份已存在，先核查：'+str(src))
  entries.append(dict(path=str(src),backup=str(bak),temp=str(tmp),before=sha(src),after=item['after']))
 state=dict(status='preparing',entries=entries);save(journal,state)
 try:
  for e,(src,item,recipe) in zip(entries,plans):reconstruct(src,e['temp'],item,recipe,root)
  for e in entries:
   if sha(e['path'])!=e['before']:raise ValueError('构建期间原文件发生变化')
  state['status']='committing';save(journal,state)
  for e in entries:
   os.rename(e['path'],e['backup']);os.rename(e['temp'],e['path'])
  state['status']='complete';save(journal,state)
 except BaseException:
  restore(journal);raise
 return '升级完成；原资源保留为.before-cn-20261001，可执行恢复'
