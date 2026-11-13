"""Explicit offline fictional projection demo. No vendor, token or domain writes."""
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from dataclasses import replace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def fixture(now=None, journal=None):
    """Trusted fabricated installer, deterministic for the supplied UTC instant."""
    from mission_control.hubspot_projection import Mapping, Observation, MockProjection
    from mission_control.registry_authorization import Principal
    from mission_control.synthetic_identity import SyntheticSession, SyntheticAuthority, SyntheticGrant, SyntheticPolicy
    from mission_control.identity_sessions import (SubjectClaims, IdentityEvidence,
        DeterministicIdentityProvider, SessionPolicy, SyntheticSessionAuthority,
        SessionBinding, ContractGuard, ScopeRequirement)
    clock = [now or datetime.now(timezone.utc)]
    start = clock[0]
    tenant = 'syn-fictional-tenant'
    subject = 'syn-fictional-subject'
    session = 'syn-fictional-legacy-session'
    ms = tuple(Mapping('syn-fictional-map-' + str(i), tenant, 'syn-fictional-portal',
        'contact' if i == 1 else 'company', 'syn-fictional-object-' + str(i),
        'syn-fictional-purpose', 'syn-fictional-classification', 'syn-fictional-visibility',
        ('syn-fictional-status-a', 'syn-fictional-status-b'),
        ('syn-fictional-association-a', 'syn-fictional-association-b'),
        ('syn-fictional-merge-target',)) for i in (1, 2))
    claim = SubjectClaims(subject, 'syn-fictional-external', 'syn-fictional-provider', tenant, 1, ('data_reader',))
    evidence = IdentityEvidence('syn-fictional-evidence', 'syn-fictional-challenge',
        'syn-fictional-provider', 'syn-fictional-issuer', 'syn-fictional-audience',
        claim.external_subject_reference, tenant, 'syn-fictional-context', 'syn-mfa',
        ('syn-factor-possession', 'syn-factor-knowledge'), start, start, start + timedelta(minutes=5))
    identity = SyntheticSessionAuthority(DeterministicIdentityProvider((evidence,)), (claim,),
        SessionPolicy(evidence.provider_reference, evidence.issuer_reference, evidence.audience_reference), lambda: clock[0])
    identity.issue('syn-fictional-contract-session', subject, evidence.reference, evidence.challenge_reference)
    guard = ContractGuard(identity, {session: SessionBinding('syn-fictional-contract-session', subject, tenant, 1, 1)},
        {('registry.read', m.mapping_reference): ScopeRequirement(('data_reader',)) for m in ms})
    principal = Principal(subject, tenant, 'mission-control-registry', ('data_reader',),
        start - timedelta(seconds=1), start + timedelta(hours=1), False)
    authority = SyntheticAuthority({session: SyntheticSession(principal, individual=True, mfa_verified=True, mfa_at=start)},
        {tenant: SyntheticPolicy(tenant, 1, tuple(SyntheticGrant('data_reader', 'registry.read', m.mapping_reference, 'allow') for m in ms),
            start - timedelta(seconds=1), start + timedelta(hours=1))}, guard)
    observations = []
    for i, m in enumerate(ms, 1):
        o = Observation('syn-fictional-observation-' + str(i), m.mapping_reference, m.portal_reference,
            m.object_type, m.object_reference, 1, start.isoformat(), start.isoformat(), start.isoformat(),
            'active', ('syn-fictional-status-a',), ('syn-fictional-association-a',))
        observations += [o,
            replace(o, observation_reference=o.observation_reference + '-next', source_version=2,
                    association_references=('syn-fictional-association-b',)),
            replace(o, observation_reference=o.observation_reference + '-deleted', source_version=3,
                    state='deleted', status_references=(), association_references=(), tombstone_reference='syn-fictional-tombstone'),
            replace(o, observation_reference=o.observation_reference + '-merged', source_version=3,
                    state='merged', status_references=(), association_references=(), tombstone_reference='syn-fictional-tombstone', merge_target='syn-fictional-merge-target'),
            replace(o, observation_reference=o.observation_reference + '-unavailable', source_version=2,
                    state='unavailable', status_references=(), association_references=()),
            replace(o, observation_reference=o.observation_reference + '-unknown', source_version=2,
                    state='unknown', status_references=(), association_references=())]
    engine = MockProjection(authority, ms, tuple(observations), lambda: clock[0], journal)
    return engine, identity, authority, clock, ms, tuple(observations), session


def main():
    if sys.argv[1:] != ['--synthetic-development']:
        print('Explicit --synthetic-development required.', file=sys.stderr)
        return 2
    from mission_control.hubspot_projection import ProjectionDenied
    from mission_control.connection_contracts import CONNECTORS
    engine, identity, _, _, ms, obs, session = fixture()
    def call(index=0, request='syn-fictional-request', **kwargs):
        m = ms[index]
        return engine.operate(session, 1, m.tenant_reference, m.mapping_reference, m.portal_reference,
            request, 'syn-fictional-correlation', **kwargs)
    def denied(fn):
        try:
            fn()
        except ProjectionDenied:
            return
        raise AssertionError('Expected denial')
    try:
        first = call(fixture=obs[0].observation_reference, expected_revision=0)
        assert first.state == 'active'
        assert call(fixture=obs[0].observation_reference, expected_revision=0) == first
        denied(lambda: call(fixture=obs[1].observation_reference, expected_revision=0))
        call(request='syn-fictional-next', fixture=obs[1].observation_reference, expected_revision=1)
        denied(lambda: call(request='syn-fictional-old', fixture=obs[0].observation_reference, expected_revision=2))
        denied(lambda: engine.operate(session, 1, 'syn-fictional-other-tenant', ms[0].mapping_reference,
            ms[0].portal_reference, 'syn-fictional-cross', 'syn-fictional-correlation'))
        assert call(request='syn-fictional-delete', fixture=obs[2].observation_reference, expected_revision=2).state == 'deleted'
        call(1, 'syn-fictional-company', fixture=obs[6].observation_reference, expected_revision=0)
        assert call(1, 'syn-fictional-merge', fixture=obs[9].observation_reference, expected_revision=1).state == 'merged'
        assert len(CONNECTORS) == 7 and all(c.enabled is False and c.state == 'unresolved' for c in CONNECTORS)
    finally:
        engine.close()
        identity.close()
    assert not engine._current and not engine._requests and not engine._fixtures and not identity.snapshot()
    print('PASS: authorized fictional projection, duplicate retry, stale/conflicting denial, cross-tenant denial, tombstone, merge, seven disabled connectors and process-local cleanup. No network, listener, database or credential.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
