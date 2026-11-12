"""Explicit tokenless deterministic identity lifecycle demo; no socket or database."""
import sys
from pathlib import Path
from datetime import datetime,timedelta,timezone
from dataclasses import replace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    if sys.argv[1:]!=['--synthetic-development']:
        print('Explicit --synthetic-development required; no arguments or values accepted.',file=sys.stderr);return 2
    from mission_control.identity_sessions import (IdentityEvidence,SubjectClaims,SessionPolicy,
        DeterministicIdentityProvider,SyntheticSessionAuthority,ScopeRequirement,IdentityDenied)
    now=[datetime(2026,1,1,tzinfo=timezone.utc)]
    first=IdentityEvidence('syn-demo-evidence','syn-demo-challenge','syn-provider','syn-issuer','syn-audience','syn-external','syn-tenant','syn-context','syn-mfa',('syn-factor-possession','syn-factor-knowledge'),now[0],now[0],now[0]+timedelta(minutes=5))
    fresh=replace(first,reference='syn-demo-fresh',challenge_reference='syn-demo-fresh-challenge',authenticated_at=now[0]+timedelta(seconds=301),issued_at=now[0]+timedelta(seconds=301),expires_at=now[0]+timedelta(seconds=601))
    subject=SubjectClaims('syn-internal-subject','syn-external','syn-provider','syn-tenant',1,('data_reader',))
    authority=SyntheticSessionAuthority(DeterministicIdentityProvider((first,fresh)),(subject,),SessionPolicy('syn-provider','syn-issuer','syn-audience'),lambda:now[0])
    def denied(call):
        try:call()
        except IdentityDenied:return
        raise AssertionError('Expected default denial')
    try:
        authority.issue('syn-demo-session',subject.subject_reference,first.reference,first.challenge_reference)
        authority.check('syn-demo-session',1,subject.subject_reference,subject.tenant_reference,'syn-demo-check')
        now[0]+=timedelta(seconds=301)
        denied(lambda:authority.check('syn-demo-session',1,subject.subject_reference,subject.tenant_reference,'syn-sensitive',ScopeRequirement(subject.roles,sensitive=True)))
        authority.reauthenticate('syn-demo-session',1,subject.subject_reference,subject.tenant_reference,fresh.reference,fresh.challenge_reference)
        authority.check('syn-demo-session',2,subject.subject_reference,subject.tenant_reference,'syn-fresh-check',ScopeRequirement(subject.roles,sensitive=True))
        authority.revoke('syn-demo-session',2)
        denied(lambda:authority.check('syn-demo-session',2,subject.subject_reference,subject.tenant_reference,'syn-after-revoke'))
    finally:authority.close()
    assert not authority.snapshot()
    print('PASS: synthetic issuance, validation, stale step-up denial, reauthentication, revision binding, revocation and cleanup. No credentials, tokens, keys, persistence, listener or provider connection.')
    return 0


if __name__=='__main__':raise SystemExit(main())
