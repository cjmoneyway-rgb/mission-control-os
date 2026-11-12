# Phase 2E — Future acceptance, automation and rollback test plan

[Assessment index](phase-2e-production-integration-readiness.md) ·
[Gap assessment](phase-2e-security-gaps.md) · [CEO decisions](phase-2e-ceo-decisions.md).

**Planned tests, not executed here.** This assessment performs only read-only
source/metadata/document checks. It does not start the operator, tests, browser,
PostgreSQL, provider sessions or vendor connections. These cases need separately
approved implementation and test-environment scopes before execution. Synthetic
mocks, isolated vendor sandbox proof and production operating evidence are three
different evidence levels; none may be substituted for another.

## Required evidence format and result policy

Each case binds the exact reviewed commit/build, environment/tenant/account,
contract and policy revisions, sanitized fixture IDs, operator/reviewer, execution
time, expected/actual outcome, minimized evidence digest and expiry. Record all
actual discovered/executed/offline/PostgreSQL/browser counts without forcing a
historical count. Require zero failures, errors, skips, expected failures or
unexpected successes for each authorized release slice, and prove every discovered
test executed. Unsupported/unrun production features are **unverified**, not green.

Keep secret values, full payloads, directives, approval evidence, cookie/session/
CSRF/IdP tokens and confidential provider outputs out of transcripts. Retain
reference-only audit evidence. Synthetic keys may be created only within a later
approved test scope; no real key/account/data is needed for this assessment.

## Acceptance matrix

