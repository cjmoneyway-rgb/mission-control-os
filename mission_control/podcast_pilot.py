"""Opaque inactive synthetic podcast lifecycle. No providers or operational actions."""
from dataclasses import asdict, dataclass, fields

from .department_routing import Contract, DepartmentPacket, Intake, ref, refs, seal
from .json_io import strict_json_loads
from .registry_authorization import positive_revision
from .synthetic_identity import fingerprint

# Public display labels belong in documentation; persisted stages are opaque tokens.
STAGES = tuple('syn-stage-'+str(index).zfill(2) for index in range(1,17))
CLASSIFICATIONS = tuple('syn-class-'+str(index).zfill(2) for index in range(1,17))
ENTRY_CLASSIFICATION = 'syn-entry-class'


@dataclass(frozen=True)
class GuestJourney(Contract):
    tenant_reference: str
    journey_id: str
    guest_reference: str
    intake_reference: str
    original_classification: str = ENTRY_CLASSIFICATION
    revision: int = 1
    state: str = 'inactive'
    schema_revision: int = 1
    content_digest: str = ''

    def validate(self):
        self.common()
        for value in (self.journey_id,self.guest_reference,self.intake_reference): ref(value)
        if self.original_classification != ENTRY_CLASSIFICATION or self.revision != 1:
            raise ValueError('Immutable synthetic entry required')


@dataclass(frozen=True)
class GuestEvent(Contract):
    tenant_reference: str
    journey_reference: str
    event_id: str
    revision: int
    stage_reference: str
    classification: str
    previous_event_reference: str | None
    dependency_references: tuple[str,...]
    evidence_references: tuple[str,...]
    outcome_references: tuple[str,...]
    handoff_references: tuple[str,...]
    rule_reference: str
    rule_revision: int
    rule_digest: str
    approval_reference: str | None
    terminal_reference: str | None = None
    state: str = 'inactive'
    schema_revision: int = 1
    content_digest: str = ''

    def validate(self):
        self.common()
        for value in (self.journey_reference,self.event_id,self.rule_reference): ref(value)
        if self.stage_reference not in STAGES or self.classification != CLASSIFICATIONS[STAGES.index(self.stage_reference)]:
            raise ValueError('Unknown or mismatched deterministic classification')
        for values in (self.dependency_references,self.outcome_references,self.handoff_references): refs(values,False)
        refs(self.evidence_references)
        positive_revision(self.rule_revision)
        if type(self.rule_digest) is not str or len(self.rule_digest)!=64 or any(char not in '0123456789abcdef' for char in self.rule_digest):
            raise ValueError('Exact rule digest required')
        if self.previous_event_reference is not None: ref(self.previous_event_reference)
        if self.previous_event_reference == self.event_id or self.event_id in self.dependency_references:
            raise ValueError('Self dependency forbidden')
        if self.previous_event_reference is not None and self.previous_event_reference not in self.dependency_references:
            raise ValueError('Predecessor dependency required')
        if self.approval_reference is not None: ref(self.approval_reference)
        if self.stage_reference == STAGES[-1]:
            if self.terminal_reference not in ('syn-completed','syn-closed'):
                raise ValueError('Explicit synthetic terminal decision required')
        elif self.terminal_reference is not None:
            raise ValueError('Premature terminal decision forbidden')


def decode_pilot(kind,payload):
    try:
        data = strict_json_loads(payload) if isinstance(payload,str) else dict(payload)
        cls = {'journey':GuestJourney,'event':GuestEvent}[kind]
        if set(data) != {field.name for field in fields(cls)}: raise ValueError('Contract keys')
        for key in ('dependency_references','evidence_references','outcome_references','handoff_references'):
            if key in data:
                if not isinstance(data[key],(list,tuple)): raise ValueError('Contract sequence')
                data[key]=tuple(data[key])
        result=cls(**data);result.validate();return result
    except Exception:
        raise ValueError('Malformed synthetic pilot contract') from None


def classify_event(event):
    event.validate()
    return CLASSIFICATIONS[STAGES.index(event.stage_reference)]


def derive_stage_packets(journey,intake,event,rule,departments,key):
    """Pure inactive proposal only. Trusted transaction verifies policy/evidence."""
    journey.validate();intake.validate();event.validate();rule.validate();ref(key)
    if (journey.tenant_reference != event.tenant_reference or intake.tenant_reference != journey.tenant_reference
            or rule.tenant_reference != journey.tenant_reference or event.journey_reference != journey.journey_id
            or intake.event_id != journey.intake_reference or intake.original_classification != journey.original_classification
            or (rule.rule_id,rule.revision,rule.content_digest,rule.classification) !=
               (event.rule_reference,event.rule_revision,event.rule_digest,classify_event(event))):
        raise ValueError('Synthetic journey/rule binding mismatch')
    if not set(rule.preconditions) <= set(event.evidence_references):
        raise ValueError('Incomplete synthetic evidence')
    if set(rule.escalation_conditions) & set(event.evidence_references):
        raise PermissionError('Separate escalation decision required')
    packets=[]
    for reference,revision,digest,executive in rule.recipients:
        department=departments.get(reference)
        if department is None: raise PermissionError('Unresolved department')
        department.validate()
        if (department.tenant_reference,department.revision,department.content_digest,department.executive_reference) != (journey.tenant_reference,revision,digest,executive):
            raise PermissionError('Stale department binding')
        if event.classification not in department.information_received:
            raise PermissionError('Department classification denied')
        packet_id='syn-packet-'+fingerprint([journey.tenant_reference,intake.event_id,event.event_id,reference])
        packets.append(seal(DepartmentPacket(journey.tenant_reference,packet_id,1,intake.event_id,
            journey.original_classification,event.classification,executive,(reference,),rule.required_action,
            event.dependency_references,'syn-normal',rule.approval_reference or 'syn-unresolved',rule.visibility_references,
            event.outcome_references,event.handoff_references,revision,digest,rule.rule_id,rule.revision,rule.content_digest,key)))
    return tuple(packets)
