"""Opt-in synthetic loopback HTTP boundary; no domain or outbound transport."""
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
import hmac
import ipaddress
import math
import socket
import threading

from .connection_contracts import MAX_REQUEST_BYTES, ROUTES, decode_request
from .connection_gateway import Gateway, LocalContext
from .synthetic_identity import canonical_bytes

COMMAND_CENTER = '/v1/command-center'
SECURITY_HEADERS = {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
    'Content-Security-Policy': "default-src 'none'; frame-ancestors 'none'",
    'Referrer-Policy': 'no-referrer',
    'X-Frame-Options': 'DENY',
    'Connection': 'close',
}


@dataclass(frozen=True)
class SyntheticBinding:
    """Installed by trusted startup code, never derived from HTTP claims."""
    token: str
    session_reference: str
    policy_revision: int


def loopback_address(host):
    if type(host) is not str or '%' in host:
        raise ValueError('Literal loopback address required')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        raise ValueError('Literal loopback address required') from None
    # This implementation deliberately supports literal IPv4 only; no DNS lookup.
    if address.version != 4 or not address.is_loopback:
        raise ValueError('IPv4 loopback required')
    return str(address)


class LocalHTTPServer(HTTPServer):
    """Serial bounded admission; start only with explicit synthetic opt-in.

    Socket timeouts bound reads/writes. Domain cancellation is cooperative through
    the unchanged gateway and transaction checks, not Python thread preemption.
    No TLS, production identity, public service, or connector activation is offered.
    """
    request_queue_size = 4
    allow_reuse_address = False

    def __init__(self, gateway=None, bindings=(), *, synthetic_development=False,
                 host='127.0.0.1', port=0, timeout_seconds=2):
        if synthetic_development is not True:
            raise PermissionError('Explicit synthetic-development flag required')
        host = loopback_address(host)
        if type(port) is not int or not 0 <= port <= 65535:
            raise ValueError('Invalid port')
        if (type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds)
                or not 0 < timeout_seconds <= 5):
            raise ValueError('Bounded timeout required')
        if type(gateway) is not Gateway or not bindings or len(bindings) > 32:
            raise PermissionError('Trusted gateway and synthetic bindings required')
        tokens = set()
        for binding in bindings:
            if (type(binding) is not SyntheticBinding or type(binding.token) is not str
                    or not 32 <= len(binding.token) <= 128 or not binding.token.isascii()
                    or not binding.token.isalnum() or binding.token in tokens):
                raise ValueError('Unique bounded synthetic token required')
            from .department_routing import ref
            from .registry_authorization import positive_revision
            ref(binding.session_reference); positive_revision(binding.policy_revision)
            tokens.add(binding.token)
        self.gateway, self.bindings = gateway, tuple(bindings)
        self.timeout_seconds = timeout_seconds
        super().__init__((host, port), _Handler)

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(self.timeout_seconds)
        if not ipaddress.ip_address(address[0]).is_loopback:
            connection.close()
            raise OSError('Loopback peer required')
        return connection, address

    def handle_error(self, request, client_address):
        # No traceback, request bytes, tokens, or confidential exception messages.
        pass


