"""Inactive persistence contracts for the existing system, without a storage adapter."""
from dataclasses import asdict, dataclass
import re
from typing import ContextManager, Protocol

from .contracts import (ApprovalEvidence, ApprovalVerifier, LifecycleEvent,
                        RegistryRecord, WorkPacket, digest, text)
from .registry_authorization import positive_revision


def content_hash(value):
    if not isinstance(value, str) or re.fullmatch(r'[0-9a-f]{64}', value) is None:
        raise ValueError('Expected a SHA-256 content digest')


@dataclass(frozen=True)
class RegistryRevision:
    tenant_reference: str
    record: RegistryRecord
    previous_revision: int
    content_digest: str
    dataset: str = 'synthetic'
    schema_revision: int = 1

    def validate(self, verifier: ApprovalVerifier | None = None):
        text(self.tenant_reference)
        if self.dataset != 'synthetic' or type(self.schema_revision) is not int or self.schema_revision != 1:
            raise ValueError('Only synthetic schema revision 1 is enabled')
        if not isinstance(self.record, RegistryRecord) or self.record.state not in ('draft', 'inactive'):
            raise ValueError('Operational registry states are disabled')
        self.record.validate(verifier)
        if type(self.previous_revision) is not int or self.previous_revision != self.record.revision - 1:
            raise ValueError('Noncontiguous registry revision')
        content_hash(self.content_digest)
        if self.content_digest != digest(self.record.payload()):
            raise ValueError('Registry content digest mismatch')


def validate_registry_append(candidate: RegistryRevision, current: RegistryRevision | None,
                             verifier: ApprovalVerifier | None = None):
    candidate.validate(verifier)
    if current is not None:
        current.validate(verifier)
        if (candidate.tenant_reference != current.tenant_reference or
                candidate.record.record_id != current.record.record_id):
            raise ConflictError('Registry head scope mismatch')
    expected = 0 if current is None else current.record.revision
    if candidate.previous_revision != expected:
        raise ConflictError('Registry head compare-and-swap conflict')


@dataclass(frozen=True)
class PacketRevision:
    tenant_reference: str
    revision: int
    previous_revision: int
    packet: WorkPacket
    source_reference: str
    purpose_reference: str
    policy_reference: str
    dataset: str = 'synthetic'
    schema_revision: int = 1

    def validate(self, registry: RegistryRevision):
        positive_revision(self.revision)
        for value in (self.tenant_reference, self.source_reference,
                      self.purpose_reference, self.policy_reference):
            text(value)
        if (self.dataset != 'synthetic' or type(self.schema_revision) is not int or self.schema_revision != 1
                or type(self.previous_revision) is not int or self.previous_revision != self.revision - 1):
            raise ValueError('Invalid packet revision or dataset')
        if not isinstance(registry, RegistryRevision):
            raise ValueError('Missing exact registry revision')
        registry.validate()
        if registry.tenant_reference != self.tenant_reference:
            raise ValueError('Cross-tenant packet reference')
        if not isinstance(self.packet, WorkPacket):
            raise ValueError('Malformed packet')
        self.packet.validate({registry.record.record_id: registry.record})


@dataclass(frozen=True)
class JournalEvent:
    tenant_reference: str
    sequence: int
    event: LifecycleEvent
    previous_digest: str | None = None
    packet_revision: int = 1
    dataset: str = 'synthetic'
    schema_revision: int = 1

    def validate(self, packet: PacketRevision, registry: RegistryRevision):
        text(self.tenant_reference)
        positive_revision(self.sequence)
        if (self.dataset != 'synthetic' or type(self.schema_revision) is not int
                or self.schema_revision != 1 or not isinstance(self.event, LifecycleEvent)):
            raise ValueError('Synthetic lifecycle event required')
        if self.event.active is not False or not isinstance(packet, PacketRevision):
            raise ValueError('Active lifecycle processing is disabled')
        packet.validate(registry)
        positive_revision(self.packet_revision)
        if self.packet_revision != packet.revision:
            raise ValueError('Event must pin an exact packet revision')
        if self.tenant_reference != packet.tenant_reference or self.event.packet != packet.packet:
            raise ValueError('Packet/tenant reference mismatch')
        for value in (self.event.event_id, self.event.journey_reference,
                      self.event.previous_state, self.event.next_state):
            text(value)
        if self.sequence == 1:
            if self.previous_digest is not None:
                raise ValueError('First event cannot reference a predecessor')
        else:
            content_hash(self.previous_digest)

    @property
    def content_digest(self):
        return digest(asdict(self))


