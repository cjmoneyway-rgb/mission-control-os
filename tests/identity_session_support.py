"""Opaque deterministic contract fixtures; no tokens, keys or provider calls."""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from mission_control.identity_sessions import (IdentityEvidence,DeterministicIdentityProvider,
    SubjectClaims,SessionPolicy,SyntheticSessionAuthority,ContractGuard,SessionBinding,ScopeRequirement)


class Clock:
    def __init__(self,now=None):self.now=now or datetime.now(timezone.utc)
    def __call__(self):return self.now
    def advance(self,seconds):self.now+=timedelta(seconds=seconds)


def fixture(subject='syn-subject-1',role='data_reader',now=None,policy_changes=None,journal=None):
    clock=Clock(now)
    claim=SubjectClaims(subject,'syn-external-1','syn-provider','syn-tenant-1',1,(role,),('syn-department',),('syn-team',),('syn-executive',))
    first=IdentityEvidence('syn-evidence-1','syn-challenge-1','syn-provider','syn-issuer','syn-audience','syn-external-1','syn-tenant-1','syn-auth-context','syn-mfa',('syn-factor-possession','syn-factor-knowledge'),clock.now,clock.now,clock.now+timedelta(minutes=5))
    second=replace(first,reference='syn-evidence-2',challenge_reference='syn-challenge-2',authenticated_at=clock.now+timedelta(seconds=301),issued_at=clock.now+timedelta(seconds=301),expires_at=clock.now+timedelta(seconds=601))
    provider=DeterministicIdentityProvider((first,second))
    policy=SessionPolicy('syn-provider','syn-issuer','syn-audience',**(policy_changes or {}))
    authority=SyntheticSessionAuthority(provider,(claim,),policy,clock,journal)
    return authority,clock,claim,first,second


def issued(**kwargs):
    authority,clock,claim,first,second=fixture(**kwargs)
    authority.issue('syn-session',claim.subject_reference,first.reference,first.challenge_reference)
    return authority,clock,claim,first,second


def check(authority,claim,request='syn-check',revision=1,scope=None):
    return authority.check('syn-session',revision,claim.subject_reference,claim.tenant_reference,request,scope)


def bind_legacy(legacy,role='data_writer',requirements=None):
    from tests.connection_support import context
    from tests.synthetic_postgres_support import session_ref
    reference=session_ref(role);principal=legacy.sessions[reference].principal
    authority,clock,claim,first,second=issued(subject=principal.subject_reference,role=role)
    guard=ContractGuard(authority,{reference:SessionBinding('syn-session',claim.subject_reference,claim.tenant_reference,1,1)},requirements or {})
    legacy.contract_guard=guard
    return authority,clock,claim,guard,context(role)
