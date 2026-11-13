# Phase 2E — Prioritized roadmap through November 30, 2026

[Assessment index](phase-2e-production-integration-readiness.md) ·
[CEO decisions](phase-2e-ceo-decisions.md) · [Acceptance plan](phase-2e-acceptance-plan.md).

**This is a conditional plan, not implementation authorization.** All dates are
America/Chicago. As of Thursday, November 12, the horizon is Monday, November 30.
There are 13 weekdays inclusive; planning assumes reduced availability November
26–27 and no weekend work, leaving 11 nominal working days including today.
Confirm holidays/availability via D09. Today's review consumes capacity, so do not
sell eleven full engineering days plus unlimited review as guaranteed throughput.

## Capacity and realistic November outcome

Planning assumption, not a staffing claim: one available engineer, a named CEO/
business reviewer, part-time security/identity reviewer and a DB/recovery owner
with scheduled review time. No names, budget or availability are assumed approved.
If reviews/owners/decisions slip, preserve gates and reduce scope, not safety.
With this staffing, cap core follow-up work at roughly eight engineer-days with
three nominal days for coordination, regression and remediation. Estimates are
ranges; parallel work requires additional named people, not implicit capacity.

**Recommended committed outcome after separate approval:** a reviewed production
boundary/control contract and synthetic/offline identity/session negative tests,
a repeatable readiness evidence report, one HubSpot read-only projection contract
with mocked events/versions, and operations/rollback runbooks/tabletop evidence.
The current synthetic operator can already automate local start/check/read/stop;
it remains synthetic, loopback-only and disconnected.

**Do not commit to production by November 30.** Real IdP/MFA/session implementation,
private protected PG, durable independent custody/audit, witnessed hosted PITR/HA,
legal/data admission, real staffing and integration authorization are not yet
selected/proven. Vendor lead time and legal/security review are unknown. A mock
connector is not a production integration. No 2nd Brain implementation, live CRM
writeback, autonomous Slack actions, email/calendar dispatch or public publishing
belongs to the deadline commitment.

## Prioritized milestones and exit evidence

Every row after M0 requires a separate CEO-authorized branch/scope. No code,
services, credentials or vendor access are created during this assessment.

| Priority / window | Work and estimate | Dependencies / accountable role | Exit evidence and acceptance IDs | De-scope or no-go trigger |
| --- | --- | --- | --- | --- |
| P0 / M0 — Nov 12–13 | CEO review of this plan; name owners, choose scope, service window, classification and target assumptions | CEO D01–D10, security and business reviewers; no engineering activation | Signed decision register with explicit rejected/deferred options and next-branch scope; G01–G12 remain visibly unresolved until proven | No decision by Nov 13: retain assessment/contract-only outcome and rebaseline dates |
| P0 / M1 — Nov 16–18 | Identity/session/authorization contract and offline negative-test harness; 3–4 engineer-days including review preparation | D01–D03; identity/security reviewer; existing gateway/domain invariants | Threat model, server-owned subject/tenant grants, mocked issuer/key/MFA/revocation/CSRF tests, exact approval/revision tests; AT-01–04, AT-09; no real IdP account or login deployment | Missing independent authority/role/custody decisions: no production adapter; preserve existing synthetic mode and return to CEO |
| P1 / M2 — Nov 19–20 | Storage/recovery/audit/IR design and tabletop evidence; 1–2 engineer-days plus DB/security owner time | D04–D06; DB/recovery/operations owner; no hosting provision | Provider decision brief, scoped role/network/key design, RPO/RTO proposal, backup/restore/replay plan, redacted audit/alert/runbook cases; AT-05–08, AT-12–13 plan/mock evidence only | Vendor selection, budget, custody or staffing absent: no hosted proof or availability claim |
| P1 / M3 — Nov 23–25 | One contract-mocked HubSpot read-only projection plus mapping/replay/stale-data tests; 1–2 engineer-days, if M1 accepted | D07, commercial data owner, C0/C1 field/product verification and M1 contract; synthetic fixtures only | Source-of-record/property map, portal/tenant/merge/tombstone contract, mocked scope/duplicate/unknown-outcome/PII rejection tests; AT-08, AT-10–12, AT-15 | Any real field/admission/account dependency unresolved: deliver contract and fixtures only, not a live read; defer Slack mock before cutting safety work |
| P2 / M4 — Nov 26–29 | Protected review/contingency window; no assumed holiday/weekend changes | D09 staffing confirmation; security/CEO availability | Evidence triage, documentation and blockers; no unstaffed production change | No reviewed exception means no scheduled activation or migration |
| P0 / M5 — Nov 30 | Review actual results, regression evidence and open gates; 1–2 engineer/reviewer-days, use contingency as needed | Business/security/DB owners attest their own evidence; CEO decision | Exact discovered/executed/PG counts for later approved implementation; zero failures/errors/skips/expected failures/unexpected successes; updated evidence graph, rollback and disabled-connector checks; AT-16 | Any failed/unknown security or recovery gate: no launch; CEO approves narrowed follow-up, not a bypass |

