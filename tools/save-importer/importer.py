#!/usr/bin/env python3
"""RPCS3 BLJS10050 save importer. Python 3.10+, standard library only."""
from pathlib import Path
import argparse
import contextlib
import csv
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid

HERE = Path(__file__).resolve().parent
PREFIX = 'BLJS10050-FREEMISSIONDAT2-'
NAMES = {PREFIX + n for n in ('E00', 'E01', 'Z00', 'Z01')}

class ImportErrorSafe(Exception):
    pass

def fail(message):
    raise ImportErrorSafe(message)

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def no_links(path):
    for p in (path, *path.parents):
        if p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()):
            fail('不支持符号链接或目录联接，请选择实际目录：' + str(p))
        if os.name == 'nt' and p.exists():
            # Also catches Windows junctions on Python 3.10/3.11.
            if getattr(p.stat(follow_symlinks=False), 'st_file_attributes', 0) & 0x400:
                fail('不支持 Windows 重解析目录：' + str(p))

def snapshot(folder):
    no_links(folder)
    if not folder.exists():
        return None
    if not folder.is_dir():
        fail('目标不是文件夹：' + str(folder))
    result = {}
    for p in sorted(folder.rglob('*')):
        no_links(p)
        if p.is_file():
            result[p.relative_to(folder).as_posix()] = digest(p)
        elif not p.is_dir():
            fail('存档中存在特殊文件：' + str(p))
    return result

def read_catalog():
    data = json.loads((HERE/'catalog.json').read_text('utf-8'))
    for row in data['saves']:
        if row['directory'] not in NAMES or not re.fullmatch(r'[ez]-(online|all)', row['id']):
            fail('存档目录清单无效。')
        if snapshot(HERE/'saves'/row['id']) != row['hashes']:
            fail('随包存档校验失败，请重新完整解压：' + row['title'])
    return data['saves']

def ensure_closed():
    try:
        if os.name == 'nt':
            text = subprocess.check_output(['tasklist', '/FO', 'CSV', '/NH'], timeout=15).decode(errors='replace')
            names = [row[0].lower() for row in csv.reader(text.splitlines()) if row]
            running = any(name.startswith('rpcs3') and name.endswith('.exe') for name in names)
        else:
            text = subprocess.check_output(['ps', '-axo', 'comm='], timeout=15).decode(errors='replace')
            running = any(Path(line.strip()).name.lower().startswith('rpcs3') for line in text.splitlines())
    except (OSError, subprocess.SubprocessError) as e:
        fail('无法检查 RPCS3 是否已退出，未写入：' + str(e))
    if running:
        fail('请先完全退出 RPCS3，再导入或恢复存档。')

def targets(selected):
    p = Path(selected).expanduser().absolute()
    no_links(p)
    if p.is_file():
        if p.name.lower() != 'rpcs3.exe':
            fail('请选择 rpcs3.exe、RPCS3 数据目录或 savedata 目录；不要选择游戏 EBOOT.BIN。')
        p = p.parent
    if p.suffix.lower() == '.app':
        p = Path.home()/'Library/Application Support/rpcs3'
    def is_save(x):
        return x.name == 'savedata' and re.fullmatch(r'\d{8}', x.parent.name) and x.parent.parent.name == 'home' and x.parent.parent.parent.name == 'dev_hdd0' and x.parent.is_dir()
    if is_save(p):
        return [p]
    candidates = []
    roots = [p, p/'dev_hdd0', p/'rpcs3/dev_hdd0']
    for root in roots:
        home = root/'home'
        if root.name == 'dev_hdd0' and home.is_dir():
            for profile in sorted(home.iterdir()):
                if profile.is_dir() and re.fullmatch(r'\d{8}', profile.name):
                    no_links(profile)
                    candidates.append(profile/'savedata')
    candidates = list(dict.fromkeys(candidates))
    if not candidates:
        fail('没有找到 RPCS3 用户目录。存档不写入 Game/PS3_GAME。请在 RPCS3 中打开数据目录，选择其中 dev_hdd0，或直接选择 home/用户编号/savedata。新装模拟器请先完成固件和用户初始化。')
    return candidates

def make_plan(target, ids):
    target = Path(target).absolute()
    if targets(target) != [target]:
        fail('需要明确选定一个用户的 savedata 目录。')
    items = read_catalog()
    ids = set(ids)
    if not ids or ids - {x['id'] for x in items}:
        fail('请选择有效存档。')
    rows = []
    for item in items:
        if item['id'] in ids:
            before = snapshot(target/item['directory'])
            rows.append(dict(item=item, before=before, action='已一致，跳过' if before == item['hashes'] else ('备份并替换' if before is not None else '新增')))
    return dict(target=str(target), rows=rows)

