-- LOCAL SYNTHETIC ONLY. No seed organization records; no automatic application.

-- PostgreSQL 14+. Applied transactionally by an explicitly authorized migration role.

CREATE SCHEMA mc_syn;

DO $$ BEGIN
IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'syn-runtime') THEN
    CREATE ROLE "syn-runtime" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
ELSIF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'syn-runtime' AND
    (rolsuper OR rolcreatedb OR rolcreaterole OR rolinherit OR rolbypassrls OR NOT rolcanlogin)) OR
    EXISTS (SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member WHERE r.rolname = 'syn-runtime') THEN
    RAISE EXCEPTION 'Unsafe existing synthetic runtime role';
END IF;
END $$;

REVOKE ALL ON SCHEMA mc_syn FROM PUBLIC;

GRANT USAGE ON SCHEMA mc_syn TO "syn-runtime";

CREATE TABLE mc_syn.schema_migrations (
    tenant_reference text NOT NULL CHECK (tenant_reference LIKE 'syn-%'),
    migration_id text NOT NULL,
    checksum text NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'),
    applied_at timestamptz NOT NULL,
    dataset text NOT NULL CHECK (dataset = 'synthetic'),
    PRIMARY KEY (tenant_reference, migration_id)
);

CREATE TABLE mc_syn.subjects (
    tenant_reference text NOT NULL CHECK (tenant_reference LIKE 'syn-%'),
    subject_reference text NOT NULL,
    issuer_reference text NOT NULL,
    audience text NOT NULL,
    status text NOT NULL,
    dataset text NOT NULL CHECK (dataset = 'synthetic'),
    PRIMARY KEY (tenant_reference, subject_reference)
);

CREATE TABLE mc_syn.policy_revisions (
    tenant_reference text NOT NULL CHECK (tenant_reference LIKE 'syn-%'),
    policy_revision bigint NOT NULL CHECK (policy_revision > 0),
    content_digest text NOT NULL CHECK (content_digest ~ '^[0-9a-f]{64}$'),
    rules_document jsonb NOT NULL,
    valid_from timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    dataset text NOT NULL CHECK (dataset = 'synthetic'),
    PRIMARY KEY (tenant_reference, policy_revision),
    CHECK (valid_from < expires_at)
);

CREATE TABLE mc_syn.role_bindings (
    tenant_reference text NOT NULL CHECK (tenant_reference LIKE 'syn-%'),
    binding_reference text NOT NULL,
    subject_reference text NOT NULL,
    role_reference text NOT NULL,
    policy_revision bigint NOT NULL CHECK (policy_revision > 0),
    valid_from timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    dataset text NOT NULL CHECK (dataset = 'synthetic'),
    PRIMARY KEY (tenant_reference, binding_reference),
    CHECK (valid_from < expires_at)
);

