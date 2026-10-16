"""Offline semantic checks for the complete synthetic graph, beyond SQL keys."""
from dataclasses import asdict
from datetime import datetime

from .department_routing import decode, derive_packets
from .podcast_pilot import STAGES, classify_event, decode_pilot, derive_stage_packets
from .synthetic_identity import canonical, fingerprint


def require(condition):
    if not condition: raise ValueError('Synthetic archive semantic invariant failed')


def exact_heads(rows,heads,identity,version,head_version=None):
    expected={}
    for row in rows:
        key=tuple(row[column] for column in identity)
        expected[key]=max(expected.get(key,0),row[version])
    actual={tuple(row[column] for column in identity):row[head_version or version] for row in heads}
    require(actual==expected)
    for key,last in expected.items():
        versions=sorted(row[version] for row in rows if tuple(row[column] for column in identity)==key)
        require(versions==list(range(1,last+1)))


def historical_approval(tables,record,kind):
    rows=[row for row in tables['routing_evidence'] if row['reference']==record.approval_reference]
    require(len(rows)==1)
    row=rows[0]
    reference=record.department_id if kind=='department' else record.rule_id
    require((row['kind'],row['record_reference'],row['record_revision'],row['content_digest'])==
            (kind,reference,record.revision,record.content_digest))


