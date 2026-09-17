#!/usr/bin/env python3
from pathlib import Path
import subprocess,sys

def main():
 print('水天之泪 BLJS10050 汉化补丁：安装 / 恢复')
 print('请先完整解压三个 ZIP 到同一目录，并退出游戏和模拟器。')
 action=input('输入 1 安装，输入 2 恢复，其他输入取消：').strip()
 if action not in ('1','2'):return 0
 raw=input('包含 PS3_GAME 的游戏目录（可拖入窗口）：').strip().strip('"').strip("'")
 if not raw:return 0
 # macOS Terminal may escape spaces in a dragged path.
 game=Path(raw).expanduser()
 if not game.exists():game=Path(raw.replace('\\ ', ' ')).expanduser()
 cmd=[sys.executable,str(Path(__file__).with_name('install_patch.py')),'--game',str(game)]
 if action=='2':cmd.append('--restore')
 else:
  raw=input('RPCS3 数据目录（包含 dev_hdd0；只安装光盘汉化可留空）：').strip().strip('"').strip("'")
  if raw:
   path=Path(raw).expanduser()
   if not path.exists():path=Path(raw.replace('\\ ',' ')).expanduser()
   cmd+=['--rpcs3',str(path)]
 return subprocess.call(cmd)

if __name__=='__main__':
 try:result=main()
 except (KeyboardInterrupt,EOFError):result=1
 input('按回车关闭窗口……');sys.exit(result)
