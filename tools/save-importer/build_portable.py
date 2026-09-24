"""Reproducible portable directory/ZIP builder; verifies pinned upstream runtime."""
from pathlib import Path, PurePosixPath
import argparse,hashlib,json,os,posixpath,shutil,tarfile,zipfile,subprocess
HERE=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def build(platform,downloads,out):
 metadata=json.loads((HERE/'runtimes.json').read_text())[platform]
 downloads.mkdir(parents=True,exist_ok=True);out.mkdir(parents=True,exist_ok=True)
 archive=downloads/metadata['name']
 if not archive.exists():
  subprocess.run(['curl','--fail','--location','--retry','3','--output',str(archive),metadata['browser_download_url']],check=True)
 if 'sha256:'+sha(archive)!=metadata['digest']:raise RuntimeError('Python runtime SHA-256 mismatch')
 stage=out/('SuitenSaveImporter-0.2.0-'+platform)
 if stage.exists():raise RuntimeError('Output exists; use a new output directory: '+str(stage))
 stage.mkdir()
 for name in ('importer.py','launch.py','catalog.json','runtime_check.py','test_importer.py','详细使用说明.md','第三方运行时说明.md','LICENSE'):
  shutil.copy2(HERE/name,stage/name)
 shutil.copytree(HERE/'saves',stage/'saves')
 shutil.copytree(HERE/'third-party-licenses',stage/'third-party-licenses')
 extracted=out/('extract-'+platform)
 extracted.mkdir()
 try:
  with tarfile.open(archive) as tar:
   for member in tar.getmembers():
    parts=PurePosixPath(member.name).parts
    if not parts or parts[0]!='python' or '..' in parts or member.name.startswith('/') or member.isdev() or member.isfifo():raise RuntimeError('Unsafe archive member')
    if member.issym():
     target=posixpath.normpath(posixpath.join(posixpath.dirname(member.name),member.linkname))
     if member.linkname.startswith('/') or not target.startswith('python/'):raise RuntimeError('Unsafe archive link')
    elif member.islnk() and not member.linkname.startswith('python/'):raise RuntimeError('Unsafe hardlink')
   if hasattr(tarfile,'data_filter'):tar.extractall(extracted,filter='data')
   else:tar.extractall(extracted)
  shutil.copytree(extracted/'python',stage/'runtime',symlinks=False)
 finally:shutil.rmtree(extracted)
 (stage/'runtime-source.json').write_text(json.dumps(metadata,indent=2)+'\n')
 if platform=='Windows-x64':
  launcher='''@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
"%~dp0runtime\\python.exe" -I -B "%~dp0launch.py" %*
if errorlevel 1 pause
'''
  (stage/'启动存档导入器.bat').write_bytes(launcher.replace('\n','\r\n').encode('utf-8'))
 else:
  launcher='''#!/bin/bash
cd -- "$(dirname -- "$0")" || exit 1
./runtime/bin/python3 -I -B ./launch.py "$@"
result=$?
if [ "$result" -ne 0 ]; then
  printf '%s\\n' '启动失败，请查阅详细使用说明中的启动问题。'
  read -r -p '按回车关闭。'
fi
exit "$result"
'''
  path=stage/'启动存档导入器.command';path.write_text(launcher);path.chmod(0o755)
 return stage

def pack(stage):
 # Do not ship local bytecode caches or reports with machine paths.
 for p in list(stage.rglob('__pycache__')):shutil.rmtree(p)
 sums=''.join(sha(p)+'  '+p.relative_to(stage).as_posix()+'\n' for p in sorted(stage.rglob('*')) if p.is_file() and p.name!='SHA256SUMS.txt')
 (stage/'SHA256SUMS.txt').write_text(sums,encoding='utf-8')
 dest=stage.parent/(stage.name+'.zip')
 with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for p in sorted(stage.rglob('*')):
   if p.is_file():z.write(p,stage.name+'/'+p.relative_to(stage).as_posix())
 with zipfile.ZipFile(dest) as z:
  assert z.testzip() is None
  for line in sums.splitlines():
   h,name=line.split('  ',1);assert hashlib.sha256(z.read(stage.name+'/'+name)).hexdigest()==h
 print(json.dumps({'file':dest.name,'bytes':dest.stat().st_size,'sha256':sha(dest)}))
 return dest

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--platform',choices=list(json.loads((HERE/'runtimes.json').read_text())));p.add_argument('--downloads',type=Path,default=Path('runtime-downloads'));p.add_argument('--out',type=Path,default=Path('portable'));p.add_argument('--pack',type=Path)
 a=p.parse_args()
 if a.pack:pack(a.pack)
 elif a.platform:print(build(a.platform,a.downloads,a.out))
 else:p.error('Need --platform or --pack')
