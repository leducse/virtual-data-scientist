import base64
import http.cookiejar
import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
import server
from analysis_engine import workspace_http


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.old_dir=server.DATA_DIR;server.DATA_DIR=Path(self.temp.name)
        self.old_instance=workspace_http._INSTANCE;workspace_http._INSTANCE=None
        self.server=ThreadingHTTPServer(('127.0.0.1',0),server.POCHandler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}/api/v2/'
        self.client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.request('workspace')
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        workspace_http._INSTANCE=self.old_instance;server.DATA_DIR=self.old_dir;self.temp.cleanup()
    def request(self,path,body=None,client=None,headers=None):
        req=urllib.request.Request(self.url+path,data=json.dumps(body).encode() if body is not None else None,
                                   headers={'Content-Type':'application/json',**(headers or {})})
        try:
            with (client or self.client).open(req) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as response:return response.code,json.load(response)
    def upload(self):
        return self.request('datasets',{'name':'sales.csv','content_base64':base64.b64encode(b'date,revenue\n2024-01-01,2').decode()})[1]['dataset']
    def test_http_upload_question_reload_and_owner_isolation(self):
        d=self.upload();status,response=self.request('runs',{'dataset_id':d['id'],'request_key':'test','question':'Show monthly revenue'})
        self.assertEqual(status,200,response);run=response['run'];self.assertEqual(run['result']['total'],2)
        self.assertEqual(self.request('workspace')[1]['runs'][0]['id'],run['id'])
        other=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.request('workspace',client=other)
        self.assertEqual(self.request('runs/'+run['id'],client=other)[0],404)
        self.assertEqual(self.request('workspace',client=other)[1]['datasets'],[])
        self.assertEqual(self.request(f"datasets/{d['id']}/delete",{})[0],200)
        self.assertEqual(self.request('runs/'+run['id'])[0],404)
    def test_nested_vendor_assets_stay_within_static_root(self):
        with self.client.open(self.url.replace('/api/v2/','/static/vendor/plotly-cartesian-4.2.0.min.js')) as response:
            self.assertEqual(response.status,200)
            self.assertIn('javascript',response.headers['Content-Type'])
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.client.open(self.url.replace('/api/v2/','/static/../server.py'))
        self.assertEqual(error.exception.code,404)

    def test_origin_host_type_and_upload_limit(self):
        for headers in [{'Origin':'https://evil.example'},{'Host':'evil.example'},{'Content-Type':'text/plain'}]:
            self.assertIn(self.request('datasets',{},headers=headers)[0],[400,403])
        self.assertEqual(self.request('datasets',{'name':'x.csv','content_base64':'!!!'})[0],400)
        req=urllib.request.Request(self.url+'datasets',data=b'{}',headers={'Content-Type':'application/json','Content-Length':str(15*1024*1024)})
        with self.assertRaises(urllib.error.HTTPError) as e:self.client.open(req)
        self.assertEqual(e.exception.code,413)


if __name__=='__main__':unittest.main()
