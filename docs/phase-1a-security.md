# Phase 1A security boundaries

This sanitized change extends the existing CLI. It does not configure operational
routing, personnel, confidential records, integrations, or a second system.
Baseline: ae478186c5029dda496ee642a1e96b027a1b06ee.

## Delivery and validation

A failed final technical governance check raises `BlockedExecution`. No record or
rejected output is attached to that exception. The CLI returns 1 with empty stdout
for blocked or invalid execution, including JSON mode. Audit-write errors also
prevent delivery. Successful CLI output remains visible locally and `--json`
contains the full successful response: do not use confidential input in an
unprotected terminal or downstream capture.

Technical checks validate shape and constrained values. They do not establish
truth, organizational permission, privacy compliance, or publication authority.
The existing summary-label and secret-pattern checks remain limited heuristics.
A technically successful response is not an organizational approval.

Department projections require exact fields and nonempty text/keywords. Routing
results require the typed contract, finite confidence in [0,1], and a configured
department. All application JSON input boundaries reject duplicate keys at every
nesting level and nonfinite constants. Live routing JSON does not coerce strings or
booleans into numbers.
The public legacy catalog is a demonstration projection, not an approved registry.

## Approval and registry foundation

Registry records default to draft. Active records require resolved department,
title, owner, and policy references, approval for the exact ID/revision/content
hash, and a trusted approval authority. No authority is configured by default.
The injected `ApprovalVerifier` must resolve the evidence reference to typed
`ApprovalEvidence` with matching approval identity, explicit authorization, and a
current timezone-aware validity interval. Missing, unresolved, expired, revoked,
mismatched, malformed, or unavailable evidence fails closed. The same authority
must affirm existence of each department/title/owner/policy reference. An
approval supplied even on an inactive record must be verifiable.
Changing content or revision invalidates the prior approval. Hashes bind contents;
they are not signatures or proof of who approved them. Evidence must be resolved
against a trusted authority, not a user-supplied flag.
Only synthetic authority implementations are included in tests. Connecting an
authenticated operational authority remains outside Phase 1A.

These contracts provide validation, not a registry service or activation endpoint.
The engine continues to use its existing demo catalog; it does not load or activate
confidential registry records. Work packets and lifecycle events remain inactive.
Generic synthetic transitions are new -> received -> prepared -> completed; they
are test scaffolding, not an approved business lifecycle. Journey history exposes
an immutable tuple of frozen events and appends accepted events. Duplicate IDs,
stale previous states, missing references, and revision mismatches are rejected.
History is in memory only: restart durability, cross-worker idempotency, and
transactional concurrency require a protected persistence design.

## External provider boundary

Mock mode remains the default. The engine checks authorization AND sensitive-data
clearance before every custom/injected provider classification, execution, and
revision call. Provider names, subclasses, or self-declared offline attributes
cannot opt out. Only the exact internally created deterministic mock is exempt;
a caller-injected mock is gated too. Replacing the engine provider after
construction does not preserve an offline exemption. Engine clearance reviews the
operation, directive, complete passed department projections, and revision feedback.
A malformed, missing, denied, or failing gate blocks the provider before invocation.

In addition, every OpenAI classification, execution, and revision
request passes its exact outbound model/instructions/input to a trusted caller's
safety gate before the SDK transmission. A `SafetyDecision` must explicitly clear
both authorization and sensitive-data review; missing, malformed, or denied
clearance blocks the call. An API key alone never authorizes transmission.
The ordinary CLI exposes no approval override and live mode is therefore blocked.
Do not replace this boundary with a production always-allow callback.

Evidence verifiers and safety-gate callbacks are trusted application dependencies,
never accepted from record payloads. Provider objects receive data only after
engine clearance, but executing arbitrary Python code is not sandboxed: a provider
constructor or malicious code with access to engine internals is outside this
boundary. No operational provider or integration is authorized by these contracts.
No external service was contacted during validation.
An authenticated review implementation remains future work; this phase does not
claim to automatically identify every category of sensitive information.

