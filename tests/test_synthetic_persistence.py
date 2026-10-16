"""Local unit/contract tests. Recording DB-API objects are NOT PostgreSQL proof."""
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from itertools import combinations
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import Mock, patch

from mission_control.contracts import Approval, digest
from mission_control.registry_persistence import ConflictError
from mission_control.synthetic_archive import (migration_checksum, read_archive,
    restore_snapshot, validate_archive, validate_payload, write_archive)
from mission_control.synthetic_identity import (PRIVILEGED, SyntheticAuthority,
    SyntheticEvidenceCustody, canonical, fingerprint)
from mission_control.synthetic_postgres import (ENTITIES, LocalSyntheticStore,
    SQL_PATH, SyntheticTransaction, apply_local_migration, local_connection)
from tests.synthetic_postgres_support import authority_fixture, session_ref, snapshot_tables
from tests.test_registry_foundation import fixtures


class RecordingCursor:
    def __init__(self,connection):
        self.connection=connection
        self.description=None
        self.rowcount=1
        self.rows=[]
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def execute(self,sql,parameters=()):
        self.connection.statements.append((sql,parameters))
        rows=[]
        if sql.startswith('SELECT current_user'):
            rows=[{'role':self.connection.role,'session_role':self.connection.role}]
        elif sql.startswith('SELECT * FROM mc_syn.policy_revisions'):
            rows=[{'content_digest':self.connection.policy_digest}] if self.connection.policy_digest else []
        if rows:
            self.description=[(key,) for key in rows[0]]
            self.rows=[tuple(row.values()) for row in rows]
    def fetchall(self): return self.rows


class RecordingConnection:
    def __init__(self,role='syn-runtime',policy_digest=None):
        self.role,self.policy_digest=role,policy_digest
        self.statements=[]
        self.commits=self.rollbacks=self.closes=0
    def cursor(self): return RecordingCursor(self)
    def commit(self): self.commits+=1
    def rollback(self): self.rollbacks+=1
    def close(self): self.closes+=1


class SyntheticSecurityTests(unittest.TestCase):
    def setUp(self): self.authority,self.custody=authority_fixture()

    def test_default_deny_human_mfa_and_individual_accounts(self):
        with self.assertRaises(PermissionError):
            SyntheticAuthority().resolve('syn-unknown','syn-tenant-1',1)
        ref=session_ref('data_writer')
        original=self.authority.sessions[ref]
        for session in (replace(original,individual=False),replace(original,mfa_verified=False),
                        replace(original,mfa_verified=1),
                        replace(original,mfa_at=datetime.now(timezone.utc)-timedelta(minutes=6)),
                        replace(original,mfa_at=datetime.now())):
            self.authority.sessions[ref]=session
            with self.assertRaises(PermissionError):
                self.authority.resolve(ref,'syn-tenant-1',1)

    def test_all_privileged_duties_are_separate(self):
        session=self.authority.sessions[session_ref('approval_issuer')]
        for pair in combinations(PRIVILEGED,2):
            invalid=replace(session,principal=replace(session.principal,roles=pair))
            with self.subTest(pair=pair), self.assertRaises(PermissionError):
                invalid.validate('syn-tenant-1')
        with self.assertRaises(PermissionError):
            SyntheticEvidenceCustody(self.authority,session_ref('encryption_custodian'),'syn-tenant-1',1)

    def test_conflicting_duties_cannot_be_split_across_sessions(self):
        issuer_ref=session_ref('approval_issuer')
        issuer=self.authority.sessions[issuer_ref]
        policy=self.authority.sessions[session_ref('policy_admin')]
        self.authority.sessions['syn-second-session']=replace(policy,principal=replace(policy.principal,subject_reference=issuer.principal.subject_reference))
        with self.assertRaises(PermissionError): self.authority.resolve(issuer_ref,'syn-tenant-1',1)

    def test_service_identity_lifetime_and_no_privilege_escalation(self):
        ref=session_ref('service_writer')
        session=self.authority.sessions[ref]
        self.authority.authorize(ref,'syn-tenant-1',1,'registry.append_draft','syn-registry-1')
        for invalid in (replace(session,mfa_verified=True),
                        replace(session,principal=replace(session.principal,expires_at=session.principal.valid_from+timedelta(hours=1))),
                        replace(session,principal=replace(session.principal,roles=('approval_issuer',)))):
            self.authority.sessions[ref]=invalid
            with self.assertRaises(PermissionError): self.authority.resolve(ref,'syn-tenant-1',1)
        self.authority.sessions[ref]=session
        with self.assertRaises(PermissionError): self.authority.authorize(ref,'syn-tenant-1',1,'approval.issue','syn-registry-1')

    def test_cross_tenant_policy_revocation_and_activation_deny(self):
        ref=session_ref('data_writer')
        with self.assertRaises(PermissionError): self.authority.resolve(ref,'syn-tenant-2',1)
        with self.assertRaises(PermissionError): self.authority.resolve(ref,'syn-tenant-1',2)
        for action in ('pilot.start','provider.external_use','registry.activate'):
            with self.assertRaises(PermissionError): self.authority.authorize(ref,'syn-tenant-1',1,action,'syn-registry-1')
        p=self.authority.policies['syn-tenant-1']
        self.authority.policies['syn-tenant-1']=replace(p,grants=p.grants+(replace(p.grants[0],effect='deny'),))
        # Explicit matching denial defeats a grant regardless of order.
        grant=next(g for g in p.grants if g.role=='data_writer' and g.action=='registry.read')
        self.authority.policies['syn-tenant-1']=replace(p,grants=p.grants+(replace(grant,effect='deny'),))
        with self.assertRaises(PermissionError): self.authority.authorize(ref,'syn-tenant-1',1,'registry.read','syn-registry-1')


