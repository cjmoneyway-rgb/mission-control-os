"""Phase 1E readiness gates use synthetic references and never launch a pilot."""
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import json
import socket
import unittest
from unittest.mock import patch

from mission_control.readiness import (
    READINESS_CONTROLS, ControlEvidence, PilotAuthorizationPlan, ReadinessPackage,
    assess_pilot_plan, assess_readiness, decode_readiness,
    require_operational_authorization, seal_readiness)
from mission_control.synthetic_identity import ROLE_ACTIONS, fingerprint


BASE_COMMIT = '287d9d8b62b95faae17e48dcbeb7108e0ec57145'


def readiness_fixtures():
    now = datetime.now(timezone.utc)
    evidence = tuple(seal_readiness(ControlEvidence(
        'syn-tenant-1', 'syn-readiness-evidence-'+str(index).zfill(2), 1, control,
        'syn-artifact-'+str(index).zfill(2), fingerprint(['artifact', control]),
        'syn-control-owner-'+str(index).zfill(2),
        'syn-control-reviewer-'+str(index).zfill(2),
        now-timedelta(minutes=1), now+timedelta(minutes=10)))
        for index, control in enumerate(READINESS_CONTROLS, 1))
    package = seal_readiness(ReadinessPackage(
        'syn-tenant-1', 'syn-readiness-package-1', 1, BASE_COMMIT,
        'syn-readiness-owner', 'syn-readiness-reviewer',
        tuple((item.control, item.evidence_id, item.revision, item.content_digest)
              for item in evidence)))
    plan = seal_readiness(PilotAuthorizationPlan(
        'syn-tenant-1', 'syn-pilot-plan-1', 1, package.package_id,
        package.revision, package.content_digest, 'syn-pilot-journey-1',
        ('syn-participant-1',), ('syn-action-observe',),
        ('syn-field-reference-1',), ('syn-stop-condition-1',),
        'syn-rollback-owner', now+timedelta(minutes=1), now+timedelta(minutes=6)))
    return evidence, package, plan, now


