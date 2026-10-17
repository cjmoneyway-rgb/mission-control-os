"""Opaque fixtures only; no guest details, contacts or real assignments."""
from dataclasses import replace

from mission_control.department_routing import CENTRAL_VIEWS, Intake, Rule, seal
from mission_control.podcast_pilot import (CLASSIFICATIONS, ENTRY_CLASSIFICATION, STAGES,
                                          GuestEvent, GuestJourney, derive_stage_packets)
from mission_control.synthetic_identity import ROLE_ACTIONS, SyntheticGrant
from tests.routing_support import contracts, reference_rows
from tests.synthetic_postgres_support import authority_fixture

TENANT='syn-tenant-1'
JOURNEY='syn-pilot-journey-1'


def pilot_contracts(tenant=TENANT):
    original,_,_=contracts(tenant)
    departments=tuple(seal(replace(department,information_received=(ENTRY_CLASSIFICATION,*CLASSIFICATIONS),
                                   approval_reference='syn-pilot-dept-evidence-'+letter))
                      for department,letter in zip(original,('alpha','beta')))
    journey=seal(GuestJourney(tenant,JOURNEY,'syn-guest-1','syn-pilot-intake-1'))
    intake=seal(Intake(tenant,journey.intake_reference,ENTRY_CLASSIFICATION,(),'syn-source-1'))
    rules=[];events=[]
    for index,stage in enumerate(STAGES,1):
        token=str(index).zfill(2)
        targets=departments if index in (9,10,15) else (departments[(index-1)%2],)
        rule=seal(Rule(tenant,'syn-pilot-rule-'+token,1,CLASSIFICATIONS[index-1],('syn-evidence-'+token,),
                       tuple((d.department_id,1,d.content_digest,d.executive_reference) for d in targets),CENTRAL_VIEWS,
                       'syn-department-packet-v1','syn-action-'+token,(),'syn-policy',1,'syn-pilot-rule-evidence-'+token))
        prior='syn-pilot-event-'+str(index-1).zfill(2) if index>1 else None
        event=seal(GuestEvent(tenant,JOURNEY,'syn-pilot-event-'+token,1,stage,CLASSIFICATIONS[index-1],prior,
                              (prior,) if prior else (),('syn-evidence-'+token,),('syn-pilot-outcome-'+token,),
                              ('syn-pilot-handoff-'+token,),rule.rule_id,1,rule.content_digest,'syn-pilot-approval-'+token,
                              'syn-completed' if index==16 else None))
        rules.append(rule);events.append(event)
    return journey,intake,departments,tuple(rules),tuple(events)


def pilot_references(tenant=TENANT):
    rows=[(kind,reference,'syn-reader-beta-'+tenant if kind=='executive' and reference=='syn-executive-beta' else parent)
          for kind,reference,parent in reference_rows(tenant)]
    rows += [('classification',value,None) for value in (ENTRY_CLASSIFICATION,*CLASSIFICATIONS)]
    for index in range(1,17):
        token=str(index).zfill(2)
        rows += [('fact','syn-evidence-'+token,None),('action','syn-action-'+token,None),
                 ('outcome','syn-pilot-outcome-'+token,None),('handoff','syn-pilot-handoff-'+token,None)]
    return rows


def pilot_authority():
    authority,custody=authority_fixture()
    for tenant,policy in list(authority.policies.items()):
        journey,intake,departments,rules,events=pilot_contracts(tenant)
        original=authority.sessions['syn-session-data_reader-'+tenant]
        authority.sessions['syn-session-reader-beta-'+tenant]=replace(original,principal=replace(original.principal,subject_reference='syn-reader-beta-'+tenant))
        department_ids={d.department_id for d in departments};rule_ids={rule.rule_id for rule in rules}
        packet_ids=set()
        for event,rule in zip(events,rules):
            packet_ids.update(packet.packet_id for packet in derive_stage_packets(journey,intake,event,rule,
                              {d.department_id:d for d in departments},'syn-stage-key'))
        resources={
            'registry.department.read':department_ids,'registry.department.append':department_ids,
            'registry.rule.read':rule_ids,'registry.rule.append':rule_ids,
            'packet.routing.append':packet_ids,'packet.routing.read':packet_ids,
            'journey.routing.read':{intake.event_id},
            'policy.reference.append':{reference for _,reference,_ in pilot_references(tenant)},
        }
        for action in ('journey.pilot.start','journey.pilot.propose','journey.pilot.advance','journey.pilot.read',
                       'approval.pilot.issue','approval.pilot.revoke'): resources[action]={JOURNEY}
        for action in ('approval.routing.issue','approval.routing.verify','approval.routing.revoke'):
            resources[action]=department_ids|rule_ids
        grants=list(policy.grants)
        for role,actions in ROLE_ACTIONS.items():
            for action in actions:
                grants.extend(SyntheticGrant(role,action,resource,'allow') for resource in sorted(resources.get(action,())))
        alpha='syn-data_reader-'+tenant
        for audience in ('command','control','governance'):
            grants.append(SyntheticGrant('data_reader','packet.view.'+audience,'syn-view-'+audience,'allow',alpha))
        for department,subject in zip(departments,(alpha,'syn-reader-beta-'+tenant)):
            for action,resource in (('packet.view.executive',department.executive_reference),('packet.distribute',department.executive_reference),
                                    *(('packet.view.team',team) for team in department.team_references)):
                grants.append(SyntheticGrant('data_reader',action,resource,'allow',subject))
        # A separately identified retry of a blocked first-stage attempt, with exact grants.
        retry=seal(replace(events[0],event_id='syn-pilot-retry-01',approval_reference='syn-pilot-retry-approval'))
        for packet in derive_stage_packets(journey,intake,retry,rules[0],{d.department_id:d for d in departments},'syn-retry-key'):
            for role in ('data_writer','service_writer'):
                for action in ('packet.routing.append','packet.routing.read'):
                    grants.append(SyntheticGrant(role,action,packet.packet_id,'allow'))
        authority.policies[tenant]=replace(policy,grants=tuple(grants))
    return authority,custody
