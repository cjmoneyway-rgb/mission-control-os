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
