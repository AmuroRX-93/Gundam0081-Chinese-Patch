#!/usr/bin/env python3
"""BLJS10050 Chinese patch installer; Python standard library only."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,time,sys
CHUNK=4*1024*1024
ROOT=Path(__file__).resolve().parent
if not (ROOT/'manifest.json').exists():ROOT=ROOT.parent

def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(CHUNK),b''):h.update(b)
 return h.hexdigest()

def rebuild(source,payload,segments,destination,expected_size,expected_hash):
 h=hashlib.sha256();total=0
 with source.open('rb') as src,payload.open('rb') as add,destination.open('xb') as out:
  for seg in segments:
   if seg['type'] not in ('copy','add'):raise ValueError('Unknown segment type')
   f=src if seg['type']=='copy' else add;left=seg['size'];offset=seg['offset']
   if left<0 or offset<0:raise ValueError('Invalid segment')
   f.seek(offset)
   while left:
    b=f.read(min(CHUNK,left))
    if not b:raise ValueError('Source or payload truncated')
    out.write(b);h.update(b);left-=len(b);total+=len(b)
  out.flush();os.fsync(out.fileno())
 if total!=expected_size or h.hexdigest()!=expected_hash:raise ValueError('Rebuilt file verification failed')

def safe_path(root,name):
 p=Path(name)
 if p.is_absolute() or '..' in p.parts:raise ValueError('Unsafe relative path')
 target=root/p
 if not target.resolve().is_relative_to(root.resolve()):raise ValueError('Path leaves chosen root')
 return target

def restore(game):
 journal=game/'.suiten-cn-install.json'
 if not journal.is_file():raise ValueError('未找到本安装器的恢复记录；不要自动恢复其他工具制作的备份。')
 data=json.loads(journal.read_text(encoding='utf-8'))
 if data.get('status')!='installed':raise ValueError('此安装记录已经恢复，或未完成安装。')
 entries=data['files']
 for row in entries:
  target=Path(row['target']);backup=Path(row['backup'])
  if not target.is_file() or not backup.is_file():raise ValueError('恢复文件缺失：'+str(target))
  if sha(target)!=row['after'] or sha(backup)!=row['before']:raise ValueError('恢复校验不匹配，未覆盖：'+str(target))
 done=[]
 try:
  for row in entries:
   target=Path(row['target']);backup=Path(row['backup']);hold=target.with_name(target.name+'.after-cn-'+data['stamp'])
   if hold.exists():raise ValueError('恢复保留文件已存在：'+str(hold))
   os.replace(target,hold)
   try:os.replace(backup,target)
   except BaseException:os.replace(hold,target);raise
   done.append((target,backup,hold))
  data['status']='restored';temp=journal.with_suffix('.json.tmp');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(temp,journal)
 except BaseException:
  for target,backup,hold in reversed(done):os.replace(target,backup);os.replace(hold,target)
  raise
 print('已恢复安装前的文件；汉化文件保留在 .after-cn-时间戳 文件中。存档未改动。')

def main():
 ap=argparse.ArgumentParser(description='请先退出游戏和模拟器，再应用 BLJS10050 汉化差分。');ap.add_argument('--game',required=True,type=Path);ap.add_argument('--rpcs3',type=Path);ap.add_argument('--restore',action='store_true');args=ap.parse_args()
 game=args.game.resolve()
 if not (game/'PS3_GAME/PARAM.SFO').is_file():raise ValueError('--game 应指向含 PS3_GAME 的游戏目录')
 if args.restore:return restore(game)
 update=args.rpcs3.resolve()/'dev_hdd0/game/BLJS10050' if args.rpcs3 else None
 m=json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))
 if m.get('format')!=1 or m.get('title_id')!='BLJS10050':raise ValueError('Wrong manifest')
 jobs=[];target_game=None;needs={};skipped=0
 for row in m['patches']:
  if row['scope']=='game':root=game
  elif row['scope']=='update':
   if update is None:continue
   root=update
  else:raise ValueError('Unknown scope')
  dest=safe_path(root,row['path']);payload=safe_path(ROOT,row['blob'])
  if not dest.is_file():raise ValueError('缺少原始文件，请先准备匹配原版/官方 1.02 升级：'+str(dest))
  digest=sha(dest)
  if row['scope']=='game' and row['path']=='PS3_GAME/USRDIR/game.arb':target_game=row
  if digest==row['target_sha256']:print('已是本版：',row['path']);skipped+=1;continue
  if digest!=row['source_sha256'] or dest.stat().st_size!=row['source_bytes']:raise ValueError('原始版本校验不匹配，未覆盖：'+str(dest))
  if sha(payload)!=row['blob_sha256']:raise ValueError('差分包损坏：'+row['blob'])
  jobs.append((row,dest,payload));dev=dest.stat().st_dev;needs.setdefault(dev,[dest,0])[1]+=row['target_bytes']
 cache=update/'USRDIR/cache/game.arb' if update else None
 cache_needed=bool(cache and cache.exists() and target_game and sha(cache)!=target_game['target_sha256'])
 if cache_needed:
  dev=cache.stat().st_dev;needs.setdefault(dev,[cache,0])[1]+=target_game['target_bytes']
 for p,n in needs.values():
  if shutil.disk_usage(p.parent).free<n+128*1024*1024:raise ValueError('空间不足：'+str(p.parent)+' 需要额外约 '+str(round(n/1024**3,2))+' GiB')
 if not jobs and not cache_needed:print('所选文件已是本版本，无需再次安装。');return
 journal=game/'.suiten-cn-install.json'
 if journal.exists() and json.loads(journal.read_text(encoding='utf-8')).get('status')=='installed':raise ValueError('已有安装恢复记录，请先恢复后再安装不同配置。')
 before={str(dest):sha(dest) for _,dest,_ in jobs}
 if cache_needed:before[str(cache)]=sha(cache)
 stamp=time.strftime('%Y%m%d-%H%M%S');prepared=[];committed=[]
 try:
  for row,dest,payload in jobs:
   temp=dest.with_name(dest.name+'.cn-'+stamp+'.partial');print('重建并校验：',row['path'],flush=True)
   try:rebuild(dest,payload,row['segments'],temp,row['target_bytes'],row['target_sha256'])
   except BaseException:
    if temp.exists():temp.unlink()
    raise
   prepared.append((dest,temp))
  if cache_needed:
   disc=game/'PS3_GAME/USRDIR/game.arb';src=next((t for d,t in prepared if d==disc),disc);temp=cache.with_name(cache.name+'.cn-'+stamp+'.partial')
   shutil.copyfile(src,temp)
   if sha(temp)!=target_game['target_sha256']:temp.unlink();raise ValueError('缓存校验失败')
   prepared.append((cache,temp))
  # Only verified candidates are committed; rollback if any replace fails.
  for dest,temp in prepared:
   backup=dest.with_name(dest.name+'.before-cn-'+stamp)
   if backup.exists():raise ValueError('备份已存在：'+str(backup))
   os.replace(dest,backup)
   try:os.replace(temp,dest)
   except BaseException:os.replace(backup,dest);raise
   committed.append((dest,backup))
  data={'format':1,'status':'installed','stamp':stamp,'release':m['release'],'files':[{'target':str(dest),'backup':str(backup),'before':before[str(dest)],'after':sha(dest)} for dest,backup in committed]}
  tempjournal=journal.with_suffix('.json.tmp');tempjournal.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(tempjournal,journal)
 except BaseException:
  for dest,backup in reversed(committed):os.replace(dest,dest.with_name(dest.name+'.failed-cn-'+stamp));os.replace(backup,dest)
  for _,temp in prepared:
   if temp.exists():temp.unlink()
  raise
 (game/'PS3_GAME/USRDIR/patch').mkdir(exist_ok=True)
 if update:(update/'USRDIR/cache').mkdir(parents=True,exist_ok=True)
 print('完成。已校验安装；旧文件保存在各目录的 .before-cn-'+stamp+' 文件中。')
 if update is None:print('未指定 --rpcs3；升级目录及已有缓存未处理，请参照使用说明。')

if __name__=='__main__':
 try:main()
 except Exception as e:print('安装停止：',e,file=sys.stderr);sys.exit(1)
