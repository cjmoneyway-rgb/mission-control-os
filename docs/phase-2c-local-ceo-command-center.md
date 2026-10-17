# Phase 2C — Local CEO Command Center Interface

Baseline: `c56c3ad09088a7b2a45fdc8da67ba1cc1ae73ccb`.
Branch: `phase-2c/local-ceo-command-center`. All work stays unstaged and uncommitted.

This is a synthetic, disabled-by-default local browser presentation layer. It is
**not production-ready** and provides no operational or organizational authority.
The CEO-authorized corrective contracts now supply all six governed queues and
server-calculated eligibility. Unknown values remain explicit. Technical success
and synthetic eligibility do not grant organizational or operational authority.

## Purpose and architecture

[Repository-native HTML, CSS and JavaScript](../mission_control/command_center_assets/index.html)
present the existing minimized gateway responses. No frontend framework, build
system, remote asset, model call, analytics, WebSocket, browser extension or service
worker is used. [The UI server](../mission_control/command_center_ui.py) separates
browser sessions, CSRF/confirmation admission and trusted fixture selection from
[the unchanged Phase 2A gateway](../mission_control/connection_gateway.py) and
[domain services](../mission_control/connection_services.py). It subclasses the
[unchanged Phase 2B HTTP server](../mission_control/local_http.py), inheriting its
socket deadlines, parser limits, logging suppression and loopback peer checks.
Its separate browser handler admits only the routes documented below. The original
Phase 2B bearer routes and their Host/Origin/cookie denial are byte-unchanged.
The corrective work extends only the existing Phase 2A connection contracts and
services. Phase 1 modules, all migrations, the gateway and Phase 2B transport are
unchanged. All earlier test assertions remain; the recording double now exposes
the new service methods, and one timeout fixture applies its short deadline only
to the operation under test, not to setup.
The browser never accesses PostgreSQL. There is no second registry, lifecycle,
routing, governance, authorization, readiness engine or audit store.

The trusted startup code supplies bounded synthetic read/action envelopes. The
server verifies their identity and policy before binding a socket; envelopes are
not browser-provided. Read candidates are reauthorized through the gateway every
time. Denied objects and their identifiers are omitted, not rendered or counted.
The server only counts authorized visible views. The original OpenAPI contract
remains unchanged; the routes below are private browser protocol, not operational
APIs. No operational connector or outbox transport is added.

## Governed six-stage operating model

Every response contains the exact ordered queues INFORMATION → INTELLIGENCE →
DECISION → ASSIGNMENT → EXECUTION → MEASUREMENT. Each queue contains its authorized
items, exact item count and exact blocked count. These are record facets, not
exclusive workflow states or a relabelling of the existing 16-stage podcast pilot.
A journey can have records in multiple queues. Accepted historical proposal
records remain visible as accepted; a queue count is not described as an exclusive
organizational backlog or an assertion that an operational activity happened.

| Stage | Existing protected source |
|---|---|
| INFORMATION | Authorized journey/intake, immutable original classification and head revision |
| INTELLIGENCE | Latest protected proposals, minimized advisory state and prerequisites |
| DECISION | Same authorized proposals viewed for technical approval/decision state |
| ASSIGNMENT | Current linked inactive packet revisions |
| EXECUTION | Current linked inactive packet technical state; no operational execution |
| MEASUREMENT | Current authorized packets with synthetic outcome references |

The service first resolves current identity and policy, enumerates exact permitted
journey-read grant candidates, and authorizes each before a target query. It never
scans hidden journey rows or reports denied/total counts. Packet fields require
separate exact packet-read authorization. Explicit deny wins. Tenant-scoped runtime
transactions/RLS and persisted policy checks remain authoritative. Aggregates are
computed after authorization from the exact projected items. Blocked counts include
blocked technical disposition, unresolved dependencies or unresolved technical
approval. Risk remains explicitly unresolved when no protected risk decision exists;
it is never inferred from names, priority, or lack of data.

Each item has exactly: reference, current_stage, original_classification,
owning_department_reference, priority, technical_status, dependency_state,
risk_state, approval_state, assigned_owner_reference, next_required_action,
outcome_evidence_reference, revision, last_authorized_update, history_references.
No raw payload, fact, approval evidence, policy, confidential name, tenant identifier,
provider output or rejected content is included. All unavailable nullable fields
are explicit null/Unresolved, never invented values. The validator rejects extra
fields and inconsistent counts. A bound of 128 items per queue and 32 KiB total
fails closed rather than silently omitting records while claiming complete counts.