class ProductionReadinessTests(unittest.TestCase):
    def setUp(self):
        self.evidence, self.package, self.plan, self.now = readiness_fixtures()

    def test_all_required_controls_are_unique_and_stable(self):
        self.assertEqual(len(READINESS_CONTROLS), 12)
        self.assertEqual(len(set(READINESS_CONTROLS)), 12)
        self.assertIn('protected-storage', READINESS_CONTROLS)
        self.assertIn('data-admission', READINESS_CONTROLS)
        self.assertIn('pilot-operating-plan', READINESS_CONTROLS)

    def test_complete_package_is_synthetically_ready_but_not_authorized(self):
        result = assess_readiness(self.package, self.evidence, self.now)
        self.assertTrue(result.synthetic_ready)
        self.assertFalse(result.operational_authorized)
        self.assertEqual(result.verified_controls, 12)
        self.assertEqual(result.package_digest, self.package.content_digest)

    def test_valid_inactive_pilot_plan_is_not_launch_permission(self):
        result = assess_pilot_plan(self.plan, self.package, self.evidence, self.now)
        self.assertTrue(result.synthetic_ready)
        self.assertFalse(result.operational_authorized)
        with self.assertRaises(PermissionError):
            require_operational_authorization(self.plan, result)

    def test_contracts_round_trip_strict_json(self):
        for kind, record in [('evidence', self.evidence[0]),
                             ('package', self.package), ('pilot-plan', self.plan)]:
            encoded = json.dumps(asdict(record), default=lambda value: value.isoformat())
            self.assertEqual(decode_readiness(kind, encoded), record)

    def test_duplicate_json_keys_and_unknown_fields_are_rejected(self):
        for kind, record in [('evidence', self.evidence[0]),
                             ('package', self.package), ('pilot-plan', self.plan)]:
            encoded = json.dumps(asdict(record), default=lambda value: value.isoformat())
            duplicate = encoded[:-1]+',"state":"active"}'
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                decode_readiness(kind, duplicate)
            data = asdict(record)
            data['syn-extra'] = 'syn-private-marker'
            with self.assertRaises(ValueError) as caught:
                decode_readiness(kind, data)
            self.assertNotIn('syn-private-marker', str(caught.exception))

    def test_operational_or_active_contracts_are_rejected(self):
        for record in (*self.evidence, self.package, self.plan):
            for change in ({'state': 'active'}, {'dataset': 'operational'},
                           {'schema_revision': 2}):
                with self.assertRaises(ValueError):
                    seal_readiness(replace(record, **change)).validate()

    def test_evidence_requires_independent_current_review(self):
        item = self.evidence[0]
        invalid = (
            replace(item, reviewer_reference=item.issuer_reference),
            replace(item, valid_from=self.now+timedelta(minutes=1)),
            replace(item, expires_at=self.now),
            replace(item, control='unknown-control'),
            replace(item, artifact_digest='bad'),
        )
        for record in invalid:
            with self.subTest(record=record), self.assertRaises(ValueError):
                seal_readiness(record).validate(self.now)

    def test_package_requires_independent_review_and_exact_commit(self):
        for change in ({'reviewer_reference': self.package.owner_reference},
                       {'base_commit': '287d9d8'}, {'base_commit': 'z'*40}):
            with self.assertRaises(ValueError):
                seal_readiness(replace(self.package, **change)).validate()

    def test_missing_duplicate_or_unknown_control_fails_closed(self):
        bindings = self.package.evidence_bindings
        cases = (
            bindings[:-1],
            (*bindings[:-1], bindings[0]),
            (('unknown-control', *bindings[0][1:]), *bindings[1:]),
        )
        for value in cases:
            with self.assertRaises(ValueError):
                seal_readiness(replace(self.package, evidence_bindings=tuple(value))).validate()

    def test_evidence_cannot_be_reused_across_controls(self):
        bindings = list(self.package.evidence_bindings)
        bindings[1] = (bindings[1][0], bindings[0][1], bindings[1][2], bindings[1][3])
        with self.assertRaises(ValueError):
            seal_readiness(replace(self.package, evidence_bindings=tuple(bindings))).validate()

    def test_stale_revision_digest_or_control_binding_fails_closed(self):
        first = self.evidence[0]
        replacements = (
            replace(first, revision=2),
            replace(first, artifact_digest=fingerprint(['changed'])),
            replace(first, control=READINESS_CONTROLS[1]),
        )
        for changed in replacements:
            changed = seal_readiness(changed)
            supplied = (changed, *self.evidence[1:])
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                assess_readiness(self.package, supplied, self.now)

    def test_cross_tenant_or_extra_evidence_fails_closed(self):
        changed = seal_readiness(replace(self.evidence[0], tenant_reference='syn-tenant-2'))
        with self.assertRaises(ValueError):
            assess_readiness(self.package, (changed, *self.evidence[1:]), self.now)
        with self.assertRaises(ValueError):
            assess_readiness(self.package, (*self.evidence, self.evidence[0]), self.now)

    def test_package_edit_invalidates_pilot_plan_binding(self):
        changed = seal_readiness(replace(self.package, revision=2))
        with self.assertRaises(ValueError):
            assess_pilot_plan(self.plan, changed, self.evidence, self.now)

    def test_pilot_plan_requires_exact_package_identity(self):
        changes = (
            {'readiness_package_id': 'syn-other-package'},
            {'readiness_package_revision': 2},
            {'readiness_package_digest': '0'*64},
            {'tenant_reference': 'syn-tenant-2'},
        )
        for change in changes:
            plan = seal_readiness(replace(self.plan, **change))
            with self.subTest(change=change), self.assertRaises(ValueError):
                assess_pilot_plan(plan, self.package, self.evidence, self.now)

    def test_pilot_plan_requires_bounded_window_and_complete_controls(self):
        cases = (
            replace(self.plan, ends_at=self.plan.starts_at),
            replace(self.plan, participant_references=()),
            replace(self.plan, permitted_actions=()),
            replace(self.plan, admitted_field_references=()),
            replace(self.plan, stop_conditions=()),
            replace(self.plan, authorization_reference='syn-self-approved'),
        )
        for record in cases:
            with self.assertRaises(ValueError):
                seal_readiness(record).validate()

    def test_mutable_or_duplicate_plan_sequences_are_rejected(self):
        for field in ('participant_references', 'permitted_actions',
                      'admitted_field_references', 'stop_conditions'):
            value = getattr(self.plan, field)
            for changed in (list(value), value+value):
                with self.subTest(field=field, changed=changed), self.assertRaises(ValueError):
                    seal_readiness(replace(self.plan, **{field: changed})).validate()

    def test_boolean_revisions_and_digest_tampering_are_rejected(self):
        for record in (self.evidence[0], self.package, self.plan):
            with self.assertRaises(ValueError):
                replace(record, revision=True).validate()
            with self.assertRaises(ValueError):
                replace(record, content_digest='0'*64).validate()

    def test_readiness_evaluation_has_no_network_or_provider_path(self):
        with patch.object(socket, 'socket', side_effect=AssertionError('Network forbidden')):
            result = assess_pilot_plan(self.plan, self.package, self.evidence, self.now)
        self.assertFalse(result.operational_authorized)

    def test_readiness_contracts_cannot_reach_existing_engine(self):
        from mission_control.engine import MissionControlOS
        engine = MissionControlOS(audit_log=None)
        with patch.object(engine, '_invoke', side_effect=AssertionError('Provider forbidden')):
            for record in (self.evidence[0], self.package, self.plan):
                with self.assertRaises(ValueError):
                    engine.run(record)

    def test_existing_roles_cannot_activate_or_authorize_pilot(self):
        for actions in ROLE_ACTIONS.values():
            self.assertNotIn('pilot.activate', actions)
            self.assertNotIn('pilot.operational_authorize', actions)
            self.assertNotIn('provider.purchase', actions)


if __name__ == '__main__':
    unittest.main()
