"""Offline identity/session negative contracts and unchanged boundary compatibility."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict,replace
from datetime import timedelta,timezone,datetime
import json
import threading
import unittest
from unittest.mock import patch

from mission_control.identity_sessions import *
from tests.identity_session_support import fixture,issued,check,bind_legacy
from tests.connection_support import gateway_fixture,envelope,encoded
from tests.pilot_support import JOURNEY


class IdentitySessionTests(unittest.TestCase):
    def test_valid_issue_and_claims(self):
        a,c,s,e,_=issued();r=check(a,s)
        self.assertEqual(r.subject,s);self.assertEqual(r.revision,1)
        self.assertNotEqual(s.subject_reference,s.external_subject_reference)
        self.assertEqual(r.evidence.provider_reference,'syn-provider')
    def test_exact_expiration_of_provider_receipt(self):
        a,c,s,e,_=fixture();c.advance(300)
        with self.assertRaises(IdentityDenied):a.issue('syn-session',s.subject_reference,e.reference,e.challenge_reference)
        self.assertFalse(a.snapshot())
    def test_unknown_subject(self):
        a,c,s,e,_=fixture()
        with self.assertRaises(IdentityDenied):a.issue('syn-session','syn-unknown',e.reference,e.challenge_reference)
    def test_email_is_not_subject(self):
        a,c,s,e,_=fixture()
        with self.assertRaises(IdentityDenied):a.issue('syn-session','not-an-identity@example.invalid',e.reference,e.challenge_reference)
    def test_duplicate_session(self):
        a,c,s,e,_=issued()
        with self.assertRaises(IdentityDenied):a.issue('syn-session',s.subject_reference,e.reference,e.challenge_reference)
        self.assertEqual(len(a.snapshot()),1)
    def test_replayed_receipt_across_session(self):
        a,c,s,e,_=issued()
        with self.assertRaises(IdentityDenied):a.issue('syn-second',s.subject_reference,e.reference,e.challenge_reference)
    def test_wrong_challenge(self):
        a,c,s,e,_=fixture()
        with self.assertRaises(IdentityDenied):a.issue('syn-session',s.subject_reference,e.reference,'syn-wrong')
    def test_wrong_audience_provider_issuer_tenant_subject(self):
        for field in ('audience_reference','provider_reference','issuer_reference','tenant_reference','external_subject_reference'):
            a,c,s,e,_=fixture();bad=replace(e,**{field:'syn-wrong'})
            a.provider=DeterministicIdentityProvider((bad,))
            with self.subTest(field=field),self.assertRaises(IdentityDenied):a.issue('syn-session',s.subject_reference,bad.reference,bad.challenge_reference)
    def test_missing_or_insufficient_mfa(self):
        _,_,_,e,_=fixture()
        for changes in ({'assurance':'syn-single-factor'},{'methods':()},{'methods':('syn-factor-possession',)},{'methods':('syn-factor-possession','syn-factor-possession')},{'methods':('syn-factor-possession','syn-unknown')}):
            with self.subTest(changes=changes),self.assertRaises(IdentityDenied):replace(e,**changes).validate()
    def test_future_or_naive_evidence(self):
        a,c,s,e,_=fixture()
        for changes in ({'issued_at':c.now+timedelta(seconds=1)},{'authenticated_at':c.now.replace(tzinfo=None)}):
            with self.subTest(changes=changes),self.assertRaises(IdentityDenied):
                bad=replace(e,**changes);a.provider=DeterministicIdentityProvider((bad,));a.issue('syn-session',s.subject_reference,bad.reference,bad.challenge_reference)
    def test_identity_substitution(self):
        a,c,s,_,_=issued()
        with self.assertRaises(IdentityDenied):a.check('syn-session',1,'syn-another',s.tenant_reference,'syn-check')
    def test_cross_tenant(self):
        a,c,s,_,_=issued()
        with self.assertRaises(IdentityDenied):a.check('syn-session',1,s.subject_reference,'syn-tenant-2','syn-check')
    def test_unknown_session(self):
        a,c,s,_,_=issued()
        with self.assertRaises(IdentityDenied):a.check('syn-missing',1,s.subject_reference,s.tenant_reference,'syn-check')
    def test_stale_and_boolean_revision(self):
        a,c,s,_,_=issued()
        for rev in (0,2,True,'1'):
            with self.subTest(rev=rev),self.assertRaises(IdentityDenied):check(a,s,revision=rev)
    def test_inactivity_exact_boundary(self):
        a,c,s,_,_=issued();c.advance(900)
        with self.assertRaises(IdentityDenied):check(a,s)
    def test_activity_renews_idle_not_absolute(self):
        a,c,s,_,_=issued(policy_changes={'absolute_seconds':1000,'inactivity_seconds':600})
        c.advance(500);check(a,s,'syn-check-1');c.advance(499);check(a,s,'syn-check-2');c.advance(1)
        with self.assertRaises(IdentityDenied):check(a,s,'syn-check-3')
    def test_reauthentication_required_and_valid(self):
        a,c,s,e,new=issued();c.advance(301);scope=ScopeRequirement(s.roles,sensitive=True)
        with self.assertRaises(IdentityDenied):check(a,s,scope=scope)
        r=a.reauthenticate('syn-session',1,s.subject_reference,s.tenant_reference,new.reference,new.challenge_reference)
        self.assertEqual(r.revision,2);check(a,s,'syn-after',2,scope)
        with self.assertRaises(IdentityDenied):check(a,s,'syn-stale',1,scope)
    def test_reauthentication_cannot_reset_absolute_timeout(self):
        a,c,s,e,new=issued(policy_changes={'absolute_seconds':400,'inactivity_seconds':350})
        c.advance(301);r=a.reauthenticate('syn-session',1,s.subject_reference,s.tenant_reference,new.reference,new.challenge_reference)
        self.assertEqual(r.absolute_expires_at,r.issued_at+timedelta(seconds=400));c.advance(99)
        with self.assertRaises(IdentityDenied):check(a,s,'syn-check',2)
    def test_reauth_replay_and_same_authentication_denied(self):
        a,c,s,e,_=issued()
        with self.assertRaises(IdentityDenied):a.reauthenticate('syn-session',1,s.subject_reference,s.tenant_reference,e.reference,e.challenge_reference)
    def test_revocation_and_reissue_denied(self):
        a,c,s,e,_=issued();r=a.revoke('syn-session',1);self.assertTrue(r.revoked)
        with self.assertRaises(IdentityDenied):check(a,s)
        with self.assertRaises(IdentityDenied):a.revoke('syn-session',1)
        with self.assertRaises(IdentityDenied):a.issue('syn-session',s.subject_reference,e.reference,e.challenge_reference)
    def test_role_department_team_executive_scope(self):
        a,c,s,_,_=issued();check(a,s,scope=ScopeRequirement(s.roles,'syn-department','syn-team','syn-executive'))
        for scope in (ScopeRequirement(('policy_admin',)),ScopeRequirement(s.roles,'syn-other'),ScopeRequirement(s.roles,team='syn-other'),ScopeRequirement(s.roles,executive='syn-other')):
            with self.subTest(scope=scope),self.assertRaises(IdentityDenied):check(a,s,'syn-bad',scope=scope)
    def test_entitlement_revision_invalidates_existing_sessions(self):
        a,c,s,_,_=issued();a.revise_subject(replace(s,revision=2,roles=('data_writer',)),1)
        with self.assertRaises(IdentityDenied):check(a,s)
    def test_subject_binding_cannot_be_reassigned(self):
        a,c,s,_,_=issued()
        for change in ({'tenant_reference':'syn-other'},{'external_subject_reference':'syn-other'},{'revision':3}):
            with self.subTest(change=change),self.assertRaises(IdentityDenied):a.revise_subject(replace(s,revision=2,**change) if 'revision' not in change else replace(s,**change),1)
    def test_disabled_subject(self):
        a,c,s,e,_=fixture();a.revise_subject(replace(s,revision=2,disabled=True),1)
        with self.assertRaises(IdentityDenied):a.issue('syn-session',s.subject_reference,e.reference,e.challenge_reference)
    def test_conflicting_privileged_roles(self):
        _,_,s,_,_=fixture()
        with self.assertRaises(IdentityDenied):replace(s,roles=('policy_admin','approval_issuer')).validate()
    def test_operation_replay(self):
        a,c,s,_,_=issued();check(a,s)
        before=a.snapshot()
        with self.assertRaises(IdentityDenied):check(a,s)
        self.assertEqual(before,a.snapshot())
    def test_clock_regression_fails_closed(self):
        a,c,s,_,_=issued();c.advance(-1)
        with self.assertRaises(IdentityDenied):check(a,s)
    def test_journal_failure_leaves_no_issued_or_consumed_state(self):
        journal=DecisionJournal();a,c,s,e,_=fixture(journal=journal)
        with patch.object(journal,'append',side_effect=RuntimeError('synthetic-private-marker')):
            with self.assertRaises(IdentityDenied) as error:a.issue('syn-session',s.subject_reference,e.reference,e.challenge_reference)
        self.assertNotIn('private-marker',str(error.exception));self.assertFalse(a.snapshot())
        a.issue('syn-session',s.subject_reference,e.reference,e.challenge_reference)
    def test_failed_check_and_revoke_do_not_partially_mutate(self):
        a,c,s,_,_=issued();before=a.snapshot()
        with patch.object(a.journal,'append',side_effect=RuntimeError('synthetic')):
            with self.assertRaises(IdentityDenied):check(a,s)
            with self.assertRaises(IdentityDenied):a.revoke('syn-session',1)
        self.assertEqual(a.snapshot(),before)
    def test_capacity_fail_closed(self):
        a,c,s,_,_=issued(journal=DecisionJournal(1))
        with self.assertRaises(IdentityDenied):check(a,s)
    def test_concurrent_duplicate_issuance_only_one(self):
        a,c,s,e,_=fixture()
        def issue(_):
            try:a.issue('syn-session',s.subject_reference,e.reference,e.challenge_reference);return True
            except IdentityDenied:return False
        with ThreadPoolExecutor(max_workers=2) as pool:self.assertEqual(sum(pool.map(issue,range(2))),1)
    def test_concurrent_revocation_has_one_current_revision(self):
        a,c,s,_,_=issued()
        def revoke(_):
            try:a.revoke('syn-session',1);return True
            except IdentityDenied:return False
        with ThreadPoolExecutor(max_workers=2) as pool:self.assertEqual(sum(pool.map(revoke,range(2))),1)
        with self.assertRaises(IdentityDenied):check(a,s,'syn-after')
    def test_close_invalidates_sessions(self):
        a,c,s,_,_=issued();a.close();self.assertFalse(a.snapshot())
        with self.assertRaises(IdentityDenied):check(a,s)
    def test_provider_default_and_foreign_adapter_deny(self):
        a,c,s,e,_=fixture()
        with self.assertRaises(IdentityDenied):SyntheticSessionAuthority(object(),(s,),a.policy,c)
        empty=SyntheticSessionAuthority(DeterministicIdentityProvider(),(s,),a.policy,c)
        with self.assertRaises(IdentityDenied):empty.issue('syn-session',s.subject_reference,e.reference,e.challenge_reference)
    def test_strict_json_and_no_token_fields(self):
        _,_,_,e,_=fixture();value=asdict(e)
        for key in ('authenticated_at','issued_at','expires_at'):value[key]=value[key].isoformat()
        raw=json.dumps(value).encode();self.assertEqual(decode_evidence(raw),e)
        for raw in (b'\xff',b'{"reference":1,"reference":2}',b'{"x":NaN}',b' '*16385,json.dumps(dict(value,access_token='synthetic-rejected-raw-value')).encode(),json.dumps(dict(value,roles=['policy_admin'])).encode()):
            with self.subTest(raw_type=type(raw)),self.assertRaises(IdentityDenied) as error:decode_evidence(raw)
            self.assertNotIn('rejected-raw-value',str(error.exception))
    def test_audit_only_minimized_decisions(self):
        a,c,s,_,_=issued();check(a,s);a.revoke('syn-session',1)
        rows=[asdict(r) for r in a.journal.snapshot()]
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(set(row),{'sequence','subject_reference','tenant_reference','operation','allowed','code','at'})
            self.assertNotIn('syn-challenge',str(row));self.assertNotIn('syn-auth-context',str(row))

    def test_audit_rejects_raw_or_unbounded_fields(self):
        a,c,s,_,_=issued()
        for changes in ({'operation':'synthetic-rejected-raw-value'},{'subject_reference':'email@example.invalid'},{'allowed':1},{'code':'raw-private-value'},{'sequence':True}):
            journal=DecisionJournal();decision=IdentityDecision(1,s.subject_reference,s.tenant_reference,'issue',True,'allowed',c.now)
            with self.subTest(changes=changes),self.assertRaises(IdentityDenied):journal.append(replace(decision,**changes))
            self.assertEqual(journal.snapshot(),())
    def test_oversized_duplicate_subjects_and_provider_records(self):
        a,c,s,e,_=fixture()
        with self.assertRaises(IdentityDenied):DeterministicIdentityProvider((e,e))
        with self.assertRaises(IdentityDenied):SyntheticSessionAuthority(a.provider,(s,s),a.policy,c)
    def test_malformed_scope_and_subject_fields_fail_closed(self):
        a,c,s,_,_=issued()
        for scope in (ScopeRequirement(()),ScopeRequirement(('unknown',)),ScopeRequirement(s.roles,team='email@example.invalid'),ScopeRequirement(s.roles,sensitive=1)):
            with self.subTest(scope=scope),self.assertRaises(IdentityDenied):check(a,s,scope=scope)
        for changes in ({'roles':[]},{'roles':({'role':'policy_admin'},)},{'teams':('syn-team','syn-team')},{'disabled':1}):
            with self.subTest(changes=changes),self.assertRaises(IdentityDenied):replace(s,**changes).validate()
    def test_post_revocation_checks_concurrently_all_deny(self):
        a,c,s,_,_=issued();a.revoke('syn-session',1)
        def denied(index):
            try:check(a,s,'syn-after-'+str(index));return False
            except IdentityDenied:return True
        with ThreadPoolExecutor(max_workers=4) as pool:self.assertTrue(all(pool.map(denied,range(12))))

    def test_clock_source_failure_is_sanitized(self):
        a,c,s,_,_=issued()
        with patch.object(a,'clock',side_effect=RuntimeError('synthetic-private-marker')):
            with self.assertRaises(IdentityDenied) as error:check(a,s)
        self.assertNotIn('private-marker',str(error.exception))


class IdentityCompatibilityTests(unittest.TestCase):
    def test_existing_gateway_requires_both_authorities(self):
        gateway,services,_=gateway_fixture();legacy=gateway.gate.authority
        a,c,s,guard,context=bind_legacy(legacy,requirements={('journey.pilot.read',JOURNEY):ScopeRequirement(('data_writer',))})
        services.result=dict(state='inactive',journey_reference=JOURNEY,original_classification='syn-class',version=0,completed_stage=0,events=[])
        raw=encoded(envelope('journey.read',JOURNEY,role='data_writer',revision=0))
        self.assertEqual(gateway.handle('GET','/v1/journeys/'+JOURNEY,raw,context)[0],200)
        a.revoke('syn-session',1)
        self.assertEqual(gateway.handle('GET','/v1/journeys/'+JOURNEY,raw,context)[0],403)
    def test_contract_scope_never_grants_missing_legacy_policy(self):
        gateway,_,_=gateway_fixture();a,c,s,g,ctx=bind_legacy(gateway.gate.authority,requirements={('journey.pilot.read','syn-no-grant'):ScopeRequirement(('data_writer',))})
        raw=encoded(envelope('journey.read','syn-no-grant',role='data_writer'))
        self.assertEqual(gateway.handle('GET','/v1/journeys/syn-no-grant',raw,ctx)[0],403)
    def test_guard_default_denies_unlisted_actions(self):
        gateway,_,_=gateway_fixture();_,_,_,_,ctx=bind_legacy(gateway.gate.authority)
        raw=encoded(envelope('journey.read',JOURNEY,role='data_writer',revision=0))
        self.assertEqual(gateway.handle('GET','/v1/journeys/'+JOURNEY,raw,ctx)[0],403)
    def test_guard_identity_and_policy_substitution(self):
        gateway,_,_=gateway_fixture();a,c,s,g,ctx=bind_legacy(gateway.gate.authority)
        with self.assertRaises(IdentityDenied):g.validate(ctx.session_reference,s.tenant_reference,2)
        wrong=replace(gateway.gate.authority.sessions[ctx.session_reference].principal,subject_reference='syn-impostor')
        with self.assertRaises(IdentityDenied):g.validate(ctx.session_reference,s.tenant_reference,1,wrong)
    def test_gateway_lease_serializes_revocation_with_admitted_work(self):
        gateway,services,_=gateway_fixture();a,c,s,g,ctx=bind_legacy(gateway.gate.authority,requirements={('journey.pilot.read',JOURNEY):ScopeRequirement(('data_writer',))})
        entered=threading.Event();release=threading.Event();revoked=threading.Event()
        def work(*_):entered.set();self.assertTrue(release.wait(5));return {'state':'inactive'}
        raw=encoded(envelope('journey.read',JOURNEY,role='data_writer',revision=0))
        with patch.object(services,'execute',side_effect=work),ThreadPoolExecutor(max_workers=2) as pool:
            future=pool.submit(gateway.handle,'GET','/v1/journeys/'+JOURNEY,raw,ctx);self.assertTrue(entered.wait(5))
            other=pool.submit(lambda:(a.revoke('syn-session',1),revoked.set()))
            self.assertFalse(revoked.wait(.05));release.set();self.assertEqual(future.result()[0],200);other.result()
        self.assertTrue(revoked.is_set());self.assertEqual(gateway.handle('GET','/v1/journeys/'+JOURNEY,raw,ctx)[0],403)
    def test_http_binding_and_revocation_preserve_token_boundary(self):
        from tests.local_http_support import running,request
        gateway,_,_=gateway_fixture()
        a,c,s,g,ctx=bind_legacy(gateway.gate.authority,'audit_reviewer',{('audit.read','syn-audit'):ScopeRequirement(('audit_reviewer',))})
        with running(gateway) as (server,binding):
            self.assertEqual(request(server,binding,envelope())[0],200)
            a.revoke('syn-session',1)
            self.assertEqual(request(server,binding,envelope())[0],403)
    def test_command_center_cookie_cannot_bypass_contract_revocation(self):
        from mission_control.command_center_ui import UIConfig,ROOT
        from tests.command_center_support import running_ui,session,ui_request
        gateway,services,_=gateway_fixture()
        a,c,s,g,ctx=bind_legacy(gateway.gate.authority,requirements={('journey.pilot.read',JOURNEY):ScopeRequirement(('data_writer',))})
        services.result=dict(state='inactive',journey_reference=JOURNEY,original_classification='syn-class',version=0,completed_stage=None,events=[])
        config=UIConfig(reads=(encoded(envelope('journey.read',JOURNEY,role='data_writer',revision=0)),))
        with running_ui(gateway,config,'data_writer') as (server,binding):
            cookie,view=session(server);self.assertEqual(view['stages'][0],'information')
            self.assertNotIn('syn-auth-context',str(view));self.assertNotIn('syn-challenge',str(view))
            a.revoke('syn-session',1)
            self.assertEqual(ui_request(server,ROOT+'/api/overview',cookie=cookie)[0],403)
    def test_contract_reauth_revision_must_be_rebound_by_server(self):
        gateway,_,_=gateway_fixture();a,c,s,g,ctx=bind_legacy(gateway.gate.authority)
        c.advance(301);e=a.provider.resolve('syn-evidence-2')
        a.reauthenticate('syn-session',1,s.subject_reference,s.tenant_reference,e.reference,e.challenge_reference)
        with self.assertRaises(IdentityDenied):g.validate(ctx.session_reference,s.tenant_reference,1)
        g.bindings[ctx.session_reference]=replace(g.bindings[ctx.session_reference],session_revision=2)
        g.validate(ctx.session_reference,s.tenant_reference,1)

    def test_multiple_guard_instances_share_replay_counter(self):
        gateway,_,_=gateway_fixture();a,c,s,g,ctx=bind_legacy(gateway.gate.authority)
        other=ContractGuard(a,g.bindings,g.requirements)
        g.validate(ctx.session_reference,s.tenant_reference,1)
        other.validate(ctx.session_reference,s.tenant_reference,1)
    def test_binding_denial_is_audited_without_activity_change(self):
        gateway,_,_=gateway_fixture();a,c,s,g,ctx=bind_legacy(gateway.gate.authority)
        before=a.snapshot();c.advance(1)
        with self.assertRaises(IdentityDenied):g.validate('syn-unknown',s.tenant_reference,1)
        self.assertEqual(a.snapshot(),before);self.assertFalse(a.journal.snapshot()[-1].allowed)
