"""Inactive synthetic lifecycle on existing routing transactions. No engine wiring."""
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json

from .department_routing import Intake, ref
from .podcast_pilot import (GuestEvent, GuestJourney, STAGES, classify_event,
                            decode_pilot, derive_stage_packets)
from .registry_authorization import current_interval, positive_revision
from .registry_persistence import ConflictError
from .routing_postgres import RoutingStore, RoutingTransaction, apply_routing_migration
from .synthetic_identity import SyntheticAuthority, SyntheticEvidenceCustody, canonical, fingerprint
from .synthetic_postgres import ROOT, _query, transactional_operation

SQL_PATH=ROOT/'migrations/postgresql/0003_synthetic_podcast_pilot.sql'
MIGRATION_ID='syn-postgresql-0003'
PILOT_COLUMNS={
 'pilot_journeys':'reference intake_reference intake_kind intake_revision original_classification payload content_digest state actor_reference policy_revision created_at',
 'pilot_proposals':'journey_reference event_reference revision previous_revision content_digest payload state actor_reference policy_revision created_at',
 'pilot_proposal_heads':'journey_reference event_reference revision',
 'pilot_evidence':'reference journey_reference event_reference proposal_revision event_digest grantor_reference policy_revision valid_from expires_at proof',
 'pilot_revocations':'reference actor_reference created_at',
 'pilot_events':'journey_reference sequence event_reference proposal_revision event_digest previous_sequence previous_digest content_digest original_classification stage_index disposition payload state',
 'pilot_heads':'journey_reference version completed_stage last_event_reference progress state',
 'pilot_decisions':'journey_reference event_reference reference classification rule_reference rule_revision rule_digest rule_kind approval_reference proposal_revision event_digest disposition reason_reference content_digest payload state',
 'pilot_packet_links':'journey_reference event_reference packet_reference packet_revision packet_kind state',
 'pilot_deliverables':'journey_reference event_reference kind reference packet_reference state',
}


def apply_pilot_migration(factory,authority=None,session=None,tenant=None,revision=1):
    if not isinstance(authority,SyntheticAuthority): raise PermissionError('Synthetic migration authority required')
    authority.authorize(session,tenant,revision,'schema.migrate','syn-schema')
    apply_routing_migration(factory,authority,session,tenant,revision)
    connection=factory()
    try:
        _query(connection,'BEGIN')
        _query(connection,'SELECT pg_advisory_xact_lock(%s)',(731843291,))
        checksum=fingerprint(SQL_PATH.read_text())
        rows,_=_query(connection,'SELECT checksum FROM mc_syn.schema_migrations WHERE tenant_reference=%s AND migration_id=%s',('syn-system',MIGRATION_ID))
        if rows:
            if rows[0]['checksum']!=checksum: raise ConflictError('Pilot migration checksum mismatch')
            connection.rollback();return 'already_applied'
        with connection.cursor() as cursor: cursor.execute(SQL_PATH.read_text())
        _query(connection,'INSERT INTO mc_syn.schema_migrations (tenant_reference,migration_id,checksum,applied_at,dataset) VALUES (%s,%s,%s,%s,%s)',
               ('syn-system',MIGRATION_ID,checksum,datetime.now(timezone.utc),'synthetic'))
        authority.authorize(session,tenant,revision,'schema.migrate','syn-schema')
        connection.commit();return 'applied'
    except BaseException:
        connection.rollback();raise
    finally: connection.close()


class PilotStore(RoutingStore):
    def transaction_type(self): return PilotTransaction


