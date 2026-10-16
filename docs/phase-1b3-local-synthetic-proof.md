# Phase 1B.3 — Local Synthetic Persistence Proof

**Uncommitted for one CEO review. PostgreSQL integration is UNVERIFIED.**

Baseline: `3f8b00d`, current main when this branch was created, containing the
14-entity Phase 1B foundation. Branch: `phase-1b3/synthetic-persistence-proof`.
This extends the existing package. It does not add another application, change the
CLI/engine, or load the new adapter by default. All data and identities are synthetic.

## Implemented files and boundaries

| File | Purpose |
|---|---|
| migrations/postgresql/0001_synthetic_foundation.sql | PostgreSQL-targeted physical migration for the approved 14 entities, composite tenant keys, foreign keys, inactive constraints, forced RLS, restricted runtime role, and append-only history triggers |
| mission_control/synthetic_identity.py | Synthetic identity/MFA/service claims, exact-resource policy grants, separate duties, and ephemeral synthetic signing custody |
| mission_control/synthetic_postgres.py | Explicit migration application/checksum check, local socket helper, parameterized DB-API adapter, transaction guards, registry/packet/event writes, receipts, approvals and revocations |
| mission_control/synthetic_archive.py | Synthetic snapshot validation, no-overwrite owner-only export, and empty-target transactional restore |
| tests/synthetic_postgres_support.py | Synthetic identities, policies, and record fixtures |
| tests/test_synthetic_persistence.py | Unit and contract tests; recording connections are explicitly not database proof |
| tests/test_postgres_integration.py | Real disposable PostgreSQL tests, explicitly skipped when installed prerequisites are unavailable |
| docs/phase-1b3-local-synthetic-proof.md | This scope, evidence, procedures, limitations, and review handoff |

No requirements, existing runtime code, existing tests, configuration, or logical
migration manifest were changed. No service or package was installed. No production
migration or new migration of any kind was executed in this environment.

## PostgreSQL migration and adapter

The SQL targets PostgreSQL 14+ and maps the existing logical model:
schema_migrations, subjects, policy_revisions, role_bindings, registry_revisions,
registry_heads, approval_evidence, approval_revocations, packet_revisions,
packet_heads, journey_events, journey_heads, idempotency_receipts, security_decisions.

The migration is not run by imports or normal CLI execution. An explicit synthetic
migration-operator grant is required. The runner takes a transaction-scoped advisory
lock and binds migration ID to a checksum of SQL plus logical model. Reapplication
with the same checksum is a no-op; an existing unknown/mismatched schema fails.
There is no down migration, destructive cleanup, or production connection option.

The runtime database identity is `syn-runtime`, not the migration owner. The adapter
rejects owner/superuser session identity rather than relying on SET ROLE from a
privileged connection. The migration grants no DELETE, TRUNCATE, ownership, DDL,
or BYPASSRLS privileges to runtime. History has immutable-update/delete triggers;
only head pointers can be updated by runtime. All tables use forced row-level
security and tenant-scoped composite keys. Database constraints prohibit active
events and operational registry/packet states. JSON payloads are validated by the
adapter and again during snapshot integrity checks; SQL alone does not validate
all nested JSON contracts.

Every adapter transaction starts SERIALIZABLE, sets a transaction-local tenant,
and applies bounded statement/lock timeouts. Reads include explicit tenant filters;
all data values are parameterized. Identifiers come from the checked-in entity
allowlist, never request text. Work packets pin exact registry revisions; events
pin exact packet revisions, sequence, predecessor digest, and journey identity.

Successful writes commit data, head pointer, idempotency receipt, and minimized
security metadata together. Same key and digest is a no-op replay; changed payload,
stale head, or a duplicate event ID under another key is a conflict. Replays require
current authorization before receipt lookup. SQL serialization/deadlock/unique
conflicts become sanitized ConflictError results; callers must retry the complete
transaction with the original key. No automatic unbounded retry is supplied.

