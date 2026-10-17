"""Real ephemeral socket checks of the disabled synthetic boundary."""
import json
import socket
import time
import unittest
from unittest.mock import patch

from mission_control.connection_contracts import CONNECTORS, MAX_REQUEST_BYTES
from mission_control.local_http import LocalHTTPServer, SyntheticBinding, SECURITY_HEADERS
from tests.connection_support import envelope, gateway_fixture
from tests.local_http_support import running, request


class LocalHTTPTests(unittest.TestCase):
    def setUp(self):
        self.gateway, self.services, self.audit = gateway_fixture()

    def check(self, code, **options):
        with running(self.gateway) as (server, binding):
            result = request(server, binding, envelope(), **options)
            self.assertEqual(result[0], code, result)
            self.assertFalse(json.loads(result[2])['operational_authorized'])
            return result

    def test_disabled_by_default(self):
        with self.assertRaises(PermissionError): LocalHTTPServer()

    def test_non_loopback_and_dns_rejected_before_bind(self):
        for host in ('0.0.0.0', '192.168.1.2', '8.8.8.8', 'localhost', '::', '::1', '127.0.0.1%eth0'):
            with self.subTest(host=host), self.assertRaises(ValueError):
                LocalHTTPServer(synthetic_development=True, host=host)

    def test_unconfigured_authority_rejected(self):
        with self.assertRaises(PermissionError): LocalHTTPServer(synthetic_development=True)

    def test_timeout_configuration_bounded(self):
        for value in (0, -1, 6, float('nan'), float('inf'), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                LocalHTTPServer(synthetic_development=True, timeout_seconds=value)

    def test_health_security_headers_and_no_cors(self):
        _, headers, raw = self.check(200)
        for key, value in SECURITY_HEADERS.items(): self.assertEqual(headers[key], value)
        self.assertNotIn('Access-Control-Allow-Origin', headers)
        self.assertEqual(json.loads(raw)['result'], {'state': 'inactive'})
        self.assertNotIn('Python', headers['Server'])

    def test_fresh_identity_is_required(self):
        self.check(403, headers={'Authorization': ''})
        self.check(403, headers={'Authorization': 'Bearer ' + 'x'*48})
        self.assertEqual(self.audit.rows, [])

    def test_forged_actor_session_and_tenant_denied(self):
        for field in ('actor_reference', 'authentication_state_reference', 'tenant_reference'):
            with running(self.gateway) as (server, binding):
                data = envelope(**{field: 'syn-forged'})
                self.assertEqual(request(server, binding, data)[0], 403)
        self.assertEqual(self.audit.rows, [])

    def test_cors_and_proxy_identity_denied(self):
        for name in ('Origin', 'Forwarded', 'X-Forwarded-For', 'X-Remote-User', 'Cookie'):
            self.check(403, headers={name:'syn-untrusted'})

    def test_host_binding_blocks_rebinding(self):
        self.check(400, headers={'Host':'example.com'})

    def test_methods_and_routes_fail_closed(self):
        for method in ('PUT','DELETE','PATCH','OPTIONS','TRACE','CONNECT','BREW'):
            self.check(405, method=method)
        self.check(404, path='/missing')
        self.check(404, method='POST')
        for path in ('/health?token=x','/he%61lth','/health#x','/v1/journeys/a/b'):
            self.check(400 if path != '/v1/journeys/a/b' else 404, path=path)

    def test_content_type_and_encoding(self):
        for value in ('text/plain','application/json; charset=latin-1','application/json; boundary=x'):
            self.check(415, headers={'Content-Type':value})
        self.check(400, headers={'Content-Encoding':'gzip'})
        self.check(400, headers={'Transfer-Encoding':'chunked'})
        self.check(431, headers={'X-Large':'x'*8200})

    def test_strict_json_and_utf8(self):
        for raw in (b'{"x":1,"x":2}', b'[]', b'{}', b'\xff', b'{"x":NaN}', b'{}{}', b''):
            self.check(400, raw=raw)
        self.assertEqual(self.audit.rows, [])

    def test_body_size_before_read(self):
        self.check(413, raw=b'x'*(MAX_REQUEST_BYTES+1))
        self.check(411, headers={'Content-Length':'-1'})
        self.check(411, headers={'Content-Length':'1x'})

    def test_schema_revision_idempotency_freshness(self):
        for change in ({'schema_version':2}, {'expected_revision':True}, {'idempotency_key':''},
                       {'timestamp':'2000-01-01T00:00:00+00:00'}, {'extra':'syn-unknown'}):
            with running(self.gateway) as (server, binding):
                self.assertEqual(request(server,binding,envelope(**change))[0],400)
        with running(self.gateway) as (server,binding):
            self.assertEqual(request(server,binding,envelope(revision=2))[0],409)

    def test_duplicate_framing_rejected(self):
        with running(self.gateway) as (server,binding):
            with socket.create_connection(server.server_address, timeout=2) as client:
                host,port=server.server_address
                raw=(f'POST /v1/decisions HTTP/1.1\r\nHost: {host}:{port}\r\n'
                     'Content-Length: 0\r\nContent-Length: 1\r\n\r\n').encode()
                client.sendall(raw)
                self.assertIn(b'400',client.recv(4096))

    def test_body_read_timeout(self):
        with running(self.gateway,timeout_seconds=0.1) as (server,binding):
            with socket.create_connection(server.server_address, timeout=2) as client:
                host,port=server.server_address
                raw=(f'GET /health HTTP/1.1\r\nHost: {host}:{port}\r\n'
                     f'Authorization: Bearer {binding.token}\r\nContent-Type: application/json\r\n'
                     'Content-Length: 10\r\n\r\nx').encode()
                client.sendall(raw)
                self.assertIn(b'408',client.recv(4096))

    def test_cooperative_domain_deadline(self):
        def slow(request,context,budget):
            time.sleep(0.06);budget.check()
        self.services.execute=slow
        with running(self.gateway,timeout_seconds=0.02) as (server,binding):
            data=envelope('readiness.status')
            self.assertEqual(request(server,binding,data,path='/v1/readiness')[0],408)

    def test_sanitized_service_failure(self):
        with patch.object(self.services,'execute',side_effect=RuntimeError('private-marker')):
            with running(self.gateway) as (server,binding):
                code,_,raw=request(server,binding,envelope('readiness.status'),path='/v1/readiness')
                self.assertEqual(code,503);self.assertNotIn(b'private-marker',raw)

    def test_command_center_reuses_gateway_projection(self):
        with running(self.gateway,role='data_reader') as (server,binding):
            data=envelope('visibility.project','syn-packet',{'audience':'command','team_reference':None},role='data_reader')
            code,_,raw=request(server,binding,data,path='/v1/command-center')
            self.assertEqual(code,200,raw)
            self.assertEqual(self.services.calls[-1].requested_action,'visibility.project')
            data['payload']['audience']='executive'
            self.assertEqual(request(server,binding,data,path='/v1/command-center')[0],400)

    def test_connector_controls_unchanged(self):
        self.assertEqual(len(CONNECTORS),7)
        for connector in CONNECTORS:
            connector.validate();self.assertFalse(connector.enabled)
            with self.assertRaises(PermissionError): connector.transmit()

    def test_rate_limit_delegated(self):
        from mission_control.connection_gateway import LocalRateLimit
        self.gateway.rate_limit=LocalRateLimit(1)
        with running(self.gateway) as (server,binding):
            self.assertEqual(request(server,binding,envelope())[0],200)
            self.assertEqual(request(server,binding,envelope())[0],429)
