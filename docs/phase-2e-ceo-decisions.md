# Phase 2E — CEO decisions required before implementation

[Assessment index](phase-2e-production-integration-readiness.md) ·
[Roadmap](phase-2e-roadmap.md) · [Security gaps](phase-2e-security-gaps.md).

**No decision is preselected or granted by this document.** Approved system roles
below are constraints supplied for this assessment, not approvals of a vendor
connection: HubSpot is the relationship/commercial record; Slack is communication,
not the operating system; the 2nd Brain is proposed approved institutional
knowledge, not operational truth. All seven connectors remain disabled.

## Decision register

| ID / proposed date | CEO decision needed | Recommendation for review, not authorization | Required co-owner / consequence if unresolved |
| --- | --- | --- | --- |
| D01 / Nov 13 | Name accountable human business/data/department, policy/security, identity, signing, encryption/secret, DB/recovery, operations/incident and independent review owners with backups | Record a real person for each responsibility, service window and delegated limit; document incompatible roles. Do not accept an unstaffed bot/“CEO handles everything” ownership model | Independent security reviewer and business owner; no relevant production action until staffing/SoD are workable |
| D02 / Nov 13 | Identity provider/product, tenant model, phishing-resistant MFA/step-up/recovery, session/revocation/service identity requirements | Approve contracts/offline verification first. Candidate human session idle 15m, absolute 8h, privileged 1h; step-up ≤5m; revocation ≤60s; service token ≤15m. Validate feasibility with selected IdP before committing these values | Identity/security owner; no real login/session implementation, credential or provider connection is authorized by this assessment |
| D03 / Nov 13 | Role/action/resource matrix, organizational approval/delegation limits, custody and independent review model | Separate authors, approvers, policy administrators, custodians and deployers; asymmetric managed signing and separate encryption custody are preferred design candidates. No shared CEO keys or universal service principal | Business/security/custody owners; unresolved authority blocks mutations and connector activation |
| D04 / Nov 20 | Managed versus self-managed PG, provider/tier/region/residency, budget, supported version/patch lifecycle, encryption/custody, RPO/RTO/availability and exit | Evaluate private managed PG against staffing/self-hosting burden; candidate RPO ≤15m/RTO ≤4h/99.9% production availability for sizing, not promise. Preserve the approved synthetic 17.11 workflow; separately qualify any production version | DB/recovery/platform owner + finance/privacy reviewer; no purchase/provision/hosting or availability claims until approved and measured |
| D05 / Nov 20 | Operating hours/on-call, incident authority/escalation, alert targets, durable audit custody and change/rollback ownership | Define a staffed window and independent security incident contact. Candidate security metadata retention: 90d searchable plus one additional immutable year; proposed PITR 35d, subject to legal/business review | Operations/security/legal owners; no admission when detection, retention or containment is unowned |
| D06 / Nov 20 | Lawful purpose, admitted fields/subjects, classifications, recipients/regions, legal holds, deletion/retention and vendor/model terms | Synthetic only until exact real-data policy and DPA/terms are reviewed; IDs/embeddings count as potentially confidential. No legacy-log migration or “sanitize by prefix” shortcut | Data/privacy/legal owner; no real contact, commercial record or knowledge admission while missing |
| D07 / Nov 23 | HubSpot account/product/API/plan, commercial owner and field/system-of-record contract; Slack workspace/channel purpose and product terms | Prioritize HubSpot read-only contract mocks. Keep writeback, Slack posting/history, email/calendar/documents/publishing off. Verify scopes/record ACL and terms before proposing any live sandbox | Commercial owner + security reviewer; no account access, webhook or real scopes without a separate explicit decision |
| D08 / before any integration implementation | Action-specific automation, durable intent/receipt/approval contract, idempotency, cost/volume/retry limits, kill switches, compensation and restart | Human approval for exact mutations; three transient retries only as a candidate bound; reconcile unknown outcomes; irreversible external sends/publishing require separate release policy | Integration/business/operations owner; no dispatcher or bypass of operational denial without independent implementation/activation review |
| D09 / Nov 13, confirm Nov 20 | Available engineering/reviewer capacity, supported OS/browser/accessibility needs, holiday availability, workload targets and Nov 30 success definition | One-engineer core scope: identity/control contracts, offline tests, runbooks and at most one HubSpot mocked projection. Reserve review/remediation; treat Nov 26–27 as reduced availability unless confirmed otherwise | CEO + named engineer/security/DB reviewers; de-scope mocks before reducing safety, do not promise full production readiness |
| D10 / after this plan review | Approve, narrow or reject the proposed next implementation branch; explicitly defer 2nd Brain implementation | Proposed `phase-2e/identity-session-contracts`, contracts and synthetic negative-test harness only; preserve local defaults and all seven disabled connectors. No real IdP, credentials, deployment, external call or 2nd Brain code | CEO + independent technical/security reviewer; branch is not created and implementation does not begin without separate authorization |

