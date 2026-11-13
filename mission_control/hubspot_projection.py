"""Fixed fictional observations only; no HubSpot client, persistence or domain writes."""
from dataclasses import dataclass, asdict, fields
from datetime import datetime, timezone
from threading import RLock
from types import MappingProxyType

from .department_routing import ref
from .json_io import strict_json_loads
from .synthetic_identity import SyntheticAuthority, fingerprint
from .identity_sessions import ContractGuard

MAX_BYTES = 16384
MAX_ITEMS = 16
MAX_FIXTURES = 128
MAX_REQUESTS = 512


class ProjectionDenied(PermissionError):
    def __init__(self):
        super().__init__('Fictional projection denied')


def fictional(value):
    ref(value)
    if not value.startswith('syn-fictional-') or len(value) > 100:
        raise ProjectionDenied()


def revision(value, zero=False):
    if type(value) is not int or value < (0 if zero else 1) or value > 1000000:
        raise ProjectionDenied()


def instant(value):
    if type(value) is not str or len(value) > 40:
        raise ProjectionDenied()
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset().total_seconds() != 0:
        raise ProjectionDenied()
    return result


def references(value):
    if type(value) is not tuple or len(value) > MAX_ITEMS or len(set(value)) != len(value):
        raise ProjectionDenied()
    for item in value:
        fictional(item)


@dataclass(frozen=True)
class Observation:
    observation_reference: str
    mapping_reference: str
    portal_reference: str
    object_type: str
    object_reference: str
    source_version: int
    source_updated_at: str
    observed_at: str
    verified_at: str
    state: str
    status_references: tuple
    association_references: tuple
    merge_target: str | None = None
    tombstone_reference: str | None = None
    schema_version: int = 1
    dataset: str = 'synthetic'

    def validate(self):
        for value in (self.observation_reference, self.mapping_reference,
                      self.portal_reference, self.object_reference):
            fictional(value)
        if self.object_type not in ('contact', 'company') or self.dataset != 'synthetic':
            raise ProjectionDenied()
        revision(self.source_version)
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ProjectionDenied()
        times = tuple(instant(v) for v in (self.source_updated_at, self.observed_at, self.verified_at))
        if not times[0] <= times[1] <= times[2]:
            raise ProjectionDenied()
        references(self.status_references)
        references(self.association_references)
        if self.state not in ('active', 'merged', 'archived', 'deleted', 'unknown', 'unavailable'):
            raise ProjectionDenied()
        if self.merge_target is not None:
            fictional(self.merge_target)
        if self.tombstone_reference is not None:
            fictional(self.tombstone_reference)
        if (self.state == 'merged') != (self.merge_target is not None):
            raise ProjectionDenied()
        if self.merge_target == self.object_reference:
            raise ProjectionDenied()
        if (self.state in ('merged', 'archived', 'deleted')) != (self.tombstone_reference is not None):
            raise ProjectionDenied()
        if self.state != 'active' and (self.status_references or self.association_references):
            raise ProjectionDenied()

    @property
    def content_digest(self):
        return fingerprint(asdict(self))

    def semantic(self):
        return (self.state, self.status_references, self.association_references,
                self.merge_target, self.tombstone_reference)


def decode_observation(raw):
    """Installation decoder; no runtime upload endpoint or vendor response acceptance."""
    try:
        if type(raw) is not bytes or len(raw) > MAX_BYTES:
            raise ProjectionDenied()
        data = strict_json_loads(raw.decode('utf-8'))
        if type(data) is not dict or set(data) != {f.name for f in fields(Observation)}:
            raise ProjectionDenied()
        for name in ('status_references', 'association_references'):
            if type(data[name]) is not list or len(data[name]) > MAX_ITEMS:
                raise ProjectionDenied()
            data[name] = tuple(data[name])
        record = Observation(**data)
        record.validate()
        return record
    except Exception:
        raise ProjectionDenied() from None


@dataclass(frozen=True)
class Mapping:
    mapping_reference: str
    tenant_reference: str
    portal_reference: str
    object_type: str
    object_reference: str
    purpose_reference: str
    classification_reference: str
    visibility_reference: str
    approved_statuses: tuple = ()
    approved_associations: tuple = ()
    approved_merge_targets: tuple = ()
    freshness_seconds: int = 300

    def validate(self):
        ref(self.tenant_reference)
        for value in (self.mapping_reference, self.portal_reference, self.object_reference,
                      self.purpose_reference, self.classification_reference, self.visibility_reference):
            fictional(value)
        if self.object_type not in ('contact', 'company'):
            raise ProjectionDenied()
        for values in (self.approved_statuses, self.approved_associations, self.approved_merge_targets):
            references(values)
        if type(self.freshness_seconds) is not int or not 1 <= self.freshness_seconds <= 3600:
            raise ProjectionDenied()


