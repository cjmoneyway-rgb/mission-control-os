"""Version-one synthetic surface contracts. No transport or domain persistence."""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from types import MappingProxyType

from .department_routing import decode, ref, refs
from .json_io import strict_json_loads
from .podcast_pilot import decode_pilot
from .registry_authorization import positive_revision
from .synthetic_identity import canonical, canonical_bytes, fingerprint

MAX_REQUEST_BYTES = 65536
MAX_RESPONSE_BYTES = 65536
SURFACES = ('syn-chatgpt', 'syn-command-center', 'syn-dashboard', 'syn-slack',
            'syn-hubspot', 'syn-email', 'syn-calendar', 'syn-documents', 'syn-publishing')
# Paths are logical HTTP-shaped dispatch contracts, not published endpoints.
ROUTES = MappingProxyType({
    ('POST', '/v1/intake'): 'intake',
    ('POST', '/v1/classifications/preserve'): 'classification.preserve',
    ('POST', '/v1/routing/preview'): 'routing.preview',
    ('POST', '/v1/work-packets'): 'work-packet.create',
    ('GET', '/v1/work-packets/{packet_id}'): 'visibility.project',
    ('POST', '/v1/decisions'): 'decision.submit',
    ('POST', '/v1/assignments/acknowledge'): 'assignment.acknowledge',
    ('POST', '/v1/handoffs'): 'handoff.record',
    ('POST', '/v1/outcomes'): 'outcome.record',
    ('GET', '/v1/journeys/{journey_id}'): 'journey.read',
    ('GET', '/v1/visibility'): 'visibility.project',
    ('POST', '/v1/governance/review'): 'governance.review',
    ('POST', '/v1/outbox'): 'outbox.prepare',
    ('GET', '/v1/readiness'): 'readiness.status',
    ('GET', '/health'): 'health',
})
PAYLOAD_KEYS = MappingProxyType({
    'intake': {'journey', 'intake'},
    'classification.preserve': {'original_classification'},
    'routing.preview': {'intake', 'rule_revision'},
    'work-packet.create': {'event_reference', 'proposal_revision'},
    'decision.submit': {'event'},
    'assignment.acknowledge': {'packet', 'acknowledgement_reference'},
    'handoff.record': {'packet', 'handoff_reference'},
    'outcome.record': {'packet', 'outcome_reference'},
    'journey.read': set(),
    'visibility.project': {'audience', 'team_reference'},
    'governance.review': {'output_reference'},
    'outbox.prepare': {'connector_reference', 'record_reference'},
    'readiness.status': set(), 'health': set(),
})
WRITE_ACTIONS = frozenset({'intake', 'work-packet.create', 'decision.submit',
                           'assignment.acknowledge', 'handoff.record', 'outcome.record'})


@dataclass(frozen=True)
class ConnectionRequest:
    request_id: str
    correlation_reference: str
    tenant_reference: str
    actor_reference: str
    actor_type: str
    authentication_state_reference: str
    data_classification: str
    purpose: str
    idempotency_key: str
    schema_version: int
    source_surface: str
    timestamp: str
    requested_action: str
    resource_reference: str
    expected_revision: int
    payload: dict


