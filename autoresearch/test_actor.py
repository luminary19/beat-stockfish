"""Offline adapter checks against the installed Inspect/OpenAI interfaces."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import httpx
from openai import RateLimitError
from inspect_ai.model._providers.openai import OpenAIAPI
import actor

class AdapterTests(unittest.TestCase):
    def test_real_sdk_error_capture_and_retry_decision(self):
        response=httpx.Response(429,request=httpx.Request('POST','http://localhost/test'))
        exc=RateLimitError('Quota exhausted',response=response,body={'code':'insufficient_quota'})
        with tempfile.TemporaryDirectory(dir='/tmp/opencode') as d:
            path=Path(d)/'errors.jsonl'
            async def fail(*args): raise exc
            with patch.object(OpenAIAPI,'generate',fail), patch.object(OpenAIAPI,'should_retry',return_value=True), patch.dict(os.environ,{'CAMPAIGN_TRANSPORT_ERRORS':str(path)}):
                actor.install()
                with self.assertRaises(RateLimitError):
                    asyncio.run(OpenAIAPI.generate(object(),[],[],'none',None))
                decision=OpenAIAPI.should_retry(object(),exc)
                self.assertFalse(decision.retry)
            row=json.loads(path.read_text())
            self.assertEqual(row['stage'],'debrief')
            self.assertEqual(row['status_code'],429)
            self.assertEqual(row['body']['code'],'insufficient_quota')
            self.assertNotIn('headers',row)

    def test_eval_adapter_preserves_args_and_bounds_only_retries(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'run'))
        import rollout
        with patch.object(rollout,'eval_set') as evaluate, patch.object(actor,'install'), patch.object(rollout,'main',side_effect=lambda: rollout.eval_set('task',model='openai/gpt-6-astra',reasoning_effort='high',retry_attempts=1)):
            actor.main()
            args,kw=evaluate.call_args
        self.assertEqual(args,('task',))
        self.assertEqual(kw,dict(model='openai/gpt-6-astra',reasoning_effort='high',
            retry_attempts=0,retry_on_error=0,max_retries=2,model_args={'max_retries':0}))

if __name__=='__main__': unittest.main()
