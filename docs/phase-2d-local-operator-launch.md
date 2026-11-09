# Phase 2D — Local operator launch and evaluation

Mission Control OS™ — **LOCAL · SYNTHETIC · NOT PRODUCTION · NO ORGANIZATIONAL AUTHORIZATION**.

This package deliberately starts the existing Phase 2C CEO Command Center with
approved synthetic fixtures. It is an evaluation tool, never an organizational
authorization, production interface, integration, or external transport. Ordinary
imports, installation, and CLI help do not start a listener. All seven connectors
remain disabled. The operator profile exposes authorized read-only views and no
mutation candidates. Existing confirmation-gated Phase 2C actions remain intact
and are exercised separately by the retained demonstration and regression suite.

## Quick operator instructions

Use a trusted checkout and a non-root POSIX account. Activate the project's Python
virtual environment with `requirements-dev.txt` installed. Run these commands from
the repository root. No API keys, passwords, browser extensions, or cloud DSN are
required. Do not enter confidential information.

The single entry point is `python -B -m mission_control.local_operator`:

```sh
python -B -m mission_control.local_operator start --synthetic-development
python -B -m mission_control.local_operator status
python -B -m mission_control.local_operator check
python -B -m mission_control.local_operator open
python -B -m mission_control.local_operator open --browser
python -B -m mission_control.local_operator stop
python -B -m mission_control.local_operator demo --synthetic-development
```

`start` prints the exact URL after health and authorized-interface verification.
The default port is allocated atomically by the kernel, not guessed or reserved
and released. Copy that URL to a local browser or explicitly use `open --browser`.
`open` without that flag checks the interface and prints the URL without opening
anything. The application itself never contacts an external application. An
explicit browser launch delegates to the operator's OS browser configuration;
use a clean local browser profile with extensions and syncing disabled for review.

`status` prints only the PID, UTC start time, literal loopback URL, and synthetic
mode. `check` verifies both the existing gateway health boundary and the actual
Phase 2C HTML/authorized overview with its session and security controls. No
response content, fixture reference, session cookie, CSRF value, or bearer token
is printed. Technical health does not confer organizational authorization.

`stop` waits for the managed process to shut down its listener, PostgreSQL cluster,
and temporary container/files. Successful return means kernel-confirmed process
exit and removal of managed transient state. A second stop is harmless. There is
no automatic login item, daemon installation, schedule, or restart. A managed
instance expires after at most ten minutes; deliberately start another instance
for further evaluation. Stop explicitly when finished rather than waiting.

Only use a fixed local port after its use is approved:

```sh
python -B -m mission_control.local_operator start --synthetic-development --port 49152
```

Binding is always literal `127.0.0.1`. Wildcards, other IPv4 addresses, hostnames
(including `localhost`), IPv6, forwarded-host configuration, proxy routes, public
URLs, and tunnels are unsupported and rejected. There is no public preview.

## Prerequisites by platform

### Linux / POSIX development (verified here)

Use Python 3.12, the pinned development dependencies, local Docker with a Unix
socket endpoint, and the **already installed** official image pinned in
[scripts/local_postgres_tests.py](../scripts/local_postgres_tests.py). Installation
and downloading an image are separate operator/environment preparation steps;
`start` never pulls images or provisions infrastructure. Docker runs the cached
PostgreSQL 17.11 image with `--network none`, `--pull=never`, no published ports,
the non-root account's UID/GID, private Unix PostgreSQL sockets, and no host DSN.
The existing `/tmp` shared-path test harness is reused. A remote Docker endpoint
is rejected before invoking Docker service operations.

```sh
python -m venv /workspace/phase-2d-env
. /workspace/phase-2d-env/bin/activate
python -m pip install -r requirements-dev.txt
python -m pip check
python -B -m mission_control.local_operator demo --synthetic-development
```

Do not run the operator as root. Do not substitute a cloud database or a production
connection string. The synthetic fixture/bootstrap modules in `tests/` are explicit
runtime dependencies of this evaluation profile; a source checkout is required.