def decode_request(raw, now=None):
    """Copy a bounded byte envelope; never accept request-supplied authority objects."""
    try:
        if type(raw) is not bytes or len(raw) > MAX_REQUEST_BYTES:
            raise ValueError('Bounded encoded request required')
        data = strict_json_loads(raw.decode('utf-8'))
        if type(data) is not dict or set(data) != set(ConnectionRequest.__dataclass_fields__):
            raise ValueError('Exact envelope required')
        request = ConnectionRequest(**data)
        for name in ('request_id', 'correlation_reference', 'tenant_reference', 'actor_reference',
                     'authentication_state_reference', 'purpose', 'idempotency_key', 'resource_reference'):
            ref(getattr(request, name))
        if request.actor_type not in ('human', 'service') or request.source_surface not in SURFACES:
            raise ValueError('Synthetic source required')
        if request.data_classification != 'syn-synthetic' or type(request.schema_version) is not int or request.schema_version != 1:
            raise ValueError('Synthetic schema required')
        if type(request.expected_revision) is not int or request.expected_revision < 0:
            raise ValueError('Exact expected revision required')
        instant = datetime.fromisoformat(request.timestamp)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError('Aware timestamp required')
        current = now or datetime.now(timezone.utc)
        if abs((current - instant).total_seconds()) > 60:
            raise ValueError('Request freshness required')
        action = request.requested_action
        if action not in PAYLOAD_KEYS or type(request.payload) is not dict or set(request.payload) != PAYLOAD_KEYS[action]:
            raise ValueError('Exact service payload required')
        p = request.payload
        # Reuse Phase 1 decoders, including all content/revision checks.
        if action == 'intake':
            records = [decode_pilot('journey', p['journey']), decode('Intake', p['intake'])]
        elif action == 'decision.submit': records = [decode_pilot('event', p['event'])]
        elif action in ('assignment.acknowledge', 'handoff.record', 'outcome.record'):
            records = [decode('DepartmentPacket', p['packet'])]
        elif action == 'routing.preview': records = [decode('Intake', p['intake'])]
        else: records = []
        for record in records:
            if record.tenant_reference != request.tenant_reference:
                raise ValueError('Tenant mismatch')
        if action == 'outbox.prepare' and p['connector_reference'] not in CONNECTOR_REFERENCES:
            raise ValueError('Unresolved connector')
        for name, value in p.items():
            if name in ('rule_revision', 'proposal_revision'): positive_revision(value)
            elif name == 'audience':
                if value not in ('executive', 'team', 'command', 'control', 'governance'):
                    raise ValueError('Unknown audience')
            elif name == 'team_reference':
                if value is not None: ref(value)
            elif name not in ('journey', 'intake', 'event', 'packet'): ref(value)
        return request
    except Exception:
        raise ValueError('Invalid synthetic connection request') from None


@dataclass(frozen=True)
class Connector:
    reference: str
    enabled: bool = False
    state: str = 'unresolved'

    def validate(self):
        if (type(self) is not Connector or self.reference not in CONNECTOR_REFERENCES
                or self.enabled is not False or self.state != 'unresolved'):
            raise PermissionError('Connector activation unavailable')

    def transmit(self, *_args, **_kwargs):
        from .readiness import require_operational_authorization
        require_operational_authorization()


CONNECTOR_REFERENCES = tuple(value for value in SURFACES if value not in ('syn-command-center', 'syn-dashboard'))
CONNECTORS = tuple(Connector(value) for value in CONNECTOR_REFERENCES)


@dataclass(frozen=True)
class OutboxIntention:
    tenant_reference: str
    request_reference: str
    correlation_reference: str
    actor_reference: str
    connector_reference: str
    record_reference: str
    authorization_decision_reference: str
    audit_event_reference: str
    state: str = 'inactive'
    dataset: str = 'synthetic'
    schema_version: int = 1

    def validate(self):
        for name in self.__dataclass_fields__:
            if name.endswith('_reference'): ref(getattr(self, name))
        if (self.connector_reference not in CONNECTOR_REFERENCES or self.state != 'inactive'
                or self.dataset != 'synthetic' or type(self.schema_version) is not int or self.schema_version != 1):
            raise ValueError('Inactive intention required')


COMMAND_STAGES = ('information', 'intelligence', 'decision', 'assignment', 'execution', 'measurement')


