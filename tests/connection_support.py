"""Opaque gateway fixtures only; no operational adapter, credentials or legacy log."""
from datetime import datetime, timezone
import json
import threading

from mission_control.connection_gateway import Gateway, LocalContext, LocalRateLimit, SyntheticPolicyGate
from mission_control.connection_contracts import SURFACES
from tests.pilot_support import TENANT, pilot_authority
from tests.synthetic_postgres_support import session_ref


class MemoryAudit:
    def __init__(self): self.rows = []; self.lock = threading.Lock()
    def append(self, value):
        with self.lock:
            if len(self.rows) >= 1024: raise PermissionError('Synthetic audit capacity reached')
            self.rows.append(dict(value))


class RecordingServices:
    """A test double, not another registry or simulated persistence implementation."""
    def __init__(self): self.calls = []; self.result = {'state': 'inactive'}
    def execute(self, request, context, budget):
        self.calls.append(request);budget.check();return self.result


def envelope(action='health', resource='syn-system', payload=None, role='audit_reviewer', tenant=TENANT,
             correlation='syn-pilot-journey-1', revision=1, **changes):
    reference = session_ref(role, tenant)
    data = dict(request_id='syn-request-1', correlation_reference=correlation,
        tenant_reference=tenant, actor_reference='syn-'+role+'-'+tenant, actor_type='human',
        authentication_state_reference=reference, data_classification='syn-synthetic',
        purpose='syn-technical-review', idempotency_key='syn-key-1', schema_version=1,
        source_surface='syn-dashboard', timestamp=datetime.now(timezone.utc).isoformat(),
        requested_action=action, resource_reference=resource, expected_revision=revision,
        payload=payload or {})
    data.update(changes)
    return data


def encoded(data): return json.dumps(data, allow_nan=False).encode()


def gateway_fixture(authority=None, services=None):
    authority = authority or pilot_authority()[0]
    services = services or RecordingServices();audit = MemoryAudit()
    return Gateway(SyntheticPolicyGate(authority, ('syn-technical-review',), SURFACES), services, LocalRateLimit(1000), audit), services, audit


def context(role='audit_reviewer', tenant=TENANT): return LocalContext(session_ref(role,tenant),1)