`commit()` requests commit on clean context exit, not immediate commit. Clean exit
without it rolls back. Any public adapter operation failure, including one caught
by the caller, marks the transaction failed and prevents committing partial writes.
Restore/export operations use the same guard. Identity and permissions are rechecked
at exit; revocation or expiry aborts the commit. A lost commit acknowledgement is
an uncertain outcome: reconnect and use the original idempotency key, not a new key.
The adapter closes connections rather than pooling tenant state.

## Synthetic identity, MFA, authorization, and duties

The authority is a local in-memory trusted fixture, with no external identity
provider or token validation. Caller-supplied claims are not accepted by an API;
the adapter is not exposed through a network service. Unconfigured authority or
connection factory denies before opening a connection.

Human fixtures require individual accounts and explicit fresh MFA state. Service
fixtures have short-lived credentials and cannot claim human MFA or privileged
roles. Synthetic test limits are five-minute MFA freshness, at most 15-minute
service credential lifetime, and at most five-minute approval lifetime. These are
local proof bounds, not approved enterprise authentication policy.

Policy administration, approval issuance, signing custody, encryption custody,
audit review, and migration operation use separate roles and subjects. Conflicting
privileged duties are rejected both within one session and across concurrent
sessions for one subject. A data author cannot approve its own record revision.
Encryption custody cannot initialize signing custody; a service writer cannot issue
approvals. Exact resource/action grants are required; explicit deny wins. There is
no wildcard grant or action permitting pilot activation, external providers, or
operational registry state. A synthetic authority or role is never CEO permission.

The persisted policy digest must match the separately trusted current authority.
Subjects/role bindings are persisted projections, not a mechanism for accepting
roles from callers or reactivating restored accounts. Policy bootstrap is an
explicit, authorized synthetic operation, not an automatic data-writer side effect.
Changing trusted policy revisions invalidates stale transactions.

## Approval issuance, verification, revocation, and custody

Approval metadata binds tenant, record, exact revision/digest, issuer, policy
revision, validity interval, evidence reference, and proof. Verification rechecks
current issuer authorization, exact persisted record, signature, expiry, and
append-only revocations. An old proof cannot approve a later edited revision.
Approval issuance or verification never changes the record to active.

The signing proof uses an ephemeral, randomly generated HMAC key, initialized only
by a synthetic signing-custodian fixture. It is not production signing, independent
nonrepudiation, a hardware key service, or persistent signing-key management. Keys
are not written into evidence, exports, source, or logs. A fresh custody instance
cannot verify old evidence; restore tests intentionally reuse the original test
custody. Production encryption is not implemented. Encryption and evidence-signing
custody remain separate roles; this proof supplies no encryption keys or cloud KMS.

## Synthetic export, restore, and integrity procedure

1. Using the exact `backup.export` grant, read all 14 entities for one tenant inside
   a single serializable transaction. The database's global migration ledger is
   not exposed by tenant RLS; the manifest instead binds the physical/logical
   migration checksum. No legacy JSONL files are read or imported.
2. Validate table schemas, tenant/dataset, typed values, unique keys, foreign keys,
   policy digests, record payload digests, contiguous history, current heads,
   packet/event references, event chains, receipts, and approval proofs. Preserve
   revoked/expired evidence as history; restoring it must not grant access.
3. Seal the manifest checksum with synthetic signing custody. Optional file export
   uses a unique owner-only staging file, fsync, atomic no-replace publication, and
   directory sync. Existing files cannot be overwritten. An interrupted unpublished
   staging file is not a valid backup; abrupt process death may require manual
   inspection of an owner-only leftover. Never auto-delete unrelated files.
4. Verify the checksum, proof, migration identity, and all integrity constraints
   before restoring. Require an independently authorized restore operator and an
   empty tenant target. Refuse cross-tenant restore, merge, overwrite, or unknown
   migration. The target physical schema must already have been explicitly migrated.
5. Restore rows and pointers in dependency order in one transaction. Require the
   restored policy to match current trusted authority; append a minimized restore
   decision. Explicit commit is still required. Any failure dooms the transaction.
