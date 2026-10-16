"""Complete real PostgreSQL snapshot/restore and corruption rejection proof."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import Mock, patch

from mission_control.pilot_archive import (TABLES, export_complete_snapshot, restore_complete_snapshot,
    validate_complete_archive, write_complete_archive, read_complete_archive)
from mission_control.synthetic_identity import fingerprint, SyntheticEvidenceCustody
from mission_control.synthetic_postgres import _query
from tests import test_postgres_integration as base_pg
from tests.pilot_pg_support import PilotFixture
from tests.pilot_support import TENANT, JOURNEY
from tests.synthetic_postgres_support import session_ref


@unittest.skipUnless(base_pg.AVAILABLE,base_pg.REASON)
class PilotArchivePostgreSQLTests(PilotFixture,unittest.TestCase):
    def archive(self):
        with self.tx('audit_reviewer') as tx: return export_complete_snapshot(tx,self.custody)

    def reseal(self,archive):
        payload=archive['payload']
        payload['table_digests']={name:fingerprint(rows) for name,rows in payload['tables'].items()}
        archive['checksum']=fingerprint(payload);archive['proof']=self.custody.seal(payload)
        return archive

    def restore(self,archive,store=None):
        store=store or self.new_empty_store()[0]
        with self.tx('migration_operator',store=store) as tx:
            restore_complete_snapshot(tx,archive,self.custody);tx.commit()
        return store

    def test_complete_sixteen_stage_export_restore_preserves_all_tenant_rows(self):
        self.complete_all();archive=self.archive()
        self.assertEqual(set(archive['payload']['tables']),set(TABLES))
        self.assertEqual(len(archive['payload']['migrations']),3)
        target=self.restore(archive)
        with self.tx('audit_reviewer',store=target) as tx: restored=export_complete_snapshot(tx,self.custody)
        for name in TABLES:
            before=archive['payload']['tables'][name];after=restored['payload']['tables'][name]
            if name=='security_decisions':
                self.assertEqual(len(after),len(before)+1)
                self.assertTrue(all(row in after for row in before))
            else: self.assertEqual(before,after,name)
        with self.tx(store=target) as tx: self.assertEqual(tx.read_pilot(JOURNEY)['head']['completed_stage'],16)

    def test_mixed_baseline_and_pilot_records_export_restore_completely(self):
        from tests.test_registry_foundation import fixtures
        registry,packet,event=fixtures()
        with self.tx() as tx:
            tx.append_registry(registry,0,'syn-baseline-registry-key')
            tx.append_packet(packet,0,'syn-baseline-packet-key')
            tx.append_event(event,0,'syn-baseline-event-key');tx.commit()
        with self.tx('approval_issuer') as tx: tx.issue_approval('syn-registry-1',1,'syn-baseline-evidence');tx.commit()
        self.stage();archive=self.archive();target=self.restore(archive)
        with self.tx(store=target) as tx:
            self.assertEqual(tx.get_registry('syn-registry-1',1),registry)
            self.assertEqual(tx.get_packet('syn-packet-1',1),packet)
            self.assertEqual(tx.get_event(event.event.event_id),event)
            self.assertEqual(tx.read_pilot(JOURNEY)['head']['completed_stage'],1)

    def test_archive_rejects_missing_or_unknown_table(self):
        original=self.archive()
        for mode in ('missing','unknown'):
            archive=deepcopy(original)
            if mode=='missing': archive['payload']['tables'].pop('pilot_deliverables')
            else: archive['payload']['tables']['syn-unreviewed']=[]
            with self.subTest(mode=mode),self.assertRaises(ValueError): validate_complete_archive(self.reseal(archive),self.custody)

    def test_missing_deliverable_is_detected_even_if_outer_signature_resealed(self):
        self.stage();archive=self.archive()
        archive['payload']['tables']['pilot_deliverables'].pop()
        with self.assertRaises(ValueError): validate_complete_archive(self.reseal(archive),self.custody)

    def test_missing_proposal_or_idempotency_receipt_is_detected(self):
        self.stage();original=self.archive()
        for table in ('pilot_proposals','routing_receipts','pilot_decisions','routing_names','routing_evidence'):
            archive=deepcopy(original);archive['payload']['tables'][table].clear()
            with self.subTest(table=table),self.assertRaises(ValueError): validate_complete_archive(self.reseal(archive),self.custody)

    def test_hash_chain_and_original_classification_tampering_rejected(self):
        self.stage();original=self.archive()
        for field,value in (('original_classification','syn-other-class'),('previous_digest','0'*64),('sequence',7)):
            archive=deepcopy(original);row=archive['payload']['tables']['pilot_events'][0]
            row[field]=value;row['payload'][field]=value;row['content_digest']=fingerprint(row['payload'])
            with self.subTest(field=field),self.assertRaises(ValueError): validate_complete_archive(self.reseal(archive),self.custody)

        archive=deepcopy(original);archive['payload']['tables']['pilot_heads'][0]['state']='draft'
        with self.assertRaises(ValueError): validate_complete_archive(self.reseal(archive),self.custody)

    def test_archive_tamper_wrong_custody_and_duplicate_keys_rejected(self):
        archive=self.archive()
        wrong=SyntheticEvidenceCustody(self.authority,session_ref('signing_custodian'),TENANT,1)
        with self.assertRaises(ValueError): validate_complete_archive(archive,wrong)
        changed=deepcopy(archive);changed['payload']['dataset']='syn-wrong'
        with self.assertRaises(ValueError): validate_complete_archive(changed,self.custody)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'synthetic.json';path.write_text('{"payload":{},"payload":{}}')
            with self.assertRaises(ValueError): read_complete_archive(path,self.custody)

    def test_plain_synthetic_archive_is_owner_only_atomic_and_no_overwrite(self):
        self.stage();archive=self.archive()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'synthetic.json'
            write_complete_archive(path,archive,self.custody)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
            self.assertEqual(read_complete_archive(path,self.custody),archive)
            original=path.read_bytes()
            with self.assertRaises(FileExistsError): write_complete_archive(path,archive,self.custody)
            self.assertEqual(path.read_bytes(),original)
            failed=Path(folder)/'interrupted.json'
            with patch('mission_control.pilot_archive.os.fsync',side_effect=OSError('Synthetic interruption')):
                with self.assertRaises(OSError): write_complete_archive(failed,archive,self.custody)
            self.assertFalse(failed.exists());self.assertEqual(sorted(p.name for p in Path(folder).iterdir()),['synthetic.json'])

    def test_archive_and_restore_are_tenant_scoped(self):
        archive=self.archive();text=json.dumps(archive)
        self.assertNotIn('syn-tenant-2',text)
        target,_=self.new_empty_store()
        with self.assertRaises(PermissionError):
            with self.tx('migration_operator',tenant='syn-tenant-2',store=target) as tx: restore_complete_snapshot(tx,archive,self.custody)
        altered=deepcopy(archive)
        altered['payload']['tables']['pilot_journeys'][0]['tenant_reference']='syn-tenant-2'
        with self.assertRaises(ValueError): validate_complete_archive(self.reseal(altered),self.custody)

    def test_restore_refuses_merge_or_overwrite_of_existing_records(self):
        archive=self.archive();before={name:self.count(name) for name in TABLES}
        with self.assertRaises(ValueError): self.restore(archive,self.store)
        self.assertEqual(before,{name:self.count(name) for name in TABLES})

    def test_restore_failure_rolls_back_every_insert(self):
        self.stage();archive=self.archive();target,admin=self.new_empty_store()
        from mission_control import pilot_archive
        original=pilot_archive._restore_row;inserted=[]
        def interrupted(tx,name,row):
            inserted.append(name)
            if len(inserted)==6: raise ValueError('Synthetic restore interruption')
            return original(tx,name,row)
        with patch('mission_control.pilot_archive._restore_row',side_effect=interrupted):
            with self.assertRaises(ValueError): self.restore(archive,target)
        with admin() as connection:
            for name in TABLES:
                self.assertEqual(connection.execute('SELECT count(*) FROM mc_syn.'+name+' WHERE tenant_reference=%s',(TENANT,)).fetchone()[0],0)

    def test_restore_without_commit_or_after_interruption_persists_nothing(self):
        archive=self.archive();target,admin=self.new_empty_store()
        with self.tx('migration_operator',store=target) as tx: restore_complete_snapshot(tx,archive,self.custody)
        with self.assertRaises(ValueError):
            with self.tx('migration_operator',store=target) as tx:
                restore_complete_snapshot(tx,archive,self.custody);tx.commit();raise ValueError('Synthetic interruption')
        with admin() as connection: self.assertEqual(connection.execute('SELECT count(*) FROM mc_syn.pilot_journeys').fetchone()[0],0)

    def test_revoked_event_evidence_is_preserved_and_remains_unusable_after_restore(self):
        event=self.prepare();self.advance()
        with self.tx('approval_issuer') as tx: tx.revoke_event_approval(event.approval_reference);tx.commit()
        archive=self.archive();target=self.restore(archive)
        self.assertEqual(len(archive['payload']['tables']['pilot_revocations']),1)
        with self.assertRaises(PermissionError):
            with self.tx(store=target) as tx: tx.advance_event(JOURNEY,event.event_id,1,0,'syn-advance-01')

    def test_blocked_attempts_and_unapproved_proposals_round_trip(self):
        from mission_control.department_routing import seal
        blocked=seal(replace(self.events[0],dependency_references=('syn-missing-dependency',)))
        self.prepare(event=blocked);self.advance(event=blocked)
        self.prepare(2,approve=False)
        archive=self.archive();target=self.restore(archive)
        with self.tx(store=target) as tx:
            snapshot=tx.read_pilot(JOURNEY)
            self.assertEqual(snapshot['head']['completed_stage'],0);self.assertEqual(snapshot['events'][0]['disposition'],'blocked')

    def test_unknown_table_or_column_schema_drift_fails_closed(self):
        for ddl,undo in (('CREATE TABLE mc_syn.syn_unreviewed (value text)','DROP TABLE mc_syn.syn_unreviewed'),
                         ('ALTER TABLE mc_syn.pilot_heads ADD COLUMN syn_unreviewed text','ALTER TABLE mc_syn.pilot_heads DROP COLUMN syn_unreviewed')):
            with self.subTest(ddl=ddl):
                with self.admin() as connection: connection.execute(ddl)
                try:
                    with self.assertRaises(ValueError):
                        with self.tx('audit_reviewer') as tx: export_complete_snapshot(tx,self.custody)
                finally:
                    with self.admin() as connection: connection.execute(undo)

    def test_export_restore_require_separate_exact_authority(self):
        archive=self.archive()
        for action in ('export','restore'):
            with self.subTest(action=action),self.assertRaises(PermissionError):
                with self.tx() as tx:
                    if action=='export': export_complete_snapshot(tx,self.custody)
                    else: restore_complete_snapshot(tx,archive,self.custody)
        untrusted=Mock()
        with self.assertRaises(PermissionError):
            with self.tx('audit_reviewer') as tx: export_complete_snapshot(tx,untrusted)
        untrusted.seal.assert_not_called();untrusted.verify.assert_not_called()