### macOS CEO evaluation instructions (manual qualification required)

No macOS execution host was available for this review. **macOS compatibility is
not claimed as tested.** Have the technical reviewer qualify the following sequence
on the actual Mac before using it for a CEO session. Do not install a LaunchAgent,
login item, service, or persistent PostgreSQL instance.

1. Open Terminal in the trusted repository checkout; activate its Python virtual
   environment and install the pinned development requirements.
2. Have the technical reviewer supply an already installed, trusted **17.11** set
   of `postgres`, `initdb`, and `pg_ctl` tools in the same directory on `PATH`.
   The package verifies each version and starts a disposable Unix-socket-only
   cluster. It does not download software or use Docker Desktop on macOS.
3. Run `python -B -m mission_control.local_operator demo --synthetic-development`.
   If peer identity, process-exit watching, or the database tools are unavailable,
   the package must fail closed; do not bypass the checks.
4. Use `start --synthetic-development`, then `check`, then `open --browser`.
   Confirm the four boundary labels and six stages. Finish with `stop` and
   `status`. If anything fails, use the verified Linux evaluation environment.

The Darwin implementation uses kernel `LOCAL_PEERPID`/`LOCAL_PEERCRED` and kqueue
process-exit notifications. Its empty private runtime directory lives under
`/private/tmp` to avoid macOS's `/tmp` symlink. Windows is unsupported and untested.

## Architecture and security boundaries

[local_operator.py](../mission_control/local_operator.py) implements process
management and local technical validation only. The worker constructs the
existing gateway, `PhaseOneServices`, server-held synthetic authority and binding,
and `LocalCEOInterface`. Synthetic bootstrap reuses the approved Phase 1 fixture
and migrations without new domain logic, database schema, or store. The six-stage
projection, original classifications, append-only history, eligibility, tenant,
identity, revision, idempotency, policy, and audit remain with those layers.

The operator profile installs a fixed read candidate for an existing synthetic
journey, no write candidates, and a separate server-held audit identity for the
existing gateway `/health` action. Browser payloads supply neither identity nor
policy. Gateway health still passes through existing admission, authorization,
budget, rate, and minimized audit controls. The operator control channel reports
only a boolean health summary, never the gateway response. No new HTTP/OpenAPI
contract was added, so the OpenAPI document is unchanged.

The UI retains all Phase 2B/2C Host, same-origin, CSRF, CSP, strict parsing,
confirmation, sanitization, cooperative timeout and authorization controls. HTML
and overview checks use direct `http.client` loopback connections without proxy
settings, redirect following, or external URLs. The HTML must byte-match the
installed asset, overview schema/queues must validate, the seven connector count
and inactive synthetic state must match, and required security headers/cookie
attributes must be exact. The HTTP response body is bounded, decoded strictly,
and discarded without output. Cookies are process-local and not stored by the
operator. No token is placed in a URL, state file, or terminal.

### Runtime state, locking and process identity

A validated existing `XDG_RUNTIME_DIR` is preferred: it must be an absolute,
non-symlink directory owned by the **effective** operator identity with exactly
mode `0700`. The application creates its dedicated `mc-operator` child there
and verifies that child independently. An invalid environment candidate fails
closed rather than being trusted, repaired, or silently replaced. Arbitrary
`HOME`, `TMPDIR`, workspace, or other environment paths do not select state.
Without XDG, the fallback is `/tmp/mc-local-operator-<effective-uid>` on Linux or
`/private/tmp/mc-local-operator-<effective-uid>` on macOS. Atomic creation with
mode `0700` and ownership/type verification are mandatory; a pre-existing unsafe
entry is rejected. Effective UID zero receives no ownership or permission bypass.