class _Handler(BaseHTTPRequestHandler):
    server_version = 'SyntheticLocalHTTP'
    sys_version = ''
    protocol_version = 'HTTP/1.1'

    def handle(self):
        # Absolute input deadline also bounds a client that drips bytes forever.
        self.input_timed_out = threading.Event()
        def stop_reading():
            self.input_timed_out.set()
            try:
                self.connection.shutdown(socket.SHUT_RD)
            except OSError:
                pass
        timer = threading.Timer(self.server.timeout_seconds, stop_reading)
        timer.daemon = True
        timer.start()
        try:
            super().handle()
        finally:
            timer.cancel()

    def __getattr__(self, name):
        if name.startswith('do_'):
            return self._dispatch
        raise AttributeError(name)

    def log_message(self, *_args):
        pass

    def version_string(self):
        return self.server_version

    def send_error(self, code, message=None, explain=None):
        self._error(code, 'invalid_http')

    def handle_expect_100(self):
        self._error(417, 'expectation_unavailable')
        return False

    def _reply(self, code, value):
        raw = canonical_bytes(value)
        self.close_connection = True
        try:
            self.send_response(code)
            for name, value in SECURITY_HEADERS.items():
                self.send_header(name, value)
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(raw)
        except (OSError, TimeoutError):
            pass

    def _error(self, code, reason):
        self._reply(*Gateway._error(code, reason))

    def _dispatch(self):
        if sum(len(name) + len(value) + 4 for name, value in self.headers.items()) > 8192:
            return self._error(431, 'headers_too_large')
        # No CORS; reject browser origins and proxy/identity claims altogether.
        if any(name.lower() in ('origin', 'forwarded', 'x-forwarded-for',
                'x-forwarded-host', 'x-forwarded-proto', 'x-remote-user',
                'x-synthetic-identity', 'cookie') for name in self.headers):
            return self._error(403, 'untrusted_headers')
        if any(len(self.headers.get_all(name)) != 1 for name in self.headers):
            return self._error(400, 'duplicate_headers')
        host, port = self.server.server_address
        if self.headers.get('Host') != f'{host}:{port}':
            return self._error(400, 'host_binding_required')
        if self.command not in ('GET', 'POST'):
            return self._error(405, 'method_unavailable')
        if len(self.path) > 256 or any(c in self.path for c in ('?', '#', '%', '\\')):
            return self._error(400, 'invalid_route')
        path = '/v1/visibility' if self.path == COMMAND_CENTER else self.path
        known = (self.command, path) in ROUTES or (self.command == 'GET' and any(
            path.startswith(stem) and path[len(stem):] and '/' not in path[len(stem):]
            for stem in ('/v1/work-packets/', '/v1/journeys/')))
        if not known:
            return self._error(404, 'route_unavailable')
        if ('Transfer-Encoding' in self.headers or 'Content-Encoding' in self.headers
                or 'Expect' in self.headers):
            return self._error(400, 'encoding_unavailable')
        if self.headers.get('Content-Type', '').lower() not in (
                'application/json', 'application/json; charset=utf-8'):
            return self._error(415, 'json_utf8_required')
        length = self.headers.get('Content-Length', '')
        if not length or not length.isascii() or not length.isdecimal():
            return self._error(411, 'length_required')
        if len(length) > 6 or int(length) > MAX_REQUEST_BYTES:
            return self._error(413, 'body_too_large')
        authorization = self.headers.get('Authorization', '')
        binding = next((item for item in self.server.bindings
            if hmac.compare_digest(authorization.encode('utf-8'),
                                   ('Bearer ' + item.token).encode('ascii'))), None)
        if binding is None:
            return self._error(403, 'denied')
        try:
            raw = self.rfile.read(int(length))
            if self.input_timed_out.is_set():
                return self._error(408, 'interrupted')
            if len(raw) != int(length):
                return self._error(400, 'incomplete_body')
            request = decode_request(raw)
            if self.path == COMMAND_CENTER and (request.requested_action != 'visibility.project'
                    or request.payload != {'audience': 'command', 'team_reference': None}):
                return self._error(400, 'command_projection_required')
        except (TimeoutError, OSError):
            return self._error(408, 'interrupted')
        except Exception:
            return self._error(400, 'invalid_request')
        context = LocalContext(binding.session_reference, binding.policy_revision)
        timer = threading.Timer(self.server.timeout_seconds, context.cancelled.set)
        timer.daemon = True
        timer.start()
        try:
            code, value = self.server.gateway.handle(self.command, path, raw, context)
        except Exception:
            return self._error(503, 'service_unavailable')
        finally:
            timer.cancel()
        self._reply(code, value)

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_HEAD = do_TRACE = do_CONNECT = _dispatch
