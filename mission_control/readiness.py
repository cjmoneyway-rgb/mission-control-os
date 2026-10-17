"""Phase 1E synthetic readiness gates; never an operational launch authority."""
from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime, timezone
import re

from .department_routing import ref, refs
from .json_io import strict_json_loads
from .registry_authorization import positive_revision
from .synthetic_identity import fingerprint


READINESS_CONTROLS = (
    'provider-contract',
    'protected-storage',
    'identity-mfa',
    'authorization-separation',
    'approval-authority',
    'key-custody',
    'audit-observability',
    'backup-recovery',
    'retention-legal-hold',
    'incident-response',
    'data-admission',
    'pilot-operating-plan',
)


def _aware(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('Timezone-aware timestamp required')


def _digest(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value):
        raise ValueError('Exact SHA-256 digest required')


def _commit(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{40}', value):
        raise ValueError('Exact Git commit required')


def _sealed(record):
    return replace(record, content_digest=fingerprint(record.payload()))


class ReadinessContract:
    def payload(self):
        return {key: value for key, value in asdict(self).items() if key != 'content_digest'}

    def common(self):
        ref(self.tenant_reference)
        positive_revision(self.revision)
        if self.dataset != 'synthetic' or self.state != 'inactive' or self.schema_revision != 1:
            raise ValueError('Phase 1E contracts are synthetic and inactive only')
        if type(self.schema_revision) is not int or self.content_digest != fingerprint(self.payload()):
            raise ValueError('Readiness content digest mismatch')


@dataclass(frozen=True)
class ControlEvidence(ReadinessContract):
    tenant_reference: str
    evidence_id: str
    revision: int
    control: str
    artifact_reference: str
    artifact_digest: str
    issuer_reference: str
    reviewer_reference: str
    valid_from: datetime
    expires_at: datetime
    state: str = 'inactive'
    dataset: str = 'synthetic'
    schema_revision: int = 1
    content_digest: str = ''

    def validate(self, at=None):
        self.common()
        for value in (self.evidence_id, self.artifact_reference,
                      self.issuer_reference, self.reviewer_reference):
            ref(value)
        if self.control not in READINESS_CONTROLS:
            raise ValueError('Unknown readiness control')
        _digest(self.artifact_digest)
        _aware(self.valid_from)
        _aware(self.expires_at)
        if self.issuer_reference == self.reviewer_reference:
            raise ValueError('Independent evidence review required')
        instant = at or datetime.now(timezone.utc)
        _aware(instant)
        if not self.valid_from <= instant < self.expires_at:
            raise ValueError('Readiness evidence is not currently valid')


@dataclass(frozen=True)
class ReadinessPackage(ReadinessContract):
    tenant_reference: str
    package_id: str
    revision: int
    base_commit: str
    owner_reference: str
    reviewer_reference: str
    evidence_bindings: tuple[tuple[str, str, int, str], ...]
    state: str = 'inactive'
    dataset: str = 'synthetic'
    schema_revision: int = 1
    content_digest: str = ''

    def validate(self):
        self.common()
        for value in (self.package_id, self.owner_reference, self.reviewer_reference):
            ref(value)
        _commit(self.base_commit)
        if self.owner_reference == self.reviewer_reference:
            raise ValueError('Independent package review required')
        if type(self.evidence_bindings) is not tuple or len(self.evidence_bindings) != len(READINESS_CONTROLS):
            raise ValueError('Complete readiness evidence required')
        controls = []
        evidence_ids = []
        for binding in self.evidence_bindings:
            if type(binding) is not tuple or len(binding) != 4:
                raise ValueError('Malformed readiness evidence binding')
            control, evidence_id, revision, digest = binding
            if control not in READINESS_CONTROLS:
                raise ValueError('Unknown readiness control binding')
            ref(evidence_id)
            positive_revision(revision)
            _digest(digest)
            controls.append(control)
            evidence_ids.append(evidence_id)
        if set(controls) != set(READINESS_CONTROLS) or len(set(controls)) != len(controls):
            raise ValueError('Each readiness control must be bound exactly once')
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError('Readiness evidence cannot be reused across controls')


@dataclass(frozen=True)
class PilotAuthorizationPlan(ReadinessContract):
    tenant_reference: str
    plan_id: str
    revision: int
    readiness_package_id: str
    readiness_package_revision: int
    readiness_package_digest: str
    journey_reference: str
    participant_references: tuple[str, ...]
    permitted_actions: tuple[str, ...]
    admitted_field_references: tuple[str, ...]
    stop_conditions: tuple[str, ...]
    rollback_owner_reference: str
    starts_at: datetime
    ends_at: datetime
    authorization_reference: None = None
    state: str = 'inactive'
    dataset: str = 'synthetic'
    schema_revision: int = 1
    content_digest: str = ''

    def validate(self):
        self.common()
        for value in (self.plan_id, self.readiness_package_id, self.journey_reference,
                      self.rollback_owner_reference):
            ref(value)
        positive_revision(self.readiness_package_revision)
        _digest(self.readiness_package_digest)
        for values in (self.participant_references, self.permitted_actions,
                       self.admitted_field_references, self.stop_conditions):
            refs(values)
        _aware(self.starts_at)
        _aware(self.ends_at)
        if self.starts_at >= self.ends_at:
            raise ValueError('Pilot authorization window is invalid')
        if self.authorization_reference is not None:
            raise ValueError('Operational authorization is outside Phase 1E')


@dataclass(frozen=True)
class ReadinessAssessment:
    package_id: str
    package_revision: int
    package_digest: str
    verified_controls: int
    synthetic_ready: bool
    operational_authorized: bool = False
    reason_code: str = 'separate_operational_authorization_required'


def assess_readiness(package, evidence, at=None):
    """Verify the complete synthetic evidence graph without granting launch authority."""
    try:
        if not isinstance(package, ReadinessPackage):
            raise ValueError('Malformed readiness package')
        package.validate()
        if not isinstance(evidence, (tuple, list)):
            raise ValueError('Malformed readiness evidence')
        by_id = {}
        for item in evidence:
            if not isinstance(item, ControlEvidence) or item.evidence_id in by_id:
                raise ValueError('Duplicate or malformed readiness evidence')
            item.validate(at)
            by_id[item.evidence_id] = item
        for control, evidence_id, revision, digest in package.evidence_bindings:
            item = by_id.get(evidence_id)
            if item is None or (item.tenant_reference, item.control, item.revision, item.content_digest) != (
                    package.tenant_reference, control, revision, digest):
                raise ValueError('Readiness evidence binding mismatch')
        if len(by_id) != len(package.evidence_bindings):
            raise ValueError('Unbound readiness evidence')
        return ReadinessAssessment(package.package_id, package.revision, package.content_digest,
                                   len(package.evidence_bindings), True)
    except Exception:
        raise ValueError('Readiness evidence could not be verified') from None


def assess_pilot_plan(plan, package, evidence, at=None):
    """Validate a proposed inactive plan; never return operational authorization."""
    try:
        if not isinstance(plan, PilotAuthorizationPlan):
            raise ValueError('Malformed pilot plan')
        plan.validate()
        assessment = assess_readiness(package, evidence, at)
        if (plan.tenant_reference, plan.readiness_package_id,
                plan.readiness_package_revision, plan.readiness_package_digest) != (
                package.tenant_reference, package.package_id,
                package.revision, package.content_digest):
            raise ValueError('Pilot plan is not bound to the readiness package')
        return assessment
    except Exception:
        raise ValueError('Pilot authorization plan could not be verified') from None


def require_operational_authorization(*_args, **_kwargs):
    """Fail closed until a separately reviewed production authority is implemented."""
    raise PermissionError('Operational pilot authorization is not implemented')


CLASSES = {'evidence': ControlEvidence, 'package': ReadinessPackage,
           'pilot-plan': PilotAuthorizationPlan}
TUPLES = {'evidence_bindings', 'participant_references', 'permitted_actions',
          'admitted_field_references', 'stop_conditions'}
TIMES = {'valid_from', 'expires_at', 'starts_at', 'ends_at'}


def decode_readiness(kind, payload):
    try:
        data = strict_json_loads(payload) if isinstance(payload, str) else dict(payload)
        cls = CLASSES[kind]
        if set(data) != {field.name for field in fields(cls)}:
            raise ValueError('Unknown or missing readiness fields')
        for name in TUPLES & data.keys():
            if not isinstance(data[name], (tuple, list)):
                raise ValueError('Malformed readiness sequence')
            data[name] = tuple(tuple(item) if name == 'evidence_bindings' and isinstance(item, (tuple, list))
                               else item for item in data[name])
        for name in TIMES & data.keys():
            if isinstance(data[name], str):
                data[name] = datetime.fromisoformat(data[name])
        result = cls(**data)
        result.validate()
        return result
    except Exception:
        raise ValueError('Invalid synthetic readiness contract') from None


seal_readiness = _sealed
