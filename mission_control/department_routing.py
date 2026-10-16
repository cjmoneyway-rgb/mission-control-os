"""Inactive synthetic registry/routing contracts. No engine/provider imports or I/O."""
from dataclasses import asdict, dataclass, fields, replace
import re

from .json_io import strict_json_loads
from .registry_authorization import positive_revision
from .synthetic_identity import fingerprint, synthetic_reference

VIEWS = ('executive', 'team', 'command', 'control', 'governance')
CENTRAL_VIEWS = ('syn-view-command', 'syn-view-control', 'syn-view-governance')


def ref(value):
    synthetic_reference(value)
    if not re.fullmatch(r'syn-[a-z0-9][a-z0-9_-]{0,150}', value):
        raise ValueError('Opaque synthetic token required')


def refs(values, nonempty=True):
    if type(values) is not tuple or (nonempty and not values) or len(set(values)) != len(values):
        raise ValueError('Unique immutable synthetic references required')
    for value in values:
        ref(value)


def seal(record):
    return replace(record, content_digest=fingerprint(record.payload()))


class Contract:
    def payload(self):
        return {key: value for key, value in asdict(self).items() if key != 'content_digest'}

    def common(self):
        ref(self.tenant_reference)
        positive_revision(self.revision)
        if self.state != 'inactive' or self.schema_revision != 1 or type(self.schema_revision) is not int:
            raise ValueError('Only inactive synthetic schema revision one is supported')
        if self.content_digest != fingerprint(self.payload()):
            raise ValueError('Exact content digest mismatch')


@dataclass(frozen=True)
class Department(Contract):
    tenant_reference: str
    department_id: str
    revision: int
    canonical_name: str
    aliases: tuple[str, ...]
    executive_reference: str
    team_references: tuple[str, ...]
    mandate: str
    information_received: tuple[str, ...]
    information_produced: tuple[str, ...]
    escalation_reference: str
    visibility_reference: str
    approval_reference: str | None
    state: str = 'inactive'
    schema_revision: int = 1
    content_digest: str = ''

    def validate(self):
        self.common()
        for value in (self.department_id, self.canonical_name, self.executive_reference,
                      self.mandate, self.escalation_reference, self.visibility_reference):
            ref(value)
        for values in (self.aliases, self.team_references):
            refs(values, False)
        for values in (self.information_received, self.information_produced):
            refs(values)
        if self.canonical_name in self.aliases:
            raise ValueError('Canonical and alias collision')
        if self.approval_reference is not None:
            ref(self.approval_reference)


@dataclass(frozen=True)
class Rule(Contract):
    tenant_reference: str
    rule_id: str
    revision: int
    classification: str
    preconditions: tuple[str, ...]
    # Each recipient pins (department ID, revision, digest, responsible executive).
    recipients: tuple[tuple[str, int, str, str], ...]
    visibility_references: tuple[str, ...]
    output_contract: str
    required_action: str
    escalation_conditions: tuple[str, ...]
    policy_reference: str
    policy_revision: int
    approval_reference: str | None
    state: str = 'inactive'
    schema_revision: int = 1
    content_digest: str = ''

    def validate(self):
        self.common()
        for value in (self.rule_id, self.classification, self.required_action, self.policy_reference):
            ref(value)
        positive_revision(self.policy_revision)
        refs(self.preconditions, False)
        refs(self.escalation_conditions, False)
        if self.visibility_references != CENTRAL_VIEWS or self.output_contract != 'syn-department-packet-v1':
            raise ValueError('Required visibility or packet contract missing')
        if type(self.recipients) is not tuple or not self.recipients:
            raise ValueError('Recipients required')
        seen = set()
        for recipient in self.recipients:
            if type(recipient) is not tuple or len(recipient) != 4:
                raise ValueError('Exact recipient revision required')
            department, revision, digest, executive = recipient
            ref(department)
            positive_revision(revision)
            ref(executive)
            if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest) or department in seen:
                raise ValueError('Malformed or duplicate recipient')
            seen.add(department)
        if self.approval_reference is not None:
            ref(self.approval_reference)


@dataclass(frozen=True)
class Intake(Contract):
    tenant_reference: str
    event_id: str
    original_classification: str
    fact_references: tuple[str, ...]
    source_reference: str
    revision: int = 1
    state: str = 'inactive'
    schema_revision: int = 1
    content_digest: str = ''

    def validate(self):
        self.common()
        for value in (self.event_id, self.original_classification, self.source_reference):
            ref(value)
        refs(self.fact_references, False)
        if self.revision != 1:
            raise ValueError('Intake is immutable and enters once')


