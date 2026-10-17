"""Local in-process gateway. No listener, network client, CLI wiring or default authority."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import threading
import time
from typing import Protocol

from .connection_contracts import (CONNECTORS, MAX_RESPONSE_BYTES, OutboxIntention, ROUTES,
    decode_request, validate_projection)
from .department_routing import ref
from .registry_authorization import positive_revision
from .registry_persistence import ConflictError
from .synthetic_identity import SyntheticAuthority, canonical, canonical_bytes, fingerprint


@dataclass(frozen=True)
class LocalContext:
    """Trusted fixture/transport dependency, never constructed from request JSON."""
    session_reference: str
    policy_revision: int
    cancelled: threading.Event = field(default_factory=threading.Event)


class Budget:
    def __init__(self, context, seconds=5):
        self.context = context
        self.deadline = time.monotonic() + seconds

    def check(self):
        if self.context.cancelled.is_set() or time.monotonic() >= self.deadline:
            raise TimeoutError('Synthetic request interrupted')


class DomainServices(Protocol):
    def execute(self, request, context, budget): ...


class RateLimit(Protocol):
    def admit(self, tenant, actor): ...


class AuditSink(Protocol):
    def append(self, metadata): ...


class RateExceeded(Exception): pass


class LocalRateLimit:
    """Bounded, process-local synthetic admission, not distributed abuse prevention."""
    def __init__(self, limit=60, seconds=60, max_principals=1024):
        if any(type(n) is not int or n < 1 for n in (limit, seconds, max_principals)):
            raise ValueError('Bounded rate policy required')
        self.limit, self.seconds, self.max_principals = limit, seconds, max_principals
        self._entries = {}; self._lock = threading.Lock()

    def admit(self, tenant, actor):
        now = time.monotonic()
        with self._lock:
            self._entries = {key: value for key, value in self._entries.items() if value[0] > now}
            key = (tenant, actor)
            if key not in self._entries:
                if len(self._entries) >= self.max_principals: raise RateExceeded()
                self._entries[key] = (now + self.seconds, 0)
            end, used = self._entries[key]
            if used >= self.limit: raise RateExceeded()
            self._entries[key] = (end, used + 1)


def required_permission(request):
    action = request.requested_action
    resource = request.resource_reference
    if action == 'intake': return 'journey.pilot.start', resource
    if action == 'decision.submit': return 'journey.pilot.propose', resource
    if action == 'work-packet.create': return 'journey.pilot.advance', resource
    if action in ('classification.preserve', 'journey.read'): return 'journey.pilot.read', resource
    if action == 'routing.preview': return 'packet.route_simulate', resource
    if action == 'outbox.prepare': return 'packet.view.command', 'syn-view-command'
    if action in ('assignment.acknowledge', 'handoff.record', 'outcome.record'):
        return 'packet.routing.append', resource
    if action == 'visibility.project':
        audience = request.payload['audience']
        if audience in ('command', 'control', 'governance'):
            return 'packet.view.' + audience, 'syn-view-' + audience
        # Additional exact-packet grant; the domain still independently resolves
        # executive/team ownership from persistence. No caller executive claim.
        return 'packet.view.' + audience, resource
    return 'audit.read', 'syn-audit'


class SyntheticPolicyGate:
    def __init__(self, authority=None, permitted_purposes=(), admitted_surfaces=()):
        self.authority = authority
        self.permitted_purposes = tuple(permitted_purposes)
        self.admitted_surfaces = tuple(admitted_surfaces)

    def verify(self, request, context):
        if type(self.authority) is not SyntheticAuthority or type(context) is not LocalContext:
            raise PermissionError('Trusted local identity required')
        if request.purpose not in self.permitted_purposes or request.source_surface not in self.admitted_surfaces:
            raise PermissionError('Unresolved admission policy')
        ref(context.session_reference); positive_revision(context.policy_revision)
        if request.authentication_state_reference != context.session_reference:
            raise PermissionError('Authentication-state binding mismatch')
        action, resource = required_permission(request)
        session, _ = self.authority.authorize(context.session_reference, request.tenant_reference,
                                              context.policy_revision, action, resource)
        if (session.principal.subject_reference, session.kind) != (request.actor_reference, request.actor_type):
            raise PermissionError('Actor binding mismatch')
        return 'syn-authz-' + fingerprint([request.tenant_reference, request.actor_reference,
            request.requested_action, resource, context.policy_revision, fingerprint(request.__dict__)])


class Gateway:
    """HTTP-equivalent dispatch only. GET envelopes are local arguments, not HTTP headers.

    Explicitly injected dependencies are trusted application code. This is not a
    sandbox against a malicious Python caller. No request can supply dependencies.
    """
    def __init__(self, gate=None, services=None, rate_limit=None, audit_sink=None):
        self.gate, self.services = gate, services
        self.rate_limit, self.audit_sink = rate_limit, audit_sink

    def handle(self, method, path, raw, context=None):
        request = None
        try:
            if type(method) is not str or type(path) is not str or len(method)>8 or len(path)>256:
                raise ValueError('Malformed route')
            request = decode_request(raw)
            action = ROUTES.get((method, path))
            path_resource = None
            for stem, pattern in (('/v1/work-packets/', '/v1/work-packets/{packet_id}'),
                                  ('/v1/journeys/', '/v1/journeys/{journey_id}')):
                if method == 'GET' and path.startswith(stem):
                    path_resource = path[len(stem):];ref(path_resource)
                    action = ROUTES[(method, pattern)]
            if action is None: return self._error(404, 'route_unavailable')
            if action != request.requested_action or (path_resource is not None and path_resource != request.resource_reference):
                raise ValueError('Route binding mismatch')
            if any(item is None for item in (self.gate, self.services, self.rate_limit, self.audit_sink)):
                raise PermissionError('Unconfigured gate')
            if type(context) is not LocalContext: raise PermissionError('Trusted context required')
            budget = Budget(context);budget.check()
            decision = self.gate.verify(request, context);ref(decision)
            self.rate_limit.admit(request.tenant_reference, request.actor_reference)
            audit_ref = 'syn-api-audit-' + fingerprint([request.tenant_reference, request.request_id, decision])
            # Admission audit precedes domain work: sink failure cannot follow a commit.
            # This records an attempt, not a success; domain writes retain their own
            # transactional minimized audit. No rejected bytes or payloads are logged.
            self.audit_sink.append(dict(audit_event_reference=audit_ref,
                request_id=request.request_id, correlation_reference=request.correlation_reference,
                tenant_reference=request.tenant_reference, actor_reference=request.actor_reference,
                action=request.requested_action, authorization_decision_reference=decision,
                policy_revision=context.policy_revision, timestamp=datetime.now(timezone.utc).isoformat(),
                decision='authorized_attempt', schema_version=1))
            budget.check()
            if action == 'health':
                if request.expected_revision != 1: raise ConflictError('Health schema revision mismatch')
                result = {'state': 'inactive'}
            else: result = self.services.execute(request, context, budget)
            result = validate_projection(result)
            # No body, directive, guest details or projection content in the intention.
            connector = request.payload.get('connector_reference', request.source_surface)
            outbox = None
            if (connector in {item.reference for item in CONNECTORS}
                    and result.get('passed', True) is not False and result.get('status') != 'blocked'):
                intention = OutboxIntention(request.tenant_reference, request.request_id,
                    request.correlation_reference, request.actor_reference, connector,
                    result.get('record_reference', 'syn-projection-' + fingerprint(result)), decision, audit_ref)
                intention.validate();outbox = canonical(intention.__dict__)
            response = dict(schema_version=1, request_id=request.request_id,
                correlation_reference=request.correlation_reference, tenant_reference=request.tenant_reference,
                actor_reference=request.actor_reference, actor_type=request.actor_type,
                authentication_state_reference=request.authentication_state_reference,
                data_classification=request.data_classification, purpose=request.purpose,
                idempotency_key=request.idempotency_key, source_surface=request.source_surface,
                timestamp=request.timestamp, requested_action=action,
                authorization_decision_reference=decision, audit_event_reference=audit_ref,
                state='inactive', operational_authorized=False, result=result, inactive_outbox=outbox)
            if len(canonical_bytes(response)) > MAX_RESPONSE_BYTES: raise ValueError('Bounded response required')
            return 200, response
        except RateExceeded: return self._error(429, 'rate_limited')
        except TimeoutError: return self._error(408, 'interrupted')
        except ConflictError: return self._error(409, 'revision_or_idempotency_conflict')
        except PermissionError: return self._error(403, 'denied')
        except (ValueError, TypeError, KeyError, RecursionError): return self._error(400, 'invalid_request')
        except Exception: return self._error(503, 'service_unavailable')

    @staticmethod
    def _error(status, code):
        return status, dict(schema_version=1, state='inactive', operational_authorized=False, error=code)
