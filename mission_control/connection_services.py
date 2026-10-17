"""Thin opt-in Phase 1 adapter. No SQL, migrations, new store, or external transport."""
from contextlib import contextmanager
from dataclasses import asdict

from .connection_contracts import validate_projection
from .department_routing import decode, derive_packets
from .governance import review_output
from .podcast_pilot import decode_pilot
from .readiness import assess_readiness
from .registry_persistence import ConflictError
from .synthetic_identity import fingerprint


class PhaseOneServices:
    def __init__(self, store=None, readiness_sources=None, governance_sources=None):
        # Trusted fixture dependencies; none is selected or supplied by a request.
        self.store = store
        self.readiness_sources = dict(readiness_sources or {})
        self.governance_sources = dict(governance_sources or {})

    def execute(self, request, context, budget):
        action = request.requested_action
        if action == 'readiness.status':
            # Independently authenticate here too; never accept evidence from JSON.
            if self.store is None: raise PermissionError('Unconfigured synthetic authority')
            self.store.authority.authorize(context.session_reference, request.tenant_reference,
                                           context.policy_revision, 'audit.read', 'syn-audit')
            package, evidence = self.readiness_sources[(request.tenant_reference, request.resource_reference)]
            if (package.tenant_reference != request.tenant_reference or package.package_id != request.resource_reference
                    or package.revision != request.expected_revision):
                raise ConflictError('Readiness binding mismatch')
            assessment = assess_readiness(package, evidence)
            budget.check()
            return validate_projection(dict(state='inactive', synthetic_ready=assessment.synthetic_ready,
                operational_authorized=False, verified_controls=assessment.verified_controls))
        if action == 'governance.review':
            if self.store is None: raise PermissionError('Unconfigured synthetic authority')
            self.store.authority.authorize(context.session_reference, request.tenant_reference,
                                           context.policy_revision, 'audit.read', 'syn-audit')
            revision, artifact = self.governance_sources[(request.tenant_reference, request.payload['output_reference'])]
            if request.resource_reference != request.payload['output_reference'] or request.expected_revision != revision:
                raise ConflictError('Governance revision mismatch')
            review = review_output(artifact)
            budget.check()
            return validate_projection(dict(state='inactive', passed=review.passed, finding_count=len(review.findings),
                                             operational_authorized=False))
        if self.store is None: raise PermissionError('Unconfigured domain store')
        with self._transaction(request, context, budget) as tx:
            budget.check()
            if request.source_surface=='syn-command-center' and request.requested_action in ('intake','decision.submit','work-packet.create','assignment.acknowledge','handoff.record','outcome.record'):
                self._dependency_gate(tx,request)
            result, write = self._execute(tx, request)
            result = validate_projection(result)
            budget.check()  # Cancellation/timeout/output errors roll back before commit.
            if write: tx.commit()
        return result

    @contextmanager
    def _transaction(self, request, context, budget):
        try:
            with self.store.transaction(request.tenant_reference, context.session_reference, context.policy_revision) as tx:
                yield tx
        except RuntimeError:
            # Phase 1 sanitizes TimeoutError into RuntimeError after rollback.
            # Reclassify only when the trusted budget confirms interruption.
            budget.check()
            raise

    @staticmethod
    def _execute(tx, request):
        p = request.payload; resource = request.resource_reference
        expected = request.expected_revision
        key = 'syn-api-' + fingerprint([request.requested_action, request.tenant_reference,
            request.actor_reference, request.purpose, request.source_surface, request.idempotency_key])
        action = request.requested_action
        if action == 'intake':
            journey = decode_pilot('journey', p['journey']); intake = decode('Intake', p['intake'])
            if expected != 0 or journey.journey_id != resource or request.correlation_reference != resource:
                raise ConflictError('Entry binding mismatch')
            tx.start_journey(journey, intake, key)
            return dict(state='inactive', journey_reference=resource, intake_reference=intake.event_id,
                        original_classification=intake.original_classification, version=0), True
        if action == 'decision.submit':
            event = decode_pilot('event', p['event'])
            if event.journey_reference != resource or request.correlation_reference != resource:
                raise PermissionError('Journey binding mismatch')
            tx.propose_event(event, expected, key)
            return dict(state='inactive', status='proposed', event_reference=event.event_id,
                        revision=event.revision, journey_reference=resource), True
        if action == 'work-packet.create':
            if request.correlation_reference != resource: raise PermissionError('Journey binding mismatch')
            result = tx.advance_event(resource, p['event_reference'], p['proposal_revision'], expected, key)
            return result, True
        if action in ('journey.read', 'classification.preserve'):
            snapshot = tx.read_pilot(resource)
            if request.correlation_reference != resource or snapshot['head']['version'] != expected:
                raise ConflictError('Journey revision mismatch')
            original = snapshot['journey']['original_classification']
            if action == 'classification.preserve' and p['original_classification'] != original:
                raise PermissionError('Original classification is immutable')
            result = dict(state='inactive', journey_reference=resource,
                original_classification=original, version=expected,
                completed_stage=snapshot['head']['completed_stage'])
            if action == 'journey.read':
                # No whole payloads, decision proofs, actors, facts or guest reference.
                result['events'] = [dict(event_reference=e['event_reference'], sequence=e['sequence'],
                                         disposition=e['disposition']) for e in snapshot['events']]
            return result, False
        if action == 'visibility.project':
            if expected < 1: raise ConflictError('Packet revision required')
            tx._get('packet', resource, expected, latest=True)
            result = tx.view_packet(resource, expected, p['audience'], p['team_reference'])
            if result['source_event_reference'] != request.correlation_reference:
                raise PermissionError('Intake correlation mismatch')
            # view_packet produces its own minimized audit; persist it on a read.
            return result, True
        if action == 'outbox.prepare':
            from .connection_contracts import CONNECTORS
            for connector in CONNECTORS: connector.validate()
            if resource != p['record_reference']: raise PermissionError('Outbox record binding mismatch')
            tx._get('packet', resource, expected, latest=True)
            projection = tx.view_packet(resource, expected, 'command')
            if projection['source_event_reference'] != request.correlation_reference:
                raise PermissionError('Outbox correlation mismatch')
            return dict(state='inactive', **p), True
        if action == 'routing.preview':
            intake = decode('Intake', p['intake'])
            if intake.event_id != request.correlation_reference or expected != p['rule_revision']:
                raise ConflictError('Routing binding mismatch')
            tx._auth('packet.route_simulate', resource)
            tx._auth('registry.rule.read', resource)
            if tx._rows('routing_records', kind='intake', reference=intake.event_id):
                if tx._get('intake', intake.event_id, 1) != intake:
                    raise PermissionError('Existing intake is immutable')
            rule = tx._get('rule', resource, expected, latest=True)
            tx._verify_evidence('rule', rule)
            departments = tx._rule_refs(rule, approved=True)
            packets = derive_packets(intake, rule, departments, key)
            for packet in packets:
                tx._auth('packet.routing.append', packet.packet_id)
                tx._auth('packet.routing.read', packet.packet_id)
            # Pure existing derivation: no intake, packet, receipt or journal insert.
            return dict(state='inactive', packet_references=[p.packet_id for p in packets],
                        original_classification=intake.original_classification), False
        if action in ('assignment.acknowledge', 'handoff.record', 'outcome.record'):
            packet = decode('DepartmentPacket', p['packet'])
            if packet.packet_id != resource or packet.source_event_reference != request.correlation_reference:
                raise PermissionError('Packet binding mismatch')
            # Responsible individual ownership is resolved by the existing service.
            tx.view_packet(resource, expected, 'executive')
            field = 'handoff_references' if action == 'handoff.record' else 'outcome_references'
            value = p['handoff_reference' if action == 'handoff.record' else
                      'acknowledgement_reference' if action == 'assignment.acknowledge' else 'outcome_reference']
            prior = tx._get('packet', resource, expected)
            if value not in getattr(packet, field) or value in getattr(prior, field):
                raise ConflictError('New linked record required')
            # Reuse exact Phase 1 revision, append-only, approval and reference rules.
            tx.append_packet_revision(packet, expected, key)
            return dict(state='inactive', packet_reference=resource, revision=packet.revision), True
        raise PermissionError('Unsupported domain command')

    def _governed_identity(self, request, context):
        from .connection_gateway import SyntheticPolicyGate
        from .connection_contracts import SURFACES
        if self.store is None:raise PermissionError('Unconfigured synthetic store')
        SyntheticPolicyGate(self.store.authority,('syn-technical-review',),SURFACES).verify(request,context)

    @staticmethod
    def _dependency_gate(tx, request):
        """Read current protected prerequisites; actual mutations retain all domain checks."""
        from .connection_gateway import required_permission
        from .podcast_pilot import derive_stage_packets
        action,resource=required_permission(request)
        tx._auth(action,resource)  # Before any target lookup.
        p=request.payload
        if request.requested_action=='intake':return
        if request.requested_action in ('decision.submit','work-packet.create'):
            if request.requested_action=='decision.submit':
                event=decode_pilot('event',p['event'])
            else:
                event=tx._proposal(request.resource_reference,p['event_reference'],p['proposal_revision'])
                try:tx._verify_pilot_approval(event)
                except PermissionError:raise UnresolvedApproval() from None
            tx._auth('registry.rule.read',event.rule_reference)
            rule=tx._get('rule',event.rule_reference,event.rule_revision,latest=True)
            try:
                tx._verify_evidence('rule',rule)
                departments=tx._rule_refs(rule,approved=True)
            except PermissionError:raise UnresolvedApproval() from None
            journey=tx._journey(event.journey_reference)
            intake=tx._get('intake',journey.intake_reference,1)
            derive_stage_packets(journey,intake,event,rule,departments,'syn-ui-eligibility')
            accepted={row['event_reference'] for row in tx._pr('pilot_events',journey_reference=journey.journey_id) if row['disposition']=='accepted'}
            if not set(event.dependency_references)<=accepted:raise UnresolvedDependencies()
            return
        if request.requested_action in ('assignment.acknowledge','handoff.record','outcome.record'):
            tx._auth('packet.routing.read',request.resource_reference)
            packet=tx._get('packet',request.resource_reference,request.expected_revision,latest=True)
            journeys=tx._pr('pilot_journeys',intake_reference=packet.source_event_reference)
            if len(journeys)!=1:raise UnresolvedDependencies()
            tx._auth('journey.pilot.read',journeys[0]['reference'])
            accepted={row['event_reference'] for row in tx._pr('pilot_events',journey_reference=journeys[0]['reference']) if row['disposition']=='accepted'}
            if not set(packet.dependencies)<=accepted:raise UnresolvedDependencies()
            return
        raise PermissionError('Unsupported synthetic action')

    def eligibility(self, request, context, budget):
        """Rollback-only rehearsal of existing services, never a new mutation engine.

        Deferred SQL constraints are forced before success; no commit is requested.
        The UI source repeats prerequisite checks inside its actual mutation transaction.
        """
        from datetime import datetime,timezone
        from .connection_contracts import WRITE_ACTIONS,validate_eligibility
        blockers=[]
        try:
            if request.requested_action not in WRITE_ACTIONS:raise ValueError('Unsupported action')
            self._governed_identity(request,context)
            with self._transaction(request,context,budget) as tx:
                budget.check();self._dependency_gate(tx,request)
                result,_=self._execute(tx,request)
                validate_projection(result)
                # Reuse commit-time authority/approval validation without committing.
                tx.recheck()
                tx.connection.execute('SET CONSTRAINTS ALL IMMEDIATE')
                budget.check()
        except UnresolvedDependencies:blockers=['unresolved_dependencies']
        except UnresolvedApproval:blockers=['unresolved_approval']
        except ConflictError:blockers=['stale_revision']
        except PermissionError:blockers=['authorization_denied']
        except TimeoutError:raise
        except Exception:blockers=['eligibility_unavailable']
        return validate_eligibility(dict(target_reference=request.resource_reference,
            requested_action=request.requested_action,eligible=not blockers,blocker_codes=blockers,
            expected_revision=request.expected_revision,evaluated_at=datetime.now(timezone.utc).isoformat(),schema_revision=1),request)

    def command_center(self, request, context, budget):
        """Six authorized record facets, from existing tables; no exclusive lifecycle fiction."""
        from .connection_contracts import COMMAND_STAGES,validate_command_center
        self._governed_identity(request,context)
        queues={stage:[] for stage in COMMAND_STAGES}
        with self._transaction(request,context,budget) as tx:
            session,policy=tx.authority.resolve(tx.session,tx.tenant,tx.revision)
            # Enumerate exact permitted grant candidates, never hidden database rows.
            candidates=sorted({grant.resource for grant in policy.grants
                if grant.role in session.principal.roles and grant.action=='journey.pilot.read'
                and grant.subject_reference in (None,session.principal.subject_reference)})
            for reference in candidates:
                budget.check()
                try:tx.authority.authorize(tx.session,tx.tenant,tx.revision,'journey.pilot.read',reference)
                except PermissionError:continue
                tx._auth('journey.pilot.read',reference)
                rows=tx._pr('pilot_journeys',reference=reference)
                if not rows:continue
                journey=tx._journey(reference)
                history=sorted(tx._pr('pilot_events',journey_reference=reference),key=lambda row:row['sequence'])
                accepted={row['event_reference'] for row in history if row['disposition']=='accepted'}
                history_refs=[row['event_reference'] for row in history]
                head=tx._pr('pilot_heads',journey_reference=reference)[0]
                def item(stage,identifier,revision,**changes):
                    value=dict(reference=identifier,current_stage=stage,original_classification=journey.original_classification,
                        owning_department_reference=None,priority=None,technical_status='inactive',dependency_state='resolved',
                        risk_state='unresolved',approval_state='not_required',assigned_owner_reference=None,next_required_action=None,
                        outcome_evidence_reference=None,revision=revision,last_authorized_update=None,history_references=history_refs)
                    value.update(changes);queues[stage].append(value)
                item('information',reference,head['version'],last_authorized_update=rows[0]['created_at'].isoformat() if head['version']==0 else None)
                proposals=tx._pr('pilot_proposal_heads',journey_reference=reference)
                for proposal in sorted(proposals,key=lambda row:row['event_reference']):
                    event=tx._proposal(reference,proposal['event_reference'],proposal['revision'])
                    state=next((row['disposition'] for row in history if row['event_reference']==event.event_id),'proposed')
                    approval='unresolved'
                    try:tx._verify_pilot_approval(event,remember=False);approval='synthetic_verified'
                    except PermissionError:pass
                    created=tx._pr('pilot_proposals',journey_reference=reference,event_reference=event.event_id,revision=event.revision)[0]['created_at']
                    shared=dict(technical_status=state,dependency_state='resolved' if set(event.dependency_references)<=accepted else 'unresolved',
                        approval_state=approval,last_authorized_update=created.isoformat())
                    # Intelligence remains an advisory facet; decision proof never leaves service.
                    item('intelligence',event.event_id,event.revision,**shared)
                    item('decision',event.event_id,event.revision,**shared)
                for link in sorted(tx._pr('pilot_packet_links',journey_reference=reference),key=lambda row:row['packet_reference']):
                    packet_ref=link['packet_reference']
                    try:
                        tx.authority.authorize(tx.session,tx.tenant,tx.revision,'packet.routing.read',packet_ref)
                    except PermissionError:continue
                    tx._auth('packet.routing.read',packet_ref)
                    packet=tx._get('packet',packet_ref,tx._head('packet',packet_ref),latest=True)
                    owner=None
                    try:
                        tx.authority.authorize(tx.session,tx.tenant,tx.revision,'packet.view.executive',packet.executive_reference)
                        executive=tx._reference('executive',packet.executive_reference)
                        if executive['parent_reference']==session.principal.subject_reference and session.kind=='human':
                            tx._auth('packet.view.executive',packet.executive_reference);owner=session.principal.subject_reference
                    except PermissionError:pass
                    packet_row=tx._rows('routing_records',kind='packet',reference=packet_ref,revision=packet.revision)[0]
                    # Evidence is checked in-process and minimized to a technical status only.
                    approval='unresolved'
                    try:
                        tx._auth('registry.rule.read',packet.rule_reference)
                        rule=tx._get('rule',packet.rule_reference,packet.rule_revision,latest=True)
                        tx._verify_evidence('rule',rule,remember=False)
                        tx._rule_refs(rule,approved=True)
                        history_row=next((row for row in history if row['event_reference']==link['event_reference']),None)
                        if history_row is None:raise ValueError('Missing protected history binding')
                        event=tx._proposal(reference,link['event_reference'],history_row['proposal_revision'])
                        tx._verify_pilot_approval(event,remember=False)
                        approval='synthetic_verified'
                    except PermissionError:pass
                    common=dict(owning_department_reference=packet.recipient_references[0],priority=packet.priority,
                        dependency_state='resolved' if set(packet.dependencies)<=accepted else 'unresolved',approval_state=approval,
                        assigned_owner_reference=owner,next_required_action=packet.required_action if owner is not None else None,
                        last_authorized_update=packet_row['created_at'].isoformat())
                    item('assignment',packet_ref,packet.revision,**common)
                    item('execution',packet_ref,packet.revision,**common)
                    if packet.outcome_references:
                        item('measurement',packet_ref,packet.revision,outcome_evidence_reference=packet.outcome_references[-1],**common)
                tx._audit('journey.pilot.read',reference,session)
            projection=validate_command_center(dict(schema_revision=1,state='inactive',queues=[dict(stage=stage,count=len(queues[stage]),
                blocked_count=sum(value['technical_status']=='blocked' or value['dependency_state']=='unresolved' or value['approval_state']=='unresolved' for value in queues[stage]),items=queues[stage]) for stage in COMMAND_STAGES]))
            budget.check();tx.commit()
        return projection


class UnresolvedDependencies(PermissionError):
    """Sanitized eligibility blocker, never contains missing protected references."""


class UnresolvedApproval(PermissionError):
    """Technical approval prerequisite unavailable; never contains evidence."""
