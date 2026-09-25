#!/usr/bin/env python3
"""BLJS10050 Chinese resource upgrade. Python 3.9+, standard library only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys

VERSION = '2026.09.25-upgrade.1'
JOURNAL = '.suiten-cn-upgrade-20260925'
ROOT = Path(__file__).resolve().parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe(root, name):
    root = Path(root).resolve()
    p = (root / name).resolve()
    if p == root or root not in p.parents:
        raise ValueError('路径越界: ' + name)
    return p


def read_at(path, offset, size):
    with Path(path).open('rb') as f:
        f.seek(offset)
        data = f.read(size)
    if len(data) != size:
        raise ValueError('文件长度不足: ' + Path(path).name)
    return data


def sfo(path):
    b = Path(path).read_bytes()
    if b[:4] != b'\0PSF':
        raise ValueError('PARAM.SFO 格式错误')
    keys, values, count = struct.unpack_from('<III', b, 8)
    result = {}
    for i in range(count):
        k, _, n, _, v = struct.unpack_from('<HHIII', b, 20 + i * 16)
        end = b.index(0, keys + k)
        result[b[keys+k:end].decode()] = b[values+v:values+v+n].rstrip(b'\0').decode('utf-8', 'replace')
    return result


def archive(path):
    length = Path(path).stat().st_size
    h = read_at(path, 0, 16)
    if h[:6] != b'BfPk\xfe\xff':
        raise ValueError('game.arb 格式错误')
    base = struct.unpack_from('>H', h, 6)[0] * 2048
    if not 16 <= base <= min(length, 16 * 1024 * 1024):
        raise ValueError('索引越界')
    h = read_at(path, 0, base)
    entries = {}; q = 16
    for _ in range(struct.unpack_from('>H', h, 8)[0]):
        off, size, _, rec, nm = struct.unpack_from('>IIIHH', h, q)
        if rec < 17 + nm or q + rec > base:
            raise ValueError('成员索引错误')
        name = h[q+17:q+17+nm].decode()
        if name in entries or base + off + size > length:
            raise ValueError('重复或越界成员')
        entries[name] = {'offset': base + off, 'size': size, 'index': q}
        q += rec
    ordered = sorted(entries.values(), key=lambda e: e['offset'])
    for i, e in enumerate(ordered):
        end = ordered[i+1]['offset'] if i+1 < len(ordered) else length
        if e['offset'] < base or e['offset'] + e['size'] > end:
            raise ValueError('成员区间重叠')
        e['capacity'] = end - e['offset']
    return entries


def decode(old, item, root):
    blob = safe(root, item['blob']).read_bytes()
    if digest(blob) != item['blob_sha256']:
        raise ValueError('差分包损坏: ' + item['blob'])
    out = bytearray()
    for kind, off, size in item['segments']:
        if kind not in ('copy', 'add') or off < 0 or size < 0:
            raise ValueError('无效差分指令')
        source = old if kind == 'copy' else blob
        piece = source[off:off+size]
        if len(piece) != size:
            raise ValueError('差分区间越界')
        out.extend(piece)
    if len(out) != item['new_size'] or digest(out) != item['after']:
        raise ValueError('差分重建校验失败')
    return bytes(out)


def operation(path, offset, before, after, whole=False):
    return dict(path=str(Path(path).resolve()), offset=offset, before=before,
                after=after, whole=whole)


def plan(game, data, manifest, root):
    game, data = Path(game).resolve(), Path(data).resolve()
    if manifest['release'] != VERSION or manifest['title_id'] != 'BLJS10050':
        raise ValueError('不支持的升级清单')
    if sfo(safe(game, 'PS3_GAME/PARAM.SFO')).get('TITLE_ID') != 'BLJS10050':
        raise ValueError('需要 BLJS10050 游戏目录（直接包含 PS3_GAME）')
    update = safe(data, 'dev_hdd0/game/BLJS10050')
    info = sfo(safe(update, 'PARAM.SFO'))
    if info.get('TITLE_ID') != 'BLJS10050' or info.get('APP_VER') != '01.02':
        raise ValueError('需要已汉化的官方 1.02 更新；请检查 RPCS3 数据目录')
    archives = [safe(game, 'PS3_GAME/USRDIR/game.arb')]
    cache = safe(update, 'USRDIR/cache/game.arb')
    if cache.exists():
        archives.append(cache)
    if len(set(archives)) != len(archives):
        raise ValueError('本体与缓存指向同一文件')
    ops, states = [], []
    for path in archives:
        entries = archive(path)
        for item in manifest['members']:
            e = entries[item['path']]
            old = read_at(path, e['offset'], e['size'])
            sha = digest(old)
            if sha == item['after'] and len(old) == item['new_size']:
                states.append('after'); continue
            if sha != item['before'] or len(old) != item['old_size']:
                raise ValueError('资源版本不匹配，未安装: ' + item['path'])
            states.append('before')
            new = decode(old, item, root)
            span = max(len(old), len(new))
            if span > e['capacity']:
                raise ValueError('资源对齐余量不足，未安装')
            before = read_at(path, e['offset'], span)
            if any(before[len(old):]):
                raise ValueError('资源后方有非零数据，未安装')
            ops.append(operation(path, e['offset'], before, new + b'\0'*(span-len(new))))
            if len(old) != len(new):
                ops.append(operation(path, e['index']+4, struct.pack('>I', len(old)), struct.pack('>I', len(new))))
    for item in manifest['files']:
        path = safe(update, item['path'])
        old = path.read_bytes()
        if digest(old) == item['after'] and len(old) == item['new_size']:
            states.append('after'); continue
        if digest(old) != item['before'] or len(old) != item['old_size']:
            raise ValueError('更新资源版本不匹配，未安装: ' + item['path'])
        states.append('before')
        ops.append(operation(path, 0, old, decode(old, item, root), True))
    if set(states) == {'before', 'after'}:
        raise ValueError('检测到混合版本。先恢复未完成的升级，或统一为 20260917_r1 汉化版。')
    return ops


def json_save(path, data):
    tmp = path.with_suffix('.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)


def write_sync(path, data):
    with path.open('xb') as f:
        f.write(data); f.flush(); os.fsync(f.fileno())


def current(op, n):
    path = Path(op['path'])
    if op['whole']:
        return path.read_bytes()
    return read_at(path, op['offset'], n)


def write_op(op, value):
    with Path(op['path']).open('r+b') as f:
        f.seek(op['offset']); f.write(value)
        if op['whole']:
            f.truncate(len(value))
        f.flush(); os.fsync(f.fileno())


def check_space_and_access(game, ops):
    needed = sum(len(o['before']) + len(o['after']) for o in ops) + 32*1024*1024
    if shutil.disk_usage(game).free < needed:
        raise ValueError('游戏目录所在磁盘空间不足；请预留至少 512 MB')
    for path in {o['path'] for o in ops}:
        if shutil.disk_usage(Path(path).parent).free < 32*1024*1024:
            raise ValueError('目标磁盘空间不足；请预留至少 32 MB')
        if not Path(path).stat().st_mode & 0o222:
            raise PermissionError('目标只读: ' + Path(path).name)
        with Path(path).open('r+b'):
            pass


def install(game, ops):
    folder = Path(game) / JOURNAL
    if folder.exists():
        raise ValueError('已有升级记录；先检查或恢复，勿删除备份目录')
    if not ops:
        return '已经是此版本，无需写入'
    check_space_and_access(game, ops)
    folder.mkdir()
    record = dict(version=VERSION, status='preparing', pending=None, operations=[])
    journal = folder/'journal.json'
    json_save(journal, record)
    try:
        for i, op in enumerate(ops):
            entry = {k:v for k,v in op.items() if k not in ('before', 'after')}
            entry['container_size'] = Path(op['path']).stat().st_size
            for side in ('before', 'after'):
                name = '%04d-%s.bin' % (i, side)
                write_sync(folder/name, op[side])
                entry[side] = dict(file=name, size=len(op[side]), sha256=digest(op[side]))
            record['operations'].append(entry)
        record['status'] = 'prepared'; json_save(journal, record)
        # Recheck every input after staging and before the first write.
        for op in ops:
            if current(op, len(op['before'])) != op['before']:
                raise ValueError('准备期间目标发生变化；未开始写入')
        for i, op in enumerate(ops):
            record['status'] = 'applying'; record['pending'] = i; json_save(journal, record)
            write_op(op, op['after'])
            if current(op, len(op['after'])) != op['after']:
                raise ValueError('写入校验失败')
        record['status'] = 'installed'; record['pending'] = None; json_save(journal, record)
    except BaseException:
        # Persistent backup and write-ahead pending index support recovery after interruption.
        if record['status'] in ('preparing', 'prepared'):
            shutil.rmtree(folder)  # No game writes occurred.
        else:
            print('安装中断，备份已保留；保持 RPCS3 关闭，选择“恢复本次升级”。')
        raise
    return '升级完成；备份已保留。请手动启动游戏验收。'


def restore(game):
    folder = Path(game)/JOURNAL; journal = folder/'journal.json'
    record = json.loads(journal.read_text(encoding='utf-8'))
    if record.get('version') != VERSION:
        raise ValueError('恢复记录版本不匹配')
    if record['status'] in ('preparing', 'prepared', 'restored'):
        shutil.rmtree(folder)
        return '未提交的准备文件或已恢复记录已清理，游戏未再改动'
    if record['status'] not in ('installed', 'applying', 'restoring'):
        raise ValueError('未知恢复状态')
    prepared = []
    for i, op in enumerate(record['operations']):
        values = []
        for side in ('before', 'after'):
            p = safe(folder, op[side]['file']); value = p.read_bytes()
            if len(value) != op[side]['size'] or digest(value) != op[side]['sha256']:
                raise ValueError('备份损坏，停止恢复: '+p.name)
            values.append(value)
        before, after = values
        if not op['whole'] and Path(op['path']).stat().st_size != op['container_size']:
            raise ValueError('游戏容器长度已改变，停止恢复')
        now = current(op, max(len(before),len(after)))
        if now not in (before, after):
            # Only the logged interrupted write may contain a torn before/after combination.
            if record['status'] not in ('applying', 'restoring') or record['pending'] != i:
                raise ValueError('安装后资源已被其他修改，停止恢复')
            if not min(len(before),len(after)) <= len(now) <= max(len(before),len(after)) or any(
                    b not in [v[j] for v in values if j < len(v)] for j,b in enumerate(now)):
                raise ValueError('中断区间含未知数据，停止恢复')
        prepared.append((op,before))
    for i in reversed(range(len(prepared))):
        record['status'] = 'restoring'; record['pending'] = i; json_save(journal, record)
        op,before = prepared[i]; write_op(op,before)
        if current(op,len(before)) != before:
            raise ValueError('恢复写入校验失败，保留备份')
    record['status']='restored'; record['pending']=None; json_save(journal,record)
    shutil.rmtree(folder)
    return '已恢复至安装本升级包前的资源。'


def ensure_closed():
    if os.name == 'nt':
        result = subprocess.run(['tasklist','/FO','CSV','/NH'], capture_output=True, text=True, errors='replace', check=True)
        names = [line.split(',')[0].strip('"').lower() for line in result.stdout.splitlines()]
    else:
        result = subprocess.run(['ps','-axo','comm='], capture_output=True, text=True, check=True)
        names = [Path(line.strip()).name.lower() for line in result.stdout.splitlines()]
    if any('rpcs3' in n for n in names):
        raise ValueError('RPCS3 仍在运行。请保存进度并完全退出后再操作。')


def main():
    p=argparse.ArgumentParser(description='水天之泪 20260917_r1 → 20260925 汉化升级')
    p.add_argument('--game', required=True, type=Path)
    p.add_argument('--rpcs3', type=Path, help='直接包含 dev_hdd0 的 RPCS3 数据目录')
    group=p.add_mutually_exclusive_group(); group.add_argument('--check', action='store_true'); group.add_argument('--restore', action='store_true')
    a=p.parse_args()
    ensure_closed()
    if a.restore:
        print(restore(a.game.resolve())); return
    if not a.rpcs3:
        p.error('本升级包要求 --rpcs3：同步本体、已有缓存和已汉化的官方 1.02 更新')
    folder=a.game/JOURNAL
    if folder.exists():
        status=json.loads((folder/'journal.json').read_text(encoding='utf-8'))['status']
        if status != 'installed':
            raise ValueError('存在未完成事务；请先 --restore，再重新安装')
    manifest=json.loads((ROOT/'upgrade-manifest.json').read_text(encoding='utf-8'))
    ops=plan(a.game,a.rpcs3,manifest,ROOT)
    if not ops:
        print('本体、缓存及更新资源均已是本版，无需再次安装。'); return
    if a.check:
        check_space_and_access(a.game,ops)
        print('全部资源与差分校验通过，可升级。未写入游戏。'); return
    print(install(a.game.resolve(),ops))


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as e:
        print('未完成：'+str(e), file=sys.stderr)
        sys.exit(1)