@dataclass(frozen=True)
class DepartmentPacket(Contract):
    tenant_reference: str
    packet_id: str
    revision: int
    source_event_reference: str
    original_classification: str
    current_classification: str
    executive_reference: str
    recipient_references: tuple[str, ...]
    required_action: str
    dependencies: tuple[str, ...]
    priority: str
    decision_reference: str
    visibility_references: tuple[str, ...]
    outcome_references: tuple[str, ...]
    handoff_references: tuple[str, ...]
    registry_revision: int
    registry_digest: str
    rule_reference: str
    rule_revision: int
    rule_digest: str
    idempotency_reference: str
    state: str = 'inactive'
    schema_revision: int = 1
    content_digest: str = ''

    def validate(self):
        self.common()
        for value in (self.packet_id, self.source_event_reference, self.original_classification,
                      self.current_classification, self.executive_reference, self.required_action,
                      self.decision_reference, self.rule_reference, self.idempotency_reference):
            ref(value)
        refs(self.recipient_references)
        if len(self.recipient_references) != 1 or self.visibility_references != CENTRAL_VIEWS:
            raise ValueError('One executive-scoped department per packet with mandatory oversight')
        for values in (self.dependencies, self.outcome_references, self.handoff_references):
            refs(values, False)
        if self.priority not in ('syn-low', 'syn-normal', 'syn-high'):
            raise ValueError('Unsupported synthetic priority')
        for value in (self.registry_revision, self.rule_revision):
            positive_revision(value)
        for value in (self.registry_digest, self.rule_digest):
            if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
                raise ValueError('Exact referenced digest required')


CLASSES = {cls.__name__: cls for cls in (Department, Rule, Intake, DepartmentPacket)}
TUPLES = {'aliases', 'team_references', 'information_received', 'information_produced',
          'preconditions', 'recipients', 'visibility_references', 'escalation_conditions',
          'fact_references', 'recipient_references', 'dependencies', 'outcome_references', 'handoff_references'}


def decode(kind, payload):
    try:
        data = strict_json_loads(payload) if isinstance(payload, str) else dict(payload)
        cls = CLASSES[kind]
        if set(data) != {field.name for field in fields(cls)}:
            raise ValueError('Unknown or missing contract fields')
        for name in TUPLES & data.keys():
            if not isinstance(data[name], (tuple, list)):
                raise ValueError('Malformed sequence')
            data[name] = tuple(tuple(item) if name == 'recipients' and isinstance(item, (list, tuple)) else item for item in data[name])
        result = cls(**data)
        result.validate()
        return result
    except Exception:
        raise ValueError('Invalid synthetic routing contract') from None


def derive_packets(intake, rule, departments, key):
    """Pure deterministic proposal; storage layer verifies authority and evidence."""
    intake.validate()
    rule.validate()
    ref(key)
    if intake.tenant_reference != rule.tenant_reference or intake.original_classification != rule.classification:
        raise ValueError('Intake and rule mismatch')
    if not set(rule.preconditions) <= set(intake.fact_references):
        raise ValueError('Unmet rule preconditions')
    if set(rule.escalation_conditions) & set(intake.fact_references):
        raise PermissionError('Synthetic escalation requires separate decision')
    packets = []
    for department_id, revision, digest, executive in rule.recipients:
        department = departments.get(department_id)
        if type(department) is not Department:
            raise ValueError('Unresolved department')
        department.validate()
        if (department.tenant_reference, department.revision, department.content_digest, department.executive_reference) != (intake.tenant_reference, revision, digest, executive):
            raise ValueError('Recipient revision mismatch')
        if intake.original_classification not in department.information_received:
            raise ValueError('Department mandate mismatch')
        packet_id = 'syn-packet-' + fingerprint([intake.tenant_reference, intake.event_id, department_id])
        packets.append(seal(DepartmentPacket(intake.tenant_reference, packet_id, 1, intake.event_id,
            intake.original_classification, intake.original_classification, executive, (department_id,),
            rule.required_action, (), 'syn-normal', rule.approval_reference or 'syn-unresolved',
            CENTRAL_VIEWS, (), (), revision, digest, rule.rule_id, rule.revision, rule.content_digest, key)))
    return tuple(packets)
