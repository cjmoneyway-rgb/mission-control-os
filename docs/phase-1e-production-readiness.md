# Phase 1E: production-readiness and pilot-authorization gates

Phase 1E extends the existing Mission Control OS™ repository after merged Phase 1D
commit `287d9d8b62b95faae17e48dcbeb7108e0ec57145`. It does not create a second
system. It closes the pre-provisioning design gap by converting every outstanding
production-readiness requirement into an exact, machine-validated evidence gate.

This phase is intentionally provider-neutral and purchase-free. It adds no hosted
database, credentials, production identity provider, key service, integration,
deployment, confidential record, operational routing or pilot activation.

## Completion boundary

Phase 1E completes everything that can be safely implemented before provider,
identity, custody, retention and operating decisions are approved. A complete
synthetic package can be technically ready while remaining explicitly unauthorized
for operational use. There is no code path that converts technical readiness into
launch permission.

The remaining work after this phase is not another architecture rebuild. It is:

1. CEO selection and approval of the actual provider, region, budget, owners,
   permissions, custody, retention and recovery objectives after current official
   documentation and contractual terms are verified.
2. Provisioning and testing an isolated protected environment with synthetic data.
3. A separate admission and launch decision for one bounded confidential pilot.

## Twelve required controls

Every readiness package must bind one unique, current evidence revision and digest
for each control. Missing, duplicate, stale, expired, cross-tenant, reused or altered
evidence fails closed.

| Control | Required decision or proof before operational use |
|---|---|
| provider-contract | Exact service, tier, region, pricing, terms, subprocessors, exit and deletion obligations |
| protected-storage | Network isolation, encryption, deletion protection, administrators and tenant boundary |
| identity-mfa | Individual identities, MFA, recovery, service identity and privileged-session requirements |
| authorization-separation | Exact role/action matrix, ownership, policy administration and separation of duties |
| approval-authority | Approval issuer, delegation, revocation, validity and evidence access |
| key-custody | Independent signing/encryption custody, rotation, recovery and key-deletion safeguards |
| audit-observability | Covered events, privileged-access visibility, restricted export and independent review |
| backup-recovery | Backup/PITR configuration, locations, RPO/RTO and witnessed restore test |
| retention-legal-hold | Separate record-class durations, legal holds, deletion authority and evidence |
| incident-response | Detection, escalation, containment, notification, rollback and accountable owners |
| data-admission | Approved real fields, classification, consent, visibility, purpose and handling rules |
| pilot-operating-plan | Named participants, duration, permitted actions, stop conditions and rollback owner |

## Evidence and package contracts

`ControlEvidence` binds the tenant, control, evidence ID, revision, artifact
reference and SHA-256 digest, issuer, independent reviewer and validity interval.
Evidence is synthetic, immutable and inactive. Issuer and reviewer must differ.

`ReadinessPackage` binds all twelve controls exactly once to their evidence ID,
revision and content digest. It also binds the exact reviewed Git commit and requires
separate package owner and reviewer identities. One evidence item cannot satisfy two
controls. Editing any evidence, package field or revision changes the digest and
invalidates downstream bindings.

`assess_readiness()` verifies the complete graph and returns
`synthetic_ready=True` only when every exact binding is current and consistent. Its
result always carries `operational_authorized=False` and reason code
`separate_operational_authorization_required`.

## Proposed pilot authorization plan

`PilotAuthorizationPlan` binds an exact readiness-package ID, revision and digest;
one opaque journey; unique participant, action and admitted-field references; a
bounded time window; stop conditions; and a rollback owner. The plan must remain
synthetic and inactive, and `authorization_reference` must remain empty.

`assess_pilot_plan()` validates the plan and the complete readiness graph. It does
not authorize launch. `require_operational_authorization()` always raises until a
separate production authority is designed, implemented, reviewed and explicitly
approved. No existing synthetic role can grant `pilot.activate`,
`pilot.operational_authorize` or `provider.purchase`.

## Input, privacy and execution boundaries

All JSON boundaries reject duplicate keys, unknown fields, missing fields and
nonfinite values through the existing strict parser. Invalid-input messages do not
echo rejected payloads. The contracts accept only opaque `syn-` references; this is
test hygiene, not a claim that prefixing real information makes it safe.

Readiness contracts are not accepted by the existing CLI or execution engine. They
have no provider, network, storage, migration, notification or integration path.
They do not alter the 34-table Phase 1D archive or legacy logs. The archive continues
to represent the synthetic registry/routing/pilot data plane; readiness planning is
a reviewed pre-provisioning control package, not an operational database record.

## Verification

Phase 1E adds 20 offline regression tests. The complete suite requirement becomes
**277 tests**, including the existing **132 PostgreSQL tests**. The manual workflow
continues to use disposable PostgreSQL 17.11, job-generated credentials, pinned
native Node.js 24 actions, read-only repository permission, no secrets, no artifacts
and no deployment.

The new tests cover:

- all twelve exact controls and complete-package enforcement;
- independent evidence and package review;
- exact commit, revision and digest binding;
- expiration, stale evidence, cross-tenant and evidence-reuse denial;
- strict JSON, duplicate-key and sanitized-error behavior;
- bounded participants, actions, admitted fields, duration, stop and rollback scope;
- package edits invalidating pilot plans;
- default-deny operational authorization;
- no provider/network path and no execution-engine path; and
- preservation of the existing no-activation role boundary.

Passing tests establish only the behavior of these synthetic contracts. They do not
verify a future vendor, production configuration, contractual commitment, human
authority or confidential pilot. Purchasing, provisioning, deployment, data entry,
integration activation and pilot launch remain separate CEO decisions.
