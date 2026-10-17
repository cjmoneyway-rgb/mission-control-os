"""Resealed incomplete archives must fail before insertion; restores are atomic."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
import unittest
from unittest.mock import patch

from mission_control import pilot_archive as archive_api
from mission_control.pilot_archive import TABLES, validate_complete_archive, restore_complete_snapshot
from mission_control.synthetic_identity import fingerprint
from tests import test_postgres_integration as base_pg
from tests import test_pilot_archive_postgres as original
from tests.pilot_pg_support import PilotFixture
from tests.pilot_support import TENANT, JOURNEY


@unittest.skipUnless(base_pg.AVAILABLE,base_pg.REASON)
class ArchiveCompletenessPostgreSQLTests(PilotFixture,unittest.TestCase):
    archive=original.PilotArchivePostgreSQLTests.archive
    restore=original.PilotArchivePostgreSQLTests.restore

    def reseal(self,archive):
        payload=archive['payload']
        payload['table_digests']={name:fingerprint(rows) for name,rows in payload['tables'].items()}
        payload['table_counts']={name:len(rows) for name,rows in payload['tables'].items()}
        archive['checksum']=fingerprint(payload);archive['proof']=self.custody.seal(payload)
        return archive

    def snapshot(self,admin):
        with admin() as connection:
            return {name:connection.execute('SELECT row_to_json(t)::text FROM mc_syn.'+name+' t ORDER BY row_to_json(t)::text').fetchall() for name in TABLES}

    def assert_empty(self,admin):
        with admin() as connection:
            for name in TABLES:
                self.assertEqual(connection.execute('SELECT count(*) FROM mc_syn.'+name+' WHERE tenant_reference=%s',(TENANT,)).fetchone()[0],0,name)

    def reject(self,archive):
        with self.assertRaises(ValueError): validate_complete_archive(self.reseal(archive),self.custody)

    def rechain(self,archive):
        events=archive['payload']['tables']['routing_events'];previous={}
        for row in events:
            intake=row['intake_reference'];prior=previous.get(intake)
            sequence=prior['sequence']+1 if prior else 1
            row.update(sequence=sequence,previous_sequence=sequence-1 or None,previous_digest=prior['content_digest'] if prior else None)
            row['payload'].update(sequence=sequence,previous_digest=row['previous_digest'])
            row['content_digest']=fingerprint(row['payload']);previous[intake]=row
        archive['payload']['tables']['routing_journey_heads']=[dict(tenant_reference=TENANT,intake_reference=intake,sequence=row['sequence'],dataset='synthetic') for intake,row in previous.items()]

    def stage_archive(self):
        self.stage();return self.archive()

    def test_all_34_tables_have_signed_counts_digests_and_inventory(self):
        archive=self.stage_archive();payload=archive['payload']
        self.assertEqual(len(TABLES),34)
        self.assertEqual(set(payload['tables']),set(archive_api.INSERT_ORDER))
        self.assertEqual(set(payload['table_counts']),set(TABLES))
        self.assertEqual(set(payload['table_digests']),set(TABLES))
        for name,rows in payload['tables'].items():
            self.assertEqual(payload['table_counts'][name],len(rows))
            self.assertEqual(payload['table_digests'][name],fingerprint(rows))
        validate_complete_archive(archive,self.custody)

    def test_removing_each_required_table_rejects_before_first_insert(self):
        source=self.stage_archive();target,admin=self.new_empty_store();before=self.snapshot(admin)
        for name in TABLES:
            damaged=deepcopy(source);damaged['payload']['tables'].pop(name);self.reseal(damaged)
            with self.subTest(table=name),patch.object(archive_api,'_restore_row') as insert:
                with self.assertRaises(ValueError): self.restore(damaged,target)
                insert.assert_not_called()
        self.assertEqual(before,self.snapshot(admin));self.assert_empty(admin)

    def test_removing_each_digest_or_count_manifest_entry_rejects(self):
        source=self.stage_archive()
        for inventory in ('table_digests','table_counts'):
            for name in TABLES:
                damaged=deepcopy(source);damaged['payload'][inventory].pop(name)
                payload=damaged['payload'];damaged.update(checksum=fingerprint(payload),proof=self.custody.seal(payload))
                with self.subTest(inventory=inventory,table=name),self.assertRaises(ValueError):
                    validate_complete_archive(damaged,self.custody)

    def test_removing_each_reviewed_schema_manifest_entry_rejects(self):
        source=self.archive()
        for name in TABLES:
            incomplete=deepcopy(TABLES);incomplete.pop(name)
            with self.subTest(table=name),patch.object(archive_api,'TABLES',incomplete),self.assertRaises(ValueError):
                validate_complete_archive(source,self.custody)

    def test_incorrect_negative_boolean_and_missing_counts_reject(self):
        source=self.stage_archive()
        for value in (-1,True,999):
            damaged=deepcopy(source);damaged['payload']['table_counts']['pilot_events']=value
            payload=damaged['payload'];damaged.update(checksum=fingerprint(payload),proof=self.custody.seal(payload))
            with self.subTest(value=value),self.assertRaises(ValueError): validate_complete_archive(damaged,self.custody)
        damaged=deepcopy(source);damaged['payload'].pop('table_counts')
        payload=damaged['payload'];damaged.update(checksum=fingerprint(payload),proof=self.custody.seal(payload))
        with self.assertRaises(ValueError): validate_complete_archive(damaged,self.custody)

    def test_empty_journal_with_retained_completed_stage_cannot_restore(self):
        damaged=self.stage_archive()
        for name in ('routing_events','routing_journey_heads'): damaged['payload']['tables'][name].clear()
        target,admin=self.new_empty_store()
        with patch.object(archive_api,'_restore_row') as insert:
            with self.assertRaises(ValueError): self.restore(self.reseal(damaged),target)
            insert.assert_not_called()
        self.assert_empty(admin)

    def test_internally_consistent_journal_prefix_cannot_restore(self):
        damaged=self.stage_archive();events=damaged['payload']['tables']['routing_events']
        events.sort(key=lambda row:row['sequence']);self.assertEqual(len(events),3);events.pop()
        self.rechain(damaged);target,admin=self.new_empty_store()
        with patch.object(archive_api,'_restore_row') as insert:
            with self.assertRaises(ValueError): self.restore(self.reseal(damaged),target)
            insert.assert_not_called()
        self.assert_empty(admin)

    def test_unexpected_journal_operation_even_with_valid_chain_rejects(self):
        damaged=self.stage_archive();damaged['payload']['tables']['routing_events'][0]['payload']['event']='syn-unexpected'
        self.rechain(damaged);self.reject(damaged)

    def test_duplicate_journal_event_with_new_sequence_rejects(self):
        damaged=self.stage_archive();events=damaged['payload']['tables']['routing_events'];events.sort(key=lambda row:row['sequence'])
        events.append(deepcopy(events[-1]));self.rechain(damaged);self.reject(damaged)

    def test_material_journal_reordering_even_with_valid_chain_rejects(self):
        damaged=self.stage_archive();events=damaged['payload']['tables']['routing_events'];events.sort(key=lambda row:row['sequence'])
        events[1],events[2]=events[2],events[1];self.rechain(damaged);self.reject(damaged)

    def test_every_populated_foreign_key_rejects_dangling_reference(self):
        source=self.stage_archive();checked=0
        for name,schema in TABLES.items():
            if not source['payload']['tables'][name]: continue
            for fk in schema['foreign_keys']:
                column=next((column for column in fk['columns'] if column!='tenant_reference'),None)
                if column is None: continue
                damaged=deepcopy(source);row=damaged['payload']['tables'][name][0]
                row[column]=999999 if schema['columns'][column]['type'] in ('int8','int4') else 'syn-missing-reference'
                with self.subTest(table=name,column=column): self.reject(damaged)
                checked+=1
        self.assertEqual(checked,40)  # Every FK populated by this one-stage fixture.

    def test_missing_cross_table_packets_decisions_deliverables_and_heads_reject(self):
        source=self.stage_archive()
        for name in ('pilot_decisions','pilot_packet_links','pilot_deliverables','pilot_heads','routing_links','routing_heads'):
            damaged=deepcopy(source);damaged['payload']['tables'][name].pop()
            with self.subTest(table=name): self.reject(damaged)

    def test_payload_table_digest_and_outer_checksum_tampering_reject(self):
        source=self.stage_archive()
        damaged=deepcopy(source);damaged['payload']['tables']['pilot_events'][0]['payload']['stage_index']=9
        self.reject(damaged)  # Recomputed table/outer hashes cannot hide the inner content mismatch.
        for field in ('stage_index','sequence','proposal_revision'):
            damaged=deepcopy(source);row=damaged['payload']['tables']['pilot_events'][0]
            row['payload'][field]=True;row['content_digest']=fingerprint(row['payload'])
            with self.subTest(integer_field=field): self.reject(damaged)
        for field in ('checksum','proof'):
            damaged=deepcopy(source);damaged[field]='syn-invalid'
            with self.subTest(field=field),self.assertRaises(ValueError): validate_complete_archive(damaged,self.custody)
        damaged=deepcopy(source);damaged['payload']['table_digests']['pilot_events']='0'*64
        payload=damaged['payload'];damaged.update(checksum=fingerprint(payload),proof=self.custody.seal(payload))
        with self.assertRaises(ValueError): validate_complete_archive(damaged,self.custody)

    def test_required_start_proposal_and_advance_receipts_cannot_disappear(self):
        source=self.stage_archive()
        for operation in ('syn-pilot-start','syn-pilot-propose','syn-pilot-advance'):
            damaged=deepcopy(source);damaged['payload']['tables']['routing_receipts']=[row for row in damaged['payload']['tables']['routing_receipts'] if row['operation']!=operation]
            with self.subTest(operation=operation): self.reject(damaged)

    def test_duplicate_operation_receipts_under_different_keys_reject(self):
        source=self.stage_archive()
        for operation in ('syn-pilot-start','syn-pilot-propose','syn-pilot-advance'):
            damaged=deepcopy(source);rows=damaged['payload']['tables']['routing_receipts']
            row=deepcopy(next(row for row in rows if row['operation']==operation));row['key']='syn-extra-key';rows.append(row)
            with self.subTest(operation=operation): self.reject(damaged)

    def test_packet_idempotency_key_must_match_advance_receipt(self):
        source=self.stage_archive()
        for operation in ('syn-pilot-propose','syn-pilot-advance'):
            damaged=deepcopy(source)
            receipt=next(row for row in damaged['payload']['tables']['routing_receipts'] if row['operation']==operation)
            if operation=='syn-pilot-propose': receipt['result'][2]=True
            else: receipt['result']['version']=True
            with self.subTest(operation=operation): self.reject(damaged)
        damaged=deepcopy(source)
        next(row for row in damaged['payload']['tables']['routing_receipts'] if row['operation']=='syn-pilot-advance')['key']='syn-wrong-key'
        self.reject(damaged)

    def test_routing_link_content_digests_must_match_exact_records(self):
        source=self.stage_archive()
        for field in ('department_digest','rule_digest'):
            damaged=deepcopy(source);damaged['payload']['tables']['routing_links'][0][field]='0'*64
            with self.subTest(field=field): self.reject(damaged)

    def test_silently_omitted_insert_is_detected_and_every_table_rolls_back(self):
        source=self.stage_archive();target,admin=self.new_empty_store();insert=archive_api._restore_row;skipped=[]
        def omit(tx,name,row):
            if name=='security_decisions' and not skipped: skipped.append(row);return
            insert(tx,name,row)
        with patch.object(archive_api,'_restore_row',side_effect=omit),self.assertRaises(ValueError): self.restore(source,target)
        self.assertTrue(skipped);self.assert_empty(admin)

    def test_inserted_metadata_mismatch_rolls_back_all_rows(self):
        source=self.stage_archive();target,admin=self.new_empty_store();insert=archive_api._restore_row
        def corrupt(tx,name,row):
            if name=='pilot_journeys':
                row['created_at']=(datetime.fromisoformat(row['created_at'])+timedelta(seconds=1)).isoformat()
            insert(tx,name,row)
        with patch.object(archive_api,'_restore_row',side_effect=corrupt),self.assertRaises(ValueError): self.restore(source,target)
        self.assert_empty(admin)

    def test_integrity_recheck_failure_rolls_back_all_rows(self):
        source=self.stage_archive();target,admin=self.new_empty_store();original_check=archive_api._verify_restored_tables
        def fail_after_recheck(*args):
            original_check(*args);raise ValueError('Synthetic post-insertion integrity failure')
        with patch.object(archive_api,'_verify_restored_tables',side_effect=fail_after_recheck),self.assertRaises(ValueError): self.restore(source,target)
        self.assert_empty(admin)

    def test_commit_failure_rolls_back_all_rows_and_preserves_shared_ledger(self):
        source=self.stage_archive();target,admin=self.new_empty_store();before=self.snapshot(admin);factory=target.factory
        class CommitFailure:
            def __init__(self): self.connection=factory()
            def __getattr__(self,name): return getattr(self.connection,name)
            def commit(self): raise RuntimeError('Synthetic failure before database commit')
        with patch.object(target,'factory',side_effect=CommitFailure),self.assertRaises(RuntimeError): self.restore(source,target)
        self.assert_empty(admin);self.assertEqual(before,self.snapshot(admin))

    def test_preexisting_destination_is_byte_for_byte_unchanged_after_failure(self):
        source=self.stage_archive();before=self.snapshot(self.admin)
        with self.assertRaises(ValueError): self.restore(source,self.store)
        self.assertEqual(before,self.snapshot(self.admin))

    def test_failed_restore_preserves_other_tenant_records(self):
        source=self.stage_archive();target,admin=self.new_empty_store()
        with self.tx('policy_admin',tenant='syn-tenant-2',store=target) as tx: tx.bootstrap_policy();tx.commit()
        before=self.snapshot(admin);insert=archive_api._restore_row;calls=[]
        def interrupted(tx,name,row):
            calls.append(name)
            if len(calls)==20: raise ValueError('Synthetic interruption')
            insert(tx,name,row)
        with patch.object(archive_api,'_restore_row',side_effect=interrupted),self.assertRaises(ValueError): self.restore(source,target)
        self.assertGreater(len(calls),1);self.assert_empty(admin);self.assertEqual(before,self.snapshot(admin))

    def test_valid_34_table_round_trip_matches_rows_counts_digests_and_proof(self):
        self.complete_all();source=self.archive();target=self.restore(source)
        with self.tx('audit_reviewer',store=target) as tx: restored=archive_api.export_complete_snapshot(tx,self.custody)
        validate_complete_archive(source,self.custody);validate_complete_archive(restored,self.custody)
        for name in TABLES:
            expected=source['payload']['tables'][name];actual=restored['payload']['tables'][name]
            if name=='security_decisions':
                extra=[row for row in actual if row not in expected]
                self.assertEqual(len(extra),1);self.assertTrue(all(row in actual for row in expected))
            else:
                self.assertEqual(expected,actual,name)
                self.assertEqual(source['payload']['table_counts'][name],restored['payload']['table_counts'][name])
                self.assertEqual(source['payload']['table_digests'][name],restored['payload']['table_digests'][name])
        self.assertEqual(source['payload']['manifest_digest'],restored['payload']['manifest_digest'])
        with self.tx(store=target) as tx: self.assertEqual(tx.read_pilot(JOURNEY)['head']['completed_stage'],16)

    def test_valid_packet_revision_and_inactive_visibility_round_trip(self):
        from mission_control.department_routing import seal
        result=self.stage();reference=result['packet_references'][0]
        with self.tx() as tx:
            packet=tx._get('packet',reference,1)
            tx.append_packet_revision(seal(replace(packet,revision=2)),1,'syn-revision-key');tx.commit()
        with self.tx('data_reader') as tx:
            tx.distribute_team_visibility(reference,2,self.departments[0].team_references[0],'syn-visibility-key');tx.commit()
        source=self.archive();target=self.restore(source)
        with self.tx('audit_reviewer',store=target) as tx: restored=archive_api.export_complete_snapshot(tx,self.custody)
        self.assertEqual(source['payload']['tables']['routing_events'],restored['payload']['tables']['routing_events'])
        # A valid FK to revision 2 must not replace the required initial packet link.
        damaged=deepcopy(source);damaged['payload']['tables']['pilot_packet_links'][0]['packet_revision']=2
        self.reject(damaged)

    def test_dangling_visibility_reference_rejects_even_after_resealing(self):
        result=self.stage();reference=result['packet_references'][0]
        with self.tx('data_reader') as tx:
            tx.distribute_team_visibility(reference,1,self.departments[0].team_references[0],'syn-visibility-key');tx.commit()
        damaged=self.archive()
        event=next(row for row in damaged['payload']['tables']['routing_events'] if row['payload']['event']=='syn-team-visibility')
        event['payload']['details']['team_reference']='syn-unresolved-team'
        receipt=next(row for row in damaged['payload']['tables']['routing_receipts'] if row['operation']=='syn-distribute')
        receipt['result'][2]='syn-unresolved-team';receipt['payload_digest']=fingerprint(receipt['result'])
        damaged['payload']['tables']['routing_events'].sort(key=lambda row:row['sequence'])
        self.rechain(damaged);self.reject(damaged)

    def test_swallowed_integrity_failure_still_prevents_commit(self):
        source=self.stage_archive();target,admin=self.new_empty_store()
        with self.assertRaises(PermissionError):
            with self.tx('migration_operator',store=target) as tx:
                with patch.object(archive_api,'_verify_restored_tables',side_effect=ValueError('Synthetic failure')):
                    with self.assertRaises(ValueError): restore_complete_snapshot(tx,source,self.custody)
                tx.commit()
        self.assert_empty(admin)

    def test_obsolete_baseline_export_cannot_omit_extended_schema(self):
        from mission_control.synthetic_archive import export_snapshot
        with self.assertRaises(ValueError):
            with self.tx('audit_reviewer') as tx: export_snapshot(tx,self.custody)
        obsolete=self.archive();obsolete['payload']['format']='syn-pilot-export-v1'
        self.reject(obsolete)

    def test_database_deferred_commit_rejection_rolls_back_complete_restore(self):
        source=self.stage_archive();target,admin=self.new_empty_store();before=self.snapshot(admin)
        # Disposable target only: inject a real deferred PostgreSQL constraint failure.
        with admin() as connection:
            connection.execute("""CREATE FUNCTION mc_syn.syn_restore_commit_failure() RETURNS trigger
                LANGUAGE plpgsql AS $$ BEGIN
                IF NEW.action='backup.restore' THEN RAISE EXCEPTION 'Synthetic commit rejection'; END IF;
                RETURN NEW; END $$""")
            connection.execute("""CREATE CONSTRAINT TRIGGER syn_restore_commit_failure
                AFTER INSERT ON mc_syn.security_decisions DEFERRABLE INITIALLY DEFERRED
                FOR EACH ROW EXECUTE FUNCTION mc_syn.syn_restore_commit_failure()""")
        from mission_control.pilot_postgres import PilotTransaction
        audit=PilotTransaction._audit
        def defer_restore_audit(tx,*args):
            if args[0]=='backup.restore': tx.connection.execute('SET CONSTRAINTS ALL DEFERRED')
            return audit(tx,*args)
        with patch.object(PilotTransaction,'_audit',defer_restore_audit),self.assertRaises(RuntimeError): self.restore(source,target)
        self.assert_empty(admin);self.assertEqual(before,self.snapshot(admin))

    def test_original_foundation_results_also_require_complete_receipts(self):
        from tests.test_registry_foundation import fixtures
        registry,packet,event=fixtures()
        with self.tx() as tx:
            tx.append_registry(registry,0,'syn-baseline-registry-key')
            tx.append_packet(packet,0,'syn-baseline-packet-key')
            tx.append_event(event,0,'syn-baseline-event-key');tx.commit()
        self.stage();source=self.archive()
        for index in range(len(source['payload']['tables']['idempotency_receipts'])):
            damaged=deepcopy(source);damaged['payload']['tables']['idempotency_receipts'].pop(index)
            with self.subTest(receipt=index): self.reject(damaged)
        duplicated=deepcopy(source);rows=duplicated['payload']['tables']['idempotency_receipts']
        row=deepcopy(rows[0]);row['idempotency_key']='syn-extra-baseline-key';rows.append(row)
        self.reject(duplicated)
