"""Opt-in, local-only synthetic PostgreSQL proof. No CLI or engine wiring.

The optional driver is imported only on explicit local connection. Missing driver
or server fails closed; no installation, TCP DSN, environment credential, or
cloud fallback is attempted. DB integration must be tested separately.
"""
from contextlib import contextmanager
from functools import wraps
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import stat
import uuid

from .contracts import Approval, ApprovalEvidence, LifecycleEvent, RegistryRecord, WorkPacket, digest
from .json_io import strict_json_loads
from .registry_authorization import positive_revision
from .registry_persistence import (ConflictError, IdempotencyReceipt, JournalEvent,
                                   PacketRevision, RegistryRevision, validate_event_append)
from .synthetic_identity import (SyntheticAuthority, SyntheticEvidenceCustody, canonical,
                                 fingerprint, synthetic_reference)

ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = ROOT / 'migrations/postgresql/0001_synthetic_foundation.sql'
LOGICAL_PATH = ROOT / 'migrations/protected_registry/0001_foundation.json'
MIGRATION_ID = 'syn-postgresql-0001'
ENTITIES = {entity['name']: entity for entity in strict_json_loads(LOGICAL_PATH.read_text())['entities']}


def local_connection(socket_directory, database, user):
    """Unix socket in a private /tmp directory only; no remote connection inputs."""
    path = Path(socket_directory)
    for value in (database, user):
        synthetic_reference(value)
    if (not path.is_absolute() or path.resolve() != path or not path.is_relative_to('/tmp')
            or not path.is_dir() or stat.S_IMODE(path.stat().st_mode) != 0o700):
        raise ValueError('Private disposable local socket directory required')
    if not (path / '.s.PGSQL.5432').is_socket():
        raise RuntimeError('Disposable local PostgreSQL is unavailable')
    try:
        import psycopg
    except ImportError:
        raise RuntimeError('Optional PostgreSQL driver is unavailable; no fallback') from None
    return psycopg.connect(host=str(path), dbname=database, user=user, connect_timeout=3)


def registry_from(payload):
    data = strict_json_loads(payload) if isinstance(payload, str) else dict(payload)
    record = dict(data.pop('record'))
    if record.get('approval') is not None:
        raise ValueError('Stored draft approval wrapper must be empty')
    result = RegistryRevision(record=RegistryRecord(**record), **data)
    result.validate()
    return result


def packet_from(payload):
    data = strict_json_loads(payload) if isinstance(payload, str) else dict(payload)
    return PacketRevision(packet=WorkPacket(**data.pop('packet')), **data)


def event_from(payload):
    data = strict_json_loads(payload) if isinstance(payload, str) else dict(payload)
    event = dict(data.pop('event'))
    event['packet'] = WorkPacket(**event['packet'])
    return JournalEvent(event=LifecycleEvent(**event), **data)


def _query(connection, sql, parameters=()):
    with connection.cursor() as cursor:
        cursor.execute(sql, parameters)
        rows = [] if cursor.description is None else [dict(zip([c[0] for c in cursor.description], row)) for row in cursor.fetchall()]
        return rows, cursor.rowcount


def apply_local_migration(factory, authority=None, session=None, tenant=None, revision=1):
    if not isinstance(authority, SyntheticAuthority):
        raise PermissionError('Synthetic migration authority required')
    authority.authorize(session, tenant, revision, 'schema.migrate', 'syn-schema')
    connection = factory()
    try:
        _query(connection, 'BEGIN')
        _query(connection, 'SELECT pg_advisory_xact_lock(%s)', (731843291,))
        exists, _ = _query(connection, "SELECT to_regclass('mc_syn.schema_migrations') AS relation")
        checksum = fingerprint({'sql': SQL_PATH.read_text(), 'logical': strict_json_loads(LOGICAL_PATH.read_text())})
        if exists[0]['relation'] is not None:
            rows, _ = _query(connection, 'SELECT checksum FROM mc_syn.schema_migrations WHERE tenant_reference=%s AND migration_id=%s', ('syn-system', MIGRATION_ID))
            if not rows or rows[0]['checksum'] != checksum:
                raise ConflictError('Migration checksum mismatch or unknown schema')
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


