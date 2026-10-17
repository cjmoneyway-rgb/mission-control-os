"""Offline adversarial tests for the local synthetic boundary, never a socket server."""
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import json
import socket
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mission_control.connection_contracts import (CONNECTORS, COMMAND_STAGES, CommandCenterStage,
    MAX_REQUEST_BYTES, OutboxIntention, ROUTES, decode_request, validate_projection)
from mission_control.connection_gateway import Budget, Gateway, LocalContext, LocalRateLimit, RateExceeded
from mission_control.connection_services import PhaseOneServices
from mission_control.readiness import require_operational_authorization
from tests.connection_support import context, encoded, envelope, gateway_fixture, MemoryAudit
from tests.pilot_support import TENANT, pilot_authority, pilot_contracts
from tests.test_production_readiness import readiness_fixtures


class ConnectionLayerTests(unittest.TestCase):
    def setUp(self): self.gateway, self.services, self.audit = gateway_fixture()

    def call(self, data=None, method='GET', path='/health', ctx=None):
        return self.gateway.handle(method,path,encoded(data or envelope()),ctx or context())

    def test_default_constructor_denies_without_dependencies(self):
        self.assertEqual(Gateway().handle('GET','/health',encoded(envelope()),context())[0],403)

    def test_health_requires_verified_identity_and_returns_no_configuration(self):
        code, body = self.call()
        self.assertEqual(code,200);self.assertEqual(body['result'],{'state':'inactive'})
        self.assertFalse(body['operational_authorized']);self.assertIsNone(body['inactive_outbox'])

    def test_missing_trusted_context_denies(self):
        self.assertEqual(self.gateway.handle('GET','/health',encoded(envelope()))[0],403)

    def test_request_cannot_construct_authority_or_credentials(self):
        for name in ('roles','authorized','token','gate','credentials','enabled','authorization_decision_reference'):
            data=envelope();data[name]='syn-private-marker'
            self.assertEqual(self.call(data)[0],400)
        self.assertEqual(self.services.calls,[])

    def test_duplicate_keys_rejected_even_if_values_are_inactive(self):
        raw=encoded(envelope())[:-1]+b',"schema_version":1}'
        self.assertEqual(self.gateway.handle('GET','/health',raw,context())[0],400)

    def test_nonfinite_json_rejected(self):
        raw=encoded(envelope()).replace(b'"expected_revision": 1',b'"expected_revision": NaN')
        self.assertEqual(self.gateway.handle('GET','/health',raw,context())[0],400)

    def test_unknown_nested_fields_rejected(self):
        data=envelope();data['payload']={'password':'syn-private-marker'}
        self.assertEqual(self.call(data)[0],400)

    def test_size_limit_precedes_parsing_and_domain(self):
        self.assertEqual(self.gateway.handle('GET','/health',b'x'*(MAX_REQUEST_BYTES+1),context())[0],400)
        self.assertEqual(self.services.calls,[])

    def test_invalid_encoding_and_nonobject_input_rejected(self):
        for raw in (b'\xff',b'[]',b'null',b'{',{},'{}'):
            self.assertEqual(self.gateway.handle('GET','/health',raw,context())[0],400)

    def test_envelope_must_have_exact_fields(self):
        for name in envelope():
            data=envelope();data.pop(name)
            self.assertEqual(self.call(data)[0],400,name)

    def test_non_synthetic_classification_denied(self):
        for value in ('confidential','public',None):
            self.assertEqual(self.call(envelope(data_classification=value))[0],400)

    def test_actor_reference_cannot_impersonate_another_subject(self):
        self.assertEqual(self.call(envelope(actor_reference='syn-other-actor'))[0],403)

    def test_actor_type_must_match_verified_session(self):
        self.assertEqual(self.call(envelope(actor_type='service'))[0],403)

    def test_authentication_state_must_match_trusted_context(self):
        self.assertEqual(self.call(envelope(authentication_state_reference='syn-forged-session'))[0],403)

    def test_cross_tenant_context_denied_before_domain(self):
        self.assertEqual(self.call(envelope(tenant='syn-tenant-2'))[0],403)
        self.assertEqual(self.services.calls,[])

    def test_expired_and_revoked_session_denied(self):
        gate=self.gateway.gate;reference=context().session_reference;original=gate.authority.sessions[reference]
        for principal in (replace(original.principal,revoked=True),
                          replace(original.principal,expires_at=datetime.now(timezone.utc)-timedelta(seconds=1))):
            gate.authority.sessions[reference]=replace(original,principal=principal)
            self.assertEqual(self.call()[0],403)

    def test_verified_identity_without_permission_denied(self):
        self.assertEqual(self.call(envelope(purpose='syn-unresolved-purpose'))[0],403)
        self.gateway.gate.admitted_surfaces=()
        self.assertEqual(self.call()[0],403)
        self.gateway.gate.admitted_surfaces=('syn-dashboard',)
        self.assertEqual(self.call(envelope(role='data_writer'),ctx=context('data_writer'))[0],403)

    def test_explicit_deny_overrides_allow(self):
        from mission_control.synthetic_identity import SyntheticGrant
        authority=self.gateway.gate.authority;policy=authority.policies[TENANT]
        authority.policies[TENANT]=replace(policy,grants=(*policy.grants,SyntheticGrant('audit_reviewer','audit.read','syn-audit','deny')))
        self.assertEqual(self.call()[0],403)

    def test_request_timestamps_are_aware_and_fresh(self):
        for stamp in ('2020-01-01T00:00:00+00:00','2026-01-01T00:00:00','invalid'):
            self.assertEqual(self.call(envelope(timestamp=stamp))[0],400)

    def test_revisions_reject_boolean_float_zero_health_and_negative(self):
        for revision in (True,1.0,'1',-1):
            self.assertEqual(self.call(envelope(expected_revision=revision))[0],400)
        self.assertEqual(self.call(envelope(expected_revision=0))[0],409)

    def test_method_action_and_path_binding(self):
        self.assertEqual(self.call(path='/'+'x'*256)[0],400)
        self.assertEqual(self.call(method='POST')[0],404)
        self.assertEqual(self.call(path='/v1/readiness')[0],400)
        data=envelope('journey.read',resource='syn-pilot-journey-1',role='data_writer')
        self.assertEqual(self.call(data,path='/v1/journeys/syn-other',ctx=context('data_writer'))[0],400)

    def test_rate_limit_is_default_required(self):
        self.gateway.rate_limit=None
        self.assertEqual(self.call()[0],403)

    def test_rate_limit_concurrent_admission_is_bounded(self):
        limiter=LocalRateLimit(3)
        def attempt(_):
            try:limiter.admit(TENANT,'syn-actor');return True
            except RateExceeded:return False
        with ThreadPoolExecutor(max_workers=8) as pool: result=list(pool.map(attempt,range(20)))
        self.assertEqual(sum(result),3)

    def test_rate_limit_bounds_principal_storage(self):
        limiter=LocalRateLimit(1,max_principals=1);limiter.admit(TENANT,'syn-actor')
        with self.assertRaises(RateExceeded):limiter.admit(TENANT,'syn-other')

    def test_rate_denial_never_calls_domain(self):
        self.gateway.rate_limit=LocalRateLimit(1)
        self.assertEqual(self.call()[0],200);self.assertEqual(self.call()[0],429)

    def test_cancelled_request_never_calls_domain(self):
        ctx=context();ctx.cancelled.set()
        self.assertEqual(self.call(ctx=ctx)[0],408);self.assertEqual(self.services.calls,[])

    def test_budget_deadline_fails_closed(self):
        with self.assertRaises(TimeoutError):Budget(context(),seconds=0).check()

    def test_audit_failure_precedes_domain_and_contains_no_payload(self):
        self.gateway.audit_sink=SimpleNamespace(append=lambda value:(_ for _ in ()).throw(OSError('syn-private-marker')))
        code,body=self.call();self.assertEqual(code,503);self.assertNotIn('syn-private-marker',str(body))
        self.assertEqual(self.services.calls,[])

    def test_audit_minimizes_references_without_directives_or_proofs(self):
        self.call();row=self.audit.rows[0]
        self.assertEqual(row['decision'],'authorized_attempt')
        self.assertFalse({'payload','directive','output','evidence','credentials','authentication_state_reference'} & row.keys())

    def test_errors_do_not_echo_rejected_bytes(self):
        code,body=self.gateway.handle('GET','/health',b'{"syn-private-marker":1}',context())
        self.assertEqual(code,400);self.assertNotIn('syn-private-marker',str(body));self.assertEqual(self.audit.rows,[])

    def test_disabled_connectors_have_no_transport_and_cannot_activate(self):
        for connector in CONNECTORS:
            connector.validate()
            with self.assertRaises(PermissionError):connector.transmit('syn-data')
            with self.assertRaises(PermissionError):replace(connector,enabled=True).validate()
        self.assertEqual(len(CONNECTORS),7)

    def test_outbox_rejects_unknown_connector_and_activation_fields(self):
        data=envelope('outbox.prepare','syn-packet',{'connector_reference':'syn-unknown','record_reference':'syn-packet'})
        self.assertEqual(self.call(data,method='POST',path='/v1/outbox')[0],400)
        data['payload']={'connector_reference':'syn-slack','record_reference':'syn-packet','enabled':True}
        self.assertEqual(self.call(data,method='POST',path='/v1/outbox')[0],400)

    def test_outbox_intention_is_inactive_reference_only(self):
        record=OutboxIntention(TENANT,'syn-request','syn-journey','syn-actor','syn-slack','syn-record','syn-decision','syn-audit')
        record.validate()
        with self.assertRaises(ValueError):replace(record,state='active').validate()
        self.assertNotIn('payload',asdict(record))

    def test_command_center_all_six_stages_are_inactive_unresolved(self):
        for stage in COMMAND_STAGES:
            record=CommandCenterStage(stage,'syn-record-type',None,(),None,(),(),True,None,(),None)
            record.validate()
            with self.assertRaises(ValueError):replace(record,status='active').validate()
        self.assertEqual(len(COMMAND_STAGES),6)

    def test_projection_rejects_full_records_secrets_and_operational_authority(self):
        for bad in ({'payload':'syn-private-marker'},{'state':'active'},{'operational_authorized':True},{'record_reference':'real text'},{'state':'inactive','revision':True},{'state':'inactive','passed':1}):
            with self.assertRaises(ValueError):validate_projection(bad)

    def test_no_network_provider_or_cli_path(self):
        with patch.object(socket,'socket',side_effect=AssertionError('No network')):
            self.assertEqual(self.call()[0],200)
        with self.assertRaises(PermissionError):require_operational_authorization()

    def test_existing_readiness_assessor_is_reused(self):
        evidence,package,_,_=readiness_fixtures();authority,_=pilot_authority()
        services=PhaseOneServices(SimpleNamespace(authority=authority),{(TENANT,package.package_id):(package,evidence)})
        self.gateway,_,_=gateway_fixture(authority,services)
        data=envelope('readiness.status',package.package_id)
        code,body=self.call(data,path='/v1/readiness')
        self.assertEqual(code,200);self.assertEqual(body['result']['verified_controls'],12)
        self.assertFalse(body['result']['operational_authorized'])

    def test_readiness_source_must_be_configured_and_revision_bound(self):
        authority,_=pilot_authority();self.gateway,_,_=gateway_fixture(authority,PhaseOneServices(SimpleNamespace(authority=authority)))
        self.assertNotEqual(self.call(envelope('readiness.status','syn-package'),path='/v1/readiness')[0],200)

    def test_existing_technical_governance_is_reused_without_returning_output(self):
        authority,_=pilot_authority();services=PhaseOneServices(SimpleNamespace(authority=authority),
            governance_sources={(TENANT,'syn-artifact'):(1,'synthetic incomplete artifact')})
        self.gateway,_,_=gateway_fixture(authority,services)
        code,body=self.call(envelope('governance.review','syn-artifact',{'output_reference':'syn-artifact'}),method='POST',path='/v1/governance/review')
        self.assertEqual(code,200);self.assertFalse(body['result']['passed'])
        self.assertNotIn('artifact',str(body['result']))

    def test_openapi_covers_every_gateway_route_and_strict_envelope(self):
        from pathlib import Path
        spec=json.loads((Path(__file__).resolve().parents[1]/'docs/phase-2a-openapi.json').read_text())
        for method,path in ROUTES:self.assertIn(method.lower(),spec['paths'][path])
        schema=spec['components']['schemas']['ConnectionRequest']
        self.assertFalse(schema['additionalProperties'])
        self.assertEqual(set(schema['required']),set(envelope()))
        def walk(value):
            if isinstance(value,dict):
                if '$ref' in value:
                    self.assertIn(value['$ref'].split('/')[-1],spec['components']['schemas'])
                for child in value.values():walk(child)
            elif isinstance(value,list):
                for child in value:walk(child)
        walk(spec)
        examples=json.loads((Path(__file__).resolve().parents[1]/'examples/phase-2a-synthetic-requests.json').read_text())
        for data in examples['requests']:
            decode_request(encoded(data),now=datetime.fromisoformat(data['timestamp']))
