from pathlib import Path
import datetime,runpy,sys,traceback
PACKAGE=Path(__file__).resolve().parent
class Tee:
 def __init__(self,terminal,log):self.terminal,self.log=terminal,log
 def write(self,s):self.log.write(s);self.terminal.write(s);self.flush();return len(s)
 def flush(self):self.log.flush();self.terminal.flush()
 def __getattr__(self,k):return getattr(self.terminal,k)
def main():
 logs=PACKAGE/'logs'
 try:
  logs.mkdir(exist_ok=True)
  stream=(logs/(datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.log')).open('x',encoding='utf-8')
 except OSError as ex:print('无法创建日志，请完整解压到可写目录：',ex);return 1
 out,err=sys.stdout,sys.stderr;status=0
 with stream:
  sys.stdout,sys.stderr=Tee(out,stream),Tee(err,stream)
  try:
   print('水天之泪 20261001 安装器编码修复 20261007；日志：',stream.name,flush=True)
   for n in ('install.py','engine.py','manifest.json'):
    if not (PACKAGE/n).is_file():raise FileNotFoundError('安装包缺少 '+n+'，请完整解压原包，再覆盖本小修复。')
   sys.path.insert(0,str(PACKAGE))
   runpy.run_path(str(PACKAGE/'install.py'),run_name='__main__')
  except SystemExit as ex:status=ex.code if isinstance(ex.code,int) else (1 if ex.code else 0)
  except (KeyboardInterrupt,EOFError):print('已取消。');status=1
  except Exception:traceback.print_exc();status=1
  finally:
   print('退出码：',status)
   sys.stdout,sys.stderr=out,err
 return status
if __name__=='__main__':raise SystemExit(main())