def transactional_operation(function):
    """Even a swallowed application error must prevent committing partial writes."""
    @wraps(function)
    def guarded(self,*args,**kwargs):
        try:
            self._open()
            return function(self,*args,**kwargs)
        except BaseException:
            self.failed = True
            raise
    return guarded


class LocalSyntheticStore:
    def __init__(self, connection_factory=None, authority=None, custody=None):
        # Factory is a trusted local/test dependency, never accepted as request data.
        self.factory = connection_factory
        self.authority = authority
        self.custody = custody

    def transaction_type(self):
        return SyntheticTransaction

    @contextmanager
    def transaction(self, tenant_reference, session_reference, policy_revision):
        if not isinstance(self.authority, SyntheticAuthority) or self.factory is None:
            raise PermissionError('Local synthetic storage is disabled')
        self.authority.resolve(session_reference, tenant_reference, policy_revision)
        connection = self.factory()
        tx = self.transaction_type()(connection, self.authority, self.custody,
                                  tenant_reference, session_reference, policy_revision)
        try:
            _query(connection, 'BEGIN ISOLATION LEVEL SERIALIZABLE')
            _query(connection, "SET LOCAL statement_timeout = '5s'")
            _query(connection, "SET LOCAL lock_timeout = '2s'")
            role, _ = _query(connection, 'SELECT current_user AS role, session_user AS session_role')
            if role != [{'role': 'syn-runtime', 'session_role': 'syn-runtime'}]:
                raise PermissionError('Dedicated non-owner runtime identity required')
            _query(connection, "SELECT set_config('mission_control.tenant', %s, true)", (tenant_reference,))
            yield tx
            if tx.failed:
                raise PermissionError('Synthetic transaction aborted by an operation failure')
            if tx.commit_requested:
                tx.recheck()
                connection.commit()
            else:
                connection.rollback()
        except BaseException as exc:
            connection.rollback()
            if getattr(exc, 'sqlstate', None) in ('40001', '40P01', '23505'):
                raise ConflictError('Synthetic transaction conflict; retry with original idempotency key') from None
            if isinstance(exc, (PermissionError, ValueError, KeyboardInterrupt, SystemExit)):
                raise
            raise RuntimeError('Synthetic PostgreSQL transaction failed') from None
        finally:
            tx.closed = True
            connection.close()