| ID / owner | Positive and negative cases in later approved environment | Required pass criterion |
| --- | --- | --- |
| AT-01 Identity/MFA — identity/security owner | Allowed verified issuer/audience/subject and individual MFA; wrong issuer/audience/tenant/algorithm, unsigned/tampered/expired/not-yet-valid tokens, nonce/state/PKCE replay, unknown/stale key, IdP outage, missing/old MFA, enrollment/recovery bypass, offboarded account and service→human impersonation | Only verified current identity is admitted; all negative cases deny before domain work; actual IdP assurance/recovery/offboarding evidence needed beyond mocked claims |
| AT-02 Session/transport — security/platform owner | Secure HttpOnly/SameSite session, CSRF/origin/Host, fixation/rotation, logout/revocation, cross-tab/concurrent sessions, browser-supplied roles/tenant, forwarded-host spoofing, TLS validation and callback handling | No browser token/storage/URL leak; every mutating request reauthorized; proposed idle 15m/absolute 8h, privileged 1h and revocation ≤60s are D02 candidates, not approved constants. Any OIDC correlation-cookie exception is separately reviewed, not a blanket weakening of the authenticated-session cookie |
| AT-03 Authorization/SoD — policy/business owner | Exact resource/department/tenant access, deny precedence, expired policy, owner changes, cross-tenant direct-object access, writer self-approval, privileged-role combinations, delegation beyond limits, approver revoked after preparation, new revision after approval | Denied request makes no domain mutation and leaks no protected values; exact approved revision/fields/recipient required; one actor cannot author/approve/deploy own authority change |
| AT-04 Custody — signing/encryption custodians + independent witness | Per-environment keys, signature verification after restart/rotation, revoked/unknown key, separate signing/encryption/service access, vault outage, credential rotation/expiry, dual-controlled recovery/deletion, no secret in source/log/browser | Historical permitted verification remains possible; wrong/expired authority fails closed; no key material export or self-grant; real selected custody service must later be independently tested |
| AT-05 PG isolation/transactions — DB owner | Nonprivileged runtime versus migration/restore roles, forced RLS/tenant grants, pooled connection reuse/reset, SQL injection inputs, unauthorized schema/admin access, CAS/idempotency, statement/deadline cancellation and concurrent transactions | No cross-tenant state or runtime privilege escalation; failed mutation fully rolls back; exact current policy/evidence rechecked; original synthetic regression suite preserved on approved 17.11 workflow plus any separately proposed production version |
| AT-06 Storage/backup/recovery — DB/recovery owner + witness | Private network/TLS/encryption, backup/PITR key availability, complete archive/schema coverage, independent checkpoint integrity, isolated point-in-time restore, replica promotion and post-restore policy/receipt reconciliation | Measured RPO/RTO against D04-approved targets, no unauthorized data or re-dispatch, witnessed readable recovery and rollback; failover alone is not restore proof and JSON export alone is not PITR |
| AT-07 Audit/monitoring — security/operations owner | Allowed/denied requests, privilege/approval/key changes, preflight attempts versus committed outcomes, audit sink outage, queue age/unknown results, backup staleness, rate/cost anomaly and incident alert routing | Durable restricted evidence without payload/secret leakage; missing required audit denies relevant work; all alerts reach named responders within D05-approved thresholds; no claim of success for an uncommitted attempt |
| AT-08 Data admission/retention — data/privacy owner | Whitelisted fields and purpose; PII/commercial notes in supposedly opaque fields, unexpected nested values/attachments, prohibited/unknown classification, extra properties, consent/rights/region/recipient mismatch, legal hold and deletion requests | Reject before unauthorized collection/persistence/outbound processing; approved field/recipient/retention policy required even for reads; log/telemetry redaction verified; legacy logs unchanged and never imported |
| AT-09 Human mutation gate — business approver | Explicit confirmation, synthetic/real mode distinction, server-issued request ref/idempotency/expected revision/CSRF, missing checkbox/confirmation, double click, back/refresh, stale dependencies and policy/approval revoked between review and commit | Exact eligible action only, no duplicate mutation, no self-approval, server reauthorization at final commit; technical validation/model confidence/chat reaction never counts as approval |
| AT-10 Connector perimeter — connector/security owner | Each of seven disabled descriptors, denied default transport, unknown scopes/destinations, account/tenant confusion, provider redirects, authenticated webhook tampering/replay/order/duplicates, malformed/oversized/invalid-UTF8/duplicate-key/nonfinite input and rate limit | Disabled means zero outbound calls, including on retry/error/startup; sandbox actions limited to exact reviewed scopes/account/fields; rejected source cannot select policy, identity or transport |
| AT-11 System-of-record/knowledge — commercial/content owner | HubSpot field ownership and merge/delete/association changes; Slack message/reaction as attempted approval; stale/contradictory knowledge, forged provenance, prompt injection and unauthorized source ACL | External facts become authorized observations/proposals only; no direct policy/lifecycle write; protected citations fail closed on revocation/expiry. 2nd Brain cases remain schema/threat-model fixtures, not an implemented connection |
| AT-12 Delivery/reconciliation/rollback — operations/integration owner | Failure before commit, after domain commit/before enqueue, after enqueue/before send, external success/ack loss, worker crash/lease reuse, concurrent retries, 429/outage, revoked approval before dispatch, restore to before external acknowledgment | Atomic future domain+intent boundary, stable dedup, fencing, bounded retries, unknown-outcome quarantine and external receipt reconciliation; no blind replay or exactly-once claim; independent human approves compensation/restart |
| AT-13 Incident/operations — incident commander | Compromised key/user, wrong audience, tenant leak, audit loss, provider outage, DB loss, host failure, recovery-key loss and unstaffed operating window | Contain admission/dispatch; page named owners; preserve minimized evidence; rotate/revoke only under authority; isolated recovery plus separately approved restart; measured stop/response targets and cost limits |
| AT-14 UI/platform/accessibility — UI/security owner | Whole warning at 320/360/375/390px and wider, 200% zoom, landmarks/labels/tables/live status, keyboard/visible focus/skip/Escape/Cancel/confirmation, screen reader, reduced motion and supported OS/browser | No page overflow or hidden warning, no keyboard trap or lost logical focus, status not color-only, manual AT evidence and explicit supported-platform matrix; local synthetic limits remain intact |
| AT-15 Deletion/propagation — records/content/commercial owner | External ID merge/tombstone, source ACL revocation, hold versus erase, knowledge chunks/embeddings/cache/vendor copies, backup retention and recipient scope change | No widened ACL/stale answer; approved propagation/revocation window met and evidence recorded; preserve legally required minimized audit without rewriting legacy logs; unresolved vendor erasure capability blocks admission |
| AT-16 Release/readiness — independent reviewer + CEO | Bind all twelve current control artifacts to exact commit/revisions/digests/owner/reviewer/validity; alter/reuse/expire one item; dependency/admission/rollback owner missing; scope change after signing | Every missing/stale/mismatched gate denies activation. Separately approved implementation, sandbox, confidential admission and production activation decisions remain distinct. CEO signs bounded actual operating scope, never merely a passing test report |