## Audit minimization and retention

New default audit lines include only opaque execution IDs, timestamps, technical
status, authorization disclaimer, schema revision, revision count, and finding
count. No directive, output, provider-generated rationale, department projection,
or rejected content is written. Diagnostic errors avoid raw provider responses.
`include_route=True` is an explicit opt-in for public/synthetic route IDs only; it
must stay disabled for confidential identifiers. `--no-log` still disables logging.

`JsonlAuditLog(retention_days=None)` imposes no invented deletion schedule.
For a positive configured day count, explicit `purge_expired()` now refreshes a
SEPARATE derived view at `<source>.retained.jsonl` and returns source, retained,
and expired counts. Despite the historical method name, it never deletes,
truncates, replaces, reorders, or rewrites the authoritative source audit. It does
not reclaim storage or enact an enterprise deletion policy. Existing callers
expecting destructive purging must adapt. Appends do not trigger retention.

A stable owner-only sidecar lock coordinates appends and retention across processes
and threads on local POSIX filesystems. Maintenance holds the same exclusive
`flock` through snapshot validation and view publication. All writers must use
this API; advisory locks cannot constrain unrelated tools. Noncooperating appends
still cannot be lost through retention, because source records are never replaced.
The view is a point-in-time snapshot; later appends appear on the next refresh.
POSIX locking and atomic rename are required; unsupported platforms fail closed.
Symlink audit paths are rejected. Do not delete or rotate a live lock sidecar.

Every source row is parsed with duplicate-key rejection before creating the view.
Legacy/unknown schemas are refused, with source and previous view unchanged.
Retained rows preserve their original bytes and order. A unique owner-only staging
file is flushed and fsynced before atomic view replacement, followed by directory
fsync. Source access permissions are never broadened in the new view. Ordinary
failures and catchable interruptions clean staging files; abrupt process death
may leave an owner-only staging file, but not a partial published view. The OS
releases the lock on process death. Such leftovers need authorized inventory, not
automatic broad deletion. A sync failure after replacement may mean the complete
view was published despite an exception; the source remains intact in every case.
Power-loss durability still depends on filesystem guarantees. Local JSONL is not
a tamper-resistant or transactional enterprise audit service.

Redaction is an allowlist, not regex-based concealment of a full payload. There is
no opt-in to log raw directives or outputs through this audit implementation.

Existing logs are not migrated or sanitized automatically. Earlier demo logs may
contain complete records. Keep them out of version control and apply an authorized
migration/disposal process before confidential use. Filesystem access controls,
backups, terminal captures, and environment snapshots need separate protection.

## Unresolved decisions and next phase

Canonical titles, ownership assignments, visibility permissions, approval gates,
approving authorities, data classification rules, retention duration, and external
provider processing permission remain UNRESOLVED. No values are inferred here.

Before confidential implementation, use a protected operational data store with
authenticated access, least privilege, encryption, audit controls, backups, and
approved retention. A private repository may hold confidential design and reviewed
policy definitions; it is not sufficient as the operational registry store.

Recommended next phase: review these controls, choose the protected store and
identity/evidence authority, and specify transactional event persistence and
policy enforcement using synthetic data. Real data, integrations, operational
activation, and any pilot require separate authorization. No merge, deployment,
environment publication, integration connection, or pilot is part of Phase 1A.

## Validation

Run from the existing checkout (no additional worktree needed):

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m pip check
.venv/bin/python main.py --demo --no-log
```

All tests use synthetic data or the existing public demo. Original tests remain;
the audit-routing test explicitly opts into synthetic route metadata, injected
test providers explicitly obtain synthetic engine clearance, and the fake SDK
contract test explicitly supplies synthetic transmission clearance. No live API calls
are required or authorized by the tests.