@dataclass(frozen=True)
class CommandCenterStage:
    """Projection schema, not an owner assignment or operational progress assertion."""
    stage: str
    record_type: str
    record_reference: str | None
    evidence_references: tuple[str, ...]
    responsible_role_reference: str | None
    allowed_viewers: tuple[str, ...]
    dependencies: tuple[str, ...]
    decision_required: bool
    next_action_reference: str | None
    outcome_references: tuple[str, ...]
    measurement_reference: str | None
    escalation_state: str = 'unresolved'
    status: str = 'inactive'

    def validate(self):
        if (self.stage not in COMMAND_STAGES or self.status != 'inactive'
                or self.escalation_state != 'unresolved' or type(self.decision_required) is not bool):
            raise ValueError('Inactive command projection required')
        ref(self.record_type)
        for name in ('record_reference', 'responsible_role_reference', 'next_action_reference', 'measurement_reference'):
            if getattr(self, name) is not None: ref(getattr(self, name))
        for name in ('evidence_references', 'allowed_viewers', 'dependencies', 'outcome_references'):
            refs(getattr(self, name), False)


PROJECTION_KEYS = frozenset({'state', 'status', 'journey_reference', 'intake_reference', 'event_reference',
    'revision', 'version', 'packet_references', 'original_classification', 'current_classification',
    'packet_reference', 'source_event_reference', 'executive_reference', 'department_references',
    'audience', 'required_action', 'completed_stage', 'events', 'sequence', 'disposition',
    'synthetic_ready', 'operational_authorized', 'verified_controls', 'passed', 'finding_count',
    'record_reference', 'connector_reference'})
ENUMS = frozenset({'inactive', 'accepted', 'blocked', 'proposed', 'pending', 'completed', 'closed',
                   'executive', 'team', 'command', 'control', 'governance'})


def validate_projection(value):
    """Reference-only response ceiling. Called by the adapter BEFORE commit."""
    def check(item):
        if type(item) is dict:
            if not set(item) <= PROJECTION_KEYS: raise ValueError('Unexpected projection fields')
            for key, child in item.items():
                if key in ('revision','version','completed_stage','verified_controls','finding_count','sequence') and type(child) is not int:
                    raise ValueError('Exact projection integer required')
                if key in ('synthetic_ready','operational_authorized','passed') and type(child) is not bool:
                    raise ValueError('Exact projection boolean required')
                if key in ('packet_references','department_references','events') and type(child) not in (tuple,list):
                    raise ValueError('Projection sequence required')
                if key not in ('revision','version','completed_stage','verified_controls','finding_count','sequence',
                               'synthetic_ready','operational_authorized','passed','packet_references','department_references','events') and type(child) is not str:
                    raise ValueError('Projection token required')
                if key == 'state' and child != 'inactive': raise ValueError('Inactive projection required')
                if key == 'operational_authorized' and child is not False: raise ValueError('No operational authority')
                check(child)
        elif type(item) in (tuple, list):
            for child in item: check(child)
        elif type(item) is str:
            if item not in ENUMS: ref(item)
        elif type(item) is int:
            if item < 0: raise ValueError('Invalid projection revision')
        elif type(item) is not bool: raise ValueError('Unexpected projection value')
    if type(value) is not dict or value.get('state') != 'inactive': raise ValueError('Inactive projection required')
    check(value)
    if len(canonical_bytes(value)) > MAX_RESPONSE_BYTES // 2: raise ValueError('Projection too large')
    return canonical(value)

# Governed Phase 2C read contracts. No new persistence or operational surface.
COMMAND_ITEM_FIELDS = frozenset({'reference','current_stage','original_classification',
    'owning_department_reference','priority','technical_status','dependency_state','risk_state',
    'approval_state','assigned_owner_reference','next_required_action','outcome_evidence_reference',
    'revision','last_authorized_update','history_references'})
ELIGIBILITY_FIELDS = frozenset({'target_reference','requested_action','eligible','blocker_codes',
    'expected_revision','evaluated_at','schema_revision'})
BLOCKER_CODES = frozenset({'unresolved_dependencies','unresolved_approval','stale_revision',
    'authorization_denied','unsupported_action','eligibility_unavailable'})