def describe(plan):
    lines = ['目标用户：' + Path(plan['target']).parent.name, '存档位置：' + plan['target'], '']
    for row in plan['rows']:
        item = row['item']
        lines.append(f"{item['title']} → {item['slot']}：{row['action']}")
        lines.append(item['description'])
    lines += ['', '导入的是预制自由任务存档，不是在现有进度上追加奖励。',
              '同槽位会替换为随包进度；原档会完整备份，可在继续游玩前恢复。',
              '剧情档、系统档及其他槽位不改。仅面向 BLJS10050 1.02＋DLC；不会安装 DLC。',
              '存档结构已检查；四档后续任务推进仍待游戏内验证。',
              '导入后：自由任务 → 读取存档；按阵营、档位说明选择，在仓库查看武器/部件，在机库查看机体。']
    return '\n'.join(lines)

@contextlib.contextmanager
def lock(target):
    p = target.parent/'.suiten-import.lock'
    no_links(p)
    try:
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        fail('存在未结束的导入锁。请先检查备份里的 receipt.json；确认无导入程序运行后再删除锁文件：' + str(p))
    try:
        os.write(fd, str(os.getpid()).encode()); os.close(fd)
        yield
    finally:
        p.unlink(missing_ok=True)

def save_json(path, data):
    tmp = path.with_suffix('.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)

def install(plan):
    ensure_closed()
    target = Path(plan['target'])
    fresh = make_plan(target, [r['item']['id'] for r in plan['rows']])
    if fresh != plan:
        fail('预览后文件发生变化，请重新预览。')
    changes = [r for r in plan['rows'] if r['action'] != '已一致，跳过']
    if not changes:
        return None
    with lock(target):
        ensure_closed()
        for r in changes:
            if snapshot(target/r['item']['directory']) != r['before']:
                fail('存档发生变化，已停止。')
        base = target.parent/'SuitenSaveBackups'
        no_links(base)
        base.mkdir(exist_ok=True)
        required = sum(sum((HERE/'saves'/r['item']['id']/f).stat().st_size for f in r['item']['hashes']) for r in changes)
        required += sum(sum(p.stat().st_size for p in (target/r['item']['directory']).rglob('*') if p.is_file()) for r in changes if r['before'] is not None)
        if shutil.disk_usage(base).free < required * 2 + 1048576:
            fail('空间不足，未写入。')
        run = base/(datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
        run.mkdir()
        receipt = dict(format=1, target=str(target), state='preparing', records=[])
        rp = run/'receipt.json'
        for r in changes:
            item=r['item']; name=item['directory']
            staged=run/'new'/name
            shutil.copytree(HERE/'saves'/item['id'], staged)
            if snapshot(staged) != item['hashes']:
                fail('暂存校验失败，尚未修改存档。')
            if r['before'] is not None:
                shutil.copytree(target/name, run/'before'/name)
                if snapshot(run/'before'/name) != r['before']:
                    fail('备份校验失败，尚未修改存档。')
            receipt['records'].append(dict(name=name,before=r['before'],after=item['hashes']))
        receipt['state']='prepared'; save_json(rp,receipt)
        ensure_closed()
        if any(snapshot(target/r['name']) != r['before'] for r in receipt['records']):
            fail('存档在备份时发生变化，未写入。')
        target.mkdir(exist_ok=True)
        (run/'old').mkdir()
        touched=[]
        try:
            receipt['state']='installing';save_json(rp,receipt)
            for r in receipt['records']:
                name=r['name']; touched.append(r)
                if r['before'] is not None:
                    os.replace(target/name,run/'old'/name)
                os.replace(run/'new'/name,target/name)
                if snapshot(target/name) != r['after']:
                    fail('写入回读不一致：'+name)
            receipt['state']='installed';save_json(rp,receipt)
        except Exception:
            for r in reversed(touched):
                name=r['name']
                if (run/'old'/name).exists():
                    if (target/name).exists():shutil.rmtree(target/name)
                    os.replace(run/'old'/name,target/name)
                elif r['before'] is None and (target/name).exists():
                    shutil.rmtree(target/name)
            receipt['state']='rolled_back';save_json(rp,receipt)
            raise
        shutil.rmtree(run/'old')
        shutil.rmtree(run/'new')
        return rp

def restore(receipt_path):
    ensure_closed()
    rp=Path(receipt_path).absolute();no_links(rp)
    receipt=json.loads(rp.read_text('utf-8'))
    if receipt.get('format')!=1 or receipt.get('state')!='installed':
        fail('只能自动恢复已完成导入的记录；中断的操作请保留整个备份目录检查。')
    target=Path(receipt['target']);run=rp.parent
    if targets(target)!=[target] or run.parent!=target.parent/'SuitenSaveBackups':
        fail('备份记录不属于这个存档目录。')
    records=receipt['records']
    if not records or len({r['name'] for r in records})!=len(records) or any(r['name'] not in NAMES for r in records):
        fail('备份记录的槽位无效。')
    with lock(target):
        for r in records:
            if snapshot(target/r['name'])!=r['after']:
                fail('导入后存档已改变（可能已有新进度），为保留进度拒绝覆盖：'+r['name'])
            if r['before'] is not None and snapshot(run/'before'/r['name'])!=r['before']:
                fail('原存档备份校验失败。')
        stage=run/('restore-'+uuid.uuid4().hex)
        stage.mkdir();(stage/'current').mkdir();(stage/'new').mkdir()
        for r in records:
            if r['before'] is not None:
                shutil.copytree(run/'before'/r['name'],stage/'new'/r['name'])
                if snapshot(stage/'new'/r['name'])!=r['before']:fail('恢复暂存校验失败。')
        ensure_closed()
        if any(snapshot(target/r['name'])!=r['after'] for r in records):fail('恢复预检后存档发生变化。')
        touched=[]
        try:
            for r in records:
                name=r['name'];os.replace(target/name,stage/'current'/name);touched.append(r)
                if r['before'] is not None:os.replace(stage/'new'/name,target/name)
                if snapshot(target/name)!=r['before']:fail('恢复校验失败。')
            receipt['state']='restored';save_json(rp,receipt)
        except Exception:
            for r in reversed(touched):
                name=r['name']
                if (target/name).exists():shutil.rmtree(target/name)
                os.replace(stage/'current'/name,target/name)
            raise
        shutil.rmtree(stage)
    return rp

def gui():
    try:
        import tkinter as tk
        from tkinter import ttk, filedialog, messagebox
    except ImportError:
        fail('图形组件缺失。请完整解压便携 ZIP，并通过随包启动文件运行；不要混用旧版文件。')
    root=tk.Tk();root.title('水天之泪 · 存档导入器');root.geometry('880x740');root.minsize(740,620)
    frame=ttk.Frame(root,padding=20);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='选择奖励存档，导入 RPCS3',font=('',20,'bold')).pack(anchor='w')
    ttk.Label(frame,text='0.2.0 · 内置运行环境 · BLJS10050 · 1.02＋DLC\n这是预制自由任务存档，不会向你当前的进度追加物品。',padding=(0,8)).pack(anchor='w')
    location=tk.StringVar(value=str(Path.home()/'Library/Application Support/rpcs3') if sys.platform=='darwin' else '')
    row=ttk.Frame(frame);row.pack(fill='x',pady=8)
    ttk.Entry(row,textvariable=location).pack(side='left',fill='x',expand=True)
    def pick_dir():
        p=filedialog.askdirectory(title='选择 RPCS3 数据目录、dev_hdd0 或 savedata')
        if p:location.set(p)
    def pick_exe():
        p=filedialog.askopenfilename(title='选择 rpcs3.exe',filetypes=[('RPCS3','rpcs3.exe')])
        if p:location.set(p)
    ttk.Button(row,text='选择文件夹',command=pick_dir).pack(side='left',padx=4)
    if os.name=='nt':ttk.Button(row,text='选 rpcs3.exe',command=pick_exe).pack(side='left')
    profile=tk.StringVar();combo=ttk.Combobox(frame,textvariable=profile,state='readonly');combo.pack(fill='x')
    status=tk.StringVar(value='选择模拟器数据位置后点击「识别用户」。多用户请选实际游玩的用户。')
    ttk.Label(frame,textvariable=status,wraplength=810).pack(anchor='w',pady=6)
    def detect():
        try:
            found=[str(p) for p in targets(location.get())];combo['values']=found
            profile.set(found[0] if len(found)==1 else '')
            status.set('找到 '+str(len(found))+' 个用户，请核对上面的 savedata 路径。')
        except Exception as e:messagebox.showerror('未找到用户',str(e))
    ttk.Button(frame,text='识别用户',command=detect).pack(anchor='w')
    checks={}
    for item in read_catalog():
        v=tk.BooleanVar(value=False);checks[item['id']]=v
        ttk.Checkbutton(frame,text=item['title']+'  →  '+item['slot']+' 槽位',variable=v).pack(anchor='w',pady=(10,0))
        ttk.Label(frame,text=item['description'],wraplength=810).pack(anchor='w')
    ttk.Button(frame,text='全选四份',command=lambda:[v.set(True) for v in checks.values()]).pack(anchor='w',pady=8)
    output=tk.Text(frame,height=9,wrap='word',font=('',12));output.pack(fill='both',expand=True,pady=8)
    output.insert('1.0','首次使用建议先预览。若槽位已有进度，会明确显示「备份并替换」。\n系统档和剧情档不会被覆盖。四档任务推进仍待游戏内验证。')
    def preview():
        if not profile.get():fail('请先识别并选择目标用户。')
        plan=make_plan(profile.get(),[k for k,v in checks.items() if v.get()])
        output.delete('1.0','end');output.insert('1.0',describe(plan));return plan
    def preview_click():
        try:preview()
        except Exception as e:messagebox.showerror('未生成预览',str(e))
    def apply():
        try:
            plan=preview()
            if not messagebox.askyesno('确认导入这些存档',describe(plan)+'\n\n现在导入？'):return
            result=install(plan)
            msg=('导入完成，文件回读校验通过。\n备份记录：'+str(result)) if result else '这些存档已经一致，没有重复写入。'
            msg+='\n\n进入「自由任务 → 读取存档」，按阵营/档位选择。\n武器、部件看仓库；机体看机库。\n游戏内加载和后续推进仍需验证。'
            output.insert('end','\n\n'+msg);messagebox.showinfo('导入结果',msg)
        except Exception as e:messagebox.showerror('未完成导入',str(e))
    def undo():
        p=filedialog.askopenfilename(title='选择本工具备份中的 receipt.json',initialdir=str(Path(profile.get()).parent/'SuitenSaveBackups') if profile.get() else None,filetypes=[('导入记录','*.json')])
        if not p:return
        if not messagebox.askyesno('恢复原档','将撤销这次导入。若导入后已产生新进度，程序会拒绝覆盖。继续？'):return
        try:restore(p);messagebox.showinfo('恢复完成','原档已恢复并校验；本次新增的存档已撤回。')
        except Exception as e:messagebox.showerror('未恢复',str(e))
    buttons=ttk.Frame(frame);buttons.pack(fill='x')
    ttk.Button(buttons,text='预览导入内容',command=preview_click).pack(side='left')
    ttk.Button(buttons,text='导入所选存档',command=apply).pack(side='left',padx=8)
    ttk.Button(buttons,text='恢复原档',command=undo).pack(side='right')
    root.mainloop()

def main():
    p=argparse.ArgumentParser(description='水天之泪存档导入器：默认只预览；--apply 才写入。无参数打开图形界面。')
    p.add_argument('--target',help='RPCS3 数据目录、rpcs3.exe、dev_hdd0 或明确的 savedata 路径')
    p.add_argument('--profile',help='八位用户编号，例如 00000001；多用户时必填')
    p.add_argument('--select',nargs='+',choices=['all','e-online','e-all','z-online','z-all'],help='选择存档，all 为四份')
    p.add_argument('--apply',action='store_true',help='执行写入（同槽位备份后替换）')
    p.add_argument('--restore',help='用 receipt.json 恢复一次导入；与 --apply 合用')
    p.add_argument('--list',action='store_true',help='显示随包存档清单')
    a=p.parse_args()
    if len(sys.argv)==1:gui();return
    if a.list:
        print(json.dumps(read_catalog(),ensure_ascii=False,indent=2));return
    if a.restore:
        if not a.apply:fail('恢复需要 --apply；请先退出 RPCS3。')
        print('已恢复：',restore(a.restore));return
    if not a.target or not a.select:p.error('需要 --target 和 --select，或不带参数打开图形界面')
    found=targets(a.target)
    if a.profile:found=[x for x in found if x.parent.name==a.profile]
    if len(found)!=1:fail('请使用 --profile 指定一个有效用户。发现：'+', '.join(str(x) for x in found))
    ids=[r['id'] for r in read_catalog()] if 'all' in a.select else a.select
    plan=make_plan(found[0],ids);print(describe(plan))
    if a.apply:print('\n写入结果：',install(plan) or '已一致，无需写入')
    else:print('\n仅预览，尚未写入。确认后加 --apply。')

if __name__=='__main__':
    try:main()
    except Exception as e:
        print('操作停止：'+str(e),file=sys.stderr);sys.exit(1)