The date windows are coordination targets; do not double-book a single engineer
for the top end of every range. Prioritize M1 and the readiness/control report;
M3 is the first item to become contract-only if capacity or review slips. A live
sandbox trial is **not** an assumed milestone. If later independently authorized,
it needs new time/budget and all relevant gates, not reuse of the mock schedule.

## What can be completed, tested and automated

| Capability by Nov 30 | Realistic status | Proof / explicit exclusion |
| --- | --- | --- |
| Current local synthetic start/status/check/open-disabled/stop demo | Already implemented in merged Phase 2D; may be reverified only under later test authorization | Local technical behavior, not production identity, external delivery or organizational authority |
| Architecture, ownership, seven-connector gates, threat/gap matrix, decision register, roadmap | Feasible in this assessment | Documentation and safe read-only validation only |
| Repeatable static readiness/evidence completeness reporting and offline regression checks | Feasible follow-up automation after implementation approval | Reports missing gates; never enables anything automatically |
| Identity/session/policy contract tests using synthetic keys/subjects/issuer fixtures | Feasible primary follow-up slice | Does not prove a chosen IdP, phishing resistance or enterprise offboarding works |
| One HubSpot field/mapping contract with fake read responses/events and deterministic conflict cases | Feasible conditional offline slice | No account access, personal records, real webhook or credential; no writeback |
| Minimal Slack notification formatting mock | Stretch only, after higher-priority acceptance | No posting/history access or workflow/approval execution |
| Isolated vendor sandbox read with approved synthetic data | Not committed; depends on new explicit authorization, vendor/owner/legal/identity/custody gates and capacity | No sandbox account, key, external connection or service activation in this phase |
| Production launch, hosted failover/PITR/security evidence, real confidential pilot | Not credible as an unconditional deadline commitment | Unknown provider/terms, independent custody, operating capacity and recovery cannot be papered over by mocks |
| 2nd Brain ingestion/indexing/retrieval/embeddings or confidential knowledge admission | Excluded | Separate later assessment/implementation authorization and product/ACL/provenance decisions required |

## Dependency order and critical decisions

Authority/roles → human/service identity and custody contracts → protected data and
operating design → approval/audit/recovery guarantees → per-connector contract →
separately approved isolated validation → separately approved admission/activation.
A connector deadline must not invert that order. Data-admission and vendor/legal
work can be reviewed in parallel but cannot be presumed complete.

Required early decisions: scope and owners by Nov 13; reviewable identity/role/key
contract by Nov 18; provider/operations decision brief by Nov 20; HubSpot field
contract by Nov 23. These are proposed decision dates, not granted authorities.
If unavailable, the Nov 30 deliverable is an honest blocked-gate plan and tested
synthetic contracts, not an enabled system. No external commercial commitment or
purchase is inferred from this schedule.

## Release, rollback and human review budget

Reserve independent review and a full regression cycle for each approved slice.
Freeze dispatch on denied/stale authority, unexpected destinations/scopes,
confidential content, audit loss, unknown commit or unreconciled restore. Retain
immutable technical evidence; never erase history to make a test appear clean.
A rollback is a reviewed containment/reconciliation plan, not automatic deletion
of external consequences. User-visible send/publication requires separate human
release authority even if all automation tests pass.

**Recommended next branch (not created):** `phase-2e/identity-session-contracts`.
Scope it first to reviewed contracts and synthetic negative tests, preserving all
existing local restrictions. See D10 before beginning any implementation. The
2nd Brain is explicitly excluded from that branch.

## Sequence status after PR #16

M1 synthetic identity/session contracts are merged at
`4f8adb93b1931f06c5819a02779b9107c1f30c8d`; real identity/MFA and custody
remain unverified. M2 is now documented in the
[storage/recovery/audit design](phase-2e-storage-recovery-audit-design.md) and
[tabletop ledger](phase-2e-operations-tabletop.md), pending CEO review.
This does not close production gates or authorize M3. November windows remain
conditional planning targets; no dates, owners or operational SLOs are granted.

## M3 synthetic implementation review

After merged M2 PR #17 at `79ab81bdb7edb37ca106b36bfb4bbd148cf348b9`, the
[M3 contract](phase-2e-hubspot-mocked-projection.md) implements only the conditional
fictional contact/company slice. No live read or deal/lifecycle properties are
included. Dates remain conditional; vendor/admission/custody gates are not closed.
