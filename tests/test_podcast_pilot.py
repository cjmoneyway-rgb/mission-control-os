"""Opaque synthetic contract tests; never a substitute for PostgreSQL proof."""
from copy import deepcopy
from dataclasses import asdict, replace
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from mission_control.department_routing import seal
from mission_control.podcast_pilot import STAGES, CLASSIFICATIONS, classify_event, decode_pilot, derive_stage_packets
from mission_control.pilot_postgres import PilotStore, apply_pilot_migration
from mission_control.pilot_archive import TABLES, INSERT_ORDER
from tests.pilot_support import pilot_authority, pilot_contracts, JOURNEY, TENANT
from tests.synthetic_postgres_support import session_ref


class PodcastPilotContractTests(unittest.TestCase):
    def setUp(self):
        self.journey,self.intake,self.departments,self.rules,self.events=pilot_contracts()

    def packets(self,event=None,rule=None):
        return derive_stage_packets(self.journey,self.intake,event or self.events[0],rule or self.rules[0],
                                   {d.department_id:d for d in self.departments},'syn-advance-01')

    def test_sixteen_stages_have_unique_deterministic_classifications(self):
        self.assertEqual(len(STAGES),16);self.assertEqual(len(set(CLASSIFICATIONS)),16)
        self.assertEqual(tuple(classify_event(event) for event in self.events),CLASSIFICATIONS)

    def test_contracts_round_trip_and_exact_digests(self):
        for kind,record in [('journey',self.journey),*(('event',event) for event in self.events)]:
            self.assertEqual(decode_pilot(kind,json.dumps(asdict(record))),record)
            with self.assertRaises(ValueError): replace(record,revision=2).validate()

    def test_duplicate_json_keys_rejected(self):
        for kind,record in (('journey',self.journey),('event',self.events[0])):
            for key in ('state','revision','tenant_reference'):
                data=json.dumps(asdict(record))[:-1]+','+json.dumps(key)+':1}'
                with self.subTest(kind=kind,key=key),self.assertRaises(ValueError): decode_pilot(kind,data)

    def test_malformed_missing_and_extra_fields_rejected(self):
        for kind,record in (('journey',self.journey),('event',self.events[0])):
            for mode in ('missing','extra','boolean-revision','real-reference'):
                data=asdict(record)
                if mode=='missing': data.pop('state')
                elif mode=='extra': data['syn-extra']=True
                elif mode=='boolean-revision': data['revision']=True
                else: data['tenant_reference']='not-a-synthetic-reference'
                with self.subTest(kind=kind,mode=mode),self.assertRaises(ValueError): decode_pilot(kind,data)

    def test_operational_states_rejected_everywhere(self):
        for record in (self.journey,*self.events):
            for state in ('active','approved','running'):
                with self.assertRaises(ValueError): seal(replace(record,state=state)).validate()

    def test_original_entry_is_immutable(self):
        for fields in ({'revision':2},{'original_classification':'syn-later-class'}):
            with self.assertRaises(ValueError): seal(replace(self.journey,**fields)).validate()

    def test_stage_classification_mismatch_rejected(self):
        with self.assertRaises(ValueError): seal(replace(self.events[0],classification=CLASSIFICATIONS[1])).validate()
        with self.assertRaises(ValueError): seal(replace(self.events[0],stage_reference='syn-unknown')).validate()

    def test_self_dependency_and_missing_predecessor_dependency_rejected(self):
        for fields in ({'dependency_references':(self.events[0].event_id,)},
                       {'previous_event_reference':self.events[0].event_id}):
            with self.assertRaises(ValueError): seal(replace(self.events[0],**fields)).validate()
        with self.assertRaises(ValueError): seal(replace(self.events[1],dependency_references=())).validate()

    def test_evidence_cannot_be_empty_or_malformed(self):
        for values in ((),('syn-evidence-01','syn-evidence-01'),['syn-evidence-01']):
            with self.assertRaises(ValueError): seal(replace(self.events[0],evidence_references=values)).validate()
        with self.assertRaises(ValueError): self.packets(event=seal(replace(self.events[0],evidence_references=('syn-evidence-other',))))

    def test_terminal_decision_only_on_final_stage(self):
        with self.assertRaises(ValueError): seal(replace(self.events[0],terminal_reference='syn-closed')).validate()
        for terminal in (None,'syn-live'):
            with self.assertRaises(ValueError): seal(replace(self.events[-1],terminal_reference=terminal)).validate()
        seal(replace(self.events[-1],terminal_reference='syn-closed')).validate()

    def test_routing_preserves_original_and_links_current_classification(self):
        for event,rule in zip(self.events,self.rules):
            packets=derive_stage_packets(self.journey,self.intake,event,rule,{d.department_id:d for d in self.departments},'syn-stage-key')
            for packet in packets:
                self.assertEqual(packet.original_classification,self.journey.original_classification)
                self.assertEqual(packet.current_classification,event.classification)
                self.assertEqual(packet.source_event_reference,self.intake.event_id)
                self.assertEqual(packet.dependencies,event.dependency_references)
                self.assertEqual(packet.outcome_references,event.outcome_references)
                self.assertEqual(packet.state,'inactive')

    def test_packet_ids_distinguish_events_not_retries(self):
        first=self.packets()
        self.assertEqual(first,self.packets())
        other=derive_stage_packets(self.journey,self.intake,self.events[2],self.rules[2],{d.department_id:d for d in self.departments},'syn-another-key')
        self.assertNotEqual(first[0].packet_id,other[0].packet_id)

    def test_cross_tenant_and_rule_digest_mismatch_fail_closed(self):
        for fields in ({'tenant_reference':'syn-tenant-2'},{'rule_digest':'0'*64},{'rule_revision':2}):
            with self.assertRaises((ValueError,PermissionError)): self.packets(event=seal(replace(self.events[0],**fields)))

    def test_pure_classification_and_derivation_have_no_network_calls(self):
        with patch('socket.socket',side_effect=AssertionError('Network forbidden')):
            self.assertEqual(classify_event(self.events[0]),CLASSIFICATIONS[0]);self.packets()

    def test_store_and_migration_default_deny_before_connecting(self):
        calls=[];factory=lambda:calls.append(True)
        with self.assertRaises(PermissionError):
            with PilotStore(factory).transaction(TENANT,'syn-unknown',1): pass
        with self.assertRaises(PermissionError): apply_pilot_migration(factory)
        self.assertEqual(calls,[])

    def test_visibility_does_not_grant_advance_or_approval(self):
        authority,_=pilot_authority()
        for action in ('journey.pilot.advance','approval.pilot.issue','journey.pilot.start'):
            with self.assertRaises(PermissionError): authority.authorize(session_ref('data_reader'),TENANT,1,action,JOURNEY)

        from mission_control.synthetic_identity import SyntheticGrant
        policy=authority.policies[TENANT];subject='syn-data_reader-'+TENANT
        authority.policies[TENANT]=replace(policy,grants=(*policy.grants,
            SyntheticGrant('data_reader','packet.view.executive','syn-executive-alpha','deny',subject)))
        with self.assertRaises(PermissionError):
            authority.authorize(session_ref('data_reader'),TENANT,1,'packet.view.executive','syn-executive-alpha')
        with self.assertRaises(PermissionError):
            authority.authorize('syn-session-reader-beta-'+TENANT,TENANT,1,'packet.view.executive','syn-executive-alpha')

    def test_complete_manifest_covers_all_thirty_four_tables(self):
        self.assertEqual(len(TABLES),34);self.assertEqual(set(INSERT_ORDER),set(TABLES))
        self.assertEqual(len(INSERT_ORDER),len(set(INSERT_ORDER)))
        self.assertIn('routing_evidence',TABLES);self.assertIn('pilot_deliverables',TABLES)
        for table in TABLES.values():
            self.assertIn('tenant_reference',table['columns']);self.assertIn('dataset',table['columns'])

    def test_inactive_contracts_cannot_reach_existing_engine(self):
        from mission_control.engine import MissionControlOS
        engine=MissionControlOS(audit_log=None)
        with patch.object(engine,'_invoke',side_effect=AssertionError('Provider forbidden')):
            for record in (self.journey,self.events[0],self.packets()[0]):
                with self.assertRaises(ValueError): engine.run(record)

    def test_invalid_input_errors_never_echo_payload(self):
        bad=asdict(self.events[0]);bad['syn-extra']='synthetic-rejected-marker'
        with self.assertRaises(ValueError) as caught: decode_pilot('event',bad)
        self.assertNotIn('synthetic-rejected-marker',str(caught.exception))
