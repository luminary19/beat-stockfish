"""Linux event-driven startup evidence wait; no polling and no model calls."""
import ctypes
import json
import os
from pathlib import Path
import select
import sys
import time
from campaign import LOGS

if __name__=='__main__':
    LOGS.mkdir(parents=True,exist_ok=True)
    libc=ctypes.CDLL(None,use_errno=True)
    fd=libc.inotify_init1(os.O_CLOEXEC|os.O_NONBLOCK)
    if fd<0: raise OSError(ctypes.get_errno(),'inotify_init1')
    watch=libc.inotify_add_watch(fd,os.fsencode(LOGS),0x00000008|0x00000080)
    if watch<0: raise OSError(ctypes.get_errno(),'inotify_add_watch')
    deadline=time.monotonic()+1250
    try:
        while True:
            for name in ('supervisor-stop.json','first-actor-request.json'):
                path=LOGS/name
                if path.exists():
                    try: result=json.loads(path.read_text())
                    except json.JSONDecodeError: continue
                    print(json.dumps(dict(evidence_file=str(path),evidence=result),indent=2))
                    sys.exit(0 if name=='first-actor-request.json' else 1)
            ready,_,_=select.select([fd],[],[],max(0,deadline-time.monotonic()))
            if not ready: raise TimeoutError('No actor-request or supervisor-stop event within startup bound')
            os.read(fd,65536)
    finally: os.close(fd)
