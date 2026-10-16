"""Generic synthetic Phase 1C fixtures; no organizational assignments."""
from dataclasses import replace

from mission_control.department_routing import CENTRAL_VIEWS, Department, Intake, Rule, derive_packets, seal
from mission_control.synthetic_identity import ROLE_ACTIONS, SyntheticGrant
from tests.synthetic_postgres_support import authority_fixture, session_ref

TENANT = 'syn-tenant-1'


def contracts(tenant=TENANT):
    departments = tuple(seal(Department(tenant, 'syn-department-'+letter, 1, 'syn-name-'+letter,
        ('syn-alias-'+letter,), 'syn-executive-'+letter, ('syn-team-'+letter,), 'syn-mandate',
        ('syn-classification-original',), ('syn-classification-derived',), 'syn-escalation',
        'syn-view-command', 'syn-evidence-department-'+letter)) for letter in ('alpha','beta'))
    rule = seal(Rule(tenant,'syn-rule-1',1,'syn-classification-original',('syn-fact-ready',),
        tuple((d.department_id,d.revision,d.content_digest,d.executive_reference) for d in departments),
        CENTRAL_VIEWS,'syn-department-packet-v1','syn-action-review',('syn-fact-escalate',),
        'syn-policy',1,'syn-evidence-rule'))
    intake = seal(Intake(tenant,'syn-intake-1','syn-classification-original',('syn-fact-ready',),'syn-source-1'))
    return departments,rule,intake


def reference_rows(tenant=TENANT):
    rows = [('executive','syn-executive-'+letter,'syn-data_reader-'+tenant) for letter in ('alpha','beta')]
    rows += [('team','syn-team-'+letter,'syn-executive-'+letter) for letter in ('alpha','beta')]
    for kind,values in {
        'mandate':('syn-mandate',), 'classification':('syn-classification-original','syn-classification-derived'),
        'escalation':('syn-escalation',), 'visibility':CENTRAL_VIEWS,
        'policy':('syn-policy',), 'action':('syn-action-review',),
        'fact':('syn-fact-ready','syn-fact-escalate'), 'dependency':('syn-dependency-1',),
        'outcome':('syn-outcome-1','syn-outcome-2'), 'handoff':('syn-handoff-1',),
    }.items():
        rows += [(kind,value,None) for value in values]
    return rows


def routing_authority():
    authority,custody = authority_fixture()
    for tenant,policy in list(authority.policies.items()):
        departments,rule,intake = contracts(tenant)
        packets = derive_packets(intake,rule,{d.department_id:d for d in departments},'syn-routing-key')
        resources = {d.department_id for d in departments} | {p.packet_id for p in packets} | {rule.rule_id,intake.event_id}
        resources |= {reference for _,reference,_ in reference_rows(tenant)}
        grants = list(policy.grants)
        for role,actions in ROLE_ACTIONS.items():
            for action in actions:
                if action.startswith(('registry.department.','registry.rule.','packet.routing.','packet.route_simulate',
                                      'packet.view.','packet.distribute','journey.routing.','approval.routing.','policy.reference.')):
                    grants += [SyntheticGrant(role,action,resource,'allow') for resource in sorted(resources)]
        authority.policies[tenant] = replace(policy,grants=tuple(grants))
    return authority,custody