All dates are proposed decision targets in America/Chicago, not appointments,
service-level promises, purchase instructions or blanket permissions.

## Separate decisions that must never collapse into one approval

1. **Plan review:** accept the ownership, risk, priorities and acceptance design.
2. **Implementation scope:** authorize an exact branch/diff objective and data/test
   boundary. This assessment does not include that authorization.
3. **Isolated validation:** separately permit any provider sandbox/account/credentials
   and synthetic external traffic, with bounded cost/scopes and cleanup ownership.
4. **Confidential-data admission:** approve exact fields, purpose, people, tenant,
   recipients, legal basis/rights, retention and hosting/vendor evidence.
5. **Operational activation:** independently approve one connector/action/environment
   and a bounded pilot after all current gates and human/technical evidence pass.

A plan approval, API key, successful mock, vendor “connected” status, signed
technical artifact or readiness result cannot replace steps 3–5. Approval must bind
an exact reviewed commit/contract/evidence revision and a finite scope/expiry;
material changes return to review. The existing code's unconditional operational
denial is not removed or reinterpreted here.

## Proposed next branch scope, if independently approved

**Name:** `phase-2e/identity-session-contracts` (recommendation only).

In scope: role/subject/tenant/session/approval boundary contracts, threat-model
fixtures, mocked issuer/key/MFA/revocation/CSRF cases, exact-grant/self-approval
negative tests, compatibility proof for existing synthetic mode and readiness
reporting. Use the existing gateway/domain architecture; no second MC system.

Out of scope: production OIDC account/login deployment, real credential creation,
public/LAN binding, infrastructure purchase/provision, migration/admission of real
records, connector transport/activation, HubSpot writeback, Slack workflow authority,
2nd Brain export/index/embedding/retrieval implementation and confidential knowledge.
The 2nd Brain requires a later independent platform/provenance/ACL/retention and
implementation decision; the document connector is not a shortcut.

Next-branch review exit: exact new diff/inventory, actual executed test counts with
zero failures/errors/skips/expected failures/unexpected successes for its authorized
scope, no domain regression, no broadened data/identity/transport authority, full
cleanup, all seven connectors disabled, and a new CEO review. Do not commit/push
or activate anything under this Phase 2E assessment authorization.

## Current plan disposition

No technical planning blocker is concealed by these undecided choices. They are
explicit future implementation/production gates with accountable roles and due
windows. If evidence needed for an actual commitment cannot be obtained, keep that
commitment conditional or deferred. CEO review decides the next scope; it does
not retrospectively turn a synthetic proof into production authorization.

## M2 review: decisions remain unresolved

PR #16 delivered the authorized synthetic identity/session scope, not production
D02/D03 completion. The [M2 options and blocked statuses](phase-2e-storage-recovery-audit-design.md#decision-options-and-explicit-blocked-status)
retain D01/D03 ownership/custody, D04 hosting/recovery, D05 operations/audit,
D06 data/retention and D09 capacity/platform decisions. No person, provider, key,
region, budget, retention period or SLO is selected by these documents.
The [tabletop results](phase-2e-operations-tabletop.md#result-ledger-and-limitations)
are conditional design evidence, not human attestations or activation permission.

## M3 scope and unresolved decisions

The [fictional projection implementation](phase-2e-hubspot-mocked-projection.md)
uses only approved synthetic contacts/companies, existing read grants and M1
sessions. D01/D03 assignments/custody, D06 admission/retention, D07 commercial
fields/vendor verification and D09 review capacity remain unresolved. D02/D04/D05
and D08 production/delivery dependencies and C0–C6 remain blocked. This scope
creates no production role, permission, account or integration authorization.

## M4 decision reconciliation — M5 not issued

The [current evidence review](phase-2e-readiness-evidence-review.md#gap-triage-and-unresolved-ceo-decisions)
retains D01–D09 required choices, recommendations, consequences and blocked
production status. D10's initial branch proposal above is historical; the current
authorization is M4 documentation/evidence review only, not future implementation.
The [M5 checklist](phase-2e-readiness-evidence-review.md#m5-preparation-checklist--no-decision-issued)
prepares options for a later CEO decision without selecting one or assigning
people, approving production terms or granting operational authority.