def validate_extended_history(payload,custody):
    tables=payload['tables'];tenant=payload['tenant']
    records={};row_records={}
    kinds={'department':('Department','department_id'),'rule':('Rule','rule_id'),'intake':('Intake','event_id'),'packet':('DepartmentPacket','packet_id')}
    refs={(row['kind'],row['reference']):row for row in tables['routing_references']}
    subjects={row['subject_reference'] for row in tables['subjects']}
    for (kind,reference),row in refs.items():
        from .department_routing import ref
        ref(reference)
        require(kind in ('executive','team','escalation','visibility','mandate','classification','fact','action','policy','dependency','outcome','handoff'))
        if kind=='executive': require(row['parent_reference'] in subjects)
        elif kind=='team': require(('executive',row['parent_reference']) in refs)
        else: require(row['parent_reference'] is None)
    for row in tables['routing_records']:
        cls,id_field=kinds[row['kind']]
        record=decode(cls,row['payload'])
        require((record.tenant_reference,getattr(record,id_field),record.revision,record.content_digest)==(tenant,row['reference'],row['revision'],row['content_digest']))
        require(row['previous_revision']==(row['revision']-1 or None) and row['state']=='inactive')
        key=(row['kind'],row['reference'],row['revision']);records[key]=record;row_records[key]=row
    exact_heads(tables['routing_records'],tables['routing_heads'],('kind','reference'),'revision')
    names={row['name']:row for row in tables['routing_names']};expected_names={}
    for key,record in records.items():
        kind,reference,revision=key
        if kind=='department':
            require(('executive',record.executive_reference) in refs)
            for team in record.team_references: require(refs[('team',team)]['parent_reference']==record.executive_reference)
            for typ,values in (('mandate',(record.mandate,)),('classification',record.information_received+record.information_produced),
                               ('escalation',(record.escalation_reference,)),('visibility',(record.visibility_reference,))):
                for value in values: require((typ,value) in refs)
            for name in (record.canonical_name,*record.aliases):
                if name in expected_names: require(expected_names[name][0]==reference)
                expected_names[name]=(reference,min(revision,expected_names.get(name,(reference,revision))[1]))
        elif kind=='rule':
            for reference,version,digest,executive in record.recipients:
                department=records[('department',reference,version)]
                require((department.content_digest,department.executive_reference)==(digest,executive))
            for typ,values in (('classification',(record.classification,)),('action',(record.required_action,)),
                               ('policy',(record.policy_reference,)),('visibility',record.visibility_references),
                               ('fact',record.preconditions+record.escalation_conditions)):
                for value in values: require((typ,value) in refs)
        elif kind=='packet' and revision>1:
            previous=records[('packet',reference,revision-1)] if ('packet',reference,revision-1) in records else decode('DepartmentPacket',next(row['payload'] for row in tables['routing_records'] if row['kind']=='packet' and row['reference']==reference and row['revision']==revision-1))
            variable={'revision','content_digest','current_classification','dependencies','priority','outcome_references','handoff_references'}
            require({k:v for k,v in asdict(previous).items() if k not in variable}=={k:v for k,v in asdict(record).items() if k not in variable})
            require(set(previous.outcome_references)<=set(record.outcome_references) and set(previous.handoff_references)<=set(record.handoff_references))
    require(set(names)==set(expected_names))
    for name,(reference,revision) in expected_names.items(): require((names[name]['department_reference'],names[name]['first_revision'])==(reference,revision))
    links={(row['packet_reference'],row['packet_revision']):row for row in tables['routing_links']}
    packet_keys={(reference,revision) for kind,reference,revision in records if kind=='packet'}
    require(set(links)==packet_keys)
    for key,link in links.items():
        packet=records[('packet',*key)];intake=records[('intake',link['intake_reference'],1)]
        department=records[('department',link['department_reference'],link['department_revision'])]
        rule=records[('rule',link['rule_reference'],link['rule_revision'])]
        require((packet.source_event_reference,packet.original_classification,packet.executive_reference,packet.recipient_references,
                 packet.registry_revision,packet.registry_digest,packet.rule_reference,packet.rule_revision,packet.rule_digest,
                 packet.required_action,packet.decision_reference,packet.visibility_references)==
                (intake.event_id,intake.original_classification,department.executive_reference,(department.department_id,),
                 department.revision,department.content_digest,rule.rule_id,rule.revision,rule.content_digest,rule.required_action,
                 rule.approval_reference,rule.visibility_references))
        require((link['department_digest'],link['rule_digest'])==(department.content_digest,rule.content_digest))
        require((department.department_id,department.revision,department.content_digest,department.executive_reference) in rule.recipients)
        for typ,values in (('classification',(packet.current_classification,)),
                           ('outcome',packet.outcome_references),('handoff',packet.handoff_references)):
            for value in values: require((typ,value) in refs)
        pilot_packet=key[1]==1 and any(row['packet_reference']==packet.packet_id for row in tables['pilot_packet_links'])
        if not pilot_packet:
            for value in packet.dependencies: require(('dependency',value) in refs)
        historical_approval(tables,department,'department');historical_approval(tables,rule,'rule')
    for row in tables['routing_evidence']:
        key=(row['kind'],row['record_reference'],row['record_revision']);record=records[key]
        require((row['content_digest'],row['reference'])==(record.content_digest,record.approval_reference))
        require(row_records[key]['actor_reference']!=row['grantor_reference'])
        require(datetime.fromisoformat(row['valid_from'])<datetime.fromisoformat(row['expires_at']))
        require(custody.verify({key:value for key,value in row.items() if key not in ('proof','dataset')},row['proof']))
    routing_events={}
    for row in sorted(tables['routing_events'],key=lambda row:(row['intake_reference'],row['sequence'])):
        intake=records[('intake',row['intake_reference'],1)];previous=routing_events.get(intake.event_id)
        data=row['payload']
        require((row['sequence'],row['previous_sequence'],row['previous_digest'])==
                ((previous['sequence']+1,previous['sequence'],previous['content_digest']) if previous else (1,None,None)))
        require((data['tenant_reference'],data['source_event_reference'],data['original_classification'],data['sequence'],data['previous_digest'],row['content_digest'])==
                (tenant,intake.event_id,intake.original_classification,row['sequence'],row['previous_digest'],fingerprint(data)))
        require(data['actor_reference'] in subjects)
        routing_events[intake.event_id]=row
    require({row['intake_reference']:row['sequence'] for row in tables['routing_journey_heads']}=={key:row['sequence'] for key,row in routing_events.items()})
    pilot_context=_validate_pilot(payload,custody,records,refs)
    _validate_receipts(tables,records,pilot_context)
    _reconcile_journal(tables,records,pilot_context)
    _reconcile_baseline_receipts(tables)