`--state-dir /absolute/private/path` is an explicit controlled configuration and
also the test-injection boundary. It receives all the same checks and may never
select the repository or a descendant. No state is created in the checkout.
Paths with traversal, symlink components, or unsuitable length fail closed.
Platform-managed ancestors such as `/`, `/tmp`, `/workspace`, or CI mounts provide
**namespace**, not application authority; the operator neither requires ownership
of them nor changes their permissions. This does not authorize an unsafe workspace
or trust its contents: the checkout/account are separate trusted prerequisites,
and no platform ancestor can supply identity or authorization through state.

Each path component is opened relative to its pinned parent descriptor using
`O_DIRECTORY | O_NOFOLLOW`; every ancestor's device/inode identity is recorded.
The dedicated leaf must be owned by the effective UID and exactly mode `0700`.
The complete namespace and pinned leaf are revalidated after lock acquisition
and before controlled operations, so ancestor/leaf replacement fails closed.
File stat/open checks use `dir_fd`, no-follow flags, regular-file/type/ownership,
mode `0600`, link count, and matching device/inode checks after open. Linux Unix
socket paths use `/proc/self/fd/<verified-fd>/control.sock` so pathname lookup
stays within the pinned directory even during a rename. Darwin checks the
namespace before and after connection and verifies the kernel peer; that path
still requires manual platform qualification.

Commands take an exclusive `flock` on the directory inode for their entire
operation. They do not create a removable lock or PID file. This prevents split
locks and serializes concurrent starts/stops. **The empty directory intentionally
remains** between runs; it contains no PID, state, lock, credential, or socket
file after shutdown. Never remove or replace that directory while commands run.
The worker inherits an independently opened directory descriptor rather than the
command's locked open description, preserving later commands' ability to lock.
The lock is released by the OS when the command exits.

During a managed run only `state.json` (regular, single link, mode `0600`) and
`control.sock` (Unix socket, mode `0600`) are accepted. State is strict, size-bounded
JSON with exact fields: version, PID, literal host, port, UTC start time, synthetic
flag, random instance discriminator, and operator-code SHA-256. The discriminator
is a public instance label, **not** a credential. No authentication secret or
domain content is written to state. Symlinks, hard links, wrong ownership, unsafe
permissions, malformed/extra fields, stale PIDs and changed code fail closed.
Cleanup unlinks only relative to the verified private directory descriptor;
it never follows a substituted ancestor to delete unrelated files.

A state PID alone is never trusted. Every connection verifies the live Unix
peer's kernel UID/PID, code digest, and exact status against the state. Stop also
pins that kernel process with Linux pidfd or Darwin kqueue before making a second
verified connection. PID reuse cannot redirect a shutdown signal: **the package
never sends OS signals or kills process groups**. It asks only the verified peer
to shut itself down, then watches that exact process exit. A bounded timeout
reports failure and never escalates into signalling an unrelated or unverifiable
process. This is intentionally safer than blind SIGKILL escalation; cleanup may
require operator investigation if a dependency is uninterruptibly stuck.

The startup parent retains a private pipe until it verifies health. Parent EOF,
interrupted verification, or timeout before acceptance tells the worker to tear
down. Container, cluster, tools, socket, state and UI sessions are cleaned up
before success is acknowledged. Worker lifetime is bounded. Cleanup does not
change filesystem permissions outside newly created private runtime resources.

### Threat model and limitations

Untrusted HTTP clients, hostile Host/Origin headers, malformed network responses,
stale or corrupted state, PID reuse, cross-user state/socket substitution, double
starts and concurrent shutdowns are within scope. The operating-system account,
trusted checkout, Python executable, installed PostgreSQL binaries, and local
Docker daemon are trusted. A hostile process with the same UID can inspect
process memory, change executable code, or forge local service behavior; this
package is not an isolation boundary against a compromised operator account.
Use a dedicated trusted local account. Never infer approval from a process name,
health check, technical readiness, or displayed synthetic record.