## Future automation contract and measurable limits

Proposed limits require D02/D05/D08 approval before implementation: no automatic
business approval; at most three transient retries with capped exponential backoff
and jitter; no retry on denied policy, invalid schema, changed recipient or expired
approval; concurrency/volume/cost per connector/account bounded by a reviewed
budget. Unknown commit/ack is quarantined until authorized reconciliation resolves
it. Disabling a connector or revoking a credential blocks new sends immediately
at dispatch; queued actions are not grandfathered into approval.

Before any real action, benchmark against a declared workload and record p95
latency, saturation, queue age, dependency failures and DB/connector timeouts.
An initial sizing proposal is a 30-minute run at twice the approved expected peak;
exact throughput/latency and error budgets remain D09 decisions. No synthetic
single-user result establishes production capacity or availability.

Webhooks require the selected vendor's current signature algorithm/canonical input,
clock skew, replay retention and rotation behavior verified before implementation.
No invented generic header proves a vendor event. Provider acknowledgment proves
only that provider's receipt, not organizational authorization or actual business
completion. Requested, accepted, dispatched, acknowledged, reconciled and domain
outcome are distinct states and auditable references.

A future durable outbox must be part of an approved transaction/schema/archive
contract, not an extra in-memory queue bolted onto current intentions. Bind tenant,
source and recipient account, action, field/destination digest, expected revision,
authorization/evidence revision, logical idempotency key, approval expiry and
minimal encrypted payload reference. Before dispatch recheck current policy,
classification, recipient, dependencies, approval, secret and kill switch.

## Rollback and failure matrix (future drill)

| Failure boundary | Safe expected behavior / recovery | Human approval boundary |
| --- | --- | --- |
| Validation/auth/audit fails before domain commit | Deny; roll back; no intent or external send | New request only after corrected evidence and authorization |
| Domain write commits but client loses acknowledgment | Read/retry via original receipt/idempotency; do not claim it never happened | Reconcile status; do not create a second unrelated mutation |
| Future delivery lease expires or workers race | Fence stale worker; dedup by tenant/action/target key; pause on uncertain ownership | Operator adjudicates conflict with minimal evidence |
| Vendor accepts but ack/receipt persistence fails | Mark unknown, query/reconcile if vendor permits; never blind retry where safe dedup is unavailable | Owner approves corrective/compensating action; cannot promise exactly once |
| Approval, recipient, policy or classification changes | Stop pending dispatch, require new exact approval; do not silently edit a queued payload | Correct owner and independent approver review the new scope |
| Wrong-recipient email/publication or irreversible vendor mutation | Contain further sends, preserve evidence, invoke incident/notification and correction process | Retraction/deletion cannot guarantee undo; independent legal/business decision required |
| Database restored to earlier state | Keep dispatch disabled; compare external receipts/delivery watermark and audit before replay | Independent restore witness and business/integration owner approve reconciliation and restart |
| Credential compromise/IdP outage/audit loss | Deny new work/dispatch, scoped revoke/rotate, preserve evidence and protect backups | Incident authority is bounded containment, not business approval; new human restart decision |

No rollback deletes append-only history, approval/audit evidence or legacy logs to
make a demonstration look clean. External compensating writes are separate new
mutations with their own approvals. Keep original receipts, negative outcomes and
correlation so a restore cannot resurrect an already-delivered action unnoticed.

## Future release evidence and current-phase boundary

Later implementation verification must execute every existing and new offline and
PostgreSQL test on the approved disposable pattern, plus selected hosted/provider
proof only under separate authorization. Record actual counts and zero unexecuted
cases; do not convert required failures to skips or label mock tests as hosted
proof. Include browser/manual accessibility, dependencies/SBOM, schema/archive,
link/path, leakage, whitespace, cleanup and seven-disabled-connector checks.

For **this assessment**, these are planned cases only. Safe read-only validation
is Git ancestry/tree checks, source/AST/JSON/Markdown inspection, connector metadata,
process/listener/container/file-presence checks and documentation consistency.
No operational test evidence, production credentials or confidential samples are
created. The final review separates current static validation from future execution.