6. Verify counts, exact records, event heads, revoked approvals, and idempotent replay
   after restore. Never execute an external action from restored lifecycle history.

The JSON artifact is **plaintext synthetic data protected by file permissions and
integrity proof**, not encrypted production backup, PostgreSQL base backup/WAL,
PITR, account disaster recovery, or a demonstrated RPO/RTO. No operational, audit,
backup, or legal-hold retention period is created here. Legacy logs remain unchanged
and excluded; quarantined logs must never be imported automatically.

## Test results and unverified items

In this environment, PostgreSQL server/client binaries and a psycopg driver are
unavailable. No software was downloaded or installed and no server was started.
No SQLite substitute was used.

Complete suite: **95 tests discovered; 85 passed, 10 PostgreSQL integration tests
skipped as UNVERIFIED**. This includes all 53 previous tests plus 32 new local unit/
contract tests. The skipped suite covers migration/reapplication, actual durable
registry/packet/event round trips, database rollback, caught stale-head rollback,
two-writer races, RLS and tenant isolation, approvals/revocations, service identity,
and database export/restore with replay after restore.

The passing tests exercise local validation, duty conflicts, MFA and service claims,
HMAC tampering/expiry/revocation, default-deny permissions, transaction protocol
calls, failure poisoning, export publication, and archive integrity. Recording
connections and staged row dictionaries are not PostgreSQL, durable commits, or
transaction-isolation evidence. Static SQL checks do not establish SQL execution
compatibility. PostgreSQL syntax/application and every skipped behavior remain
unverified until the real suite runs.

To rerun existing and new checks from the checkout:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m unittest discover -s tests -v
.venv/bin/python -m pip --no-cache-dir check
.venv/bin/python -B main.py --demo --no-log
git diff --check
```

If initdb, pg_ctl, psycopg 3, POSIX, and a non-root user are already available, the
integration suite creates ONLY its own private /tmp cluster, with TCP disabled and
local trust authentication on an owner-only socket directory. It creates only
synthetic databases/users, uses a dedicated non-owner runtime identity, and stops
its own instance afterward. The isolated trust configuration is not suitable for
production. There is no environment DSN, cloud connection, credential prompt, or
installation fallback. Missing prerequisites cause explicit skips. A runtime
adapter factory is a trusted constructor/test dependency, not untrusted request
data or a sandbox; the supplied local connector rejects TCP/remote paths.

## Risks, limitations, and next review gate

- This is an implementation proposal, not a successful PostgreSQL persistence proof.
  Database correctness, privileges, concurrency, crash recovery, driver behavior,
  and actual restore remain blocked on local tool availability.
- Synthetic identity/MFA claims are assertions from fixtures, not real authentication.
  No identity provider, service credential issuer, signing service, or production
  approval authority is connected.
- RLS reinforces tenant-scoped application queries. A compromised backend holding
  runtime credentials may change its session context; this is not a security
  sandbox or protection from arbitrary privileged Python/SQL code.
- The runtime role has tenant-scoped SQL privileges, while exact-resource/duty
  enforcement occurs in the adapter. Direct DB access must not be exposed to users.
- Successful operations persist minimized security decisions. Denied attempts and
  transactions rolled back on failure do not create an independent durable denial
  audit; production incident logging requires a separately reviewed design.
- Exports are not encrypted and signing keys are ephemeral. Production backup,
  signing-key persistence/recovery, immutability, independent custody, legal holds,
  and retention remain separate decisions. No availability architecture is chosen.
- Pending integration tests are a blocker to claiming PostgreSQL verification, not
  a reason to substitute a different database or quietly install services.

Recommended next step: one focused CEO code review of these uncommitted files.
Then, only with approved existing tooling or separate tooling authorization, run
all ten PostgreSQL integration tests in an isolated synthetic environment and fix
any failures before committing or connecting this adapter to existing application
flows. Confidential pilot availability, provider selection, key custody, identity,
policy ownership, and pilot launch remain separately approved decisions.

No commit, push, merge, deployment, environment publication, cloud connection,
confidential-data entry, external integration, or pilot activation occurred.