class ConflictError(ValueError):
    """Stale revision, conflicting idempotency key, or invalid transition."""


def validate_event_append(candidate: JournalEvent, previous: JournalEvent | None,
                          duplicate: JournalEvent | None, packet: PacketRevision,
                          registry: RegistryRevision) -> str:
    """Pure check; adapters MUST lock/read/check/write together in one transaction.

    Exact retries are acknowledged, never re-appended. Duplicate lookup and head
    reads must be tenant-scoped. This function does not provide durable storage.
    """
    candidate.validate(packet, registry)
    if duplicate is not None:
        if (type(duplicate) is not JournalEvent or
                duplicate.tenant_reference != candidate.tenant_reference or
                duplicate.event.event_id != candidate.event.event_id or
                duplicate.content_digest != candidate.content_digest):
            raise ConflictError('Idempotency key collision')
        return 'duplicate'
    expected_sequence = 1 if previous is None else previous.sequence + 1
    expected_digest = None if previous is None else previous.content_digest
    expected_state = 'new' if previous is None else previous.event.next_state
    if previous is not None and (previous.tenant_reference != candidate.tenant_reference or
                                previous.event.journey_reference != candidate.event.journey_reference):
        raise ConflictError('Cross-tenant or cross-journey predecessor')
    transitions = {'new': 'received', 'received': 'prepared', 'prepared': 'completed'}
    if (candidate.sequence != expected_sequence or candidate.previous_digest != expected_digest or
            candidate.event.previous_state != expected_state or
            transitions.get(expected_state) != candidate.event.next_state):
        raise ConflictError('Stale sequence, predecessor, or invalid transition')
    return 'append'


@dataclass(frozen=True)
class IdempotencyReceipt:
    tenant_reference: str
    operation: str
    key: str
    payload_digest: str
    result_reference: str
    result_revision: int

    def validate(self):
        for value in (self.tenant_reference, self.key, self.result_reference):
            text(value)
        if self.operation not in ('registry.append_draft', 'packet.append_inactive', 'journey.append_inactive'):
            raise ValueError('Unsupported idempotent operation')
        content_hash(self.payload_digest)
        positive_revision(self.result_revision)


class RegistryTransaction(Protocol):
    """Tenant-scoped unit of work. Exit without explicit commit MUST roll back.

    Reads and writes MUST enforce authenticated policy inside the transaction;
    Python dataclasses or an earlier AccessDecision are not authorization tokens.
    Compare-and-swap conflicts MUST roll back; unique constraints arbitrate races.
    """
    def get_receipt(self, operation: str, key: str) -> IdempotencyReceipt | None: ...
    def append_receipt(self, receipt: IdempotencyReceipt) -> None: ...
    def get_registry(self, record_reference: str, revision: int) -> RegistryRevision | None: ...
    def append_registry(self, revision: RegistryRevision, expected_revision: int) -> None: ...
    def append_packet(self, packet: PacketRevision, expected_revision: int) -> None: ...
    def get_event(self, event_reference: str) -> JournalEvent | None: ...
    def get_journey_head(self, journey_reference: str) -> JournalEvent | None: ...
    def append_event(self, event: JournalEvent, expected_sequence: int) -> None: ...
    def resolve_approval(self, reference: str) -> ApprovalEvidence | None: ...
    def commit(self) -> None: ...


class ProtectedRegistryStore(Protocol):
    """No implementation or connection is shipped; factory is tenant-scoped."""
    def transaction(self, tenant_reference: str, session_reference: str,
                    policy_revision: int) -> ContextManager[RegistryTransaction]: ...
