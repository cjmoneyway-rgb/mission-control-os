"""Offline adversarial, session, confirmation and structural accessibility checks."""
from dataclasses import asdict
from html.parser import HTMLParser
from pathlib import Path
import socket
import time
import unittest
from unittest.mock import patch

from mission_control.command_center_ui import LocalCEOInterface,UIConfig,ROOT,ASSET_ROOT,CSP
from mission_control.connection_contracts import CONNECTORS,COMMAND_STAGES
from tests.command_center_support import running_ui,ui_request,session
from tests.connection_support import envelope,encoded,gateway_fixture
from tests.pilot_support import pilot_contracts,JOURNEY


def intake_config():
    journey,intake,*_=pilot_contracts()
    return UIConfig(actions=(encoded(envelope('intake',JOURNEY,{'journey':asdict(journey),'intake':asdict(intake)},role='data_writer',revision=0)),))


def prepared(server,cookie,overview):
    return ui_request(server,ROOT+'/api/prepare','POST',{'action_reference':'syn-ui-action-1','csrf_token':overview['csrf_token']},cookie)


def confirmed(value,**changes):
    body={key:value[key] for key in ('request_reference','idempotency_key','expected_revision','csrf_token')}
    body['confirmed']=True;body.update(changes);return body


class UIBoundaryTests(unittest.TestCase):
    def test_disabled_without_authority(self):
        with self.assertRaises(PermissionError):LocalCEOInterface()
        with self.assertRaises(PermissionError):LocalCEOInterface(synthetic_development=True)

    def test_literal_host_only(self):
        for host in ('localhost','0.0.0.0','127.0.0.2','192.168.1.2','8.8.8.8','::1','*'):
            with self.subTest(host=host),self.assertRaises(ValueError):LocalCEOInterface(host=host,synthetic_development=True)

    def test_shutdown_clears_sessions_and_releases_ephemeral_port(self):
        with running_ui() as (server,_):
            session(server);address=server.server_address
            self.assertNotEqual(address[1],0);self.assertTrue(server.sessions)
        self.assertEqual(server.sessions,{})
        with socket.socket() as sock:self.assertNotEqual(sock.connect_ex(address),0)

    def test_import_does_not_start_listener(self):
        import subprocess,sys
        code="from unittest.mock import patch; guard=patch('http.server.HTTPServer.__init__',side_effect=AssertionError('No listener')); guard.start(); import mission_control.command_center_ui"
        subprocess.run([sys.executable,'-B','-c',code],check=True)

    def test_cookie_and_no_bearer_exposure(self):
        with running_ui() as (server,binding):
            code,headers,page=ui_request(server)
            self.assertEqual(code,200)
            for attribute in ('HttpOnly','SameSite=Strict','Path=/command-center','Max-Age=300'):self.assertIn(attribute,headers['Set-Cookie'])
            self.assertNotIn('Secure',headers['Set-Cookie'])
            self.assertNotIn(binding.token.encode(),page)
            cookie=headers['Set-Cookie'].split(';')[0]
            for path in ('/app.js','/app.css','/api/overview'):
                code,_,data=ui_request(server,ROOT+path,cookie=cookie)
                self.assertEqual(code,200);self.assertNotIn(binding.token,str(data))

    def test_unknown_expired_and_restart_session_denied(self):
        with running_ui() as (server,_):
            self.assertEqual(ui_request(server,ROOT+'/api/overview',cookie='mc_ceo_session=unknown')[0],403)
            cookie,_=session(server)
            for entry in server.sessions.values():entry['expires']=0
            self.assertEqual(ui_request(server,ROOT+'/api/overview',cookie=cookie)[0],403)
        with running_ui() as (server,_):self.assertEqual(ui_request(server,ROOT+'/api/overview',cookie=cookie)[0],403)

    def test_security_headers(self):
        with running_ui() as (server,_):
            _,headers,_=ui_request(server)
            for name in ('Content-Security-Policy','X-Content-Type-Options','Referrer-Policy','X-Frame-Options','Permissions-Policy','Cache-Control','Pragma','Cross-Origin-Resource-Policy'):self.assertIn(name,headers)
            self.assertEqual(headers['Content-Security-Policy'],CSP)
            self.assertNotIn('Access-Control-Allow-Origin',headers)

    def test_host_origin_forwarding_and_fetch_site_rejected(self):
        with running_ui() as (server,_):
            self.assertEqual(ui_request(server,headers={'Sec-Fetch-Site':'none'})[0],200)
            for headers in ({'Host':'evil.test'},{'Origin':'http://evil.test'},{'X-Forwarded-Host':'127.0.0.1'},{'Sec-Fetch-Site':'cross-site'},{'Authorization':'Bearer hidden'}):
                self.assertIn(ui_request(server,headers=headers)[0],(400,403))

    def test_method_route_and_asset_body_rejected(self):
        with running_ui() as (server,_):
            for method in ('OPTIONS','HEAD','TRACE','PATCH','DELETE','BREW'):self.assertEqual(ui_request(server,method=method)[0],405)
            for path in ('/v1/intake',ROOT+'/credentials',ROOT+'/connectors',ROOT+'?token=x',ROOT+'/%2e%2e'):
                self.assertIn(ui_request(server,path)[0],(400,404))
            self.assertEqual(ui_request(server,body={'x':1})[0],400)

    def test_header_body_content_type_and_encoding_limits(self):
        with running_ui(config=intake_config(),role='data_writer') as (server,_):
            cookie,overview=session(server)
            path=ROOT+'/api/prepare'
            for raw,headers,code in ((b'x'*65537,{},413),(b'{}',{'Content-Type':'text/plain'},415),(b'{}',{'Content-Encoding':'gzip'},400),(b'{}',{'X-Large':'x'*8200},431)):
                self.assertEqual(ui_request(server,path,'POST',cookie=cookie,raw=raw,headers=headers)[0],code)

    def test_json_and_browser_authority_claims_rejected(self):
        with running_ui(config=intake_config(),role='data_writer') as (server,_):
            cookie,overview=session(server)
            for raw in (b'{"x":1,"x":2}',b'{"x":NaN}',b'\xff',b'[]',b'{"x":"\\ud800"}'):
                self.assertEqual(ui_request(server,ROOT+'/api/prepare','POST',cookie=cookie,raw=raw)[0],400)
            for key in ('role','tenant_reference','approval','authorized','payload'):
                body=dict(action_reference='syn-ui-action-1',csrf_token=overview['csrf_token']);body[key]='syn-forged'
                self.assertEqual(ui_request(server,ROOT+'/api/prepare','POST',body,cookie)[0],400)

    def test_csrf_missing_bad_and_cross_session_rejected(self):
        with running_ui(config=intake_config(),role='data_writer') as (server,_):
            cookie,overview=session(server)
            for token in ('', 'x'*64):
                self.assertEqual(ui_request(server,ROOT+'/api/prepare','POST',{'action_reference':'syn-ui-action-1','csrf_token':token},cookie)[0],403)
            other_cookie,other=session(server)
            self.assertEqual(ui_request(server,ROOT+'/api/prepare','POST',{'action_reference':'syn-ui-action-1','csrf_token':overview['csrf_token']},other_cookie)[0],403)
            self.assertEqual(prepared(server,cookie,overview)[0],200)

    def test_confirmation_and_csrf_replay_and_double_click(self):
        gateway,services,_=gateway_fixture()
        services.result=dict(state='inactive',journey_reference=JOURNEY,intake_reference=pilot_contracts()[1].event_id,original_classification='syn-entry-class',version=0)
        with running_ui(gateway=gateway,config=intake_config(),role='data_writer') as (server,_):
            cookie,overview=session(server);code,_,value=prepared(server,cookie,overview);self.assertEqual(code,200)
            self.assertEqual(prepared(server,cookie,overview)[2],value)
            for change,code in (({'confirmed':False},403),({'csrf_token':'invalid'},403),({'expected_revision':1},409),({'idempotency_key':'syn-forged'},409)):
                self.assertEqual(ui_request(server,ROOT+'/api/confirm','POST',confirmed(value,**change),cookie)[0],code)
            self.assertEqual(ui_request(server,ROOT+'/api/confirm','POST',confirmed(value),cookie)[0],200)
            self.assertEqual(ui_request(server,ROOT+'/api/confirm','POST',confirmed(value),cookie)[0],409)
            self.assertEqual(prepared(server,cookie,overview)[0],409)

    def test_unresolved_dependencies_block_later_actions(self):
        _,_,_,_,events=pilot_contracts()
        config=UIConfig(actions=(encoded(envelope('decision.submit',JOURNEY,{'event':asdict(events[0])},role='data_writer',revision=0)),))
        with running_ui(config=config,role='data_writer') as (server,_):
            cookie,overview=session(server);code,_,body=prepared(server,cookie,overview)
            self.assertEqual(code,409);self.assertEqual(body['error'],'dependencies_unresolved')

    def test_unknown_direct_object_and_confirmation_reference_denied(self):
        with running_ui(config=intake_config(),role='data_writer') as (server,_):
            cookie,overview=session(server)
            body={'action_reference':'syn-not-admitted','csrf_token':overview['csrf_token']}
            self.assertEqual(ui_request(server,ROOT+'/api/prepare','POST',body,cookie)[0],403)
            self.assertEqual(ui_request(server,ROOT+'/api/confirm','POST',{'request_reference':'syn-forged','idempotency_key':'syn-forged','expected_revision':0,'confirmed':True,'csrf_token':overview['csrf_token']},cookie)[0],403)

    def test_sanitized_malformed_and_private_service_failures(self):
        gateway,services,_=gateway_fixture()
        services.result=dict(state='inactive',packet_reference='syn-packet',revision=1,source_event_reference='syn-pilot-journey-1',original_classification='syn-class',current_classification='syn-class',executive_reference='syn-executive',department_references=['syn-department'],audience='command')
        with running_ui(gateway=gateway) as (server,_):
            cookie,overview=session(server)
            for result in ({'state':'active'}, {'state':'inactive','payload':'<script>private-marker</script>'}):
                with patch.object(gateway,'handle',return_value=(200,{'state':'inactive','operational_authorized':False,'result':result})):
                    code,_,body=ui_request(server,ROOT+'/api/overview',cookie=cookie)
                    self.assertEqual(code,400);self.assertNotIn('private-marker',str(body))
            with patch.object(gateway,'handle',side_effect=RuntimeError('private-marker')):
                code,_,body=ui_request(server,ROOT+'/api/overview',cookie=cookie)
                self.assertEqual(code,503);self.assertNotIn('private-marker',str(body))

    def test_empty_and_ordered_overview_counts_are_not_invented(self):
        with running_ui(config=intake_config(),role='data_writer') as (server,_):
            _,overview=session(server)
            self.assertEqual(overview['items'],[]);self.assertEqual(overview['stages'],list(COMMAND_STAGES))
            self.assertIsNone(overview['counts']['decision']);self.assertIsNone(overview['readiness'])

    def test_identity_revocation_is_rechecked(self):
        gateway,services,_=gateway_fixture()
        services.result=dict(state='inactive',packet_reference='syn-packet',revision=1,source_event_reference='syn-pilot-journey-1',original_classification='syn-class',current_classification='syn-class',executive_reference='syn-executive',department_references=['syn-department'],audience='command')
        with running_ui(gateway=gateway) as (server,_):
            cookie,_=session(server)
            with patch.object(gateway.gate,'verify',side_effect=PermissionError('private-marker')):
                code,_,body=ui_request(server,ROOT+'/api/overview',cookie=cookie)
                self.assertEqual(code,403);self.assertNotIn('private-marker',str(body))

    def test_connector_and_storage_boundary(self):
        self.assertEqual(len(CONNECTORS),7)
        for connector in CONNECTORS:
            connector.validate();self.assertFalse(connector.enabled)
            with self.assertRaises(PermissionError):connector.transmit()
        js=(ASSET_ROOT/'app.js').read_text()
        for forbidden in ('localStorage','sessionStorage','indexedDB','WebSocket','serviceWorker','innerHTML','outerHTML','insertAdjacentHTML','document.cookie','Authorization','Bearer'):
            self.assertNotIn(forbidden,js)
        for filename in ('index.html','app.css','app.js'):
            self.assertNotIn('https://',(ASSET_ROOT/filename).read_text())
            self.assertNotIn('http://',(ASSET_ROOT/filename).read_text())


class AccessibilityStructureTests(unittest.TestCase):
    def test_landmarks_headings_labels_and_tables(self):
        html=(ASSET_ROOT/'index.html').read_text()
        for element in ('<main','<header','<nav','<footer','<fieldset','<legend','<caption','scope="col"','role="status"','aria-live="polite"','href="#workspace"','tabindex="-1"'):
            self.assertIn(element,html)
        self.assertEqual(html.count('<h1>'),1)
        self.assertIn('aria-describedby="action-error"',html)
        self.assertIn('aria-labelledby="confirmation-title"',html)
        self.assertIn('I understand this is a synthetic, inactive action.',html)

    def test_six_stage_order_and_keyboard_focus_styles(self):
        html=(ASSET_ROOT/'index.html').read_text();positions=[html.index('<h3>'+stage.upper()+'</h3>') for stage in COMMAND_STAGES]
        self.assertEqual(positions,sorted(positions))
        css=(ASSET_ROOT/'app.css').read_text()
        for token in (':focus-visible','prefers-reduced-motion','max-width:700px','overflow-x:auto'):
            self.assertIn(token,css)
        self.assertIn('showModal()',(ASSET_ROOT/'app.js').read_text())