A responsible owner/next action is exposed only with separate executive-view
permission, a human session and an existing executive-parent binding to that exact
subject. Command visibility alone never grants owner information. Outcome references
require authorized journey and exact packet read. History contains only existing
append-only event references, in sequence. Original classification comes from the
validated immutable journey. Proposal and packet revision timestamps come from
existing protected created_at records. If a journey head advanced without an
available authoritative update timestamp, its update time remains null rather than
substituting request time or intake creation time. No migration or parallel store
is needed; the existing 34 tables remain intact.

Readiness continues to use only an existing readiness assessment when explicitly
installed. Missing readiness evidence displays Unresolved and never grants launch.
The [OpenAPI document](phase-2a-openapi.json) documents the new internal projection
schemas as browser-only contracts; no public/operational endpoint is added.

## Identity, sessions and CSRF

The Phase 2B `SyntheticBinding` stays process-local. Its bearer token is never
sent to HTML, JavaScript, URLs, browser storage, application logs or response JSON.
No browser-supplied identity, tenant, role, authorization or approval claim is
accepted. Every use is rechecked against the installed synthetic policy gate.
There is no login, password, OAuth, SSO, MFA or production identity simulation.

A direct visit to the shell issues a random 256-bit local session cookie named
`mc_ceo_session`, with HttpOnly, SameSite=Strict, Path=/command-center and a maximum
300-second lifetime. There are at most 16 live sessions. Sessions do not persist,
do not renew on API requests, and are invalidated on shutdown and close. Unknown
or expired API sessions are denied; navigating to the shell may establish a new
local fixture session. Secure is unavailable over this plain localhost HTTP
binding. This is one reason it is unsuitable for production. Any program with
access to the local listener may obtain the explicitly installed synthetic fixture
session; the cookie is not a human-authentication mechanism or a security boundary
against malicious local software.

The overview returns an independent random 256-bit session CSRF value. It is kept
only in JavaScript memory. Prepare requests require it plus an admitted opaque
action reference. Confirmation uses a different random one-use CSRF value bound
to the server-held intent, request reference, idempotency key, expected revision,
60-second expiry and local session. Exact same-origin Origin is mandatory for both
POST routes. Session isolation, expiry and policy are checked again. Duplicate,
expired, cross-session, unconfirmed, altered-revision or altered-key confirmations
fail closed. A confirmation is consumed before gateway dispatch, including errors
or uncertain commit outcomes. Replays return conflict and never run domain work.

## Confirmation rules and supported actions

The page initially performs only reads. Selecting an action merely requests a
server-side eligibility check. The confirmation dialog displays requested action,
opaque target, exact revision, owning department reference (Unresolved for intake),
resolved dependency state without protected dependency references, technical consequences and the synthetic/inactive warning.
The checkbox “I understand this is a synthetic, inactive action.” and explicit
Confirm synthetic action button are both required. Native modal behavior, keyboard
focus and a cancel button keep the confirmation accessible.

Only preinstalled actions in the existing Phase 2B route table are considered.
The existing PhaseOneServices now exposes a strict eligibility query with only
opaque target reference, requested action, eligible boolean, sanitized blocker
codes, expected revision, evaluation time and schema revision. Browser-supplied
eligibility, roles, tenants, domain payloads and approvals are rejected.

Eligibility uses a rollback-only rehearsal of the existing service implementation:
current identity/policy, protected dependencies, routing and event approval checks,
revision/CAS and deferred SQL constraints are checked; no commit is requested.
All trial writes and transactional audit rows roll back. No alternate mutation
engine, grant, approval or durable UI store is introduced. Dependencies must be
accepted existing journey events; unknown references fail closed. Proposal eligibility
requires current routing prerequisites, not an approval of the proposal being
submitted. Packet creation requires separately issued exact event approval.
Acknowledgment, handoff and outcome actions retain existing executive ownership,
append-only packet, rule/approval, tenant and revision checks.

The overview disables ineligible action options, but this is only a usability aid.
Prepare rechecks eligibility; confirm obtains a new current evaluation immediately
before dispatch. Missing, malformed, stale, denied, timed-out or failed evaluations
cannot authorize a mutation. UI-originated mutations also repeat the prerequisite
gate inside the actual service transaction, retaining commit-time policy/evidence
rechecks. A displayed eligible state is never an approval capability. All allowed
existing synthetic intake/proposal/packet/acknowledgment/handoff/outcome operations
can be confirmed when their real prerequisites are satisfied, and remain inactive.