class SyntheticTransaction:
    def __init__(self, connection, authority, custody, tenant, session, revision):
        self.connection, self.authority, self.custody = connection, authority, custody
        self.tenant, self.session, self.revision = tenant, session, revision
        self.commit_requested = False
        self.closed = False
        self.failed = False
        self.checks = []

    def _open(self):
        if self.closed or self.commit_requested or self.failed:
            raise PermissionError('Transaction is closed for new operations')

    def _auth(self, action, resource, context=True):
        self._open()
        session, policy = self.authority.authorize(self.session, self.tenant, self.revision, action, resource)
        if context:
            rows = self._select('policy_revisions', policy_revision=self.revision)
            if not rows or rows[0]['content_digest'] != fingerprint(asdict(policy)):
                raise PermissionError('Persisted policy is missing or mismatched')
        self.checks.append((action, resource))
        return session, policy

    def recheck(self):
        self.authority.resolve(self.session, self.tenant, self.revision)
        for action, resource in self.checks:
            self.authority.authorize(self.session, self.tenant, self.revision, action, resource)

    @transactional_operation
    def commit(self):
        self._open()
        self.commit_requested = True  # Actual commit occurs on clean context exit.

    def _select(self, table, **keys):
        self._open()
        if table not in ENTITIES or not set(keys) <= ENTITIES[table]['columns'].keys():
            raise ValueError('Unknown storage selector')
        clauses = ['tenant_reference=%s'] + [name+'=%s' for name in keys]
        return _query(self.connection, 'SELECT * FROM mc_syn.'+table+' WHERE '+' AND '.join(clauses),
                      (self.tenant, *keys.values()))[0]

    def _insert(self, table, row):
        self._open()
        row = {'tenant_reference': self.tenant, **row, 'dataset': 'synthetic'}
        if table not in ENTITIES or set(row) != set(ENTITIES[table]['columns']) or row['tenant_reference'] != self.tenant:
            raise ValueError('Storage row schema or tenant mismatch')
        placeholders = ['%s::jsonb' if ENTITIES[table]['columns'][column] == 'json' else '%s' for column in row]
        values = []
        for column,value in row.items():
            kind = ENTITIES[table]['columns'][column]
            if kind == 'json':
                value = json.dumps(canonical(value), allow_nan=False)
            elif kind == 'timestamp' and isinstance(value,str):
                value = datetime.fromisoformat(value)
            values.append(value)
        _query(self.connection, 'INSERT INTO mc_syn.'+table+' ('+','.join(row)+') VALUES ('+','.join(placeholders)+')', tuple(values))

    def _audit(self, action, resource, session):
        self._insert('security_decisions', {'decision_reference':'syn-decision-'+uuid.uuid4().hex,
                     'subject_reference':session.principal.subject_reference, 'action':action,
                     'resource_reference':resource, 'policy_revision':self.revision, 'allowed':True,
                     'reason_code':'synthetic_validated', 'created_at':datetime.now(timezone.utc)})

    @transactional_operation
    def bootstrap_policy(self):
        session, policy = self._auth('policy.append', 'syn-policy', context=False)
        for candidate in self.authority.sessions.values():
            if candidate.principal.tenant_reference != self.tenant:
                continue
            candidate.validate(self.tenant)
            p = candidate.principal
            if not self._select('subjects', subject_reference=p.subject_reference):
                self._insert('subjects', {'subject_reference':p.subject_reference, 'issuer_reference':'syn-local-fixture', 'audience':p.audience, 'status':'synthetic'})
        existing = self._select('policy_revisions', policy_revision=self.revision)
        if existing:
            if existing[0]['content_digest'] != fingerprint(asdict(policy)):
                raise ConflictError('Policy revision cannot be edited')
            return 'duplicate'
        self._insert('policy_revisions', {'policy_revision':self.revision, 'content_digest':fingerprint(asdict(policy)),
                     'rules_document':asdict(policy), 'valid_from':policy.valid_from, 'expires_at':policy.expires_at})
        bindings = set()
        for candidate in self.authority.sessions.values():
            if candidate.principal.tenant_reference == self.tenant:
                for role in candidate.principal.roles:
                    if (candidate.principal.subject_reference,role) in bindings:
                        continue
                    bindings.add((candidate.principal.subject_reference,role))
                    self._insert('role_bindings', {'binding_reference':'syn-binding-'+fingerprint([candidate.principal.subject_reference,role,self.revision]),
                                 'subject_reference':candidate.principal.subject_reference, 'role_reference':role,
                                 'policy_revision':self.revision, 'valid_from':policy.valid_from, 'expires_at':policy.expires_at})
        self._audit('policy.append', 'syn-policy', session)
        return 'appended'

    @transactional_operation
    def read_security_decisions(self):
        self._auth('audit.read','syn-audit')
        return self._select('security_decisions')

    @transactional_operation
    def get_registry(self, record_reference, revision):
        positive_revision(revision)
        self._auth('registry.read', record_reference)
        rows = self._select('registry_revisions', record_reference=record_reference, revision=revision)
        if not rows:
            return None
        row = rows[0]
        result = registry_from(row['payload'])
        if (result.tenant_reference, result.record.record_id, result.record.revision, result.content_digest,
                result.previous_revision,result.schema_revision,result.record.state) != (self.tenant, record_reference, revision, row['content_digest'],
                row['previous_revision'],row['schema_revision'],row['state']):
            raise ValueError('Registry row integrity mismatch')
        return result

    @transactional_operation
    def get_packet(self, packet_reference, revision):
        positive_revision(revision)
        self._auth('packet.read', packet_reference)
        rows = self._select('packet_revisions', packet_reference=packet_reference, revision=revision)
        if not rows:
            return None
        row = rows[0]
        packet = packet_from(row['payload'])
        registry = self.get_registry(packet.packet.registry_reference, packet.packet.registry_revision)
        packet.validate(registry)
        if (packet.tenant_reference,packet.packet.packet_id,packet.revision,fingerprint(asdict(packet)),
                packet.previous_revision,packet.schema_revision,packet.packet.registry_reference,packet.packet.registry_revision,packet.packet.state) != (self.tenant,packet_reference,revision,row['content_digest'],
                row['previous_revision'],row['schema_revision'],row['registry_reference'],row['registry_revision'],row['state']):
            raise ValueError('Packet row integrity mismatch')
        return packet

    def _receipt(self, operation, key, payload):
        synthetic_reference(key)
        rows = self._select('idempotency_receipts', operation_reference=operation, idempotency_key=key)
        if rows and rows[0]['payload_digest'] != fingerprint(payload):
            raise ConflictError('Idempotency key payload collision')
        return bool(rows)

    def _save_receipt(self, operation, key, payload, result, revision):
        self._insert('idempotency_receipts', {'operation_reference':operation, 'idempotency_key':key,
                     'payload_digest':fingerprint(payload), 'result_reference':result,
                     'result_revision':revision, 'created_at':datetime.now(timezone.utc)})

    @transactional_operation
    def get_receipt(self, operation, key):
        rows = self._select('idempotency_receipts', operation_reference=operation, idempotency_key=key)
        if not rows:
            return None
        row = rows[0]
        try:
            self._auth(operation, row['result_reference'])
        except PermissionError:
            return None  # No distinction between absent and unauthorized receipt.
        return IdempotencyReceipt(self.tenant, operation, key, row['payload_digest'], row['result_reference'], row['result_revision'])

    @transactional_operation
    def append_receipt(self, receipt):
        raise PermissionError('Standalone success receipts are disabled')

    def _cas(self, table, key_column, key, column, expected, new):
        allowed = {'registry_heads':('record_reference','revision'), 'packet_heads':('packet_reference','revision'), 'journey_heads':('journey_reference','sequence')}
        if allowed.get(table) != (key_column,column):
            raise ValueError('Unknown head selector')
        if expected == 0:
            _, count = _query(self.connection, f'INSERT INTO mc_syn.{table} (tenant_reference,{key_column},{column},dataset) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING', (self.tenant,key,new,'synthetic'))
        else:
            _, count = _query(self.connection, f'UPDATE mc_syn.{table} SET {column}=%s WHERE tenant_reference=%s AND {key_column}=%s AND {column}=%s', (new,self.tenant,key,expected))
        if count != 1:
            raise ConflictError('Optimistic head conflict')

    @transactional_operation
    def append_registry(self, revision, expected_revision, idempotency_key=None):
        revision.validate()
        if revision.tenant_reference != self.tenant or type(expected_revision) is not int or revision.previous_revision != expected_revision:
            raise ConflictError('Registry scope/revision mismatch')
        resource = revision.record.record_id
        session, _ = self._auth('registry.append_draft', resource)
        payload = asdict(revision)
        if self._receipt('registry.append_draft', idempotency_key, payload):
            return 'duplicate'
        self._insert('registry_revisions', {'record_reference':resource, 'revision':revision.record.revision,
                     'previous_revision':expected_revision, 'state':revision.record.state, 'payload':payload,
                     'content_digest':revision.content_digest, 'created_at':datetime.now(timezone.utc),
                     'actor_reference':session.principal.subject_reference, 'policy_revision':self.revision, 'schema_revision':1})
        self._cas('registry_heads','record_reference',resource,'revision',expected_revision,revision.record.revision)
        self._save_receipt('registry.append_draft', idempotency_key, payload, resource, revision.record.revision)
        self._audit('registry.append_draft',resource,session)
        return 'appended'

    @transactional_operation
    def append_packet(self, packet, expected_revision, idempotency_key=None):
        session, _ = self._auth('packet.append_inactive',packet.packet.packet_id)
        registry = self.get_registry(packet.packet.registry_reference,packet.packet.registry_revision)
        packet.validate(registry)
        if packet.tenant_reference != self.tenant or type(expected_revision) is not int or packet.previous_revision != expected_revision:
            raise ConflictError('Packet scope/revision mismatch')
        payload = asdict(packet)
        if self._receipt('packet.append_inactive', idempotency_key, payload):
            return 'duplicate'
        self._insert('packet_revisions', {'packet_reference':packet.packet.packet_id, 'revision':packet.revision,
                     'previous_revision':expected_revision,'registry_reference':packet.packet.registry_reference,
                     'registry_revision':packet.packet.registry_revision,'state':'inactive','payload':payload,
                     'content_digest':fingerprint(payload),'created_at':datetime.now(timezone.utc),
                     'actor_reference':session.principal.subject_reference,'policy_revision':self.revision,'schema_revision':1})
        self._cas('packet_heads','packet_reference',packet.packet.packet_id,'revision',expected_revision,packet.revision)
        self._save_receipt('packet.append_inactive',idempotency_key,payload,packet.packet.packet_id,packet.revision)
        self._audit('packet.append_inactive',packet.packet.packet_id,session)
        return 'appended'

    def _event(self, row):
        event = event_from(row['payload'])
        packet = self.get_packet(event.event.packet.packet_id,event.packet_revision)
        registry = self.get_registry(packet.packet.registry_reference,packet.packet.registry_revision)
        event.validate(packet,registry)
        if (event.tenant_reference,event.event.event_id,event.sequence,event.content_digest,
                event.event.journey_reference,event.event.packet.packet_id,event.packet_revision,event.previous_digest,event.schema_revision) != (self.tenant,row['event_reference'],row['sequence'],row['content_digest'],
                row['journey_reference'],row['packet_reference'],row['packet_revision'],row['previous_digest'],row['schema_revision']):
            raise ValueError('Event row integrity mismatch')
        return event

    @transactional_operation
    def get_event(self, event_reference):
        rows = self._select('journey_events',event_reference=event_reference)
        if not rows:
            return None
        try:
            self._auth('journey.read',rows[0]['journey_reference'])
        except PermissionError:
            return None
        return self._event(rows[0])

    @transactional_operation
    def get_journey_head(self, journey_reference):
        self._auth('journey.read',journey_reference)
        heads = self._select('journey_heads',journey_reference=journey_reference)
        if not heads:
            return None
        rows = self._select('journey_events',journey_reference=journey_reference,sequence=heads[0]['sequence'])
        return self._event(rows[0])

    @transactional_operation
    def append_event(self,event,expected_sequence,idempotency_key=None):
        resource = event.event.journey_reference
        session,_ = self._auth('journey.append_inactive',resource)
        packet = self.get_packet(event.event.packet.packet_id,event.packet_revision)
        registry = self.get_registry(packet.packet.registry_reference,packet.packet.registry_revision)
        event.validate(packet,registry)
        if event.tenant_reference != self.tenant or type(expected_sequence) is not int or expected_sequence != event.sequence-1:
            raise ConflictError('Event scope/sequence mismatch')
        key = idempotency_key or event.event.event_id
        payload = asdict(event)
        if self._receipt('journey.append_inactive',key,payload):
            return 'duplicate'
        duplicate = self.get_event(event.event.event_id)
        if duplicate is not None:
            raise ConflictError('Duplicate event ID under a different receipt')
        previous = self.get_journey_head(resource)
        validate_event_append(event,previous,None,packet,registry)
        self._insert('journey_events',{'event_reference':event.event.event_id,'journey_reference':resource,
                     'sequence':event.sequence,'packet_reference':event.event.packet.packet_id,'packet_revision':event.packet_revision,
                     'previous_digest':event.previous_digest,'content_digest':event.content_digest,'payload':payload,'active':False,
                     'created_at':datetime.now(timezone.utc),'actor_reference':session.principal.subject_reference,
                     'policy_revision':self.revision,'schema_revision':1})
        self._cas('journey_heads','journey_reference',resource,'sequence',expected_sequence,event.sequence)
        self._save_receipt('journey.append_inactive',key,payload,resource,event.sequence)
        self._audit('journey.append_inactive',resource,session)
        return 'appended'

    @transactional_operation
    def issue_approval(self,record_reference,revision,evidence_reference,lifetime=timedelta(minutes=5)):
        synthetic_reference(evidence_reference)
        session,_ = self._auth('approval.issue',record_reference)
        record = self.get_registry(record_reference,revision)
        rows = self._select('registry_revisions',record_reference=record_reference,revision=revision)
        if record is None or rows[0]['actor_reference'] == session.principal.subject_reference:
            raise PermissionError('Missing record or self-approval forbidden')
        if not isinstance(lifetime,timedelta) or not timedelta(0) < lifetime <= timedelta(minutes=5):
            raise ValueError('Invalid synthetic approval lifetime')
        if not isinstance(self.custody,SyntheticEvidenceCustody):
            raise PermissionError('Signing custody unavailable')
        now = datetime.now(timezone.utc)
        row = {'evidence_reference':evidence_reference,'record_reference':record_reference,'record_revision':revision,
               'content_digest':digest(record.record.payload()),
               'grantor_reference':session.principal.subject_reference,'policy_revision':self.revision,
               'valid_from':now,'expires_at':min(now+lifetime,session.principal.expires_at),'status':'issued'}
        row['proof_reference'] = json.dumps(self.custody.seal({'tenant_reference':self.tenant,**row}))
        self._insert('approval_evidence',row)
        self._audit('approval.issue',record_reference,session)
        return evidence_reference

    @transactional_operation
    def resolve_approval(self,reference):
        rows = self._select('approval_evidence',evidence_reference=reference)
        if not rows:
            return None
        row = rows[0]
        self._auth('approval.verify',row['record_reference'])
        if self._select('approval_revocations',evidence_reference=reference):
            return None
        payload = {key:value for key,value in row.items() if key not in ('dataset','proof_reference')}
        if not isinstance(self.custody,SyntheticEvidenceCustody) or not self.custody.verify(payload,strict_json_loads(row['proof_reference'])):
            return None
        # Revalidate issuing authority's current identity, policy and permission.
        candidates = [key for key,value in self.authority.sessions.items() if value.principal.subject_reference == row['grantor_reference'] and value.principal.tenant_reference == self.tenant]
        valid_grantor = False
        for candidate in candidates:
            try:
                self.authority.authorize(candidate,self.tenant,row['policy_revision'],'approval.issue',row['record_reference'])
                valid_grantor = True
                break
            except PermissionError:
                continue
        record = self.get_registry(row['record_reference'],row['record_revision'])
        if not valid_grantor or record is None or row['status'] != 'issued' or row['tenant_reference'] != self.tenant:
            return None
        authors = self._select('registry_revisions',record_reference=row['record_reference'],revision=row['record_revision'])
        if not authors or authors[0]['actor_reference'] == row['grantor_reference']:
            return None
        approval = Approval(row['record_reference'],row['record_revision'],row['content_digest'],reference)
        approval.validate(record.record.record_id,record.record.revision,record.record.payload())
        evidence = ApprovalEvidence(approval,row['valid_from'],row['expires_at'],True)
        try:
            evidence.validate(approval)
        except ValueError:
            return None
        return evidence

    @transactional_operation
    def revoke_approval(self,reference):
        rows = self._select('approval_evidence',evidence_reference=reference)
        if not rows:
            raise PermissionError('Evidence unavailable')
        session,_ = self._auth('approval.revoke',rows[0]['record_reference'])
        if self._select('approval_revocations',evidence_reference=reference):
            return 'duplicate'
        self._insert('approval_revocations',{'evidence_reference':reference,'revocation_reference':'syn-revocation-'+uuid.uuid4().hex,
                     'revoked_at':datetime.now(timezone.utc),'actor_reference':session.principal.subject_reference})
        self._audit('approval.revoke',rows[0]['record_reference'],session)
        return 'revoked'
