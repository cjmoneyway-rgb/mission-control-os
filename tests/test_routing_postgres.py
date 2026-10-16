"""Real Phase 1C PostgreSQL tests; same explicit disposable harness as Phase 1B.3."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import timedelta
import threading
import unittest
from unittest.mock import patch

from mission_control.department_routing import CENTRAL_VIEWS, derive_packets, seal
from mission_control.registry_persistence import ConflictError
from mission_control.routing_postgres import RoutingStore, apply_routing_migration
from mission_control.synthetic_archive import export_snapshot, restore_snapshot
from mission_control.synthetic_identity import SyntheticEvidenceCustody, fingerprint
from mission_control.synthetic_postgres import _query
from tests import test_postgres_integration as base_pg
from tests.synthetic_postgres_support import session_ref
from tests.routing_support import TENANT, contracts, reference_rows, routing_authority


@unittest.skipUnless(base_pg.AVAILABLE,base_pg.REASON)
class RoutingPostgreSQLTests(unittest.TestCase):
    setUpClass=classmethod(base_pg.PostgreSQLIntegrationTests.setUpClass.__func__)
    tearDownClass=classmethod(base_pg.PostgreSQLIntegrationTests.tearDownClass.__func__)

    def setUp(self):
        self.authority,self.custody=routing_authority()
        base,self.admin=base_pg.PostgreSQLIntegrationTests.new_store(self)
        apply_routing_migration(self.admin,self.authority,session_ref('migration_operator'),TENANT,1)
        self.store=RoutingStore(base.factory,self.authority,self.custody)
        self.departments,self.rule,self.intake=contracts()
        self.expected=derive_packets(self.intake,self.rule,{d.department_id:d for d in self.departments},'syn-routing-key')
        for tenant in (TENANT,'syn-tenant-2'):
            with self.tx('policy_admin',tenant) as tx:
                tx.bootstrap_policy()
                for kind,reference,parent in reference_rows(tenant):
                    tx.register_reference(kind,reference,parent)
                tx.commit()
        with self.tx() as tx:
            for department in self.departments: tx.append_department(department)
            tx.append_rule(self.rule)
            tx.commit()

    def tx(self,role='data_writer',tenant=TENANT):
        return self.store.transaction(tenant,session_ref(role,tenant),1)

    def approve(self,lifetime=timedelta(minutes=5)):
        with self.tx('approval_issuer') as tx:
            for record in self.departments:
                tx.issue_routing_approval('department',record.department_id,1,record.approval_reference,lifetime)
            tx.issue_routing_approval('rule',self.rule.rule_id,1,self.rule.approval_reference,lifetime)
            tx.commit()

    def route(self,key='syn-routing-key',intake=None,commit=True):
        with self.tx() as tx:
            packets=tx.simulate_routing(intake or self.intake,self.rule.rule_id,1,key)
            if commit: tx.commit()
        return packets

    def count(self,table):
        with self.admin() as connection:
            return _query(connection,'SELECT count(*) AS count FROM mc_syn.'+table)[0][0]['count']

    def test_forward_migration_checksum_and_reapplication(self):
        self.assertEqual(apply_routing_migration(self.admin,self.authority,session_ref('migration_operator'),TENANT,1),'already_applied')
        with patch('mission_control.routing_postgres.SQL_PATH') as path:
            path.read_text.return_value='-- changed synthetic migration'
            with self.assertRaises(ConflictError):
                apply_routing_migration(self.admin,self.authority,session_ref('migration_operator'),TENANT,1)
        with self.admin() as connection:
            rows,_=_query(connection,"SELECT count(*) AS count FROM pg_tables WHERE schemaname='mc_syn'")
            self.assertEqual(rows[0]['count'],24)

    def test_multi_recipient_inactive_routing_and_oversight_projections(self):
        self.approve()
        packets=self.route()
        self.assertEqual(packets,self.expected)
        for packet in packets:
            with self.tx('data_reader') as tx:
                for audience in ('command','control','governance'):
                    view=tx.view_packet(packet.packet_id,1,audience)
                    self.assertEqual(view['state'],'inactive')
                    self.assertNotIn('required_action',view)
                    self.assertNotIn('approval_reference',view)
                self.assertEqual(tx.view_packet(packet.packet_id,1,'executive')['required_action'],'syn-action-review')
        with self.tx() as tx:
            history=tx.read_journey(self.intake.event_id)
            self.assertEqual([event['event'] for event in history],['syn-intake','syn-packet-proposed','syn-packet-proposed'])

    def test_duplicate_intake_same_key_exact_retry_no_new_records(self):
        self.approve(); first=self.route()
        before={name:self.count(name) for name in ('routing_records','routing_events','routing_receipts','security_decisions')}
        self.assertEqual(self.route(),first)
        self.assertEqual(before,{name:self.count(name) for name in before})

    def test_duplicate_event_different_key_rejected(self):
        self.approve();self.route()
        with self.assertRaises(ConflictError): self.route('syn-second-key')
        self.assertEqual(self.count('routing_receipts'),1)

    def test_changed_payload_same_idempotency_key_fails(self):
        self.approve();self.route()
        with self.assertRaises(ConflictError): self.route(intake=seal(replace(self.intake,source_reference='syn-source-other')))
        self.assertEqual(self.count('routing_events'),3)

    def test_missing_approval_cannot_persist_intake_or_packet(self):
        with self.assertRaises(PermissionError): self.route()
        self.assertEqual(self.count('routing_receipts'),0)
        self.assertEqual(self.count('routing_events'),0)

    def test_department_approval_required_independently(self):
        with self.tx('approval_issuer') as tx:
            tx.issue_routing_approval('rule',self.rule.rule_id,1,self.rule.approval_reference)
            tx.commit()
        with self.assertRaises(PermissionError): self.route()
        self.assertEqual(self.count('routing_events'),0)

    def test_revoked_approval_and_replay_fail_closed(self):
        self.approve();self.route()
        with self.tx('approval_issuer') as tx:
            self.assertEqual(tx.revoke_routing_approval(self.departments[0].approval_reference),'revoked')
            self.assertEqual(tx.revoke_routing_approval(self.departments[0].approval_reference),'duplicate')
            tx.commit()
        with self.assertRaises(PermissionError): self.route()

    def test_expired_evidence_fails(self):
        self.approve(timedelta(microseconds=1))
        with self.assertRaises(PermissionError): self.route()
        self.assertEqual(self.count('routing_receipts'),0)

    def test_unverifiable_signing_custody_fails(self):
        self.approve()
        self.store.custody=SyntheticEvidenceCustody(self.authority,session_ref('signing_custodian'),TENANT,1)
        with self.assertRaises(PermissionError): self.route()

    def test_revoked_issuing_identity_fails(self):
        self.approve()
        key=session_ref('approval_issuer');original=self.authority.sessions[key]
        self.authority.sessions[key]=replace(original,principal=replace(original.principal,revoked=True))
        with self.assertRaises(PermissionError): self.route()

    def test_self_approval_forbidden_even_with_combined_roles(self):
        key=session_ref('approval_issuer');issuer=self.authority.sessions[key]
        # A trusted fixture assigning issuer and writer roles must still fail self approval.
        self.authority.sessions[key]=replace(issuer,principal=replace(issuer.principal,subject_reference='syn-data_writer-'+TENANT,roles=('approval_issuer','data_writer')))
        with self.assertRaises(PermissionError):
            with self.tx('approval_issuer') as tx:
                tx.issue_routing_approval('department',self.departments[0].department_id,1,self.departments[0].approval_reference)
                tx.commit()

    def test_visibility_does_not_grant_routing_approval_or_writes(self):
        with self.assertRaises(PermissionError):
            with self.tx('data_reader') as tx:
                tx.simulate_routing(self.intake,self.rule.rule_id,1,'syn-routing-key')
        with self.assertRaises(PermissionError):
            with self.tx('data_reader') as tx:
                tx.issue_routing_approval('rule',self.rule.rule_id,1,self.rule.approval_reference)

    def test_default_deny_visibility_without_exact_grant(self):
        self.approve();packet=self.route()[0]
        with self.assertRaises(PermissionError):
            with self.tx() as tx: tx.view_packet(packet.packet_id,1,'command')
        with self.assertRaises(PermissionError):
            with self.tx('data_reader') as tx: tx.view_packet(packet.packet_id,1,'unknown')

    def test_team_visibility_requires_executive_distribution(self):
        self.approve();packet=self.route()[0]
        with self.assertRaises(PermissionError):
            with self.tx('data_reader') as tx: tx.view_packet(packet.packet_id,1,'team','syn-team-alpha')
        with self.tx('data_reader') as tx:
            self.assertEqual(tx.distribute_team_visibility(packet.packet_id,1,'syn-team-alpha','syn-distribution-1'),'appended')
            tx.commit()
        with self.tx('data_reader') as tx:
            self.assertEqual(tx.view_packet(packet.packet_id,1,'team','syn-team-alpha')['audience'],'team')
            self.assertEqual(tx.distribute_team_visibility(packet.packet_id,1,'syn-team-alpha','syn-distribution-1'),'duplicate')
            tx.commit()

    def test_central_router_and_wrong_executive_cannot_assign_teams(self):
        self.approve();packet=self.route()[0]
        for role,team in (('data_writer','syn-team-alpha'),('service_writer','syn-team-alpha'),('data_reader','syn-team-beta')):
            with self.subTest(role=role,team=team),self.assertRaises(PermissionError):
                with self.tx(role) as tx:
                    tx.distribute_team_visibility(packet.packet_id,1,team,'syn-distribution-1')
                    tx.commit()

    def test_claimed_executive_without_subject_binding_fails(self):
        self.approve();packet=self.route()[0]
        key=session_ref('data_reader');session=self.authority.sessions[key]
        self.authority.sessions[key]=replace(session,principal=replace(session.principal,subject_reference='syn-other-subject'))
        with self.assertRaises(PermissionError):
            with self.tx('data_reader') as tx: tx.view_packet(packet.packet_id,1,'executive')

    def test_cross_tenant_intake_and_packet_read_denied(self):
        self.approve();packet=self.route()[0]
        with self.assertRaises(PermissionError): self.route(intake=seal(replace(self.intake,tenant_reference='syn-tenant-2')))
        with self.assertRaises(PermissionError):
            with self.tx('data_reader','syn-tenant-2') as tx: tx.view_packet(packet.packet_id,1,'command')
        with self.assertRaises(PermissionError):
            with self.store.transaction('syn-tenant-2',session_ref('data_writer'),1): pass

    def test_all_new_tables_rls_default_deny_and_cross_tenant_filter(self):
        self.approve();self.route()
        from mission_control.routing_postgres import COLUMNS
        connection=self.store.factory()
        try:
            for table in COLUMNS:
                self.assertEqual(_query(connection,'SELECT * FROM mc_syn.'+table)[0],[])
            connection.rollback()
        finally: connection.close()
        with self.tx(tenant='syn-tenant-2') as tx:
            for table in COLUMNS:
                rows,_=_query(tx.connection,'SELECT * FROM mc_syn.'+table+' WHERE tenant_reference=%s',(TENANT,))
                self.assertEqual(rows,[])

    def test_canonical_and_alias_collisions_roll_back_revision_and_head(self):
        first,second=self.departments
        for field,value in (('canonical_name',first.canonical_name),('aliases',(first.aliases[0],)),('canonical_name',first.aliases[0])):
            with self.subTest(field=field,value=value),self.assertRaises(ConflictError):
                with self.tx() as tx:
                    tx.append_department(seal(replace(second,revision=2,**{field:value})),1)
                    tx.commit()
        with self.tx() as tx: self.assertEqual(tx._head('department',second.department_id),1)

    def test_removed_alias_cannot_be_reassigned(self):
        first,second=self.departments
        with self.tx() as tx:
            tx.append_department(seal(replace(first,revision=2,aliases=())),1);tx.commit()
        with self.assertRaises(ConflictError):
            with self.tx() as tx:
                tx.append_department(seal(replace(second,revision=2,aliases=first.aliases)),1);tx.commit()

    def test_stale_department_revision_invalidates_routing(self):
        self.approve()
        with self.tx() as tx:
            tx.append_department(seal(replace(self.departments[0],revision=2)),1);tx.commit()
        with self.assertRaises(PermissionError): self.route()

    def test_rule_revision_needs_new_exact_approval(self):
        self.approve()
        rule=seal(replace(self.rule,revision=2))
        with self.tx() as tx: tx.append_rule(rule,1);tx.commit()
        with self.assertRaises(PermissionError): self.route()
        with self.assertRaises(PermissionError):
            with self.tx() as tx: tx.simulate_routing(self.intake,self.rule.rule_id,2,'syn-routing-key')

    def test_unresolved_references_and_policy_revision_rejected(self):
        for record in (seal(replace(self.departments[0],revision=2,mandate='syn-missing')),
                       seal(replace(self.departments[0],revision=2,team_references=('syn-team-beta',)))):
            with self.assertRaises(PermissionError):
                with self.tx() as tx: tx.append_department(record,1);tx.commit()
        with self.assertRaises(PermissionError):
            with self.tx() as tx: tx.append_rule(seal(replace(self.rule,revision=2,policy_revision=2)),1);tx.commit()

    def test_synthetic_policy_denial_and_stale_policy_fail_closed(self):
        self.approve()
        policy=self.authority.policies[TENANT]
        self.authority.policies[TENANT]=replace(policy,grants=tuple(grant for grant in policy.grants if grant.action!='packet.route_simulate'))
        with self.assertRaises(PermissionError): self.route()
        self.assertEqual(self.count('routing_events'),0)

    def test_optimistic_concurrent_routing_has_one_intake_and_packet_set(self):
        self.approve();barrier=threading.Barrier(2)
        def route(_):
            try:
                with self.tx() as tx:
                    barrier.wait(timeout=10)
                    tx.simulate_routing(self.intake,self.rule.rule_id,1,'syn-routing-key');tx.commit()
                return 'committed'
            except ConflictError: return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertCountEqual(list(executor.map(route,(1,2))),['committed','conflict'])
        self.assertEqual(self.count('routing_receipts'),1)
        self.assertEqual(self.count('routing_events'),3)
        self.assertEqual(self.route(),self.expected)

    def test_routing_rollback_on_interruption_or_missing_commit(self):
        self.approve();self.route(commit=False)
        self.assertEqual(self.count('routing_events'),0)
        with self.assertRaises(ValueError):
            with self.tx() as tx:
                tx.simulate_routing(self.intake,self.rule.rule_id,1,'syn-routing-key');tx.commit()
                raise ValueError('Synthetic interruption')
        self.assertEqual(self.count('routing_receipts'),0)

    def test_swallowed_failure_dooms_all_partial_work(self):
        self.approve()
        with self.assertRaises(PermissionError):
            with self.tx() as tx:
                tx.simulate_routing(self.intake,self.rule.rule_id,1,'syn-routing-key')
                try: tx.append_department(seal(replace(self.departments[0],revision=2,mandate='syn-missing')),1)
                except PermissionError: pass
        self.assertEqual(self.count('routing_events'),0)

    def test_original_classification_and_append_only_journey_survive_enrichment(self):
        self.approve();packet=self.route()[0]
        with self.tx() as tx: original=tx.read_journey(self.intake.event_id)
        changed=seal(replace(packet,revision=2,current_classification='syn-classification-derived',
                             outcome_references=('syn-outcome-1',),handoff_references=('syn-handoff-1',)))
        with self.tx() as tx:
            tx.append_packet_revision(changed,1,'syn-enrichment-1');tx.commit()
        with self.tx() as tx:
            self.assertEqual(tx.append_packet_revision(changed,1,'syn-enrichment-1'),'duplicate');tx.commit()
        with self.tx() as tx:
            history=tx.read_journey(self.intake.event_id)
            self.assertEqual(history[:3],original)
            self.assertEqual(len(history),4)
            self.assertTrue(all(event['original_classification']==self.intake.original_classification for event in history))
            self.assertEqual(tx._get('packet',packet.packet_id,1),packet)
            self.assertEqual(tx._get('packet',packet.packet_id,2),changed)

    def test_invalid_packet_revision_and_identity_changes_cannot_commit(self):
        self.approve();packet=self.route()[0]
        for fields in ({'original_classification':'syn-classification-derived'}, {'source_event_reference':'syn-other'},
                       {'executive_reference':'syn-executive-beta'},{'state':'active'},{'revision':3}):
            changed=seal(replace(packet,revision=2,**{key:value for key,value in fields.items() if key!='revision'})) if 'revision' not in fields else seal(replace(packet,revision=3))
            with self.subTest(fields=fields),self.assertRaises((PermissionError,ValueError,ConflictError)):
                with self.tx() as tx: tx.append_packet_revision(changed,1,'syn-enrichment-1');tx.commit()
        self.assertEqual(self.count('routing_events'),3)

    def test_prior_outcomes_cannot_be_erased(self):
        self.approve();packet=self.route()[0]
        second=seal(replace(packet,revision=2,outcome_references=('syn-outcome-1',)))
        with self.tx() as tx: tx.append_packet_revision(second,1,'syn-enrichment-1');tx.commit()
        third=seal(replace(second,revision=3,outcome_references=()))
        with self.assertRaises(PermissionError):
            with self.tx() as tx: tx.append_packet_revision(third,2,'syn-enrichment-2');tx.commit()

    def test_database_constraints_forbid_active_and_history_mutation(self):
        self.approve();packet=self.route()[0]
        for table in ('routing_records','routing_events','routing_receipts','routing_evidence','routing_references'):
            with self.subTest(table=table),self.assertRaises(RuntimeError):
                with self.tx() as tx:
                    _query(tx.connection,'UPDATE mc_syn.'+table+" SET dataset='synthetic'");tx.commit()
        with self.assertRaises(RuntimeError):
            with self.tx() as tx:
                _query(tx.connection,"UPDATE mc_syn.routing_heads SET revision=revision+2 WHERE kind='packet'");tx.commit()
        with self.assertRaises(RuntimeError):
            with self.tx() as tx:
                row=tx._rows('routing_records',kind='packet',reference=packet.packet_id,revision=1)[0]
                row={key:value for key,value in row.items() if key not in ('tenant_reference','dataset')}
                row['state']='active';row['reference']='syn-new-packet'
                tx._put('routing_records',**row);tx.commit()

    def test_cross_tenant_foreign_keys_fail_even_with_owner_connection(self):
        self.approve();packet=self.route()[0]
        with self.admin() as connection:
            with self.assertRaises(self.psycopg.IntegrityError):
                connection.execute("INSERT INTO mc_syn.routing_links SELECT 'syn-tenant-2',packet_reference,packet_revision,packet_kind,department_reference,department_revision,department_digest,department_kind,rule_reference,rule_revision,rule_digest,rule_kind,intake_reference,intake_revision,intake_kind,dataset FROM mc_syn.routing_links WHERE packet_reference=%s",(packet.packet_id,))
            connection.rollback()

    def test_old_archive_format_cannot_silently_omit_phase1c(self):
        for role in ('audit_reviewer','migration_operator'):
            with self.subTest(role=role),self.assertRaises(ValueError):
                with self.tx(role) as tx:
                    if role=='audit_reviewer': export_snapshot(tx,self.custody)
                    else: restore_snapshot(tx,{},self.custody)

    def test_no_external_provider_calls_or_operational_engine_delivery(self):
        self.approve()
        with patch('mission_control.providers.OpenAIProvider.classify',side_effect=AssertionError('External call forbidden')), \
             patch('mission_control.providers.OpenAIProvider.execute',side_effect=AssertionError('External call forbidden')), \
             patch('mission_control.engine.MissionControlOS.run',side_effect=AssertionError('Engine forbidden')):
            packets=self.route()
        self.assertTrue(all(packet.state=='inactive' for packet in packets))

    def test_minimized_audit_does_not_store_contract_contents(self):
        self.approve();self.route()
        with self.tx('audit_reviewer') as tx:
            rows=tx.read_security_decisions()
        for row in rows:
            self.assertNotIn('payload',row)
            self.assertNotIn('original_classification',row)
            self.assertNotIn('proof',row)
            self.assertIn(row['reason_code'],('synthetic_validated',))

    def test_same_names_in_different_tenant_are_independent(self):
        departments,rule,_=contracts('syn-tenant-2')
        with self.tx(tenant='syn-tenant-2') as tx:
            for department in departments: tx.append_department(department)
            tx.append_rule(rule);tx.commit()
        self.assertEqual(self.count('routing_names'),8)

    def test_failed_forward_migration_rolls_back_extension_and_ledger(self):
        _,admin=base_pg.PostgreSQLIntegrationTests.new_store(self)
        from mission_control.routing_postgres import SQL_PATH
        sql=SQL_PATH.read_text()
        with patch('mission_control.routing_postgres.SQL_PATH') as path:
            path.read_text.return_value=sql+'\nSELECT syn_missing_function();'
            with self.assertRaises(self.psycopg.Error):
                apply_routing_migration(admin,self.authority,session_ref('migration_operator'),TENANT,1)
        with admin() as connection:
            self.assertIsNone(connection.execute("SELECT to_regclass('mc_syn.routing_records')").fetchone()[0])
            self.assertEqual(connection.execute("SELECT count(*) FROM mc_syn.schema_migrations WHERE migration_id='syn-postgresql-0002'").fetchone()[0],0)
        self.assertEqual(apply_routing_migration(admin,self.authority,session_ref('migration_operator'),TENANT,1),'applied')

    def test_concurrent_registry_revision_compare_and_swap(self):
        barrier=threading.Barrier(2)
        department=seal(replace(self.departments[0],revision=2))
        def append(_):
            try:
                with self.tx() as tx:
                    barrier.wait(timeout=10);tx.append_department(department,1);tx.commit()
                return 'committed'
            except ConflictError: return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertCountEqual(list(executor.map(append,(1,2))),['committed','conflict'])
        with self.tx() as tx: self.assertEqual(tx._head('department',department.department_id),2)

    def test_evidence_issuer_revocation_before_commit_rolls_back_routing(self):
        self.approve()
        key=session_ref('approval_issuer');issuer=self.authority.sessions[key]
        try:
            with self.assertRaises(PermissionError):
                with self.tx() as tx:
                    tx.simulate_routing(self.intake,self.rule.rule_id,1,'syn-routing-key')
                    self.authority.sessions[key]=replace(issuer,principal=replace(issuer.principal,revoked=True))
                    tx.commit()
        finally: self.authority.sessions[key]=issuer
        self.assertEqual(self.count('routing_events'),0)

    def test_database_trigger_rejects_original_classification_rewrite(self):
        self.approve();packet=self.route()[0]
        changed=seal(replace(packet,revision=2,original_classification='syn-classification-derived'))
        with self.assertRaises(RuntimeError):
            with self.tx() as tx:
                original=tx._rows('routing_records',kind='packet',reference=packet.packet_id,revision=1)[0]
                values={key:value for key,value in original.items() if key not in ('tenant_reference','dataset')}
                values.update(revision=2,previous_revision=1,content_digest=changed.content_digest,payload=asdict(changed))
                tx._put('routing_records',**values);tx.commit()
        self.assertEqual(self.count('routing_events'),3)

    def test_invalid_rule_recipient_digest_and_reference_fail_closed(self):
        for recipient in (('syn-department-alpha',1,'0'*64,'syn-executive-alpha'),
                          ('syn-department-missing',1,self.departments[0].content_digest,'syn-executive-alpha')):
            rule=seal(replace(self.rule,revision=2,recipients=(recipient,)))
            with self.assertRaises(PermissionError):
                with self.tx() as tx: tx.append_rule(rule,1);tx.commit()
        with self.tx() as tx: self.assertEqual(tx._head('rule',self.rule.rule_id),1)

    def test_database_requires_packet_links_matching_original_intake(self):
        self.approve();packet=self.route()[0]
        for mismatch in ('source','missing-links'):
            changed=seal(replace(packet,packet_id='syn-new-packet',original_classification=(
                'syn-classification-derived' if mismatch=='source' else packet.original_classification)))
            with self.subTest(mismatch=mismatch),self.assertRaises(RuntimeError):
                with self.tx() as tx:
                    original=tx._rows('routing_records',kind='packet',reference=packet.packet_id,revision=1)[0]
                    values={key:value for key,value in original.items() if key not in ('tenant_reference','dataset')}
                    values.update(reference=changed.packet_id,content_digest=changed.content_digest,payload=asdict(changed))
                    tx._put('routing_records',**values)
                    if mismatch=='source': tx._packet_links(changed)
                    tx.commit()
