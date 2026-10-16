"""Synthetic contract tests. These do not substitute for PostgreSQL tests."""
from dataclasses import asdict, replace
import json
import unittest
from unittest.mock import patch

from mission_control.department_routing import (CENTRAL_VIEWS, DepartmentPacket, decode,
                                                derive_packets, ref, seal)
from mission_control.routing_postgres import RoutingStore, apply_routing_migration
from tests.routing_support import contracts, routing_authority


class DepartmentRoutingContractTests(unittest.TestCase):
    def setUp(self):
        self.departments,self.rule,self.intake = contracts()
        self.mapping = {d.department_id:d for d in self.departments}

    def packets(self, intake=None, rule=None, mapping=None):
        return derive_packets(intake or self.intake,rule or self.rule,mapping or self.mapping,'syn-routing-key')

    def test_all_contracts_round_trip_exact_digest(self):
        for record in (*self.departments,self.rule,self.intake,*self.packets()):
            record.validate()
            self.assertEqual(decode(type(record).__name__,json.dumps(asdict(record))),record)

    def test_duplicate_json_keys_fail_at_all_contract_boundaries(self):
        for record in (*self.departments,self.rule,self.intake,*self.packets()):
            value = json.dumps(asdict(record))
            for key in ('revision','tenant_reference'):
                with self.subTest(kind=type(record).__name__,key=key),self.assertRaises(ValueError):
                    decode(type(record).__name__,value[:-1]+','+json.dumps(key)+':1}')

    def test_unknown_missing_and_malformed_fields_fail(self):
        for record in (*self.departments,self.rule,self.intake,*self.packets()):
            for mode in ('unknown','missing','malformed'):
                data=asdict(record)
                if mode=='unknown': data['syn-extra']=True
                elif mode=='missing': data.pop('state')
                else: data['revision']=True
                with self.subTest(kind=type(record).__name__,mode=mode),self.assertRaises(ValueError):
                    decode(type(record).__name__,data)

    def test_non_synthetic_text_is_rejected_without_echo(self):
        for value in ('External Name','syn-Private Name','syn-secret@example.test','syn-line\nvalue','unresolved','syn-*'):
            with self.assertRaises(ValueError) as caught: ref(value)
            self.assertNotIn(value,str(caught.exception))

    def test_inactive_state_enforced_in_every_contract(self):
        for record in (*self.departments,self.rule,self.intake,*self.packets()):
            for state in ('active','approved','retired',None):
                with self.subTest(kind=type(record).__name__,state=state),self.assertRaises(ValueError):
                    seal(replace(record,state=state)).validate()

    def test_exact_revision_and_digest_binding(self):
        for record in (*self.departments,self.rule,self.intake,*self.packets()):
            with self.assertRaises(ValueError): replace(record,revision=2).validate()
        for value in (0,-1,True,1.5):
            with self.assertRaises(ValueError): seal(replace(self.rule,revision=value)).validate()

    def test_duplicate_alias_and_canonical_collision(self):
        department=self.departments[0]
        for aliases in ((department.canonical_name,),('syn-alias','syn-alias')):
            with self.assertRaises(ValueError): seal(replace(department,aliases=aliases)).validate()

    def test_visibility_mandatory_and_distinct(self):
        for views in ((),CENTRAL_VIEWS[:-1],('syn-view-command',)*3):
            with self.assertRaises(ValueError): seal(replace(self.rule,visibility_references=views)).validate()
            with self.assertRaises(ValueError): seal(replace(self.packets()[0],visibility_references=views)).validate()

    def test_multi_recipient_deterministic_executive_packets(self):
        first=self.packets()
        self.assertEqual(first,self.packets())
        self.assertEqual(len(first),2)
        self.assertEqual(len({packet.packet_id for packet in first}),2)
        for packet,department in zip(first,self.departments):
            self.assertEqual(packet.executive_reference,department.executive_reference)
            self.assertEqual(packet.recipient_references,(department.department_id,))
            self.assertEqual(packet.original_classification,self.intake.original_classification)
            self.assertEqual(packet.visibility_references,CENTRAL_VIEWS)
            self.assertEqual(packet.state,'inactive')

    def test_duplicate_and_malformed_recipients_rejected(self):
        for recipients in ((self.rule.recipients[0],)*2,(('syn-team-alpha',),),()):
            with self.assertRaises(ValueError): seal(replace(self.rule,recipients=recipients)).validate()

    def test_wrong_recipient_revision_digest_or_executive_fail(self):
        for field,value in (('revision',2),('executive_reference','syn-executive-other'),('mandate','syn-other-mandate')):
            changed=seal(replace(self.departments[0],**{field:value}))
            mapping={**self.mapping,changed.department_id:changed}
            with self.assertRaises(ValueError): self.packets(mapping=mapping)

    def test_missing_department_reference_fails(self):
        with self.assertRaises(ValueError): self.packets(mapping={self.departments[1].department_id:self.departments[1]})

    def test_cross_tenant_derivation_fails(self):
        with self.assertRaises(ValueError): self.packets(intake=seal(replace(self.intake,tenant_reference='syn-tenant-2')))
        department=seal(replace(self.departments[0],tenant_reference='syn-tenant-2'))
        rule=seal(replace(self.rule,recipients=((department.department_id,1,department.content_digest,department.executive_reference),)))
        with self.assertRaises(ValueError): self.packets(rule=rule,mapping={department.department_id:department})

    def test_preconditions_escalation_and_classification_fail_closed(self):
        with self.assertRaises(ValueError): self.packets(intake=seal(replace(self.intake,fact_references=())))
        with self.assertRaises(ValueError): self.packets(intake=seal(replace(self.intake,original_classification='syn-other')))
        with self.assertRaises(PermissionError): self.packets(intake=seal(replace(self.intake,fact_references=('syn-fact-ready','syn-fact-escalate'))))

    def test_intake_can_never_be_revised(self):
        with self.assertRaises(ValueError): seal(replace(self.intake,revision=2)).validate()

    def test_central_contract_has_no_team_assignment_field(self):
        data=asdict(self.packets()[0]);data['internal_team_assignment']='syn-team-alpha'
        with self.assertRaises(ValueError): decode('DepartmentPacket',data)
        with self.assertRaises(ValueError): seal(replace(self.packets()[0],recipient_references=('syn-department-alpha','syn-team-alpha'))).validate()

    def test_no_external_calls_in_pure_derivation(self):
        with patch('socket.socket',side_effect=AssertionError('Network forbidden')):
            self.assertEqual(len(self.packets()),2)

    def test_disabled_store_and_migration_require_authority_before_connection(self):
        called=[]
        factory=lambda:called.append(True)
        with self.assertRaises(PermissionError):
            with RoutingStore(factory).transaction('syn-tenant-1','syn-missing',1): pass
        with self.assertRaises(PermissionError): apply_routing_migration(factory)
        self.assertEqual(called,[])

    def test_visibility_does_not_authorize_other_actions(self):
        authority,_=routing_authority()
        from tests.synthetic_postgres_support import session_ref
        for action in ('packet.route_simulate','approval.routing.issue','registry.department.append','activate','external.process'):
            with self.subTest(action=action),self.assertRaises(PermissionError):
                authority.authorize(session_ref('data_reader'),'syn-tenant-1',1,action,'syn-rule-1')

    def test_service_cannot_hold_human_privileged_duties(self):
        authority,_=routing_authority()
        from tests.synthetic_postgres_support import session_ref
        service=authority.sessions[session_ref('service_writer')]
        for role in ('approval_issuer','policy_admin','signing_custodian'):
            changed=replace(service,principal=replace(service.principal,roles=(role,)))
            with self.assertRaises(PermissionError): changed.validate('syn-tenant-1')

    def test_rule_and_packet_cannot_substitute_for_execution_request(self):
        # Existing engine/CLI remains untouched; synthetic contract is not a directive.
        from mission_control.engine import MissionControlOS
        engine=MissionControlOS(audit_log=None)
        with patch.object(engine.provider,'classify',side_effect=AssertionError('Provider forbidden')):
            for record in (self.rule,self.packets()[0]):
                with self.assertRaises((ValueError,TypeError,AttributeError)):
                    engine.run(record)
