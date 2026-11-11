"""Read-only helper exposed to restricted native ticks; no arbitrary arguments."""
import json
import os
from pathlib import Path
import sys
from campaign import A, ROOT, OPENING, validate_proposal, fingerprint, costs, readj

def validate(path):
    p=readj(path); state=readj(A/'research-state.json')
    assert 1<=len(p['candidates'])<=2
    base=(A/'original-task.txt').read_text()
    seen=set(state['historical_fingerprints'])|{c['fingerprint'] for c in state['candidates'].values()}
    rows=[]
    for c in p['candidates']:
        opening,asset=validate_proposal(c)
        prompt=base.replace(OPENING,opening,1); fp=fingerprint(prompt,asset)
        assert fp not in seen,'Duplicate candidate'
        seen.add(fp); rows.append(dict(fingerprint=fp,costs=costs(base,prompt,asset)))
    return rows

if __name__=='__main__':
    assert len(sys.argv)==1,'No arguments accepted'
    path=(ROOT/os.environ['AUTORESEARCH_TICK_OUTPUT']).resolve()
    assert path.is_relative_to((A/'ticks').resolve()) and path.name=='proposal.json'
    try: print(json.dumps(dict(valid=True,candidates=validate(path)),indent=2))
    except Exception as e:
        print(json.dumps(dict(valid=False,error=str(e)))); sys.exit(1)