Plain loopback HTTP has no TLS and cannot use a Secure cookie. Browser security,
server-held synthetic identity, CSP and strict sessions do not make it production
ready. There is no login/OAuth/SSO/MFA, no confidential-data path, telemetry,
production identity, secrets management, persistent session, external connector,
outbox delivery, deployment, public URL, or remote database. Cooperative service
deadlines cannot preempt arbitrary blocked Python/native code. A bounded failed
stop is a blocker, not a claim of successful cleanup. No domain files or migrations
were modified. The UI changes are the complete boundary warning, responsive wrapping and the
reviewed Escape focus-restoration handler. No text is hidden, truncated,
abbreviated or horizontally scrolled. No domain behavior changes.

## Troubleshooting and recovery

| Symptom | Safe action |
| --- | --- |
| Occupied fixed port | Confirm no managed instance is running, then use default port zero. Never kill the process occupying an arbitrary port. |
| Double start | Run `status` and `check`; use the existing verified instance or `stop` it first. |
| Stale/malformed/symlinked state | Stop evaluation. Do not edit the PID, broaden permissions, or blindly signal it. A technical reviewer must establish that no managed process/container remains. After a system restart and verification, remove only that account's stale runtime entries, leaving the empty private directory. |
| Failed health / unexpected HTML | Do not open the interface. During startup this rolls back automatically. After startup use verified `stop`; inspect trusted checkout/tool versions without logging response content. |
| Interrupted startup | Allow the bounded startup/cleanup window to finish, then run `status`. Unknown leftover state is a blocker; do not launch another instance over it. |
| Shutdown timeout | Stop the evaluation and report NOT READY. Do not use `kill` on the stored PID. Investigate the owned disposable database/container with a technical reviewer; reverify identity before any manual remediation. |
| Code changed during a run | Do not edit a running evaluation checkout. The identity digest deliberately rejects changed code; let the bounded instance expire before reviewing cleanup. |
| Missing image/tools | Prepare the already pinned local dependencies separately; no remote/cloud fallback is permitted. |
| macOS peer/tool failure | Leave controls intact and use the verified Linux workflow until macOS manual qualification passes. |

The CLI sanitizes exceptions into a constant failure message and nonzero exit.
It never prints raw exceptions, stack traces, paths from rejected payloads, or
protected responses. Detailed security failures belong in technical tests, not
operator terminal dumps.

## Accessibility evaluation checklist

Automated/browser checks supplement, rather than replace, manual assistive-
technology review. Before CEO use, record the browser, OS, assistive technology,
reviewer, date and findings outside the repository.

- Navigate using keyboard only: skip link, load/clear controls, six stages and
  boundary information; visible focus, logical order and no keyboard traps.
- Confirm one page heading, semantic landmarks, logical heading order, table
  caption and column headers, meaningful control names, and labelled fields.
- Confirm loading, empty, blocked, denied and failure announcements are understandable
  with a screen reader and status is never communicated by color alone.
- At 200% zoom and narrow viewport, confirm content remains readable and all
  controls remain reachable without lost focus.
- Confirm reduced-motion settings are respected and no automatic refresh disrupts
  focus. Confirm the four boundary labels are legible and do not obscure controls.
- In the separate synthetic action demonstration, inspect confirmation focus,
  checkbox requirement, cancel/Escape behavior, result focus and stale/replay denial.
- Review contrast, screen-reader announcements and native dialog behavior using
  the actual intended browser/assistive-technology combination. Record remaining
  manual findings; automated structural checks are not WCAG certification.

## Verification and review evidence

Run the complete disposable suite using:

```sh
python -B scripts/local_postgres_tests.py
python -B scripts/demo_command_center.py --synthetic-development --browser-check
python -B -m mission_control.local_operator demo --synthetic-development
python -m pip check
git diff --check
```

The review package outside the checkout contains exact discovered/executed and
PostgreSQL counts, full transcripts, offline results, browser/accessibility output,
leakage/external-reference and path checks, legacy-log comparison, final cleanup
checks, proposed patch, file inventory, security findings and draft PR text.
The original 424 test IDs remain required; added tests exercise operator lifecycle,
concurrency, hostile state/transport, startup cleanup, PID mismatch and safe stop.
No test is disabled to make the package pass.