CREATE TABLE mc_syn.registry_revisions (
    tenant_reference text NOT NULL CHECK (tenant_reference LIKE 'syn-%'),
    record_reference text NOT NULL,
    revision bigint NOT NULL CHECK (revision > 0),
    previous_revision bigint NOT NULL,
    state text NOT NULL CHECK (state IN ('draft','inactive')),
    payload jsonb NOT NULL,
    content_digest text NOT NULL CHECK (content_digest ~ '^[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL,
    actor_reference text NOT NULL,
    policy_revision bigint NOT NULL CHECK (policy_revision > 0),
    dataset text NOT NULL CHECK (dataset = 'synthetic'),
    schema_revision bigint NOT NULL CHECK (schema_revision = 1),
    PRIMARY KEY (tenant_reference, record_reference, revision),
    CHECK (previous_revision = revision - 1)
);

CREATE TABLE mc_syn.registry_heads (
    tenant_reference text NOT NULL CHECK (tenant_reference LIKE 'syn-%'),
    record_reference text NOT NULL,
    revision bigint NOT NULL CHECK (revision > 0),
    dataset text NOT NULL CHECK (dataset = 'synthetic'),
    PRIMARY KEY (tenant_reference, record_reference)
);

CREATE TABLE mc_syn.approval_evidence (
    tenant_reference text NOT NULL CHECK (tenant_reference LIKE 'syn-%'),
    evidence_reference text NOT NULL,
    record_reference text NOT NULL,
    record_revision bigint NOT NULL CHECK (record_revision > 0),
    content_digest text NOT NULL CHECK (content_digest ~ '^[0-9a-f]{64}$'),
    grantor_reference text NOT NULL,
    policy_revision bigint NOT NULL CHECK (policy_revision > 0),
    valid_from timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    status text NOT NULL,
    proof_reference text NOT NULL,
    dataset text NOT NULL CHECK (dataset = 'synthetic'),
    PRIMARY KEY (tenant_reference, evidence_reference),
    CHECK (valid_from < expires_at)
);

CREATE TABLE mc_syn.approval_revocations (
    tenant_reference text NOT NULL CHECK (tenant_reference LIKE 'syn-%'),
    evidence_reference text NOT NULL,
    revocation_reference text NOT NULL,
    revoked_at timestamptz NOT NULL,
    actor_reference text NOT NULL,
    dataset text NOT NULL CHECK (dataset = 'synthetic'),
    PRIMARY KEY (tenant_reference, revocation_reference)
);

CREATE TABLE mc_syn.packet_revisions (
    tenant_reference text NOT NULL CHECK (tenant_reference LIKE 'syn-%'),
    packet_reference text NOT NULL,
    revision bigint NOT NULL CHECK (revision > 0),
    previous_revision bigint NOT NULL,
    registry_reference text NOT NULL,
    registry_revision bigint NOT NULL CHECK (registry_revision > 0),
    state text NOT NULL CHECK (state IN ('draft','inactive')),
    payload jsonb NOT NULL,
    content_digest text NOT NULL CHECK (content_digest ~ '^[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL,
    actor_reference text NOT NULL,
    policy_revision bigint NOT NULL CHECK (policy_revision > 0),
    dataset text NOT NULL CHECK (dataset = 'synthetic'),
    schema_revision bigint NOT NULL CHECK (schema_revision = 1),
    PRIMARY KEY (tenant_reference, packet_reference, revision),
    CHECK (previous_revision = revision - 1)
);

CREATE TABLE mc_syn.packet_heads (
    tenant_reference text NOT NULL CHECK (tenant_reference LIKE 'syn-%'),
    packet_reference text NOT NULL,
    revision bigint NOT NULL CHECK (revision > 0),
    dataset text NOT NULL CHECK (dataset = 'synthetic'),
    PRIMARY KEY (tenant_reference, packet_reference)
);

CREATE TABLE mc_syn.journey_events (
    tenant_reference text NOT NULL CHECK (tenant_reference LIKE 'syn-%'),
    event_reference text NOT NULL,
    journey_reference text NOT NULL,
    sequence bigint NOT NULL CHECK (sequence > 0),
    packet_reference text NOT NULL,
    packet_revision bigint NOT NULL CHECK (packet_revision > 0),
    previous_digest text CHECK (previous_digest ~ '^[0-9a-f]{64}$'),
    content_digest text NOT NULL CHECK (content_digest ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL,
    active boolean NOT NULL CHECK (active = false),
    created_at timestamptz NOT NULL,
    actor_reference text NOT NULL,
    policy_revision bigint NOT NULL CHECK (policy_revision > 0),
    dataset text NOT NULL CHECK (dataset = 'synthetic'),
    schema_revision bigint NOT NULL CHECK (schema_revision = 1),
    PRIMARY KEY (tenant_reference, event_reference),
    UNIQUE (tenant_reference, journey_reference, sequence),
    CHECK ((sequence = 1 AND previous_digest IS NULL) OR (sequence > 1 AND previous_digest IS NOT NULL))
);

CREATE TABLE mc_syn.journey_heads (
    tenant_reference text NOT NULL CHECK (tenant_reference LIKE 'syn-%'),
    journey_reference text NOT NULL,
    sequence bigint NOT NULL CHECK (sequence > 0),
    dataset text NOT NULL CHECK (dataset = 'synthetic'),
    PRIMARY KEY (tenant_reference, journey_reference)
);

CREATE TABLE mc_syn.idempotency_receipts (
    tenant_reference text NOT NULL CHECK (tenant_reference LIKE 'syn-%'),
    operation_reference text NOT NULL,
    idempotency_key text NOT NULL,
    payload_digest text NOT NULL CHECK (payload_digest ~ '^[0-9a-f]{64}$'),
    result_reference text NOT NULL,
    result_revision bigint NOT NULL CHECK (result_revision > 0),
    created_at timestamptz NOT NULL,
    dataset text NOT NULL CHECK (dataset = 'synthetic'),
    PRIMARY KEY (tenant_reference, operation_reference, idempotency_key)
);

CREATE TABLE mc_syn.security_decisions (
    tenant_reference text NOT NULL CHECK (tenant_reference LIKE 'syn-%'),
    decision_reference text NOT NULL,
    subject_reference text NOT NULL,
    action text NOT NULL,
    resource_reference text NOT NULL,
    policy_revision bigint NOT NULL CHECK (policy_revision > 0),
    allowed boolean NOT NULL,
    reason_code text NOT NULL,
    created_at timestamptz NOT NULL,
    dataset text NOT NULL CHECK (dataset = 'synthetic'),
    PRIMARY KEY (tenant_reference, decision_reference)
);

ALTER TABLE mc_syn.role_bindings ADD CONSTRAINT role_bindings_fk_0 FOREIGN KEY (tenant_reference, subject_reference) REFERENCES mc_syn.subjects (tenant_reference, subject_reference);

ALTER TABLE mc_syn.role_bindings ADD CONSTRAINT role_bindings_fk_1 FOREIGN KEY (tenant_reference, policy_revision) REFERENCES mc_syn.policy_revisions (tenant_reference, policy_revision);

ALTER TABLE mc_syn.registry_revisions ADD CONSTRAINT registry_revisions_fk_0 FOREIGN KEY (tenant_reference, actor_reference) REFERENCES mc_syn.subjects (tenant_reference, subject_reference);

ALTER TABLE mc_syn.registry_revisions ADD CONSTRAINT registry_revisions_fk_1 FOREIGN KEY (tenant_reference, policy_revision) REFERENCES mc_syn.policy_revisions (tenant_reference, policy_revision);

ALTER TABLE mc_syn.registry_heads ADD CONSTRAINT registry_heads_fk_0 FOREIGN KEY (tenant_reference, record_reference, revision) REFERENCES mc_syn.registry_revisions (tenant_reference, record_reference, revision);

ALTER TABLE mc_syn.approval_evidence ADD CONSTRAINT approval_evidence_fk_0 FOREIGN KEY (tenant_reference, record_reference, record_revision) REFERENCES mc_syn.registry_revisions (tenant_reference, record_reference, revision);

ALTER TABLE mc_syn.approval_evidence ADD CONSTRAINT approval_evidence_fk_1 FOREIGN KEY (tenant_reference, grantor_reference) REFERENCES mc_syn.subjects (tenant_reference, subject_reference);

ALTER TABLE mc_syn.approval_evidence ADD CONSTRAINT approval_evidence_fk_2 FOREIGN KEY (tenant_reference, policy_revision) REFERENCES mc_syn.policy_revisions (tenant_reference, policy_revision);

ALTER TABLE mc_syn.approval_revocations ADD CONSTRAINT approval_revocations_fk_0 FOREIGN KEY (tenant_reference, evidence_reference) REFERENCES mc_syn.approval_evidence (tenant_reference, evidence_reference);

ALTER TABLE mc_syn.approval_revocations ADD CONSTRAINT approval_revocations_fk_1 FOREIGN KEY (tenant_reference, actor_reference) REFERENCES mc_syn.subjects (tenant_reference, subject_reference);

ALTER TABLE mc_syn.packet_revisions ADD CONSTRAINT packet_revisions_fk_0 FOREIGN KEY (tenant_reference, registry_reference, registry_revision) REFERENCES mc_syn.registry_revisions (tenant_reference, record_reference, revision);

ALTER TABLE mc_syn.packet_revisions ADD CONSTRAINT packet_revisions_fk_1 FOREIGN KEY (tenant_reference, actor_reference) REFERENCES mc_syn.subjects (tenant_reference, subject_reference);

ALTER TABLE mc_syn.packet_revisions ADD CONSTRAINT packet_revisions_fk_2 FOREIGN KEY (tenant_reference, policy_revision) REFERENCES mc_syn.policy_revisions (tenant_reference, policy_revision);

ALTER TABLE mc_syn.packet_heads ADD CONSTRAINT packet_heads_fk_0 FOREIGN KEY (tenant_reference, packet_reference, revision) REFERENCES mc_syn.packet_revisions (tenant_reference, packet_reference, revision);

ALTER TABLE mc_syn.journey_events ADD CONSTRAINT journey_events_fk_0 FOREIGN KEY (tenant_reference, packet_reference, packet_revision) REFERENCES mc_syn.packet_revisions (tenant_reference, packet_reference, revision);

ALTER TABLE mc_syn.journey_events ADD CONSTRAINT journey_events_fk_1 FOREIGN KEY (tenant_reference, actor_reference) REFERENCES mc_syn.subjects (tenant_reference, subject_reference);

ALTER TABLE mc_syn.journey_events ADD CONSTRAINT journey_events_fk_2 FOREIGN KEY (tenant_reference, policy_revision) REFERENCES mc_syn.policy_revisions (tenant_reference, policy_revision);

ALTER TABLE mc_syn.journey_heads ADD CONSTRAINT journey_heads_fk_0 FOREIGN KEY (tenant_reference, journey_reference, sequence) REFERENCES mc_syn.journey_events (tenant_reference, journey_reference, sequence);

CREATE FUNCTION mc_syn.reject_history_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Synthetic history is append-only'; END;
$$;

ALTER TABLE mc_syn.schema_migrations ENABLE ROW LEVEL SECURITY;

ALTER TABLE mc_syn.schema_migrations FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_scope ON mc_syn.schema_migrations TO "syn-runtime" USING (tenant_reference = current_setting('mission_control.tenant', true) AND dataset = 'synthetic') WITH CHECK (tenant_reference = current_setting('mission_control.tenant', true) AND dataset = 'synthetic');

GRANT SELECT ON mc_syn.schema_migrations TO "syn-runtime";

CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON mc_syn.schema_migrations FOR EACH ROW EXECUTE FUNCTION mc_syn.reject_history_mutation();

ALTER TABLE mc_syn.subjects ENABLE ROW LEVEL SECURITY;

ALTER TABLE mc_syn.subjects FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_scope ON mc_syn.subjects TO "syn-runtime" USING (tenant_reference = current_setting('mission_control.tenant', true) AND dataset = 'synthetic') WITH CHECK (tenant_reference = current_setting('mission_control.tenant', true) AND dataset = 'synthetic');

GRANT SELECT ON mc_syn.subjects TO "syn-runtime";

GRANT INSERT ON mc_syn.subjects TO "syn-runtime";

CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON mc_syn.subjects FOR EACH ROW EXECUTE FUNCTION mc_syn.reject_history_mutation();

ALTER TABLE mc_syn.policy_revisions ENABLE ROW LEVEL SECURITY;

ALTER TABLE mc_syn.policy_revisions FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_scope ON mc_syn.policy_revisions TO "syn-runtime" USING (tenant_reference = current_setting('mission_control.tenant', true) AND dataset = 'synthetic') WITH CHECK (tenant_reference = current_setting('mission_control.tenant', true) AND dataset = 'synthetic');

GRANT SELECT ON mc_syn.policy_revisions TO "syn-runtime";

GRANT INSERT ON mc_syn.policy_revisions TO "syn-runtime";

CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON mc_syn.policy_revisions FOR EACH ROW EXECUTE FUNCTION mc_syn.reject_history_mutation();

ALTER TABLE mc_syn.role_bindings ENABLE ROW LEVEL SECURITY;

ALTER TABLE mc_syn.role_bindings FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_scope ON mc_syn.role_bindings TO "syn-runtime" USING (tenant_reference = current_setting('mission_control.tenant', true) AND dataset = 'synthetic') WITH CHECK (tenant_reference = current_setting('mission_control.tenant', true) AND dataset = 'synthetic');

GRANT SELECT ON mc_syn.role_bindings TO "syn-runtime";

GRANT INSERT ON mc_syn.role_bindings TO "syn-runtime";

CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON mc_syn.role_bindings FOR EACH ROW EXECUTE FUNCTION mc_syn.reject_history_mutation();

ALTER TABLE mc_syn.registry_revisions ENABLE ROW LEVEL SECURITY;

ALTER TABLE mc_syn.registry_revisions FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_scope ON mc_syn.registry_revisions TO "syn-runtime" USING (tenant_reference = current_setting('mission_control.tenant', true) AND dataset = 'synthetic') WITH CHECK (tenant_reference = current_setting('mission_control.tenant', true) AND dataset = 'synthetic');

GRANT SELECT ON mc_syn.registry_revisions TO "syn-runtime";

GRANT INSERT ON mc_syn.registry_revisions TO "syn-runtime";

CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON mc_syn.registry_revisions FOR EACH ROW EXECUTE FUNCTION mc_syn.reject_history_mutation();

ALTER TABLE mc_syn.registry_heads ENABLE ROW LEVEL SECURITY;

ALTER TABLE mc_syn.registry_heads FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_scope ON mc_syn.registry_heads TO "syn-runtime" USING (tenant_reference = current_setting('mission_control.tenant', true) AND dataset = 'synthetic') WITH CHECK (tenant_reference = current_setting('mission_control.tenant', true) AND dataset = 'synthetic');

GRANT SELECT ON mc_syn.registry_heads TO "syn-runtime";

GRANT INSERT ON mc_syn.registry_heads TO "syn-runtime";

GRANT UPDATE ON mc_syn.registry_heads TO "syn-runtime";

ALTER TABLE mc_syn.approval_evidence ENABLE ROW LEVEL SECURITY;

ALTER TABLE mc_syn.approval_evidence FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_scope ON mc_syn.approval_evidence TO "syn-runtime" USING (tenant_reference = current_setting('mission_control.tenant', true) AND dataset = 'synthetic') WITH CHECK (tenant_reference = current_setting('mission_control.tenant', true) AND dataset = 'synthetic');

GRANT SELECT ON mc_syn.approval_evidence TO "syn-runtime";

GRANT INSERT ON mc_syn.approval_evidence TO "syn-runtime";

CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON mc_syn.approval_evidence FOR EACH ROW EXECUTE FUNCTION mc_syn.reject_history_mutation();

ALTER TABLE mc_syn.approval_revocations ENABLE ROW LEVEL SECURITY;

ALTER TABLE mc_syn.approval_revocations FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_scope ON mc_syn.approval_revocations TO "syn-runtime" USING (tenant_reference = current_setting('mission_control.tenant', true) AND dataset = 'synthetic') WITH CHECK (tenant_reference = current_setting('mission_control.tenant', true) AND dataset = 'synthetic');

GRANT SELECT ON mc_syn.approval_revocations TO "syn-runtime";

GRANT INSERT ON mc_syn.approval_revocations TO "syn-runtime";

CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON mc_syn.approval_revocations FOR EACH ROW EXECUTE FUNCTION mc_syn.reject_history_mutation();

ALTER TABLE mc_syn.packet_revisions ENABLE ROW LEVEL SECURITY;

ALTER TABLE mc_syn.packet_revisions FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_scope ON mc_syn.packet_revisions TO "syn-runtime" USING (tenant_reference = current_setting('mission_control.tenant', true) AND dataset = 'synthetic') WITH CHECK (tenant_reference = current_setting('mission_control.tenant', true) AND dataset = 'synthetic');

GRANT SELECT ON mc_syn.packet_revisions TO "syn-runtime";

GRANT INSERT ON mc_syn.packet_revisions TO "syn-runtime";

CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON mc_syn.packet_revisions FOR EACH ROW EXECUTE FUNCTION mc_syn.reject_history_mutation();

ALTER TABLE mc_syn.packet_heads ENABLE ROW LEVEL SECURITY;

ALTER TABLE mc_syn.packet_heads FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_scope ON mc_syn.packet_heads TO "syn-runtime" USING (tenant_reference = current_setting('mission_control.tenant', true) AND dataset = 'synthetic') WITH CHECK (tenant_reference = current_setting('mission_control.tenant', true) AND dataset = 'synthetic');

GRANT SELECT ON mc_syn.packet_heads TO "syn-runtime";

GRANT INSERT ON mc_syn.packet_heads TO "syn-runtime";

GRANT UPDATE ON mc_syn.packet_heads TO "syn-runtime";

ALTER TABLE mc_syn.journey_events ENABLE ROW LEVEL SECURITY;

ALTER TABLE mc_syn.journey_events FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_scope ON mc_syn.journey_events TO "syn-runtime" USING (tenant_reference = current_setting('mission_control.tenant', true) AND dataset = 'synthetic') WITH CHECK (tenant_reference = current_setting('mission_control.tenant', true) AND dataset = 'synthetic');

GRANT SELECT ON mc_syn.journey_events TO "syn-runtime";

GRANT INSERT ON mc_syn.journey_events TO "syn-runtime";

CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON mc_syn.journey_events FOR EACH ROW EXECUTE FUNCTION mc_syn.reject_history_mutation();

ALTER TABLE mc_syn.journey_heads ENABLE ROW LEVEL SECURITY;

ALTER TABLE mc_syn.journey_heads FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_scope ON mc_syn.journey_heads TO "syn-runtime" USING (tenant_reference = current_setting('mission_control.tenant', true) AND dataset = 'synthetic') WITH CHECK (tenant_reference = current_setting('mission_control.tenant', true) AND dataset = 'synthetic');

GRANT SELECT ON mc_syn.journey_heads TO "syn-runtime";

GRANT INSERT ON mc_syn.journey_heads TO "syn-runtime";

GRANT UPDATE ON mc_syn.journey_heads TO "syn-runtime";

ALTER TABLE mc_syn.idempotency_receipts ENABLE ROW LEVEL SECURITY;

ALTER TABLE mc_syn.idempotency_receipts FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_scope ON mc_syn.idempotency_receipts TO "syn-runtime" USING (tenant_reference = current_setting('mission_control.tenant', true) AND dataset = 'synthetic') WITH CHECK (tenant_reference = current_setting('mission_control.tenant', true) AND dataset = 'synthetic');

GRANT SELECT ON mc_syn.idempotency_receipts TO "syn-runtime";

GRANT INSERT ON mc_syn.idempotency_receipts TO "syn-runtime";

CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON mc_syn.idempotency_receipts FOR EACH ROW EXECUTE FUNCTION mc_syn.reject_history_mutation();

ALTER TABLE mc_syn.security_decisions ENABLE ROW LEVEL SECURITY;

ALTER TABLE mc_syn.security_decisions FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_scope ON mc_syn.security_decisions TO "syn-runtime" USING (tenant_reference = current_setting('mission_control.tenant', true) AND dataset = 'synthetic') WITH CHECK (tenant_reference = current_setting('mission_control.tenant', true) AND dataset = 'synthetic');

GRANT SELECT ON mc_syn.security_decisions TO "syn-runtime";

GRANT INSERT ON mc_syn.security_decisions TO "syn-runtime";

CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON mc_syn.security_decisions FOR EACH ROW EXECUTE FUNCTION mc_syn.reject_history_mutation();

REVOKE ALL ON FUNCTION mc_syn.reject_history_mutation() FROM PUBLIC;

-- No DELETE, TRUNCATE, DDL, ownership, or BYPASSRLS privilege is granted to runtime.