def _validate_pilot(payload,custody,records,refs):
    tables=payload['tables'];tenant=payload['tenant']
    journeys={};proposals={};proposal_rows={}
    for row in tables['pilot_journeys']:
        journey=decode_pilot('journey',row['payload']);intake=records[('intake',row['intake_reference'],1)]
        require((journey.journey_id,journey.tenant_reference,journey.intake_reference,journey.original_classification,journey.content_digest)==
                (row['reference'],tenant,intake.event_id,intake.original_classification,row['content_digest']))
        require(row['original_classification']==journey.original_classification)
        journeys[journey.journey_id]=journey
    for row in tables['pilot_proposals']:
        event=decode_pilot('event',row['payload'])
        require((event.tenant_reference,event.journey_reference,event.event_id,event.revision,event.content_digest)==
                (tenant,row['journey_reference'],row['event_reference'],row['revision'],row['content_digest']))
        require(row['previous_revision']==(event.revision-1 or None))
        rule=records[('rule',event.rule_reference,event.rule_revision)]
        require((event.rule_digest,classify_event(event))==(rule.content_digest,rule.classification))
        for kind,values in (('fact',event.evidence_references),('outcome',event.outcome_references),('handoff',event.handoff_references)):
            for value in values: require((kind,value) in refs)
        key=(event.journey_reference,event.event_id,event.revision);proposals[key]=event;proposal_rows[key]=row
    exact_heads(tables['pilot_proposals'],tables['pilot_proposal_heads'],('journey_reference','event_reference'),'revision')
    evidence={row['reference']:row for row in tables['pilot_evidence']}
    for row in evidence.values():
        key=(row['journey_reference'],row['event_reference'],row['proposal_revision']);proposal=proposals[key]
        require((proposal.approval_reference,proposal.content_digest)==(row['reference'],row['event_digest']))
        require(row['grantor_reference']!=proposal_rows[key]['actor_reference'])
        require(datetime.fromisoformat(row['valid_from'])<datetime.fromisoformat(row['expires_at']))
        require(custody.verify({key:value for key,value in row.items() if key not in ('proof','dataset')},row['proof']))
    decisions={(row['journey_reference'],row['event_reference']):row for row in tables['pilot_decisions']}
    links={};deliverables=set()
    for row in tables['pilot_packet_links']:
        links.setdefault((row['journey_reference'],row['event_reference']),[]).append(row['packet_reference'])
    for row in tables['pilot_deliverables']:
        deliverables.add((row['journey_reference'],row['event_reference'],row['kind'],row['reference'],row['packet_reference']))
    expected_deliverables=set();context={};heads={};accepted={};previous={}
    for row in sorted(tables['pilot_events'],key=lambda row:(row['journey_reference'],row['sequence'])):
        journey=journeys[row['journey_reference']];key=(journey.journey_id,row['event_reference'])
        proposal=proposals[(*key,row['proposal_revision'])];rule=records[('rule',proposal.rule_reference,proposal.rule_revision)]
        historical_approval(tables,rule,'rule')
        for reference,revision,_,_ in rule.recipients: historical_approval(tables,records[('department',reference,revision)],'department')
        require(proposal.approval_reference in evidence)
        proof=evidence[proposal.approval_reference]
        require((proof['journey_reference'],proof['event_reference'],proof['proposal_revision'],proof['event_digest'])==(*key,proposal.revision,proposal.content_digest))
        prior=previous.get(journey.journey_id);completed=accepted.setdefault(journey.journey_id,[])
        require((row['sequence'],row['previous_sequence'],row['previous_digest'])==
                ((prior['sequence']+1,prior['sequence'],prior['content_digest']) if prior else (1,None,None)))
        require(row['stage_index']==len(completed)+1 and proposal.stage_reference==STAGES[len(completed)])
        require(proposal.previous_event_reference==(completed[-1] if completed else None))
        missing=tuple(sorted(set(proposal.dependency_references)-set(completed)))
        disposition='blocked' if missing else 'accepted'
        require(row['disposition']==disposition)
        data=row['payload']
        require(set(data)=={'tenant_reference','journey_reference','event_reference','proposal_revision','event_digest',
                           'sequence','previous_digest','original_classification','stage_index','disposition',
                           'decision_reference','actor_reference','policy_revision','result'})
        require(row['content_digest']==fingerprint(data))
        for field in ('journey_reference','sequence','event_reference','proposal_revision','event_digest','previous_digest','original_classification','stage_index','disposition'):
            require(fingerprint(data[field])==fingerprint(row[field]))
        require(row['event_digest']==proposal.content_digest and row['original_classification']==journey.original_classification and data['tenant_reference']==tenant)
        decision=decisions[key];body=decision['payload']
        require(set(body)=={'reference','journey_reference','event_reference','classification','rule_reference',
                           'rule_revision','rule_digest','approval_reference','proposal_revision','event_digest',
                           'disposition','reason_reference','missing_dependencies','packet_references','state'})
        require(decision['reference']=='syn-decision-'+fingerprint(list(key)))
        require(decision['content_digest']==fingerprint(body))
        for field in ('journey_reference','event_reference','reference','classification','rule_reference','rule_revision','rule_digest','approval_reference','proposal_revision','event_digest','disposition','reason_reference','state'):
            require(fingerprint(body[field])==fingerprint(decision[field]))
        require((decision['classification'],decision['rule_reference'],decision['rule_revision'],decision['rule_digest'],decision['approval_reference'],decision['proposal_revision'],decision['event_digest'],decision['disposition'])==
                (classify_event(proposal),rule.rule_id,rule.revision,rule.content_digest,proposal.approval_reference,proposal.revision,proposal.content_digest,disposition))
        require(body['missing_dependencies']==list(missing) and decision['reason_reference']==('syn-missing-dependencies' if missing else 'syn-validated'))
        packet_ids=links.get(key,[])
        require(set(packet_ids)==set(body['packet_references']) and len(packet_ids)==len(body['packet_references']))
        require(data['decision_reference']==decision['reference'])
        result=data['result']
        require(fingerprint(result)==fingerprint(dict(journey_reference=journey.journey_id,event_reference=proposal.event_id,version=row['sequence'],status=disposition,packet_references=body['packet_references'],state='inactive')))
        if missing: require(not packet_ids)
        else:
            require(bool(packet_ids))
            key_values={records[('packet',reference,1)].idempotency_reference for reference in packet_ids}
            require(len(key_values)==1)
            departments={reference:records[('department',reference,revision)] for reference,revision,_,_ in rule.recipients}
            packets=derive_stage_packets(journey,records[('intake',journey.intake_reference,1)],proposal,rule,departments,next(iter(key_values)))
            require(body['packet_references']==[packet.packet_id for packet in packets])
            for packet in packets:
                require(packet==records[('packet',packet.packet_id,1)])
                for kind,values in (('outcome',proposal.outcome_references),('handoff',proposal.handoff_references)):
                    expected_deliverables.update((journey.journey_id,proposal.event_id,kind,value,packet.packet_id) for value in values)
            completed.append(proposal.event_id)
        progress='blocked' if missing else ('pending' if len(completed)<16 else proposal.terminal_reference.removeprefix('syn-'))
        heads[journey.journey_id]=(row['sequence'],len(completed),completed[-1] if completed else None,progress)
        previous[journey.journey_id]=row
        context[key]=(proposal,row,result)
    require(set(decisions)==set(context) and set(links)<=set(context) and deliverables==expected_deliverables)
    actual_heads={row['journey_reference']:(row['version'],row['completed_stage'],row['last_event_reference'],row['progress']) for row in tables['pilot_heads']}
    require(actual_heads=={reference:heads.get(reference,(0,0,None,'pending')) for reference in journeys})
    return journeys,proposals,context