Double clicks are guarded in JavaScript and at the server. Repeated prepare calls
reuse the same unexpired intent; used intents cannot generate new action keys in
the session. Refresh and navigation do no mutations. A missing response may leave
an uncertain commit; the server does not offer a new intent as an automatic retry.
Existing domain idempotency remains authoritative and is regression-tested.

## Browser-only routes

| Method and route | Admission and purpose |
|---|---|
| GET /command-center | Exact Host, trusted direct/same-origin navigation, create/reuse ephemeral local session; public static shell contains no domain data |
| GET /command-center/app.css or /app.js | Exact asset allowlist and existing session; no dynamic content |
| GET /command-center/api/overview | Session and current policy; existing authorized projections, minimized counts and session CSRF |
| POST /command-center/api/prepare | Exact Origin, session, JSON, session CSRF, exact `action_reference` and `csrf_token` fields; server eligibility check only |
| POST /command-center/api/confirm | Exact Origin, session, JSON; exact `request_reference`, `idempotency_key`, `expected_revision`, `csrf_token`, `confirmed` fields; reauthorized existing gateway action |

GET bodies, query strings, percent escapes, fragments, extra routes, forwarding
headers, browser Authorization headers and methods other than GET/POST are denied.
No credential, connector, external webhook, organizational approval or delivery
route exists. Phase 2B API routes are not exposed by the UI handler.

## Localhost, transport and content controls

Startup requires `synthetic_development=True`, a configured exact Gateway,
SyntheticPolicyGate, SyntheticAuthority, services, audit sink, rate limiter,
SyntheticBinding and explicit fixture candidates. The UI binds only literal
127.0.0.1, on port zero by default. It rejects localhost/DNS names, 127.0.0.2,
IPv6, wildcard, LAN and public addresses before creating a socket. Import, ordinary
CLI use, installation and test discovery do not start it. Tests explicitly install
synthetic fixtures and opt in to ephemeral listeners.

Host must match the exact bound address/port. Cross-site requests are rejected.
Only initial direct GET navigation may use `Sec-Fetch-Site: none`; asset/API calls
must be same-origin when that header is present. No CORS allowance is emitted.
JSON requires application/json, optionally charset=utf-8; strict UTF-8, duplicate
keys, nonfinite values, unknown fields, oversized bodies/headers, encodings,
framing and methods are rejected. The request ceiling is 64 KiB; parsed headers
are limited to 8 KiB with inherited stdlib line/count limits. Responses/assets
are capped at 64 KiB. Freshness and exact schema/revision/idempotency validation
remain at the existing gateway.

The inherited absolute input and socket timeouts apply. Gateway cancellation is
cooperative through the existing LocalContext and precommit budget checks; SQL
retains its existing statement/lock timeouts. Arbitrary blocking trusted Python
callbacks cannot be forcibly terminated. No production hard deadline or guaranteed
rollback after a lost response is claimed.

All dynamic browser values use textContent/native text nodes, never raw HTML,
attributes, CSS or URLs. Backend projections are checked against the existing
reference-only ceiling, required response fields and request bindings. Malformed
service output fails closed. Unknown fields and injection-shaped browser input
are rejected. Errors contain stable sanitized codes/messages, no rejected bytes,
exception text or stack traces. HTTP request/error logging stays suppressed; only
existing minimized gateway/domain audit metadata is written. Session identifiers,
CSRF values, bearer tokens, pages and browser payloads are not audited.

Headers include no-store, Pragma no-cache, nosniff, no-referrer, DENY framing,
same-origin resource policy, restrictive Permissions-Policy, and CSP with
default-src 'none', self-hosted scripts/styles, connect-src 'self',
frame-ancestors 'none', base-uri 'none', form-action 'self'. There are no inline
scripts, remote fonts/images, CDN assets, service workers, browser storage or
external requests. All seven connector descriptors remain disabled/unresolved.

## Accessibility and usability

The restrained charcoal/white/gold page has semantic landmarks, one page heading,
logical sections, a skip link, native labelled controls, fieldset/legend, table
captions/scoped headers, visible focus, textual status and polite live regions.
Errors are connected to the action control, and status receives focus after an
error or confirmation result. The native dialog starts at the checkbox and supports
Tab, Escape and Cancel; no inaccessible custom control is introduced. Refresh is
explicit. Reduced motion is honored. Responsive CSS supports narrow layouts and
200% layout zoom; table overflow is contained in its own scroll area.

