"""Sanitized contracts. Validation never grants organizational authority."""
from dataclasses import dataclass
import hashlib
import json
from typing import Protocol
from datetime import datetime, timezone


def text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Expected nonempty text')


def digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class Approval:
    record_id: str
    revision: int
    content_digest: str
    evidence_reference: str

    def validate(self, record_id, revision, payload):
        for value in (self.record_id, self.content_digest, self.evidence_reference):
            text(value)
        if self.evidence_reference.strip().lower() == 'unresolved':
            raise ValueError('Unresolved approval evidence')
        if type(self.revision) is not int or self.revision < 1:
            raise ValueError('Invalid approval revision')
        if (self.record_id, self.revision, self.content_digest) != (record_id, revision, digest(payload)):
            raise ValueError('Approval does not match record revision and content')


@dataclass(frozen=True)
class ApprovalEvidence:
    """Resolved by a trusted authority, never accepted from record input alone."""
    approval: Approval
    valid_from: datetime
    expires_at: datetime
    authorized: bool

    def validate(self, expected):
        if not isinstance(self.approval, Approval) or type(self.approval.revision) is not int:
            raise ValueError('Malformed resolved approval')
        if self.approval != expected or self.authorized is not True:
            raise ValueError('Approval evidence mismatch or denial')
        for timestamp in (self.valid_from, self.expires_at):
            if not isinstance(timestamp, datetime) or timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError('Evidence requires timezone-aware validity dates')
        if not self.valid_from <= datetime.now(timezone.utc) < self.expires_at:
            raise ValueError('Approval evidence is expired or not yet valid')


class ApprovalVerifier(Protocol):
    """Trusted deployment dependency; no operational implementation in Phase 1A."""
    def resolve_approval(self, reference: str) -> ApprovalEvidence | None: ...
    def resolve_reference(self, kind: str, reference: str) -> bool: ...


@dataclass(frozen=True)
class RegistryRecord:
    record_id: str
    revision: int
    department_reference: str | None
    title_reference: str | None = None
    owner_reference: str | None = None
    policy_reference: str | None = None
    state: str = 'draft'
    approval: Approval | None = None

    def payload(self):
        return {k: v for k, v in vars(self).items() if k != 'approval'}

    def validate(self, trusted_evidence: ApprovalVerifier | None = None):
        text(self.record_id)
        if type(self.revision) is not int or self.revision < 1:
            raise ValueError('Invalid revision')
        if self.state not in ('draft', 'inactive', 'active', 'retired'):
            raise ValueError('Invalid registry state')
        refs = (self.department_reference, self.title_reference, self.owner_reference, self.policy_reference)
        for ref in refs:
            if ref is not None:
                text(ref)
        if self.state == 'active':
            if any(ref is None or ref.strip().lower() == 'unresolved' for ref in refs):
                raise ValueError('Unresolved active record')
            if not isinstance(self.approval, Approval):
                raise ValueError('Active record requires approval')
        if self.approval is not None:
            if not isinstance(self.approval, Approval):
                raise ValueError('Malformed approval')
            self.approval.validate(self.record_id, self.revision, self.payload())
            try:
                if trusted_evidence is None:
                    raise ValueError('Approval authority is unavailable')
                evidence = trusted_evidence.resolve_approval(self.approval.evidence_reference)
                if not isinstance(evidence, ApprovalEvidence):
                    raise ValueError('Approval reference could not be resolved')
                evidence.validate(self.approval)
                for kind, reference in zip(('department', 'title', 'owner', 'policy'), refs):
                    if reference is not None and trusted_evidence.resolve_reference(kind, reference) is not True:
                        raise ValueError('Registry reference could not be resolved')
            except Exception:
                raise ValueError('Approval evidence or registry references are unverifiable') from None


@dataclass(frozen=True)
class WorkPacket:
    packet_id: str
    registry_reference: str
    registry_revision: int
    action: str
    state: str = 'inactive'

    def validate(self, registry):
        text(self.packet_id)
        text(self.registry_reference)
        text(self.action)
        if self.state != 'inactive':
            raise ValueError('Phase 1A work packets must remain inactive')
        if self.registry_reference not in registry:
            raise ValueError('Unknown registry reference')
        record = registry[self.registry_reference]
        if not isinstance(record, RegistryRecord) or record.record_id != self.registry_reference:
            raise ValueError('Invalid registry reference target')
        record.validate()
        if type(self.registry_revision) is not int or record.revision != self.registry_revision:
            raise ValueError('Registry revision mismatch')


@dataclass(frozen=True)
class LifecycleEvent:
    event_id: str
    journey_reference: str
    previous_state: str
    next_state: str
    packet: WorkPacket
    active: bool = False


class JourneyHistory:
    """In-memory append-only synthetic history; no integrations or persistence."""
    _transitions = {'new': {'received'}, 'received': {'prepared'}, 'prepared': {'completed'}}

    def __init__(self):
        self._events = ()

    @property
    def events(self):
        return self._events

    def append(self, event, registry):
        if not isinstance(event, LifecycleEvent):
            raise ValueError('Invalid lifecycle event')
        text(event.event_id)
        text(event.journey_reference)
        text(event.previous_state)
        text(event.next_state)
        if event.active is not False:
            raise ValueError('Live lifecycle events are disabled')
        if any(item.event_id == event.event_id for item in self._events):
            raise ValueError('Duplicate event')
        if not isinstance(event.packet, WorkPacket):
            raise ValueError('Invalid work packet')
        event.packet.validate(registry)
        previous = [item for item in self._events if item.journey_reference == event.journey_reference]
        current = previous[-1].next_state if previous else 'new'
        if event.previous_state != current or event.next_state not in self._transitions.get(current, set()):
            raise ValueError('Invalid lifecycle transition')
        self._events += (event,)