class TransactionBoundaryTests(unittest.TestCase):
    def setUp(self): self.authority,self.custody=authority_fixture()
    def store(self,connection): return LocalSyntheticStore(lambda:connection,self.authority,self.custody)

    def test_authority_required_before_connection(self):
        factory=Mock()
        with self.assertRaises(PermissionError):
            with LocalSyntheticStore(factory).transaction('syn-tenant-1','syn-session',1): pass
        factory.assert_not_called()

    def test_owner_connection_rejected(self):
        connection=RecordingConnection(role='syn-owner')
        with self.assertRaises(PermissionError):
            with self.store(connection).transaction('syn-tenant-1',session_ref('data_writer'),1): pass
        self.assertEqual(connection.commits,0)
        self.assertEqual(connection.rollbacks,1)
        self.assertEqual(connection.closes,1)

    def test_explicit_commit_only_after_clean_exit(self):
        for request_commit,throw in ((False,False),(True,False),(True,True)):
            connection=RecordingConnection()
            try:
                with self.store(connection).transaction('syn-tenant-1',session_ref('data_writer'),1) as tx:
                    if request_commit: tx.commit()
                    self.assertEqual(connection.commits,0)
                    if throw: raise ValueError('synthetic failure')
            except ValueError: pass
            self.assertEqual(connection.commits,int(request_commit and not throw))
            self.assertEqual(connection.rollbacks,int(not request_commit or throw))
            self.assertEqual(connection.closes,1)
            self.assertIn(('BEGIN ISOLATION LEVEL SERIALIZABLE',()),connection.statements)
            self.assertIn(("SELECT set_config('mission_control.tenant', %s, true)",('syn-tenant-1',)),connection.statements)
            with self.assertRaises(PermissionError): tx.get_registry('syn-registry-1',1)

    def test_revocation_before_exit_rolls_back(self):
        connection=RecordingConnection()
        with self.assertRaises(PermissionError):
            with self.store(connection).transaction('syn-tenant-1',session_ref('data_writer'),1) as tx:
                tx.commit()
                self.authority.sessions.pop(session_ref('data_writer'))
        self.assertEqual(connection.commits,0)
        self.assertEqual(connection.rollbacks,1)

    def test_swallowed_operation_failure_still_forces_rollback(self):
        connection=RecordingConnection()
        with self.assertRaises(PermissionError):
            with self.store(connection).transaction('syn-tenant-1',session_ref('data_writer'),1) as tx:
                try:
                    tx.bootstrap_policy()  # Denied, even if caller suppresses it.
                except PermissionError:
                    pass
                self.assertTrue(tx.failed)
        self.assertEqual(connection.commits,0)
        self.assertEqual(connection.rollbacks,1)

    def test_caught_cas_after_insert_cannot_commit_partial_history(self):
        policy=self.authority.policies['syn-tenant-1']
        connection=RecordingConnection(policy_digest=fingerprint(asdict(policy)))
        with self.assertRaises(PermissionError):
            with self.store(connection).transaction('syn-tenant-1',session_ref('data_writer'),1) as tx:
                tx._receipt=Mock(return_value=False)
                tx._cas=Mock(side_effect=ConflictError('synthetic stale head'))
                registry,_,_=fixtures()
                try:
                    tx.append_registry(registry,0,'syn-key')
                except ConflictError:
                    pass
                self.assertTrue(tx.failed)
        self.assertTrue(any(sql.startswith('INSERT INTO mc_syn.registry_revisions') for sql,_ in connection.statements))
        self.assertEqual(connection.commits,0)
        self.assertEqual(connection.rollbacks,1)

    def test_parameterized_selectors_and_cas_conflict(self):
        connection=RecordingConnection()
        with self.store(connection).transaction('syn-tenant-1',session_ref('data_writer'),1) as tx:
            value="syn-id' OR true --"
            tx._select('registry_revisions',record_reference=value)
            sql,parameters=connection.statements[-1]
            self.assertNotIn(value,sql)
            self.assertEqual(parameters,('syn-tenant-1',value))
            with self.assertRaises(ValueError): tx._select('subjects; DROP TABLE x')
            with patch('mission_control.synthetic_postgres._query',return_value=([],0)), self.assertRaises(ConflictError):
                tx._cas('registry_heads','record_reference','syn-registry-1','revision',0,1)

    def test_failure_diagnostics_do_not_expose_driver_payload(self):
        connection=RecordingConnection()
        with self.assertRaisesRegex(RuntimeError,'^Synthetic PostgreSQL transaction failed$'):
            with self.store(connection).transaction('syn-tenant-1',session_ref('data_writer'),1):
                raise RuntimeError('SYNTHETIC_PRIVATE_DRIVER_PAYLOAD')
        class SerializationFailure(Exception): sqlstate='40001'
        with self.assertRaises(ConflictError):
            with self.store(connection).transaction('syn-tenant-1',session_ref('data_writer'),1):
                raise SerializationFailure()
        self.assertEqual(connection.commits,0)

    def test_read_revision_types_fail_before_sql(self):
        for method in ('get_registry','get_packet'):
            for revision in (True,1.0,'1',0,-1):
                tx=SyntheticTransaction(None,self.authority,self.custody,'syn-tenant-1',session_ref('data_writer'),1)
                tx._select=Mock(side_effect=AssertionError('Malformed revision reached SQL'))
                with self.subTest(method=method,revision=revision), self.assertRaises(ValueError):
                    getattr(tx,method)('syn-registry-1',revision)
                tx._select.assert_not_called()
                self.assertTrue(tx.failed)

    def test_replay_requires_authorization_before_receipt_lookup(self):
        registry,_,_=fixtures()
        tx=SyntheticTransaction(None,self.authority,self.custody,'syn-tenant-1',session_ref('audit_reviewer'),1)
        tx._receipt=Mock(return_value=True)
        with self.assertRaises(PermissionError): tx.append_registry(registry,0,'syn-key')
        tx._receipt.assert_not_called()

    def test_bootstrap_policy_is_restricted(self):
        connection=RecordingConnection()
        with self.assertRaises(PermissionError):
            with self.store(connection).transaction('syn-tenant-1',session_ref('data_writer'),1) as tx:
                tx.bootstrap_policy()
        connection=RecordingConnection()
        with self.store(connection).transaction('syn-tenant-1',session_ref('policy_admin'),1) as tx:
            self.assertEqual(tx.bootstrap_policy(),'appended')
            tx.commit()
        inserts=[sql for sql,_ in connection.statements if sql.startswith('INSERT')]
        self.assertTrue(any('mc_syn.policy_revisions' in sql for sql in inserts))
        self.assertEqual(connection.commits,1)

    def test_audit_review_is_separate_from_data_write(self):
        policy=self.authority.policies['syn-tenant-1']
        connection=RecordingConnection(policy_digest=fingerprint(asdict(policy)))
        with self.assertRaises(PermissionError):
            with self.store(connection).transaction('syn-tenant-1',session_ref('data_writer'),1) as tx:
                tx.read_security_decisions()
        with self.assertRaises(PermissionError):
            with self.store(connection).transaction('syn-tenant-1',session_ref('audit_reviewer'),1) as tx:
                self.assertEqual(tx.read_security_decisions(),[])
                registry,_,_=fixtures()
                tx.append_registry(registry,0,'syn-key')

    def test_exact_replay_has_no_new_insert(self):
        policy=self.authority.policies['syn-tenant-1']
        connection=RecordingConnection(policy_digest=fingerprint(asdict(policy)))
        with self.store(connection).transaction('syn-tenant-1',session_ref('data_writer'),1) as tx:
            tx._receipt=Mock(return_value=True)
            tx._insert=Mock(side_effect=AssertionError('Replay must not insert'))
            registry,_,_=fixtures()
            self.assertEqual(tx.append_registry(registry,0,'syn-key'),'duplicate')
            tx._insert.assert_not_called()

    def test_local_connector_rejects_remote_or_nonprivate_paths(self):
        for path in ('https://example.invalid','/workspace','/tmp'):
            with self.assertRaises((ValueError,RuntimeError)):
                local_connection(path,'syn-proof','syn-runtime')


