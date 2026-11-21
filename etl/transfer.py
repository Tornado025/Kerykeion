"""Bounded parallel HTTP ranges, atomic checkpoints, full-file SHA-256."""
import hashlib,json,os,threading,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import requests

def download(url,target,workers=None):
    workers = int(os.getenv("KERYKEION_DOWNLOAD_WORKERS", "6")) if workers is None else workers
    if not 1 <= workers <= 8:
        raise ValueError("Download workers must be between 1 and 8")
    probe=requests.get(url,headers={'Range':'bytes=0-0'},timeout=(30,60))
    probe.raise_for_status()
    if probe.status_code!=206 or 'Content-Range' not in probe.headers:raise ValueError('Server does not support verified ranges')
    total=int(probe.headers['Content-Range'].split('/')[-1]);modified=probe.headers.get('Last-Modified','');probe.close()
    side=target.with_suffix(target.suffix+'.ranges.json');chunk=4*2**20
    if side.exists():
        state=json.loads(side.read_text())
        if (state['url'],state['total'],state['modified'])!=(url,total,modified):raise ValueError('Remote artifact changed during transfer')
    else:
        prefix=min(target.stat().st_size,total) if target.exists() else 0
        state=dict(url=url,total=total,modified=modified,prefix=prefix,done={})
        with target.open('ab') as f:f.truncate(total)
    lock=threading.Lock()
    def checkpoint():
        temp=side.with_suffix('.tmp');temp.write_text(json.dumps(state));temp.replace(side)
    checkpoint();jobs=[(s,min(s+chunk,total)) for s in range(state['prefix'],total,chunk)]
    def fetch(span):
        start,end=span;key=str(start)
        if key in state['done']:return
        for attempt in range(4):
            try:
                r=requests.get(url,headers={'Range':f'bytes={start}-{end-1}','If-Range':modified},timeout=(30,90));r.raise_for_status()
                if r.status_code!=206 or r.headers.get('Content-Range')!=f'bytes {start}-{end-1}/{total}' or len(r.content)!=end-start:raise ValueError('Invalid range response')
                data=r.content;r.close()
                with target.open('r+b',buffering=0) as f:f.seek(start);f.write(data);os.fsync(f.fileno())
                with lock:
                    state['done'][key]=hashlib.sha256(data).hexdigest();checkpoint()
                    completed=state['prefix']+sum(min(chunk,total-int(k)) for k in state['done'])
                    print(f'{target.name}: {completed//2**20}/{total//2**20} MiB',flush=True)
                return
            except Exception:
                if attempt==3:raise
                time.sleep(min(2**attempt,8))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for future in as_completed([pool.submit(fetch,j) for j in jobs]):future.result()
    digest=hashlib.sha256()
    with target.open('rb') as f:
        for block in iter(lambda:f.read(2**20),b''):digest.update(block)
    return digest.hexdigest(),total,modified