Backward-compatibility risks are limited to factoring the existing disposable
PostgreSQL tool context for reuse, updating strict runner counts, and expanding
the visible boundary label and wrapping. Existing Phase 1–2C service/API contracts, migrations,
connectors, frontend actions and security checks remain unchanged. The explicit
manual CI workflow retains its pinned service image and zero-skip requirement.

Recommended commit message and PR title: `Add Phase 2D local operator launch and evaluation package`.
No commit, push, deployment, environment publication, persistent listener,
integration activation, or Phase 2E work is part of this implementation review.


### Reconstruction verification scope

The reconstruction includes responsive boundary wrapping, a descriptor-based
private runtime directory trust model and a governed worker lifecycle. Browser regressions check the entire
unmodified warning text, full component visibility, no clipping/ellipsis and no
document overflow at **320, 360, 375, 390, 768 and 1280px**, plus 200% layout zoom.
Existing keyboard confirmation, result focus, text contrast, reduced motion,
semantic/structural accessibility and no-external-request assertions are retained.
Manual assistive-technology review remains a separate documented requirement.

Runtime regressions cover non-owned platform ancestors with a private leaf,
wrong leaf/effective ownership, permissions, root without exemptions, XDG candidate
validation, symlinked ancestor/state/lock/socket, unexpected PID/lock entries,
ancestor and directory substitution, and state replacement between stat/open.
Real disposable tests verify startup, status, health, read-only open, clean stop,
concurrency, PID mismatch, interrupted/failed startup, occupied ports and demo.
The test runners report actual discovered, executed, offline and PostgreSQL
counts; no historical count is an acceptance gate. Every discovered test must
execute with zero failures, errors, skips, expected failures or unexpected
successes. The fresh durable evidence package is `/workspace/phase-2d-review/`.
It is generated by this reconstruction, not recovered evidence or prior approval.
The package contains current execution results, exact changed-file hashes and the
complete patch. No statement from earlier verification is carried forward as
proof for this reconstruction.


The worker handles incoming SIGTERM/SIGINT as orderly termination requests and
cleans its listener, sessions, PostgreSQL cluster, container, tools and state before
exiting. Normal stop uses only the verified private control connection, never a
PID-based signal. Process-creation failure closes startup pipes and descriptors.
Parser errors use a constant message so rejected arguments cannot echo values to
the terminal. These cases have explicit offline and real-process regressions.

Uncatchable termination (SIGKILL), host failure or a compromised operator account
cannot be made cleanup-safe by Python finally blocks. These remain production
exclusions: stale state fails closed and requires separately verified manual
recovery. A cleanup timeout is a blocker, never evidence that cleanup succeeded.
Do not blindly signal a stored PID or delete unknown resources. The final review
includes an actual end-of-validation process/listener/container/file inventory.

The workspace-backed evidence is newly generated under the current authorization.
No previous approval or lost evidence is reused. It is outside the checkout and
outside `/tmp`; no remote backup, environment publication or future VM restoration
is claimed. Retain the package through your review-record process before discarding
this execution environment.


Narrow Phase 2C presentation compatibility correction: Escape now explicitly
closes the native confirmation dialog and restores focus to the invoking prepare
control. The native cancel event previously closed the dialog with focus left on
the page body. The new browser regression verifies Escape, the Cancel button,
focus restoration, checkbox gating and keyboard confirmation. No confirmation,
request, policy, eligibility, revision, audit, approval or domain action changes.
This one-line presentation change is included in the proposed diff for review.


Repeated technical checks open ephemeral UI sessions under the existing Phase 2C
capacity limit (16 sessions, at most five minutes each). Excessive checks can
fail closed until expiry; they never bypass identity/session controls. `status`
does not consume a UI session. A browser explicitly opened by the user is owned
by the user, not killed by `stop`; the operator invalidates server-side sessions
and stops its own listener. Evaluation browser tests manage and close their own
disposable Chromium context/profile.