Automated checks cover structure, stage order, focus styles, actual Chromium
keyboard confirmation, disabled confirmation before acknowledgment, focus return,
visible text contrast, 360px layout, 200% layout zoom, reduced motion, escaping,
empty/loaded/blocked states, cookies and absence of external requests/storage.
These checks target WCAG 2.2 AA behavior; they are not a conformance certificate.
**Manual screen-reader/assistive-technology review remains required before
production or confidential use. It is not a blocker to this synthetic review
when automated/keyboard checks pass and limitations remain documented.** No production accessibility claim is made.

## Reproduction, startup and shutdown

Use the existing isolated checkout; do not create a worktree. Python 3.12,
repository development dependencies, Docker, and the already available reviewed
PostgreSQL 17.11 image are needed. The browser check additionally uses the
execution environment's existing Node Playwright and /usr/bin/chromium; there is
no frontend runtime/build dependency or automatic download.

From the repository root:

```sh
/tmp/phase-2b-venv/bin/python -m pip check
/tmp/phase-2b-venv/bin/python -B -m unittest tests.test_command_center_ui -v
/tmp/phase-2b-venv/bin/python -B scripts/demo_command_center.py --synthetic-development
/tmp/phase-2b-venv/bin/python -B scripts/demo_command_center.py --synthetic-development --browser-check
/tmp/phase-2b-venv/bin/python -B scripts/local_postgres_tests.py
```

If the venv is absent, create an external development venv and install
requirements-dev.txt using the repository's normal setup. The demo and complete
suite use the existing digest-pinned PG 17.11 image and a disposable network-disabled
container, private /tmp Unix sockets, non-root UID, read-only passwd and UTF-8
initialization. The container is a temporary test fixture, not provisioned
infrastructure. No TCP database port, supplied DSN, real credential or external
connection is used. The demo loads the overview, traverses all stages, checks a
confirmation-gated synthetic intake and a blocked/replayed action, verifies seven
disabled connectors, and automatically closes the listener and deletes its
sessions/database/wrapper files. There is no persistent-listener CLI or preview.
Trusted Python callers must pair shutdown() and server_close() after serve_forever;
context-managed test/demo fixtures do so even after exceptions.

The final suite inventory is 424 tests including 189 PostgreSQL tests, retaining
all previous 402 tests and adding 8 governed-contract and 14 governed PostgreSQL
tests across the initial and corrective work (the original Phase 2C added 29). The
external CEO report records actual final counts and transcripts. CI trigger,
permissions, action/image pins and credential handling are preserved; only count
inventory/label change. No remote workflow is dispatched.

## Threat model and review boundary

| Threat | Implemented boundary / remaining limit |
|---|---|
| Cross-site access, CSRF, rebinding | Exact Host/Origin/fetch metadata, strict path cookie, one-use confirmation CSRF, no CORS; malicious local software is outside this synthetic fixture's trust boundary |
| Role/tenant/approval forgery, IDOR | Server-held immutable candidate envelopes, current gateway policy and exact session binding; no browser payload can choose a domain target |
| Replay, stale revision, double click | Server request/key/revision, 60-second intent, explicit confirmation, consumed-before-dispatch, existing transactional idempotency/CAS |
| Stored/reflected injection | Strict reference-only projections, exact request schemas, textContent/native text nodes, restrictive CSP; no HTML from stored/provider content |
| Information disclosure | Denied objects omitted, missing fields unresolved, no invented stage counts, no secrets in DOM/URLs/storage/audit, sanitized failures |
| Timeout or interrupted mutation | Existing cooperative precommit/SQL controls, rollback tests; uncertain outcomes remain possible near commit |
| False business authority | Every view/action synthetic and inactive, approvals unresolved, seven disabled connectors, no transmission or operational controls |

No confidential data, external application, operational routing, deployment, real
identity/credential, production authentication, TLS, durable UI session, distributed
rate limiter, production hard timeout, integration activation or Phase 2D work is
included. Legacy logs are neither imported nor changed. Known local synthetic limitations and the required manual accessibility disposition
are explicit in the external CEO review package.


The compatibility `items` read envelope and legacy nullable `counts` fields are
retained for earlier clients/tests. The browser renders only governed `queues` and
uses their count/blocked_count values. Legacy nullable counts are not a second
aggregation or a claim that governed queues are unknown. Current governed reads
and eligibility also retain process-local rate admission and reference-only
attempt audit; audit-sink failure prevents domain work. No CSRF/session/bearer
value is included in that audit.
