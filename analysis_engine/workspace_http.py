"""Loopback-only local demo API. Replace cookie identity with verified auth before hosting."""
from __future__ import annotations
import base64
import binascii
import hashlib
import json
import os
import re
import secrets
import threading
from http.cookies import SimpleCookie
from urllib.parse import urlparse
from pydantic import ValidationError
from analysis_engine.ingestion import InputError
from analysis_engine.workspace import Workspace

_INSTANCE = None
_LOCK = threading.Lock()


def workspace(root):
    global _INSTANCE
    with _LOCK:
        if _INSTANCE is None:
            if os.environ.get("VDS_RUNTIME_ARN"):
                from analysis_engine.cloud_proxy import CloudProxy
                _INSTANCE = CloudProxy(os.environ["VDS_RUNTIME_ARN"], os.environ.get("AWS_REGION", "us-east-1"))
            else:
                _INSTANCE = Workspace(root / "workspace")
                _INSTANCE.recover()
        return _INSTANCE


def handle(handler, method, root):
    path = urlparse(handler.path).path
    if not path.startswith("/api/v2/"):
        return False
    cookie_header = None
    try:
        host = handler.headers.get("Host", "")
        parsed_host = urlparse("http://" + host)
        if parsed_host.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed_host.port != handler.server.server_port:
            raise InputError("This demo API is available only on the local loopback host.", "access_denied")
        if method != "GET":
            origin = handler.headers.get("Origin")
            if origin and origin != "http://" + host:
                raise InputError("Cross-origin mutations are blocked.", "access_denied")
            if handler.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise InputError("Use application/json.")
        cookie = SimpleCookie()
        cookie.load(handler.headers.get("Cookie", ""))
        token = cookie.get("vds_owner")
        token = token.value if token else None
        if not token or not re.fullmatch(r"[a-f0-9]{64}", token):
            if method != "GET" or path != "/api/v2/workspace":
                raise InputError("Open the workspace before making a request.", "access_denied")
            token = secrets.token_hex(32)
            cookie_header = f"vds_owner={token}; HttpOnly; SameSite=Strict; Path=/api/v2; Max-Age=2592000"
        owner = hashlib.sha256(token.encode()).hexdigest()
        service = workspace(root)
        payload = {}
        if method != "GET":
            length = int(handler.headers.get("Content-Length", "0"))
            if not 0 < length <= 14*1024*1024:
                raise InputError("Request exceeds the 14 MiB body limit.", "upload_limit")
            payload = json.loads(handler.rfile.read(length))
            if not isinstance(payload,dict):
                raise InputError("JSON body must be an object.")
        status = 200
        if method == "GET" and path == "/api/v2/workspace":
            result = service.list(owner)
        elif path == '/api/v2/public-datasets' and method == 'GET':
            from analysis_engine.public_datasets import catalog
            result={'datasets':catalog()}
        elif path == '/api/v2/public-datasets' and method == 'POST':
            result={'dataset':service.load_sample(owner,payload.get('sample_id'))}
        elif method == "POST" and path == "/api/v2/datasets":
            try:
                raw = base64.b64decode(payload.get("content_base64", ""), validate=True)
            except (ValueError,binascii.Error) as exc:
                raise InputError("Upload content must be base64 encoded.") from exc
            result = {"dataset": service.ingest(owner,str(payload.get("name","")),raw,payload.get("sheet"),payload.get("header_row"),payload.get("question"))}
            status = 201
        elif method == "POST" and path == "/api/v2/runs":
            result = {"run": service.submit(owner,payload)}
            status = 202 if result["run"]["status"] in {"queued","running","reviewing"} else 200
        elif method == "GET" and re.fullmatch(r"/api/v2/runs/[a-f0-9]{32}",path):
            result = {"run": service.run(owner,path.rsplit("/",1)[-1])}
        elif method == 'GET' and re.fullmatch(r'/api/v2/runs/[a-f0-9]{32}/(artifacts|prepared-data)',path) and hasattr(service,'artifacts'):
            from urllib.parse import parse_qs
            query=parse_qs(urlparse(handler.path).query)
            run_id=path.split('/')[-2]
            result=service.prepared_data(owner,run_id) if path.endswith('prepared-data') else service.artifacts(owner,run_id,query.get('palette',['decision'])[0])
        elif method == "POST" and re.fullmatch(r"/api/v2/runs/[a-f0-9]{32}/cancel",path):
            result = {"run": service.cancel(owner,path.split("/")[-2])}
        elif method == "POST" and re.fullmatch(r"/api/v2/datasets/[a-f0-9]{32}/delete",path):
            result = service.delete(owner,path.split("/")[-2])
        else:
            raise InputError("Endpoint not found.","not_found")
        body = {"ok":True,**result}
    except InputError as exc:
        status = {"not_found":404,"access_denied":403,"capacity_exceeded":429,"idempotency_conflict":409,"upload_limit":413}.get(exc.code,400)
        body = {"ok":False,"error":{"code":exc.code,"message":str(exc),"details":exc.details}}
    except (ValueError,TypeError,ValidationError) as exc:
        status,body = 400,{"ok":False,"error":{"code":"invalid_input","message":"Check the request fields and file format."}}
    except Exception:
        status,body = 500,{"ok":False,"error":{"code":"internal_error","message":"The workspace could not complete this request."}}
    encoded = json.dumps(body,allow_nan=False).encode()
    handler.send_response(status)
    for key,value in [("Content-Type","application/json; charset=utf-8"),("Content-Length",str(len(encoded))),("Cache-Control","no-store"),("X-Content-Type-Options","nosniff")]:
        handler.send_header(key,value)
    if cookie_header:
        handler.send_header("Set-Cookie",cookie_header)
    handler.end_headers()
    handler.wfile.write(encoded)
    return True
