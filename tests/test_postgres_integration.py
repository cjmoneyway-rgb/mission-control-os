"""Real PostgreSQL tests, explicitly UNVERIFIED when existing prerequisites lack.

Never installs software or uses a supplied/cloud DSN. When tools are present,
starts ONLY its own disposable instance on a private local Unix socket, with TCP
disabled. Local trust auth is limited to this synthetic disposable cluster.
Explicit manual CI mode instead uses the job-owned loopback service through the
GitHub-hosted guard and job-generated credentials; setup errors cannot skip tests.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
import importlib.util
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import threading
import unittest
import uuid

from mission_control.registry_persistence import ConflictError
from mission_control.synthetic_archive import export_snapshot, restore_snapshot, validate_archive
from mission_control.synthetic_identity import fingerprint
from mission_control.synthetic_postgres import LocalSyntheticStore, apply_local_migration, local_connection, _query
from tests.synthetic_postgres_support import authority_fixture, session_ref
from tests.test_registry_foundation import fixtures


def binary(name):
    found=shutil.which(name)
    if found: return found
    return next((str(path) for path in Path('/usr/lib/postgresql').glob('*/bin/'+name) if os.access(path,os.X_OK)),None)


INITDB,PG_CTL=binary('initdb'),binary('pg_ctl')
DRIVER=importlib.util.find_spec('psycopg') is not None
CI_SERVICE=os.environ.get('MC_SYN_CI_POSTGRES')=='1'
AVAILABLE=CI_SERVICE or bool(INITDB and PG_CTL and DRIVER and os.name=='posix' and os.geteuid()!=0)
REASON='UNVERIFIED PostgreSQL integration: requires existing initdb, pg_ctl, psycopg 3, POSIX, and non-root user; no install/fallback'


@unittest.skipUnless(AVAILABLE,REASON)
class PostgreSQLIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.psycopg=psycopg
        if CI_SERVICE:
            from scripts.ci_postgres import service_connection
            with service_connection('postgres','syn-admin') as connection:
                if connection.execute("SHOW server_version_num").fetchone()[0] != "170011":
                    raise RuntimeError("Unexpected disposable PostgreSQL version")
            return
        cls.temporary=tempfile.TemporaryDirectory(prefix='mc-syn-pg-',dir='/tmp')
        root=Path(cls.temporary.name)
        cls.data=root/'data'
        cls.socket=root/'socket'
        cls.socket.mkdir(mode=0o700)
        try:
            subprocess.run([INITDB,'-D',str(cls.data),'-U','syn-admin','--auth-local=trust','--auth-host=reject','--no-locale'],check=True,capture_output=True,text=True)
            options='-k '+shlex.quote(str(cls.socket))+" -c listen_addresses='' -c unix_socket_permissions=0700"
            subprocess.run([PG_CTL,'-D',str(cls.data),'-l',str(root/'server.log'),'-o',options,'-w','start'],check=True,capture_output=True,text=True)
        except BaseException:
            try:
                subprocess.run([PG_CTL,'-D',str(cls.data),'-m','immediate','-w','stop'],check=False,capture_output=True,text=True)
            finally:
                cls.temporary.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        if CI_SERVICE:
            return
        try:
            subprocess.run([PG_CTL,'-D',str(cls.data),'-m','fast','-w','stop'],check=True,capture_output=True,text=True)
        finally:
            cls.temporary.cleanup()

    def new_store(self):
        database='syn-proof-'+uuid.uuid4().hex
        if CI_SERVICE:
            from scripts.ci_postgres import service_connection, credentials
            metadata=lambda:service_connection('postgres','syn-admin',autocommit=True)
            admin=lambda:service_connection(database,'syn-admin')
            runtime=lambda:service_connection(database,'syn-runtime')
        else:
            metadata=lambda:self.psycopg.connect(host=str(self.socket),dbname='postgres',user='syn-admin',autocommit=True)
            admin=lambda:local_connection(self.socket,database,'syn-admin')
            runtime=lambda:local_connection(self.socket,database,'syn-runtime')
        with metadata() as connection:
            connection.execute(self.psycopg.sql.SQL('CREATE DATABASE {}').format(self.psycopg.sql.Identifier(database)))
        apply_local_migration(admin,self.authority,session_ref('migration_operator'),'syn-tenant-1',1)
        if CI_SERVICE:
            with admin() as connection:
                connection.execute(self.psycopg.sql.SQL('ALTER ROLE {} PASSWORD {}').format(
                    self.psycopg.sql.Identifier('syn-runtime'),self.psycopg.sql.Literal(credentials()['runtime_password'])))
        store=LocalSyntheticStore(runtime,self.authority,self.custody)
        return store,admin

    def setUp(self):
        self.authority,self.custody=authority_fixture()
        self.store,self.admin=self.new_store()
        self.registry,self.packet,self.event=fixtures()
        for tenant in ('syn-tenant-1','syn-tenant-2'):
            with self.store.transaction(tenant,session_ref('policy_admin',tenant),1) as tx:
                tx.bootstrap_policy()
                tx.commit()

    def write_fixture(self,store=None):
        store=store or self.store
        with store.transaction('syn-tenant-1',session_ref('data_writer'),1) as tx:
            tx.append_registry(self.registry,0,'syn-registry-key')
            tx.append_packet(self.packet,0,'syn-packet-key')
            tx.append_event(self.event,0,'syn-event-key')
            tx.commit()

    def test_migration_reapplication_and_fourteen_tables(self):
        self.assertEqual(apply_local_migration(self.admin,self.authority,session_ref('migration_operator'),'syn-tenant-1',1),'already_applied')
        with self.admin() as connection:
            rows,_=_query(connection,"SELECT count(*) AS total FROM pg_tables WHERE schemaname='mc_syn'")
            self.assertEqual(rows[0]['total'],14)

    def test_rollback_without_commit_and_after_commit_request(self):
        for interrupted in (False,True):
            try:
                with self.store.transaction('syn-tenant-1',session_ref('data_writer'),1) as tx:
                    tx.append_registry(self.registry,0,'syn-key')
                    if interrupted:
                        tx.commit()
                        raise ValueError('synthetic interruption')
            except ValueError: pass
            with self.store.transaction('syn-tenant-1',session_ref('data_writer'),1) as tx:
                self.assertIsNone(tx.get_registry('syn-registry-1',1))
                self.assertIsNone(tx.get_receipt('registry.append_draft','syn-key'))

    def test_persistence_exact_retries_and_duplicate_event_rejection(self):
        self.write_fixture()
        with self.store.transaction('syn-tenant-1',session_ref('data_writer'),1) as tx:
            self.assertEqual(tx.get_registry('syn-registry-1',1),self.registry)
            self.assertEqual(tx.get_packet('syn-packet-1',1),self.packet)
            self.assertEqual(tx.get_event('syn-event-1'),self.event)
            self.assertEqual(tx.append_event(self.event,0,'syn-event-key'),'duplicate')
            tx.commit()
        with self.assertRaises(ConflictError):
            with self.store.transaction('syn-tenant-1',session_ref('data_writer'),1) as tx:
                tx.append_event(self.event,0,'syn-other-key')
                tx.commit()
        changed=replace(self.registry,record=replace(self.registry.record,revision=2),previous_revision=1)
        from mission_control.contracts import digest
        changed=replace(changed,content_digest=digest(changed.record.payload()))
        with self.assertRaises(ConflictError):
            with self.store.transaction('syn-tenant-1',session_ref('data_writer'),1) as tx:
                tx.append_registry(changed,1,'syn-registry-key')
                tx.commit()

    def test_swallowed_stale_head_conflict_rolls_back_partial_revision(self):
        from mission_control.contracts import digest
        self.write_fixture()
        record3=replace(self.registry.record,revision=3)
        revision3=replace(self.registry,record=record3,previous_revision=2,content_digest=digest(record3.payload()))
        with self.assertRaises(PermissionError):
            with self.store.transaction('syn-tenant-1',session_ref('data_writer'),1) as tx:
                try:
                    tx.append_registry(revision3,2,'syn-stale-key')
                except ConflictError:
                    pass
        with self.store.transaction('syn-tenant-1',session_ref('data_writer'),1) as tx:
            self.assertIsNone(tx.get_registry('syn-registry-1',3))
            self.assertIsNone(tx.get_receipt('registry.append_draft','syn-stale-key'))

    def test_two_writer_optimistic_concurrency(self):
        barrier=threading.Barrier(2)
        def write(key):
            try:
                with self.store.transaction('syn-tenant-1',session_ref('data_writer'),1) as tx:
                    barrier.wait(timeout=5)
                    tx.append_registry(self.registry,0,key)
                    tx.commit()
                return 'committed'
            except ConflictError: return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as executor:
            results=list(executor.map(write,('syn-race-1','syn-race-2')))
        self.assertCountEqual(results,['committed','conflict'])
        with self.store.transaction('syn-tenant-1',session_ref('data_writer'),1) as tx:
            self.assertIsNotNone(tx.get_registry('syn-registry-1',1))
            self.assertEqual(len(tx._select('idempotency_receipts')),1)

    def test_tenant_isolation_and_database_rls_default_deny(self):
        self.write_fixture()
        other=replace(self.registry,tenant_reference='syn-tenant-2')
        with self.store.transaction('syn-tenant-2',session_ref('data_writer','syn-tenant-2'),1) as tx:
            tx.append_registry(other,0,'syn-registry-key')
            tx.commit()
        with self.assertRaises(PermissionError):
            with self.store.transaction('syn-tenant-2',session_ref('data_writer'),1): pass
        with self.store.transaction('syn-tenant-1',session_ref('data_writer'),1) as tx:
            self.assertEqual(tx.get_registry('syn-registry-1',1).tenant_reference,'syn-tenant-1')
            self.assertEqual(_query(tx.connection,'SELECT * FROM mc_syn.registry_revisions WHERE tenant_reference=%s',('syn-tenant-2',))[0],[])
        connection=self.store.factory()
        try:
            self.assertEqual(_query(connection,'SELECT * FROM mc_syn.registry_revisions')[0],[])
        finally: connection.close()

    def test_approval_issue_revision_verification_and_revocation(self):
        self.write_fixture()
        with self.store.transaction('syn-tenant-1',session_ref('approval_issuer'),1) as tx:
            tx.issue_approval('syn-registry-1',1,'syn-proof-1')
            tx.commit()
        with self.store.transaction('syn-tenant-1',session_ref('approval_issuer'),1) as tx:
            evidence=tx.resolve_approval('syn-proof-1')
            self.assertEqual(evidence.approval.revision,1)
            with self.assertRaises(ValueError):
                evidence.approval.validate('syn-registry-1',2,replace(self.registry.record,revision=2).payload())
            tx.revoke_approval('syn-proof-1')
            self.assertIsNone(tx.resolve_approval('syn-proof-1'))
            tx.commit()
        with self.store.transaction('syn-tenant-1',session_ref('approval_issuer'),1) as tx:
            self.assertIsNone(tx.resolve_approval('syn-proof-1'))

    def test_service_identity_can_write_but_cannot_issue_approval(self):
        with self.store.transaction('syn-tenant-1',session_ref('service_writer'),1) as tx:
            tx.append_registry(self.registry,0,'syn-service-key')
            tx.commit()
        with self.assertRaises(PermissionError):
            with self.store.transaction('syn-tenant-1',session_ref('service_writer'),1) as tx:
                tx.issue_approval('syn-registry-1',1,'syn-proof-1')

    def test_export_restore_integrity_and_retry_after_restore(self):
        self.write_fixture()
        with self.store.transaction('syn-tenant-1',session_ref('approval_issuer'),1) as tx:
            tx.issue_approval('syn-registry-1',1,'syn-proof-1')
            tx.revoke_approval('syn-proof-1')
            tx.commit()
        with self.store.transaction('syn-tenant-1',session_ref('audit_reviewer'),1) as tx:
            archive=export_snapshot(tx,self.custody)
        validate_archive(archive,self.custody)
        restored,_=self.new_store()
        with restored.transaction('syn-tenant-1',session_ref('migration_operator'),1) as tx:
            restore_snapshot(tx,archive,self.custody)
            tx.commit()
        with restored.transaction('syn-tenant-1',session_ref('data_writer'),1) as tx:
            self.assertEqual(tx.get_event('syn-event-1'),self.event)
            self.assertEqual(tx.append_event(self.event,0,'syn-event-key'),'duplicate')
            tx.commit()
        with restored.transaction('syn-tenant-1',session_ref('approval_issuer'),1) as tx:
            self.assertIsNone(tx.resolve_approval('syn-proof-1'))

    def test_database_history_mutation_and_active_state_blocked(self):
        self.write_fixture()
        with self.assertRaises(RuntimeError):
            with self.store.transaction('syn-tenant-1',session_ref('data_writer'),1) as tx:
                _query(tx.connection,"UPDATE mc_syn.registry_revisions SET state='active'")
                tx.commit()
        with self.store.transaction('syn-tenant-1',session_ref('data_writer'),1) as tx:
            self.assertEqual(tx.get_registry('syn-registry-1',1).record.state,'draft')
