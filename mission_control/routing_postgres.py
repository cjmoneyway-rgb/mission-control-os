"""Opt-in Phase 1C extension of the existing synthetic store. No live router."""
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import json

from .department_routing import (CENTRAL_VIEWS, Department, DepartmentPacket, Intake, Rule,
                                 decode, derive_packets, ref, seal)
from .registry_authorization import current_interval, positive_revision
from .registry_persistence import ConflictError
from .synthetic_identity import SyntheticAuthority, SyntheticEvidenceCustody, canonical, fingerprint
from .synthetic_postgres import (ROOT, LocalSyntheticStore, SyntheticTransaction, _query,
                                 apply_local_migration, transactional_operation)

SQL_PATH = ROOT / 'migrations/postgresql/0002_department_routing.sql'
MIGRATION_ID = 'syn-postgresql-0002'
KINDS = {'department': ('Department', 'department_id'), 'rule': ('Rule', 'rule_id'),
         'intake': ('Intake', 'event_id'), 'packet': ('DepartmentPacket', 'packet_id')}
COLUMNS = {
    'routing_records': 'kind reference revision previous_revision content_digest payload state actor_reference policy_revision created_at',
    'routing_heads': 'kind reference revision',
    'routing_names': 'name department_reference department_kind first_revision',
    'routing_references': 'kind reference parent_reference actor_reference policy_revision',
    'routing_links': 'packet_reference packet_revision packet_kind department_reference department_revision department_digest department_kind rule_reference rule_revision rule_digest rule_kind intake_reference intake_revision intake_kind',
    'routing_evidence': 'reference kind record_reference record_revision content_digest grantor_reference policy_revision valid_from expires_at proof',
    'routing_revocations': 'reference actor_reference created_at',
    'routing_events': 'intake_reference intake_kind intake_revision sequence previous_sequence previous_digest content_digest payload state',
    'routing_journey_heads': 'intake_reference sequence',
    'routing_receipts': 'operation key payload_digest result',
}
JSON_COLUMNS = {'payload', 'proof', 'result'}


def apply_routing_migration(factory, authority=None, session=None, tenant=None, revision=1):
    """Explicit approved disposable DB only; shares baseline migration lock/ledger."""
    if not isinstance(authority, SyntheticAuthority):
        raise PermissionError('Synthetic migration authority required')
    authority.authorize(session, tenant, revision, 'schema.migrate', 'syn-schema')
    apply_local_migration(factory, authority, session, tenant, revision)
    connection = factory()
    try:
        _query(connection, 'BEGIN')
        _query(connection, 'SELECT pg_advisory_xact_lock(%s)', (731843291,))
        checksum = fingerprint(SQL_PATH.read_text())
        rows, _ = _query(connection, 'SELECT checksum FROM mc_syn.schema_migrations WHERE tenant_reference=%s AND migration_id=%s', ('syn-system', MIGRATION_ID))
        if rows:
            if rows[0]['checksum'] != checksum:
                raise ConflictError('Routing migration checksum mismatch')
            connection.rollback()
            return 'already_applied'
        with connection.cursor() as cursor:
            cursor.execute(SQL_PATH.read_text())
        _query(connection, 'INSERT INTO mc_syn.schema_migrations (tenant_reference,migration_id,checksum,applied_at,dataset) VALUES (%s,%s,%s,%s,%s)',
               ('syn-system', MIGRATION_ID, checksum, datetime.now(timezone.utc), 'synthetic'))
        authority.authorize(session, tenant, revision, 'schema.migrate', 'syn-schema')
        connection.commit()
        return 'applied'
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


class RoutingStore(LocalSyntheticStore):
    def transaction_type(self):
        return RoutingTransaction


