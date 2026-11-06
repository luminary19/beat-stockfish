#!/usr/bin/env python3
"""Campaign-local error-path adapter; leaves the shared runner/packages untouched."""
import functools
import json
import os
from pathlib import Path
import sys
import traceback

from campaign import classify, now

def error_record(exc, stage):
    return dict(time=now(), source='OpenAIAPI transport exception', stage=stage,
        exception_class=type(exc).__module__+'.'+type(exc).__qualname__,
        message=str(exc), code=getattr(exc,'code',None), type=getattr(exc,'type',None),
        body=getattr(exc,'body',None), status_code=getattr(exc,'status_code',None),
        request_id=getattr(exc,'request_id',None), traceback=traceback.format_exc())

def record(exc,stage):
    path=os.environ.get('CAMPAIGN_TRANSPORT_ERRORS')
    if path:
        with open(path,'a') as f:
            f.write(json.dumps(error_record(exc,stage),default=str)+'\n')
            f.flush(); os.fsync(f.fileno())

def install():
    from inspect_ai.model._providers.openai import OpenAIAPI
    from inspect_ai.model._model import RetryDecision
    from openai import APIError
    generate=OpenAIAPI.generate
    retry=OpenAIAPI.should_retry
    @functools.wraps(generate)
    async def captured(self,input,tools,tool_choice,config):
        stage='debrief' if tool_choice=='none' else 'actor'
        transport_path=os.environ.get('CAMPAIGN_TRANSPORT_ERRORS')
        startup_marker=os.environ.get('CAMPAIGN_STARTUP_MARKER')
        if transport_path and startup_marker and stage=='actor':
            # Exclusive first-request marker: observational only, no request changes.
            try:
                with Path(startup_marker).open('x') as f:
                    json.dump(dict(time=now(),pid=os.getpid(),episode=str(Path(transport_path).parent),
                                   event='OpenAIAPI.generate entered',model='openai/gpt-6-astra'),f)
                    f.flush(); os.fsync(f.fileno())
            except FileExistsError: pass
        try:
            result=await generate(self,input,tools,tool_choice,config)
            if isinstance(result,tuple) and isinstance(result[0],Exception):
                record(result[0],stage)
            return result
        except APIError as exc:
            record(exc,stage)
            raise
    @functools.wraps(retry)
    def bounded_retry(self,exc):
        if classify(error_record(exc,'retry-decision')) in ('quota_exhausted','blocker_auth_config'):
            return RetryDecision.no()
        return retry(self,exc)
    OpenAIAPI.generate=captured
    OpenAIAPI.should_retry=bounded_retry

def main():
    install()
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'run'))
    import rollout
    original=rollout.eval_set
    def bounded(*args,**kwargs):
        kwargs.update(max_retries=2,model_args={'max_retries':0},
                      retry_attempts=0,retry_on_error=0)
        print(json.dumps(dict(time=now(),event='campaign_actor_runner_entered',
            request_retries=2,sdk_retries=0,episode_retries=0,
            actor_turns=100,actor_seconds=10800,reasoning='high')),flush=True)
        return original(*args,**kwargs)
    rollout.eval_set=bounded
    rollout.main()

if __name__=='__main__': main()
