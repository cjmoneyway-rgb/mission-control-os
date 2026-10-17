"""Explicit loopback synthetic transport fixture; never opens a nonlocal client."""
from contextlib import contextmanager
import http.client
import secrets
import threading

from mission_control.local_http import LocalHTTPServer, SyntheticBinding
from tests.connection_support import context, encoded


@contextmanager
def running(gateway, role='audit_reviewer', **options):
    ctx = context(role)
    binding = SyntheticBinding(secrets.token_hex(24), ctx.session_reference, ctx.policy_revision)
    server = LocalHTTPServer(gateway, (binding,), synthetic_development=True, **options)
    worker = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
    worker.start()
    try:
        yield server, binding
    finally:
        server.shutdown(); server.server_close(); worker.join(timeout=6)
        if worker.is_alive():
            raise RuntimeError('Synthetic server failed to stop')


def request(server, binding, data, method='GET', path='/health', headers=None, raw=None):
    connection = http.client.HTTPConnection(*server.server_address, timeout=6)
    fields = {'Content-Type': 'application/json; charset=utf-8',
              'Authorization': 'Bearer ' + binding.token}
    fields.update(headers or {})
    try:
        connection.request(method, path, encoded(data) if raw is None else raw, fields)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()