class RoutingTransaction(SyntheticTransaction):
    def __init__(self, *args):
        super().__init__(*args)
        self.evidence_checks = []

    def recheck(self):
        # Recheck evidence and issuing identity on clean exit as well as at routing.
        requested = self.commit_requested
        self.commit_requested = False
        try:
            for kind, record in self.evidence_checks:
                self._verify_evidence(kind, record, remember=False)
        finally:
            self.commit_requested = requested
        super().recheck()

    def _rows(self, table, **keys):
        self._open()
        if table not in COLUMNS or not set(keys) <= set(COLUMNS[table].split()):
            raise ValueError('Unknown routing selector')
        clauses = ['tenant_reference=%s'] + [key+'=%s' for key in keys]
        return _query(self.connection, 'SELECT * FROM mc_syn.'+table+' WHERE '+' AND '.join(clauses), (self.tenant, *keys.values()))[0]

    def _put(self, table, **values):
        self._open()
        if table not in COLUMNS or set(values) != set(COLUMNS[table].split()):
            raise ValueError('Invalid routing storage row')
        row = {'tenant_reference': self.tenant, **values, 'dataset': 'synthetic'}
        markers = ['%s::jsonb' if key in JSON_COLUMNS else '%s' for key in row]
        parameters = [json.dumps(canonical(value), allow_nan=False) if key in JSON_COLUMNS else value for key, value in row.items()]
        _query(self.connection, 'INSERT INTO mc_syn.'+table+' ('+','.join(row)+') VALUES ('+','.join(markers)+')', tuple(parameters))

    def _head(self, kind, reference):
        rows = self._rows('routing_heads', kind=kind, reference=reference)
        return rows[0]['revision'] if rows else 0

    def _cas_head(self, kind, reference, expected, revision):
        if expected == 0:
            _, count = _query(self.connection, 'INSERT INTO mc_syn.routing_heads (tenant_reference,kind,reference,revision,dataset) VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING', (self.tenant, kind, reference, revision, 'synthetic'))
        else:
            _, count = _query(self.connection, 'UPDATE mc_syn.routing_heads SET revision=%s WHERE tenant_reference=%s AND kind=%s AND reference=%s AND revision=%s', (revision, self.tenant, kind, reference, expected))
        if count != 1:
            raise ConflictError('Routing revision conflict')

    def _get(self, kind, reference, revision, latest=False):
        ref(reference)
        positive_revision(revision)
        if kind not in KINDS:
            raise ValueError('Unknown routing contract kind')
        rows = self._rows('routing_records', kind=kind, reference=reference, revision=revision)
        if not rows or (latest and self._head(kind, reference) != revision):
            raise PermissionError('Missing or stale synthetic revision')
        record = decode(KINDS[kind][0], rows[0]['payload'])
        if (record.tenant_reference, getattr(record, KINDS[kind][1]), record.revision, record.content_digest) != (self.tenant, reference, revision, rows[0]['content_digest']):
            raise ValueError('Routing row integrity mismatch')
        return record

    def _reference(self, kind, reference):
        ref(reference)
        rows = self._rows('routing_references', kind=kind, reference=reference)
        if not rows:
            raise PermissionError('Unresolved synthetic reference')
        return rows[0]

    @transactional_operation
    def register_reference(self, kind, reference, parent_reference=None):
        ref(reference)
        session, _ = self._auth('policy.reference.append', reference)
        if kind in ('executive', 'team'):
            ref(parent_reference)
            if kind == 'executive':
                if not self._select('subjects', subject_reference=parent_reference):
                    raise PermissionError('Executive subject is unresolved')
            else:
                self._reference('executive', parent_reference)
        elif parent_reference is not None:
            raise ValueError('Unsupported synthetic reference parent')
        self._put('routing_references', kind=kind, reference=reference, parent_reference=parent_reference,
                  actor_reference=session.principal.subject_reference, policy_revision=self.revision)
        self._audit('policy.reference.append', reference, session)

    def _record(self, kind, record, expected, action):
        if type(record) is not {'department': Department, 'rule': Rule, 'packet': DepartmentPacket, 'intake': Intake}[kind]:
            raise ValueError('Wrong routing contract type')
        record.validate()
        reference = getattr(record, KINDS[kind][1])
        session, _ = self._auth(action, reference)
        if type(expected) is not int or expected < 0 or record.tenant_reference != self.tenant or record.revision != expected+1:
            raise ConflictError('Routing tenant or revision mismatch')
        self._put('routing_records', kind=kind, reference=reference, revision=record.revision,
                  previous_revision=expected or None, content_digest=record.content_digest, payload=asdict(record),
                  state='inactive', actor_reference=session.principal.subject_reference,
                  policy_revision=self.revision, created_at=datetime.now(timezone.utc))
        self._cas_head(kind, reference, expected, record.revision)
        self._audit(action, reference, session)

    def _department_refs(self, department):
        self._reference('executive', department.executive_reference)
        for team in department.team_references:
            if self._reference('team', team)['parent_reference'] != department.executive_reference:
                raise PermissionError('Team distribution belongs to another executive')
        for kind, references in (('mandate', (department.mandate,)), ('classification', department.information_received+department.information_produced),
                                 ('escalation', (department.escalation_reference,)), ('visibility', (department.visibility_reference,))):
            for reference in references:
                self._reference(kind, reference)

    @transactional_operation
    def append_department(self, record, expected=0):
        if type(record) is not Department:
            raise ValueError('Department contract required')
        record.validate()
        self._auth('registry.department.append', record.department_id)
        self._department_refs(record)
        self._record('department', record, expected, 'registry.department.append')
        for name in (record.canonical_name, *record.aliases):
            rows = self._rows('routing_names', name=name)
            if rows and rows[0]['department_reference'] != record.department_id:
                raise ConflictError('Canonical name or alias is already reserved')
            if not rows:
                self._put('routing_names', name=name, department_reference=record.department_id, department_kind='department', first_revision=record.revision)

    def _rule_refs(self, rule, approved=False):
        if rule.policy_revision != self.revision:
            raise PermissionError('Rule policy revision mismatch')
        self._reference('policy', rule.policy_reference)
        self._reference('classification', rule.classification)
        self._reference('action', rule.required_action)
        for fact in rule.preconditions+rule.escalation_conditions:
            self._reference('fact', fact)
        for visibility in rule.visibility_references:
            self._reference('visibility', visibility)
        departments = {}
        for reference, revision, digest, executive in rule.recipients:
            self._auth('registry.department.read', reference)
            department = self._get('department', reference, revision, latest=True)
            if department.content_digest != digest or department.executive_reference != executive:
                raise PermissionError('Rule department binding mismatch')
            self._department_refs(department)
            if approved:
                self._verify_evidence('department', department)
            departments[reference] = department
        return departments

    @transactional_operation
    def append_rule(self, rule, expected=0):
        if type(rule) is not Rule:
            raise ValueError('Rule contract required')
        rule.validate()
        self._auth('registry.rule.append', rule.rule_id)
        self._rule_refs(rule)
        self._record('rule', rule, expected, 'registry.rule.append')

    @transactional_operation
    def issue_routing_approval(self, kind, reference, revision, evidence_reference, lifetime=timedelta(minutes=5)):
        if kind not in ('department', 'rule'):
            raise ValueError('Unsupported approval target')
        ref(evidence_reference)
        session, _ = self._auth('approval.routing.issue', reference)
        self._auth('registry.'+kind+'.read', reference)
        record = self._get(kind, reference, revision, latest=True)
        row = self._rows('routing_records', kind=kind, reference=reference, revision=revision)[0]
        if row['actor_reference'] == session.principal.subject_reference or record.approval_reference != evidence_reference:
            raise PermissionError('Self approval or unbound evidence forbidden')
        if not isinstance(lifetime, timedelta) or not timedelta(0) < lifetime <= timedelta(minutes=5):
            raise ValueError('Invalid evidence lifetime')
        if not isinstance(self.custody, SyntheticEvidenceCustody):
            raise PermissionError('Synthetic signing custody unavailable')
        now = datetime.now(timezone.utc)
        payload = dict(tenant_reference=self.tenant, reference=evidence_reference, kind=kind, record_reference=reference,
                       record_revision=revision, content_digest=record.content_digest, grantor_reference=session.principal.subject_reference,
                       policy_revision=self.revision, valid_from=now, expires_at=min(now+lifetime,session.principal.expires_at))
        self._put('routing_evidence', **{key:value for key,value in payload.items() if key != 'tenant_reference'}, proof=self.custody.seal(payload))
        self._audit('approval.routing.issue', reference, session)

    def _verify_evidence(self, kind, record, remember=True):
        if self._get(kind,getattr(record,KINDS[kind][1]),record.revision,latest=True) != record:
            raise PermissionError('Approval target changed')
        reference = record.approval_reference
        if reference is None:
            raise PermissionError('Unresolved synthetic approval')
        rows = self._rows('routing_evidence', reference=reference)
        if not rows or self._rows('routing_revocations', reference=reference):
            raise PermissionError('Missing or revoked synthetic approval')
        row = rows[0]
        if (row['kind'],row['record_reference'],row['record_revision'],row['content_digest'],row['policy_revision']) != (kind,getattr(record,KINDS[kind][1]),record.revision,record.content_digest,self.revision):
            raise PermissionError('Approval revision mismatch')
        payload = {key:value for key,value in row.items() if key not in ('proof','dataset')}
        if not isinstance(self.custody,SyntheticEvidenceCustody) or not self.custody.verify(payload,row['proof']) or not current_interval(row['valid_from'],row['expires_at']):
            raise PermissionError('Unverifiable or expired synthetic approval')
        author = self._rows('routing_records',kind=kind,reference=row['record_reference'],revision=record.revision)[0]['actor_reference']
        valid = False
        for key, session in self.authority.sessions.items():
            if session.principal.subject_reference != row['grantor_reference'] or session.principal.tenant_reference != self.tenant or author == row['grantor_reference']:
                continue
            try:
                self.authority.authorize(key,self.tenant,self.revision,'approval.routing.issue',row['record_reference'])
                valid = True
                break
            except PermissionError:
                continue
        if not valid:
            raise PermissionError('Issuing authority unavailable')
        if remember and (kind, record) not in self.evidence_checks:
            self.evidence_checks.append((kind,record))

    @transactional_operation
    def revoke_routing_approval(self, reference):
        rows = self._rows('routing_evidence', reference=reference)
        if not rows:
            raise PermissionError('Unknown approval')
        session, _ = self._auth('approval.routing.revoke',rows[0]['record_reference'])
        if self._rows('routing_revocations',reference=reference):
            return 'duplicate'
        self._put('routing_revocations',reference=reference,actor_reference=session.principal.subject_reference,created_at=datetime.now(timezone.utc))
        self._audit('approval.routing.revoke',rows[0]['record_reference'],session)
        return 'revoked'

    def _journal(self, intake, event, reference, revision, extra=None):
        heads = self._rows('routing_journey_heads',intake_reference=intake.event_id)
        previous = heads[0]['sequence'] if heads else 0
        previous_digest = self._rows('routing_events',intake_reference=intake.event_id,sequence=previous)[0]['content_digest'] if previous else None
        payload = dict(tenant_reference=self.tenant,source_event_reference=intake.event_id,
                       original_classification=intake.original_classification,sequence=previous+1,
                       previous_digest=previous_digest,event=event,reference=reference,revision=revision,
                       actor_reference=self.authority.resolve(self.session,self.tenant,self.revision)[0].principal.subject_reference,
                       policy_revision=self.revision,details=extra or {})
        self._put('routing_events',intake_reference=intake.event_id,intake_kind='intake',intake_revision=1,
                  sequence=previous+1,previous_sequence=previous or None,previous_digest=previous_digest,
                  content_digest=fingerprint(payload),payload=payload,state='inactive')
        if not previous:
            _,count = _query(self.connection,'INSERT INTO mc_syn.routing_journey_heads (tenant_reference,intake_reference,sequence,dataset) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING',(self.tenant,intake.event_id,1,'synthetic'))
        else:
            _,count = _query(self.connection,'UPDATE mc_syn.routing_journey_heads SET sequence=%s WHERE tenant_reference=%s AND intake_reference=%s AND sequence=%s',(previous+1,self.tenant,intake.event_id,previous))
        if count != 1:
            raise ConflictError('Concurrent synthetic journey append')

    def _packet_links(self, packet):
        self._put('routing_links',packet_reference=packet.packet_id,packet_revision=packet.revision,packet_kind='packet',
            department_reference=packet.recipient_references[0],department_revision=packet.registry_revision,
            department_digest=packet.registry_digest,department_kind='department',rule_reference=packet.rule_reference,
            rule_revision=packet.rule_revision,rule_digest=packet.rule_digest,rule_kind='rule',
            intake_reference=packet.source_event_reference,intake_revision=1,intake_kind='intake')

    @transactional_operation
    def simulate_routing(self, intake, rule_reference, rule_revision, key):
        if type(intake) is not Intake:
            raise ValueError('Intake contract required')
        intake.validate()
        ref(key)
        self._auth('packet.route_simulate',rule_reference)
        self._auth('registry.rule.read',rule_reference)
        if intake.tenant_reference != self.tenant:
            raise PermissionError('Cross-tenant intake forbidden')
        rule = self._get('rule',rule_reference,rule_revision,latest=True)
        self._verify_evidence('rule',rule)
        departments = self._rule_refs(rule,approved=True)
        packets = derive_packets(intake,rule,departments,key)
        # Every recipient and packet needs an explicit grant, including replays.
        for packet in packets:
            self._auth('packet.routing.append',packet.packet_id)
            self._auth('packet.routing.read',packet.packet_id)
        payload_digest = fingerprint([asdict(intake),asdict(rule),key])
        receipts = self._rows('routing_receipts',operation='syn-route',key=key)
        if receipts:
            if receipts[0]['payload_digest'] != payload_digest or receipts[0]['result'] != [packet.packet_id for packet in packets]:
                raise ConflictError('Routing idempotency payload collision')
            return tuple(self._get('packet',packet.packet_id,1) for packet in packets)
        if self._rows('routing_records',kind='intake',reference=intake.event_id):
            raise ConflictError('Intake event already entered')
        # Intake uses the authorized rule resource, not an implicit intake grant.
        session,_ = self._auth('packet.route_simulate',rule_reference)
        self._put('routing_records',kind='intake',reference=intake.event_id,revision=1,previous_revision=None,
                  content_digest=intake.content_digest,payload=asdict(intake),state='inactive',
                  actor_reference=session.principal.subject_reference,policy_revision=self.revision,created_at=datetime.now(timezone.utc))
        self._cas_head('intake',intake.event_id,0,1)
        self._journal(intake,'syn-intake',intake.event_id,1)
        for packet in packets:
            self._record('packet',packet,0,'packet.routing.append')
            self._packet_links(packet)
            self._journal(intake,'syn-packet-proposed',packet.packet_id,1)
        self._put('routing_receipts',operation='syn-route',key=key,payload_digest=payload_digest,result=[packet.packet_id for packet in packets])
        return packets

    @transactional_operation
    def append_packet_revision(self, packet, expected, key):
        if type(packet) is not DepartmentPacket:
            raise ValueError('Department packet required')
        packet.validate()
        ref(key)
        self._auth('packet.routing.append',packet.packet_id)
        self._auth('packet.routing.read',packet.packet_id)
        if packet.tenant_reference != self.tenant or type(expected) is not int or packet.revision != expected+1:
            raise ConflictError('Packet revision or tenant mismatch')
        prior = self._get('packet',packet.packet_id,expected)
        variable = {'revision','content_digest','current_classification','dependencies','priority','outcome_references','handoff_references'}
        if {k:v for k,v in asdict(prior).items() if k not in variable} != {k:v for k,v in asdict(packet).items() if k not in variable}:
            raise PermissionError('Original classification and routing identity are permanent')
        if not set(prior.outcome_references) <= set(packet.outcome_references) or not set(prior.handoff_references) <= set(packet.handoff_references):
            raise PermissionError('Prior outcomes and handoffs cannot be erased')
        rule = self._get('rule',packet.rule_reference,packet.rule_revision,latest=True)
        self._verify_evidence('rule',rule)
        self._rule_refs(rule,approved=True)
        self._reference('classification',packet.current_classification)
        for kind,values in (('dependency',packet.dependencies),('outcome',packet.outcome_references),('handoff',packet.handoff_references)):
            for value in values: self._reference(kind,value)
        receipt = self._rows('routing_receipts',operation='syn-packet-revision',key=key)
        if receipt:
            if receipt[0]['payload_digest'] != packet.content_digest:
                raise ConflictError('Packet revision idempotency collision')
            return 'duplicate'
        if self._head('packet',packet.packet_id) != expected:
            raise ConflictError('Stale packet revision')
        self._record('packet',packet,expected,'packet.routing.append')
        self._packet_links(packet)
        intake = self._get('intake',packet.source_event_reference,1)
        self._journal(intake,'syn-packet-revised',packet.packet_id,packet.revision)
        self._put('routing_receipts',operation='syn-packet-revision',key=key,payload_digest=packet.content_digest,result=[packet.packet_id,packet.revision])
        return 'appended'

    @transactional_operation
    def read_journey(self, intake_reference):
        self._auth('journey.routing.read',intake_reference)
        intake = self._get('intake',intake_reference,1)
        rows = sorted(self._rows('routing_events',intake_reference=intake_reference),key=lambda row:row['sequence'])
        previous = None
        for sequence,row in enumerate(rows,1):
            payload = row['payload']
            if (row['sequence'],row['previous_digest'],row['content_digest'],payload['original_classification'],payload['sequence'],payload['previous_digest']) != (sequence,previous,fingerprint(payload),intake.original_classification,sequence,previous):
                raise ValueError('Journey integrity mismatch')
            previous = row['content_digest']
        head = self._rows('routing_journey_heads',intake_reference=intake_reference)
        if not head or head[0]['sequence'] != len(rows):
            raise ValueError('Journey head integrity mismatch')
        return tuple(row['payload'] for row in rows)

    @transactional_operation
    def view_packet(self, packet_reference, revision, audience, team_reference=None):
        if audience not in ('executive','team','command','control','governance'):
            raise PermissionError('Unknown visibility audience')
        packet = self._get('packet',packet_reference,revision)
        if audience in ('executive','team'):
            if audience == 'executive':
                resource = packet.executive_reference
            else:
                resource = team_reference
                team = self._reference('team',resource)
                if team['parent_reference'] != packet.executive_reference:
                    raise PermissionError('Team outside executive boundary')
                events = self._rows('routing_events',intake_reference=packet.source_event_reference)
                if not any(row['payload']['event']=='syn-team-visibility' and row['payload']['reference']==packet_reference
                           and row['payload']['revision']==revision and row['payload']['details'].get('team_reference')==resource for row in events):
                    raise PermissionError('Executive distribution decision missing')
        else:
            resource = 'syn-view-'+audience
        session,_ = self._auth('packet.view.'+audience,resource)
        if audience == 'executive':
            executive = self._reference('executive',packet.executive_reference)
            if executive['parent_reference'] != session.principal.subject_reference or session.kind != 'human':
                raise PermissionError('Responsible individual executive required')
        # Projection intentionally omits mandate, aliases, teams, approvals and content.
        result = dict(packet_reference=packet.packet_id,revision=packet.revision,
                      source_event_reference=packet.source_event_reference,original_classification=packet.original_classification,
                      current_classification=packet.current_classification,executive_reference=packet.executive_reference,
                      department_references=packet.recipient_references,state='inactive',audience=audience)
        if audience in ('executive','team'):
            result['required_action']=packet.required_action
        self._audit('packet.view.'+audience,packet.packet_id,session)
        return result

    @transactional_operation
    def distribute_team_visibility(self, packet_reference, revision, team_reference, key):
        ref(key)
        packet = self._get('packet',packet_reference,revision,latest=True)
        session,_ = self._auth('packet.distribute',packet.executive_reference)
        executive = self._reference('executive',packet.executive_reference)
        team = self._reference('team',team_reference)
        department = self._get('department',packet.recipient_references[0],packet.registry_revision)
        if (session.kind!='human' or executive['parent_reference'] != session.principal.subject_reference
                or team['parent_reference'] != packet.executive_reference or team_reference not in department.team_references):
            raise PermissionError('Only responsible executive controls internal distribution')
        payload = fingerprint([packet.packet_id,revision,team_reference])
        receipts = self._rows('routing_receipts',operation='syn-distribute',key=key)
        if receipts:
            if receipts[0]['payload_digest'] != payload:
                raise ConflictError('Distribution idempotency collision')
            return 'duplicate'
        intake = self._get('intake',packet.source_event_reference,1)
        self._journal(intake,'syn-team-visibility',packet.packet_id,revision,{'team_reference':team_reference})
        self._put('routing_receipts',operation='syn-distribute',key=key,payload_digest=payload,result=[packet_reference,revision,team_reference])
        self._audit('packet.distribute',packet_reference,session)
        return 'appended'