def _validate_receipts(tables,records,pilot):
    journeys,proposals,context=pilot
    advanced=set();started=set();proposed=set()
    for row in tables['routing_receipts']:
        operation,key,result=row['operation'],row['key'],row['result']
        if operation in ('syn-route','syn-packet-revision','syn-distribute','syn-pilot-start','syn-pilot-propose'):
            require(isinstance(result,list))
            if operation=='syn-route': require(bool(result) and all(isinstance(value,str) for value in result))
            elif operation=='syn-pilot-start': require(len(result)==1 and isinstance(result[0],str))
            elif operation=='syn-pilot-propose':
                require(len(result)==3 and all(isinstance(value,str) for value in result[:2]) and type(result[2]) is int and result[2]>0)
            else:
                require(len(result)==(3 if operation=='syn-distribute' else 2) and isinstance(result[0],str)
                        and type(result[1]) is int and result[1]>0)
                if operation=='syn-distribute': require(isinstance(result[2],str))
        if operation=='syn-route':
            packets=[records[('packet',reference,1)] for reference in result]
            require(bool(packets))
            intake=records[('intake',packets[0].source_event_reference,1)]
            rule=records[('rule',packets[0].rule_reference,packets[0].rule_revision)]
            departments={reference:records[('department',reference,version)] for reference,version,_,_ in rule.recipients}
            require(tuple(packets)==derive_packets(intake,rule,departments,key))
            digest=fingerprint([asdict(intake),asdict(rule),key])
        elif operation=='syn-packet-revision': digest=records[('packet',result[0],result[1])].content_digest
        elif operation=='syn-distribute':
            require(any(event['payload']['event']=='syn-team-visibility' and event['payload']['reference']==result[0] and event['payload']['revision']==result[1] and event['payload']['details']['team_reference']==result[2] for event in tables['routing_events']))
            digest=fingerprint(result)
        elif operation=='syn-pilot-start':
            journey=journeys[result[0]];started.add(journey.journey_id)
            digest=fingerprint([asdict(journey),asdict(records[('intake',journey.intake_reference,1)])])
        elif operation=='syn-pilot-propose':
            proposal=proposals[tuple(result)];proposed.add(tuple(result));digest=proposal.content_digest
        elif operation=='syn-pilot-advance':
            proposal,event,expected=context[(result['journey_reference'],result['event_reference'])]
            require(fingerprint(result)==fingerprint(expected));advanced.add((result['journey_reference'],result['event_reference']))
            digest=fingerprint([proposal.content_digest,event['sequence']-1])
        else: raise ValueError('Unknown extended receipt operation')
        require(digest==row['payload_digest'])
    require(started==set(journeys) and proposed==set(proposals) and advanced==set(context))


