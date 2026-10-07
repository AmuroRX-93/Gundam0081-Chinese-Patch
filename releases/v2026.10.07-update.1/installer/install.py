import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import argparse,json,traceback,datetime
from engine import iso,update,restore

def ask(label):return Path(input(label).strip().strip('"').strip("'"))
def main():
 m=json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))
 if m.get('release')!='v2026.10.01-candidate.1' or m.get('kind')!='tree':raise ValueError('此小修复仅适用于水天之泪 20261001 Candidate 累计包，请核对原包文件名。')
 p=argparse.ArgumentParser(description=m['title'])
 p.add_argument('--input',type=Path);p.add_argument('--output',type=Path);p.add_argument('--game',type=Path);p.add_argument('--update-dir',type=Path);p.add_argument('--check',action='store_true');p.add_argument('--restore',action='store_true');args=p.parse_args()
 if m['kind']=='iso':
  if args.restore:raise ValueError('回退只需重新打开旧ISO，工具从不覆盖输入ISO')
  src=args.input or ask('将旧版ISO拖入这里（或输入路径），回车：')
  out=args.output or src.with_name(src.stem+'_20260928修订.iso')
  print(iso(src,out,m['items'][0],ROOT,args.check))
 else:
  print('操作前请彻底退出游戏和模拟器。请选择目录式本体；ISO需先提取。')
  game=(args.game or ask('游戏根目录（直接包含PS3_GAME）：')).resolve()
  journal=game/'.cn-upgrade-20261001.json'
  if args.restore:print(restore(journal));return
  upd=(args.update_dir or ask('1.02更新目录（直接包含PARAM.SFO与USRDIR的BLJS10050目录）：')).resolve()
  # Read PARAM.SFO to refuse wrong game/update before planning writes.
  import struct
  def sfo(path):
   b=path.read_bytes()
   if b[:4]!=b'\0PSF':raise ValueError('PARAM.SFO无效')
   k,v,n=struct.unpack_from('<III',b,8);r={}
   for i in range(n):
    ki,_,sz,_,vi=struct.unpack_from('<HHIII',b,20+i*16);key=b[k+ki:b.index(0,k+ki)].decode();r[key]=b[v+vi:v+vi+sz].rstrip(b'\0').decode('utf8','replace')
   return r
  if sfo(game/'PS3_GAME/PARAM.SFO').get('TITLE_ID')!='BLJS10050':raise ValueError('本体编号不是BLJS10050')
  info=sfo(upd/'PARAM.SFO')
  if info.get('TITLE_ID')!='BLJS10050' or info.get('APP_VER')!='01.02':raise ValueError('需要BLJS10050官方1.02更新')
  targets=[(game/'PS3_GAME/USRDIR/game.arb',m['items'][0])]+[(upd/i['path'],i) for i in m['items'][1:]]
  cache=upd/'USRDIR/cache/game.arb'
  if cache.exists():targets.append((cache,m['items'][0]))
  if len({x.resolve() for x,_ in targets})!=len(targets):raise ValueError('文件路径重复')
  print(update(targets,ROOT,journal,args.check))
if __name__=='__main__':
 try:main()
 except Exception as e:
  print('操作失败：',e)
  try:
   with (ROOT/'安装日志.txt').open('a',encoding='utf8') as f:f.write('\n'+str(datetime.datetime.now())+'\n'+traceback.format_exc())
  except OSError:pass
  sys.exit(1)
