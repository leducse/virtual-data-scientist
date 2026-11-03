"""Bound every provider request, including internal structured-output retries.

Nova Pro does not expose CountTokens in this account/region. For text-only
Converse requests we reserve UTF-8 request bytes plus protocol headroom and the
maximum output tokens. This deliberately over-reserves; measured usage releases
headroom only after a completed agent turn. Unknown outcomes keep the reservation.
"""
import json
import threading
from analysis_engine.ingestion import InputError


class TokenBudget:
    def __init__(self,limit):
        self.limit=int(limit)
        self.committed=0
        self.lock=threading.Lock()

    def before_call(self,params,**_):
        # Only text/tool JSON is permitted by this app. Never estimate image/audio
        # tokenization with a text heuristic if a future model adds these blocks.
        raw=json.dumps(params,ensure_ascii=False,default=str).encode()
        def unsupported(value):
            if isinstance(value,dict):return any(k in ('image','video','document','audio') or unsupported(v) for k,v in value.items())
            if isinstance(value,list):return any(unsupported(v) for v in value)
            return False
        if unsupported(params.get('messages',[])):
            raise InputError('This preview supports text-only model requests.','quota_exceeded')
        output=int(params.get('inferenceConfig',{}).get('maxTokens',2500))
        hold=len(raw)+4096+output
        with self.lock:
            if self.committed+hold>self.limit:
                raise InputError('The remaining preview allowance cannot cover this analysis safely. Try a shorter question or a smaller dataset. Saved results remain available.','quota_exceeded')
            self.committed+=hold

    def reconcile(self,before,actual):
        with self.lock:
            held=self.committed-before
            if actual>held:
                # Fail closed if a provider/model changes its tokenization or the
                # adapter no longer supplies a preflight for every model request.
                raise InputError('Model usage exceeded its reserved estimate. Further analysis is paused.','quota_exceeded')
            self.committed=before+actual
