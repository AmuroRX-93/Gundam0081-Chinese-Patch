#!/usr/bin/env python3
"""Reproduce release delta payloads from separately held, hash-pinned resources.

The repository does not supply complete baseline/candidate game assets.
Each directory must mirror member paths and USRDIR/patch paths in the manifest.
"""
import argparse
import json
from pathlib import Path
from install_upgrade import digest, safe


def encode(a,b):
    shifts={0}
    for at in [len(a)//4,len(a)//2,3*len(a)//4]:
        if at+128<=len(a):
            pos=b.find(a[at:at+128])
            if pos>=0:shifts.add(pos-at)
    segments=[];payload=bytearray()
    for q in range(0,len(b),4096):
        chunk=b[q:q+4096]
        pos=next((q-shift for shift in sorted(shifts) if q-shift>=0 and a[q-shift:q-shift+len(chunk)]==chunk),None)
        if pos is None:kind='add';pos=len(payload);payload.extend(chunk)
        else:kind='copy'
        if segments and segments[-1][0]==kind and segments[-1][1]+segments[-1][2]==pos:segments[-1][2]+=len(chunk)
        else:segments.append([kind,pos,len(chunk)])
    return bytes(payload),segments


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline-dir',required=True,type=Path)
    p.add_argument('--candidate-dir',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    args=p.parse_args()
    m=json.loads(Path(__file__).with_name('upgrade-manifest.json').read_text())
    for item in m['members']+m['files']:
        a=safe(args.baseline_dir,item['path']).read_bytes();b=safe(args.candidate_dir,item['path']).read_bytes()
        if digest(a)!=item['before'] or digest(b)!=item['after']:raise ValueError('Source hash mismatch: '+item['path'])
        payload,segments=encode(a,b)
        if digest(payload)!=item['blob_sha256'] or segments!=item['segments']:raise ValueError('Recipe mismatch')
        target=safe(args.output,item['blob']);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(payload)
    print('All payloads reproduced and hash-verified.')

if __name__=='__main__':main()
