# Phase 2B synthetic localhost HTTP boundary

Review baseline: `426e29cfb2937336df8efe393db8013827ea2171`.
Local branch: `phase-2b/localhost-http-boundary`. Work remains unstaged and uncommitted.

The opt-in [HTTP adapter](../mission_control/local_http.py) wraps the existing
[Phase 2A gateway](../mission_control/connection_gateway.py) and
[services](../mission_control/connection_services.py). Importing the adapter or
running the existing application starts no listener. Explicit trusted construction
requires `synthetic_development=True`, an actual Gateway, and server-installed
`SyntheticBinding` records. There is no configuration switch that activates a
connector, chooses a database, accepts real credentials, or enables operations.

## Boundary contract

Only literal IPv4 loopback addresses are accepted. DNS names, IPv6, wildcard,
LAN and public addresses fail before socket creation. Default port is ephemeral
(`0`). This intentionally narrower implementation refuses IPv6 loopback as well.
Every connection closes after one response. The serial server has a bounded
backlog of four; it is a synthetic development fixture, not a production server.

All accepted routes use the exact existing JSON envelope, including GET requests.
GET bodies are a deliberate local testing contract, unsuitable for browser API
use or generic intermediary caching. No query strings, percent escapes, fragments,
path rewriting, proxy trust, cookies, CORS origins or forwarded identity are
accepted. Host must equal the bound literal address and actual port. Methods are
GET/POST only; methods absent from the route table fail closed. HEAD returns no
body. No OPTIONS preflight or cross-origin response is supported.

Requests require one Content-Length, at most 65,536 bytes, with no transfer or
content encoding or Expect negotiation. Content-Type must be application/json,
optionally with charset=utf-8. Strict UTF-8, duplicate keys, nonfinite values,
unknown fields, reference formats, schema/revision/idempotency requirements and
freshness are enforced by the existing decoder. Duplicate HTTP headers and more
than 8 KiB of parsed header fields are rejected; stdlib parser line/count limits
also apply before dispatch. The absolute input deadline bounds byte-drip clients;
socket idle/write timeouts and domain cancellation default to two seconds and
cannot exceed five seconds.

`Authorization: Bearer <ephemeral synthetic token>` maps only to a server-held
session and policy revision. Generate tokens locally (for example secrets.token_hex),
keep them process-local, and never print or save them. Tokens are synthetic fixture
capabilities, not production authentication. The gateway independently verifies
current authority, tenant, actor, session, purpose, surface and exact resource
grants on every call and retry. JSON and identity-looking headers cannot install
roles, policies or sessions. Default construction has no authority.

The gateway owns rate limits, canonical response ceilings, sanitized errors and
reference-only admission audit. Existing services own transactional idempotency,
CAS revisions, immutable classification, approvals, lifecycle, tenant RLS,
visibility, readiness and governance. The adapter adds no SQL or domain storage.
Errors reveal stable codes only. No request/error logging is performed. Responses
set no-store, nosniff, restrictive CSP, frame denial and no-referrer headers; no
CORS allowance is returned. HTTP is unencrypted and only for synthetic loopback use.

Domain cancellation remains cooperative through existing budget and precommit
checks; arbitrary Python dependencies cannot be forcibly interrupted. SQL retains
its existing five-second statement/two-second lock limits. Client disconnection or
a timeout can have an uncertain commit outcome: retry the same original domain
idempotency key, never assume rollback from a missing response. No daemon worker,
thread termination, durable denial audit or production hard deadline is claimed.

## CEO Command Center

`GET /v1/command-center` delegates to the existing `/v1/visibility` gateway route,
requiring `visibility.project`, `audience: command`, `team_reference: null`, an
exact packet revision and matching intake correlation. The existing command
projection is returned unchanged. No stage progress, staffing, measurements,
escalation policy, broader visibility or operational approval is invented. The
six-stage Phase 2A presentation schemas remain available but unresolved fields
are not populated by this transport. See the updated [OpenAPI contract](phase-2a-openapi.json).

All seven connectors retain disabled/unresolved descriptors. Existing outbox
routes produce only inactive, reference-only intentions. No dispatcher, delivery,
connector transport, external connection, tunnel, pilot or Phase 2C work is added.
Phase 1 migrations, archive inventory, identity and operational denial remain
unchanged. Legacy logs are never imported or used as a data source.

## Reproduce locally

Use the current isolated checkout; do not create a Git worktree. Python 3.12,
Docker and the reviewed official PostgreSQL image are prerequisites. Install into
an external environment to keep the checkout clean:

```sh
python -m venv /tmp/phase-2b-venv
/tmp/phase-2b-venv/bin/python -m pip install -r requirements-dev.txt
/tmp/phase-2b-venv/bin/python -m pip check
/tmp/phase-2b-venv/bin/python -B -m unittest tests.test_local_http -v
/tmp/phase-2b-venv/bin/python -B scripts/demo_local_http.py --synthetic-development
/tmp/phase-2b-venv/bin/python -B scripts/local_postgres_tests.py
/tmp/phase-2b-venv/bin/python -B main.py --demo --no-log
git diff --check
```

The local runner requires the already downloaded digest-pinned PostgreSQL 17.11
image specified in the existing CI workflow. It never downloads an image, uses a
cloud DSN or impersonates GitHub Actions. It uses a disposable container with
`--network none`, matching non-root UID, read-only host passwd, and shared `/tmp`
for the existing private Unix socket fixtures. No TCP port is published. Only the
trusted PostgreSQL binary runs in this container. UTF-8 initialization avoids the
SQL_ASCII default of no-locale clusters. Each fixture owns its temporary cluster;
the runner removes its container and wrapper directory even on test failure.
No persistent database, system service or infrastructure is provisioned.

The suite count gates require 373 tests, including 167 real PostgreSQL tests, with
zero skips/failures/errors/expected failures. Existing 342 tests are retained;
Phase 2B adds 21 offline socket tests and 10 HTTP/PostgreSQL tests. Manual CI
preserves its existing trigger, permissions, action/image pins and credential
handling; only its count inventory/step label changes. No workflow is dispatched.
For independent OpenAPI validation install openapi-spec-validator into the external
venv and call its validator on docs/phase-2a-openapi.json. No runtime dependency is
added. Local relative Markdown links and specification references must resolve.

The demonstration opens an ephemeral loopback server, proves authenticated inactive
health and forged-actor denial, and stops it. It prints no token or request body.
It does not pretend to validate domain persistence; PostgreSQL tests prove that.

Publication, deployment, integration activation and commits are outside this review.