@dataclass(frozen=True)
class Projection:
    mapping_reference: str
    portal_reference: str
    object_type: str
    object_reference: str
    purpose_reference: str
    classification_reference: str
    visibility_reference: str
    projection_revision: int
    state: str
    source_version: int | None
    source_updated_at: str | None
    observed_at: str | None
    verified_at: str | None
    status_references: tuple = ()
    association_references: tuple = ()
    merge_target: str | None = None
    tombstone_reference: str | None = None
    observation_digest: str | None = None
    schema_version: int = 1
    dataset: str = 'synthetic'


@dataclass(frozen=True)
class Decision:
    sequence: int
    request_reference: str | None
    correlation_reference: str | None
    mapping_reference: str | None
    source_version: int | None
    projection_revision: int | None
    allowed: bool
    reason: str
    timestamp: str
    schema_version: int = 1


class Journal:
    """Bounded demonstration decisions, not independent durable audit custody."""
    def __init__(self, capacity=2048):
        if type(capacity) is not int or not 1 <= capacity <= 8192:
            raise ProjectionDenied()
        self.capacity = capacity
        self._rows = []

    def append(self, row):
        if type(row) is not Decision or len(self._rows) >= self.capacity:
            raise ProjectionDenied()
        self._rows.append(row)

    def snapshot(self):
        return tuple(self._rows)


