"""Synthetic local UI fixtures; no external client, credentials or domain implementation."""
from contextlib import contextmanager
import http.client
import json
import secrets
import threading

from mission_control.command_center_ui import LocalCEOInterface, UIConfig, ROOT
from mission_control.local_http import SyntheticBinding
from tests.connection_support import context, envelope, encoded, gateway_fixture


@contextmanager
def running_ui(gateway=None,config=None,role='data_reader',**options):
    if gateway is None:
        gateway,services,_=gateway_fixture()
        services.result=dict(state='inactive',packet_reference='syn-packet',revision=1,source_event_reference='syn-pilot-journey-1',original_classification='syn-class',current_classification='syn-class',executive_reference='syn-executive',department_references=['syn-department'],audience='command')
    ctx=context(role)
    binding=SyntheticBinding(secrets.token_hex(24),ctx.session_reference,ctx.policy_revision)
    config=config or UIConfig(reads=(encoded(envelope('visibility.project','syn-packet',
        {'audience':'command','team_reference':None},role=role)),))
    server=LocalCEOInterface(gateway,binding,config,synthetic_development=True,**options)
    worker=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':0.01},daemon=True);worker.start()
    try:yield server,binding
    finally:
        server.shutdown();server.server_close();worker.join(timeout=6)
        if worker.is_alive():raise RuntimeError('Listener did not stop')


def ui_request(server,path=ROOT,method='GET',body=None,cookie=None,headers=None,raw=None):
    connection=http.client.HTTPConnection(*server.server_address,timeout=6)
    fields={}
    if cookie:fields['Cookie']=cookie
    if method=='POST':fields.update({'Origin':f'http://127.0.0.1:{server.server_address[1]}','Content-Type':'application/json; charset=utf-8'})
    fields.update(headers or {})
    try:
        connection.request(method,path,raw if raw is not None else (json.dumps(body).encode() if body is not None else None),fields)
        response=connection.getresponse();data=response.read();result_headers=dict(response.getheaders())
        if data and result_headers.get('Content-Type','').startswith('application/json'):data=json.loads(data)
        return response.status,result_headers,data
    finally:connection.close()


def session(server):
    code,headers,_=ui_request(server)
    assert code==200
    cookie=headers['Set-Cookie'].split(';')[0]
    code,_,overview=ui_request(server,ROOT+'/api/overview',cookie=cookie)
    assert code==200,(code,overview)
    return cookie,overview
