"""Synthetic fixture identities/records only. Never production authentication."""
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from mission_control.registry_authorization import Principal
from mission_control.synthetic_identity import (ROLE_ACTIONS, SyntheticAuthority,
    SyntheticEvidenceCustody, SyntheticGrant, SyntheticPolicy, SyntheticSession, canonical, fingerprint)
from mission_control.synthetic_postgres import ENTITIES
from tests.test_registry_foundation import fixtures


def authority_fixture():
    now = datetime.now(timezone.utc)
    sessions,policies = {},{}
    resources = {'registry':'syn-registry-1','packet':'syn-packet-1','journey':'syn-journey-1',
                 'policy':'syn-policy','approval':'syn-registry-1','audit':'syn-audit',
                 'backup':'syn-backup','schema':'syn-schema','signing':'syn-signing-key','encryption':'syn-encryption-key'}
    for tenant in ('syn-tenant-1','syn-tenant-2'):
        grants=[]
        for role,actions in ROLE_ACTIONS.items():
            service = role == 'service_writer'
            principal = Principal('syn-'+role+'-'+tenant,tenant,'mission-control-registry',(role,),
                                  now-timedelta(seconds=1),now+timedelta(minutes=10),False)
            session = SyntheticSession(principal, 'service' if service else 'human',True,not service,None if service else now-timedelta(seconds=1))
            sessions['syn-session-'+role+'-'+tenant] = session
            grants += [SyntheticGrant(role,action,resources[action.split('.')[0]],'allow') for action in actions]
        policies[tenant] = SyntheticPolicy(tenant,1,tuple(grants),now-timedelta(seconds=1),now+timedelta(minutes=10))
    authority = SyntheticAuthority(sessions,policies)
    custody = SyntheticEvidenceCustody(authority,session_ref('signing_custodian'),'syn-tenant-1',1)
    return authority,custody


def session_ref(role,tenant='syn-tenant-1'):
    return 'syn-session-'+role+'-'+tenant


def snapshot_tables(authority):
    registry,packet,event = fixtures()
    tenant = registry.tenant_reference
    policy = authority.policies[tenant]
    now = datetime.now(timezone.utc)
    tables = {name:[] for name in ENTITIES}
    def row(table,**values):
        tables[table].append(canonical({'tenant_reference':tenant,**values,'dataset':'synthetic'}))
    for session in authority.sessions.values():
        p=session.principal
        if p.tenant_reference==tenant:
            row('subjects',subject_reference=p.subject_reference,issuer_reference='syn-fixture',audience=p.audience,status='synthetic')
    row('policy_revisions',policy_revision=1,content_digest=fingerprint(asdict(policy)),rules_document=asdict(policy),valid_from=policy.valid_from,expires_at=policy.expires_at)
    actor=authority.sessions[session_ref('data_writer')].principal.subject_reference
    row('registry_revisions',record_reference=registry.record.record_id,revision=1,previous_revision=0,state='draft',
        payload=asdict(registry),content_digest=registry.content_digest,created_at=now,actor_reference=actor,policy_revision=1,schema_revision=1)
    row('registry_heads',record_reference=registry.record.record_id,revision=1)
    row('packet_revisions',packet_reference=packet.packet.packet_id,revision=1,previous_revision=0,registry_reference=registry.record.record_id,
        registry_revision=1,state='inactive',payload=asdict(packet),content_digest=fingerprint(asdict(packet)),created_at=now,actor_reference=actor,policy_revision=1,schema_revision=1)
    row('packet_heads',packet_reference=packet.packet.packet_id,revision=1)
    row('journey_events',event_reference=event.event.event_id,journey_reference=event.event.journey_reference,sequence=1,
        packet_reference=packet.packet.packet_id,packet_revision=1,previous_digest=None,content_digest=event.content_digest,payload=asdict(event),
        active=False,created_at=now,actor_reference=actor,policy_revision=1,schema_revision=1)
    row('journey_heads',journey_reference=event.event.journey_reference,sequence=1)
    for operation,key,result,item,revision in (
            ('registry.append_draft','syn-registry-key',registry.record.record_id,registry,1),
            ('packet.append_inactive','syn-packet-key',packet.packet.packet_id,packet,1),
            ('journey.append_inactive','syn-event-key',event.event.journey_reference,event,1)):
        row('idempotency_receipts',operation_reference=operation,idempotency_key=key,payload_digest=fingerprint(asdict(item)),result_reference=result,result_revision=revision,created_at=now)
    return tables