class MockProjection:
    """Trusted installation plus guarded technical cache; no MC domain authority."""
    def __init__(self, authority, mappings, fixtures, clock, journal=None):
        try:
            if type(authority) is not SyntheticAuthority or type(authority.contract_guard) is not ContractGuard:
                raise ProjectionDenied()
            if type(mappings) is not tuple or not 1 <= len(mappings) <= MAX_ITEMS:
                raise ProjectionDenied()
            if type(fixtures) is not tuple or not 1 <= len(fixtures) <= MAX_FIXTURES:
                raise ProjectionDenied()
            ms = {}
            for m in mappings:
                if type(m) is not Mapping:
                    raise ProjectionDenied()
                m.validate()
                if m.mapping_reference in ms:
                    raise ProjectionDenied()
                if any((m.tenant_reference, m.portal_reference, m.object_type, m.object_reference) ==
                       (v.tenant_reference, v.portal_reference, v.object_type, v.object_reference) for v in ms.values()):
                    raise ProjectionDenied()
                ms[m.mapping_reference] = m
            fs = {}
            for o in fixtures:
                if type(o) is not Observation:
                    raise ProjectionDenied()
                o.validate()
                m = ms[o.mapping_reference]
                if (o.portal_reference, o.object_type, o.object_reference) != (m.portal_reference, m.object_type, m.object_reference):
                    raise ProjectionDenied()
                if not set(o.status_references) <= set(m.approved_statuses) or not set(o.association_references) <= set(m.approved_associations):
                    raise ProjectionDenied()
                if o.merge_target is not None and o.merge_target not in m.approved_merge_targets:
                    raise ProjectionDenied()
                if o.observation_reference in fs:
                    raise ProjectionDenied()
                fs[o.observation_reference] = o
            self._authority = authority
            self._mappings = MappingProxyType(ms)
            self._fixtures = MappingProxyType(fs)
            self._clock = clock
            self.journal = journal if journal is not None else Journal()
            self._lock = RLock()
            self._current = {}
            self._requests = {}
            self._revoked = set()
            self._closed = False
            self._last_time = None
        except Exception:
            raise ProjectionDenied() from None

    def _now(self):
        now = self._clock()
        if type(now) is not datetime or now.tzinfo is None or now.utcoffset().total_seconds() != 0:
            raise ProjectionDenied()
        if self._last_time is not None and now < self._last_time:
            raise ProjectionDenied()
        self._last_time = now
        return now

    def _audit(self, now, allowed, request=None, correlation=None, mapping=None, source=None, version=None):
        self.journal.append(Decision(len(self.journal.snapshot()) + 1, request, correlation,
            mapping, source, version, allowed, 'allowed' if allowed else 'denied', now.isoformat()))

    def _view(self, m, now):
        current = self._current.get(m.mapping_reference)
        o, version = current if current else (None, 0)
        state = o.state if o else 'unknown'
        if o and state == 'active' and (now - instant(o.source_updated_at)).total_seconds() > m.freshness_seconds:
            state = 'stale'
        active = state == 'active'
        return Projection(m.mapping_reference, m.portal_reference, m.object_type, m.object_reference,
            m.purpose_reference, m.classification_reference, m.visibility_reference, version, state,
            o.source_version if o else None, o.source_updated_at if o else None,
            o.observed_at if o else None, o.verified_at if o else None,
            o.status_references if active else (), o.association_references if active else (),
            o.merge_target if o else None, o.tombstone_reference if o else None,
            o.content_digest if o else None)

    def operate(self, session, policy_revision, tenant, mapping, portal, request, correlation,
                *, fixture=None, expected_revision=None):
        """Read or explicitly replay an installed fixture under an exact read grant."""
        with self._lock:
            now = None
            try:
                if self._closed:
                    raise ProjectionDenied()
                now = self._now()
                for v in (session, tenant, request, correlation):
                    ref(v)
                fictional(mapping)
                fictional(portal)
                revision(policy_revision)
                m = self._mappings[mapping]
                if m.tenant_reference != tenant or m.portal_reference != portal or mapping in self._revoked:
                    raise ProjectionDenied()
                guard = self._authority.contract_guard
                if type(guard) is not ContractGuard:
                    raise ProjectionDenied()
                with guard.lease(session, tenant, policy_revision):
                    self._authority.authorize(session, tenant, policy_revision, 'registry.read', mapping)
                    current = self._current.get(mapping)
                    old, version = current if current else (None, 0)
                    if fixture is None:
                        if expected_revision is not None:
                            raise ProjectionDenied()
                        result = self._view(m, now)
                        signature = (tenant, portal, m.object_type, m.object_reference, None, correlation)
                        if request in self._requests:
                            previous, previous_result = self._requests[request]
                            if previous != signature or previous_result != result:
                                raise ProjectionDenied()
                            result = previous_result
                        elif len(self._requests) >= MAX_REQUESTS:
                            raise ProjectionDenied()
                        self._audit(now, True, request, correlation, mapping,
                                    old.source_version if old else None, version)
                        self._requests[request] = (signature, result)
                        return result
                    fictional(fixture)
                    revision(expected_revision, True)
                    o = self._fixtures[fixture]
                    if o.mapping_reference != mapping or instant(o.verified_at) > now:
                        raise ProjectionDenied()
                    if (now - instant(o.source_updated_at)).total_seconds() > m.freshness_seconds:
                        raise ProjectionDenied()
                    key = request
                    signature = (tenant, portal, m.object_type, m.object_reference,
                                 fixture, o.content_digest, expected_revision, correlation)
                    if key in self._requests:
                        previous, result = self._requests[key]
                        if previous != signature or not current or old != o or result.projection_revision != version:
                            raise ProjectionDenied()
                        self._audit(now, True, request, correlation, mapping, o.source_version, version)
                        return result
                    if expected_revision != version or len(self._requests) >= MAX_REQUESTS:
                        raise ProjectionDenied()
                    if old == o:
                        result = self._view(m, now)
                        self._audit(now, True, request, correlation, mapping, o.source_version, version)
                        self._requests[key] = (signature, result)
                        return result
                    if old:
                        if old.state in ('merged', 'archived', 'deleted'):
                            raise ProjectionDenied()
                        if o.source_version <= old.source_version or instant(o.source_updated_at) < instant(old.source_updated_at):
                            raise ProjectionDenied()
                        if o.semantic() == old.semantic():
                            raise ProjectionDenied()
                    # Construct immutable result before audit; publish only after required audit succeeds.
                    active = o.state == 'active'
                    result = Projection(m.mapping_reference, m.portal_reference, m.object_type, m.object_reference,
                        m.purpose_reference, m.classification_reference, m.visibility_reference, version + 1,
                        o.state, o.source_version, o.source_updated_at, o.observed_at, o.verified_at,
                        o.status_references if active else (), o.association_references if active else (),
                        o.merge_target, o.tombstone_reference, o.content_digest)
                    self._audit(now, True, request, correlation, mapping, o.source_version, version + 1)
                    self._current[mapping] = (o, version + 1)
                    self._requests[key] = (signature, result)
                    return result
            except Exception:
                if now is not None:
                    try:
                        # Rejected values, identities and session material never enter denied rows.
                        self._audit(now, False)
                    except Exception:
                        pass
                raise ProjectionDenied() from None

    def revoke_source(self, session, policy_revision, tenant, mapping, portal, request, correlation):
        """Trusted local fixture withdrawal; cannot restore access or grant domain authority."""
        with self._lock:
            self.operate(session, policy_revision, tenant, mapping, portal, request, correlation)
            self._revoked.add(mapping)

    def close(self):
        with self._lock:
            self._current.clear()
            self._requests.clear()
            self._revoked.clear()
            self._mappings = MappingProxyType({})
            self._fixtures = MappingProxyType({})
            self._closed = True