class ApprovalProofTests(unittest.TestCase):
    def setUp(self):
        self.authority,self.custody=authority_fixture()
        self.registry,_,_=fixtures()
        self.tx=SyntheticTransaction(None,self.authority,self.custody,'syn-tenant-1',session_ref('approval_issuer'),1)
        self.rows=[]
        self.revocations=[]
        self.author=self.authority.sessions[session_ref('data_writer')].principal.subject_reference
        self.tx._auth=lambda action,resource,context=True: self.authority.authorize(self.tx.session,self.tx.tenant,1,action,resource)
        self.tx.get_registry=lambda resource,revision: self.registry if revision==1 else None
        def select(table,**keys):
            if table=='approval_evidence': return [row for row in self.rows if row['evidence_reference']==keys['evidence_reference']]
            if table=='approval_revocations': return self.revocations
            if table=='registry_revisions': return [{'actor_reference':self.author}]
            raise AssertionError(table)
        self.tx._select=select
        def insert(table,row):
            if table=='approval_evidence': self.rows.append({'tenant_reference':'syn-tenant-1',**row,'dataset':'synthetic'})
            elif table=='approval_revocations': self.revocations.append(row)
            else: raise AssertionError(table)
        self.tx._insert=insert
        self.tx._audit=Mock()

    def test_issue_exact_revision_verify_and_revoke(self):
        self.tx.issue_approval('syn-registry-1',1,'syn-proof-1')
        evidence=self.tx.resolve_approval('syn-proof-1')
        self.assertIsNotNone(evidence)
        evidence.approval.validate('syn-registry-1',1,self.registry.record.payload())
        record2=replace(self.registry.record,revision=2)
        with self.assertRaises(ValueError): evidence.approval.validate('syn-registry-1',2,record2.payload())
        self.assertEqual(self.tx.revoke_approval('syn-proof-1'),'revoked')
        self.assertIsNone(self.tx.resolve_approval('syn-proof-1'))
        self.assertEqual(self.tx.revoke_approval('syn-proof-1'),'duplicate')
        self.assertEqual(len(self.revocations),1)

    def test_self_approval_and_wrong_roles_deny(self):
        self.author=self.authority.sessions[session_ref('approval_issuer')].principal.subject_reference
        with self.assertRaises(PermissionError): self.tx.issue_approval('syn-registry-1',1,'syn-proof-1')
        self.tx.failed=False
        self.tx.session=session_ref('service_writer')
        with self.assertRaises(PermissionError): self.tx.issue_approval('syn-registry-1',1,'syn-proof-1')
        self.assertEqual(self.rows,[])

    def test_unknown_revoked_issuer_and_tamper_fail_closed(self):
        self.assertIsNone(self.tx.resolve_approval('syn-missing'))
        self.tx.issue_approval('syn-registry-1',1,'syn-proof-1')
        original=deepcopy(self.rows[0])
        self.rows[0]['content_digest']='0'*64
        self.assertIsNone(self.tx.resolve_approval('syn-proof-1'))
        self.rows[0]=original
        issuer=session_ref('approval_issuer')
        self.authority.sessions.pop(issuer)
        # A separate valid verifier session cannot resurrect a revoked issuer.
        self.authority2,self.custody2=authority_fixture()
        self.authority.sessions['syn-verifier']=self.authority2.sessions[issuer]
        self.tx.session='syn-verifier'
        self.authority.sessions['syn-verifier']=replace(self.authority.sessions['syn-verifier'],principal=replace(self.authority.sessions['syn-verifier'].principal,subject_reference='syn-different-verifier'))
        self.assertIsNone(self.tx.resolve_approval('syn-proof-1'))

    def test_expired_signed_evidence_is_rejected(self):
        self.tx.issue_approval('syn-registry-1',1,'syn-proof-1')
        row=self.rows[0]
        row['valid_from']=datetime.now(timezone.utc)-timedelta(minutes=10)
        row['expires_at']=datetime.now(timezone.utc)-timedelta(minutes=1)
        signed={key:value for key,value in row.items() if key not in ('dataset','proof_reference')}
        row['proof_reference']=json.dumps(self.custody.seal(signed))
        self.assertIsNone(self.tx.resolve_approval('syn-proof-1'))
        with self.assertRaises(ValueError):
            self.tx.issue_approval('syn-registry-1',1,'syn-proof-2',timedelta(days=1))

    def test_fresh_custody_cannot_verify_previous_proof(self):
        self.tx.issue_approval('syn-registry-1',1,'syn-proof-1')
        self.tx.custody=SyntheticEvidenceCustody(self.authority,session_ref('signing_custodian'),'syn-tenant-1',1)
        self.assertIsNone(self.tx.resolve_approval('syn-proof-1'))


