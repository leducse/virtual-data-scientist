"""Containerized AgentCore entrypoint for the automatically prepared-data workflow."""
from __future__ import annotations
import asyncio
import os
import threading
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from analysis_engine.ingestion import InputError
from analysis_engine.cloud_service import CloudService

app=BedrockAgentCoreApp()
_service=None
_lock=threading.Lock()


def dispatch(payload):
    global _service
    if payload.get('action')=='health':
        return {'ok':True,'service':'virtual-data-scientist-v2','release':os.environ.get('VDS_RELEASE','development')}
    with _lock:
        if _service is None:_service=CloudService(app)
    return {'ok':True,**_service.dispatch(payload)}


@app.entrypoint
async def invoke(payload,context=None):
    try:
        return await asyncio.to_thread(dispatch,payload)
    except InputError as exc:
        return {'ok':False,'error':{'code':exc.code,'message':str(exc),'details':exc.details}}
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Invocation failed')
        return {'ok':False,'error':{'code':'dependency_failure','message':'The cloud service could not complete this request.'}}


if __name__=='__main__':app.run(host='0.0.0.0',port=8080)