def _projection_time(value):
    if type(value) is not str or len(value)>40:
        raise ValueError('Bounded aware time required')
    instant=datetime.fromisoformat(value)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError('Aware time required')


def validate_command_center(value):
    if type(value) is not dict or set(value)!={'schema_revision','state','queues'}:
        raise ValueError('Exact governed projection required')
    if type(value['schema_revision']) is not int or value['schema_revision']!=1 or value['state']!='inactive':
        raise ValueError('Inactive versioned projection required')
    queues=value['queues']
    if type(queues) is not list or len(queues)!=6:
        raise ValueError('Six queues required')
    for queue,stage in zip(queues,COMMAND_STAGES):
        if type(queue) is not dict or set(queue)!={'stage','count','blocked_count','items'} or queue['stage']!=stage:
            raise ValueError('Exact ordered queue required')
        items=queue['items']
        if type(items) is not list or len(items)>128 or type(queue['count']) is not int or queue['count']!=len(items):
            raise ValueError('Authorized bounded count required')
        blocked=0
        for item in items:
            if type(item) is not dict or set(item)!=COMMAND_ITEM_FIELDS or item['current_stage']!=stage:
                raise ValueError('Exact minimized item required')
            for key in ('reference','original_classification'):
                ref(item[key])
            for key in ('owning_department_reference','assigned_owner_reference','next_required_action','outcome_evidence_reference'):
                if item[key] is not None:ref(item[key])
            if item['priority'] not in (None,'syn-low','syn-normal','syn-high') or item['technical_status'] not in ('inactive','proposed','accepted','blocked'):
                raise ValueError('Synthetic technical state required')
            if item['dependency_state'] not in ('resolved','unresolved') or item['risk_state'] not in ('unresolved','indicated') or item['approval_state'] not in ('unresolved','synthetic_verified','not_required'):
                raise ValueError('Explicit governed state required')
            if type(item['revision']) is not int or item['revision']<0:raise ValueError('Exact revision required')
            if item['last_authorized_update'] is not None:_projection_time(item['last_authorized_update'])
            if type(item['history_references']) is not list:raise ValueError('History references required')
            refs(tuple(item['history_references']),False)
            blocked+=item['technical_status']=='blocked' or item['dependency_state']=='unresolved' or item['approval_state']=='unresolved'
        if type(queue['blocked_count']) is not int or queue['blocked_count']!=blocked:
            raise ValueError('Exact blocked count required')
    if len(canonical_bytes(value))>MAX_RESPONSE_BYTES//2:raise ValueError('Bounded projection required')
    return canonical(value)


def validate_eligibility(value,request=None):
    if type(value) is not dict or set(value)!=ELIGIBILITY_FIELDS:
        raise ValueError('Exact eligibility required')
    ref(value['target_reference'])
    if value['requested_action'] not in WRITE_ACTIONS or type(value['eligible']) is not bool:
        raise ValueError('Supported synthetic eligibility required')
    if type(value['blocker_codes']) is not list or not set(value['blocker_codes'])<=BLOCKER_CODES:
        raise ValueError('Sanitized blockers required')
    if value['eligible'] != (not value['blocker_codes']):raise ValueError('Eligibility mismatch')
    if type(value['expected_revision']) is not int or value['expected_revision']<0 or type(value['schema_revision']) is not int or value['schema_revision']!=1:
        raise ValueError('Exact eligibility revisions required')
    _projection_time(value['evaluated_at'])
    if abs((datetime.now(timezone.utc)-datetime.fromisoformat(value['evaluated_at'])).total_seconds())>5:
        raise ValueError('Fresh eligibility required')
    if request is not None and (value['target_reference'],value['requested_action'],value['expected_revision'])!=(request.resource_reference,request.requested_action,request.expected_revision):
        raise ValueError('Eligibility binding mismatch')
    return canonical(value)