def _reconcile_journal(tables,records,pilot):
    """Require the journal implied by the retained graph, not merely a valid prefix.

    Table arrays are unordered sets. Journal sequence, atomic operation batches,
    lifecycle order and packet revision order are material and cannot be resealed
    into a different history. Receipt keys themselves need not be chronological.
    """
    from collections import defaultdict, deque
    journeys,proposals,context=pilot
    policies={row['policy_revision'] for row in tables['policy_revisions']}
    subjects={row['subject_reference'] for row in tables['subjects']}
    record_rows={(row['kind'],row['reference'],row['revision']):row for row in tables['routing_records']}
    journey_rows={row['reference']:row for row in tables['pilot_journeys']}
    journal=defaultdict(deque)
    fields={'tenant_reference','source_event_reference','original_classification','sequence','previous_digest',
            'event','reference','revision','actor_reference','policy_revision','details'}

    def descriptor(intake,event,reference,revision,details,actor,policy):
        return fingerprint([intake,event,reference,revision,details,actor,policy])

    for row in sorted(tables['routing_events'],key=lambda row:(row['intake_reference'],row['sequence'])):
        body=row['payload']
        require(set(body)==fields and type(body['revision']) is int and body['revision']>0)
        require(type(body['policy_revision']) is int and body['policy_revision'] in policies and body['actor_reference'] in subjects)
        require(row['intake_kind']=='intake' and row['intake_revision']==1)
        journal[descriptor(row['intake_reference'],body['event'],body['reference'],body['revision'],
                           body['details'],body['actor_reference'],body['policy_revision'])].append(row['sequence'])

    def group(intake,items,metadata):
        positions=[]
        for event,reference,revision,details in items:
            key=descriptor(intake,event,reference,revision,details,metadata['actor_reference'],metadata['policy_revision'])
            require(bool(journal[key]));positions.append(journal[key].popleft())
        require(positions==list(range(positions[0],positions[0]+len(positions))))
        return positions

    seen=set();covered_intakes=set();covered_packets=set();starts={};advances={};packet_positions={};visibility=[]
    refs={(row['kind'],row['reference']):row for row in tables['routing_references']}
    for receipt in tables['routing_receipts']:
        operation,result=receipt['operation'],receipt['result']
        # Replays produce no additional receipts, except explicit visibility
        # requests with distinct keys, which legitimately append distinct events.
        if operation!='syn-distribute':
            identity=(operation,fingerprint(result));require(identity not in seen);seen.add(identity)
        if operation=='syn-pilot-propose': continue
        if operation=='syn-pilot-start':
            require(isinstance(result,list) and len(result)==1)
            journey=journeys[result[0]];intake=journey.intake_reference
            require(all(record_rows[('intake',intake,1)][field]==journey_rows[journey.journey_id][field]
                        for field in ('actor_reference','policy_revision')))
            positions=group(intake,[('syn-pilot-entry',journey.journey_id,1,{})],journey_rows[journey.journey_id])
            starts[journey.journey_id]=positions[0];covered_intakes.add(intake)
            require(positions[0]==1)
        elif operation=='syn-pilot-advance':
            key=(result['journey_reference'],result['event_reference']);proposal,event,_=context[key]
            intake=journeys[key[0]].intake_reference;metadata=event['payload']
            decision=next(row for row in tables['pilot_decisions'] if (row['journey_reference'],row['event_reference'])==key)
            items=[('syn-pilot-classified',key[1],proposal.revision,
                    {'decision_reference':decision['reference'],'status':event['disposition']})]
            for reference in result['packet_references']:
                items.append(('syn-pilot-packet',reference,1,{'event_reference':key[1]}))
                packet_row=record_rows[('packet',reference,1)]
                require(all(packet_row[field]==metadata[field] for field in ('actor_reference','policy_revision')))
                require(records[('packet',reference,1)].idempotency_reference==receipt['key'])
            positions=group(intake,items,metadata);advances[key]=positions
            for reference,position in zip(result['packet_references'],positions[1:]):
                require((reference,1) not in covered_packets);covered_packets.add((reference,1));packet_positions[(reference,1)]=position
        elif operation=='syn-route':
            require(isinstance(result,list) and bool(result))
            first=records[('packet',result[0],1)];intake=first.source_event_reference
            require(intake not in covered_intakes);covered_intakes.add(intake)
            metadata=record_rows[('intake',intake,1)]
            items=[('syn-intake',intake,1,{})]+[('syn-packet-proposed',reference,1,{}) for reference in result]
            positions=group(intake,items,metadata);require(positions[0]==1)
            for reference,position in zip(result,positions[1:]):
                require((reference,1) not in covered_packets);covered_packets.add((reference,1));packet_positions[(reference,1)]=position
                require(all(record_rows[('packet',reference,1)][field]==metadata[field] for field in ('actor_reference','policy_revision')))
        elif operation=='syn-packet-revision':
            require(isinstance(result,list) and len(result)==2 and type(result[1]) is int and result[1]>1)
            reference,revision=result;packet=records[('packet',reference,revision)]
            position=group(packet.source_event_reference,[('syn-packet-revised',reference,revision,{})],record_rows[('packet',reference,revision)])[0]
            require((reference,revision) not in covered_packets);covered_packets.add((reference,revision));packet_positions[(reference,revision)]=position
        elif operation=='syn-distribute':
            require(isinstance(result,list) and len(result)==3 and type(result[1]) is int)
            reference,revision,team=result;packet=records[('packet',reference,revision)]
            department=records[('department',packet.recipient_references[0],packet.registry_revision)]
            require(team in department.team_references and refs[('team',team)]['parent_reference']==department.executive_reference)
            actor=refs[('executive',department.executive_reference)]['parent_reference']
            # Visibility journal records do not have a separate metadata row.
            candidates=[row for row in tables['routing_events'] if row['intake_reference']==packet.source_event_reference
                        and row['payload']['event']=='syn-team-visibility' and row['payload']['reference']==reference
                        and row['payload']['revision']==revision and row['payload']['details']=={'team_reference':team}
                        and row['payload']['actor_reference']==actor]
            positions=[]
            for row in sorted(candidates,key=lambda row:row['sequence']):
                body=row['payload'];key=descriptor(packet.source_event_reference,'syn-team-visibility',reference,revision,body['details'],actor,body['policy_revision'])
                if journal[key]: positions=[journal[key].popleft()];break
            require(bool(positions));visibility.append(((reference,revision),positions[0]))
        else: raise ValueError('Unknown journal operation')
    require(not any(journal.values()))
    require(covered_intakes=={reference for kind,reference,revision in records if kind=='intake'})
    require(covered_packets=={(reference,revision) for kind,reference,revision in records if kind=='packet'})
    for journey in journeys:
        previous=starts[journey]
        for key,(_,event,_) in sorted(context.items(),key=lambda item:item[1][1]['sequence']):
            if key[0]!=journey: continue
            positions=advances[key];require(positions[0]>previous);previous=positions[-1]
    for (reference,revision),position in packet_positions.items():
        if revision>1: require(position>packet_positions[(reference,revision-1)])
    for key,position in visibility: require(position>packet_positions[key])



def _reconcile_baseline_receipts(tables):
    # The complete archive includes the original foundation as well as the pilot.
    # Baseline validation checks receipt -> result; require result -> receipt too.
    expected=set()
    for table,operation,reference,revision in (
            ('registry_revisions','registry.append_draft','record_reference','revision'),
            ('packet_revisions','packet.append_inactive','packet_reference','revision'),
            ('journey_events','journey.append_inactive','journey_reference','sequence')):
        expected.update((operation,row[reference],row[revision]) for row in tables[table])
    actual=[(row['operation_reference'],row['result_reference'],row['result_revision'])
            for row in tables['idempotency_receipts']]
    require(len(actual)==len(set(actual)) and set(actual)==expected)
