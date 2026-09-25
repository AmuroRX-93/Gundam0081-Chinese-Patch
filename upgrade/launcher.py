#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys

def ask(prompt):
    return input(prompt).strip().strip('"').strip("'")

def main():
    print('水天之泪汉化升级包 2026.09.25 · 仅适用 20260917_r1 汉化 + 官方 1.02')
    print('请保存进度、完全退出 RPCS3。请先阅读包内“使用说明.md”。')
    print('1 安装升级  /  2 只检查  /  3 恢复本次升级  /  其他 退出')
    mode=ask('选择：')
    if mode not in ('1','2','3'): return
    game=ask('游戏目录（直接包含 PS3_GAME，不是 ISO 文件）：')
    args=[sys.executable,str(Path(__file__).with_name('install_upgrade.py')),'--game',game]
    if mode=='3': args+=['--restore']
    else:
        default=Path.home()/'Library/Application Support/rpcs3' if sys.platform=='darwin' else Path.home()/'.config/rpcs3'
        print('RPCS3 数据目录是直接包含 dev_hdd0 的目录。Windows 通常在 RPCS3 文件夹。')
        if default.is_dir() and sys.platform!='win32':
            data=ask('RPCS3 数据目录（留空使用 '+str(default)+'）：') or str(default)
        else: data=ask('RPCS3 数据目录：')
        args+=['--rpcs3',data]
        if mode=='2':args+=['--check']
    result=subprocess.run(args)
    print('操作结束。' if result.returncode==0 else '操作未完成，请阅读上方原因；不要删除备份。')

if __name__=='__main__':
    try: main()
    except KeyboardInterrupt: print('\n已取消。')
    except Exception as exc: print('未完成：'+str(exc))
    try: input('按回车关闭…')
    except (EOFError,KeyboardInterrupt): pass