class ArchiveProofTests(unittest.TestCase):
    def setUp(self):
        self.authority,self.custody=authority_fixture()
        payload={'format':'syn-postgres-export-v1','dataset':'synthetic','tenant':'syn-tenant-1',
                 'migration_checksum':migration_checksum(),'tables':snapshot_tables(self.authority)}
        self.archive={'payload':payload,'checksum':fingerprint(payload),'proof':self.custody.seal(payload)}

    def test_roundtrip_exclusive_export_and_no_key_material(self):
        validate_archive(self.archive,self.custody)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'synthetic.json'
            write_archive(path,self.archive,self.custody)
            self.assertEqual(read_archive(path,self.custody),self.archive)
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            self.assertNotIn(self.custody._key.hex(),path.read_text())
            original=path.read_bytes()
            with self.assertRaises(FileExistsError): write_archive(path,self.archive,self.custody)
            self.assertEqual(path.read_bytes(),original)

    def test_tamper_checksum_and_recomputed_checksum_still_deny(self):
        damaged=deepcopy(self.archive)
        damaged['payload']['tables']['registry_heads'][0]['revision']=2
        with self.assertRaises(ValueError): validate_archive(damaged,self.custody)
        damaged['checksum']=fingerprint(damaged['payload'])
        with self.assertRaises(ValueError): validate_archive(damaged,self.custody)

    def test_structural_corruption_even_if_signed_is_rejected(self):
        for table,column,value in (
                ('registry_revisions','tenant_reference','syn-tenant-2'),
                ('registry_heads','revision',2),('journey_events','active',True),
                ('packet_revisions','registry_revision',2),
                ('journey_events','previous_digest','0'*64),
                ('idempotency_receipts','payload_digest','0'*64)):
            payload=deepcopy(self.archive['payload'])
            payload['tables'][table][0][column]=value
            with self.subTest(table=table,column=column), self.assertRaises((ValueError,KeyError)):
                validate_payload(payload,self.custody)

    def test_export_interruption_leaves_no_partial_published_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'synthetic.json'
            with patch('mission_control.synthetic_archive.os.fsync',side_effect=OSError('synthetic interruption')), self.assertRaises(OSError):
                write_archive(path,self.archive,self.custody)
            self.assertFalse(path.exists())
            self.assertEqual(list(Path(folder).iterdir()),[])

    def test_restore_requires_empty_target_exact_tenant_and_explicit_commit(self):
        tx=SyntheticTransaction(None,self.authority,self.custody,'syn-tenant-1',session_ref('migration_operator'),1)
        staging={name:[] for name in ENTITIES}
        tx._select=lambda table,**keys: staging[table]
        tx._insert=lambda table,row: staging[table].append({'tenant_reference':tx.tenant,**row,'dataset':'synthetic'})
        restore_snapshot(tx,self.archive,self.custody)
        self.assertFalse(tx.commit_requested)
        self.assertEqual(len(staging['registry_revisions']),1)
        self.assertEqual(len(staging['journey_events']),1)
        self.assertEqual(len(staging['security_decisions']),1)
        with self.assertRaises(ValueError): restore_snapshot(tx,self.archive,self.custody)
        tx.tenant='syn-tenant-2'
        tx.session=session_ref('migration_operator','syn-tenant-2')
        with self.assertRaises(PermissionError): restore_snapshot(tx,self.archive,self.custody)

    def test_malformed_duplicate_json_archive_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'bad.json'
            path.write_text('{"payload":{},"payload":{}}')
            with self.assertRaises(ValueError): read_archive(path,self.custody)


class MigrationDefinitionTests(unittest.TestCase):
    def test_all_fourteen_entities_have_rls_and_tenant_keys(self):
        sql=SQL_PATH.read_text()
        for name in ENTITIES:
            self.assertIn('CREATE TABLE mc_syn.'+name+' (',sql)
            self.assertIn('ALTER TABLE mc_syn.'+name+' FORCE ROW LEVEL SECURITY;',sql)
        self.assertEqual(sql.count('CREATE TABLE mc_syn.'),14)
        self.assertIn('NOBYPASSRLS',sql)
        self.assertNotIn('GRANT DELETE',sql)
        self.assertNotIn('GRANT TRUNCATE',sql)
        self.assertIn("CHECK (active = false)",sql)
        self.assertIn("CHECK (state IN ('draft','inactive'))",sql)

    def test_migration_is_not_automatic_and_denies_without_authority(self):
        factory=Mock()
        with self.assertRaises(PermissionError): apply_local_migration(factory)
        factory.assert_not_called()
        authority,_=authority_fixture()
        with self.assertRaises(PermissionError):
            apply_local_migration(factory,authority,session_ref('data_writer'),'syn-tenant-1',1)
        factory.assert_not_called()