class PilotTransaction(RoutingTransaction):
    def __init__(self,*args):
        super().__init__(*args)
        self.pilot_checks=[]

    def recheck(self):
        requested=self.commit_requested;self.commit_requested=False
        try:
            _,policy=self.authority.resolve(self.session,self.tenant,self.revision)
            rows=self._select('policy_revisions',policy_revision=self.revision)
            if not rows or rows[0]['content_digest']!=fingerprint(asdict(policy)):
                raise PermissionError('Persisted pilot policy changed before commit')
            for event in self.pilot_checks: self._verify_pilot_approval(event,remember=False)
        finally: self.commit_requested=requested
        super().recheck()

    def _pr(self,table,**keys):
        self._open()
        if table not in PILOT_COLUMNS or not set(keys)<=set(PILOT_COLUMNS[table].split()): raise ValueError('Unknown pilot selector')
        clauses=['tenant_reference=%s']+[key+'=%s' for key in keys]
        return _query(self.connection,'SELECT * FROM mc_syn.'+table+' WHERE '+' AND '.join(clauses),(self.tenant,*keys.values()))[0]

    def _pp(self,table,**values):
        self._open()
        if table not in PILOT_COLUMNS or set(values)!=set(PILOT_COLUMNS[table].split()): raise ValueError('Invalid pilot row')
        row={'tenant_reference':self.tenant,**values,'dataset':'synthetic'}
        markers=['%s::jsonb' if key in ('payload','proof') else '%s' for key in row]
        parameters=[json.dumps(canonical(value),allow_nan=False) if key in ('payload','proof') else value for key,value in row.items()]
        _query(self.connection,'INSERT INTO mc_syn.'+table+' ('+','.join(row)+') VALUES ('+','.join(markers)+')',tuple(parameters))

    def _journey(self,reference):
        ref(reference)
        rows=self._pr('pilot_journeys',reference=reference)
        if not rows: raise PermissionError('Synthetic journey unavailable')
        row=rows[0];journey=decode_pilot('journey',row['payload'])
        if (journey.tenant_reference,journey.journey_id,journey.intake_reference,journey.content_digest,journey.original_classification)!=(self.tenant,reference,row['intake_reference'],row['content_digest'],row['original_classification']):
            raise ValueError('Journey integrity mismatch')
        return journey

    def _proposal(self,journey,event,revision,latest=True):
        ref(journey);ref(event);positive_revision(revision)
        rows=self._pr('pilot_proposals',journey_reference=journey,event_reference=event,revision=revision)
        heads=self._pr('pilot_proposal_heads',journey_reference=journey,event_reference=event)
        if not rows or not heads or (latest and heads[0]['revision']!=revision): raise PermissionError('Missing or stale event proposal')
        record=decode_pilot('event',rows[0]['payload'])
        if (record.tenant_reference,record.journey_reference,record.event_id,record.revision,record.content_digest)!=(self.tenant,journey,event,revision,rows[0]['content_digest']):
            raise ValueError('Event proposal integrity mismatch')
        return record

    def _pilot_receipt(self,operation,key,digest):
        ref(key)
        rows=self._rows('routing_receipts',operation=operation,key=key)
        if rows and rows[0]['payload_digest']!=digest: raise ConflictError('Pilot idempotency payload collision')
        return rows[0]['result'] if rows else None

    def _pilot_receipt_save(self,operation,key,digest,result):
        self._put('routing_receipts',operation=operation,key=key,payload_digest=digest,result=result)

    @transactional_operation
    def start_journey(self,journey,intake,key):
        if type(journey) is not GuestJourney or type(intake) is not Intake: raise ValueError('Synthetic entry contracts required')
        journey.validate();intake.validate()
        session,_=self._auth('journey.pilot.start',journey.journey_id)
        if (journey.tenant_reference,intake.tenant_reference,journey.intake_reference,journey.original_classification)!=(self.tenant,self.tenant,intake.event_id,intake.original_classification):
            raise PermissionError('Cross-tenant or original entry mismatch')
        self._reference('classification',journey.original_classification)
        digest=fingerprint([asdict(journey),asdict(intake)])
        if self._pilot_receipt('syn-pilot-start',key,digest) is not None: return 'duplicate'
        if self._rows('routing_records',kind='intake',reference=intake.event_id): raise ConflictError('Information already entered')
        self._put('routing_records',kind='intake',reference=intake.event_id,revision=1,previous_revision=None,content_digest=intake.content_digest,
                  payload=asdict(intake),state='inactive',actor_reference=session.principal.subject_reference,policy_revision=self.revision,created_at=datetime.now(timezone.utc))
        self._cas_head('intake',intake.event_id,0,1)
        self._pp('pilot_journeys',reference=journey.journey_id,intake_reference=intake.event_id,intake_kind='intake',intake_revision=1,
                 original_classification=journey.original_classification,payload=asdict(journey),content_digest=journey.content_digest,state='inactive',
                 actor_reference=session.principal.subject_reference,policy_revision=self.revision,created_at=datetime.now(timezone.utc))
        self._pp('pilot_heads',journey_reference=journey.journey_id,version=0,completed_stage=0,last_event_reference=None,progress='pending',state='inactive')
        self._journal(intake,'syn-pilot-entry',journey.journey_id,1)
        self._pilot_receipt_save('syn-pilot-start',key,digest,[journey.journey_id])
        self._audit('journey.pilot.start',journey.journey_id,session)
        return 'appended'

    @transactional_operation
    def propose_event(self,event,expected,key):
        if type(event) is not GuestEvent: raise ValueError('Synthetic event required')
        event.validate()
        session,_=self._auth('journey.pilot.propose',event.journey_reference)
        journey=self._journey(event.journey_reference)
        if event.tenant_reference!=self.tenant or type(expected) is not int or expected<0 or event.revision!=expected+1:
            raise ConflictError('Event tenant or revision mismatch')
        self._auth('registry.rule.read',event.rule_reference)
        rule=self._get('rule',event.rule_reference,event.rule_revision,latest=True)
        if rule.content_digest!=event.rule_digest or rule.classification!=classify_event(event): raise PermissionError('Event rule/classification mismatch')
        self._rule_refs(rule)
        for kind,values in (('fact',event.evidence_references),('outcome',event.outcome_references),('handoff',event.handoff_references)):
            for value in values: self._reference(kind,value)
        if self._pilot_receipt('syn-pilot-propose',key,event.content_digest) is not None: return 'duplicate'
        if self._pr('pilot_events',journey_reference=journey.journey_id,event_reference=event.event_id): raise ConflictError('Processed event cannot be revised')
        self._pp('pilot_proposals',journey_reference=event.journey_reference,event_reference=event.event_id,revision=event.revision,
                 previous_revision=expected or None,content_digest=event.content_digest,payload=asdict(event),state='inactive',
                 actor_reference=session.principal.subject_reference,policy_revision=self.revision,created_at=datetime.now(timezone.utc))
        if expected==0:
            _,count=_query(self.connection,'INSERT INTO mc_syn.pilot_proposal_heads (tenant_reference,journey_reference,event_reference,revision,dataset) VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(self.tenant,event.journey_reference,event.event_id,event.revision,'synthetic'))
        else:
            _,count=_query(self.connection,'UPDATE mc_syn.pilot_proposal_heads SET revision=%s WHERE tenant_reference=%s AND journey_reference=%s AND event_reference=%s AND revision=%s',(event.revision,self.tenant,event.journey_reference,event.event_id,expected))
        if count!=1: raise ConflictError('Proposal compare-and-swap conflict')
        self._pilot_receipt_save('syn-pilot-propose',key,event.content_digest,[event.journey_reference,event.event_id,event.revision])
        self._audit('journey.pilot.propose',event.event_id,session)
        return 'appended'

    @transactional_operation
    def issue_event_approval(self,journey_reference,event_reference,revision,reference,lifetime=timedelta(minutes=5)):
        ref(reference)
        session,_=self._auth('approval.pilot.issue',journey_reference)
        event=self._proposal(journey_reference,event_reference,revision)
        author=self._pr('pilot_proposals',journey_reference=journey_reference,event_reference=event_reference,revision=revision)[0]['actor_reference']
        if event.approval_reference!=reference or author==session.principal.subject_reference: raise PermissionError('Self approval or unbound event evidence')
        if not isinstance(lifetime,timedelta) or not timedelta(0)<lifetime<=timedelta(minutes=5): raise ValueError('Invalid synthetic evidence lifetime')
        if not isinstance(self.custody,SyntheticEvidenceCustody): raise PermissionError('Synthetic custody unavailable')
        now=datetime.now(timezone.utc)
        signed=dict(tenant_reference=self.tenant,reference=reference,journey_reference=journey_reference,event_reference=event_reference,
                    proposal_revision=revision,event_digest=event.content_digest,grantor_reference=session.principal.subject_reference,
                    policy_revision=self.revision,valid_from=now,expires_at=min(now+lifetime,session.principal.expires_at))
        self._pp('pilot_evidence',**{key:value for key,value in signed.items() if key!='tenant_reference'},proof=self.custody.seal(signed))
        self._audit('approval.pilot.issue',event_reference,session)

    def _verify_pilot_approval(self,event,remember=True):
        if self._proposal(event.journey_reference,event.event_id,event.revision)!=event: raise PermissionError('Approval target changed')
        rows=self._pr('pilot_evidence',reference=event.approval_reference) if event.approval_reference else []
        if not rows or self._pr('pilot_revocations',reference=event.approval_reference): raise PermissionError('Missing or revoked event evidence')
        row=rows[0]
        if (row['journey_reference'],row['event_reference'],row['proposal_revision'],row['event_digest'],row['policy_revision'])!=(event.journey_reference,event.event_id,event.revision,event.content_digest,self.revision):
            raise PermissionError('Event evidence revision mismatch')
        signed={key:value for key,value in row.items() if key not in ('proof','dataset')}
        if not isinstance(self.custody,SyntheticEvidenceCustody) or not self.custody.verify(signed,row['proof']) or not current_interval(row['valid_from'],row['expires_at']):
            raise PermissionError('Expired or unverifiable event evidence')
        author=self._pr('pilot_proposals',journey_reference=event.journey_reference,event_reference=event.event_id,revision=event.revision)[0]['actor_reference']
        valid=False
        for reference,session in self.authority.sessions.items():
            if session.principal.subject_reference!=row['grantor_reference'] or session.principal.tenant_reference!=self.tenant or row['grantor_reference']==author: continue
            try:
                self.authority.authorize(reference,self.tenant,self.revision,'approval.pilot.issue',event.journey_reference)
                valid=True;break
            except PermissionError: continue
        if not valid: raise PermissionError('Issuing authority unavailable')
        if remember and event not in self.pilot_checks: self.pilot_checks.append(event)

    @transactional_operation
    def revoke_event_approval(self,reference):
        rows=self._pr('pilot_evidence',reference=reference)
        if not rows: raise PermissionError('Event evidence unavailable')
        session,_=self._auth('approval.pilot.revoke',rows[0]['journey_reference'])
        if self._pr('pilot_revocations',reference=reference): return 'duplicate'
        self._pp('pilot_revocations',reference=reference,actor_reference=session.principal.subject_reference,created_at=datetime.now(timezone.utc))
        self._audit('approval.pilot.revoke',rows[0]['event_reference'],session)
        return 'revoked'

    @transactional_operation
    def advance_event(self,journey_reference,event_reference,revision,expected_version,key):
        session,_=self._auth('journey.pilot.advance',journey_reference)
        journey=self._journey(journey_reference)
        event=self._proposal(journey_reference,event_reference,revision)
        self._verify_pilot_approval(event)
        self._auth('registry.rule.read',event.rule_reference)
        rule=self._get('rule',event.rule_reference,event.rule_revision,latest=True)
        self._verify_evidence('rule',rule)
        departments=self._rule_refs(rule,approved=True)
        intake=self._get('intake',journey.intake_reference,1)
        packets=derive_stage_packets(journey,intake,event,rule,departments,key)
        for packet in packets:
            self._auth('packet.routing.append',packet.packet_id)
            self._auth('packet.routing.read',packet.packet_id)
        if type(expected_version) is not int or expected_version<0: raise ValueError('Exact journey version required')
        request_digest=fingerprint([event.content_digest,expected_version])
        receipt=self._pilot_receipt('syn-pilot-advance',key,request_digest)
        if receipt is not None: return receipt
        heads=self._pr('pilot_heads',journey_reference=journey_reference)
        if not heads or heads[0]['version']!=expected_version: raise ConflictError('Stale pilot head')
        head=heads[0];stage_index=STAGES.index(event.stage_reference)+1
        if head['completed_stage']==16 or stage_index!=head['completed_stage']+1 or event.previous_event_reference!=head['last_event_reference']:
            raise ValueError('Invalid synthetic lifecycle transition')
        if self._pr('pilot_events',journey_reference=journey_reference,event_reference=event_reference): raise ConflictError('Duplicate lifecycle event')
        accepted={row['event_reference'] for row in self._pr('pilot_events',journey_reference=journey_reference) if row['disposition']=='accepted'}
        missing=tuple(sorted(set(event.dependency_references)-accepted))
        disposition='blocked' if missing else 'accepted'
        sequence=head['version']+1
        previous=self._pr('pilot_events',journey_reference=journey_reference,sequence=head['version']) if head['version'] else []
        previous_digest=previous[0]['content_digest'] if previous else None
        packet_references=[packet.packet_id for packet in packets] if not missing else []
        decision_reference='syn-decision-'+fingerprint([journey_reference,event_reference])
        result=dict(journey_reference=journey_reference,event_reference=event_reference,version=sequence,
                    status=disposition,packet_references=packet_references,state='inactive')
        decision=dict(reference=decision_reference,journey_reference=journey_reference,event_reference=event_reference,
                      classification=classify_event(event),rule_reference=event.rule_reference,rule_revision=event.rule_revision,
                      rule_digest=event.rule_digest,approval_reference=event.approval_reference,proposal_revision=event.revision,
                      event_digest=event.content_digest,disposition=disposition,reason_reference=('syn-missing-dependencies' if missing else 'syn-validated'),
                      missing_dependencies=missing,packet_references=packet_references,state='inactive')
        payload=dict(tenant_reference=self.tenant,journey_reference=journey_reference,event_reference=event_reference,
                     proposal_revision=event.revision,event_digest=event.content_digest,sequence=sequence,previous_digest=previous_digest,
                     original_classification=journey.original_classification,stage_index=stage_index,disposition=disposition,
                     decision_reference=decision_reference,actor_reference=session.principal.subject_reference,policy_revision=self.revision,result=result)
        self._pp('pilot_events',journey_reference=journey_reference,sequence=sequence,event_reference=event_reference,proposal_revision=event.revision,
                 event_digest=event.content_digest,previous_sequence=head['version'] or None,previous_digest=previous_digest,
                 content_digest=fingerprint(payload),original_classification=journey.original_classification,stage_index=stage_index,
                 disposition=disposition,payload=payload,state='inactive')
        fields={name:decision[name] for name in ('journey_reference','event_reference','reference','classification','rule_reference','rule_revision',
                                                'rule_digest','approval_reference','proposal_revision','event_digest','disposition','reason_reference','state')}
        self._pp('pilot_decisions',**fields,rule_kind='rule',payload=decision,content_digest=fingerprint(decision))
        self._journal(intake,'syn-pilot-classified',event_reference,event.revision,{'decision_reference':decision_reference,'status':disposition})
        if not missing:
            for packet in packets:
                self._record('packet',packet,0,'packet.routing.append')
                self._packet_links(packet)
                self._pp('pilot_packet_links',journey_reference=journey_reference,event_reference=event_reference,packet_reference=packet.packet_id,
                         packet_revision=1,packet_kind='packet',state='inactive')
                for kind,values in (('outcome',event.outcome_references),('handoff',event.handoff_references)):
                    for value in values:
                        self._pp('pilot_deliverables',journey_reference=journey_reference,event_reference=event_reference,kind=kind,reference=value,
                                 packet_reference=packet.packet_id,state='inactive')
                self._journal(intake,'syn-pilot-packet',packet.packet_id,1,{'event_reference':event_reference})
        progress='blocked' if missing else ('pending' if stage_index<16 else event.terminal_reference.removeprefix('syn-'))
        _,count=_query(self.connection,'UPDATE mc_syn.pilot_heads SET version=%s,completed_stage=%s,last_event_reference=%s,progress=%s WHERE tenant_reference=%s AND journey_reference=%s AND version=%s',
                       (sequence,head['completed_stage'] if missing else stage_index,head['last_event_reference'] if missing else event_reference,progress,self.tenant,journey_reference,expected_version))
        if count!=1: raise ConflictError('Concurrent pilot event conflict')
        self._pilot_receipt_save('syn-pilot-advance',key,request_digest,result)
        self._audit('journey.pilot.advance',event_reference,session)
        return result

    @transactional_operation
    def read_pilot(self,journey_reference):
        self._auth('journey.pilot.read',journey_reference)
        journey=self._journey(journey_reference)
        # Detailed journey access is separate from minimized executive/oversight views.
        return dict(journey=asdict(journey),head=self._pr('pilot_heads',journey_reference=journey_reference)[0],
                    events=sorted(self._pr('pilot_events',journey_reference=journey_reference),key=lambda row:row['sequence']))
